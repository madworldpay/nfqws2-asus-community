"""Real Entware opkg: edited Lua survives while unchanged official Lua advances."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tarfile
import tempfile
import unittest
import test_migration as migration

ROOT = migration.ROOT
PHP = Path(os.environ.get('PHP_TEST_BINARY', '/usr/bin/php'))
NAMES = ['zapret-lib.lua', 'zapret-antidpi.lua', 'zapret-auto.lua', 'zapret-obfs.lua', 'zapret-pcap.lua', 'zapret-tests.lua']


def official(archive):
    with tarfile.open(ROOT.parent / 'sources' / archive) as source:
        return {name: source.extractfile(next(m for m in source.getmembers() if m.isfile() and m.name.endswith('/lua/' + name))).read() for name in NAMES}


@unittest.skipUnless(migration.OPKG.exists() and migration.BUSYBOX.exists() and PHP.exists(), 'real Entware opkg, BusyBox and PHP required')
class LuaOpkgUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base / 'root'; self.opt = self.root / 'opt'
        (self.opt / 'tmp').mkdir(parents=True); (self.base / 'tmp').mkdir()
        config = self.base / 'opkg.conf'; config.write_text('dest root /\narch aarch64-3.10 10\n')
        self.command = [str(migration.OPKG), '-f', str(config), '-o', str(self.root), '--force-postinstall', '--tmp-dir', str(self.base / 'tmp')]
        self.old = official('zapret2-221d7dff.tar.gz'); self.new = official('zapret2-038c97e5.tar.gz')

    def run_opkg(self, *args, ok=True):
        result = subprocess.run(self.command + list(map(str, args)), capture_output=True, text=True, timeout=20)
        if ok: self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def package(self, version, scripts, upgrade=False):
        payload = {'opt/etc/nfqws2/lua/' + name: (raw, 0o644) for name, raw in scripts.items()}
        baseline = {'resources': {'lua/' + name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in scripts.items()}}
        payload['opt/share/nfqws2-asus/report-baseline.json'] = (json.dumps(baseline).encode(), 0o644)
        payload['opt/libexec/nfqws2-asus/busybox'] = (migration.BUSYBOX.read_bytes(), 0o755)
        controls = {'control': (f'Package: nfqws2-asus\nVersion: {version}\nArchitecture: aarch64-3.10\nDescription: Lua ownership transition\n'.encode(), 0o644)}
        for action in ['preinst', 'postinst', 'prerm', 'postrm']: controls[action] = (b'#!/bin/sh\nexit 0\n', 0o755)
        if upgrade:
            helper = getattr(migration.b, 'add_lua_factory_resources', None)
            conffiles = helper(payload) if helper else '/opt/etc/nfqws2/lua/local-tls13-stun.lua\n'
            controls['conffiles'] = (conffiles.encode(), 0o644)
            hook = ROOT / 'asus/ipk/lua-upgrade.sh'
            if hook.exists():
                migration_code = (ROOT / 'asus/ipk/migration.sh').read_text()
                hook_code = hook.read_text()
                code = (migration_code + '\n' + hook_code).replace('/opt/', str(self.opt) + '/').replace('ASUS_MIGRATION_OWNER=0', 'ASUS_MIGRATION_OWNER=' + str(os.getuid()))
                controls['preinst'] = (('#!/bin/sh\n' + code + '\nasus_lua_upgrade_save || exit $?\n').encode(), 0o755)
                php = (ROOT / 'asus/lua-upgrade.php').read_text().replace('/opt/', str(self.opt) + '/').replace('0\\s+0\\s+0\\s+0', '\\s+'.join([str(os.getuid())]*4)).replace("'/opt/etc/nfqws2'", repr(str(self.opt / 'etc/nfqws2')))
                php = php.replace("'/opt/share/nfqws2-asus/defaults'", repr(str(self.opt / 'share/nfqws2-asus/defaults')))
                # The fixture runs as the current user; production requires root.
                php = php.replace(",0);", ',' + str(os.getuid()) + ');')
                php = php.replace(",0,'/opt'", ',' + str(os.getuid()) + ',' + repr(str(self.opt)))
                payload['opt/lib/nfqws2-asus/lua-upgrade.php'] = (php.encode(), 0o644)
                for name in ['openwrt-resource-upgrade.php', 'support-json-schema.php', 'platform.php']:
                    payload['opt/share/nfqws-asus-web/' + name] = ((ROOT / 'webui/web/public' / name).read_bytes(), 0o644)
                command = [str(PHP), '-n', '-d', 'register_argc_argv=1', '-q', '-f', str(self.opt / 'lib/nfqws2-asus/lua-upgrade.php'), '--']
                controls['postinst'] = (('#!/bin/sh\n' + shlex.join(command) + '\n').encode(), 0o755)
        path = self.base / (version + '.ipk')
        path.write_bytes(migration.b.compressed_tar({'debian-binary': (b'2.0\n', 0o644), 'control.tar.gz': (migration.b.compressed_tar(controls), 0o644), 'data.tar.gz': (migration.b.compressed_tar(payload), 0o644)}))
        return path

    def prepare(self):
        self.run_opkg('install', self.package('1.3.2+b87', self.old))
        self.lua = self.opt / 'etc/nfqws2/lua'
        self.edited = self.old['zapret-antidpi.lua'] + b'\n-- Owner edit retained across engine upgrades\n'
        (self.lua / 'zapret-antidpi.lua').write_bytes(self.edited); (self.lua / 'zapret-antidpi.lua').chmod(0o600)
        (self.lua / 'custom.lua').write_bytes(b'-- owner custom Lua\n')

    def test_real_106_to_107_upgrade_preserves_edits_and_advances_unchanged_lua(self):
        self.prepare(); self.run_opkg('install', self.package('1.3.2+b88', self.new, True))
        self.assertEqual((self.lua / 'zapret-antidpi.lua').read_bytes(), self.edited)
        self.assertEqual(stat.S_IMODE((self.lua / 'zapret-antidpi.lua').stat().st_mode), 0o600)
        for name in NAMES:
            if name != 'zapret-antidpi.lua': self.assertEqual((self.lua / name).read_bytes(), self.new[name], name)
        self.assertEqual((self.lua / 'custom.lua').read_bytes(), b'-- owner custom Lua\n')
        self.assertFalse((self.opt / 'var/lib/nfqws2-asus/lua-upgrade/previous-baseline.json').exists())

    def test_later_upgrade_uses_the_new_baseline_and_preserves_new_owner_edits(self):
        self.prepare(); self.run_opkg('install', self.package('1.3.2+b88', self.new, True))
        custom = self.new['zapret-auto.lua'] + b'\n-- later owner edit\n'; (self.lua / 'zapret-auto.lua').write_bytes(custom)
        next_lua = {name: raw + b'\n-- fixture-only subsequent factory revision\n' for name, raw in self.new.items()}
        self.run_opkg('install', self.package('1.3.2+b89', next_lua, True))
        self.assertEqual((self.lua / 'zapret-antidpi.lua').read_bytes(), self.edited)
        self.assertEqual((self.lua / 'zapret-auto.lua').read_bytes(), custom)
        self.assertEqual((self.lua / 'zapret-lib.lua').read_bytes(), next_lua['zapret-lib.lua'])

    def test_missing_previous_baseline_preserves_unclassified_existing_lua(self):
        self.prepare(); (self.opt / 'share/nfqws2-asus/report-baseline.json').unlink()
        self.run_opkg('install', self.package('1.3.2+b88', self.new, True))
        self.assertEqual((self.lua / 'zapret-antidpi.lua').read_bytes(), self.edited)
        self.assertEqual((self.lua / 'zapret-lib.lua').read_bytes(), self.old['zapret-lib.lua'])

    def test_entware_opt_alias_preserves_edits_and_updates_factory_bytes(self):
        destination = self.root / 'entware'; self.opt.rename(destination); self.opt.symlink_to('entware', target_is_directory=True)
        self.prepare(); self.run_opkg('install', self.package('1.3.2+b88', self.new, True))
        self.assertEqual((self.lua / 'zapret-antidpi.lua').read_bytes(), self.edited)
        self.assertEqual((self.lua / 'zapret-obfs.lua').read_bytes(), self.new['zapret-obfs.lua'])

    def test_interrupted_baseline_copy_retries_without_touching_owner_lua(self):
        self.prepare(); state = self.opt / 'var/lib/nfqws2-asus/lua-upgrade'; state.mkdir(parents=True, mode=0o700)
        for path in [self.opt / 'var', self.opt / 'var/lib', self.opt / 'var/lib/nfqws2-asus']: path.chmod(0o755)
        stage = state / 'previous-baseline.new'; stage.write_bytes(b'INTERRUPTED'); stage.chmod(0o644)
        self.run_opkg('install', self.package('1.3.2+b88', self.new, True))
        self.assertFalse(stage.exists()); self.assertEqual((self.lua / 'zapret-antidpi.lua').read_bytes(), self.edited)
        self.assertEqual((self.lua / 'zapret-obfs.lua').read_bytes(), self.new['zapret-obfs.lua'])


if __name__ == '__main__': unittest.main()
