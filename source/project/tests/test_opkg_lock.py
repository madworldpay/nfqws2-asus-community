"""Installer and postinst preflight under the real Entware opkg lock."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPKG = Path(os.environ.get('OPKG_TEST_BINARY', ROOT / '.work/packaging-audit-20261012/opkg-x64'))
spec = importlib.util.spec_from_file_location('builder', ROOT / 'asus/build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@unittest.skipUnless(OPKG.exists(), 'matching test opkg not supplied')
class OpkgLockTests(unittest.TestCase):
    def install(self, runtime=False):
        with tempfile.TemporaryDirectory() as td:
            w = Path(td)
            root = w / 'root'
            (root / 'opt/tmp').mkdir(parents=True)
            cfg = root / 'opt/etc/opkg.conf'
            cfg.parent.mkdir(parents=True)
            cfg.write_text('dest root /\narch all 100\narch aarch64-3.10 160\n')
            (w / 'tmp').mkdir()
            base = [str(OPKG), '-f', str(cfg), '-o', str(root), '--force-postinstall', '--tmp-dir', str(w / 'tmp')]
            commands = w / 'bin'
            commands.mkdir()
            status = w / 'proc-status'
            status.write_text('Uid:\t0\t0\t0\t0\n')
            for name, body in {
                'opkg': 'exec ' + shlex.join(base) + ' "$@"',
                'nvram': 'case "$2" in sw_mode) echo 1;; *) echo GT-BE19000AI;; esac',
                'uname': 'echo aarch64',
                'cru': 'exit 0',
                'id': 'echo 0',
            }.items():
                p = commands / name
                p.write_text('#!/bin/sh\n' + body + '\n')
                p.chmod(0o755)
            controls = {'control': (b'Package: nfqws-lock-probe\nVersion: 1\nArchitecture: aarch64-3.10\nDescription: lock regression\n', 0o644)}
            payload = {}
            if runtime:
                body = (ROOT / 'asus/lifecycle.sh').read_text().replace('/opt/', str(root) + '/opt/')
                body += '\nasus_model() { return 0; }\nasus_error() { echo "$*" >&2; }\nasus_validate() { return 0; }\nasus_load_modules() { :; }\nasus_probe_family() { return 0; }\n'
                # Tool selection probes the router's kernel. This fixture
                # exercises the real opkg/ABI lock boundary, not netfilter.
                body += 'asus_choose_tools() { return 0; }\nNFQWS_BIN=/bin/true; IPV6_ENABLED=0; asus_check\n'
                controls['postinst'] = (('#!/bin/sh\n' + body).encode(), 0o755)
                payload['opt/lib/nfqws2-asus/target.sh'] = (b"ASUS_PACKAGE_ARCH='aarch64-3.10'\n", 0o644)
                payload['opt/libexec/nfqws2-asus/busybox'] = (b'#!/bin/sh\nexit 0\n', 0o755)
                payload['opt/lib/nfqws2-asus/abi.sh'] = ((ROOT/'asus/abi.sh').read_text().replace('/opt/', str(root)+'/opt/').encode(), 0o644)
            else:
                body = (ROOT / 'asus/ipk/preinst').read_text().replace('. /opt/lib/nfqws2-asus/abi.sh', (ROOT/'asus/abi.sh').read_text()).replace('/proc/self/status', str(status)).replace('/opt/', str(root) + '/opt/')
                controls['preinst'] = (body.encode(), 0o755)
            pkg = w / 'probe.ipk'
            pkg.write_bytes(builder.compressed_tar({'debian-binary': (b'2.0\n', 0o644), 'control.tar.gz': (builder.compressed_tar(controls), 0o644), 'data.tar.gz': (builder.compressed_tar(payload), 0o644)}))
            result = subprocess.run(base + ['install', str(pkg)], env={**os.environ, 'PATH': str(commands) + ':' + os.environ['PATH']}, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_preinst_checks_abi_while_parent_opkg_holds_lock(self):
        self.install()

    def test_postinst_runtime_check_while_parent_opkg_holds_lock(self):
        self.install(runtime=True)

    def test_arch_declarations_match_real_opkg_parser(self):
        cases = ['arch "aarch64-3.10" 160\n', '"arch" "aarch64-3.10" "160"\n',
                 'arch aarch64-3.10 160', 'arch aarch64-3.10 160 # arch\n',
                 'arch aarch64-3.10 160 extra\n', 'arch aarch64-3.10 "160 spaces"\n',
                 'arch aarch64-3.10\n', '"arch""aarch64-3.10""160"\n',
                 'arch armv7-3.2 160\n', '# arch aarch64-3.10 160\n']
        with tempfile.TemporaryDirectory() as td:
            w = Path(td); (w/'root/opt/tmp').mkdir(parents=True); (w/'tmp').mkdir()
            cfg = w/'opkg.conf'
            helper = (ROOT/'asus/abi.sh').read_text().replace('/opt/etc/opkg.conf', str(cfg)).replace('/opt/etc/opkg/*.conf', str(w/'*.extra.conf'))
            for line in cases:
                with self.subTest(line=line):
                    cfg.write_text('dest root /\n'+line)
                    actual = subprocess.run([str(OPKG), '-f', str(cfg), '-o', str(w/'root'), '--tmp-dir', str(w/'tmp'), 'print-architecture'], text=True, capture_output=True, check=True)
                    prefix = ''
                    if os.environ.get('MIGRATION_BUSYBOX_TEST_BINARY'):
                        prefix = 'awk() { '+shlex.quote(os.environ['MIGRATION_BUSYBOX_TEST_BINARY'])+' awk "$@"; }\n'
                    result = subprocess.run(['sh', '-c', prefix+helper+'\nasus_entware_abi_matches aarch64-3.10'], text=True, capture_output=True)
                    self.assertEqual(result.returncode == 0, 'arch aarch64-3.10 ' in actual.stdout, result.stderr+actual.stderr)

    def test_arch_drop_in_with_noglob_keeps_caller_flags(self):
        with tempfile.TemporaryDirectory() as td:
            w = Path(td); root = w/'root'
            (root/'opt/etc/opkg').mkdir(parents=True); (root/'opt/tmp').mkdir()
            (w/'tmp').mkdir()
            cfg = root/'opt/etc/opkg.conf'
            cfg.write_text('dest root /\narch all 100\n')
            (root/'opt/etc/opkg/arch.conf').write_text('arch aarch64-3.10 160')
            # opkg's offline-root mode scans root/etc/opkg, unlike live Entware.
            (root/'etc/opkg').mkdir(parents=True)
            (root/'etc/opkg/arch.conf').symlink_to(root/'opt/etc/opkg/arch.conf')
            actual = subprocess.run([str(OPKG), '-f', str(cfg), '-o', str(root), '--tmp-dir', str(w/'tmp'), 'print-architecture'], text=True, capture_output=True, check=True)
            self.assertIn('arch aarch64-3.10 ', actual.stdout)
            helper = (ROOT/'asus/abi.sh').read_text().replace('/opt/', str(root)+'/opt/')
            result = subprocess.run(['sh', '-c', 'set -f\n'+helper+'\nasus_entware_abi_matches aarch64-3.10 || exit $?\ncase "$-" in *f*) exit 0;; *) exit 9;; esac'], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
