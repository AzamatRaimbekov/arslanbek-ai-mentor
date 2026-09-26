#!/usr/bin/env python3
"""Сбор данных для школы: промпты и срезы по ученику уходят на единый бэкенд.

  telemetry.py prompt                      # stdin: JSON хука UserPromptSubmit
  telemetry.py summary --level N --stage "..." --summary "..." \
                       [--strengths ..] [--struggles ..] [--next ..] [--session ID]
  telemetry.py profile                     # отправить student-profile.md
  telemetry.py flush                       # досылает очередь
  telemetry.py status                      # что настроено и сколько ждёт отправки
  telemetry.py consent yes|no|show         # согласие ученика на сбор данных

Без явного согласия ученика («consent yes») ничего не собирается и не отправляется.

Работает без зависимостей. Ни одна команда не падает с ошибкой на хук:
нет сети или бэкенда — записи ждут в очереди и уходят позже.
"""
import argparse, getpass, json, os, platform, re, secrets, shlex, socket, subprocess
import sys, time, urllib.request, uuid
from datetime import datetime, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get("ARSLANBEK_STATE", Path.home() / ".claude" / ".arslanbek"))
QUEUE = STATE / "queue"
SESSIONS = STATE / "sessions"
LOCK = STATE / "flush.lock"
CONSENT = STATE / "consent.json"
DELIVERY = STATE / "delivery.json"
REVOKE = STATE / "revoke-pending.json"
CONSENT_VERSION = 2
SKILL_VERSION = "telemetry-2"
PROFILE = SKILL / "references" / "student-profile.md"
QUEUE_MAX = 5000
BATCH = 100
# срез просим на 3-м промпте сессии и дальше каждые 15
SUMMARY_FIRST, SUMMARY_EVERY = 3, 15


# ── настройки ──────────────────────────────────────────────────────────────

def config():
    cfg = {}
    for f in [SKILL / "telemetry.conf", SKILL / "telemetry.local.conf"]:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"')
    url = os.environ.get("ARSLANBEK_TELEMETRY_URL", cfg.get("SUPABASE_URL", "")).rstrip("/")
    key = os.environ.get("ARSLANBEK_TELEMETRY_KEY", cfg.get("SUPABASE_ANON_KEY", ""))
    off = os.environ.get("ARSLANBEK_TELEMETRY", "").lower() in ("0", "off", "false")
    return url, key, off


def consent():
    """'yes', 'no' или '' — если ученика ещё не спрашивали."""
    try:
        a = json.loads(CONSENT.read_text()).get("answer", "")
        return a if a in ("yes", "no") else ""
    except (OSError, ValueError):
        return ""


def consent_record():
    try:
        return json.loads(CONSENT.read_text())
    except (OSError, ValueError):
        return {}


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + "." + secrets.token_hex(4) + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False)
    tmp.replace(path)


def delivery_status(**values):
    try:
        old = json.loads(DELIVERY.read_text())
    except (OSError, ValueError):
        old = {}
    private_write(DELIVERY, {**old, **values})


def device():
    f = STATE / "device.json"
    try:
        d = json.loads(f.read_text())
        if d.get("device_id") and len(d.get("secret", "")) >= 32:
            return d
    except (OSError, ValueError):
        pass
    d = {"device_id": str(uuid.uuid4()), "secret": secrets.token_hex(32)}
    private_write(f, d)
    return d


def _git(key):
    try:
        return subprocess.run(["git", "config", "--global", key], capture_output=True,
                              text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def identity():
    acc = {}
    try:
        acc = json.loads((Path.home() / ".claude.json").read_text()).get("oauthAccount") or {}
    except (OSError, ValueError):
        pass
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    return {
        "claude_email": acc.get("emailAddress", ""),
        "claude_name": acc.get("fullName") or acc.get("displayName", ""),
        "claude_org": acc.get("organizationName", ""),
        "git_email": _git("user.email"),
        "git_name": _git("user.name"),
        "os_user": user,
        "hostname": socket.gethostname(),
        "os": platform.platform(terse=True),
        "skill_version": SKILL_VERSION,
        "consent_version": consent_record().get("version", 1),
        "consented_at": consent_record().get("ts"),
        "analysis_allowed": consent() == "yes" and consent_record().get("version", 1) >= CONSENT_VERSION,
    }


# ── вырезаем секреты до того, как текст покинет машину ─────────────────────

REDACT = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[ключ скрыт]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "[ключ скрыт]"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"), "[ключ скрыт]"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[ключ скрыт]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "[ключ скрыт]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "[ключ скрыт]"),
    (re.compile(r"\b(?:sbp|sb_secret|sb_publishable|vercel|glpat|npm)_[A-Za-z0-9_\-]{16,}"), "[ключ скрыт]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), "[токен скрыт]"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b"), "[токен скрыт]"),  # бот Telegram
    (re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:)[^\s@/]+(@)", re.I), r"\1[пароль скрыт]\2"),
    (re.compile(r"(\b(?:password|passwd|pwd|пароль|secret|token|api[_\-]?key|access[_\-]?key|"
                r"client[_\-]?secret|private[_\-]?key)\b[\"']?\s*[:=]\s*)[\"']?[^\s\"',;]+", re.I),
     r"\1[скрыто]"),
]


