"""Persist chat + HTML defaults for a native client or an optional project."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

START = "<!-- arslanbek-answer-mode:start -->"
END = "<!-- arslanbek-answer-mode:end -->"
BLOCK = """<!-- arslanbek-answer-mode:start -->
## Формат ответов Ментора и visual-explainer

В этом проекте пользователь выбрал постоянный режим ответов после запуска
Ментора или visual-explainer. Прочитай `.arslanbek/answer-mode.json`:
`format: chat+html` включает правила ниже, `format: chat` отключает HTML.
Правило действует для всех последующих финальных ответов в проекте, включая
другие задачи и новые сессии; повторный вызов скилла не нужен.
Если в пользовательских инструкциях есть глобальная настройка Арсланбека,
прочитай также её state: format=chat отключает HTML во всех проектах.
Проектный format=chat отключает его только здесь. Прямая просьба пользователя
о формате имеет приоритет.

- В чате используй понятные смысловые блоки: заголовки `## ✅ [1 · Результат]`,
  скобки, линии `---`, жирные ключевые мысли и эмодзи по смыслу. Объясняй результат,
  причины, проверку и следующий шаг; объём выбирай по задаче и просьбе пользователя.
- Голос Арсланбека: пиши как старший брат-ментор в переписке — на «ты», тепло,
  разговорно, с юмором и открытым смехом 😂🤣. Эмодзи щедро: в каждом заголовке,
  в первой и последней строке и 1–2 в каждом блоке рядом с ключевой мыслью
  (🔥 🚀 💪 👀 🎯 ✨ 🤝 😅). Короткие живые фразы, без канцелярита. Человек расстроен
  или пропали данные/деньги — сначала поддержка, шутка потом. Отчёты школе — без шуток.
- К каждому финальному ответу создай отдельный HTML с тем же содержанием в
  `.arslanbek/answers/` и дай ссылку на реально созданный файл. HTML добавляет
  цветные блоки, линии, читаемые заголовки; схемы и интерактивность — по задаче.
  Цвет и статус должны иметь фактическое основание.
- Для обычных ответов используй `scripts/render_html.py` из фактически установленного
  Ментора или visual-explainer: один JSON создаёт совпадающий текст для чата и HTML.
  Для сложной схемы можно создать самостоятельный HTML, сохранив факты и объяснения
  в обеих версиях. Если файловый доступ отсутствует, дай HTML-артефакт или полный
  HTML в блоке кода и прямо сообщи об ограничении.
- Промежуточные сообщения, вывод инструментов и структурированные отчёты школе
  сохраняют свой формат. HTML не публикуй и не передавай в учебную телеметрию.
  Браузер открывай по просьбе пользователя.
- Явное «только чат» отменяет HTML на указанный период; «короче» сокращает обе версии.
  При отключении на весь проект сохрани `format: chat`; возвращай `chat+html` только
  по новой просьбе пользователя. Если нужен шаг человека, заверши блоком
  `[Что требуется от тебя]` с точным действием и ожидаемым результатом.
