"""Exercise sockets policy across stock firmware parents and strict Entware paths."""
import json
import os
import subprocess
import unittest
import test_ip_health_permissions as permissions
import test_ip_health_sockets as sockets
from test_dpi_normalize import PHP


class SocketsFirmwarePermissionTests(unittest.TestCase):
    def setUp(self):
        self.f=permissions.IpHealthFirmwarePermissionTests()
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.options={'opt':str(self.f.opt_root),'owner':os.getuid(),'run':str(self.f.core)}

    def call(self,mode):
        script='''require $argv[1].'/ip-health-sockets.php';
        try{$p=new NfqwsIpHealthSockets(json_decode($argv[2],true));
        echo json_encode(['value'=>$argv[3]==='status'?$p->status():$p->admitted()]);}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',script,str(self.f.app),json.dumps(self.options),mode],capture_output=True,text=True,timeout=3)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)

    def assert_firmware_modes_unchanged(self):
        for path in [self.f.system_tmp,self.f.system_tmp/'mnt',self.f.system_tmp/'mnt/Flashka']:
            self.assertEqual(path.stat().st_mode&0o1777,0o777)

    def test_saved_enable_and_passive_status_accept_stock_mount_parents_without_chmod(self):
        self.assertTrue(self.f.php('configure')['ok'])
        self.assertEqual(self.call('admitted'),{'value':True})
        root=self.f.opt_root/'var/lib/nfqws2-asus/ip-health-sockets'
        root.mkdir(parents=True,mode=0o700)
        for path in [self.f.opt_root/'var',self.f.opt_root/'var/lib',self.f.opt_root/'var/lib/nfqws2-asus']:
            path.chmod(0o755)
        status=root/'status.json';status.write_text('{"state":"ready","code":null}');status.chmod(0o600)
        before=status.stat()
        self.assertEqual(self.call('status'),{'value':{'state':'ready','code':None}})
        self.assertEqual(list(root.iterdir()),[status]);self.assertEqual(status.stat().st_mtime_ns,before.st_mtime_ns)
        self.assert_firmware_modes_unchanged()

    def test_default_stopped_remains_inert_and_unsafe_managed_parent_is_rejected(self):
        self.assertEqual(self.call('admitted'),{'value':False});self.assertFalse(self.f.state.exists())
        self.assertTrue(self.f.php('configure')['ok'])
        (self.f.opt_root/'etc').chmod(0o777)
        self.assertEqual(self.call('admitted'),{'error':'invalid_state'})
        self.assert_firmware_modes_unchanged()


@unittest.skipUnless(sockets.OPKG.is_file() and (sockets.FIXTURES/'php8-mod-sockets_8.2.8-1_armv7-2.6.ipk').is_file(),'verified archive and actual Entware opkg required')
class SocketsManagerParentPermissionTests(unittest.TestCase):
    def test_real_manager_policy_anchors_at_opt_above_writable_parent(self):
        f=sockets.IpHealthSocketsTests();f.setUp();self.addCleanup(f.doCleanups)
        f.base.chmod(0o777)
        before=f.foreign();job=f.prepare()
        self.assertEqual(f.call('apply',job),{'value':{'state':'ready','code':None}})
        self.assertTrue(f.installed());self.assertEqual(f.foreign(),before)
        self.assertEqual(f.base.stat().st_mode&0o777,0o777)
        (f.opt/'lib/php8').chmod(0o777)
        self.assertEqual(f.call('prepare'),{'error':'sockets_path_conflict'})


if __name__=='__main__':unittest.main()
