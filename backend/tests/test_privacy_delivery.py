"""Inspect real outbound HTTP and legacy queue migration, using only a local API."""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'skills/arslanbek-ai-mentor/scripts'


class PrivacyDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        spec = importlib.util.spec_from_file_location('delivery_test', SCRIPTS / 'telemetry.py')
        self.t = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.t)
        self.raw_identity = {'claude_name': 'Alice Smith', 'claude_email': 'alice@example.test',
                             'git_name': 'Alice Smith', 'git_email': 'alice@example.test',
                             'os_user': 'private-user', 'hostname': 'private-host',
                             'claude_org': 'private-organization', 'os': 'test-os',
                             'skill_version': self.t.SKILL_VERSION, 'analysis_allowed': False}
        self.patches = [patch.object(self.t, 'identity', return_value=self.raw_identity), patch.object(self.t, 'spawn_flush'), patch('pathlib.Path.home', return_value=self.state / 'user')]
        for field, path in {'STATE': self.state, 'QUEUE': self.state / 'queue', 'SESSIONS': self.state / 'sessions',
                            'CONSENT': self.state / 'consent.json', 'LOCK': self.state / 'flush.lock',
                            'DELIVERY': self.state / 'delivery.json', 'REVOKE': self.state / 'revoke.json'}.items():
            self.patches.append(patch.object(self.t, field, path))
        for item in self.patches:
            item.start()
        self.t.private_write(self.t.CONSENT, {'answer': 'yes', 'version': 3})
        self.received = []
        received = self.received
        class Api(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        self.api = ThreadingHTTPServer(('127.0.0.1', 0), Api)
        self.thread = Thread(target=self.api.serve_forever, daemon=True)
        self.thread.start()
        self.connection = patch.object(self.t, 'config', return_value=(f'http://127.0.0.1:{self.api.server_port}', 'test-public-key', False))
        self.connection.start()

    def tearDown(self):
        self.connection.stop()
        self.api.shutdown()
        self.api.server_close()
        self.thread.join(timeout=2)
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def assert_private(self, value):
        serialized = json.dumps(value, ensure_ascii=False)
        for raw in ('Alice Smith', 'alice@example.test', 'private-user', 'private-host', 'private-organization',
                    '555 123 456', 'customer-project', 'password-value'):
            self.assertNotIn(raw, serialized)
        self.assertNotIn('entries', serialized)

    def test_prompt_report_and_identity_are_clean_in_queue_and_actual_http(self):
        self.t.capture_prompt({'prompt': 'Alice Smith: alice@example.test, +996 555 123 456, password=password-value',
                               'session_id': 'alice@example.test', 'cwd': '/Users/private-user/customer-project'})
        report = json.loads((SCRIPTS.parent / 'references/progress-example.json').read_text())
        report['result'] = 'Alice Smith проверила приложение, контакт alice@example.test'
        report['skills'][0]['evidence'] = 'Alice Smith объяснила решение'
        event = self.t.submit_report(report, session='alice@example.test', project='customer-project')
        records = [json.loads(path.read_text()) for path in self.t.QUEUE.glob('*.json')]
        self.assert_private(records)
        module = self.t.report_module()
        module.validate(next(record['report'] for record in records if 'report' in record))
        self.assertEqual(self.t.flush(), 2)
        self.assertEqual(len(self.received), 2)
        self.assert_private(self.received)
        summary = next(body['p_summary'] for body in self.received if body['p_summary'])
        self.assertEqual(summary['event_id'], event)
        self.assertTrue(all(body['p_device'] == self.t.device()['device_id'] for body in self.received))
        self.assertTrue(all(body['p_secret'] == self.t.device()['secret'] for body in self.received))
        self.assertEqual(self.received[0]['p_identity'], self.received[1]['p_identity'])
        self.assertNotIn('SECRET_REMOVED', (self.state / 'privacy/vault.json').read_text())

    def test_legacy_pending_data_are_cleaned_before_first_network_write_and_id_stays_stable(self):
        event = str(uuid.uuid4())
        path = self.t.QUEUE / 'old.json'
        self.t.private_write(path, {'type': 'prompt', 'event_id': event, 'prompt': 'Alice Smith alice@example.test',
                                    'session_id': 'alice@example.test', 'project': 'customer-project', 'ts': self.t.now_iso()})
        self.assertEqual(self.t.flush(), 1)
        self.assert_private(self.received)
        self.assertEqual(self.received[0]['p_prompts'][0]['event_id'], event)
        self.assertFalse(path.exists())

    def test_corrupt_vault_blocks_http_and_does_not_discard_pending_event(self):
        event = str(uuid.uuid4())
        path = self.t.QUEUE / 'old.json'
        self.t.private_write(path, {'type': 'prompt', 'event_id': event, 'prompt': 'Alice Smith alice@example.test'})
        vault = self.state / 'privacy/vault.json'
        vault.parent.mkdir()
        vault.write_text('invalid vault')
        self.assertEqual(self.t.flush(), 0)
        self.assertEqual(self.received, [])
        self.assertTrue(path.exists())
        self.assertEqual(json.loads(self.t.DELIVERY.read_text())['error'], 'PrivacyError')

    def test_profile_is_anonymized_before_queue(self):
        with patch.object(self.t, 'profile_md', return_value='Alice Smith, alice@example.test, +996 555 123 456'):
            self.t.cmd_profile(None)
        self.assert_private([json.loads(path.read_text()) for path in self.t.QUEUE.glob('*.json')])

    def test_tool_payload_sends_categories_without_tool_arguments_or_response_values(self):
        event = {'tool_name': 'Bash', 'tool_use_id': 'synthetic-tool-call', 'session_id': 'private-session',
                 'tool_input': {'command': 'curl --password=hidden-private-password https://private.example.test'},
                 'tool_response': {'output': 'sk-' + 'b' * 32}}
        self.t.capture_tool(event)
        self.assertEqual(self.t.flush(), 1)
        stored = self.received[0]['p_identity']['tool_event']
        self.assertEqual(stored['actor'], 'agent'); self.assertEqual(stored['source'], 'tool_hook')
        self.assertTrue(stored['privacy_signals'])
        for value in ('hidden-private-password', 'private.example.test', 'sk-' + 'b' * 32, 'tool_input', 'tool_response'):
            self.assertNotIn(value, json.dumps(self.received))

    def test_large_pending_prompt_batches_split_before_the_privacy_boundary_limit(self):
        for _ in range(80):
            self.t.enqueue({'type': 'prompt', 'prompt': 'technical ' * 1600,
                            'observability': {'version': 1, 'tags': ['backend'], 'tag_source': 'keyword_rules', 'privacy_signals': []}})
        self.assertEqual(self.t.flush(), 80)
        self.assertGreater(len(self.received), 1)
        self.assertTrue(all(len(json.dumps(body).encode()) < 600000 for body in self.received))


if __name__ == '__main__':
    unittest.main()
