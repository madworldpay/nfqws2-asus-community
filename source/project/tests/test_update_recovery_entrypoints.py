"""Execute both shipped root CLI entries against a sealed-worker protocol fixture."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_package_update_guard import NATIVE

PROJECT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(NATIVE.is_file() and shutil.which('unshare'), 'native PHP and root user namespace required')
class RecoveryEntrypointTests(unittest.TestCase):
    def setUp(self):
        probe=subprocess.run(['unshare','-Ur','true'],capture_output=True)
        if probe.returncode:self.skipTest('root user namespace unavailable')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.id='a'*32
        self.entries=[]
        for source in ['asus/update/worker.php','asus/install-worker.php']:
            root=self.base/('panel' if '/update/' in source else 'installer');root.mkdir()
            entry=root/'entry.php';shutil.copyfile(PROJECT/source,entry)
            app=root/'app';app.mkdir();(root/'resources').mkdir();(root/'resources/update-release-key.pem').write_text('fixture public key')
            (app/'update-worker.php').write_text('''<?php
class AsusUpdateStore {public function path($p){return '/sealed/'.$p;}public function readOperation($id){return ['runtime_digest'=>'sealed'];}public static function uptime(){return 10;}}
class AsusUpdateRuntime {public static function load($p){return ['digest'=>'sealed','argv'=>['sealed/php','-n','sealed/entry.php']];}}
class AsusUpdatePrepare {public function __construct(...$args){}public function environment(){return ['pending'=>true];}public static function code($e){return $e->getMessage();}}
class AsusGithubUpdateSource {}
class AsusUpdateDeadline {public function __construct(...$args){}}
class AsusUpdateWorker {public function __construct($s,$prepare=null){$GLOBALS['prepared']=$prepare instanceof AsusUpdatePrepare;}public function recoverBeforeInstall($id){echo json_encode(['id'=>$id,'prepare'=>$GLOBALS['prepared']]);return ['state'=>getenv('RECOVERY_RESULT')?:'restored'];}}
class AsusUpdateWatchdog {public function __construct(...$args){}public function applyBudget(...$args){return 240;}public function run(...$args){echo json_encode($args);}}
''')
            for name in ['update-watchdog.php','update-check.php','update-github.php']:(app/name).write_text('<?php')
            self.entries.append(entry)
    def call(self,entry,mode,*args,result='restored',http=False):
        env=os.environ.copy();env['RECOVERY_RESULT']=result
        if http:env['REQUEST_METHOD']='POST'
        return subprocess.run(['unshare','-Ur',str(NATIVE),'-n','-f',str(entry),'--',mode,*args],env=env,capture_output=True,text=True,timeout=5)
    def test_recovery_exit_status_and_preparation_factory(self):
        for entry in self.entries:
            for state,code in [('restored',0),('skipped',0),('failed',1)]:
                with self.subTest(entry=entry.parent.name,state=state):
                    r=self.call(entry,'restore-before-install',self.id,result=state)
                    self.assertEqual(r.returncode,code,r.stderr)
                    self.assertEqual(json.loads(r.stdout),{'id':self.id,'prepare':True})
    def test_guardian_receives_fixed_recovery_command(self):
        for entry in self.entries:
            with self.subTest(entry=entry.parent.name):
                r=self.call(entry,'guard-apply',self.id);self.assertEqual(r.returncode,0,r.stderr)
                args=json.loads(r.stdout)
                self.assertEqual(args,[self.id,['sealed/php','-n','sealed/entry.php','--','apply',self.id],250,['sealed/php','-n','sealed/entry.php','--','restore-before-install',self.id]])
    def test_recovery_rejects_malformed_id_extra_arguments_and_http(self):
        for entry in self.entries:
            for args,http in [(('a'*31,),False),((self.id,'extra'),False),((self.id,),True)]:
                with self.subTest(entry=entry.parent.name,args=args,http=http):
                    r=self.call(entry,'restore-before-install',*args,http=http)
                    self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,'')

if __name__=='__main__':unittest.main()
