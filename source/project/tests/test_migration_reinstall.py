"""Ordinary Entware opkg remove/reinstall with retained settings and real BusyBox."""
import importlib.util
import io
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reinstall_builder', ROOT/'asus/build.py')
builder = importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
OPKG = Path(os.environ.get('OPKG_TEST_BINARY', ROOT/'.work/packaging-audit-20261012/opkg-x64'))
BUSYBOX = Path(os.environ.get('MIGRATION_BUSYBOX_TEST_BINARY', '/bin/busybox'))
QEMU_FIXTURES = Path(os.environ.get('MIGRATION_QEMU_TEST_DIR', ROOT/'.work/packaging-audit-20261012'))


@unittest.skipUnless(OPKG.exists() and BUSYBOX.exists(), 'test opkg and a real BusyBox required')
class ReinstallMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name);self.root = self.work/'root';(self.root/'opt/tmp').mkdir(parents=True)
        (self.work/'tmp').mkdir();self.config = self.work/'opkg.conf'
        self.config.write_text('dest root /\narch aarch64-3.10 160\n')
        self.base = [str(OPKG), '-f', str(self.config), '-o', str(self.root), '--force-postinstall', '--tmp-dir', str(self.work/'tmp')]
        self.private = self.root/'opt/libexec/nfqws2-asus/busybox'
        self.system = self.root/'bin/busybox';self.system.parent.mkdir()
        self.system.write_bytes(self.wrapper('system'));self.system.chmod(0o755)
        self.values = {
            'opt/etc/nfqws2/nfqws2.conf': b'# retained owner config\n',
            'opt/etc/nfqws2/lists/user.list': b'owner.example\n',
            'opt/etc/nfqws2/lists/custom.list': b'custom.example\n',
            'opt/etc/nfqws-asus-web/auth.json': b'{"private":"retained owner password"}\n',
            'opt/etc/nfqws-asus-web/ark-backup.json': b'{"backup":"retain"}\n',
        }

    def wrapper(self, label):
        return ('#!/bin/sh\nprintf "%s\\n" '+shlex.quote(label+':')+'"$1" >> '+shlex.quote(str(self.work/'tools'))+'\nexec '+shlex.quote(str(BUSYBOX))+' "$@"\n').encode()

    def migration(self):
        return (ROOT/'asus/ipk/migration.sh').read_text().replace('/opt/', str(self.root)+'/opt/').replace(
            'ASUS_MIGRATION_OWNER=0', f'ASUS_MIGRATION_OWNER={os.getuid()}').replace(
            ' /bin/busybox', ' '+str(self.system))

    def package(self, version='1.3.1-asus6+b62', bootstrap=True):
        data = {
            'opt/etc/nfqws2/nfqws2.conf.notactive': (b'# packaged template\n', 0o600),
            'opt/etc/nfqws2/lists/user.list.notactive': (b'template.example\n', 0o600),
            'opt/etc/nfqws-asus-web/auth.json': (b'{"factory":true}\n', 0o600),
            'opt/libexec/nfqws2-asus/busybox': (self.wrapper('private'), 0o755),
        }
        migration = self.migration()
        defaults = (ROOT/'asus/ipk/defaults.sh').read_text().replace('/opt/', str(self.root)+'/opt/')
        controls = {
            'control': (f'Package: nfqws2-asus\nVersion: {version}\nArchitecture: aarch64-3.10\nDescription: reinstall regression\n'.encode(), 0o644),
            'conffiles': (b'/opt/etc/nfqws-asus-web/auth.json\n', 0o644),
            'preinst': (("#!/bin/sh\nASUS_PACKAGE_ABI='aarch64-3.10'\n"+migration+'\nasus_migration_save || exit $?\n').encode(), 0o755),
            'postinst': (('#!/bin/sh\n'+migration+'\n'+defaults+'\nasus_migration_restore || exit $?\nasus_install_defaults || exit $?\nasus_migration_complete || exit $?\n').encode(), 0o755),
            'prerm': (b'#!/bin/sh\nexit 0\n', 0o755),
            'postrm': (b'#!/bin/sh\nexit 0\n', 0o755),
        }
        if bootstrap:controls['busybox-migration-aarch64-3.10'] = (self.wrapper('bootstrap'), 0o755)
        path = self.work/(version+'.ipk')
        path.write_bytes(builder.compressed_tar({'debian-binary': (b'2.0\n', 0o644),
                        'control.tar.gz': (builder.compressed_tar(controls), 0o644),
                        'data.tar.gz': (builder.compressed_tar(data), 0o644)}))
        return path

    def run_opkg(self, *args, ok=True):
        result = subprocess.run(self.base+list(map(str,args)), env={**os.environ, 'NFQWS_ASUS_NO_START': '1'},
                                capture_output=True, text=True, timeout=20)
        if ok:self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return result

    def write_data(self):
        for name, value in self.values.items():
            path = self.root/name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(value);path.chmod(0o600)

    def assert_data(self):
        for name, value in self.values.items():
            path = self.root/name;self.assertEqual(path.read_bytes(), value, name)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, name);self.assertEqual(path.stat().st_uid, os.getuid(), name)

    def assert_snapshot(self):
        snapshot = self.root/'opt/etc/nfqws2-asus-migration/snapshot'
        self.assertTrue((snapshot/'manifest').is_file());self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o700)
        for name in ['manifest', 'presence', 'config', 'auth', 'ark']:
            path = snapshot/name;self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, name)
            self.assertEqual(path.stat().st_uid, os.getuid(), name)
        for key, name in [('config', 'opt/etc/nfqws2/nfqws2.conf'), ('auth', 'opt/etc/nfqws-asus-web/auth.json'), ('ark', 'opt/etc/nfqws-asus-web/ark-backup.json')]:
            self.assertEqual((snapshot/key).read_bytes(), self.values[name], key)
        result = subprocess.run([str(BUSYBOX), 'sha256sum', '-c', 'manifest'], cwd=snapshot, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_documented_remove_then_same_package_reinstall_keeps_all_owner_data(self):
        package = self.package();self.run_opkg('install', package);self.write_data()
        self.run_opkg('remove', 'nfqws2-asus');self.assertFalse(self.private.exists())
        self.assertTrue((self.root/'opt/etc/nfqws-asus-web/auth.json').exists())
        self.run_opkg('install', package)
        self.assert_data();self.assert_snapshot()
        self.assertIn('bootstrap:sha256sum', (self.work/'tools').read_text())

    def test_retained_data_without_any_installed_runtime_gets_a_verified_snapshot(self):
        self.write_data();self.run_opkg('install', self.package(bootstrap=False))
        self.assert_data();self.assert_snapshot()
        self.assertIn('system:sha256sum', (self.work/'tools').read_text())

    def test_reinstall_uses_control_helper_when_stock_busybox_has_no_sha256_or_stat(self):
        self.write_data();self.system.write_text('#!/bin/sh\ncase "$1" in --list) printf "awk\\nchmod\\ncp\\nfind\\ngrep\\nmkdir\\nmv\\nrm\\nsync\\n";; *) exit 1;; esac\n');self.system.chmod(0o755)
        self.run_opkg('install', self.package());self.assert_data();self.assert_snapshot()
        self.assertIn('bootstrap:sha256sum', (self.work/'tools').read_text())

    def test_only_opkg_save_without_private_runtime_is_backed_up_and_restored(self):
        self.values = {'opt/etc/nfqws2/nfqws2.conf': b'legacy configuration\n',
                       'opt/etc/nfqws-asus-web/auth.json': b'legacy auth\n'}
        for name, value in self.values.items():
            path = self.root/(name+'.opkg-save');path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(value);path.chmod(0o600)
        self.run_opkg('install', self.package());self.assert_data()
        snapshot = self.root/'opt/etc/nfqws2-asus-migration/snapshot'
        self.assertEqual((snapshot/'config').read_bytes(), self.values['opt/etc/nfqws2/nfqws2.conf'])
        self.assertEqual((snapshot/'auth').read_bytes(), self.values['opt/etc/nfqws-asus-web/auth.json'])

    def test_fresh_install_still_succeeds_without_any_preinstalled_busybox(self):
        self.system.unlink();self.run_opkg('install', self.package())
        self.assertEqual((self.root/'opt/etc/nfqws2/nfqws2.conf').read_bytes(), b'# packaged template\n')
        self.assertTrue(self.private.is_file())

    def test_incomplete_system_busybox_fails_before_payload_or_owner_data_change(self):
        self.write_data();self.system.write_text('#!/bin/sh\ncase "$1" in --list) printf "cp\\nstat\\nfind\\n";; *) exit 0;; esac\n');self.system.chmod(0o755)
        result = self.run_opkg('install', self.package(bootstrap=False), ok=False)
        self.assertNotEqual(result.returncode, 0);self.assert_data();self.assertFalse(self.private.exists())
        self.assertFalse((self.root/'opt/etc/nfqws2-asus-migration/snapshot').exists())

    def test_no_system_busybox_with_retained_data_fails_before_unpack(self):
        self.write_data();self.system.unlink()
        result = self.run_opkg('install', self.package(bootstrap=False), ok=False)
        self.assertNotEqual(result.returncode, 0);self.assert_data();self.assertFalse(self.private.exists())

    def test_symlink_data_is_not_followed_by_system_fallback(self):
        outside = self.work/'outside';outside.write_bytes(b'KEEP')
        path = self.root/'opt/etc/nfqws2/nfqws2.conf';path.parent.mkdir(parents=True);path.symlink_to(outside)
        result = self.run_opkg('install', self.package(), ok=False)
        self.assertNotEqual(result.returncode, 0);self.assertTrue(path.is_symlink());self.assertEqual(outside.read_bytes(), b'KEEP')
        self.assertFalse(self.private.exists())

    def test_completed_previous_snapshot_is_retained_and_current_reinstall_data_is_backed_up(self):
        package = self.package();self.run_opkg('install', package);self.write_data();self.run_opkg('remove', 'nfqws2-asus')
        self.run_opkg('install', package);self.assert_snapshot()
        old = dict(self.values)
        self.values = {name: value+b'latest owner edit\n' for name,value in self.values.items()};self.write_data()
        self.run_opkg('remove', 'nfqws2-asus');self.run_opkg('install', package)
        self.assert_data();self.assert_snapshot()
        previous = list((self.root/'opt/etc').glob('nfqws2-asus-migration.previous.*'))
        self.assertEqual(len(previous), 1)
        self.assertEqual((previous[0]/'snapshot/config').read_bytes(), old['opt/etc/nfqws2/nfqws2.conf'])
        self.assertEqual(stat.S_IMODE(previous[0].stat().st_mode), 0o700)

    def test_corrupt_previous_snapshot_stops_reinstall_before_payload(self):
        package = self.package();self.run_opkg('install', package);self.write_data();self.run_opkg('remove', 'nfqws2-asus')
        self.run_opkg('install', package);self.run_opkg('remove', 'nfqws2-asus')
        snapshot = self.root/'opt/etc/nfqws2-asus-migration/snapshot';(snapshot/'config').write_bytes(b'CORRUPTED')
        result = self.run_opkg('install', package, ok=False)
        self.assertNotEqual(result.returncode, 0);self.assert_data();self.assertFalse(self.private.exists())
        self.assertEqual((snapshot/'config').read_bytes(), b'CORRUPTED')
        self.assertEqual(list((self.root/'opt/etc').glob('nfqws2-asus-migration.previous.*')), [])

    def test_dangling_legacy_opkg_save_symlink_stops_before_unpack(self):
        path = self.root/'opt/etc/nfqws2/nfqws2.conf.opkg-save';path.parent.mkdir(parents=True)
        path.symlink_to(self.work/'missing')
        result = self.run_opkg('install', self.package(), ok=False)
        self.assertNotEqual(result.returncode, 0);self.assertTrue(path.is_symlink());self.assertFalse(self.private.exists())


class MigrationBootstrapPackagingTests(unittest.TestCase):
    def verify_family(self, family):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            if family == 'aarch64-3.10':
                payload = {'opt/libexec/nfqws2-asus/busybox': (b'pinned aarch64 fixture', 0o755)}
                expected = {'busybox-migration-aarch64-3.10': b'pinned aarch64 fixture'}
            else:
                payload = {'opt/libexec/nfqws2-asus/busybox': (b'ABI selector shim', 0o755),
                           'opt/libexec/nfqws2-asus/armv7-2.6/busybox': (b'pinned legacy fixture', 0o755),
                           'opt/libexec/nfqws2-asus/armv7-3.2/busybox': (b'pinned modern fixture', 0o755)}
                expected = {'busybox-migration-armv7-2.6': b'pinned legacy fixture',
                            'busybox-migration-armv7-3.2': b'pinned modern fixture'}
            builder.package(output, 'nfqws2-asus', '1.3.1-asus6+b64', '', '', payload, 'unified',
                            arch='all' if family == 'armv7' else family, family=family, filename_arch=family)
            with tarfile.open(next(output.glob('*.ipk'))) as outer:
                with tarfile.open(fileobj=io.BytesIO(outer.extractfile('control.tar.gz').read())) as control:
                    helpers = {member.name.removeprefix('./'): member for member in control if member.name.removeprefix('./').startswith('busybox-migration-')}
                    self.assertEqual(set(helpers), set(expected))
                    for name, content in expected.items():
                        self.assertEqual(control.extractfile(helpers[name]).read(), content);self.assertEqual(helpers[name].mode, 0o755)
                    preinst = control.extractfile('preinst').read().decode()
                    self.assertIn('ASUS_PACKAGE_ABI=$(asus_resolve_package_abi', preinst)
                    self.assertLess(preinst.index('ASUS_PACKAGE_ABI=$(asus_resolve_package_abi'), preinst.index('asus_migration_save || exit $?'))

    def test_aarch64_preinst_gets_exact_payload_tool_in_control(self):self.verify_family('aarch64-3.10')

    def test_armv7_preinst_gets_both_exact_abi_payload_tools_in_control(self):self.verify_family('armv7')


class MigrationBootstrapExecutableTests(unittest.TestCase):
    """Execute the packaged ELF under its real basename; shell wrappers hide argv[0]."""
    def verify_executable(self, family, cases):
        locations = {abi: (QEMU_FIXTURES/emulator, QEMU_FIXTURES/sysroot)
                     for abi, emulator, sysroot in cases}
        if not all(emulator.exists() and (sysroot/'opt/bin/busybox').exists()
                   for emulator, sysroot in locations.values()):
            self.skipTest('matching QEMU/Entware BusyBox fixtures required')
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            payload = {'opt/libexec/nfqws2-asus/busybox': (b'ABI selector fixture', 0o755)}
            for abi, (_, sysroot) in locations.items():
                path = ('opt/libexec/nfqws2-asus/busybox' if family == 'aarch64-3.10' else
                        'opt/libexec/nfqws2-asus/'+abi+'/busybox')
                payload[path] = ((sysroot/'opt/bin/busybox').read_bytes(), 0o755)
            builder.package(output, 'nfqws2-asus', '1.3.1-asus6+b64', '', '', payload, 'unified',
                            arch='all' if family == 'armv7' else family, family=family, filename_arch=family)
            with tarfile.open(next(output.glob('*.ipk'))) as outer:
                with tarfile.open(fileobj=io.BytesIO(outer.extractfile('control.tar.gz').read())) as control:
                    for abi, (emulator, sysroot) in locations.items():
                        with self.subTest(abi=abi):
                            member = next(member for member in control if member.name.removeprefix('./').endswith('-'+abi))
                            executable = output/member.name.removeprefix('./')
                            executable.write_bytes(control.extractfile(member).read());executable.chmod(member.mode)
                            self.assertEqual(executable.read_bytes()[:4], b'\x7fELF')
                            command = [str(emulator), '-L', str(sysroot), str(executable)]
                            result = subprocess.run(command+['--list'], capture_output=True, text=True, timeout=5)
                            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                            self.assertIn('sha256sum', result.stdout.splitlines());self.assertIn('stat', result.stdout.splitlines())
                            good = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  /dev/null\n'
                            checked = subprocess.run(command+['sha256sum', '-c', '-'], input=good, capture_output=True, text=True, timeout=5)
                            self.assertEqual(checked.returncode, 0, checked.stdout+checked.stderr)

    def test_aarch64_bootstrap_runs_as_the_packaged_elf_name(self):
        self.verify_executable('aarch64-3.10', [('aarch64-3.10', 'qemu-aarch64', 'aarch64-sysroot')])

    def test_both_armv7_bootstraps_run_as_the_packaged_elf_names(self):
        self.verify_executable('armv7', [('armv7-2.6', 'qemu-arm', 'armv7-legacy-sysroot'),
                                       ('armv7-3.2', 'qemu-arm', 'armv7-sysroot')])


if __name__ == '__main__':unittest.main()
