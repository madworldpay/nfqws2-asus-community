import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PUBLIC

NATIVE=Path(os.environ.get('PHP_NATIVE_TEST_BINARY',Path.home()/'.local/state/nfqws2-asus/development/package-updates-20261016/native-php/root/usr/bin/php8.5'))


@unittest.skipUnless(NATIVE.is_file(),'native PHP fixture required for cross-process executable identity')
class PackageUpdateGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.state=self.base/'state';self.state.mkdir(mode=0o700);ops=self.state/'operations';ops.mkdir(mode=0o700)
        self.id='a'*32;self.runtime=ops/self.id/'runtime';self.runtime.mkdir(parents=True,mode=0o700);self.runtime.parent.chmod(0o700)
        self.php=self.runtime/'php';shutil.copyfile(NATIVE,self.php);self.php.chmod(0o700)
    def call(self,action,phase='starting',intent='running',own=True,extra=None,old_operation=False):
        code='''if(!is_file($argv[1].'/update-guard.php')){echo json_encode(['error'=>'missing_guard']);exit;}
        require $argv[1].'/update-guard.php';$p=json_decode(stream_get_contents(STDIN),true);
        try{$s=new AsusUpdateStore($argv[2],(int)$argv[3]);$identity=AsusUpdateLifecycle::identity(getmypid());
        if($p['old_operation']){$j=$s->reserve(str_repeat('b',64),str_repeat('c',32),['revision'=>str_repeat('b',64),'package_version'=>'1.3.1-asus6+b11']);$s->update($j['id'],['state'=>'prepared']);$s->update($j['id'],['state'=>'applying']);$db=json_decode($s->readFile('operations.json'),true);$db['operations'][$j['id']]['boot_id']='previous-boot';$db['operations'][$j['id']]['created_uptime']+=86400;$s->writeFile('operations.json',json_encode($db));}
        $ticket=['schema'=>1,'id'=>str_repeat('a',32),'boot_id'=>AsusUpdateStore::boot(),'worker'=>$identity,'installer'=>null,'phase'=>$p['phase'],'intent'=>['mode'=>$p['intent']]];
        if(!$p['own'])$ticket['worker']['start_ticks']='1';if($p['extra']){$ticket=array_replace($ticket,$p['extra']);if(isset($p['extra']['boot_id']))$ticket['worker']['boot_id']=$p['extra']['boot_id'];}
        $s->writeFile('transaction.json',json_encode($ticket));$g=new AsusUpdateGuard($s,(int)$argv[3]);
        if($p['action']==='ordinary'){$f=$g->mutationLease();fclose($f);$v='allowed';}
        else $v=$g->authorize($p['action']);echo json_encode(['value'=>$v]);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        r=subprocess.run([str(self.php),'-n','-r',code,str(PUBLIC),str(self.state),str(os.getuid())],input=json.dumps({'action':action,'phase':phase,'intent':intent,'own':own,'extra':extra,'old_operation':old_operation}),capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def test_own_worker_phase_and_intent_are_all_required_to_start(self):
        self.assertEqual(self.call('core-start'),{'value':True})
        self.assertEqual(self.call('core-start',intent='stopped'),{'value':False})
        self.assertEqual(self.call('core-start',phase='installing'),{'value':False})
        self.assertEqual(self.call('core-start',own=False),{'value':False})
    def test_worker_start_permission_does_not_authorize_unrelated_mutations(self):
        self.assertEqual(self.call('ordinary'),{'error':'busy'})
        self.assertEqual(self.call('ordinary',own=False),{'value':'allowed'})
    def test_unknown_action_boot_change_and_unknown_ticket_fields_are_refused(self):
        self.assertEqual(self.call('restart-all'),{'error':'invalid_request'})
        self.assertEqual(self.call('core-start',extra={'boot_id':'old-boot'}),{'value':False})
        self.assertEqual(self.call('core-start',extra={'bypass':True}),{'error':'invalid_state'})
    def test_worker_cannot_pretend_to_be_opkg_for_maintainer_hooks(self):
        self.assertEqual(self.call('hook-postinst',phase='installing'),{'value':False})
        self.assertEqual(self.call('hook-prerm',phase='installing'),{'value':False})

    def test_previous_boot_operation_cannot_block_startup_with_old_uptime(self):
        self.assertEqual(self.call('ordinary',own=False,old_operation=True),{'value':'allowed'})
        states=json.loads((self.state/'operations.json').read_text())['operations']
        self.assertEqual(next(iter(states.values()))['state'],'interrupted')


if __name__=='__main__':unittest.main()
