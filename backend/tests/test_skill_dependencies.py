"""Offline, client-specific dependency setup and preservation of personal skill edits."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / 'skills/arslanbek-ai-mentor'


def module():
    path = SKILL / 'scripts/skill_dependencies.py'
    spec = importlib.util.spec_from_file_location('dependency_test_module', path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class DependencyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="Арсланбек student's ")
        self.root = Path(self.temporary.name)
        self.dependencies = module()

    def tearDown(self):
        self.temporary.cleanup()

    def test_core_installs_offline_in_each_selected_client_and_is_idempotent(self):
        for client in ('claude-code', 'codex'):
            target = self.root / client / 'skills'
            target.mkdir(parents=True)
            (target / 'unrelated.md').write_text('keep me')
            with patch('subprocess.run', side_effect=AssertionError('No CLI should be needed for bundled skills')):
                result = self.dependencies.ensure(SKILL, client, skills_home=target)
            self.assertTrue(result['ready'], result)
            self.assertEqual(len(result['skills']), 11)
            self.assertEqual({item['status'] for item in result['skills']}, {'installed'})
            self.assertTrue((target / 'visual-explainer/assets/answer.html').is_file())
            before = {path.relative_to(target):path.read_bytes() for path in target.rglob('*') if path.is_file()}
            second = self.dependencies.ensure(SKILL, client, skills_home=target)
            self.assertTrue(second['ready'])
            self.assertEqual({path.relative_to(target):path.read_bytes() for path in target.rglob('*') if path.is_file()}, before)

    def test_existing_custom_skill_and_existing_symlink_are_preserved(self):
        target = self.root / 'skills'
        existing = target / 'visual-explainer'
        existing.mkdir(parents=True)
        (existing / 'SKILL.md').write_text('---\nname: visual-explainer\ndescription: Custom\n---\nPersonal instructions')
        other = self.root / 'personal'
        other.mkdir()
        (other / 'SKILL.md').write_text('---\nname: brainstorming\ndescription: Custom\n---\nKeep this')
        (target / 'brainstorming').symlink_to(other, target_is_directory=True)
        result = self.dependencies.ensure(SKILL, 'codex', skills_home=target)
        self.assertTrue(result['ready'], result)
        self.assertIn('Personal instructions', (existing / 'SKILL.md').read_text())
        self.assertTrue((target / 'brainstorming').is_symlink())
        self.assertIn('Keep this', (other / 'SKILL.md').read_text())

    def fixture(self, text):
        skill = self.root / 'fixture'
        bundle = skill / 'bundled/example'
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / 'SKILL.md').write_text('---\nname: example\ndescription: Example\n---\n' + text)
        digest = hashlib.sha256((bundle / 'SKILL.md').read_bytes()).hexdigest()
        entry = {'name':'example','description':'Example','source':'local','revision':text,'files':{'SKILL.md':digest}}
        (skill / 'bundled/manifest.json').write_text(json.dumps({'version':1,'skills':[entry]}))
        return skill

    def test_managed_updates_preserve_user_modifications(self):
        skill = self.fixture('version one')
        target = self.root / 'skills'
        self.dependencies.ensure(skill, 'codex', skills_home=target)
        self.fixture('version two')
        updated = self.dependencies.ensure(skill, 'codex', skills_home=target)
        self.assertEqual(updated['skills'][0]['status'], 'updated')
        installed = target / 'example/SKILL.md'
        installed.write_text(installed.read_text() + '\nPersonal note')
        self.fixture('version three')
        preserved = self.dependencies.ensure(skill, 'codex', skills_home=target)
        self.assertTrue(preserved['ready'])
        self.assertEqual(preserved['skills'][0]['status'], 'preserved')
        self.assertIn('version two', installed.read_text())
        self.assertIn('Personal note', installed.read_text())

    def test_corrupt_bundle_and_path_traversal_cannot_write_a_partial_installation(self):
        skill = self.fixture('version one')
        target = self.root / 'skills'
        (skill / 'bundled/example/SKILL.md').write_text('corrupted')
        with self.assertRaises(ValueError):
            self.dependencies.ensure(skill, 'codex', skills_home=target)
        self.assertFalse(target.exists())
        skill = self.fixture('fixed')
        manifest = skill / 'bundled/manifest.json'
        contents = json.loads(manifest.read_text())
        contents['skills'][0]['files']['../outside'] = '0' * 64
        manifest.write_text(json.dumps(contents))
        with self.assertRaises(ValueError):
            self.dependencies.ensure(skill, 'codex', skills_home=target)
        self.assertFalse(target.exists())

    def test_dry_run_has_no_side_effects_and_mcp_only_serves_bundled_instructions(self):
        target = self.root / 'skills'
        planned = self.dependencies.ensure(SKILL, 'codex', skills_home=target, dry_run=True)
        self.assertFalse(target.exists())
        self.assertEqual({item['status'] for item in planned['skills']}, {'planned'})
        desktop = self.dependencies.ensure(SKILL, 'claude-desktop', skills_home=target)
        self.assertTrue(desktop['ready'])
        self.assertFalse(target.exists())
        self.assertEqual({item['status'] for item in desktop['skills']}, {'available-via-mcp'})
        content = self.dependencies.read(SKILL, 'visual-explainer')
        self.assertIn('# Visual Explainer', content['content'])
        for name, path in [('visual-explainer','../../telemetry.conf'), ('unknown','SKILL.md')]:
            with self.assertRaises(ValueError):
                self.dependencies.read(SKILL, name, path)

    def test_default_paths_honor_current_native_client(self):
        with patch.object(self.dependencies.Path, 'home', return_value=self.root), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.dependencies.destination('codex'), self.root / '.agents/skills')
            self.assertEqual(self.dependencies.destination('claude-code'), self.root / '.claude/skills')
        custom = self.root / 'claude preferences'
        self.assertEqual(self.dependencies.destination('claude-code', native_home=custom), custom / 'skills')

    def test_cli_reports_real_installation_failures(self):
        target = self.root / 'blocked'
        target.write_text('not a directory')
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}
        result = subprocess.run([sys.executable,'-B',str(SKILL / 'scripts/ensure_tools.py'),
                                 '--client','codex','--skills-home',str(target)], capture_output=True,text=True,env=env)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('not_ready',result.stdout)

    def online_module(self):
        sys.path.insert(0,str(SKILL / 'scripts'))
        try:
            spec = importlib.util.spec_from_file_location('ensure_tools_test',SKILL / 'scripts/ensure_tools.py')
            loaded = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loaded)
            return loaded
        finally:
            sys.path.pop(0)

    def test_optional_skill_installation_targets_only_the_selected_native_agent(self):
        installer = self.online_module()
        for client in ('codex','claude-code'):
            with patch.object(installer.dependencies.Path,'home',return_value=self.root), patch.dict(os.environ,{},clear=True):
                target = installer.dependencies.destination(client)
                calls = []
                def install(command):
                    calls.append(command)
                    destination = target / 'task-skill'
                    destination.mkdir(parents=True)
                    (destination / 'SKILL.md').write_text('---\nname: task-skill\ndescription: Task\n---\nInstructions')
                    return True
                with patch.object(installer.shutil,'which',return_value='/mock/npx'),patch.object(installer,'run',side_effect=install):
                    result = installer.add_skill('owner/repository','task-skill',client,target)
                self.assertEqual(result['status'],'installed')
                self.assertEqual(calls[0][-2:],['--agent',client])
                self.assertNotIn('--all',calls[0])

    def test_optional_plugins_are_not_attempted_in_codex_or_mcp_and_existing_skills_are_not_reinstalled(self):
        installer = self.online_module()
        with patch.object(installer,'run',side_effect=AssertionError('Wrong-client installation attempted')):
            for client in ('codex','claude-desktop','mcp'):
                self.assertEqual(installer.add_plugins(client,self.root)[0]['status'],'unsupported')
            target = self.root / 'skills'
            path = target / 'task-skill'
            path.mkdir(parents=True)
            (path / 'SKILL.md').write_text('---\nname: task-skill\ndescription: Personal\n---\nKeep my edits')
            self.assertEqual(installer.add_skill('owner/repository','task-skill','codex',target)['status'],'existing')
            self.assertIn('Keep my edits',(path / 'SKILL.md').read_text())

    def test_unknown_managed_paths_are_rejected_without_changing_installed_files(self):
        skill = self.fixture('version one')
        target = self.root / 'skills'
        self.dependencies.ensure(skill,'codex',skills_home=target)
        state = target / '.arslanbek-dependencies.json'
        contents = json.loads(state.read_text())
        contents['skills']['example']['files']['../../external'] = '0'*64
        state.write_text(json.dumps(contents))
        before = (target / 'example/SKILL.md').read_bytes()
        with self.assertRaises(ValueError):
            self.dependencies.ensure(skill,'codex',skills_home=target)
        self.assertEqual((target / 'example/SKILL.md').read_bytes(),before)

    @unittest.skipUnless(shutil.which('bash'),'Legacy shell entry requires Bash; Windows uses the Python entry')
    def test_legacy_shell_entry_preserves_arguments_and_uses_the_portable_installer(self):
        target = self.root / 'skills with spaces'
        env = {**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        result = subprocess.run([shutil.which('bash'),str(SKILL / 'scripts/ensure-tools.sh'),
                                 '--client','codex','--skills-home',str(target),'--dry-run'],
                                capture_output=True,text=True,env=env)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['client'],'codex')
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
