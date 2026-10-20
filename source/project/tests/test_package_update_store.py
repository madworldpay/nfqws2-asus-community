import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from test_dpi_normalize import PHP, PUBLIC
PUBLIC=Path(os.environ.get('UPDATE_STORE_TEST_PUBLIC',PUBLIC))


class PackageUpdateStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name);self.root = self.base/'state'

    def call(self, commands, owner=None):
        code = '''if(!is_file($argv[1].'/update-store.php')){echo json_encode(['error'=>'missing_store']);exit;}
        require $argv[1].'/update-store.php';try{$s=new AsusUpdateStore($argv[2],(int)$argv[3]);$out=[];$last=null;
        foreach(json_decode(stream_get_contents(STDIN),true) as $c){$a=$c[1];foreach($a as &$v)if($v==='LAST')$v=$last;unset($v);
        $v=$s->{$c[0]}(...$a);if($c[0]==='reserve')$last=$v['id'];$out[]=$v;}echo json_encode($out);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        r = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid() if owner is None else owner)],
                           input=json.dumps(commands),capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def reserve(self, n=1, revision='a'*64):
        return ['reserve',[revision,f'{n:032x}',{'revision':revision,'package_version':'1.3.1-asus6+b11'}]]

    def test_same_pair_is_idempotent_and_second_active_request_is_busy(self):
        r=self.call([self.reserve(),self.reserve()]);self.assertIsInstance(r,list)
        self.assertEqual(r[0]['id'],r[1]['id']);self.assertEqual(r[0]['state'],'preparing')
        self.assertEqual(self.call([self.reserve(2)]),{'error':'busy'})
        self.assertEqual(self.call([self.reserve(revision='b'*64)]),{'error':'request_conflict'})

    def test_worker_read_and_completion_survive_brief_status_journal_contention(self):
        job=self.call([self.reserve()])[0]['id']
        for command in [['readOperation',[job]],['update',[job,{'state':'prepared'}]]]:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                with (self.root/'control.lock').open('r+b') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX);future=pool.submit(self.call,[command]);time.sleep(.2)
                value=future.result(timeout=4)
            self.assertIsInstance(value,list,value)
    def test_retry_lock_never_repeats_a_callback_that_already_entered(self):
        code="require $argv[1].'/update-store.php';$s=new AsusUpdateStore($argv[2],(int)$argv[3]);$n=0;if(!method_exists($s,'withRetryLock')){echo 'missing';exit;}try{$s->withRetryLock(function()use(&$n){$n++;throw new RuntimeException('busy');});}catch(Throwable $e){}echo $n;"
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,'1')
    def test_reservation_is_serialized_across_processes(self):
        self.call([['status',[]]])
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results=list(pool.map(lambda n:self.call([self.reserve(n)]),range(1,6)))
        self.assertEqual(sum(isinstance(x,list) for x in results),1,results)
        self.assertEqual(sum(x=={'error':'busy'} for x in results),4,results)

    def test_atomic_state_and_artifacts_are_private_and_unknown_file_survives_rotation(self):
        first=self.call([self.reserve(),['update',['LAST',{'state':'failed','code':'download_hash'}]]])
        self.assertIsInstance(first,list)
        folder=self.root/'operations'/first[0]['id'];foreign=folder/'operator-note';foreign.write_text('KEEP')
        for n in [2,3,4]:self.call([self.reserve(n),['update',['LAST',{'state':'failed','code':'download_hash'}]]])
        status=self.call([['status',[]]])[0]
        self.assertEqual(len(status['history']),2);self.assertIsNone(status['active'])
        self.assertEqual(foreign.read_text(),'KEEP')
        self.assertEqual(self.root.stat().st_mode&0o777,0o700)
        for p in self.root.glob('*.json'):self.assertEqual(p.stat().st_mode&0o777,0o600)
        self.assertEqual(folder.stat().st_mode&0o777,0o700)

    def test_rotation_removes_only_manifest_owned_backup_files(self):
        import hashlib
        first=self.call([self.reserve()]);self.assertIsInstance(first,list);job=first[0]['id']
        backup=self.root/'operations'/job/'backup';backup.mkdir(mode=0o700)
        own=backup/'owned.conf';own.write_text('PRIVATE');own.chmod(0o600)
        unknown=backup/'operator-note';unknown.write_text('KEEP')
        manifest={'files':{'owned.conf':{'mode':0o600,'size':7,'sha256':hashlib.sha256(b'PRIVATE').hexdigest()}},'total':7}
        index=backup/'snapshot.json';index.write_text(json.dumps(manifest));index.chmod(0o600)
        self.call([['update',[job,{'state':'failed','code':'download_hash'}]]])
        for n in [2,3]:self.call([self.reserve(n),['update',['LAST',{'state':'failed','code':'download_hash'}]]])
        self.assertFalse(own.exists());self.assertEqual(unknown.read_text(),'KEEP')

    def test_symlink_and_foreign_owner_refused_without_touching_target(self):
        self.call([['status',[]]])
        outside=self.base/'outside';outside.write_text('KEEP')
        (self.root/'operations.json').unlink();(self.root/'operations.json').symlink_to(outside)
        self.assertEqual(self.call([['status',[]]]),{'error':'invalid_state'});self.assertEqual(outside.read_text(),'KEEP')
        self.assertEqual(self.call([['status',[]]],owner=os.getuid()+1),{'error':'invalid_state'})

    def test_invalid_id_and_state_transition_are_rejected(self):
        self.assertEqual(self.call([['readOperation',['../../outside']]]),{'error':'invalid_request'})
        self.assertEqual(self.call([self.reserve(),['update',['LAST',{'state':'succeeded'}]]]),{'error':'invalid_transition'})
        self.call([['update',[self.call([self.reserve()])[0]['id'],{'state':'failed','code':'download_hash'}]]])
        self.assertEqual(self.call([['update',[self.call([self.reserve()])[0]['id'],{'state':'applying'}]]]),{'error':'invalid_transition'})

    def test_boot_change_marks_active_interrupted_but_keeps_backup(self):
        result=self.call([self.reserve()]);self.assertIsInstance(result,list)
        job=result[0];self.call([['writeFile',['operations/'+job['id']+'/snapshot.json','{"PRIVATE":"BACKUP"}']]])
        status=self.call([['reconcile',['changed-boot',1]],['status',[]]])[-1]
        self.assertIsNone(status['active']);self.assertEqual(status['history'][0]['state'],'interrupted')
        self.assertIn('BACKUP',(self.root/'operations'/job['id']/'snapshot.json').read_text())

    def test_unchanged_status_poll_does_not_rewrite_flash_journal(self):
        self.assertIsInstance(self.call([self.reserve()]),list)
        journal=self.root/'operations.json';before=journal.stat()
        for _ in range(3):self.call([['reconcile',[Path('/proc/sys/kernel/random/boot_id').read_text().strip(),float(Path('/proc/uptime').read_text().split()[0])]],['status',[]]])
        self.assertEqual(journal.stat().st_ino,before.st_ino)
        self.assertEqual(journal.stat().st_mtime_ns,before.st_mtime_ns)

    def test_lock_recovers_after_killed_owner_and_does_not_unlink_foreign_lock(self):
        self.call([['status',[]]])
        code='''require $argv[1].'/update-store.php';$s=new AsusUpdateStore($argv[2],(int)$argv[3]);
        $s->withLock(function()use($argv){file_put_contents($argv[2].'/entered','1');sleep(10);});'''
        p=subprocess.Popen([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            import time
            end=time.monotonic()+2
            while not (self.root/'entered').exists() and time.monotonic()<end:time.sleep(.01)
            self.assertTrue((self.root/'entered').exists())
            self.assertEqual(self.call([self.reserve()]),{'error':'busy'})
            p.kill();p.communicate(timeout=2)
            self.assertIsInstance(self.call([self.reserve()]),list)
            self.assertTrue((self.root/'control.lock').is_file())
        finally:
            if p.poll() is None:p.kill();p.communicate()

    def test_exec_child_cannot_keep_updater_mutation_lease_alive(self):
        code='''require $argv[1].'/update-store.php';$s=new AsusUpdateStore($argv[2],(int)$argv[3]);$f=$s->lease('apply.lock');
        $p=proc_open(['/bin/sleep','1'],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes);$child=proc_get_status($p)['pid'];
        fclose($f);echo "released ".$child."\\n";flush();proc_close($p);'''
        p=subprocess.Popen([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            words=p.stdout.readline().strip().split();self.assertEqual(words[0],'released');child=int(words[1]);deadline=time.monotonic()+.7
            while time.monotonic()<deadline:
                try:
                    if Path(f'/proc/{child}/exe').resolve()==Path('/bin/sleep').resolve():break
                except FileNotFoundError:pass
                time.sleep(.005)
            else:self.fail('controlled child did not reach exec boundary')
            with (self.root/'apply.lock').open('r+') as lease:
                try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:self.fail('exec child inherited the update lease and kept mutations locked')
            out,err=p.communicate(timeout=2);self.assertEqual(p.returncode,0,err);self.assertEqual(out,'');self.assertEqual(err,'')
        finally:
            if p.poll() is None:p.kill();p.communicate()


    def test_apply_claim_is_atomic_idempotent_and_bound_to_revision(self):
        created=self.call([self.reserve(),['update',['LAST',{'state':'prepared','runtime_digest':'c'*64}]],['claimApply',['LAST','a'*64,'d'*32]],['claimApply',['LAST','a'*64,'d'*32]]])
        self.assertIsInstance(created,list);first,repeated=created[2:]
        self.assertTrue(first['launch']);self.assertFalse(repeated['launch']);self.assertEqual(first['operation']['state'],'applying')
        self.assertIn('apply_uptime',first['operation'])
        self.assertEqual(self.call([['claimApply',[first['operation']['id'],'b'*64,'d'*32]]]),{'error':'request_conflict'})
    def test_apply_claim_requires_a_prepared_execution_closure(self):
        job=self.call([self.reserve(),['update',['LAST',{'state':'prepared'}]]])[0]
        self.assertEqual(self.call([['claimApply',[job['id'],'a'*64,'d'*32]]]),{'error':'invalid_state'})
    def test_rotation_reclaims_only_indexed_files_from_a_killed_runtime_stage(self):
        import hashlib
        first=self.call([self.reserve()])[0];runtime=self.root/'operations'/first['id']/'runtime';runtime.mkdir(mode=0o700)
        partial=runtime/'php';partial.write_bytes(b'partial');partial.chmod(0o600)
        foreign=runtime/'operator-note';foreign.write_text('KEEP')
        index=runtime/'staging.json';index.write_text(json.dumps({'files':{'php':{'mode':0o700,'size':100,'sha256':hashlib.sha256(b'complete').hexdigest()}}}));index.chmod(0o600)
        self.call([['update',[first['id'],{'state':'interrupted','code':'interrupted'}]]])
        for n in [2,3]:self.call([self.reserve(n),['update',['LAST',{'state':'failed','code':'download_hash'}]]])
        self.assertFalse(partial.exists());self.assertFalse(index.exists());self.assertEqual(foreign.read_text(),'KEEP')
    def test_prepare_launch_is_claimed_once_across_repeated_requests(self):
        result=self.call([self.reserve(),['claimPrepare',['LAST']],['claimPrepare',['LAST']],['update',['LAST',{'state':'prepared'}]],['claimPrepare',['LAST']]])
        self.assertIsInstance(result,list);self.assertEqual([result[1],result[2],result[4]],[True,False,False])


if __name__=='__main__':unittest.main()
