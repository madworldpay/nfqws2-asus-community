"""Real offline Entware opkg removal of b100-owned lists during the upgrade."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tempfile
import unittest

from test_migration import BUSYBOX, OPKG, ROOT, b


@unittest.skipUnless(OPKG.is_file() and BUSYBOX.is_file(), 'offline Entware opkg and BusyBox required')
class OwnedHostlistUpgradeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.opt = self.base / 'root/opt'
        (self.opt / 'tmp').mkdir(parents=True)
        (self.base / 'tmp').mkdir()
        config = self.base / 'opkg.conf'
        config.write_text('dest root /\narch aarch64-3.10 10\n')
        self.opkg = [str(OPKG), '-f', str(config), '-o', str(self.opt.parent), '--force-postinstall',
                     '--tmp-dir', str(self.base / 'tmp')]
        self.samples = {p.name: p.read_bytes() for p in sorted((ROOT / 'asus/zapret2-pack-lists').glob('*.list.gz'))}
        self.pins = {'lists/' + name: {'sha256': hashlib.sha256(buf).hexdigest(), 'bytes': len(buf)}
                     for name, buf in self.samples.items()}
        self.lists = self.opt / 'etc/nfqws2/lists'

    def package(self, build, pause=False):
        old = build == 100
        version = f'1.3.2-asus6+b{build}'
        baseline = {'package_version': version, 'resources': self.pins if old else {}}
        if not old:
            baseline['package_lists'] = self.pins
        prefix = 'opt/etc/nfqws2/lists/' if old else 'opt/share/nfqws2-asus/factory/lists/'
        payload = {prefix + name: (buf, 0o644) for name, buf in self.samples.items()}
        payload['opt/libexec/nfqws2-asus/busybox'] = (BUSYBOX.read_bytes(), 0o755)
        payload['opt/share/nfqws2-asus/report-baseline.json'] = (json.dumps(baseline, separators=(',', ':')).encode(), 0o644)
        control = {'control': (f'Package: nfqws2-asus\nVersion: {version}\nArchitecture: aarch64-3.10\nDescription: upgrade fixture\n'.encode(), 0o644)}
        if not old:
            hooks = [ROOT / 'asus/ipk' / f for f in ('migration.sh', 'lua-upgrade.sh', 'defaults.sh')]
            script = '#!/bin/sh\n' + '\n'.join(p.read_text() for p in hooks) + '\n'
            script = script.replace('/opt/', str(self.opt) + '/').replace('ASUS_MIGRATION_OWNER=0', 'ASUS_MIGRATION_OWNER=' + str(os.getuid()))
            control['preinst'] = ((script + 'asus_migration_save && asus_lua_upgrade_save\n').encode(), 0o755)
            marker = self.base / 'pause'
            body = 'asus_migration_restore || exit 1\n'
            if pause:
                body += f'if [ -f {shlex.quote(str(marker))} ]; then exit 17; fi\n'
            body += 'asus_b100_lists_restore || exit 1\n'
            control['postinst'] = ((script + body).encode(), 0o755)
        path = self.base / f'{build}.ipk'
        path.write_bytes(b.compressed_tar({'debian-binary': (b'2.0\n', 0o644),
            'data.tar.gz': (b.compressed_tar(payload), 0o644), 'control.tar.gz': (b.compressed_tar(control), 0o644)}))
        return path

    def invoke(self, *args, ok=True):
        result = subprocess.run([*self.opkg, *map(str, args)], capture_output=True, text=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_completed_old_snapshot_and_interrupted_new_install_preserve_live_settings(self):
        self.invoke('install', self.package(100))
        names = list(self.samples)
        changed, deleted = (self.lists / n for n in names[:2])
        changed.write_bytes(b'owner edit'); changed.chmod(0o640)
        deleted.unlink()
        (self.lists / 'user.list').write_bytes(b'owner hosts\n')
        before = {p.name: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) for p in self.lists.iterdir()}
        # A completed older migration must never replay its settings over these edits.
        old = self.opt / 'etc/nfqws2-asus-migration'
        snapshot = old / 'snapshot'
        snapshot.mkdir(mode=0o700, parents=True)
        for name in ('data-restored', 'complete'):
            (old / name).write_text('previous installation\n')
        presence = b'lists absent\nblobs absent\n'
        (snapshot / 'presence').write_bytes(presence)
        (snapshot / 'manifest').write_text(hashlib.sha256(presence).hexdigest() + '  ./presence\n')
        marker = self.base / 'pause'
        marker.touch()
        self.assertNotEqual(self.invoke('install', self.package(101, pause=True), ok=False).returncode, 0)
        self.assertFalse(changed.exists(), 'the real opkg should have removed the obsolete active file')
        marker.unlink()
        self.invoke('configure', 'nfqws2-asus')
        after = {p.name: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) for p in self.lists.iterdir()}
        self.assertEqual(after, before)
        self.assertFalse(deleted.exists())
        self.assertNotIn('/opt/etc/nfqws2/lists/z2-pack-', self.invoke('files', 'nfqws2-asus').stdout)
        self.assertEqual((snapshot / 'presence').read_bytes(), presence)
