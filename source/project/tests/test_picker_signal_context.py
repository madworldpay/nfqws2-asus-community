"""Signal eligibility must retain the complete observed process context."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC

class PickerSignalContextTests(unittest.TestCase):
    def setUp(self):
        artifact=os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifact:self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=artifact))
        else:
            t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)

    def call(self,mode):
        code=r'''require $argv[1].'/strategy-picker-runtime.php';$f=new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'sameProcess');$proof=NfqwsStrategyPickerRuntime::identity(getmypid());$out=['before'=>$proof,'clean'=>$f->invoke(null,$proof)];$mode=$argv[3];
        if($mode==='chdir'){mkdir($argv[2].'/changed',0700);chdir($argv[2].'/changed');$out['after']=NfqwsStrategyPickerRuntime::identity(getmypid());$out['accepted']=$f->invoke(null,$proof);}
        elseif($mode==='legacy'){$proof=array_intersect_key($proof,array_flip(['pid','ticks','boot','argv']));$out['accepted']=$f->invoke(null,$proof);}
        elseif(in_array($mode,['uid','cwd','argv'],true)){$proof[$mode]=$mode==='uid'?999999:($mode==='cwd'?'/never-current-owned-context':['CONTROLLED_DIFFERENT_ARGV']);$out['accepted']=$f->invoke(null,$proof);}
        elseif($mode==='invalid'){$out['invalid']=[];foreach([null,[],['pid'=>0],['pid'=>1],['pid'=>'2']]as $v)$out['invalid'][]=$f->invoke(null,$v);}
        echo json_encode($out,JSON_THROW_ON_ERROR);'''
        for name,data in [('php-r.private',code.encode()),('mode.private',mode.encode()),('runtime.private',(PUBLIC/'strategy-picker-runtime.php').read_bytes()),('admission.private',(PUBLIC/'strategy-picker-admission.php').read_bytes())]:(self.root/name).write_bytes(data)
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),mode],cwd=self.root,capture_output=True,timeout=25)
        (self.root/'stdout.private').write_bytes(r.stdout);(self.root/'stderr.private').write_bytes(r.stderr)
        self.assertEqual((r.returncode,r.stderr),(0,b''));return json.loads(r.stdout)

    def test_actual_same_process_chdir_revokes_prior_signal_eligibility(self):
        v=self.call('chdir');self.assertTrue(v['clean']);self.assertFalse(v['accepted']);self.assertNotEqual(v['before']['cwd'],v['after']['cwd']);self.assertEqual({k:v['before'][k]for k in ('pid','ticks','boot','uid','argv')},{k:v['after'][k]for k in ('pid','ticks','boot','uid','argv')})
    def test_wrong_UID_cannot_authorize_signal(self):self.assertFalse(self.call('uid')['accepted'])
    def test_wrong_cwd_cannot_authorize_signal(self):self.assertFalse(self.call('cwd')['accepted'])
    def test_wrong_argv_cannot_authorize_signal(self):self.assertFalse(self.call('argv')['accepted'])
    def test_legacy_partial_context_cannot_authorize_signal(self):self.assertFalse(self.call('legacy')['accepted'])
    def test_unchanged_complete_actual_context_still_matches(self):self.assertTrue(self.call('clean')['clean'])
    def test_invalid_missing_and_init_proofs_are_closed(self):self.assertEqual(self.call('invalid')['invalid'],[False]*5)

if __name__=='__main__':unittest.main()
