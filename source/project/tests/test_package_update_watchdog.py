"""Deadline ownership must never kill a worker crossing into installation."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from test_dpi_normalize import PUBLIC
from test_package_update_guard import NATIVE


@unittest.skipUnless(NATIVE.is_file(), 'native PHP fixture required')
class PackageUpdateWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.worker = self.base / 'child.php'
        self.driver = self.base / 'driver.php'
        self.driver.write_text('''<?php
        if(!is_file($argv[1].'/update-watchdog.php')){echo json_encode(['error'=>'missing_watchdog']);exit;}
        require $argv[1].'/update-watchdog.php';
        try{$s=new AsusUpdateStore($argv[2].'/state',(int)$argv[3]);
        $j=$s->reserve(str_repeat('a',64),str_repeat('b',32),['revision'=>str_repeat('a',64),'package_version'=>'1.3.1-asus6+b11']);
        $s->update($j['id'],['state'=>'prepared']);$s->update($j['id'],['state'=>'applying']);
        file_put_contents($argv[2].'/operation',$j['id']);
        (new AsusUpdateWatchdog($s,(int)$argv[3]))->run($j['id'],[PHP_BINARY,'-n',$argv[2].'/child.php',$argv[1],$argv[2],$j['id'],$argv[3]],AsusUpdateStore::uptime()+(float)$argv[4]);
        echo json_encode($s->readOperation($j['id']));}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}''')
    def run_child(self, body, seconds=.15):
        self.worker.write_text('''<?php require $argv[1].'/update-store.php';
        $s=new AsusUpdateStore($argv[2].'/state',(int)$argv[4]);$id=$argv[3];
        file_put_contents($argv[2].'/pid',(string)getmypid());
        ''' + body)
        r=subprocess.run([str(NATIVE),'-n',str(self.driver),str(PUBLIC),str(self.base),str(os.getuid()),str(seconds)],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)
    def test_deadline_cancels_only_own_preinstall_child(self):
        unrelated=subprocess.Popen(['/bin/sleep','5']);self.addCleanup(lambda: (unrelated.terminate(),unrelated.wait()) if unrelated.poll() is None else None)
        result=self.run_child("usleep(700000);file_put_contents($argv[2].'/unexpected','installed');")
        self.assertEqual(result.get('state'),'interrupted');self.assertEqual(result.get('code'),'timed_out')
        self.assertFalse((self.base/'unexpected').exists());self.assertIsNone(unrelated.poll())
    def test_installing_boundary_is_not_killed_by_expired_deadline(self):
        result=self.run_child("$f=$s->lease('operations/'.$id.'/critical.lock');$s->writeFile('operations/'.$id.'/boundary.json',json_encode(['phase'=>'installing']));fclose($f);usleep(350000);$s->update($id,['state'=>'succeeded']);")
        self.assertEqual(result.get('state'),'succeeded')
        self.assertFalse(any((self.base/'state/operations').glob('*/cancel.json')))
    def test_boundary_lock_serializes_cancel_with_transition(self):
        result=self.run_child("$f=$s->lease('operations/'.$id.'/critical.lock');usleep(300000);$s->writeFile('operations/'.$id.'/boundary.json',json_encode(['phase'=>'installing']));fclose($f);usleep(100000);$s->update($id,['state'=>'succeeded']);")
        self.assertEqual(result.get('state'),'succeeded')
    def test_child_exit_without_completion_is_never_success(self):
        result=self.run_child('exit(0);')
        self.assertEqual(result.get('state'),'interrupted');self.assertEqual(result.get('code'),'interrupted')
    def test_completed_failure_is_preserved(self):
        result=self.run_child("$s->update($id,['state'=>'failed','code'=>'core_stop_failed']);")
        self.assertEqual(result.get('state'),'failed');self.assertEqual(result.get('code'),'core_stop_failed')
    def test_network_phase_deadline_bounds_a_stalled_lookup(self):
        result=self.run_child("$s->writeFile('operations/'.$id.'/network.json',json_encode(['deadline'=>AsusUpdateStore::uptime()+0.05]));usleep(700000);file_put_contents($argv[2].'/unexpected','finished');",seconds=2)
        self.assertEqual(result.get('code'),'timed_out');self.assertFalse((self.base/'unexpected').exists())


if __name__=='__main__':unittest.main()
