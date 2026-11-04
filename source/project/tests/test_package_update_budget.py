"""Slow USB flushes must fit preparation without unbounding the guardian."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PUBLIC
from test_package_update_guard import NATIVE

@unittest.skipUnless(NATIVE.is_file(), 'native PHP fixture required')
class PackageUpdateBudgetTests(unittest.TestCase):
    def call(self, code, *args):
        p=subprocess.run([str(NATIVE),'-n','-r','require $argv[1]."/update-deadline.php";'+code,str(PUBLIC),*map(str,args)],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
    def test_measured_slow_usb_fits_all_durable_writes(self):
        # AI reproduction: 360 flushes at 0.85s exceed the old 240s guard.
        budget=self.call('echo json_encode(AsusUpdateApplyBudget::seconds(360,.85));')
        self.assertGreaterEqual(budget,360*.85*2+120)
        self.assertLessEqual(budget,1800)
    def test_fast_media_retains_short_budget_and_slow_media_has_hard_cap(self):
        self.assertEqual(self.call('echo json_encode([AsusUpdateApplyBudget::seconds(360,.001),AsusUpdateApplyBudget::seconds(1040,10)]);'),[240,1800])
    def test_invalid_measurements_are_refused(self):
        v=self.call('''$v=[];foreach([[-1,1],[4097,1],[1,-.1],[1,INF],[1,NAN]] as [$n,$t]){try{AsusUpdateApplyBudget::seconds($n,$t);$v[]="accepted";}catch(Throwable $e){$v[]=$e->getMessage();}}echo json_encode($v);''')
        self.assertEqual(v,['invalid_state']*5)
    def test_real_flush_probe_is_private_bounded_and_removed(self):
        with tempfile.TemporaryDirectory() as d:
            v=self.call('echo json_encode(AsusUpdateApplyBudget::measure($argv[2],360,(int)$argv[3]));',d,os.getuid())
            self.assertEqual(v['durable_files'],360);self.assertGreaterEqual(v['seconds'],240);self.assertLessEqual(v['seconds'],1800)
            self.assertGreaterEqual(v['fsync_seconds'],0);self.assertEqual(list(Path(d).iterdir()),[])
    def test_probe_refuses_a_symlink_directory(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'link';p.symlink_to(d,target_is_directory=True)
            v=self.call('try{AsusUpdateApplyBudget::measure($argv[2],360,(int)$argv[3]);echo json_encode("accepted");}catch(Throwable $e){echo json_encode($e->getMessage());}',p,os.getuid())
            self.assertEqual(v,'invalid_state')

    def test_apply_probe_claims_its_live_guardian_before_slow_io(self):
        with tempfile.TemporaryDirectory() as d:
            v=self.call('''require $argv[1]."/update-watchdog.php";require $argv[1]."/update-guard.php";
            $s=new AsusUpdateStore($argv[2]."/state",(int)$argv[3]);$j=$s->reserve(str_repeat("a",64),str_repeat("b",32),["revision"=>str_repeat("a",64),"package_version"=>"1.3.2-asus6+b87"]);$id=$j["id"];$s->update($id,["state"=>"prepared"]);$s->update($id,["state"=>"applying"]);
            $b=(new AsusUpdateWatchdog($s,(int)$argv[3]))->applyBudget($id,["pending"=>true]);
            try{$f=(new AsusUpdateGuard($s,(int)$argv[3]))->mutationLease();fclose($f);$state="unguarded";}catch(Throwable $e){$state=$e->getMessage();}
            echo json_encode(["state"=>$state,"record"=>json_decode($s->readFile("operations/".$id."/apply-budget.json"),true),"budget"=>$b,"owned"=>$s->readOperation($id)["identity"]["pid"]===getmypid()]);''',d,os.getuid())
            self.assertEqual(v['state'],'busy');self.assertTrue(v['owned']);self.assertEqual(v['record']['seconds'],v['budget'])