def redact(text):
    for rx, sub in REDACT:
        text = rx.sub(sub, text)
    return text


# ── очередь ────────────────────────────────────────────────────────────────

def enqueue(rec):
    QUEUE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if len(list(QUEUE.glob("*.json"))) >= QUEUE_MAX:
        delivery_status(error="queue_full", failed_at=now_iso())
        raise RuntimeError("Очередь заполнена: новая запись не сохранена. Проверьте telemetry.py status.")
    rec = {"event_id": str(uuid.uuid4()), "ts": now_iso(), **rec}
    name = f"{time.time_ns()}-{secrets.token_hex(3)}.json"
    private_write(QUEUE / name, rec)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def spawn_flush():
    subprocess.Popen([sys.executable, __file__, "flush"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def api_headers(key):
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def post(url, key, dev, prompts, summary):
    body = json.dumps({
        "p_device": dev["device_id"], "p_secret": dev["secret"], "p_identity": identity(),
        "p_prompts": prompts, "p_summary": summary,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{url}/rest/v1/rpc/ingest", data=body, method="POST", headers=api_headers(key))
    with urllib.request.urlopen(req, timeout=15) as r:
        return 200 <= r.status < 300 and json.load(r).get("ok") is True


def send_revocation():
    url, key, _ = config()
    if not REVOKE.exists() or not url or not key:
        return
    try:
        dev = json.loads((STATE / "device.json").read_text())
        body = json.dumps({"p_device": dev["device_id"], "p_secret": dev["secret"]}).encode()
        req = urllib.request.Request(f"{url}/rest/v1/rpc/revoke_analysis_consent", data=body,
                                     method="POST", headers=api_headers(key))
        with urllib.request.urlopen(req, timeout=15):
            REVOKE.unlink(missing_ok=True)
    except Exception:
        delivery_status(error="consent_revocation_pending", failed_at=now_iso())


def take_lock():
    try:
        LOCK.mkdir(parents=True)
        return True
    except FileExistsError:
        if time.time() - LOCK.stat().st_mtime > 1200:  # не отбираем блокировку у длинной отправки
            LOCK.rmdir()
            return take_lock()
        return False


def flush():
    send_revocation()
    url, key, off = config()
    if off or consent() != "yes" or consent_record().get("version", 1) < CONSENT_VERSION or not url or not key or not QUEUE.exists() or not take_lock():
        return 0
    sent = 0
    try:
        dev = device()
        files = sorted(QUEUE.glob("*.json"))
        recs = []
        for f in files:
            try:
                recs.append((f, json.loads(f.read_text(encoding="utf-8"))))
                if not recs[-1][1].get("event_id"):
                    recs[-1][1]["event_id"] = str(uuid.uuid4())
                    recs[-1][1].setdefault("ts", datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat())
                    private_write(f, recs[-1][1])
            except (OSError, ValueError):
                delivery_status(error="invalid_queue_record", failed_at=now_iso())
                continue
        prompts = [(f, r) for f, r in recs if r.get("type") == "prompt"]
        summaries = [(f, r) for f, r in recs if r.get("type") == "summary"]
        for i in range(0, len(prompts), BATCH):
            if consent() != "yes" or config()[2]:
                return sent
            chunk = prompts[i:i + BATCH]
            payload = [{k: r.get(k) for k in ("event_id", "session_id", "project", "prompt", "ts")} for _, r in chunk]
            if not post(url, key, dev, payload, None):
                delivery_status(error="invalid_server_acknowledgement", failed_at=now_iso())
                return sent
            for f, _ in chunk:
                f.unlink(missing_ok=True)
            sent += len(chunk)
        for f, r in summaries:
            if consent() != "yes" or config()[2]:
                return sent
            if not post(url, key, dev, [], {k: v for k, v in r.items() if k != "type"}):
                delivery_status(error="invalid_server_acknowledgement", failed_at=now_iso())
                return sent
            f.unlink(missing_ok=True)
            sent += 1
        if sent:
            delivery_status(error=None, last_success=now_iso(), sent_last_batch=sent)
    except Exception as error:
        code = getattr(error, "code", None)
        delivery_status(error=f"http_{code}" if code else type(error).__name__, failed_at=now_iso())
    finally:
        try:
            LOCK.rmdir()
        except OSError:
            pass
    return sent


# ── команды ────────────────────────────────────────────────────────────────

def cmd_prompt(_):
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    text = (data.get("prompt") or "").strip()
    _, _, off = config()
    if not text or off:
        return
    session = re.sub(r"[^A-Za-z0-9_-]", "_", str(data.get("session_id") or ""))[:100]
    answer = consent()
    if answer == "no":
        return
    if not answer or consent_record().get("version", 1) < CONSENT_VERSION:
        ask_consent(session)
        return
    cwd = data.get("cwd") or os.getcwd()
    enqueue({"type": "prompt", "session_id": session, "project": os.path.basename(cwd.rstrip("/")),
             "prompt": redact(text), "ts": now_iso()})
    spawn_flush()

    # сколько промптов в сессии — пора ли наставнику прислать срез
    if session:
        SESSIONS.mkdir(parents=True, exist_ok=True)
        f = SESSIONS / re.sub(r"[^A-Za-z0-9_\-]", "_", session)
        n = int(f.read_text() or 0) + 1 if f.exists() else 1
        f.write_text(str(n))
        if n == SUMMARY_FIRST or (n > SUMMARY_FIRST and n % SUMMARY_EVERY == 0):
            print(f"""<arslanbek-report priority="must-follow">
Это {n}-й промпт сессии — пора обновить срез по ученику. После ответа на запрос
выполни одну команду и последней строкой ответа коротко скажи ученику,
что поставил срез в очередь для наставника и какой уровень наблюдал:
bash ~/.claude/skills/arslanbek-ai-mentor/scripts/report.sh --session "{session}" \\
  --level <0-5> --stage "<этап одной фразой>" --summary "<2-3 предложения: что делал, как справлялся>" \\
  --strengths "<что получается>" --struggles "<что даётся тяжело>" --next "<следующий шаг>"
Уровень — по шкале references/ai-levels.md. Если доказательств мало, используй --level unknown.
Не считай свой код достижением ученика. Укажи наблюдения ученика и ограничения
в references/honest-reporting.md. «В очереди» не означает «доставлено».
</arslanbek-report>""")
    # старые счётчики сессий не копим
    if SESSIONS.exists():
        cutoff = time.time() - 14 * 86400
        for f in SESSIONS.iterdir():
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)


def ask_consent(session):
    """Пока ученик не ответил — ничего не пишем, а раз в сессию просим агента спросить."""
    if session:
        SESSIONS.mkdir(parents=True, exist_ok=True)
        f = SESSIONS / (re.sub(r"[^A-Za-z0-9_\-]", "_", session)[:100] + f".consent-v{CONSENT_VERSION}.asked")
        if f.exists():
            return
        f.write_text("1")
    print("""<arslanbek-consent priority="must-follow">
Нужно согласие версии 2 на данные для школы и ИИ-анализ — сейчас НИЧЕГО не отправляется.
Ответь на запрос, а в конце задай вопрос о согласии своими словами, перечислив, что уходит:
  • тексты промптов (пароли и ключи вырезаются до отправки);
  • срезы наставника: уровень владения ИИ 0–5, этап, что получается и что трудно;
  • email и имя из аккаунта Claude и git, имя компьютера и ОС — чтобы школа понимала, чьи это данные;
  • отрывки промптов и срезов обрабатываются внешним ИИ-сервисом для отчёта команды.
Отчёты доступны администратору школы. Передумать можно в любой момент.
Если ранее было согласие только на сбор, объясни расширение и спроси заново.
Ответил «да» —  bash ~/.claude/skills/arslanbek-ai-mentor/scripts/consent.sh yes
Ответил «нет» — bash ~/.claude/skills/arslanbek-ai-mentor/scripts/consent.sh no
Сам команду без ответа ученика не запускай.
</arslanbek-consent>""")


def profile_md():
    try:
        return PROFILE.read_text(encoding="utf-8")
    except OSError:
        return ""


def cmd_summary(a):
    if consent() != "yes" or consent_record().get("version", 1) < CONSENT_VERSION:
        sys.exit("ученик не давал согласия — срез не отправлен")
    if a.level is not None and not 0 <= a.level <= 5:
        sys.exit("level: от 0 до 5")
    if config()[2]:
        sys.exit("сбор выключен — срез не сохранён")
    enqueue({"type": "summary", "session_id": a.session[:100], "project": os.path.basename(os.getcwd()),
             "level": a.level, "stage": a.stage, "summary": redact(a.summary),
             "strengths": redact(a.strengths), "struggles": redact(a.struggles),
             "next_step": redact(a.next), "profile_md": redact(profile_md())})
    spawn_flush()
    print("Срез сохранён в очередь. Доставку показывает telemetry.py status.")


def cmd_profile(_):
    if consent() != "yes" or consent_record().get("version", 1) < CONSENT_VERSION or config()[2]:
        return
    md = profile_md()
    if md:
        enqueue({"type": "summary", "profile_md": redact(md)})
        spawn_flush()


def cmd_flush(_):
    flush()


def cmd_consent(a):
    if a.answer == "show":
        print({"yes": "согласие дано", "no": "ученик отказался"}.get(consent(), "ученика ещё не спрашивали"))
        return
    private_write(CONSENT, {"answer": a.answer, "ts": now_iso(), "version": CONSENT_VERSION})
    if a.answer == "no" and QUEUE.exists():
        for f in QUEUE.glob("*.json"):  # что не успело уйти — не отправляем
            f.unlink(missing_ok=True)
    if a.answer == "no" and (STATE / "device.json").exists():
        private_write(REVOKE, {"requested_at": now_iso()})
        spawn_flush()
    if a.answer == "yes":
        enqueue({"type": "summary"})  # register only after explicit consent
        spawn_flush()
    print("ok: сбор включён" if a.answer == "yes" else "ok: сбор выключен, очередь очищена")


def cmd_status(_):
    url, key, off = config()
    n = len(list(QUEUE.glob("*.json"))) if QUEUE.exists() else 0
    print(f"бэкенд:   {url or 'НЕ НАСТРОЕН (telemetry.conf)'}")
    print(f"ключ:     {'есть' if key else 'нет'}")
    print(f"выключен: {'да (ARSLANBEK_TELEMETRY)' if off else 'нет'}")
    print(f"согласие: {consent() or 'не спрашивали'}")
    print(f"версия согласия: {consent_record().get('version', 'нет')}")
    print(f"в очереди: {n}")
    print(f"отзыв согласия ожидает сети: {'да' if REVOKE.exists() else 'нет'}")
    try:
        status = json.loads(DELIVERY.read_text())
    except (OSError, ValueError):
        status = {}
    print(f"последняя успешная доставка: {status.get('last_success', 'ещё не было')}")
    print(f"последняя ошибка: {status.get('error') or 'нет'}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prompt").set_defaults(fn=cmd_prompt)
    s = sub.add_parser("summary")
    s.add_argument("--level", type=lambda v: None if v == "unknown" else int(v), required=True)
    s.add_argument("--stage", default="")
    s.add_argument("--summary", default="")
    s.add_argument("--strengths", default="")
    s.add_argument("--struggles", default="")
    s.add_argument("--next", default="")
    s.add_argument("--session", default="")
    s.set_defaults(fn=cmd_summary)
    sub.add_parser("profile").set_defaults(fn=cmd_profile)
    sub.add_parser("flush").set_defaults(fn=cmd_flush)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    c = sub.add_parser("consent")
    c.add_argument("answer", choices=("yes", "no", "show"))
    c.set_defaults(fn=cmd_consent)
    a = p.parse_args()
    try:
        a.fn(a)
    except Exception as error:
        if a.cmd in ("prompt", "flush", "profile"):
            print(f"arslanbek telemetry: {type(error).__name__}; проверьте status", file=sys.stderr)
        else:
            raise


if __name__ == "__main__":
    main()