<!-- arslanbek-answer-mode:end -->"""


def managed_document(original, block=BLOCK):
    """Replace only our block, preserving the surrounding text and line endings."""
    newline = "\r\n" if "\r\n" in original else "\n"
    block = block.replace("\n", newline)
    starts, ends = original.count(START), original.count(END)
    if starts == ends == 0:
        separator = "" if not original else (newline if original.endswith(newline) else newline * 2)
        return original + separator + block + newline
    if starts != 1 or ends != 1 or original.index(END) < original.index(START):
        raise ValueError("Ambiguous answer-mode block; preserving the existing instructions")
    begin, end = original.index(START), original.index(END) + len(END)
    return original[:begin] + block + original[end:]


def read_file(path):
    if path.is_symlink():
        raise ValueError(f"Refusing to replace a symbolic link: {path}")
    return path.read_bytes() if path.exists() else None


def atomic_write(path, content):
    descriptor, temporary = tempfile.mkstemp(prefix=".answer-mode-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(content)
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def activate(project, enable=False, disable=False):
    project = Path(project).resolve(strict=True)
    if not project.is_dir() or project == Path(project.anchor) or project == Path.home():
        raise ValueError("Choose an existing project directory, rather than the home or filesystem root")
    state_dir = project / ".arslanbek"
    if state_dir.is_symlink():
        raise ValueError("The project answer-mode directory must not be a symbolic link")
    state_path = state_dir / "answer-mode.json"
    before = read_file(state_path)
    state = json.loads(before.decode("utf-8")) if before is not None else {"version": 1, "format": "chat+html"}
    if not isinstance(state, dict) or state.get("version") != 1 or state.get("format") not in ("chat", "chat+html"):
        raise ValueError("Unrecognized answer-mode state; preserving the existing choice")
    if enable:
        state["format"] = "chat+html"
    if disable:
        state["format"] = "chat"
    state_bytes = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    changes = [(state_path, before, state_bytes)]
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = project / name
        before = read_file(path)
        original = before.decode("utf-8") if before is not None else ""
        changes.append((path, before, managed_document(original).encode("utf-8")))
    # Validate both instruction files before writing anything.
    state_dir.mkdir(exist_ok=True)
    for path, before, content in changes:
        if read_file(path) != before:
            raise ValueError(f"File changed during activation; preserving it: {path}")
        if content != before:
            atomic_write(path, content)
    return state["format"]


NATIVE_CLIENTS = ("codex", "claude-code")
STATE_NAME = "arslanbek-answer-mode.json"
POINTER_NAME = ".arslanbek-answer-home.json"


def client_home(client, override=None):
    variable, directory = ("CODEX_HOME", ".codex") if client == "codex" else ("CLAUDE_CONFIG_DIR", ".claude")
    home = Path(override or os.environ.get(variable) or Path.home() / directory).expanduser().absolute()
    if home == Path(home.anchor) or home == Path.home() or home.is_symlink():
        raise ValueError("Choose the native application's configuration directory")
    return home


def selected_client(skill):
    client = os.environ.get("ARSLANBEK_CLIENT")
    if not client:
        marker = read_file(Path(skill) / ".arslanbek-client.json")
        client = json.loads(marker.decode("utf-8")).get("client") if marker else "claude-code"
    return client


def global_block(state_path, renderer, reference):
    # JSON-quoted absolute paths preserve spaces, Cyrillic and Windows separators.
    paths = json.dumps({"state": str(state_path), "renderer": str(renderer), "reference": str(reference)}, ensure_ascii=False, indent=2)
    return f'''{START}
## Постоянный формат ответов Арсланбека

Пользователь один раз включил формат «чат + HTML» в этом приложении.
Применяй его ко всем последующим финальным ответам, включая короткие вопросы,
другие задачи, другие проекты и новые сессии. Повторный вызов скилла не требуется.

Локальные пути настройки и встроенного инструмента:
```json
{paths}
```

Прочитай state: format=chat+html включает режим, format=chat отключает HTML.
Явное «только чат» для всех следующих ответов сохраняй в state как format=chat;
обычный повторный запуск скилла сохраняет этот выбор. Включай обратно только
по просьбе пользователя. Локальный .arslanbek/answer-mode.json с format=chat
отключает HTML для этого проекта. Прямую просьбу пользователя о формате выполняй.

- Дай понятный ответ в чате: заметные смысловые блоки, жирные ключевые мысли,
  скобки, линии и эмодзи по смыслу. Объём выбирай по вопросу; «короче» сокращает обе версии.
- Голос Арсланбека: пиши как старший брат-ментор в переписке — на «ты», тепло,
  разговорно, с юмором и открытым смехом 😂🤣. Эмодзи щедро: в каждом заголовке,
  в первой и последней строке и 1–2 в каждом блоке рядом с ключевой мыслью
  (🔥 🚀 💪 👀 🎯 ✨ 🤝 😅). Короткие живые фразы, без канцелярита. Человек расстроен
  или пропали данные/деньги — сначала поддержка, шутка потом. Отчёты школе — без шуток.
- К каждому финальному ответу сам создай отдельный локальный HTML с тем же
  содержанием и дай ссылку на реально созданный файл. Для обычного ответа используй
  renderer: один JSON создаёт HTML и совпадающий текст для чата. Подробности — reference.
  Сохраняй результат в разрешённой рабочей папке .arslanbek/answers/, а не в папке установки.
- Промежуточные обновления, вывод инструментов и структурированные отчёты школе
  сохраняют свой формат. HTML не публикуй и не передавай школе. Браузер открывай по просьбе.
- Если файлы недоступны, дай HTML-артефакт или самостоятельный HTML в блоке кода,
  обозначь ограничение. При ошибке сохранения сообщи о ней, не обещай несуществующую ссылку.
{END}'''


def activate_global(client, skill, codex_home=None, claude_home=None, enable=False, disable=False, register=False):
    clients = NATIVE_CLIENTS if client == "all" else (client,)
    if any(item not in NATIVE_CLIENTS for item in clients):
        raise ValueError("Global files are supported by Codex and Claude Code; other clients use their host instructions")
    skill = Path(skill).resolve(strict=True)
    renderer, reference = skill / "scripts/render_html.py", skill / "references/html-answer.md"
    if not renderer.is_file() or not reference.is_file():
        raise ValueError("The installed skill must contain its renderer and format reference")
    changes, results, homes = [], {}, {}
    for item in clients:
        home = client_home(item, codex_home if item == "codex" else claude_home)
        homes[item] = str(home)
        state_path = home / STATE_NAME
        before = read_file(state_path)
        state = json.loads(before.decode("utf-8")) if before else {"version": 1, "scope": "global", "format": "chat+html"}
        if not isinstance(state, dict) or state.get("version") != 1 or state.get("format") not in ("chat", "chat+html"):
            raise ValueError("Unrecognized global answer-mode state; preserving the existing choice")
        if enable:
            state["format"] = "chat+html"
        if disable:
            state["format"] = "chat"
        state.update(scope="global", renderer=str(renderer), reference=str(reference))
        changes.append((state_path, before, (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")))
        instruction = home / ("AGENTS.md" if item == "codex" else "CLAUDE.md")
        if item == "codex":
            override = home / "AGENTS.override.md"
            existing_override = read_file(override)
            if existing_override is not None and existing_override.decode("utf-8-sig").strip():
                instruction = override  # Codex reads the first nonempty global file.
        before = read_file(instruction)
        original = before.decode("utf-8") if before is not None else ""
        content = managed_document(original, global_block(state_path, renderer, reference)).encode("utf-8")
        changes.append((instruction, before, content))
        results[item] = {"format": state["format"], "instructions": str(instruction), "state": str(state_path)}
    if register:
        pointer = skill / POINTER_NAME
        before = read_file(pointer)
        saved = json.loads(before.decode("utf-8")) if before else {"version": 1, "homes": {}}
        if not isinstance(saved, dict) or saved.get("version") != 1 or not isinstance(saved.get("homes"), dict):
            raise ValueError("Unrecognized local answer-mode pointer")
        saved["homes"].update(homes)
        changes.append((pointer, before, (json.dumps(saved, ensure_ascii=False, indent=2) + "\n").encode("utf-8")))
    # Preflight every document before any mutation; preserve unrelated instructions.
    for path, before, content in changes:
        if read_file(path) != before:
            raise ValueError(f"File changed during activation; preserving it: {path}")
    for path, before, content in changes:
        if content != before:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, content)
    return results


def prompt_context(client, skill, cwd=None):
    """A short hook reminder, independent of school reporting or its opt-out."""
    if client not in NATIVE_CLIENTS:
        return ""
    try:
        pointer = read_file(Path(skill) / POINTER_NAME)
        override = json.loads(pointer.decode("utf-8")).get("homes", {}).get(client) if pointer else None
        raw = read_file(client_home(client, override) / STATE_NAME)
        if not raw:
            return ""
        state = json.loads(raw.decode("utf-8"))
        mode = state.get("format") if isinstance(state, dict) and state.get("version") == 1 else None
        if mode not in ("chat", "chat+html"):
            return ""
        if cwd and mode != "chat":
            location = Path(cwd).resolve()
            for parent in (location, *list(location.parents)[:16]):
                directory = parent / ".arslanbek"
                if directory.is_symlink():
                    continue
                local = read_file(directory / "answer-mode.json")
                choice = json.loads(local.decode("utf-8")) if local else {}
                if isinstance(choice, dict) and choice.get("format") == "chat":
                    mode = "chat"
                    break
        if mode == "chat":
            return "<arslanbek-answer-format>HTML отключён выбором пользователя. Ответь в чате голосом Арсланбека: на «ты», тепло, с юмором и щедрыми эмодзи 😄</arslanbek-answer-format>"
        return ("<arslanbek-answer-format>Постоянный формат: понятный ответ в чате и отдельный HTML с тем же содержанием. "
                "Сам создай файл через scripts/render_html.py из установленного Арсланбека, дай реальную ссылку. "
                "Голос Арсланбека: на «ты», тепло и по-человечески, с юмором и смехом, эмодзи в заголовках и в каждом блоке 🔥😂. "
                "Прямая просьба пользователя о формате имеет приоритет.</arslanbek-answer-format>")
    except (OSError, ValueError, UnicodeError, TypeError, AttributeError):
        return ""


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, help="Optional project-specific preference")
    parser.add_argument("--global", dest="global_mode", action="store_true", help="Persist the preference across projects")
    parser.add_argument("--client", choices=(*NATIVE_CLIENTS, "all"))
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--claude-home", type=Path)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--enable", action="store_true", help="Explicitly re-enable HTML at the user's request")
    choice.add_argument("--disable", action="store_true", help="Explicitly persist the chat-only preference")
    args = parser.parse_args()
    if not args.project and not args.global_mode:
        parser.error("Choose --global or --project")
    try:
        if args.global_mode:
            skill = Path(__file__).resolve().parent.parent
            result = activate_global(args.client or selected_client(skill), skill, args.codex_home, args.claude_home,
                                     args.enable, args.disable, register=True)
            print(json.dumps({"scope": "global", "clients": result}, ensure_ascii=False, indent=2))
        if args.project:
            mode = activate(args.project, args.enable, args.disable)
            print(f"Project answer mode: {mode}\nProject: {args.project.resolve()}\nInstructions: AGENTS.md + CLAUDE.md")
    except (OSError, ValueError, UnicodeError) as error:
        parser.exit(1, f"Answer mode not activated: {error}\n")


if __name__ == "__main__":
    main()
