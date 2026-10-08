import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / 'skills/arslanbek-ai-mentor'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MulticlientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.env = {'ARSLANBEK_STATE': str(self.state), 'ARSLANBEK_CLIENT': 'codex',
                    'ARSLANBEK_TELEMETRY_URL': '', 'ARSLANBEK_TELEMETRY': '1'}
        self.environment = patch.dict(os.environ, self.env)
        self.environment.start()
        self.t = load('test_runtime', SKILL / 'scripts/telemetry.py')
        self.report = json.loads((SKILL / 'references/progress-example.json').read_text())

    def tearDown(self):
        self.environment.stop()
        self.tmp.cleanup()

    def consent(self, runtime=None):
        t = runtime or self.t
        t.private_write(t.CONSENT, {'answer': 'yes', 'version': 3})

    def mcp(self, requests):
        result = subprocess.run([sys.executable, str(SKILL / 'scripts/mcp-server.py')],
                                input='\n'.join(json.dumps(r) for r in requests) + '\n',
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_client_consent_is_separate_but_device_identity_is_shared(self):
        with patch.dict(os.environ, {'ARSLANBEK_CLIENT': 'claude-code'}):
            claude = load('test_claude', SKILL / 'scripts/telemetry.py')
        self.consent(claude)
        self.assertEqual(claude.consent(), 'yes')
        self.assertEqual(self.t.consent(), '')
        self.assertEqual(claude.device(), self.t.device())
        self.consent()
        self.assertNotEqual(claude.QUEUE, self.t.QUEUE)

    def test_structured_report_requires_consent_and_redacts_nested_evidence(self):
        with self.assertRaises(ValueError):
            self.t.submit_report(self.report)
        self.consent()
        self.report['skills'][0]['evidence'] = 'password=hidden-value'
        event = self.t.submit_report(self.report, project='cart', model='DeepSeek')
        record = json.loads(next(self.t.QUEUE.glob('*.json')).read_text())
        self.assertEqual(record['event_id'], event)
        self.assertEqual(record['client'], 'codex')
        self.assertEqual(record['model'], 'DeepSeek')
        self.assertNotIn('hidden-value', json.dumps(record))
        self.assertIsNone(record['level'])

    def test_incomplete_and_unsupported_progress_is_rejected_before_queueing(self):
        self.consent()
        for update in ({'next_steps': []}, {'skills': 'text'}, {'status': 'invented'}, {'version': True}, {'task': ''}):
            with self.assertRaises(ValueError):
                self.t.submit_report({**self.report, **update})
        self.assertFalse(self.t.QUEUE.exists())

    def test_codex_hook_captures_current_prompt_and_report_reminder(self):
        self.consent()
        out = io.StringIO()
        with patch.object(self.t, 'spawn_flush'), patch('sys.stdout', out):
            for _ in range(3):
                with patch('sys.stdin', io.StringIO(json.dumps({'prompt': 'Current task', 'session_id': 'codex-session', 'cwd': '/project', 'turn_id': 'turn-1'}))):
                    self.t.cmd_prompt(None)
        self.assertIn('progress-report.md', out.getvalue())
        self.assertNotIn('~/.claude/skills/', out.getvalue())
        records = [json.loads(p.read_text()) for p in self.t.QUEUE.glob('*.json')]
        self.assertEqual(len(records), 3)
        self.assertTrue(all(r['client'] == 'codex' for r in records))

    def test_mcp_negotiation_error_and_offline_submission_are_valid_jsonl(self):
        init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25', 'clientInfo': {'name': 'test', 'version': '1'}}}
        call = {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'arslanbek_submit_progress', 'arguments': {'report': self.report, 'model': 'DeepSeek'}}}
        denied = self.mcp([init, call])
        self.assertTrue(denied[-1]['result']['isError'])
        self.assertFalse(self.t.QUEUE.exists())
        self.consent()
        responses = self.mcp([init, {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, call])
        self.assertEqual(len(responses), 3)
        self.assertEqual(responses[0]['result']['protocolVersion'], '2025-11-25')
        names = {tool['name'] for tool in responses[1]['result']['tools']}
        self.assertTrue({'arslanbek_status', 'arslanbek_record_prompt', 'arslanbek_submit_progress'} <= names)
        self.assertNotIn('arslanbek_restore', names)  # Never send restored PII back through model-facing tools.
        result = json.loads(responses[-1]['result']['content'][0]['text'])
        self.assertEqual(result['delivery'], 'queued')
        self.assertTrue(result['event_id'])


if __name__ == '__main__':
    unittest.main()
