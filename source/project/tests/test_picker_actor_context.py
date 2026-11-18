"""Picker actor identity reuses admission's real UID and cwd observations."""
import json,os,selectors,subprocess,sys,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC


class PickerActorContextTests(unittest.TestCase):
    def setUp(self):
        artifact=os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifact:self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=artifact))
        else:
            t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)

    def call(self,mode,pid=0):
        code=r'''require $argv[1].'/strategy-picker-runtime.php';$r=$argv[2];$d=json_decode(stream_get_contents(STDIN),true,16,JSON_THROW_ON_ERROR);$mode=$d['mode'];$out=[];
        if($mode==='invalid'){$out['identities']=[];foreach([-1,0,1]as $pid)$out['identities'][]=NfqwsStrategyPickerRuntime::identity($pid);}
        elseif($mode==='external'){$out['runtime']=NfqwsStrategyPickerRuntime::identity($d['pid']);$out['admission']=NfqwsStrategyPickerAdmission::identity($d['pid']);}
        else{
            $out['runtime']=NfqwsStrategyPickerRuntime::identity(getmypid());$out['admission']=NfqwsStrategyPickerAdmission::identity(getmypid());$out['same_before']=NfqwsStrategyPickerRuntime::sameActor($out['runtime']);
            $out['actual_pid']=getmypid();$out['actual_cwd']=getcwd();$status=file_get_contents('/proc/self/status');preg_match('/^Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$/m',$status,$uid);$out['actual_uids']=array_map('intval',array_slice($uid,1));
            if($mode==='cwd'){mkdir($r.'/changed-cwd',0700);if(!chdir($r.'/changed-cwd'))throw new RuntimeException('fixture_chdir_failed');$out['same_after']=NfqwsStrategyPickerRuntime::sameActor($out['runtime']);$out['after']=NfqwsStrategyPickerRuntime::identity(getmypid());$out['admission_after']=NfqwsStrategyPickerAdmission::identity(getmypid());}
            if($mode==='legacy'){$legacy=array_intersect_key($out['runtime'],array_flip(['pid','ticks','boot','argv']));$out['legacy']=$legacy;$out['legacy_accepted']=NfqwsStrategyPickerRuntime::sameActor($legacy);}
            if($mode==='tampered'){$out['tampered']=[];foreach(['uid','cwd']as $key){$v=$out['runtime'];$v[$key]=$key==='uid'?999999:$r.'/never-current';$out['tampered'][$key]=NfqwsStrategyPickerRuntime::sameActor($v);}}
        }echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request=json.dumps({'mode':mode,'pid':pid}).encode()
        for name,raw in [('php-r.private',code.encode()),('request.private.json',request),('actual-runtime.private',(PUBLIC/'strategy-picker-runtime.php').read_bytes()),('actual-admission.private',(PUBLIC/'strategy-picker-admission.php').read_bytes())]:(self.root/name).write_bytes(raw)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root)],input=request,capture_output=True,cwd=self.root,timeout=25)
        (self.root/'stdout.private').write_bytes(q.stdout);(self.root/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stdout.decode()[:2000]+q.stderr.decode()[:1000]);return json.loads(q.stdout)

    def child(self,closed=False):
        code="import json,os,sys\nprint(json.dumps({'pid':os.getpid(),'uid':os.getuid(),'cwd':os.getcwd()}),flush=True)\nsys.stdin.readline()\n"
        (self.root/'owned-child.private.py').write_text(code)
        q=subprocess.Popen([sys.executable,'-B','-u',str(self.root/'owned-child.private.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=self.root)
        record={'pid':q.pid};result=None
        try:
            with selectors.DefaultSelector()as selector:
                selector.register(q.stdout,selectors.EVENT_READ);self.assertTrue(selector.select(5),'owned child startup deadline')
            raw=q.stdout.readline();(self.root/'owned-child-start.private').write_bytes(raw);record['started']=json.loads(raw);self.assertEqual(record['started']['pid'],q.pid)
            if not closed:result=self.call('external',q.pid)
            out,err=q.communicate(b'close\n',timeout=5);record.update({'exit':q.returncode,'stdout_after':out.decode(),'stderr':err.decode(),'proc_absent':not Path('/proc',str(q.pid)).exists()})
            self.assertEqual((q.returncode,err),(0,b''));self.assertTrue(record['proc_absent'])
            if closed:result=self.call('external',q.pid)
        finally:
            if q.poll()is None:q.terminate();q.communicate(timeout=5);record['failure_only_own_child_terminated']=True
            record['final_exit']=q.returncode;record['final_proc_absent']=not Path('/proc',str(q.pid)).exists();(self.root/'owned-child-closure.private.json').write_text(json.dumps(record))
        return result,record

    def test_global_identity_matches_actual_admission_UID_cwd_and_closed_six_fields(self):
        v=self.call('identity');self.assertEqual(v['runtime'],v['admission']);self.assertEqual(set(v['runtime']),{'pid','ticks','boot','uid','argv','cwd'});self.assertEqual(v['runtime']['pid'],v['actual_pid']);self.assertEqual(v['runtime']['cwd'],v['actual_cwd']);self.assertEqual([v['runtime']['uid']]*4,v['actual_uids'])
    def test_same_actual_process_chdir_invalidates_prior_identity(self):
        v=self.call('cwd');self.assertTrue(v['same_before']);self.assertFalse(v['same_after']);self.assertEqual(v['after'],v['admission_after']);self.assertNotEqual(v['after']['cwd'],v['runtime']['cwd']);self.assertEqual({k:v['after'][k]for k in ['pid','ticks','boot','uid','argv']},{k:v['runtime'][k]for k in ['pid','ticks','boot','uid','argv']})
    def test_legacy_four_field_identity_is_not_current_actor_context(self):
        v=self.call('legacy');self.assertTrue(v['same_before']);self.assertEqual(set(v['legacy']),{'pid','ticks','boot','argv'});self.assertFalse(v['legacy_accepted'])
    def test_separate_actual_owned_child_identity_matches_UID_cwd_then_child_closes(self):
        v,c=self.child();self.assertEqual(v['runtime'],v['admission']);self.assertEqual(v['runtime']['pid'],c['pid']);self.assertEqual(v['runtime']['uid'],c['started']['uid']);self.assertEqual(v['runtime']['cwd'],c['started']['cwd']);self.assertTrue(c['final_proc_absent'])
    def test_exited_actual_owned_child_identity_is_null_without_signals(self):
        v,c=self.child(closed=True);self.assertIsNone(v['runtime']);self.assertIsNone(v['admission']);self.assertNotIn('failure_only_own_child_terminated',c)
    def test_unchanged_actual_process_and_tampered_context_controls(self):
        v=self.call('tampered');self.assertTrue(v['same_before']);self.assertEqual(v['tampered'],{'uid':False,'cwd':False})
    def test_invalid_and_init_PID_boundary_stays_null(self):
        v=self.call('invalid');self.assertEqual(v['identities'],[None,None,None])


if __name__=='__main__':unittest.main()
