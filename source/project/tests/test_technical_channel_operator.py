"""Operator discovery rejects untrusted or stale metadata before key authentication."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

PATH = Path(__file__).resolve().parents[1]/'technical-channel/connect.py'


class TechnicalOperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('technical_operator', PATH)
        cls.operator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.operator)

    def test_banner_login_is_bound_to_the_requested_signed_session(self):
        self.assertEqual(self.operator.parse_banner(b'NFQWS2-TECH-META/1 '+b'b'*32+b' owner_123\nno authentication methods\n', 'b'*32), 'owner_123')

    def test_missing_legacy_banner_session_mixup_and_unsafe_login_fail_closed(self):
        for raw in [b'Permission denied (publickey).\n',
                    b'NFQWS2-TECH-META/1 '+b'a'*32+b' root\n',
                    b'NFQWS2-TECH-META/2 '+b'b'*32+b' root\n',
                    b'NFQWS2-TECH-META/1 '+b'b'*32+b' root;id\n',
                    b'NFQWS2-TECH-META/1 '+b'b'*32+b' -oProxyCommand=id\n',
                    b'NFQWS2-TECH-META/1 '+b'b'*32+b' root extra\n',
                    b'NFQWS2-TECH-META/1 '+b'b'*32+b' root\nNFQWS2-TECH-META/1 '+b'b'*32+b' admin\n',
                    b'NFQWS2-TECH-META/1 '+b'b'*32+b' root\x00\n', b'x'*16385]:
            with self.subTest(raw=raw[:100]):
                with self.assertRaises(ValueError):
                    self.operator.parse_banner(raw, 'b'*32)

    def test_expired_or_unsafe_session_files_are_rejected_before_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o700)
            path = root/'session.json'
            valid = dict(schema_version=1, purpose='technical_channel', session_id='b'*32,
                         remote_port=45091, expires_at=int(time.time())+60)
            for patch in [dict(expires_at=int(time.time())-1), dict(session_id='bad'),
                          dict(remote_port=True), dict(remote_port=22), dict(purpose='shell')]:
                with self.subTest(patch=patch):
                    path.write_text(json.dumps(valid | patch))
                    path.chmod(0o600)
                    with self.assertRaises(ValueError):
                        self.operator.load_session(root)
            path.write_text(json.dumps(valid))
            path.chmod(0o600)
            self.assertEqual(self.operator.load_session(root), (root, valid))
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                self.operator.load_session(root)
            path.unlink()
            path.symlink_to(root/'other')
            with self.assertRaises(OSError):
                self.operator.load_session(root)

    @unittest.skipUnless(shutil.which('ssh'), 'OpenSSH configuration parser required')
    def test_real_ssh_preserves_unicode_spaces_quotes_and_backslash_in_pin_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloads = root/'Загрузки с пробелом'
            downloads.mkdir()
            for path in [downloads/'known "hosts" \\ pin', root/"single'quote known hosts", root/'%d-literal known hosts']:
                with self.subTest(path=path):
                    path.write_text('')
                    args = self.operator.ssh_base(dict(remote_port=45091), path, 'fixture-router')
                    result = subprocess.run(args+['-G', '127.0.0.1'], stdin=subprocess.DEVNULL,
                                            text=True, capture_output=True, timeout=5, check=True)
                    configured = next(line.removeprefix('userknownhostsfile ') for line in result.stdout.splitlines()
                                      if line.startswith('userknownhostsfile '))
                    self.assertEqual(configured, str(path))
                    self.assertTrue(Path(configured).samefile(path))

    def test_control_characters_and_ssh_environment_expansion_in_pin_path_fail_closed(self):
        for suffix in ['\x00', '\n', '\r', '\t', '\x1b', '\x7f', '\x85', '${HOME}']:
            with self.subTest(suffix=suffix):
                with self.assertRaises(ValueError):
                    self.operator.ssh_base(dict(remote_port=45091), Path('/tmp/pins'+suffix), 'fixture-router')


if __name__ == '__main__':
    unittest.main()
