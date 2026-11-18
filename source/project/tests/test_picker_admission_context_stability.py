"""Admission's observed process context must survive its own read IO."""
import base64,json,os,subprocess,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
import test_picker_actor_context as actor_context_fixture


class PickerAdmissionContextStabilityTests(unittest.TestCase):
    setUp=actor_context_fixture.PickerActorContextTests.setUp

    def call(self,mode,pid=0):
        body=(PUBLIC/'strategy-picker-admission.php').read_text().removeprefix('<?php')
        code=r'''require $argv[1].'/strategy-picker-runtime.php';$r=$argv[2];$d=json_decode(stream_get_contents(STDIN),true,16,JSON_THROW_ON_ERROR);$GLOBALS['r']=$r;$GLOBALS['mode']=$d['mode'];$GLOBALS['drifted']=false;$GLOBALS['reads']=[];mkdir($r.'/changed-cwd',0700);
        $wrapper=<<<'PHP'
        namespace AdmissionContextProbe;
        use \RuntimeException;
        function file_get_contents($p,...$args){$raw=\file_get_contents($p,...$args);$GLOBALS['reads'][]=['kind'=>'file','path'=>$p,'raw_base64'=>\is_string($raw)?\base64_encode($raw):null];if(!$GLOBALS['drifted']&&$GLOBALS['mode']==='after_uid'&&$p==='/proc/'.\getmypid().'/status'){$GLOBALS['drifted']=true;if(!\chdir($GLOBALS['r'].'/changed-cwd'))throw new \RuntimeException('fixture_chdir_failed');}return $raw;}
        function readlink($p){$value=\readlink($p);$GLOBALS['reads'][]=['kind'=>'link','path'=>$p,'value'=>$value];if(!$GLOBALS['drifted']&&$GLOBALS['mode']==='after_cwd'&&$p==='/proc/'.\getmypid().'/cwd'){$GLOBALS['drifted']=true;if(!\chdir($GLOBALS['r'].'/changed-cwd'))throw new \RuntimeException('fixture_chdir_failed');}return $value;}
        PHP;
        eval($wrapper.$d['body']);$out=['cwd_before'=>getcwd(),'pid'=>getmypid()];
        if($d['mode']==='external'){$out['runtime']=NfqwsStrategyPickerRuntime::identity($d['pid']);$out['admission']=NfqwsStrategyPickerAdmission::identity($d['pid']);}
        elseif($d['mode']==='global'){$out['runtime']=NfqwsStrategyPickerRuntime::identity(getmypid());$out['admission']=NfqwsStrategyPickerAdmission::identity(getmypid());}
        else{$out['observed']=\AdmissionContextProbe\NfqwsStrategyPickerAdmission::identity(getmypid());$out['actual_after']=NfqwsStrategyPickerAdmission::identity(getmypid());}
        $out['cwd_after']=getcwd();$out['drifted']=$GLOBALS['drifted'];$out['reads']=$GLOBALS['reads'];echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request=json.dumps({'mode':mode,'pid':pid,'body':body}).encode()
        for name,raw in [('php-r.private',code.encode()),('request.private.json',request),('actual-admission-class.private',body.encode()),('actual-runtime.private',(PUBLIC/'strategy-picker-runtime.php').read_bytes())]:(self.root/name).write_bytes(raw)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root)],input=request,capture_output=True,cwd=self.root,timeout=25)
        (self.root/'stdout.private').write_bytes(q.stdout);(self.root/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stdout.decode()[:2000]+q.stderr.decode()[:1000]);return json.loads(q.stdout)

    def test_actual_cwd_change_after_readlink_refuses_stale_observation(self):
        v=self.call('after_cwd');self.assertTrue(v['drifted']);self.assertIsNone(v['observed']);self.assertEqual(v['actual_after']['cwd'],str(self.root/'changed-cwd'));self.assertEqual(v['cwd_before'],str(self.root));self.assertEqual(v['cwd_after'],str(self.root/'changed-cwd'))
    def test_actual_cwd_change_during_UID_read_refuses_stale_observation(self):
        v=self.call('after_uid');self.assertTrue(v['drifted']);self.assertIsNone(v['observed']);self.assertEqual(v['actual_after']['cwd'],str(self.root/'changed-cwd'));self.assertTrue(any(x['path']=='/proc/'+str(v['pid'])+'/status'for x in v['reads']))
    def test_GLOBAL_Runtime_accepts_actual_stable_context_through_changed_Admission_reader(self):
        v=self.call('global');self.assertEqual(v['runtime'],v['admission']);self.assertEqual(set(v['runtime']),{'pid','ticks','boot','uid','argv','cwd'});self.assertEqual(v['runtime']['pid'],v['pid']);self.assertEqual(v['runtime']['uid'],os.getuid());self.assertEqual(v['runtime']['cwd'],str(self.root));self.assertFalse(v['drifted'])
    def test_GLOBAL_stable_separate_owned_child_context_survives_reader_and_child_closes(self):
        v,c=actor_context_fixture.PickerActorContextTests.child(self);self.assertEqual(v['runtime'],v['admission']);self.assertEqual(v['runtime']['pid'],c['pid']);self.assertEqual(v['runtime']['uid'],c['started']['uid']);self.assertEqual(v['runtime']['cwd'],c['started']['cwd']);self.assertTrue(c['final_proc_absent'])


if __name__=='__main__':unittest.main()
