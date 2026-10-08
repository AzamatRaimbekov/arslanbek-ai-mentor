"""Inspect distributed runtimes and their actual outgoing HTTP, locally only."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import test_privacy_delivery as delivery

ROOT = Path(__file__).resolve().parents[2]
DOWNLOADS = ROOT / 'dashboard/public/downloads'


class DownloadedPrivacyTest(delivery.PrivacyDeliveryTest):
    def setUp(self):
        archive = DOWNLOADS / 'arslanbek-ai-mentor.zip'
        if not archive.exists():
            self.skipTest('Build the downloadable release first')
        extracted = tempfile.TemporaryDirectory()
        self.addCleanup(extracted.cleanup)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted.name)
        scripts = Path(extracted.name) / 'arslanbek-ai-mentor/scripts'
        replacement = patch.object(delivery, 'SCRIPTS', scripts)
        replacement.start()
        self.addCleanup(replacement.stop)
        super().setUp()


class DistributedPrivacyFilesTest(unittest.TestCase):
    def test_each_distributed_client_contains_tested_anonymizer_and_no_private_table(self):
        manifest = DOWNLOADS / 'release.json'
        if not manifest.exists():
            self.skipTest('Build client downloads first')
        releases = json.loads(manifest.read_text())['files']
        expected = (ROOT / 'skills/arslanbek-ai-mentor/scripts/anonymizer.py').read_bytes()
        for filename, metadata in releases.items():
            with self.subTest(client=filename):
                path = DOWNLOADS / filename
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), metadata['sha256'])
                with zipfile.ZipFile(path) as bundle:
                    self.assertEqual(bundle.read('arslanbek-ai-mentor/scripts/anonymizer.py'), expected)
                    self.assertIn('arslanbek-ai-mentor/references/privacy.md', bundle.namelist())
                    self.assertFalse(any(name.endswith('/vault.json') for name in bundle.namelist()))
                    self.assertNotIn('arslanbek_restore', bundle.read('arslanbek-ai-mentor/scripts/mcp-server.py').decode())


if __name__ == '__main__':
    unittest.main()
