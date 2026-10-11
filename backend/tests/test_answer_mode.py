"""Check persistent project activation without replacing unrelated agent instructions."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/arslanbek-ai-mentor/scripts/activate_answer_mode.py"
spec = importlib.util.spec_from_file_location("mentor_answer_mode", SCRIPT)
mode = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mode)


class AnswerModeTest(unittest.TestCase):
    def test_activation_is_idempotent_and_preserves_existing_instructions(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            existing = b"# Existing rules\r\n\r\nKeep this byte-for-byte.\r\n"
            (project / "AGENTS.md").write_bytes(existing)
            mode.activate(project)
            snapshots = {name: (project / name).read_bytes() for name in ["AGENTS.md", "CLAUDE.md", ".arslanbek/answer-mode.json"]}
            mode.activate(project)
            self.assertTrue(snapshots["AGENTS.md"].startswith(existing))
            self.assertNotIn(b"\n", snapshots["AGENTS.md"].replace(b"\r\n", b""))
            for name, before in snapshots.items():
                self.assertEqual((project / name).read_bytes(), before)
            self.assertFalse((Path(temporary) / "AGENTS.md").exists())
            self.assertEqual(json.loads(snapshots[".arslanbek/answer-mode.json"])["format"], "chat+html")

    def test_updating_only_changes_the_managed_region(self):
        original = "Before\n" + mode.START + "\nOld rule\n" + mode.END + "\nAfter\n"
        updated = mode.managed_document(original)
        self.assertTrue(updated.startswith("Before\n"))
        self.assertTrue(updated.endswith("\nAfter\n"))
        self.assertEqual(updated.count(mode.START), 1)
        self.assertNotIn("Old rule", updated)

    def test_invalid_second_document_does_not_write_first_document_or_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "AGENTS.md").write_text("Existing agent instructions", encoding="utf-8")
            (project / "CLAUDE.md").write_text(mode.START + "\nunfinished", encoding="utf-8")
            with self.assertRaises(ValueError):
                mode.activate(project)
            self.assertEqual((project / "AGENTS.md").read_text(), "Existing agent instructions")
            self.assertFalse((project / ".arslanbek").exists())

    def test_explicit_chat_choice_persists_until_explicit_reenable(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            mode.activate(project)
            state = project / ".arslanbek/answer-mode.json"
            state.write_text(json.dumps({"version": 1, "format": "chat", "custom": "preserve"}))
            self.assertEqual(mode.activate(project), "chat")
            self.assertEqual(json.loads(state.read_text())["custom"], "preserve")
            self.assertEqual(mode.activate(project, enable=True), "chat+html")

    def test_symlinked_instruction_is_preserved_and_cli_creates_project_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            external = Path(temporary) / "outside.md"
            external.write_text("Do not edit me")
            (project / "AGENTS.md").symlink_to(external)
            with self.assertRaises(ValueError):
                mode.activate(project)
            self.assertEqual(external.read_text(), "Do not edit me")
            self.assertFalse((project / ".arslanbek").exists())
            safe = Path(temporary) / "safe"
            safe.mkdir()
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--project", str(safe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("chat+html", result.stdout)
            self.assertTrue((safe / "CLAUDE.md").is_file())


if __name__ == "__main__":
    unittest.main()
