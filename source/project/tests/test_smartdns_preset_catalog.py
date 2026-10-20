"""The checked-in choices must match their pinned source and TLS bootstrap data."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('dns_presets', ROOT / 'asus/smartdns/build-presets.py')
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)


class SmartDnsPresetCatalogTests(unittest.TestCase):
    def test_checked_in_catalog_is_reproducible(self):
        actual = json.loads((ROOT / 'webui/web/src/api/smartDnsPresets.json').read_text())
        self.assertEqual(GEN.generate(), actual)

    def fixture(self, directory):
        root = Path(directory)
        (root / 'support').mkdir()
        for name in ['dpi-catalog.json', 'dpi-native-defaults.json', 'smartdns-preset-bootstrap.json']:
            (root / 'support' / name).write_bytes((ROOT / 'support' / name).read_bytes())
        return root

    def test_missing_bootstrap_never_falls_back_to_system_dns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            path = root / 'support/smartdns-preset-bootstrap.json'
            data = json.loads(path.read_text())
            del data['hosts']['wikimedia-dns.org']
            path.write_text(json.dumps(data))
            with patch.object(GEN, 'ROOT', root), self.assertRaisesRegex(ValueError, 'Missing explicit bootstrap'):
                GEN.generate()

    def test_mixed_upstream_versions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            path = root / 'support/dpi-native-defaults.json'
            data = json.loads(path.read_text())
            data['commit'] = 'wrong-version'
            path.write_text(json.dumps(data))
            with patch.object(GEN, 'ROOT', root), self.assertRaisesRegex(ValueError, 'same pinned version'):
                GEN.generate()
