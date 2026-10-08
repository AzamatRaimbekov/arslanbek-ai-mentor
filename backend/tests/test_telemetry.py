import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'skills/arslanbek-ai-mentor/scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


t = load('telemetry', 'telemetry.py')
installer = load('installer', 'install-telemetry-hooks.py')


class TelemetryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = Path(self.tmp.name)
        self.patches = []
        for key, value in {'STATE': state, 'QUEUE': state / 'queue', 'SESSIONS': state / 'sessions', 'LOCK': state / 'lock', 'CONSENT': state / 'consent.json', 'DELIVERY': state / 'delivery.json', 'REVOKE': state / 'revoke.json'}.items():
            self.patches.append(patch.object(t, key, value))
        self.patches += [patch.object(t, 'spawn_flush'), patch.object(t, 'config', return_value=('https://test.supabase.co', 'sb_publishable_test', False)), patch.object(t, 'profile_md', return_value='Test profile')]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def consent(self, answer='yes', version=2):
        t.private_write(t.CONSENT, {'answer': answer, 'version': version, 'ts': t.now_iso()})

    def test_no_collection_without_consent(self):
        for value in [None, ('no', 2), ('no', 3)]:
            if value:
                self.consent(*value)
            with patch('sys.stdin', io.StringIO(json.dumps({'prompt': 'private', 'session_id': 'x'}))), patch('sys.stdout', io.StringIO()):
                t.cmd_prompt(None)
            self.assertFalse(t.QUEUE.exists())
            self.assertFalse((t.STATE / 'device.json').exists())

    def test_collection_consent_does_not_authorize_external_analysis(self):
        for version in [1, 2, 3]:
            self.consent(version=version)
            args = argparse.Namespace(level=None, session='s', stage='Проверка', summary='Агент исправил ошибку; участник проверил результат.', strengths='', struggles='', next='Проверить отказ сервера')
            with patch('sys.stdout', io.StringIO()):
                t.cmd_summary(args)
            with patch.object(t, '_git', return_value=''):
                self.assertFalse(t.identity()['analysis_allowed'])
        self.assertEqual(len(list(t.QUEUE.glob('*.json'))), 3)
        with patch('sys.stdout', io.StringIO()):
            t.cmd_consent(argparse.Namespace(answer='yes'))
        self.assertEqual(t.consent_record()['version'], 3)
        self.assertFalse(t.consent_record()['analysis_allowed'])

    def test_queue_redacts_secrets_and_uses_private_permissions(self):
        self.consent()
        with patch('sys.stdin', io.StringIO(json.dumps({'prompt': 'password=hidden sk-' + 'a' * 30, 'session_id': 'safe'}))):
            t.cmd_prompt(None)
        path = next(t.QUEUE.glob('*.json'))
        rec = json.loads(path.read_text())
        self.assertNotIn('hidden', rec['prompt'])
        self.assertNotIn('sk-', rec['prompt'])
        self.assertTrue(rec['event_id'])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_retry_keeps_same_event_id_and_removes_only_acknowledged_events(self):
        self.consent()
        t.enqueue({'type': 'prompt', 'prompt': 'test', 'session_id': 's'})
        sent = []
        def post(url, key, dev, prompts, summary):
            sent.append(prompts)
            if len(sent) == 1:
                raise TimeoutError('lost response')
            return True
        with patch.object(t, 'post', side_effect=post):
            self.assertEqual(t.flush(), 0)
            self.assertEqual(len(list(t.QUEUE.glob('*.json'))), 1)
            self.assertEqual(t.flush(), 1)
        self.assertEqual(sent[0][0]['event_id'], sent[1][0]['event_id'])
        self.assertEqual(len(list(t.QUEUE.glob('*.json'))), 0)
        self.assertIsNone(json.loads(t.DELIVERY.read_text())['error'])

    def test_unknown_level_stays_unknown_and_off_switch_blocks_summaries(self):
        self.consent()
        args = argparse.Namespace(level=None, session='s', stage='test', summary='No evidence of independent work', strengths='', struggles='', next='Ask for a demonstration')
        with patch('sys.stdout', io.StringIO()):
            t.cmd_summary(args)
        self.assertIsNone(json.loads(next(t.QUEUE.glob('*.json')).read_text())['level'])
        with patch.object(t, 'config', return_value=('', '', True)), self.assertRaises(SystemExit):
            t.cmd_summary(args)

    def test_revoke_clears_queue_and_marks_server_revocation_pending(self):
        self.consent()
        t.device()
        t.enqueue({'type': 'prompt', 'prompt': 'test'})
        with patch('sys.stdout', io.StringIO()):
            t.cmd_consent(argparse.Namespace(answer='no'))
        self.assertEqual(list(t.QUEUE.glob('*.json')), [])
        self.assertTrue(t.REVOKE.exists())
        with patch.object(t, 'post') as post, patch.object(t, 'send_revocation'):
            t.flush()
            post.assert_not_called()

    def test_headers_and_read_only_status(self):
        self.assertNotIn('Authorization', t.api_headers('sb_publishable_test'))
        self.assertEqual(t.api_headers('eyJtest')['Authorization'], 'Bearer eyJtest')
        with patch('sys.stdout', io.StringIO()):
            t.cmd_status(None)
        self.assertFalse((t.STATE / 'device.json').exists())

    def test_installer_waits_for_acknowledgement_and_keeps_failed_registration(self):
        args = argparse.Namespace(answer='yes', source='installer', wait=True)
        with patch.object(t, 'post', side_effect=TimeoutError('offline')), patch('sys.stdout', io.StringIO()):
            t.cmd_consent(args)
        self.assertEqual(t.consent_record()['source'], 'installer')
        self.assertEqual(len(list(t.QUEUE.glob('*.json'))), 1)
        self.assertEqual(json.loads(t.DELIVERY.read_text())['error'], 'TimeoutError')
        t.spawn_flush.assert_not_called()
        with patch.object(t, 'post', return_value=True):
            self.assertEqual(t.flush(), 1)
        self.assertEqual(list(t.QUEUE.glob('*.json')), [])
        self.assertTrue(json.loads(t.DELIVERY.read_text())['last_success'])

    def test_hook_installation_preserves_settings_and_does_not_duplicate(self):
        home = t.STATE / 'claude'
        home.mkdir()
        (home / 'settings.json').write_text(json.dumps({'permissions': {'allow': ['Read']}, 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'existing'}]}]}}))
        skill = ROOT / 'skills/arslanbek-ai-mentor'
        self.assertTrue(installer.install(home, skill))
        self.assertFalse(installer.install(home, skill))
        result = json.loads((home / 'settings.json').read_text())
        self.assertEqual(result['permissions']['allow'], ['Read'])
        self.assertEqual(result['hooks']['Stop'][0]['hooks'][0]['command'], 'existing')
        self.assertEqual(len(result['hooks']['UserPromptSubmit']), 1)
        self.assertEqual(len(result['hooks']['SessionStart']), 1)
        self.assertEqual(result['hooks']['SessionStart'][0]['hooks'][0]['async'], True)


if __name__ == '__main__':
    unittest.main()
