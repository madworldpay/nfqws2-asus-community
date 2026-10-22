"""Ordinary Entware opkg remove/reinstall with retained settings and real BusyBox."""
import importlib.util
import io
import os
from pathlib import Path
import shlex
import shutil
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


@unittest.skipUnless(shutil.which('bwrap') and OPKG.exists() and Path('/bin/busybox').exists(),
                     'normal-root opkg, native BusyBox and bubblewrap required')
class NormalRootReinstallMigrationTests(unittest.TestCase):
    """Normal opkg uses package-prefixed info files; offline-root takes a different branch."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name);self.opt = self.work/'opt';self.temp = self.work/'tmp'
        (self.opt/'etc').mkdir(parents=True);(self.opt/'var/lock').mkdir(parents=True)
        (self.opt/'tmp').mkdir();self.temp.mkdir()
        (self.opt/'etc/opkg.conf').write_text('dest root /\narch aarch64-3.10 160\n')
        self.busybox = Path('/bin/busybox').read_bytes()
        stock = self.temp/'busybox-stock';stock.write_bytes(self.busybox);stock.chmod(0o755)
        self.stock_stub = self.work/'stock-stub'
        self.stock_stub.write_text('#!/bin/sh\nif [ "$1" = --list ]; then\n/tmp/busybox-stock --list | /tmp/busybox-stock grep -Ev "^(sha256sum|stat)$"\nelse exec /tmp/busybox-stock "$@"; fi\n')
        self.stock_stub.chmod(0o755)
        # All host paths are read-only. Only fixture /opt and /tmp can change;
        # a user namespace supplies root semantics and the network is absent.
        self.sandbox = ['bwrap', '--unshare-all', '--uid', '0', '--gid', '0', '--ro-bind', '/', '/',
                        '--bind', str(self.opt), '/opt', '--bind', str(self.temp), '/tmp',
                        '--ro-bind', str(self.stock_stub), '/bin/busybox', '--proc', '/proc', '--dev', '/dev',
                        '--chdir', '/tmp']
        probe = subprocess.run(self.sandbox+['/bin/true'], capture_output=True, text=True, timeout=5)
        if probe.returncode:self.skipTest('bubblewrap user namespace unavailable: '+probe.stderr[:100])
        self.values = {'etc/nfqws2/nfqws2.conf': b'owner config\n',
                       'etc/nfqws2/lists/user.list': b'owner.example\n',
                       'etc/nfqws2/lists/custom.list': b'custom.example\n',
                       'etc/nfqws-asus-web/auth.json': b'owner auth\n',
                       'etc/nfqws-asus-web/ark-backup.json': b'owner ARK backup\n'}

    def package(self, legacy=False, template=b'factory config\n', real_defaults=False):
        migration = (ROOT/'asus/ipk/migration.sh').read_text()
        # A frozen release source can be supplied to preserve RED evidence
        # without changing the working source while other work is running.
        defaults = Path(os.environ.get('MIGRATION_DEFAULTS_TEST_SOURCE', ROOT/'asus/ipk/defaults.sh')).read_text()
        controls = {
            'control': (('Package: nfqws2-asus\nVersion: 1.3.1-asus6+b'+('62' if legacy else '64')+'\nArchitecture: aarch64-3.10\nDescription: normal-root reinstall fixture\n').encode(), 0o644),
            'conffiles': (b'/opt/etc/nfqws-asus-web/auth.json\n', 0o644),
            'preinst': (("#!/bin/sh\nASUS_PACKAGE_ABI='aarch64-3.10'\nprintf '%s\\n' \"$0\" >> /tmp/preinst-paths\n"+migration+'\nasus_migration_save || exit $?\n').encode(), 0o755),
            'postinst': (('#!/bin/sh\n'+migration+'\n'+defaults+'\nasus_migration_restore || exit $?\nasus_install_defaults || exit $?\n'+
                         '[ -f /opt/etc/nfqws2/nfqws2.conf ] || { echo "ASUS NFQWS2: Configuration missing: /opt/etc/nfqws2/nfqws2.conf" >&2; exit 1; }\n'+
                         'asus_migration_complete || exit $?\n').encode(), 0o755),
            'prerm': (b'#!/bin/sh\nexit 0\n', 0o755), 'postrm': (b'#!/bin/sh\nexit 0\n', 0o755),
            # The helper itself is an ELF, never a wrapper changing argv[0].
            'busybox-migration-aarch64-3.10': (self.busybox, 0o755),
        }
        data = {'opt/libexec/nfqws2-asus/busybox': (self.busybox, 0o755),
                'opt/etc/nfqws2/nfqws2.conf.notactive': (template, 0o600),
                'opt/etc/nfqws2/lists/user.list.notactive': (b'factory list\n', 0o600),
                'opt/etc/nfqws-asus-web/auth.json': (b'factory auth\n', 0o600)}
        if legacy:
            controls['conffiles'] = (controls['conffiles'][0]+b'/opt/etc/nfqws2/nfqws2.conf\n/opt/etc/nfqws2/lists/user.list\n', 0o644)
            del data['opt/etc/nfqws2/nfqws2.conf.notactive'];del data['opt/etc/nfqws2/lists/user.list.notactive']
            data['opt/etc/nfqws2/nfqws2.conf'] = (b'legacy factory config\n', 0o600)
            data['opt/etc/nfqws2/lists/user.list'] = (b'legacy factory list\n', 0o600)
        if real_defaults:
            public = Path(os.environ.get('MIGRATION_PREFLIGHT_IPK_TEST_FILE',
                          ROOT/'.work/build64-release/nfqws2-asus_1.3.1-asus6+b64_aarch64-3.10.ipk'))
            emulator = QEMU_FIXTURES/'qemu-aarch64';sysroot = QEMU_FIXTURES/'aarch64-sysroot'
            if not public.exists() or not emulator.exists() or not sysroot.exists():
                self.skipTest('packaged AArch64 defaults/engine and matching QEMU runtime required')
            data = {name: value for name,value in data.items() if not name.startswith('opt/etc/nfqws2/')}
            with tarfile.open(public) as outer:
                with tarfile.open(fileobj=io.BytesIO(outer.extractfile('data.tar.gz').read())) as payload:
                    for member in payload:
                        name = member.name.removeprefix('./')
                        if member.isfile() and (name.startswith('opt/etc/nfqws2/') or
                           name in ['opt/lib/nfqws2-asus/args.sh', 'opt/usr/bin/nfqws2']):
                            data[name] = (payload.extractfile(member).read(), member.mode)
            preflight = ('mkdir -p /opt/var/log\nset -f\n. /opt/etc/nfqws2/nfqws2.conf\n. /opt/lib/nfqws2-asus/args.sh\n'+
                         'args=$(_startup_args | sed "s/--user=[^ ]* //")\n'+
                         shlex.join([str(emulator), '-L', str(sysroot), '/opt/usr/bin/nfqws2'])+' --dry-run $args || exit $?\n')
            controls['postinst'] = (controls['postinst'][0].replace(b'asus_migration_complete || exit $?',
                                    preflight.encode()+b'asus_migration_complete || exit $?'), 0o755)
        (self.temp/'candidate.ipk').write_bytes(builder.compressed_tar({'debian-binary': (b'2.0\n', 0o644),
                   'control.tar.gz': (builder.compressed_tar(controls), 0o644), 'data.tar.gz': (builder.compressed_tar(data), 0o644)}))

    def run_opkg(self, opkg, *args):
        result = subprocess.run(self.sandbox+opkg+['-f', '/opt/etc/opkg.conf', '--tmp-dir', '/tmp']+list(args),
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr+'\npreinst paths: '+
                         ((self.temp/'preinst-paths').read_text() if (self.temp/'preinst-paths').exists() else 'none'))

    def exercise(self, opkg):
        self.package();self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        for name, value in self.values.items():
            path = self.opt/name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(value);path.chmod(0o600)
        self.run_opkg(opkg, 'remove', 'nfqws2-asus');self.assertFalse((self.opt/'libexec/nfqws2-asus/busybox').exists())
        self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        # Installed info files are prefixed, but both actual opkg binaries run
        # the new preinst from its unprefixed temporary control directory.
        self.assertTrue((self.opt/'lib/opkg/info/nfqws2-asus.busybox-migration-aarch64-3.10').is_file())
        for path in (self.temp/'preinst-paths').read_text().splitlines():
            self.assertRegex(path, r'^/tmp/opkg-[A-Za-z0-9]+/nfqws2-asus-[A-Za-z0-9]+/preinst$')
        for name, value in self.values.items():self.assertEqual((self.opt/name).read_bytes(), value, name)
        snapshot = self.opt/'etc/nfqws2-asus-migration/snapshot'
        self.assertEqual((snapshot/'config').read_bytes(), self.values['etc/nfqws2/nfqws2.conf'])
        self.assertEqual((snapshot/'auth').read_bytes(), self.values['etc/nfqws-asus-web/auth.json'])
        self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o700)
        self.assertEqual(list(self.temp.glob('nfqws2-migration.*')), [], 'temporary executable aliases must be cleaned')

    def test_normal_opkg_remove_reinstall_with_real_elf_bootstrap(self):
        self.exercise([str(OPKG)])

    def test_actual_aarch64_opkg_normal_remove_reinstall(self):
        actual = os.environ.get('OPKG_AARCH64_TEST_BINARY')
        emulator = QEMU_FIXTURES/'qemu-aarch64'
        if not actual or not Path(actual).is_file() or not emulator.is_file():
            self.skipTest('actual AArch64 opkg and QEMU required')
        # The actual ARM opkg executes host-native fixture scripts/tools after
        # execve. Separate direct-ELF tests cover all target BusyBox ABIs.
        self.exercise([str(emulator), actual])

    def missing_config_with_retained_lists(self, opkg):
        self.package(legacy=True);self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        lists = self.opt/'etc/nfqws2/lists';(lists/'user.list').write_bytes(b'owner retained list\n')
        (lists/'custom.list').write_bytes(b'custom retained list\n')
        self.run_opkg(opkg, 'remove', 'nfqws2-asus')
        self.assertFalse((self.opt/'etc/nfqws2/nfqws2.conf').exists(), 'opkg removes the unmodified legacy conffile')
        self.assertFalse((self.opt/'etc/nfqws2-asus-migration/defaults-initialized').exists())
        self.package(template=b'current package config\n');self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        self.assertEqual((self.opt/'etc/nfqws2/nfqws2.conf').read_bytes(), b'current package config\n')
        self.assertEqual((lists/'user.list').read_bytes(), b'owner retained list\n')
        self.assertEqual((lists/'custom.list').read_bytes(), b'custom retained list\n')

    def test_normal_remove_reinstall_initializes_missing_config_without_replacing_retained_lists(self):
        self.missing_config_with_retained_lists([str(OPKG)])

    def test_actual_aarch64_opkg_reinstall_with_retained_lists_and_missing_config(self):
        actual = os.environ.get('OPKG_AARCH64_TEST_BINARY');emulator = QEMU_FIXTURES/'qemu-aarch64'
        if not actual or not Path(actual).is_file() or not emulator.is_file():self.skipTest('actual AArch64 opkg and QEMU required')
        self.missing_config_with_retained_lists([str(emulator), actual])

    def test_defaults_marker_does_not_skip_missing_config_or_reactivate_deleted_lists(self):
        opkg = [str(OPKG)];self.package();self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        self.run_opkg(opkg, 'remove', 'nfqws2-asus')
        config = self.opt/'etc/nfqws2/nfqws2.conf';config.unlink()
        lists = self.opt/'etc/nfqws2/lists';(lists/'user.list').unlink()
        # Saved package candidates are not active owner data. The next payload
        # replaces .notactive, while .opkg-new must never become the config.
        (config.parent/'nfqws2.conf.opkg-new').write_bytes(b'foreign old package candidate\n')
        (config.parent/'nfqws2.conf.notactive').write_bytes(b'stale template\n')
        self.assertTrue((self.opt/'etc/nfqws2-asus-migration/defaults-initialized').is_file())
        self.package(template=b'current replacement template\n');self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        self.assertEqual(config.read_bytes(), b'current replacement template\n')
        self.assertFalse((lists/'user.list').exists())
        self.assertEqual((config.parent/'nfqws2.conf.opkg-new').read_bytes(), b'foreign old package candidate\n')
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)

    def test_marker_and_deleted_config_tree_reinstall_passes_real_engine_preflight(self):
        opkg = [str(OPKG)];self.package(real_defaults=True);self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        self.run_opkg(opkg, 'remove', 'nfqws2-asus')
        shutil.rmtree(self.opt/'etc/nfqws2')
        self.assertTrue((self.opt/'etc/nfqws2-asus-migration/defaults-initialized').exists())
        self.package(real_defaults=True);self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        for name in ['user.list', 'auto.list', 'exclude.list', 'ipset.list', 'ipset_exclude.list']:
            self.assertTrue((self.opt/'etc/nfqws2/lists'/name).is_file(), name)

    def test_missing_config_restores_required_stock_lists_and_preserves_retained_files(self):
        opkg = [str(OPKG)];self.package(real_defaults=True);self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        self.run_opkg(opkg, 'remove', 'nfqws2-asus')
        config = self.opt/'etc/nfqws2/nfqws2.conf';config.unlink()
        lists = self.opt/'etc/nfqws2/lists'
        for name in ['auto.list', 'ipset.list', 'ipset_exclude.list']:(lists/name).unlink()
        retained = {'user.list': b'owner.example\n', 'exclude.list': b'excluded-owner.example\n',
                    'custom.list': b'custom.example\n', 'optional.list.notactive': b'never activate\n'}
        for name, content in retained.items():(lists/name).write_bytes(content)
        self.package(real_defaults=True);self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        for name, content in retained.items():self.assertEqual((lists/name).read_bytes(), content, name)
        self.assertFalse((lists/'optional.list').exists())

    def test_existing_owner_config_does_not_restore_lists_it_no_longer_uses(self):
        opkg = [str(OPKG)];self.package(real_defaults=True);self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        config = self.opt/'etc/nfqws2/nfqws2.conf'
        owner = config.read_text().replace('NFQWS_ARGS_IPSET="--ipset=/opt/etc/nfqws2/lists/ipset.list --ipset-exclude=/opt/etc/nfqws2/lists/ipset_exclude.list"',
                                           'NFQWS_ARGS_IPSET=""')
        self.assertNotEqual(config.read_text(), owner);config.write_text(owner)
        lists = self.opt/'etc/nfqws2/lists'
        for name in ['ipset.list', 'ipset_exclude.list']:(lists/name).unlink()
        self.run_opkg(opkg, 'remove', 'nfqws2-asus')
        self.package(real_defaults=True);self.run_opkg(opkg, 'install', '/tmp/candidate.ipk')
        self.assertEqual(config.read_text(), owner)
        for name in ['ipset.list', 'ipset_exclude.list']:self.assertFalse((lists/name).exists(), name)


@unittest.skipUnless(BUSYBOX.exists(), 'a real BusyBox required')
class DefaultPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name);self.opt = self.root/'opt'
        self.config = self.opt/'etc/nfqws2/nfqws2.conf'
        lists = self.config.parent/'lists';lists.mkdir(parents=True)
        self.template = self.config.with_name(self.config.name+'.notactive')
        self.template.write_text('NFQWS_EXTRA_ARGS="--hostlist='+str(lists/'user.list')+'"\n')
        self.template.chmod(0o600)
        self.user_template = lists/'user.list.notactive';self.user_template.write_bytes(b'full factory list\n')
        self.user = lists/'user.list'
        state = self.opt/'etc/nfqws2-asus-migration';state.mkdir(mode=0o700)
        (state/'defaults-initialized').write_text('previous install\n')

    def call(self, fail_source):
        migration = (ROOT/'asus/ipk/migration.sh').read_text().replace('/opt/', str(self.opt)+'/').replace(
            'ASUS_MIGRATION_OWNER=0', 'ASUS_MIGRATION_OWNER='+str(os.getuid()))
        defaults = (ROOT/'asus/ipk/defaults.sh').read_text().replace('/opt/', str(self.opt)+'/')
        script = migration+'\n'+defaults+'\nASUS_MIGRATION_BUSYBOX='+shlex.quote(str(BUSYBOX))+'\n'
        script += 'fault_source='+shlex.quote(str(fail_source))+'\nfault_marker='+shlex.quote(str(self.root/'failed-once'))+'\n'
        script += '''asus_migration_cmd() {
            local arg last='' matches=0
            if [ "$1" = cp ] && [ ! -f "$fault_marker" ]; then
                for arg; do last=$arg; [ "$arg" != "$fault_source" ] || matches=1; done
                if [ "$matches" = 1 ]; then
                    printf 'PARTIAL' > "$last" || return 1
                    printf 'failed once\\n' > "$fault_marker"
                    return 1
                fi
            fi
            "$ASUS_MIGRATION_BUSYBOX" "$@"
        }
        asus_install_defaults
        '''
        return subprocess.run(['/bin/sh', '-c', script], capture_output=True, text=True, timeout=10)

    def exercise_partial_copy(self, source, target):
        first = self.call(source);self.assertNotEqual(first.returncode, 0, first.stdout+first.stderr)
        self.assertFalse(target.exists(), 'failed copy must not publish a partial active file')
        second = self.call(source);self.assertEqual(second.returncode, 0, second.stdout+second.stderr)
        self.assertEqual(self.config.read_bytes(), self.template.read_bytes())
        self.assertEqual(self.user.read_bytes(), self.user_template.read_bytes())
        self.assertEqual(list(self.root.rglob('.nfqws2-default.*')), [])

    def test_partial_config_copy_is_not_active_and_retry_publishes_complete_bytes(self):
        self.exercise_partial_copy(self.template, self.config)

    def test_partial_required_list_copy_is_not_active_and_retry_publishes_complete_bytes(self):
        self.exercise_partial_copy(self.user_template, self.user)


if __name__ == '__main__':unittest.main()
