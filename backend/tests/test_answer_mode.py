"""Check persistent project activation without replacing unrelated agent instructions."""
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/arslanbek-ai-mentor/scripts/activate_answer_mode.py"
spec = importlib.util.spec_from_file_location("mentor_answer_mode", SCRIPT)
mode = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mode)


class AnswerModeTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.skill = Path(temporary.name) / 'skill'
        for name in ('scripts/render_html.py', 'references/html-answer.md'):
            target = self.skill / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SCRIPT.parent.parent / name, target)

    def test_global_defaults_apply_to_other_projects_without_creating_project_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            codex, claude = base / 'codex', base / 'claude'
            codex.mkdir(); claude.mkdir()
            original = b'# My instructions\r\nKeep my preferences.\r\n'
            (codex / 'AGENTS.md').write_bytes(original)
            (claude / 'CLAUDE.md').write_text('Keep my Claude preferences.\n')
            result = mode.activate_global('all', self.skill, codex, claude)
            for client, home, name in [('codex', codex, 'AGENTS.md'), ('claude-code', claude, 'CLAUDE.md')]:
                self.assertEqual(result[client]['format'], 'chat+html')
                before = (home / name).read_bytes()
                mode.activate_global('all', self.skill, codex, claude)
                self.assertEqual((home / name).read_bytes(), before)
                for project_name in ('first-project', 'unrelated-project'):
                    project = base / project_name
                    project.mkdir(exist_ok=True)
                    with patch.dict(os.environ, {'CODEX_HOME': str(codex), 'CLAUDE_CONFIG_DIR': str(claude)}):
                        self.assertIn('HTML', mode.prompt_context(client, self.skill, project))
                    self.assertEqual(list(project.iterdir()), [])
            self.assertTrue((codex / 'AGENTS.md').read_bytes().startswith(original))
            self.assertNotIn(b'\n', (codex / 'AGENTS.md').read_bytes().replace(b'\r\n', b''))

    def test_codex_uses_existing_nonempty_override_and_preserves_base(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / 'AGENTS.md').write_text('Base instruction stays unchanged')
            (home / 'AGENTS.override.md').write_text('Override instruction stays first\n')
            result = mode.activate_global('codex', self.skill, codex_home=home)
            self.assertTrue(result['codex']['instructions'].endswith('AGENTS.override.md'))
            self.assertEqual((home / 'AGENTS.md').read_text(), 'Base instruction stays unchanged')
            self.assertTrue((home / 'AGENTS.override.md').read_text().startswith('Override instruction stays first\n'))
            (home / 'AGENTS.override.md').write_text(' \n')
            mode.activate_global('codex', self.skill, codex_home=home)
            self.assertEqual((home / 'AGENTS.override.md').read_text(), ' \n')
            self.assertIn(mode.START, (home / 'AGENTS.md').read_text())

    def test_global_disable_survives_repeat_activation_and_hook_reads_project_choice(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / 'codex'
            project = Path(temporary) / 'project'
            project.mkdir()
            mode.activate_global('codex', self.skill, codex_home=home, disable=True)
            mode.activate_global('codex', self.skill, codex_home=home)
            self.assertEqual(json.loads((home / mode.STATE_NAME).read_text())['format'], 'chat')
            with patch.dict(os.environ, {'CODEX_HOME': str(home)}):
                self.assertIn('отключён', mode.prompt_context('codex', self.skill, project))
                mode.activate_global('codex', self.skill, codex_home=home, enable=True)
                mode.activate(project, disable=True)
                nested = project / 'nested'
                nested.mkdir()
                self.assertIn('отключён', mode.prompt_context('codex', self.skill, nested))
                mode.activate(project, enable=True)
                self.assertIn('Постоянный формат', mode.prompt_context('codex', self.skill, nested))

    def test_invalid_global_second_document_causes_no_partial_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            claude = base / 'claude'
            claude.mkdir()
            (claude / 'CLAUDE.md').write_text(mode.START + '\nunfinished')
            with self.assertRaises(ValueError):
                mode.activate_global('all', self.skill, codex_home=base / 'codex', claude_home=claude)
            self.assertFalse((base / 'codex').exists())
            self.assertFalse((claude / mode.STATE_NAME).exists())

    def test_global_symlink_is_rejected_and_host_config_dirs_are_respected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / 'outside.md'
            outside.write_text('Leave this file alone')
            home = base / 'codex'
            home.mkdir()
            (home / 'AGENTS.md').symlink_to(outside)
            with self.assertRaises(ValueError):
                mode.activate_global('codex', self.skill, codex_home=home)
            self.assertFalse((home / mode.STATE_NAME).exists())
            self.assertEqual(outside.read_text(), 'Leave this file alone')
            with patch.dict(os.environ, {'CODEX_HOME': str(base / 'custom-codex'), 'CLAUDE_CONFIG_DIR': str(base / 'custom-claude')}):
                result = mode.activate_global('all', self.skill)
                self.assertEqual(result['codex']['state'], str(base / 'custom-codex' / mode.STATE_NAME))
                self.assertEqual(result['claude-code']['state'], str(base / 'custom-claude' / mode.STATE_NAME))

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
