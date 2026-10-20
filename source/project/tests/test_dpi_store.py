import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from test_dpi_normalize import PHP, PUBLIC

BOOT=Path('/proc/sys/kernel/random/boot_id').read_text().strip()


class DpiStoreTests(unittest.TestCase):
    def test_private_options_are_outside_index_and_preferences_remove_proxy(self):
        request=self.reserve();request[1][2]['options']={'proxy':'socks5://user:SECRET@localhost:1080'}
        r=self.call([request,['readOptions',['LAST']],['writePreferences',[{'proxy':'socks5://user:SECRET@localhost:1080'}]],['readPreferences',[]]])
        self.assertIsInstance(r,list);self.assertIn('SECRET',r[1]['proxy']);self.assertNotIn('SECRET',json.dumps(r[-1]))
        self.assertNotIn('SECRET',(self.root/'jobs.json').read_text())
        job=r[0]['id'];self.call([['update',[job,{'state':'failed','finished_at':int(time.time())}]],['deleteResult',[job]]])
        self.assertFalse((self.root/(job+'.options.json')).exists())

    def test_local_native_payload_has_independent_limit_and_delete(self):
        r=self.call([self.reserve(),['update',['LAST',{'state':'running'}]],['update',['LAST',{'native':'{"type":"nfqws2_dpi_native","padding":"'+'x'*300000+'"}','state':'partial'}]],['readNative',['LAST']]])
        self.assertIsInstance(r,list);self.assertGreater(len(r[-1]),262144)
        self.call([['deleteResult',[r[0]['id']]]]);self.assertFalse((self.root/(r[0]['id']+'.native.json')).exists())
    def test_trusted_entware_opt_alias_is_resolved_before_protected_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);real=base/'mounted-entware';real.mkdir();alias=base/'opt';alias.symlink_to(real,target_is_directory=True)
            code='''require $argv[1].'/dpi-store.php';$p=AsusDpiStore::optPath('/state',$argv[2]);$s=new AsusDpiStore($p,(int)$argv[3]);echo json_encode([$p,$s->status()]);'''
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(alias),str(os.getuid())],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr);path,status=json.loads(p.stdout)
            self.assertEqual(path,str(real/'state'));self.assertEqual(status,{'active':None,'history':[]})

    def test_new_shared_parent_is_traversable_while_state_stays_private(self):
        root=self.base/'shared'/'product'/'state'
        result=self.call([['status',[]]],root=root)
        self.assertIsInstance(result,list)
        self.assertEqual(root.stat().st_mode&0o777,0o700)
        self.assertEqual((self.base/'shared').stat().st_mode&0o777,0o755)
        self.assertEqual((self.base/'shared/product').stat().st_mode&0o777,0o755)
        self.assertEqual(self.base.stat().st_mode&0o777,0o700)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.root=self.base/'state'
    def tearDown(self):self.tmp.cleanup()
    def call(self,commands,root=None,owner=None):
        code='''require $argv[1].'/dpi-store.php';try{$s=new AsusDpiStore($argv[2],(int)$argv[3]);
        $out=[];$last=null;foreach(json_decode(stream_get_contents(STDIN),true) as $c){
        $args=$c[1];foreach($args as &$a)if($a==='LAST')$a=$last;unset($a);
        $v=$s->{$c[0]}(...$args);if($c[0]==='reserve')$last=$v['id'];$out[]=$v;}echo json_encode($out);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root or self.root),str(os.getuid() if owner is None else owner)],input=json.dumps(commands),text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
    def reserve(self,n=1):return ['reserve',[f'{n:08x}-1111-4111-8111-111111111111','run',{'tests':[1,2]}]]

    def test_same_request_is_idempotent_and_other_request_busy(self):
        result=self.call([self.reserve(),self.reserve()])
        self.assertIsInstance(result,list);self.assertEqual(result[0]['id'],result[1]['id'])
        self.assertEqual(self.call([self.reserve(2)]),{'error':'busy'})
        changed=self.reserve();changed[1][2]['tests']=[3]
        self.assertEqual(self.call([changed]),{'error':'request_conflict'})

    def test_concurrent_reserve_is_single_job(self):
        self.call([['status',[]]])
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda n:self.call([self.reserve(n)]),range(1,7)))
        self.assertEqual(sum(isinstance(r,list) for r in results),1)
        self.assertEqual(sum(r=={'error':'busy'} for r in results),5)

    def test_staging_reconciliation_is_serialized_with_new_install_reservation(self):
        self.call([['status',[]]])
        code='''require $argv[1].'/dpi-store.php';$s=new AsusDpiStore($argv[2],(int)$argv[3]);$s->cleanupArtifacts(function($active)use($argv){file_put_contents($argv[2].'/entered','1');usleep(350000);});'''
        p=subprocess.Popen([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            end=time.monotonic()+2
            while not (self.root/'entered').exists() and p.poll() is None and time.monotonic()<end:time.sleep(0.005)
            self.assertTrue((self.root/'entered').exists())
            start=time.monotonic();job=self.call([self.reserve()])[0]
            self.assertGreater(time.monotonic()-start,0.2,'new installer raced artifact reconciliation')
            out,err=p.communicate(timeout=3);self.assertEqual(p.returncode,0,err);self.assertEqual(out,'')
        finally:
            if p.poll() is None:p.kill();p.communicate()

    def test_boot_change_and_clock_rollback_do_not_extend_lifetime(self):
        self.call([self.reserve(),['update',['LAST',{'state':'running'}]]])
        status=self.call([['reconcile',[float(Path('/proc/uptime').read_text().split()[0]),int(time.time()),'changed-boot']],['status',[]]])[-1]
        self.assertIsNone(status['active']);self.assertEqual(status['history'][0]['state'],'interrupted')
        self.call([['reconcile',[0,1,BOOT]]])
        self.assertEqual(self.call([['status',[]]])[-1]['history'],[])

    def test_terminal_cannot_return_to_running_and_retention_keeps_three(self):
        first=self.call([self.reserve(),['update',['LAST',{'state':'running'}]],['update',['LAST',{'state':'failed','finished_at':int(time.time())}]]])[0]['id']
        self.assertEqual(self.call([['update',[first,{'state':'running'}]]]),{'error':'invalid_transition'})
        for i in range(2,6):self.call([self.reserve(i),['update',['LAST',{'state':'failed','finished_at':int(time.time())}]]])
        self.assertEqual(len(self.call([['status',[]]])[-1]['history']),3)

    def test_symlink_fifo_foreign_owner_and_partial_json_are_rejected(self):
        real=self.base/'real';real.mkdir();self.root.symlink_to(real,target_is_directory=True)
        self.assertEqual(self.call([['status',[]]]),{'error':'invalid_state'})
        self.root.unlink();self.root.mkdir(mode=0o700)
        os.mkfifo(self.root/'control.lock',0o600)
        self.assertEqual(self.call([['status',[]]]),{'error':'invalid_state'})
        (self.root/'control.lock').unlink()
        self.assertEqual(self.call([['status',[]]],owner=os.getuid()+1),{'error':'invalid_state'})
        (self.root/'jobs.json').write_text('{');(self.root/'jobs.json').chmod(0o600)
        self.assertEqual(self.call([['status',[]]]),{'error':'invalid_state'})

    def test_interrupted_atomic_write_is_pruned_under_store_lock(self):
        self.call([['status',[]]])
        orphan=self.root/('.write-'+'a'*24);orphan.write_text('private partial payload');orphan.chmod(0o600)
        canary=self.root/'.write-unmanaged';canary.write_text('keep')
        self.call([['status',[]]])
        self.assertFalse(orphan.exists());self.assertEqual(canary.read_text(),'keep')

    def test_cleanup_does_not_delete_unmanaged_files(self):
        self.call([self.reserve(),['update',['LAST',{'state':'failed','finished_at':int(time.time())}]]])
        canary=self.root/'unmanaged';canary.write_text('keep')
        self.call([['reconcile',[0,int(time.time())+86401,BOOT]]])
        self.assertEqual(canary.read_text(),'keep')
        self.assertEqual(self.call([['status',[]]])[-1]['history'],[])

    def test_old_active_job_cannot_be_reissued_as_a_fresh_attachment(self):
        self.call([self.reserve(),['update',['LAST',{'state':'running','groups':[{'group':2,'rows':[]}]}]]])
        db=json.loads((self.root/'jobs.json').read_text());job=next(iter(db['jobs'].values()))
        job['started_at']-=172800;job['started_uptime']-=172800
        (self.root/'jobs.json').write_text(json.dumps(db))
        code='''require $argv[1].'/dpi-jobs.php';$s=new AsusDpiStore($argv[2],(int)$argv[3]);echo json_encode((new AsusDpiJobs($s))->status());'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);status=json.loads(p.stdout)
        self.assertIsNone(status['active']);self.assertEqual(status['history'],[])
        self.assertEqual(list(self.root.glob('*.result.json')),[])
        self.assertEqual(json.loads((self.root/'jobs.json').read_text())['jobs'],[])

    def test_delete_erases_retained_group_payload_and_attachment_eligibility(self):
        job=self.call([self.reserve(),['update',['LAST',{'state':'running','groups':[{'group':2,'rows':[{'target':'PRIVATE_CANARY'}]}]}]],['update',['LAST',{'state':'partial','finished_at':int(time.time())}]]])[0]
        self.call([['deleteResult',[job['id']]]])
        stored=json.loads((self.root/'jobs.json').read_text())
        self.assertNotIn('PRIVATE_CANARY',json.dumps(stored));self.assertEqual(stored['jobs'][job['id']]['groups'],[])

    def test_terminal_uptime_prevents_extension_by_wall_rollback(self):
        job=self.call([self.reserve(),['update',['LAST',{'state':'failed','finished_at':int(time.time())}]]])[0]
        db=json.loads((self.root/'jobs.json').read_text());row=db['jobs'][job['id']]
        row['started_at']-=172800;row['finished_at']-=3600
        row['started_uptime']-=172800;row['finished_uptime']=float(Path('/proc/uptime').read_text().split()[0])-86401
        (self.root/'jobs.json').write_text(json.dumps(db))
        self.assertEqual(self.call([['status',[]]])[-1]['history'],[])
