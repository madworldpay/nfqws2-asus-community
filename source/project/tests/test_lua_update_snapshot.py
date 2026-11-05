"""A real opkg Lua upgrade must pass postflight without losing owner edits."""
import json
import os
import subprocess
import unittest
from test_lua_opkg_upgrade import LuaOpkgUpgradeTests, PHP
from test_dpi_normalize import PUBLIC


class LuaSnapshotIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.case = LuaOpkgUpgradeTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.prepare()
        self.backup = self.case.base / 'snapshot'

    def baseline_schema(self):
        path = self.case.opt / 'share/nfqws2-asus/report-baseline.json'
        value = json.loads(path.read_text()); value['schema_version'] = 1
        path.write_text(json.dumps(value))

    def call(self, action):
        code = '''require $argv[1].'/update-prepare.php';try{
        $v=$argv[5]==='capture'?AsusUpdateSnapshot::capture($argv[2],$argv[3],(int)$argv[4]):AsusUpdateSnapshot::verify($argv[2],$argv[3],(int)$argv[4],true);
        echo json_encode(['ok'=>true]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p = subprocess.run([str(PHP), '-n', '-r', code, str(PUBLIC), str(self.case.opt), str(self.backup), str(os.getuid()), action], capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, '')
        return json.loads(p.stdout)

    def test_real_upgrade_accepts_only_factory_matching_new_lua_sidecars(self):
        self.baseline_schema(); self.assertEqual(self.call('capture'), {'ok': True})
        self.case.run_opkg('install', self.case.package('1.3.2+b88', self.case.new, True))
        self.baseline_schema()
        self.assertEqual((self.case.lua / 'zapret-antidpi.lua').read_bytes(), self.case.edited)
        # Earlier maintainer hooks can leave this signed factory alternative.
        # New hooks remove their own copies, but postflight must still accept
        # an exact factory copy and detect a later operator edit to it.
        alternative=self.case.lua/'zapret-obfs.lua-opkg'
        if not alternative.exists():
            alternative.write_bytes(self.case.new['zapret-obfs.lua']);alternative.chmod(0o644)
        sidecars = list(self.case.lua.glob('*.lua-opkg'))
        self.assertTrue(sidecars)
        for path in sidecars:
            self.assertEqual(path.read_bytes(), self.case.new[path.name.removesuffix('-opkg')])
        self.assertEqual(self.call('verify'), {'ok': True})
        sidecars[0].write_bytes(b'OWNER SIDECAR EDIT')
        self.assertEqual(self.call('verify'), {'error': 'settings_changed'})
