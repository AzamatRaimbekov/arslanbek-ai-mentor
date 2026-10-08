"""Check offline HTML output, Unicode, content parity, and safe handling of answer text."""
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/arslanbek-ai-mentor/scripts/render_html.py"
spec = importlib.util.spec_from_file_location("mentor_html", SCRIPT)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags, self.links, self.ids, self.text = [], [], [], []
        self.feed(source)

    def handle_starttag(self, tag, attributes):
        self.tags.append(tag)
        attributes = dict(attributes)
        if "href" in attributes:
            self.links.append(attributes["href"])
        if "id" in attributes:
            self.ids.append(attributes["id"])

    def handle_data(self, value):
        self.text.append(value)


class HtmlAnswerTest(unittest.TestCase):
    def answer(self):
        return {"title": "Проверка заявки", "summary": "Чат и HTML объясняют один результат.",
                "sections": [{"title": "Что проверено", "kind": "success",
                              "paragraphs": ["**Пустое поле** показывает подсказку. Кыргызча: салам!"],
                              "code": "print('салам')\n# ``` is text", "code_language": "python"},
                             {"title": "Что требуется от тебя", "kind": "action", "ordered": True,
                              "items": ["Открой форму.", "Скажи, появилась ли подсказка."]},
                             {"title": "Проверки", "kind": "info", "table": {
                                 "headers": ["Сценарий", "Результат"],
                                 "rows": [["Пустое поле", "Подсказка"], ["Телефон", "Отправка"]]}}]}

    def test_chat_and_html_keep_unicode_code_and_actions(self):
        chat, page = renderer.render(self.answer())
        parsed = Document(page)
        text = " ".join(parsed.text)
        for expected in ("Проверка заявки", "Кыргызча: салам!", "Открой форму.",
                         "Скажи, появилась ли подсказка.", "print('салам')", "Пустое поле", "Отправка"):
            self.assertIn(expected, chat)
            self.assertIn(expected, text)
        self.assertIn("strong", parsed.tags)
        self.assertIn("table", parsed.tags)
        for href in parsed.links:
            if href.startswith("#"):
                self.assertIn(href[1:], parsed.ids)

    def test_answer_text_and_links_cannot_create_active_html(self):
        answer = self.answer()
        answer["title"] = '</title><script>alert("x")</script>'
        answer["sections"][0]["paragraphs"] = [
            '<img src=x onerror="alert(1)"> **<script>code</script>**',
            '[Unsafe](javascript:alert) [Data](data:text/html,test) [Safe](https://example.com/path?a=1&b=2)']
        _, page = renderer.render(answer)
        parsed = Document(page)
        self.assertNotIn("script", parsed.tags)
        self.assertNotIn("img", parsed.tags)
        self.assertFalse(any(href.startswith(("javascript:", "data:")) for href in parsed.links))
        self.assertIn("https://example.com/path?a=1&b=2", parsed.links)
        self.assertIn('<img src=x onerror="alert(1)">', " ".join(parsed.text))

    def test_cli_creates_html_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory(prefix="Ответ ученика ") as folder:
            folder = Path(folder)
            source, output = folder / "ответ.json", folder / "ответ.html"
            source.write_text(json.dumps(self.answer(), ensure_ascii=False), encoding="utf-8")
            command = [sys.executable, str(SCRIPT), "--input", str(source), "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(output), result.stdout)
            self.assertIn("Проверка заявки", output.read_text(encoding="utf-8"))
            original = output.read_bytes()
            again = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(output.read_bytes(), original)

    def test_invalid_answer_creates_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "answer.html"
            result = subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)],
                                    input='{"title":"Missing content","sections":[{"title":"Empty"}]}',
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
