"""Ensure a distributable skill cannot include local restoration tables."""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]


class PrivacyPackagingTest(unittest.TestCase):
    def test_local_vault_and_context_are_excluded_without_removing_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            skill = root / 'skill'
            shutil.copytree(ROOT / 'skills/arslanbek-ai-mentor', skill)
            (skill / 'privacy').mkdir(exist_ok=True)
            (skill / 'privacy/vault.json').write_text(json.dumps({'namespace': '0123456789ab', 'entries': {'identity': 'alice@example.test'}}))
            (skill / 'references/local-context.json').write_text(json.dumps({'namespace': '0123456789ab', 'tokens': ['private-token']}))
            (skill / 'local-vault.json').write_text(json.dumps({'namespace': '0123456789ab', 'entries': {}}))
            spec = importlib.util.spec_from_file_location('privacy_package_test', ROOT / 'backend/railway/package-skill.py')
            builder = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(builder)
            output = root / 'release.zip'
            with patch.object(builder, 'SKILL', skill), patch.object(builder, 'ROOT', root), patch.object(builder, 'OUTPUT', output), patch('sys.stdout', io.StringIO()):
                builder.main()
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertIn('arslanbek-ai-mentor/scripts/anonymizer.py', names)
                self.assertIn('arslanbek-ai-mentor/references/privacy.md', names)
                for path in ('privacy/vault.json', 'references/local-context.json', 'local-vault.json'):
                    self.assertNotIn('arslanbek-ai-mentor/' + path, names)
                for name in names:
                    self.assertNotIn(b'alice@example.test', archive.read(name))


if __name__ == '__main__':
    unittest.main()
