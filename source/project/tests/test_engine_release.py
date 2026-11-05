"""Exercise the engine and Lua actually selected by both package builders.

Set NFQWS_TEST_ENGINE_CACHE to verified vendor IPKs and NFQWS_TEST_QEMU_DIR
to static qemu-user binaries. No packet interception or network probes run.
"""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CACHE = os.environ.get('NFQWS_TEST_ENGINE_CACHE')
QEMU = os.environ.get('NFQWS_TEST_QEMU_DIR')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@unittest.skipUnless(CACHE and QEMU, 'Requires verified vendor inputs and qemu-user')
class EngineReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asus = module('engine_asus_builder', 'asus/build.py')
        cls.native = module('engine_native_builder', 'openwrt/build.py')
        cls.source = cls.native.source_payload(CACHE, True)

    def test_all_seven_packaged_engine_families_run_the_reviewed_release(self):
        families = {'arm_cortex-a9': 'arm', 'aarch64_cortex-a53': 'aarch64',
                    'mips_24kc': 'mips', 'mipsel_24kc': 'mipsel',
                    'mips64_octeonplus': 'mips64', 'i386_pentium4': 'i386',
                    'x86_64': None}
        with tempfile.TemporaryDirectory() as folder:
            for arch, emulator in families.items():
                with self.subTest(arch=arch):
                    target = self.native.native_metadata('24.10', arch)
                    engine = self.native.prepare_engine(target, self.source, os.environ.get('NFQWS_BUILD_UPX'))
                    path = Path(folder) / target['engine']
                    path.write_bytes(engine)
                    path.chmod(0o755)
                    command = ([str(Path(QEMU) / ('qemu-' + emulator))] if emulator else []) + [str(path)]
                    version = subprocess.check_output(command + ['--version'], text=True, timeout=20)
                    self.assertIn('v1.0.7 (038c97e5819df10f8e8c22a2f1fffe57f2f7379b)', version)
                    result = subprocess.run(command + ['--qnum=0', '--fastpath-workaround=auto', '--dry-run'],
                                            capture_output=True, text=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    files = self.native.payload_files(target, engine, self.source)
                    baseline = json.loads(files['usr/share/nfqws2/report-baseline.json'][0])
                    self.assertEqual(baseline['engine']['version'], '1.0.7')
                    self.assertEqual(baseline['engine']['sha256'], hashlib.sha256(engine).hexdigest())

    def test_asus_and_native_deliver_the_same_reviewed_lua_and_arm_engine(self):
        native = self.native.prepare_engine(self.native.native_metadata('24.10', 'arm_cortex-a9'),
                                            self.source, os.environ.get('NFQWS_BUILD_UPX'))
        for arch in self.asus.TARGETS:
            with self.subTest(arch=arch):
                target = self.asus.TARGETS[arch]
                source = self.asus.asset(target['engine_asset'], Path(CACHE), True)
                engine = self.asus.prepare_engine(source[target['engine_member']], target)
                if arch == 'armv7-3.2':
                    self.assertEqual(engine, native)
                else:
                    self.assertEqual(hashlib.sha256(engine).hexdigest(),
                                     '96f61de18dafa255dbffb5f2cc34f23652ccf6bb34fd0c7d3d4fd4c196e80b29')
                for name in ['zapret-lib', 'zapret-antidpi', 'zapret-auto', 'zapret-obfs', 'zapret-pcap', 'zapret-tests']:
                    member = 'opt/etc/nfqws2/lua/' + name + '.lua.gz'
                    self.assertEqual(gzip.decompress(source[member]), gzip.decompress(self.source[member]))


if __name__ == '__main__':
    unittest.main()
