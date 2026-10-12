"""Persist the user's chat + HTML preference in one project's agent instructions."""
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

- В чате используй понятные смысловые блоки: заголовки `## ✅ [1 · Результат]`,
  скобки, линии `---`, жирные ключевые мысли и эмодзи по смыслу. Объясняй результат,
  причины, проверку и следующий шаг; объём выбирай по задаче и просьбе пользователя.
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


def managed_document(original):
    """Replace only our block, preserving the surrounding text and line endings."""
    newline = "\r\n" if "\r\n" in original else "\n"
    block = BLOCK.replace("\n", newline)
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


def activate(project, enable=False):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path, help="Root of the project chosen by the user")
    parser.add_argument("--enable", action="store_true", help="Explicitly re-enable HTML at the user's request")
    args = parser.parse_args()
    try:
        mode = activate(args.project, args.enable)
    except (OSError, ValueError, UnicodeError) as error:
        parser.exit(1, f"Answer mode not activated: {error}\n")
    print(f"Project answer mode: {mode}\nProject: {args.project.resolve()}\nInstructions: AGENTS.md + CLAUDE.md")


if __name__ == "__main__":
    main()
