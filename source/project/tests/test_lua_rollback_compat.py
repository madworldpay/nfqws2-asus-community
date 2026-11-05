"""Real opkg rollback preserves edited Lua and its original factory bookkeeping."""
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tarfile
import unittest

import test_lua_opkg_upgrade as upgrade
from test_dpi_normalize import PHP, PUBLIC


@unittest.skipUnless(upgrade.migration.OPKG.is_file() and upgrade.migration.BUSYBOX.is_file() and Path(PHP).is_file(), 'real Entware opkg, BusyBox and PHP required')
class LuaRollbackCompatTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(os.umask, os.umask(0o022))
        self.case = upgrade.LuaOpkgUpgradeTests()
        self.case.setUp(); self.addCleanup(self.case.doCleanups)
        self.case.prepare()
        self.base = self.case.base; self.opt = self.case.opt
        self.snapshot = self.base / 'rollback'; self.settings = self.base / 'settings'
        self.status = self.opt / 'lib/opkg/status'
        self.installed = '1.3.2-asus6+b88'
        self.case.run_opkg('--force-downgrade', 'install', self.package(self.installed, self.case.new))
        self.assertEqual((self.case.lua / 'zapret-antidpi.lua').read_bytes(), self.case.edited)
        self.assertEqual(stat.S_IMODE((self.case.lua / 'zapret-antidpi.lua').stat().st_mode), 0o600)
        self.defaults = {}

    def package(self, version, scripts):
        path = self.case.package(version, scripts, True)
        with tarfile.open(path) as outer:
            parts = {m.name: (outer.extractfile(m).read(), m.mode) for m in outer if m.isfile()}
        with tarfile.open(fileobj=io.BytesIO(parts['data.tar.gz'][0])) as archive:
            payload = {m.name: (archive.extractfile(m).read(), m.mode) for m in archive if m.isfile()}
        name = 'opt/share/nfqws2-asus/report-baseline.json'
        baseline = json.loads(payload[name][0]); baseline['schema_version'] = 1
        payload[name] = (json.dumps(baseline).encode(), 0o644)
        parts['data.tar.gz'] = (upgrade.migration.b.compressed_tar(payload), 0o644)
        path.write_bytes(upgrade.migration.b.compressed_tar(parts))
        return path

    def call(self, action):
        script = r'''require $argv[1].'/update-rollback.php';
        try {
          $env=['opt'=>$argv[2],'owner'=>(int)$argv[5],'installed'=>$argv[9],'pending'=>false,'status'=>file_get_contents($argv[2].'/lib/opkg/status'),'defaults'=>json_decode($argv[8],true)];
          $result=match($argv[6]){
            'settings'=>AsusUpdateSnapshot::capture($argv[2],$argv[4],(int)$argv[5]),
            'attest'=>AsusUpdateRollback::attest($env),
            'capture'=>AsusUpdateRollback::capture($env,$argv[3],$argv[4],$argv[7]),
            'load'=>AsusUpdateRollback::load($argv[3],(int)$argv[5]),
            'finalize'=>AsusUpdateRollback::finalize($env,$argv[3],$argv[4]),
            'verify'=>AsusUpdateRollback::verifyInstalled($env,$argv[3],$argv[4])};
          echo json_encode(['value'=>$result]);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        args = [str(PUBLIC), str(self.opt), str(self.snapshot), str(self.settings), str(os.getuid())]
        command = shlex.join([PHP, '-n', '-r', script] + args + ['finalize', '', json.dumps(self.defaults), self.installed])
        result = subprocess.run([PHP, '-n', '-d', 'memory_limit=16M', '-r', script] + args + [action, '#!/bin/sh\nexec ' + command + '\n', json.dumps(self.defaults), self.installed], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def capture(self):
        self.assertIn('value', self.call('settings'))
        self.assertIn('value', self.call('attest'))
        result = self.call('capture'); self.assertIn('value', result, result)
        return result['value']

    def test_actual_rollback_restores_edited_lua_and_old_conffile_hashes(self):
        # Reverting factory seeding to edited active bytes changes opkg's stored
        # Conffiles hash, even when the final active script looks correct.
        # The operator already handled one prior opkg offer; other existing
        # sidecars remain settings and must return unchanged.
        (self.case.lua / 'zapret-antidpi.lua-opkg').unlink(missing_ok=True)
        old_sidecars = {path.name: path.read_bytes() for path in self.case.lua.glob('*.lua-opkg')}
        old_status = [line for line in self.status.read_text().split('Conffiles:', 1)[1].splitlines() if line.startswith(' ')]
        next_lua = {name: raw + b'\n-- new factory revision\n' for name, raw in self.case.new.items()}
        self.defaults = {'etc/nfqws2/lua/' + name + '-opkg': {'mode': 0o644, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in next_lua.items()}
        manifest = self.capture()
        self.assertEqual(len(manifest['conffiles']), 6)
        with tarfile.open(self.snapshot / 'archive/data.tar.gz') as archive:
            self.assertEqual(archive.extractfile('opt/etc/nfqws2/lua/zapret-antidpi.lua').read(), self.case.new['zapret-antidpi.lua'])
        self.case.run_opkg('install', self.package('1.3.2-asus6+b89', next_lua))
        self.assertEqual((self.opt / 'share/nfqws2-asus/factory/lua/zapret-lib.lua').read_bytes(), next_lua['zapret-lib.lua'])
        # Simulate an offer retained by older hooks. Current hooks consume
        # their own proven stock duplicate before the updater postflight.
        sidecar=self.case.lua/'zapret-antidpi.lua-opkg'
        sidecar.write_bytes(next_lua['zapret-antidpi.lua']);sidecar.chmod(0o644)
        self.assertEqual((self.case.lua / 'zapret-antidpi.lua-opkg').read_bytes(), next_lua['zapret-antidpi.lua'])
        # Saved factory proof must survive replacement of the live factory.
        self.assertIn('value', self.call('load'))
        result = self.case.run_opkg('--force-downgrade', '--force-reinstall', '--force-maintainer', 'install', self.snapshot / 'package.ipk')
        self.assertNotIn('error', result.stdout, result.stdout + result.stderr)
        self.assertIn('"restored":true', result.stdout)
        self.assertIn('value', self.call('verify'))
        self.assertEqual((self.case.lua / 'zapret-antidpi.lua').read_bytes(), self.case.edited)
        self.assertEqual(stat.S_IMODE((self.case.lua / 'zapret-antidpi.lua').stat().st_mode), 0o600)
        self.assertEqual((self.case.lua / 'custom.lua').read_bytes(), b'-- owner custom Lua\n')
        self.assertEqual([line for line in self.status.read_text().split('Conffiles:', 1)[1].splitlines() if line.startswith(' ')], old_status)
        self.assertEqual({path.name: path.read_bytes() for path in self.case.lua.glob('*.lua-opkg')}, old_sidecars)
        self.assertTrue(any(path.is_file() and path.read_bytes() == next_lua['zapret-antidpi.lua'] for path in (self.snapshot / 'quarantine').rglob('*')))

    def test_mismatched_factory_hash_refuses_before_snapshot(self):
        self.assertIn('value', self.call('attest'))
        factory = self.opt / 'share/nfqws2-asus/factory/lua/zapret-antidpi.lua'
        factory.write_bytes(self.case.edited)
        self.assertEqual(self.call('attest'), {'error': 'rollback_unavailable'})
        self.assertFalse(self.snapshot.exists())

    def test_factory_links_and_writable_parents_refuse_without_touching_owner_lua(self):
        self.assertIn('value', self.call('attest'))
        factory = self.opt / 'share/nfqws2-asus/factory/lua/zapret-antidpi.lua'
        raw = factory.read_bytes(); outside = self.base / 'outside-lua'; outside.write_bytes(raw); outside.chmod(0o644)
        for kind in ['symlink', 'hardlink', 'writable-parent']:
            with self.subTest(kind=kind):
                if kind == 'writable-parent': factory.parent.chmod(0o777)
                else:
                    factory.unlink()
                    if kind == 'symlink': factory.symlink_to(outside)
                    else: os.link(outside, factory)
                self.assertIn(self.call('attest').get('error'), ['rollback_unavailable', 'invalid_state'])
                self.assertEqual((self.case.lua / 'zapret-antidpi.lua').read_bytes(), self.case.edited)
                self.assertEqual(outside.read_bytes(), raw)
                if kind == 'writable-parent': factory.parent.chmod(0o755)
                else: factory.unlink(); factory.write_bytes(raw); factory.chmod(0o644)

    def test_factory_requires_package_ownership_and_excludes_foreign_claims(self):
        self.assertIn('value', self.call('attest'))
        info = self.opt / 'lib/opkg/info'; own = info / 'nfqws2-asus.list'; original = own.read_text()
        factory = 'share/nfqws2-asus/factory/lua/zapret-antidpi.lua'
        own.write_text('\n'.join(line for line in original.splitlines() if not line.rstrip('/').endswith('/' + factory)) + '\n')
        self.assertEqual(self.call('attest'), {'error': 'rollback_unavailable'})
        own.write_text(original)
        foreign = info / 'foreign.list'; foreign.write_text('/opt/' + factory + '\n'); foreign.chmod(0o644)
        self.assertEqual(self.call('attest'), {'error': 'rollback_unavailable'})
        foreign.write_text('/opt/etc/nfqws2/lua/zapret-antidpi.lua\n')
        self.assertEqual(self.call('attest'), {'error': 'rollback_unavailable'})

    def test_retained_lua_omitted_by_opkg_requires_factory_and_no_foreign_claim(self):
        own = self.opt / 'lib/opkg/info/nfqws2-asus.list'
        active = 'etc/nfqws2/lua/zapret-antidpi.lua'
        own.write_text('\n'.join(line for line in own.read_text().splitlines() if not line.rstrip('/').endswith('/' + active)) + '\n')
        self.assertIn('value', self.call('attest'))
        foreign = own.with_name('foreign.list'); foreign.write_text('/opt/' + active + '\n'); foreign.chmod(0o644)
        self.assertEqual(self.call('attest'), {'error': 'rollback_unavailable'})

    def test_changed_lua_sidecar_is_preserved_and_rollback_refuses(self):
        sidecar = self.case.lua / 'zapret-antidpi.lua-opkg'; sidecar.unlink(missing_ok=True)
        raw = b'-- candidate factory offer\n'
        self.defaults = {'etc/nfqws2/lua/zapret-antidpi.lua-opkg': {'mode': 0o644, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}
        self.capture()
        sidecar.write_bytes(b'-- owner changed this offer\n'); sidecar.chmod(0o644)
        self.assertEqual(self.call('finalize'), {'error': 'rollback_failed'})
        self.assertEqual(sidecar.read_bytes(), b'-- owner changed this offer\n')
        self.assertFalse((self.snapshot / 'quarantine').exists())

    def test_saved_factory_hash_is_bound_to_old_opkg_conffile_hash(self):
        self.capture()
        name = 'share/nfqws2-asus/factory/lua/zapret-antidpi.lua'
        path = self.snapshot / 'payload' / name; raw = b'-- replacement factory\n'; path.write_bytes(raw)
        manifest = json.loads((self.snapshot / 'snapshot.json').read_text())
        manifest['payload'][name].update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        (self.snapshot / 'snapshot.json').write_text(json.dumps(manifest))
        self.assertEqual(self.call('load'), {'error': 'rollback_failed'})


if __name__ == '__main__': unittest.main()
