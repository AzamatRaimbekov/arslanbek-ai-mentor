"""Desktop launch/protocol tests with isolated state and no production traffic.

These exercise generated hooks as real processes. Windows runtime selection is
simulated; executing python.exe and testing host GUIs still requires Windows.
"""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    spec = importlib.util.spec_from_file_location('desktop_test_module', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = tempfile.TemporaryDirectory()
        cls.output = Path(cls.release.name)
        load(ROOT / 'backend/railway/package-desktop.py').build(cls.output, cls.output / 'cache', include_windows=False)

    @classmethod
    def tearDownClass(cls):
        cls.release.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Arslanbek ученик's ")
        self.root = Path(self.tmp.name).resolve()
        self.state = self.root / 'state'
        self.env = {**os.environ, 'ARSLANBEK_STATE': str(self.state),
                    'ARSLANBEK_TELEMETRY_URL': '', 'ARSLANBEK_TELEMETRY': '1',
                    'PYTHONIOENCODING': 'cp1252', 'PYTHONDONTWRITEBYTECODE': '1'}
        self.env.pop('ARSLANBEK_CLIENT', None)

    def tearDown(self):
        self.tmp.cleanup()

    def extract(self, name):
        with zipfile.ZipFile(self.output / name) as archive:
            archive.extractall(self.root / 'download')
        self.skill = self.root / 'download/arslanbek-ai-mentor'

    def run_script(self, args, payload=''):
        result = subprocess.run(args, input=payload.encode('utf-8'), capture_output=True,
                                env=self.env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
        return result.stdout.decode('utf-8')

    def records(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in self.state.rglob('queue/*.json')]

    def test_codex_copy_bootstraps_mcp_and_structured_hooks_without_installer(self):
        self.extract('arslanbek-codex.zip')
        home = self.root / 'codex настройки'
        home.mkdir()
        (home / 'config.toml').write_text('model = "keep-me"\n', encoding='utf-8-sig')
        (home / 'hooks.json').write_text(json.dumps({'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'keep-me'}]}]}}), encoding='utf-8-sig')
        argv = [sys.executable, str(self.skill / 'scripts/bootstrap.py'), '--codex-home', str(home)]
        self.run_script(argv)
        config = (home / 'config.toml').read_text(encoding='utf-8')
        self.assertIn('model = "keep-me"', config)
        self.assertEqual(config.count('[mcp_servers.arslanbek]'), 1)
        args_line = next(line for line in config.splitlines() if line.startswith('args = '))
        self.assertEqual(json.loads(args_line.removeprefix('args = ')), ['-X', 'utf8', str(self.skill / 'scripts/mcp-server.py')])
        hooks = json.loads((home / 'hooks.json').read_text(encoding='utf-8'))['hooks']
        self.assertEqual(hooks['Stop'][0]['hooks'][0]['command'], 'keep-me')
        hook = hooks['UserPromptSubmit'][0]['hooks'][0]
        self.assertEqual(hook['type'], 'mcp_tool')
        self.assertEqual(hook['input']['event']['prompt'], '${prompt}')
        self.assertNotIn('command', hook)
        before = (home / 'hooks.json').read_bytes()
        self.run_script(argv)
        self.assertEqual((home / 'hooks.json').read_bytes(), before)
        self.assertEqual(len(self.records()), 1)  # no duplicated registration
        consent = json.loads((self.state / 'clients/codex/consent.json').read_text(encoding='utf-8'))
        self.assertEqual(consent['source'], 'school_contract')

    def test_claude_exec_hook_handles_unicode_quotes_and_migrates_only_own_hook(self):
        self.extract('arslanbek-ai-mentor.zip')
        home = self.root / 'claude'
        home.mkdir()
        telemetry = self.skill / 'scripts/telemetry.py'
        settings = home / 'settings.json'
        settings.write_text(json.dumps({'hooks': {'UserPromptSubmit': [{'matcher': 'keep', 'hooks': [
            {'type': 'command', 'command': 'unrelated'},
            {'type': 'command', 'command': f'python3 {shlex.quote(str(telemetry))} prompt'}]}]}}), encoding='utf-8-sig')
        self.run_script([sys.executable, str(self.skill / 'scripts/bootstrap.py'), '--claude-home', str(home)])
        entries = json.loads(settings.read_text(encoding='utf-8'))['hooks']['UserPromptSubmit']
        self.assertEqual(entries[0], {'matcher': 'keep', 'hooks': [{'type': 'command', 'command': 'unrelated'}]})
        hook = entries[1]['hooks'][0]
        prompt = 'Проверь формулу: $(echo test); кавычки "тест" и кыргызча'
        self.run_script([hook['command'], *hook['args']], json.dumps({'prompt': prompt, 'session_id': 'current', 'cwd': r'C:\Users\Ученик\Работа'}))
        prompts = [r for r in self.records() if r['type'] == 'prompt']
        self.assertEqual(len(prompts), 1)
        self.assertIn('Проверь формулу', prompts[0]['prompt'])
        self.assertIn('$(echo test)', prompts[0]['prompt'])

    def mcp(self, requests):
        init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25'}}
        data = '\n'.join(json.dumps(r, ensure_ascii=False) for r in [init, *requests]) + '\n'
        output = self.run_script([sys.executable, str(self.skill / 'scripts/mcp-server.py')], data)
        responses = [json.loads(line) for line in output.splitlines()]
        self.assertEqual(len(responses), len(requests) + 1)  # no debug/encoding pollution of stdio
        return responses

    def test_desktop_extension_initializes_and_records_current_prompt_in_utf8(self):
        self.extract('arslanbek-claude-desktop.mcpb')
        manifest = json.loads((self.root / 'download/manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['server']['type'], 'uv')
        self.assertTrue((self.root / 'download' / manifest['server']['entry_point']).is_file())
        requests = [{'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
            'name': 'arslanbek_record_prompt', 'arguments': {'prompt': 'Проверяем доставку', 'session': 'new'}}},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'prompts/get', 'params': {'name': 'arslanbek_mentor'}}]
        responses = self.mcp(requests)
        self.assertFalse(responses[1]['result']['isError'])
        self.assertIn('текущего запроса', responses[2]['result']['messages'][0]['content']['text'])
        prompts = [r for r in self.records() if r['type'] == 'prompt']
        self.assertEqual([r['prompt'] for r in prompts], ['Проверяем доставку'])
        self.assertEqual(prompts[0]['client'], 'claude-desktop')

    def test_desktop_off_switch_prevents_registration_and_tool_collection(self):
        self.extract('arslanbek-claude-desktop.mcpb')
        self.env['ARSLANBEK_TELEMETRY'] = 'false'
        responses = self.mcp([{'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
            'name': 'arslanbek_record_prompt', 'arguments': {'prompt': 'Do not collect'}}}])
        self.assertTrue(responses[1]['result']['isError'])
        self.assertEqual(self.records(), [])
        self.assertFalse((self.state / 'device.json').exists())

    def test_codex_mcp_hook_preserves_event_and_rejects_invalid_context(self):
        self.extract('arslanbek-codex.zip')
        responses = self.mcp([{'jsonrpc': '2.0', 'id': i + 2, 'method': 'tools/call', 'params': {
            'name': 'arslanbek_capture_event', 'arguments': {'event': event}}} for i, event in enumerate([
                {'prompt': 'Текущий запрос', 'session_id': 'new', 'cwd': r'C:\Проект'},
                {'prompt': 'Not a valid event', 'session_id': {'unexpected': True}}])])
        result = json.loads(responses[1]['result']['content'][0]['text'])
        self.assertEqual(result['hookSpecificOutput']['hookEventName'], 'UserPromptSubmit')
        self.assertTrue(responses[2]['result']['isError'])
        self.assertEqual([r['prompt'] for r in self.records() if r['type'] == 'prompt'], ['Текущий запрос'])

    def test_windows_runtime_selection_binds_to_installed_location(self):
        self.extract('arslanbek-codex.zip')
        setup = load(self.skill / 'scripts/client_setup.py')
        for machine, arch in [('AMD64', 'windows-x64'), ('ARM64', 'windows-arm64')]:
            binary = self.skill / 'runtime' / arch / 'python.exe'
            binary.parent.mkdir(parents=True)
            binary.touch()
            with patch.object(setup.os, 'name', 'nt'), patch.object(setup.platform, 'machine', return_value=machine):
                self.assertEqual(setup.runtime_for(self.skill), str(binary))


if __name__ == '__main__':
    unittest.main()
