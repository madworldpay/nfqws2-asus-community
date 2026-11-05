"""Validate server-generated tracker WEBSITE rules with actual pinned engines."""
import os
from pathlib import Path
import shlex
import subprocess
import unittest
import test_import_torrent_sites as fixtures

ROOT = Path(__file__).resolve().parents[1]
ENGINE = os.environ.get('NFQWS_TEST_ENGINE_DIR')
QEMU = os.environ.get('NFQWS_TEST_QEMU_DIR')


@unittest.skipUnless(ENGINE and QEMU, 'Requires pinned unpacked 1.0.7 engines and qemu-user')
class TorrentSitesEngineTests(unittest.TestCase):
    def test_generated_profile_and_original_filters_parse_on_all_seven_engines(self):
        plan = fixtures.TorrentSitesImportTests().plan()
        self.assertTrue(plan.get('ready'), plan)
        changes = {r['key']: r['after'] for r in plan['changes']}
        base = changes['NFQWS_BASE_ARGS'].replace('/opt/etc/nfqws2/lua/', str(Path(ENGINE) / 'lua') + '/')
        base = base.replace('/opt/etc/nfqws2/blobs/tls_clienthello.bin', str(ROOT / 'asus/blobs/files/tls_clienthello.bin'))
        # CUSTOM runs before the main profile in both platforms' pinned common startup.
        args = shlex.split(base + ' ' + changes['NFQWS_ARGS_CUSTOM'] + ' --new ' + changes['NFQWS_ARGS'])
        families = {'armv7':'arm', 'aarch64':'aarch64', 'mips':'mips', 'mipsel':'mipsel',
                    'mips64':'mips64', 'x86':'i386', 'x86_64':None}
        for family, emulator in families.items():
            with self.subTest(family=family):
                command = ([str(Path(QEMU) / ('qemu-' + emulator))] if emulator else []) + [str(Path(ENGINE) / ('nfqws2-' + family))]
                version = subprocess.check_output(command + ['--version'], text=True, timeout=20)
                self.assertIn('v1.0.7 (038c97e5819df10f8e8c22a2f1fffe57f2f7379b)', version)
                result = subprocess.run(command + ['--qnum=0', '--fastpath-workaround=auto', '--dry-run'] + args,
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn('WARNING', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
