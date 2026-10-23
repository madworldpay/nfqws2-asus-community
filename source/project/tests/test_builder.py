"""Catch wrong native payloads before packaging or router rules."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import subprocess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('asus_builder', ROOT/'asus/build.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)

class BuilderTests(unittest.TestCase):
    def test_build_number_is_validated_and_opkg_orders_successive_builds(self):
        self.assertTrue(callable(getattr(builder, 'package_version', None)), 'build number support is missing')
        versions = [builder.package_version(n) for n in ['1', '2', '10']]
        self.assertEqual(versions, [builder.CORE_VERSION+'+b'+n for n in ['1', '2', '10']])
        for invalid in ['', '0', '-1', '01', '1\n2', '1;id', '1.2']:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                builder.package_version(invalid)
        opkg = ROOT/'.work/packaging-audit-20261012/opkg-x64'
        if opkg.exists():
            with tempfile.TemporaryDirectory() as td:
                cfg = Path(td)/'opkg.conf'; cfg.write_text('arch all 100\n')
                (Path(td)/'root/opt/tmp').mkdir(parents=True)
                for old, new in [('1.3.1-asus5', versions[0]), *zip(versions, versions[1:])]:
                    result = subprocess.run([str(opkg), '-f', str(cfg), '-o', str(Path(td)/'root'), '--tmp-dir',td, 'compare-versions', new, '>', old], capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
    def test_native_targets_validate_all_elf_components(self):
        self.assertTrue(hasattr(builder, 'TARGETS'), 'architecture selection is missing')
        for arch, cls, machine in [('armv7-3.2', 1, 40), ('aarch64-3.10', 2, 183)]:
            target = builder.TARGETS[arch]
            for component in ['engine', 'busybox', 'lighttpd', 'mod_cgi']:
                elf = bytearray(64); elf[:6] = b'\x7fELF'+bytes([cls, 1]); elf[18:20] = machine.to_bytes(2,'little')
                builder.validate_elf(bytes(elf), target, component)
                elf[18:20] = (62).to_bytes(2,'little')
                with self.assertRaisesRegex(RuntimeError, component):
                    builder.validate_elf(bytes(elf), target, component)
                with self.assertRaises(RuntimeError):
                    builder.validate_elf(b'not an elf', target, component)
    def test_missing_offline_asset_identifies_file(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, 'Missing cached asset: busybox'):
                builder.asset('busybox_1.37.0-6_aarch64-3.10.ipk', Path(d), True)
    def test_corrupt_cached_asset_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            name='busybox_1.37.0-6_aarch64-3.10.ipk'; (Path(d)/name).write_bytes(b'bad')
            with self.assertRaisesRegex(RuntimeError, 'SHA256 mismatch'):
                builder.asset(name, Path(d), True)

    def test_engine_unpack_verifies_derived_bytes_and_rejects_wrong_output(self):
        import hashlib
        target = {**builder.TARGETS['armv7-3.2'],
                  'packed_sha256': hashlib.sha256(b'packed').hexdigest(),
                  'unpacked_sha256': hashlib.sha256(b'plain').hexdigest()}
        # The host UPX executable is external; use an executable fixture that
        # actually writes output. A wrong/untrusted transform must not ship.
        with tempfile.TemporaryDirectory() as td:
            exe = Path(td)/'upx'
            exe.write_text('#!/bin/sh\nprintf plain > "$3"\n')
            exe.chmod(0o755)
            with patch.dict('os.environ', {'NFQWS_BUILD_UPX': str(exe)}):
                self.assertEqual(builder.prepare_engine(b'packed', target), b'plain')
                exe.write_text('#!/bin/sh\nprintf corrupt > "$3"\n')
                with self.assertRaisesRegex(RuntimeError, 'unpacked engine SHA256'):
                    builder.prepare_engine(b'packed', target)
                with self.assertRaisesRegex(RuntimeError, 'packed engine SHA256'):
                    builder.prepare_engine(b'other', target)
