"""Check actual local anonymization and restoration with synthetic identities."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'skills/arslanbek-ai-mentor/scripts/anonymizer.py'
spec = importlib.util.spec_from_file_location('privacy_tests', SCRIPT)
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)


class AnonymizerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / 'privacy/vault.json'
        self.anon = privacy.Anonymizer(self.vault)

    def tearDown(self):
        self.temp.cleanup()

    def test_nested_pii_becomes_consistent_tokens_and_restores_locally(self):
        original = {'claude_name': 'Alice Smith', 'email': 'alice@example.test',
                    'phone': '+996 (555) 123-456', 'address': 'Бишкек, ул. Ибраимова, 115',
                    'passport_number': 'ID1234567', 'date_of_birth': '1993-01-20',
                    'profile': ['Alice Smith проверила тесты; контакт alice@example.test'],
                    'skills': [{'name': 'SQL', 'evidence': 'Alice Smith написала JOIN'}],
                    'checks': [{'name': 'npm test', 'status': 'passed'}]}
        clean, context = self.anon.prepare(original)
        serialized = json.dumps(clean, ensure_ascii=False)
        for raw in ('Alice Smith', 'alice@example.test', '555', 'Ибраимова', 'ID1234567', '1993-01-20'):
            self.assertNotIn(raw, serialized)
        self.assertEqual(clean['skills'][0]['name'], 'SQL')
        self.assertEqual(clean['checks'][0]['name'], 'npm test')
        self.assertIn(clean['claude_name'], clean['profile'][0])
        self.assertEqual(self.anon.restore(clean, context), original)

    def test_detects_unstructured_contact_network_and_home_path(self):
        text = ('Меня зовут Иван Петров, email: ivan@example.test, телефон +996 555 123 456. '
                'Адрес: Бишкек, улица Ибраимова, 115; дата рождения: 20.01.1993. '
                'Сервер 192.168.1.13 и 2001:db8::1, файл /Users/ivan/project/a.py, '
                'ссылка https://customer.example.test/profile?name=ivan.')
        clean, context = self.anon.prepare(text)
        for raw in ('Иван Петров', 'ivan@example.test', '555', 'Ибраимова', '20.01.1993', '192.168.1.13', '2001:db8::1', '/Users/ivan', 'customer.example'):
            self.assertNotIn(raw, clean)
        self.assertEqual(self.anon.restore(clean, context), text)

    def test_secret_values_never_enter_vault_or_return_on_restoration(self):
        original = {'password': 'hidden-password', 'token': 'hidden-token',
                    'text': 'password=private-value Authorization: Bearer secret-value sk-' + 'a' * 30,
                    'endpoint': 'postgres://user:db-password@localhost/db'}
        clean, context = self.anon.prepare(original)
        restored = self.anon.restore(clean, context)
        all_saved = json.dumps([clean, restored, json.loads(self.vault.read_text())])
        for raw in ('hidden-password', 'hidden-token', 'private-value', 'secret-value', 'sk-' + 'a' * 30, 'db-password'):
            self.assertNotIn(raw, all_saved)
        self.assertIn(privacy.SECRET, all_saved)

    def test_retries_and_another_process_keep_existing_tokens(self):
        clean, _ = self.anon.prepare({'email': 'alice@example.test', 'project': 'private-client', 'session_id': 'session-alice'})
        again, _ = privacy.Anonymizer(self.vault).prepare(clean)
        same, _ = privacy.Anonymizer(self.vault).prepare({'email': 'alice@example.test', 'project': 'private-client', 'session_id': 'session-alice'})
        self.assertEqual(clean, again)
        self.assertEqual(clean, same)

    def test_restore_does_not_resolve_tokens_from_another_request_or_unused_dictionary(self):
        other, _ = self.anon.prepare('other@example.test')
        current, context = self.anon.prepare('current@example.test', [{'category': 'PERSON', 'value': 'Never Sent'}])
        entries = json.loads(self.vault.read_text())['entries']
        unused = next(token for token, value in entries.items() if value['value'] == 'Never Sent')
        response = current + ' ' + other + ' ' + unused
        restored = self.anon.restore(response, context)
        self.assertIn('current@example.test', restored)
        self.assertNotIn('other@example.test', restored)
        self.assertNotIn('Never Sent', restored)

    def test_concurrent_hooks_do_not_lose_mappings_or_change_shared_entity(self):
        def prepare(index):
            return privacy.Anonymizer(self.vault).prepare({'email': 'same@example.test', 'text': f'other{index}@example.test'})[0]
        with ThreadPoolExecutor(max_workers=8) as pool:
            outputs = list(pool.map(prepare, range(24)))
        self.assertEqual(len({item['email'] for item in outputs}), 1)
        self.assertEqual(len({item['text'] for item in outputs}), 24)
        self.assertEqual(len(json.loads(self.vault.read_text())['entries']), 25)

    def test_invalid_vault_and_symlink_do_not_allow_unprotected_output(self):
        self.vault.parent.mkdir()
        self.vault.write_text('invalid-private-record')
        with self.assertRaises(privacy.PrivacyError):
            self.anon.prepare('alice@example.test')
        self.vault.unlink()
        target = self.root / 'some-file'
        target.write_text('unrelated')
        self.vault.symlink_to(target)
        with self.assertRaises(privacy.PrivacyError):
            self.anon.prepare('alice@example.test')
        self.assertEqual(target.read_text(), 'unrelated')

    def test_wrong_context_cannot_restore_and_vault_is_private(self):
        clean, context = self.anon.prepare('alice@example.test')
        other = privacy.Anonymizer(self.root / 'other/vault.json')
        other.prepare('bob@example.test')
        with self.assertRaises(privacy.PrivacyError):
            other.restore(clean, context)
        if os.name != 'nt':
            self.assertEqual(self.vault.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.vault.parent.stat().st_mode & 0o777, 0o700)

    def test_cli_writes_private_files_and_never_prints_originals(self):
        source, clean, context = (self.root / name for name in ('input.json', 'out.json', 'context.json'))
        source.write_text(json.dumps({'email': 'alice@example.test'}))
        args = [sys.executable, str(SCRIPT), 'prepare', '--json', '--input', str(source), '--output', str(clean), '--context', str(context), '--vault', str(self.vault)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('alice@example.test', result.stdout + result.stderr + clean.read_text() + context.read_text())
        restored = self.root / 'restored.json'
        result = subprocess.run([sys.executable, str(SCRIPT), 'restore', '--json', '--input', str(clean), '--output', str(restored), '--context', str(context), '--vault', str(self.vault)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(restored.read_text()), json.loads(source.read_text()))
        self.assertNotIn('alice@example.test', result.stdout + result.stderr)

    def test_numeric_personal_fields_restore_their_original_json_type(self):
        original = {'phone': 996555123456, 'passport_number': 12345678, 'values': [123456789012, 42], 'level': 3}
        clean, context = self.anon.prepare(original)
        self.assertNotIn('996555123456', json.dumps(clean))
        self.assertEqual(clean['level'], 3)
        self.assertEqual(self.anon.restore(clean, context), original)

    def test_overlapping_names_email_and_urls_restore_without_nested_placeholders(self):
        original = 'Alice Smith: alice@example.test; https://example.test/Alice?email=alice@example.test; /Users/Alice/customer/file.py'
        clean, context = self.anon.prepare(original, [{'category': 'PERSON', 'value': 'Alice'}, {'category': 'PERSON', 'value': 'Alice Smith'}, {'category': 'EMAIL', 'value': 'alice@example.test'}])
        self.assertNotIn('Alice', clean)
        self.assertEqual(self.anon.restore(clean, context), original)

    def test_cli_rejects_shared_context_vault_and_input_paths_without_overwriting(self):
        source = self.root / 'original.json'
        source.write_text('{"email":"alice@example.test"}')
        self.anon.prepare('before@example.test')
        vault_before = self.vault.read_bytes()
        for context in (self.vault, source):
            result = subprocess.run([sys.executable, str(SCRIPT), 'prepare', '--json',
                                     '--input', str(source), '--output', str(self.root / 'output.json'),
                                     '--context', str(context), '--vault', str(self.vault)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(self.vault.read_bytes(), vault_before)
            self.assertEqual(source.read_text(), '{"email":"alice@example.test"}')
            self.assertFalse((self.root / 'output.json').exists())


if __name__ == '__main__':
    unittest.main()
