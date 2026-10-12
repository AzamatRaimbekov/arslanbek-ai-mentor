"""Render matching chat text and an offline HTML answer. Python standard library only."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from string import Template
import sys
from urllib.parse import urlsplit
import uuid

SKILL = Path(__file__).resolve().parents[1]
STYLES = {
    "neutral": ("💬", "РАЗБОР"), "info": ("🔵", "ПОЯСНЕНИЕ"),
    "success": ("🟢", "РЕЗУЛЬТАТ"), "warning": ("🟡", "ВНИМАНИЕ"),
    "danger": ("🔴", "ПРОБЛЕМА"), "action": ("🙋", "ДЕЙСТВИЕ"),
}
INLINE = re.compile(r"`([^`\n]+)`|\*\*([^*\n]+)\*\*|\[([^\]\n]+)\]\(([^)\s]+)\)")


def inline(text):
    parts, cursor = [], 0
    for match in INLINE.finditer(text):
        parts.append(html.escape(text[cursor:match.start()]))
        if match.group(1) is not None:
            parts.append("<code>" + html.escape(match.group(1)) + "</code>")
        elif match.group(2) is not None:
            parts.append("<strong>" + html.escape(match.group(2)) + "</strong>")
        else:
            label, url = match.group(3), match.group(4)
            scheme = urlsplit(url).scheme.lower()
            if scheme in ("http", "https", "mailto") or (not scheme and not url.startswith("//")):
                parts.append('<a href="' + html.escape(url, quote=True) + '">' + html.escape(label) + "</a>")
            else:
                parts.append(html.escape(label))
        cursor = match.end()
    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


def strings(value, field):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(field + " must be an array of strings")
    return value


def validate(document):
    if not isinstance(document, dict) or not isinstance(document.get("title"), str) or not document["title"].strip():
        raise ValueError("title must be a nonempty string")
    for field in ("summary", "footnote"):
        if not isinstance(document.get(field, ""), str):
            raise ValueError(field + " must be a string")
    sections = document.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("sections must contain at least one section")
    for index, section in enumerate(sections, 1):
        if not isinstance(section, dict) or not isinstance(section.get("title"), str) or not section["title"].strip():
            raise ValueError(f"section {index}: title must be a nonempty string")
        if section.get("kind", "neutral") not in STYLES:
            raise ValueError(f"section {index}: unknown kind")
        for field in ("paragraphs", "items"):
            strings(section.get(field, []), field)
        if not isinstance(section.get("ordered", False), bool):
            raise ValueError("ordered must be a boolean")
        for field in ("code", "code_language", "icon"):
            if not isinstance(section.get(field, ""), str):
                raise ValueError(field + " must be a string")
        if "table" in section:
            table = section["table"]
            if not isinstance(table, dict):
                raise ValueError("table must be an object")
            headers = strings(table.get("headers"), "table.headers")
            rows = table.get("rows")
            if not headers or not isinstance(rows, list):
                raise ValueError("table requires headers and rows")
            for row in rows:
                strings(row, "table row")
                if len(row) != len(headers):
                    raise ValueError("table row width must match headers")
        if not any(section.get(field) for field in ("paragraphs", "items", "code", "table")):
            raise ValueError(f"section {index}: empty section")
    return document


def render(document):
    validate(document)
    sections, navigation = [], []
    chat = ["**" + document["title"] + "**"]
    if document.get("summary"):
        chat.append(document["summary"])
    for index, section in enumerate(document["sections"], 1):
        kind = section.get("kind", "neutral")
        default_icon, label = STYLES[kind]
        icon = section.get("icon") or default_icon
        heading = f'{icon} [{index} · {section["title"]}]'
        chat.extend(["---", "## " + heading])
        navigation.append(f'<li><a href="#section-{index}"><span class="nav-number">{index:02}</span><span>{html.escape(section["title"])}</span></a></li>')
        content = [f'<section class="block" data-kind="{kind}" id="section-{index}" aria-labelledby="heading-{index}">',
                   f'<span class="status">{html.escape(icon)} {label}</span>',
                   f'<div class="block-head"><span class="number">[{index:02}]</span><h2 id="heading-{index}">{html.escape(section["title"])}</h2></div>']
        for paragraph in section.get("paragraphs", []):
            content.append("<p>" + inline(paragraph) + "</p>")
            chat.append(paragraph)
        items = section.get("items", [])
        if items:
            ordered = section.get("ordered", False)
            tag = "ol" if ordered else "ul"
            content.append("<" + tag + ">" + "".join("<li>" + inline(item) + "</li>" for item in items) + "</" + tag + ">")
            chat.append("\n".join((str(i) + ". " if ordered else "- ") + item for i, item in enumerate(items, 1)))
        if section.get("code"):
            code, language = section["code"], section.get("code_language", "")
            fence = "`" * max(3, 1 + max((len(m.group()) for m in re.finditer(r"`+", code)), default=0))
            content.append('<pre><span class="code-label">' + html.escape(language or "Код / вывод") + '</span><code>' + html.escape(code) + "</code></pre>")
            chat.append(fence + language + "\n" + code + "\n" + fence)
        if "table" in section:
            headers, rows = section["table"]["headers"], section["table"]["rows"]
            content.append('<div class="table-wrap"><table><thead><tr>' + "".join('<th scope="col">' + inline(cell) + "</th>" for cell in headers) + "</tr></thead><tbody>" + "".join("<tr>" + "".join("<td>" + inline(cell) + "</td>" for cell in row) + "</tr>" for row in rows) + "</tbody></table></div>")
            cells = lambda row: "| " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in row) + " |"
            chat.append("\n".join([cells(headers), cells(["---"] * len(headers)), *[cells(row) for row in rows]]))
        content.append("</section>")
        sections.append("\n".join(content))
    if document.get("footnote"):
        chat.append(document["footnote"])
    template = Template((SKILL / "assets/answer.html").read_text(encoding="utf-8"))
    page = template.substitute(
        title=html.escape(document["title"]), navigation="\n".join(navigation), sections="\n".join(sections),
        summary='<p class="summary">' + inline(document["summary"]) + "</p>" if document.get("summary") else "",
        footnote='<p class="footnote">' + inline(document["footnote"]) + "</p>" if document.get("footnote") else "",
    )
    return "\n\n".join(chat) + "\n", page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="JSON answer; omit to read UTF-8 JSON from stdin")
    parser.add_argument("--output", type=Path, help="New HTML file; default: .arslanbek/answers/<unique-name>.html in cwd")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        raw = args.input.read_text(encoding="utf-8-sig") if args.input else sys.stdin.buffer.read().decode("utf-8-sig")
        chat, page = render(json.loads(raw))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output = args.output or Path.cwd() / ".arslanbek/answers" / f"{stamp}-{uuid.uuid4().hex[:8]}.html"
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as target:
            target.write(page)
    except (OSError, ValueError) as error:
        parser.exit(1, f"HTML answer not created: {error}\n")
    print(chat, end="")
    link = "<" + str(output) + ">" if " " in str(output) else str(output)
    print(f"\n[Открыть HTML-ответ]({link})")


if __name__ == "__main__":
    main()
