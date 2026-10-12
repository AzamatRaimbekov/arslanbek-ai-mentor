"""Exercise the actual downloaded installer in an isolated home, without production requests."""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    spec = importlib.util.spec_from_file_location('package_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SkillBundleTestCase(unittest.TestCase):
    contract = False
    @classmethod
    def setUpClass(cls):
        cls.release = tempfile.TemporaryDirectory()
        cls.archive = Path(cls.release.name) / 'skill.zip'
        builder = load(ROOT / 'backend/railway/package-skill.py')
        with patch.object(builder, 'OUTPUT', cls.archive), patch.object(builder, 'ROOT', Path(cls.release.name)), patch('sys.stdout', io.StringIO()):
            builder.main(contract=cls.contract)

    @classmethod
    def tearDownClass(cls):
        cls.release.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bundle = self.root / 'download'
        with zipfile.ZipFile(self.archive) as archive:
            archive.extractall(self.bundle)
        self.home = self.root / 'claude'
        self.state = self.root / 'state'
        self.skill = self.home / 'skills/arslanbek-ai-mentor'
        self.env = {**os.environ, 'ARSLANBEK_STATE': str(self.state),
                    'ARSLANBEK_SKILLS_HOME':str(self.root / 'dependencies'),
                    'ARSLANBEK_TELEMETRY_URL': '', 'ARSLANBEK_TELEMETRY': '1'}

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, choice='', *args):
        result = subprocess.run([sys.executable, str(self.bundle / 'install.py'),
                                 '--claude-home', str(self.home), *args],
                                input=choice, text=True, capture_output=True, env=self.env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def consent(self):
        return json.loads((self.state / 'consent.json').read_text())

    def assert_no_chat_consent_question(self):
        with patch.dict(os.environ, self.env):
            telemetry = load(self.skill / 'scripts/telemetry.py')
            with patch('sys.stdin', io.StringIO(json.dumps({'prompt': 'test task', 'session_id': 's'}))), patch('sys.stdout', io.StringIO()) as out, patch.object(telemetry, 'spawn_flush'):
                telemetry.cmd_prompt(None)
        self.assertNotIn('arslanbek-consent', out.getvalue())

    def bootstrap(self):
        result = subprocess.run([sys.executable, str(self.skill / 'scripts/bootstrap.py'),
                                 '--claude-home', str(self.home)],
                                text=True, capture_output=True, env=self.env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout


class SkillInstallTest(SkillBundleTestCase):

    def test_standard_release_keeps_participant_choice_and_matching_instructions(self):
        skill = self.bundle / 'arslanbek-ai-mentor'
        self.assertFalse((skill / 'school-policy.json').exists())
        self.assertEqual((skill / '.school-release').read_text().strip(), 'telemetry-10-global-format-standard')
        self.assertIn('SKILL_VERSION = "telemetry-10-global-format-standard"', (skill / 'scripts/telemetry.py').read_text())
        instructions = (self.bundle / 'START_HERE.txt').read_text()
        self.assertIn('python3 install.py --client codex', instructions)
        self.assertIn('При первой установке выберите', instructions)
        self.assertNotIn('передача включается автоматически', instructions)

    def test_accept_records_choice_and_queues_registration_without_chat_question(self):
        output = self.install('1\n')
        consent = self.consent()
        self.assertEqual(consent['answer'], 'yes')
        self.assertEqual(consent['source'], 'installer')
        self.assertEqual(consent['version'], 3)
        self.assertTrue(consent['ts'])
        self.assertFalse(consent['analysis_allowed'])
        self.assertEqual((self.state / 'consent.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(list((self.state / 'queue').glob('*.json'))), 1)
        self.assertIn('последняя успешная доставка: ещё не было', output)
        self.assert_no_chat_consent_question()

    def test_decline_installs_without_registration_or_chat_question(self):
        self.install('2\n')
        self.assertTrue((self.skill / 'SKILL.md').exists())
        self.assertEqual(self.consent()['answer'], 'no')
        self.assert_no_chat_consent_question()
        self.assertFalse((self.state / 'queue').exists())
        self.assertFalse((self.state / 'device.json').exists())

    def test_codex_installs_skill_hooks_and_mcp_without_reusing_claude_consent(self):
        self.install('1\n')
        codex, agents = self.root / 'codex', self.root / 'agents'
        codex.mkdir()
        config = codex / 'config.toml'
        config.write_text('model = "existing-model"\n[mcp_servers.existing]\ncommand = "existing"\n')
        self.install('1\n', '--client', 'codex', '--codex-home', str(codex), '--agents-home', str(agents))
        skill = agents / 'skills/arslanbek-ai-mentor'
        self.assertTrue((skill / 'SKILL.md').exists())
        self.assertNotIn('CLAUDE_SKILL_DIR', (skill / 'SKILL.md').read_text())
        self.assertEqual(json.loads((skill / '.arslanbek-client.json').read_text())['client'], 'codex')
        hooks = json.loads((codex / 'hooks.json').read_text())['hooks']
        self.assertEqual(len(hooks['UserPromptSubmit']), 1)
        self.assertEqual(len(hooks['SessionStart']), 1)
        self.assertIn('existing-model', config.read_text())
        self.assertIn('[mcp_servers.existing]', config.read_text())
        self.assertEqual(config.read_text().count('[mcp_servers.arslanbek]'), 1)
        record = json.loads((self.state / 'clients/codex/consent.json').read_text())
        self.assertEqual(record['answer'], 'yes')
        self.install('', '--client', 'codex', '--codex-home', str(codex), '--agents-home', str(agents))
        self.assertEqual(config.read_text().count('[mcp_servers.arslanbek]'), 1)
        self.assertEqual(len(json.loads((codex / 'hooks.json').read_text())['hooks']['UserPromptSubmit']), 1)

    def test_generic_mcp_install_produces_connection_config_without_claude_hooks(self):
        home = self.root / 'mcp'
        self.install('2\n', '--client', 'mcp', '--mcp-home', str(home))
        skill = home / 'skills/arslanbek-ai-mentor'
        config = json.loads((skill / 'mcp.json').read_text())
        self.assertEqual(config['mcpServers']['arslanbek']['args'], [str((skill / 'scripts/mcp-server.py').resolve())])
        self.assertFalse((self.home / 'settings.json').exists())
        self.assertEqual(json.loads((self.state / 'clients/mcp/consent.json').read_text())['answer'], 'no')

    def test_cancel_blank_eof_and_invalid_then_cancel_do_not_mutate(self):
        for choice in ('0\n', '\n', '', 'yes\n0\n'):
            self.install(choice)
            self.assertFalse(self.home.exists())
            self.assertFalse(self.state.exists())

    def test_update_preserves_both_choices_profile_and_other_hooks(self):
        for choice in ('1\n', '2\n'):
            self.install(choice, '--choose-collection')
            original = self.consent()
            profile = self.skill / 'references/student-profile.md'
            profile.write_text('Existing learner observations')
            config = self.skill / 'telemetry.local.conf'
            config.write_text('# Local settings retained\n')
            settings_path = self.home / 'settings.json'
            settings = json.loads(settings_path.read_text())
            settings['permissions'] = {'allow': ['Read']}
            settings['hooks']['Stop'] = [{'hooks': [{'type': 'command', 'command': 'existing'}]}]
            settings_path.write_text(json.dumps(settings))
            self.install()  # no input: existing choice must survive updates
            self.assertEqual(self.consent(), original)
            self.assertEqual(profile.read_text(), 'Existing learner observations')
            self.assertEqual(config.read_text(), '# Local settings retained\n')
            updated = json.loads(settings_path.read_text())
            self.assertEqual(updated, settings)

    def test_explicit_change_to_no_clears_unsent_records(self):
        self.install('1\n')
        self.install('2\n', '--choose-collection')
        self.assertEqual(self.consent()['answer'], 'no')
        self.assertEqual(list((self.state / 'queue').glob('*.json')), [])

    def test_copied_skill_connects_itself_without_installer_or_automatic_consent(self):
        shutil.copytree(self.bundle / 'arslanbek-ai-mentor', self.skill)
        output = self.bootstrap()
        settings_path = self.home / 'settings.json'
        original = settings_path.read_bytes()
        settings = json.loads(original)
        self.assertEqual(len(settings['hooks']['UserPromptSubmit']), 1)
        self.assertEqual(len(settings['hooks']['SessionStart']), 1)
        self.assertIn('arslanbek-consent', output)
        self.assertFalse(self.state.exists())
        self.bootstrap()
        self.assertEqual(settings_path.read_bytes(), original)
        self.assertFalse(self.state.exists())

    def test_bootstrap_preserves_yes_and_no_without_repeating_question(self):
        for choice in ('1\n', '2\n'):
            self.install(choice, '--choose-collection')
            original = self.consent()
            settings_path = self.home / 'settings.json'
            settings = json.loads(settings_path.read_text())
            settings['permissions'] = {'allow': ['Read']}
            settings['hooks']['Stop'] = [{'hooks': [{'type': 'command', 'command': 'existing'}]}]
            settings_path.write_text(json.dumps(settings))
            original_settings = settings_path.read_bytes()
            output = self.bootstrap()
            self.assertNotIn('arslanbek-consent', output)
            self.assertEqual(self.consent(), original)
            self.assertEqual(settings_path.read_bytes(), original_settings)
            if original['answer'] == 'no':
                self.assertEqual(list((self.state / 'queue').glob('*.json')), [])

    def test_setup_only_installs_without_input_and_without_granting_consent(self):
        self.install('', '--setup-only')
        self.assertTrue((self.skill / 'SKILL.md').exists())
        self.assertTrue((self.home / 'settings.json').exists())
        self.assertFalse(self.state.exists())

    def test_setup_only_update_keeps_refusal_and_personal_observations(self):
        self.install('2\n')
        original = self.consent()
        profile = self.skill / 'references/student-profile.md'
        profile.write_text('Existing learner observations')
        self.install('', '--setup-only')
        self.assertEqual(self.consent(), original)
        self.assertEqual(profile.read_text(), 'Existing learner observations')
        self.assertFalse((self.state / 'device.json').exists())


class SchoolContractTest(SkillBundleTestCase):
    contract = True

    def copy_skill(self):
        shutil.copytree(self.bundle / 'arslanbek-ai-mentor', self.skill)

    def test_copy_enrolls_without_question_and_preserves_settings_on_repeat(self):
        self.copy_skill()
        self.home.mkdir(parents=True, exist_ok=True)
        settings_path = self.home / 'settings.json'
        settings_path.write_text(json.dumps({'permissions': {'allow': ['Read'], 'deny': ['Bash(rm *)']},
                                             'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'existing'}]}]}}))
        output = self.bootstrap()
        record = self.consent()
        self.assertEqual(record['answer'], 'yes')
        self.assertEqual(record['source'], 'school_contract')
        self.assertIsNone(record['ts'])
        self.assertTrue(record['activated_at'])
        self.assertNotIn('arslanbek-consent', output)
        self.assertEqual(len(list((self.state / 'queue').glob('*.json'))), 1)
        settings = json.loads(settings_path.read_text())
        self.assertIn('Read', settings['permissions']['allow'])
        self.assertEqual(settings['permissions']['deny'], ['Bash(rm *)'])
        self.assertTrue(any('record-prompt' in rule for rule in settings['permissions']['allow']))
        self.assertEqual(settings['hooks']['Stop'][0]['hooks'][0]['command'], 'existing')
        before = settings_path.read_bytes()
        self.bootstrap()
        self.assertEqual(settings_path.read_bytes(), before)
        self.assertEqual(self.consent(), record)
        self.assertEqual(len(list((self.state / 'queue').glob('*.json'))), 1)

    def test_installer_accepts_no_input_and_records_school_basis(self):
        output = self.install()
        self.assertTrue((self.skill / 'SKILL.md').is_file())
        self.assertEqual(self.consent()['source'], 'school_contract')
        self.assertNotIn('Ваш выбор', output)
        self.assert_no_chat_consent_question()

    def test_explicit_opt_out_is_not_reenabled_by_bootstrap_or_update(self):
        self.install()
        with patch.dict(os.environ, self.env):
            telemetry = load(self.skill / 'scripts/telemetry.py')
            with patch.object(telemetry, 'spawn_flush'), patch('sys.stdout', io.StringIO()):
                telemetry.cmd_consent(argparse.Namespace(answer='no'))
        original = self.consent()
        self.bootstrap()
        self.install('', '--setup-only')
        self.assertEqual(self.consent(), original)
        self.assertEqual(list((self.state / 'queue').glob('*.json')), [])

    def test_environment_off_prevents_enrollment_and_collection(self):
        self.copy_skill()
        self.env['ARSLANBEK_TELEMETRY'] = 'off'
        self.bootstrap()
        self.assertFalse(self.state.exists())

    def test_contract_policy_cannot_authorize_a_different_server(self):
        self.copy_skill()
        self.env['ARSLANBEK_TELEMETRY_URL'] = 'https://different.example'
        with patch.dict(os.environ, self.env):
            telemetry = load(self.skill / 'scripts/telemetry.py')
            self.assertFalse(telemetry.ensure_school_authorization())
        self.assertFalse(self.state.exists())

    def test_current_session_records_prompt_once_then_defers_to_hook(self):
        self.copy_skill()
        self.bootstrap()
        with patch.dict(os.environ, self.env):
            telemetry = load(self.skill / 'scripts/telemetry.py')
            with patch.object(telemetry, 'spawn_flush'):
                event = {'prompt': 'current task', 'session_id': 'current', 'cwd': '/tmp/project'}
                telemetry.capture_prompt(event, hook=False)
                self.assertFalse(telemetry.hook_active('current'))
                telemetry.capture_prompt({**event, 'prompt': 'next task'}, hook=True)
                self.assertTrue(telemetry.hook_active('current'))
                telemetry.capture_prompt({**event, 'prompt': 'next task'}, hook=False)
            records = [json.loads(path.read_text()) for path in telemetry.QUEUE.glob('*.json')]
        prompts = [record for record in records if record['type'] == 'prompt']
        self.assertEqual([record['prompt'] for record in sorted(prompts, key=lambda r: r['ts'])], ['current task', 'next task'])

    def test_downloaded_package_delivers_enrollment_prompt_and_summary_to_api(self):
        self.copy_skill()
        received = []
        class Api(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                result = b'{"ok":true}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(result)))
                self.end_headers()
                self.wfile.write(result)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Api)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = 'http://127.0.0.1:' + str(server.server_port)
            policy_path = self.skill / 'school-policy.json'
            policy = json.loads(policy_path.read_text())
            policy['server_url'] = url
            policy_path.write_text(json.dumps(policy))
            self.env['ARSLANBEK_TELEMETRY_URL'] = url
            self.bootstrap()
            with patch.dict(os.environ, self.env):
                telemetry = load(self.skill / 'scripts/telemetry.py')
                with patch.object(telemetry, 'spawn_flush'), patch('sys.stdout', io.StringIO()):
                    telemetry.capture_prompt({'prompt': 'task token=secret-value', 'session_id': 'test', 'cwd': '/tmp/project'}, hook=False)
                    telemetry.cmd_summary(argparse.Namespace(level=None, stage='Проверка', summary='Проверена задача', strengths='', struggles='', next='Следующий шаг', session='test'))
                self.assertEqual(telemetry.flush(), 2)
            self.assertEqual(len(received), 3)
            self.assertTrue(all(path == '/rest/v1/rpc/ingest' for path, _ in received))
            self.assertEqual(received[0][1]['p_identity']['authorization_source'], 'school_contract')
            self.assertIsNone(received[0][1]['p_identity']['consented_at'])
            self.assertIsNone(received[0][1]['p_summary'])
            self.assertEqual(received[0][1]['p_prompts'], [])
            payloads = [body for _, body in received]
            prompt = next(body['p_prompts'][0] for body in payloads if body['p_prompts'])
            self.assertNotIn('secret-value', prompt['prompt'])
            self.assertEqual(next(body['p_summary']['summary'] for body in payloads if body['p_summary'] and 'summary' in body['p_summary']), 'Проверена задача')
            self.assertEqual(list((self.state / 'queue').glob('*.json')), [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
