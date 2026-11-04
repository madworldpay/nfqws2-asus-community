"""Validate native settings identities without a complete backup or a router."""
import subprocess
import unittest

from test_dpi_normalize import ROOT
from test_package_update_guard import NATIVE


@unittest.skipUnless(NATIVE.is_file(), 'native PHP fixture required')
class NativeUpdateSnapshotTests(unittest.TestCase):
    def test_state_and_backup_verification_share_strict_live_settings_proof(self):
        result = subprocess.run(
            [str(NATIVE), '-n', '-f', str(ROOT / 'tests/test_openwrt_update_snapshot.php')],
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertIn('PASS:', result.stdout)
