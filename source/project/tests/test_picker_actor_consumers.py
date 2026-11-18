"""Keep unknown live actor context separate from a verified exited process."""
import json,os,subprocess,sys,time,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
import test_picker_actor_context as actor_fixture


class PickerActorConsumerTests(unittest.TestCase):
    def setUp(self):
        actor_fixture.PickerActorContextTests.setUp(self);self.sequence=0

    def call(self,mode,pid=0,proof=None):
        self.sequence+=1;capture=self.root/('call-%02d'%self.sequence);capture.mkdir(mode=0o700)
        code=r'''require $argv[1].'/strategy-picker-runtime.php';$r=$argv[2];$d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$mode=$d['mode'];$u=(int)$argv[3];$out=[];
        if($mode==='external'){$out['runtime']=NfqwsStrategyPickerRuntime::identity($d['pid']);$out['admission']=NfqwsStrategyPickerAdmission::identity($d['pid']);echo json_encode($out,JSON_THROW_ON_ERROR);return;}
        $pin=static function($p){clearstatcache(true,$p);return array_intersect_key(lstat($p),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));};
        $record=static function($p)use($pin){return ['pin'=>$pin($p),'raw_base64'=>base64_encode(file_get_contents($p))];};
        $cf=$r.'/nfqws2.conf';file_put_contents($cf,"LOCAL_ORIGINAL_CONFIG\n");chmod($cf,0664);$s=new NfqwsStrategyPickerState($r.'/picker',$u);$lock=$s->lock();$c=new NfqwsStrategyPickerConfig($s,$cf,$u);$j=$c->snapshot(false);$rt=new NfqwsStrategyPickerRuntime($s,$c);$a=$d['proof']??NfqwsStrategyPickerRuntime::identity(getmypid());$out['actual_identity']=$a;$boot=false;$name='actor-work.json';
        if(str_starts_with($mode,'custom_')){
            $boot=true;$j['boot']=$j['boot']==='00000000-0000-0000-0000-000000000000'?'11111111-1111-1111-1111-111111111111':'00000000-0000-0000-0000-000000000000';$a['boot']=$j['boot'];$j['custom_sample_pending']=[];
            if($mode==='custom_previous_legacy')$a=array_intersect_key($a,array_flip(['pid','ticks','boot','argv']));
            if($mode==='custom_bad_uid')$a['uid']=$u+1;
            if($mode==='custom_bad_cwd')$a['cwd']='relative/not-authority';
            if($mode==='custom_extra')$a['caller_owned']=true;
            if($mode==='custom_partial')unset($a['cwd']);
            if($mode==='custom_current_legacy'){
                $boot=false;$j['boot']=AsusUpdateStore::boot();$a['boot']=$j['boot'];$a=array_intersect_key($a,array_flip(['pid','ticks','boot','argv']));$nonce=str_repeat('b',32);$j['deadline']=AsusUpdateStore::uptime()+10;$j['custom_worker']=['stage'=>'prepare','nonce'=>$nonce,'payload_sha256'=>str_repeat('c',64),'deadline'=>$j['deadline']];$a['argv']=[__DIR__.'/unused', $argv[1].'/strategy-picker-custom-worker.php','--','prepare',$j['id'],$nonce];
            }
            $j['actuator']=$a;$s->write($j);$method=new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'customReap');$args=[$boot];
        }else{
            if($mode==='actor_legacy')$a=array_intersect_key($a,array_flip(['pid','ticks','boot','argv']));
            if($mode==='actor_uid')$a['uid']=$u+1;
            if($mode==='actor_ticks')$a['ticks']=(string)((int)$a['ticks']+1);
            if($mode!=='actor_missing')$s->write(['id'=>$mode==='actor_other_job'?str_repeat('f',32):$j['id'],'identity'=>$a],$name);
            if($mode==='actor_cwd'){mkdir($r.'/changed-cwd',0700);if(!chdir($r.'/changed-cwd'))throw new RuntimeException('fixture_chdir_failed');}
            $method=new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'actor');$args=['work',$j['id']];
        }
        $out['journal_before']=$record($s->path('state.json'));$out['config_before']=$record($cf);$out['actor_before']=file_exists($s->path($name))?$record($s->path($name)):null;
        try{$out['result']=$method->invokeArgs($rt,$args);$out['success']=true;}catch(Throwable $e){$out['error']=$e->getMessage();}
        $out['journal_after']=$record($s->path('state.json'));$out['config_after']=$record($cf);$out['actor_after']=file_exists($s->path($name))?$record($s->path($name)):null;$out['cwd_after']=getcwd();
        flock($lock,LOCK_UN);fclose($lock);$l=fopen($r.'/picker/engine.lock','rb');$out['lock_free_after']=flock($l,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($l,LOCK_UN);fclose($l);echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request=json.dumps({'mode':mode,'pid':pid,'proof':proof}).encode()
        (capture/'php-r.private').write_text(code);(capture/'request.private.json').write_bytes(request)
        for name in ['strategy-picker-runtime.php','strategy-picker-custom-runtime.php','strategy-picker-core.php','strategy-picker-admission.php']:(capture/(name+'.actual.private')).write_bytes((PUBLIC/name).read_bytes())
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(capture),str(os.getuid())],input=request,capture_output=True,cwd=self.root,timeout=25)
        (capture/'stdout.private').write_bytes(q.stdout);(capture/'stderr.private').write_bytes(q.stderr);self.assertEqual((q.returncode,q.stderr),(0,b''),q.stdout.decode()[:2000]+q.stderr.decode()[:1000]);v=json.loads(q.stdout)
        if mode!='external':self.assertTrue(v['lock_free_after']);self.assertEqual(v['config_after'],v['config_before'])
        return v

    def refusal(self,mode):
        v=self.call(mode);self.assertEqual(v.get('error'),'recovery_required');self.assertNotIn('success',v);self.assertEqual(v['journal_after'],v['journal_before']);self.assertEqual(v['actor_after'],v['actor_before']);return v

    def test_live_same_process_cwd_drift_requires_attention_preserving_journals(self):self.refusal('actor_cwd')
    def test_live_legacy_identity_is_unknown_context_not_absent_worker(self):self.refusal('actor_legacy')
    def test_live_UID_mismatch_is_unknown_context_not_absent_worker(self):self.refusal('actor_uid')
    def test_live_birth_tick_mismatch_preserves_foreign_process_observation(self):self.refusal('actor_ticks')
    def test_live_unregistered_argv_is_not_absence_or_cleanup_permission(self):self.refusal('actor_argv')
    def test_missing_actor_record_stays_null_without_journal_publication(self):
        v=self.call('actor_missing');self.assertTrue(v.get('success'));self.assertIsNone(v['result']);self.assertEqual(v['journal_after'],v['journal_before'])
    def test_other_job_actor_record_stays_filtered_without_mutation(self):
        v=self.call('actor_other_job');self.assertTrue(v.get('success'));self.assertIsNone(v['result']);self.assertEqual(v['actor_after'],v['actor_before'])
    def test_actual_exited_owned_child_is_absent_without_signal_or_journal_change(self):
        v,c=actor_fixture.PickerActorContextTests.child(self);gone=self.call('actor_gone',proof=v['runtime']);self.assertTrue(gone.get('success'),gone.get('error'));self.assertIsNone(gone['result']);self.assertEqual(gone['journal_after'],gone['journal_before']);self.assertTrue(c['final_proc_absent'])
    def test_actual_owned_zombie_is_closed_then_reaped_without_signal(self):
        code="import json,os,sys\nprint(json.dumps({'pid':os.getpid()}),flush=True)\nsys.stdin.readline()\n";(self.root/'zombie-child.private.py').write_text(code)
        q=subprocess.Popen([sys.executable,'-B','-u',str(self.root/'zombie-child.private.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=self.root);record={'pid':q.pid}
        try:
            with actor_fixture.selectors.DefaultSelector()as selector:
                selector.register(q.stdout,actor_fixture.selectors.EVENT_READ);self.assertTrue(selector.select(5),'owned child startup deadline')
            start=q.stdout.readline();(self.root/'zombie-start.private').write_bytes(start);self.assertEqual(json.loads(start)['pid'],q.pid);proof=self.call('external',q.pid)['runtime'];q.stdin.write(b'close\n');q.stdin.flush();until=time.monotonic()+5;z=None
            while z is None and time.monotonic()<until:
                z=os.waitid(os.P_PID,q.pid,os.WEXITED|os.WNOWAIT|os.WNOHANG)
                if z is None:time.sleep(.01)
            self.assertIsNotNone(z,'owned child exit deadline');record['waitid_pid']=z.si_pid;record['stat_before']=Path('/proc',str(q.pid),'stat').read_text();self.assertEqual(record['stat_before'].rsplit(')',1)[1].strip().split()[0],'Z')
            v=self.call('actor_gone',proof=proof);self.assertTrue(v.get('success'),v.get('error'));self.assertIsNone(v['result']);self.assertEqual(v['journal_after'],v['journal_before'])
        finally:
            out,err=q.communicate(b'',timeout=5);record.update({'exit':q.returncode,'stderr':err.decode(),'stdout_after':out.decode(),'proc_absent':not Path('/proc',str(q.pid)).exists()});(self.root/'zombie-closure.private.json').write_text(json.dumps(record))
        self.assertEqual(record['exit'],0);self.assertTrue(record['proc_absent'])
    def test_previous_boot_full_six_field_journal_closes_metadata_without_signals(self):
        v=self.call('custom_previous_full');self.assertTrue(v.get('success'),v.get('error'));self.assertTrue(v['result']);self.assertIsNone(json.loads(__import__('base64').b64decode(v['journal_after']['raw_base64']))['actuator'])
    def test_previous_boot_legacy_journal_retains_existing_metadata_cleanup_compatibility(self):
        v=self.call('custom_previous_legacy');self.assertTrue(v.get('success'),v.get('error'));self.assertTrue(v['result'])
    def test_custom_context_invalid_or_same_boot_legacy_variants_preserve_all_bytes(self):
        for mode in ['custom_bad_uid','custom_bad_cwd','custom_extra','custom_partial','custom_current_legacy']:
            with self.subTest(mode=mode):self.refusal(mode)


if __name__=='__main__':unittest.main()
