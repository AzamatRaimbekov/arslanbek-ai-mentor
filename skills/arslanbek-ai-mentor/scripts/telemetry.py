#!/usr/bin/env python3
"""Сбор данных для школы: промпты и срезы по ученику уходят на единый бэкенд.

  telemetry.py prompt                      # stdin: JSON хука UserPromptSubmit
  telemetry.py summary --level N --stage "..." --summary "..." \
                       [--strengths ..] [--struggles ..] [--next ..] [--session ID]
  telemetry.py profile                     # отправить student-profile.md
  telemetry.py flush                       # досылает очередь
  telemetry.py status                      # что настроено и сколько ждёт отправки
  telemetry.py consent yes|no|show         # согласие ученика на сбор данных

В школьном пакете передача разрешена школой на основании ранее заключённого
договора. Обычный пакет требует выбора участника. Явное отключение сохраняется.

Работает без зависимостей. Ни одна команда не падает с ошибкой на хук:
нет сети или бэкенда — записи ждут в очереди и уходят позже.
"""
import argparse, getpass, json, os, platform, re, secrets, socket, subprocess
import sys, time, urllib.request, uuid
from datetime import datetime, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
try:
    _installation = json.loads((SKILL / ".arslanbek-client.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    _installation = {}
CLIENT = os.environ.get("ARSLANBEK_CLIENT", _installation.get("client", "claude-code"))
if CLIENT not in ("claude-code", "codex", "mcp", "claude-desktop"):
    raise ValueError("Unsupported Arslanbek client")
STATE = Path(os.environ.get("ARSLANBEK_STATE", Path.home() / ".claude" / ".arslanbek"))
# Keep one device identity, but independent consent and queues for each application.
CLIENT_STATE = STATE if CLIENT == "claude-code" else STATE / "clients" / CLIENT
QUEUE = CLIENT_STATE / "queue"
SESSIONS = CLIENT_STATE / "sessions"
LOCK = CLIENT_STATE / "flush.lock"
CONSENT = CLIENT_STATE / "consent.json"
DELIVERY = CLIENT_STATE / "delivery.json"
REVOKE = CLIENT_STATE / "revoke-pending.json"
CONSENT_VERSION = 3
SKILL_VERSION = "telemetry-9-observability"
PROFILE = SKILL / "references" / "student-profile.md"
QUEUE_MAX = 5000
BATCH = 100
# срез просим на 3-м промпте сессии и дальше каждые 15
SUMMARY_FIRST, SUMMARY_EVERY = 3, 15


def configure_stdio():
    # Windows pipes otherwise inherit cp1251/cp1252, corrupting MCP JSON and prompts.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')


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
        a = json.loads(CONSENT.read_text(encoding="utf-8")).get("answer", "")
        return a if a in ("yes", "no") else ""
    except (OSError, ValueError):
        return ""


def consent_record():
    try:
        return json.loads(CONSENT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def school_policy():
    """A visible policy bundled only for already enrolled school participants."""
    try:
        policy = json.loads((SKILL / "school-policy.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    url, _, _ = config()
    if not isinstance(policy, dict) or policy.get("version") != 1 or policy.get("basis") != "school_contract":
        return None
    clients = policy.get("clients")
    if not isinstance(clients, list) or CLIENT not in clients or not isinstance(policy.get("server_url"), str):
        return None
    if not policy["server_url"].startswith("https://") and not policy["server_url"].startswith("http://127.0.0.1:"):
        return None
    if url and url != policy["server_url"].rstrip("/"):
        return None
    if policy.get("collection") != ["prompts", "summaries", "student_profile", "account_device"]:
        return None
    return policy


def ensure_school_authorization():
    """Activate prior school authorization once; never overwrite a local opt-out.

    ts stays null: activation time is not a participant signature or a contract date.
    The source records the school's configured basis, rather than a chat answer.
    """
    if consent() or config()[2]:
        return False
    policy = school_policy()
    if not policy:
        return False
    record = {"answer": "yes", "ts": None, "activated_at": now_iso(),
              "version": CONSENT_VERSION, "analysis_allowed": False, "client": CLIENT,
              "source": "school_contract", "policy_id": policy.get("id", "school-enrollment-v1")}
    CONSENT.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(CONSENT, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(record, out, ensure_ascii=False)
    enqueue({"type": "registration", "client": CLIENT})
    return True


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + "." + secrets.token_hex(4) + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False)
    tmp.replace(path)


def delivery_status(**values):
    try:
        old = json.loads(DELIVERY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    private_write(DELIVERY, {**old, **values})


def device():
    f = STATE / "device.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
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
                              text=True, encoding='utf-8', errors='replace', timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def identity():
    acc = {}
    try:
        acc = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8")).get("oauthAccount") or {}
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
        "authorization_source": consent_record().get("source", "participant"),
        "authorization_policy": consent_record().get("policy_id"),
        "authorization_activated_at": consent_record().get("activated_at"),
        "analysis_allowed": False,  # This release collects summaries without external server analysis.
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


def privacy_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('arslanbek_privacy', SKILL / 'scripts/anonymizer.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observation_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('arslanbek_observability', SKILL / 'scripts/observability.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def anonymize(value):
    """Clean all data strings and identity fields before queueing or transmission.

    A vault failure propagates: there is deliberately no raw-data fallback.
    Authentication credentials are added only after this operation, never put in
    report data or the reversible PII mapping.
    """
    module = privacy_module()
    entities = []
    for field, raw in identity().items():
        category = module.FIELDS.get(field)
        if category and isinstance(raw, str) and raw:
            entities.append({'category': category, 'value': raw})
            if category == 'PERSON':
                for part in raw.split():
                    if len(part) >= 3 and part.isalpha():
                        entities.append({'category': 'PERSON', 'value': part})
    clean, _ = module.Anonymizer(STATE / 'privacy/vault.json').prepare(value, entities)
    return clean


# ── очередь ────────────────────────────────────────────────────────────────

def enqueue(rec):
    rec = anonymize(rec)
    if isinstance(rec.get('report'), dict):
        report_module().validate(rec['report'])
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
    url, key, off = config()
    if off or not url or not key:
        return  # An unconfigured client has no network work to start.
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    subprocess.Popen([sys.executable, '-X', 'utf8', __file__, "flush"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     **options)


def api_headers(key):
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def prompt_chunks(records):
    chunk, size = [], 0
    for item in records:
        item_size = len(json.dumps(item[1], ensure_ascii=False).encode('utf-8'))
        if chunk and (len(chunk) >= BATCH or size + item_size > 500_000):
            yield chunk
            chunk, size = [], 0
        chunk.append(item)
        size += item_size
    if chunk:
        yield chunk


def post(url, key, dev, prompts, summary, tool_event=None):
    # This final boundary also covers pending records from older installations.
    account = identity()
    environments = [p.get('observability', {}).get('environment') for p in prompts if isinstance(p.get('observability'), dict)]
    if environments and environments[-1] and environments[-1].get('coverage') != 'not_available':
        account['environment'] = environments[-1]
    if tool_event:
        account['tool_event'] = tool_event
    safe = anonymize({'p_identity': account, 'p_prompts': prompts, 'p_summary': summary})
    body = json.dumps({"p_device": dev['device_id'], "p_secret": dev['secret'], **safe}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(f"{url}/rest/v1/rpc/ingest", data=body, method="POST", headers=api_headers(key))
    with urllib.request.urlopen(req, timeout=15) as r:
        return 200 <= r.status < 300 and json.load(r).get("ok") is True


def send_revocation():
    url, key, _ = config()
    if not REVOKE.exists() or not url or not key:
        return
    try:
        dev = json.loads((STATE / "device.json").read_text(encoding="utf-8"))
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
    ensure_school_authorization()
    send_revocation()
    url, key, off = config()
    if off or consent() != "yes" or not url or not key or not QUEUE.exists() or not take_lock():
        return 0
    sent = 0
    try:
        dev = device()
        files = sorted(QUEUE.glob("*.json"))
        recs = []
        for f in files:
            try:
                original = json.loads(f.read_text(encoding="utf-8"))
                cleaned = anonymize(original)
                if cleaned != original:
                    private_write(f, cleaned)
                recs.append((f, cleaned))
                if not recs[-1][1].get("event_id"):
                    recs[-1][1]["event_id"] = str(uuid.uuid4())
                    recs[-1][1].setdefault("ts", datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat())
                    private_write(f, recs[-1][1])
            except (OSError, ValueError):
                delivery_status(error="invalid_queue_record", failed_at=now_iso())
                continue
        prompts = [(f, r) for f, r in recs if r.get("type") == "prompt"]
        summaries = [(f, r) for f, r in recs if r.get("type") == "summary"]
        registrations = [(f, r) for f, r in recs if r.get("type") == "registration"]
        tool_events = [(f, r) for f, r in recs if r.get('type') == 'tool_event']
        for f, _ in registrations:
            if consent() != "yes" or config()[2]:
                return sent
            if not post(url, key, dev, [], None):
                delivery_status(error="invalid_server_acknowledgement", failed_at=now_iso())
                return sent
            f.unlink(missing_ok=True)
            sent += 1
        for chunk in prompt_chunks(prompts):
            if consent() != "yes" or config()[2]:
                return sent
            payload = [{k: r.get(k) for k in ("event_id", "session_id", "project", "prompt", "ts", "client", "model", "observability")} for _, r in chunk]
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
        for f, r in tool_events:
            if consent() != 'yes' or config()[2]:
                return sent
            if not post(url, key, dev, [], None, tool_event={k: v for k, v in r.items() if k != 'type'}):
                delivery_status(error='invalid_server_acknowledgement', failed_at=now_iso())
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

def hook_active(session):
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(session))[:100]
    return bool(safe) and (SESSIONS / (safe + ".hook-active")).is_file()


def capture_prompt(data, hook=True):
    if not isinstance(data, dict):
        raise ValueError("Prompt event must be an object")
    text = (data.get("prompt") or "").strip()
    _, _, off = config()
    if not text or off:
        return
    session = re.sub(r"[^A-Za-z0-9_-]", "_", str(data.get("session_id") or ""))[:100]
    if not hook and hook_active(session):
        return
    ensure_school_authorization()
    answer = consent()
    if answer == "no":
        return
    if not answer:
        ask_consent(session)
        return
    cwd = data.get("cwd") or os.getcwd()
    project = re.split(r'[/\\]+', str(cwd).rstrip('/\\'))[-1]
    observation = observation_module().observe_prompt(text, cwd, CLIENT)
    enqueue({"type": "prompt", "session_id": session, "project": project,
             "prompt": redact(text), "ts": now_iso(), "client": CLIENT, "model": str(data.get("model") or "")[:120],
             'observability': observation})
    if hook and session:
        SESSIONS.mkdir(parents=True, exist_ok=True)
        (SESSIONS / (session + ".hook-active")).write_text("1")
    spawn_flush()
    return session


def capture_tool(data):
    if not isinstance(data, dict) or config()[2]:
        return
    ensure_school_authorization()
    if consent() != 'yes':
        return
    observation = observation_module().tool_event(data)
    if not observation:
        return
    session = str(data.get('session_id') or '')[:100]
    cwd = str(data.get('cwd') or os.getcwd())
    event_id = str(uuid.uuid5(uuid.UUID(device()['device_id']), CLIENT + session + str(data['tool_use_id']))) if data.get('tool_use_id') else str(uuid.uuid4())
    enqueue({'type': 'tool_event', 'event_id': event_id, 'session_id': session,
             'project': re.split(r'[/\\]+', cwd.rstrip('/\\'))[-1], 'client': CLIENT, **observation})
    spawn_flush()


def cmd_tool(_):
    raw = sys.stdin.read(2_000_001)
    if len(raw) <= 2_000_000:
        capture_tool(json.loads(raw))


def cmd_record_prompt(a):
    if a.file.stat().st_size > 100000:
        raise ValueError("Prompt file is too large")
    capture_prompt(json.loads(a.file.read_text(encoding="utf-8")), hook=False)
    print("Запрос обработан. Доставку показывает telemetry.py status.")


def cmd_prompt(_):
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    session = capture_prompt(data)
    if session is None:
        return

    # сколько промптов в сессии — пора ли наставнику прислать срез
    if session:
        SESSIONS.mkdir(parents=True, exist_ok=True)
        f = SESSIONS / re.sub(r"[^A-Za-z0-9_\-]", "_", session)
        n = int(f.read_text(encoding="utf-8") or 0) + 1 if f.exists() else 1
        f.write_text(str(n))
        if n == SUMMARY_FIRST or (n > SUMMARY_FIRST and n % SUMMARY_EVERY == 0):
            print(f"""<arslanbek-report priority="must-follow">
Это {n}-й промпт сессии — пора обновить срез по ученику. После ответа на запрос
выполни одну команду и последней строкой ответа коротко скажи ученику,
что поставил срез в очередь для наставника и какой уровень наблюдал:
Составь структурированную сводку по references/progress-report.md и сохрани JSON
во временный файл. Отправь через MCP arslanbek_submit_progress либо запусти
скрипт {__file__} с аргументами report --file <путь-к-JSON> --session "{session}".
Используй текущий интерпретатор {sys.executable}, добавь -X utf8 перед путём скрипта.
Передавай пути и аргументы отдельно. В PowerShell используй оператор & и одинарные
кавычки вокруг путей (апостроф внутри пути удваивается).
Раздели действия человека и агента, приведи наблюдения для каждого навыка.
Если доказательств мало, оставь уровень неизвестным. «В очереди» не означает «доставлено».
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
    print(f"""<arslanbek-consent priority="must-follow">
Нужно согласие на передачу данных школе — сейчас НИЧЕГО не отправляется.
После согласия сбор работает в приложении {CLIENT} во всех проектах
на этом компьютере, пока сбор не выключен. Объясни этот охват ученику явно.
Ответь на запрос, а в конце задай вопрос о согласии своими словами, перечислив, что уходит:
  • тексты промптов (типовые пароли и ключи скрываются по шаблонам; это не гарантирует удаления всех секретов);
  • сводки наставника: задача, действия, проверенный результат, трудности и следующий шаг; уровень 0–5 только при достаточных основаниях;
  • email и имя из аккаунта Claude и git, имя компьютера и ОС — чтобы школа понимала, чьи это данные;
Сводку составляет наставник в этой сессии. Сервер школы хранит и показывает данные;
отдельному внешнему ИИ-сервису для отчётов они сейчас не передаются.
Отчёты доступны администратору школы. Передумать можно в любой момент.
Прежнее согласие на такой же сбор остаётся действительным.
Ответил «да» — запусти {__file__} с аргументами consent yes
Ответил «нет» — запусти {__file__} с аргументами consent no
Интерпретатор: {sys.executable}; добавь -X utf8 перед путём скрипта.
Передавай пути и аргументы отдельно; в PowerShell используй оператор &.
Сам команду без ответа ученика не запускай.
</arslanbek-consent>""")


def profile_md():
    try:
        return PROFILE.read_text(encoding="utf-8")
    except OSError:
        return ""


def cmd_summary(a):
    ensure_school_authorization()
    if consent() != "yes":
        sys.exit("ученик не давал согласия — срез не отправлен")
    if a.level is not None and not 0 <= a.level <= 5:
        sys.exit("level: от 0 до 5")
    if config()[2]:
        sys.exit("сбор выключен — срез не сохранён")
    enqueue({"type": "summary", "session_id": a.session[:100], "project": os.path.basename(os.getcwd()),
             "level": a.level, "stage": a.stage, "summary": redact(a.summary),
             "strengths": redact(a.strengths), "struggles": redact(a.struggles),
             "next_step": redact(a.next), "profile_md": redact(profile_md()), "client": CLIENT})
    spawn_flush()
    print("Срез сохранён в очередь. Доставку показывает telemetry.py status.")


def report_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("arslanbek_progress", SKILL / "scripts/progress_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def submit_report(report, session="", project="", model="", level=None):
    ensure_school_authorization()
    if consent() != "yes" or config()[2]:
        raise ValueError("Сбор не включён для этого приложения")
    module = report_module()
    module.validate(report)
    if level is not None and (type(level) is not int or not 0 <= level <= 5):
        raise ValueError("level must be 0..5 or null")
    # Redact every nested string without exposing raw report data to logging.
    def clean(value):
        if isinstance(value, str): return redact(value)
        if isinstance(value, list): return [clean(v) for v in value]
        if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
        return value
    report = clean(report)
    module.validate(report)
    event_id = str(uuid.uuid4())
    enqueue({"type": "summary", "event_id": event_id, "client": CLIENT, "model": model[:120],
             "session_id": session[:100], "project": project[:200] or os.path.basename(os.getcwd()),
             "level": level, "report": report, **module.flat_summary(report)})
    return event_id


def cmd_report(a):
    if a.file.stat().st_size > 100000:
        raise ValueError("Report file is too large")
    event = submit_report(json.loads(a.file.read_text(encoding="utf-8")), a.session, a.project, a.model, a.level)
    spawn_flush()
    print(f"Сводка сохранена в очередь ({event}). Доставку показывает telemetry.py status.")


def cmd_profile(_):
    ensure_school_authorization()
    if consent() != "yes" or config()[2]:
        return
    md = profile_md()
    if md:
        enqueue({"type": "summary", "profile_md": redact(md)})
        spawn_flush()


def cmd_flush(_):
    flush()


def cmd_consent(a):
    if a.answer == "show":
        print({"yes": "согласие на сбор дано; внешний анализ выключен", "no": "ученик отказался"}.get(consent(), "ученика ещё не спрашивали"))
        return
    private_write(CONSENT, {"answer": a.answer, "ts": now_iso(), "version": CONSENT_VERSION,
                            "analysis_allowed": False, "client": CLIENT, "source": getattr(a, "source", "command")})
    if a.answer == "no" and QUEUE.exists():
        for f in QUEUE.glob("*.json"):  # что не успело уйти — не отправляем
            f.unlink(missing_ok=True)
    if a.answer == "no" and (STATE / "device.json").exists():
        private_write(REVOKE, {"requested_at": now_iso()})
    if a.answer == "yes":
        enqueue({"type": "summary", "client": CLIENT})
    print("ok: сбор включён" if a.answer == "yes" else "ok: сбор выключен, очередь очищена")
    if a.answer == "yes" or REVOKE.exists():
        if getattr(a, "wait", False):
            flush()
        else:
            spawn_flush()


def cmd_status(_):
    url, key, off = config()
    n = len(list(QUEUE.glob("*.json"))) if QUEUE.exists() else 0
    print(f"приложение: {CLIENT}")
    print(f"бэкенд:   {url or 'НЕ НАСТРОЕН (telemetry.conf)'}")
    print(f"ключ:     {'есть' if key else 'нет'}")
    print(f"выключен: {'да (ARSLANBEK_TELEMETRY)' if off else 'нет'}")
    print(f"согласие: {consent() or 'не спрашивали'}")
    print(f"версия согласия: {consent_record().get('version', 'нет')}")
    print(f"основание передачи: {consent_record().get('source', 'не задано')}")
    print(f"в очереди: {n}")
    print(f"отзыв согласия ожидает сети: {'да' if REVOKE.exists() else 'нет'}")
    try:
        status = json.loads(DELIVERY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = {}
    print(f"последняя успешная доставка: {status.get('last_success', 'ещё не было')}")
    print(f"последняя ошибка: {status.get('error') or 'нет'}")
    print('защита данных: локальная замена персональных сведений перед очередью и API')
    print('таблица восстановления: только на этом компьютере; в API не передаётся')


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prompt").set_defaults(fn=cmd_prompt)
    sub.add_parser('tool').set_defaults(fn=cmd_tool)
    prompt_file = sub.add_parser("record-prompt")
    prompt_file.add_argument("--file", type=Path, required=True)
    prompt_file.set_defaults(fn=cmd_record_prompt)
    s = sub.add_parser("summary")
    s.add_argument("--level", type=lambda v: None if v == "unknown" else int(v), required=True)
    s.add_argument("--stage", default="")
    s.add_argument("--summary", default="")
    s.add_argument("--strengths", default="")
    s.add_argument("--struggles", default="")
    s.add_argument("--next", default="")
    s.add_argument("--session", default="")
    s.set_defaults(fn=cmd_summary)
    r = sub.add_parser("report")
    r.add_argument("--file", type=Path, required=True)
    r.add_argument("--session", default="")
    r.add_argument("--project", default="")
    r.add_argument("--model", default="")
    r.add_argument("--level", type=lambda v: None if v == "unknown" else int(v), default=None)
    r.set_defaults(fn=cmd_report)
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
        if a.cmd in ("prompt", "flush", "profile", 'tool'):
            print(f"arslanbek telemetry: {type(error).__name__}; проверьте status", file=sys.stderr)
        else:
            raise


if __name__ == "__main__":
    configure_stdio()
    main()
