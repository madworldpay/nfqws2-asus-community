"""Native defaults use real BusyBox publication without replacing owner files."""
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUSYBOX = Path('/bin/busybox')
FAKEROOT = shutil.which('fakeroot')


@unittest.skipUnless(BUSYBOX.exists() and FAKEROOT, 'BusyBox and fakeroot required')
class NativeAtomicDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base / 'root'
        self.source = self.root / 'usr/share/nfqws2/defaults'
        self.active = self.root / 'etc/nfqws2'
        self.bin = self.base / 'bin'; self.bin.mkdir()
        # fakeroot needs dynamically linked stat/chown; byte copies and link
        # publication still use the real BusyBox applets supplied by OpenWrt.
        for applet in ['cp', 'cmp', 'ln', 'find', 'mkdir', 'chmod', 'rm', 'rmdir', 'mktemp', 'sync', 'cat', 'touch', 'readlink']:
            (self.bin / applet).symlink_to(BUSYBOX)
        self.resources = {'blobs/new.bin': b'COMPLETE\x00\xffBLOB', 'lua/new.lua': b'-- complete Lua\n', 'lists/new.list': b'complete.example\n'}
        for kind in ['lists', 'lua', 'blobs']:
            (self.source / kind).mkdir(parents=True)
            (self.active / kind).mkdir(parents=True)
        for name, data in self.resources.items(): (self.source / name).write_bytes(data)
        (self.source / 'nfqws2.conf').write_bytes(b'STOCK_CONFIG\n')
        (self.source / 'lists/auto.list').write_bytes(b'')
        (self.active / 'nfqws2.conf').write_bytes(b'OWNER_CONFIG\n')
        (self.active / 'lists/auto.list').write_bytes(b'')
        self.owner = self.active / 'blobs/owner.bin'; self.owner.write_bytes(b'OWNER\x00\xff'); self.owner.chmod(0o640)
        for path in self.root.rglob('*'):
            if path.is_dir(): path.chmod(0o755)
            elif path != self.owner: path.chmod(0o644)
        self.root.chmod(0o755)

    def call(self, prefix=''):
        library = (ROOT / 'openwrt/package-lifecycle.sh').read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
        body = 'chown -R 0:0 "$IPKG_INSTROOT" || exit\n' + library + '\n' + prefix + '\nnfqws_package_defaults\n'
        return subprocess.run([FAKEROOT, '/bin/sh', '-c', body], env=os.environ | {'IPKG_INSTROOT': str(self.root), 'PATH': str(self.bin) + ':' + os.environ['PATH']}, capture_output=True, text=True, timeout=15)

    def ok(self, result): self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_owner(self, inode):
        self.assertEqual(self.owner.read_bytes(), b'OWNER\x00\xff')
        self.assertEqual(self.owner.stat().st_ino, inode)
        self.assertEqual(stat.S_IMODE(self.owner.stat().st_mode), 0o640)
        self.assertEqual((self.active / 'nfqws2.conf').read_bytes(), b'OWNER_CONFIG\n')

    def failing_copy(self, name, success=False):
        path = shlex.quote(str(self.source / name))
        return f'''cp() {{
 if [ "$1" = {path} ]; then printf PARTIAL > "$2"; return {0 if success else 1}; fi
 "$NATIVE_TEST_BUSYBOX" cp "$@"
}}
NATIVE_TEST_BUSYBOX={shlex.quote(str(BUSYBOX))}
'''

    def test_interrupted_resource_copies_publish_nothing_and_retry_complete_bytes(self):
        inode = self.owner.stat().st_ino
        for name, data in self.resources.items():
            with self.subTest(name=name):
                target = self.active / name; target.unlink(missing_ok=True)
                failed = self.call(self.failing_copy(name))
                self.assertNotEqual(failed.returncode, 0)
                self.assertFalse(target.exists(), 'An incomplete default must not have an active name')
                self.ok(self.call()); self.assertEqual(target.read_bytes(), data)
                self.assertEqual(target.stat().st_nlink, 1)
        self.assert_owner(inode)

    def test_fresh_missing_resource_directory_is_retriable_after_copy_failure(self):
        self.owner.unlink(); (self.active / 'blobs').rmdir()
        self.assertNotEqual(self.call(self.failing_copy('blobs/new.bin')).returncode, 0)
        self.assertFalse((self.active / 'blobs/new.bin').exists())
        self.ok(self.call()); self.assertEqual((self.active / 'blobs/new.bin').read_bytes(), self.resources['blobs/new.bin'])

    def test_failed_new_config_copy_is_not_published(self):
        (self.active / 'nfqws2.conf').unlink()
        self.assertNotEqual(self.call(self.failing_copy('nfqws2.conf')).returncode, 0)
        self.assertFalse((self.active / 'nfqws2.conf').exists())
        self.ok(self.call()); self.assertEqual((self.active / 'nfqws2.conf').read_bytes(), b'STOCK_CONFIG\n')

    def test_fresh_empty_offline_root_seeds_all_resources_with_safe_modes(self):
        shutil.rmtree(self.root / 'etc')
        self.ok(self.call())
        self.assertEqual((self.active / 'nfqws2.conf').read_bytes(), b'STOCK_CONFIG\n')
        self.assertEqual(stat.S_IMODE((self.active / 'nfqws2.conf').stat().st_mode), 0o600)
        for name, data in self.resources.items():
            self.assertEqual((self.active / name).read_bytes(), data)
            self.assertEqual(stat.S_IMODE((self.active / name).stat().st_mode), 0o644)

    def test_web_template_copy_failure_is_retriable_without_partial_config(self):
        service = self.root / 'usr/lib/nfqws2-web/nfqws2-native-web'; service.parent.mkdir(parents=True)
        for parent in [service.parent, service.parent.parent]: parent.chmod(0o755)
        service.write_bytes(b'fixture'); service.chmod(0o644)
        (self.source / 'web-config').write_bytes(b'COMPLETE_WEB_CONFIG\n'); (self.source / 'web-config').chmod(0o600)
        self.assertNotEqual(self.call(self.failing_copy('web-config')).returncode, 0)
        target = self.root / 'etc/config/nfqws2-web'; self.assertFalse(target.exists())
        self.ok(self.call()); self.assertEqual(target.read_bytes(), b'COMPLETE_WEB_CONFIG\n')
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_successful_but_truncated_copy_is_verified_before_publication(self):
        self.assertNotEqual(self.call(self.failing_copy('blobs/new.bin', success=True)).returncode, 0)
        self.assertFalse((self.active / 'blobs/new.bin').exists())
        self.ok(self.call())

    def test_failed_link_removes_staging_and_retry_succeeds(self):
        failed = self.call('ln() { return 1; }')
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((self.active / 'blobs/new.bin').exists())
        self.assertEqual(list(self.active.rglob('.nfqws2-seed.*')), [])
        self.ok(self.call())

    def test_owner_publication_winning_link_race_is_preserved(self):
        prefix = '''ln() {
 local target arg
 for arg; do target=$arg; done
 case "$target" in */blobs/new.bin) printf OWNER_WON > "$target";; esac
 /bin/busybox ln "$@"
}'''
        self.ok(self.call(prefix)); self.assertEqual((self.active / 'blobs/new.bin').read_bytes(), b'OWNER_WON')
        self.assertEqual(list(self.active.rglob('.nfqws2-seed.*')), [])

    def test_crash_after_link_reclaims_only_stage_and_preserves_published_inode(self):
        stage = self.active / 'blobs/.nfqws2-seed.new.bin.ABCDEF'; stage.mkdir(mode=0o700)
        partial = stage / 'file'; partial.write_bytes(b'PUBLISHED'); partial.chmod(0o644)
        target = self.active / 'blobs/new.bin'; os.link(partial, target); inode = target.stat().st_ino
        self.ok(self.call()); self.assertFalse(stage.exists())
        self.assertEqual(target.read_bytes(), b'PUBLISHED'); self.assertEqual(target.stat().st_ino, inode); self.assertEqual(target.stat().st_nlink, 1)

    def test_abandoned_copy_stage_is_reclaimed_but_foreign_links_are_rejected(self):
        stage = self.active / 'blobs/.nfqws2-seed.new.bin.ABCDEF'; stage.mkdir(mode=0o700)
        (stage / 'file').write_bytes(b'PARTIAL'); (stage / 'file').chmod(0o600)
        self.ok(self.call()); self.assertFalse(stage.exists())
        stage.mkdir(mode=0o700); outside = self.base / 'outside'; outside.write_bytes(b'PRIVATE')
        os.link(outside, stage / 'file'); outside.chmod(0o600)
        self.assertNotEqual(self.call().returncode, 0)
        self.assertEqual(outside.read_bytes(), b'PRIVATE'); self.assertTrue((stage / 'file').exists())

    def test_unsafe_source_and_parent_are_rejected_without_owner_changes(self):
        inode = self.owner.stat().st_ino; source = self.source / 'blobs/new.bin'
        original = source.read_bytes(); source.unlink(); outside = self.base / 'outside'; outside.write_bytes(b'PRIVATE')
        source.symlink_to(outside)
        self.assertNotEqual(self.call().returncode, 0); self.assertFalse((self.active / 'blobs/new.bin').exists())
        source.unlink(); source.write_bytes(original)
        self.active.chmod(0o777); self.assertNotEqual(self.call().returncode, 0)
        self.assertEqual(stat.S_IMODE(self.active.stat().st_mode), 0o777)
        self.active.chmod(0o755)
        self.assertNotEqual(self.call('chown 65534:65534 '+shlex.quote(str(source))).returncode, 0)
        self.assertFalse((self.active / 'blobs/new.bin').exists()); self.assertEqual(outside.read_bytes(), b'PRIVATE'); self.assert_owner(inode)


if __name__ == '__main__': unittest.main()
