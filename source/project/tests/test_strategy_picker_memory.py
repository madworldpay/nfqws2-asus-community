import json, os, subprocess, tempfile, unittest
from test_dpi_normalize import PHP, PUBLIC


class PickerFailureDiagnosticsTests(unittest.TestCase):
    def test_memory_failure_records_bounded_context_without_secret_trace_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            code=r'''require $argv[1].'/strategy-picker-runtime.php';ini_set('zend.exception_ignore_args','0');
            $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);
            $s->write(['id'=>str_repeat('a',32),'state'=>'running','phase'=>'discovering','current_name'=>'trial 8','profiles'=>[],'goal'=>'youtube','private_value'=>'PRIVATE_CONFIG_CANARY']);
            $r=new NfqwsStrategyPickerRuntime($s);
            function withPrivateArgument($secret){throw new RuntimeException('insufficient_memory');}
            try{withPrivateArgument('PRIVATE_TRACE_CANARY');}catch(Throwable $error){
              try{(new ReflectionMethod($r,'recordFailure'))->invoke($r,$error);}catch(ReflectionException $missing){}
            }
            echo json_encode(['journal'=>$s->read(),'public'=>$r->status()],JSON_THROW_ON_ERROR);'''
            run=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),directory,str(os.getuid())],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr+run.stdout)
        self.assertEqual(run.stderr,'')
        out=json.loads(run.stdout);d=out['journal'].get('failure_diagnostics',{})
        self.assertEqual(d.get('code'),'insufficient_memory')
        self.assertEqual(d.get('phase'),'discovering')
        self.assertEqual(out['journal']['state'],'running')
        self.assertIsInstance(d.get('available_kib'),int)
        self.assertGreaterEqual(d['available_kib'],0)
        self.assertGreater(d.get('php_peak_bytes',0),0)
        self.assertLessEqual(len(d.get('trace',[])),8)
        self.assertTrue(any(x.get('function')=='withPrivateArgument'for x in d['trace']))
        self.assertTrue(all(set(x)<= {'file','line','class','function'} for x in d['trace']))
        self.assertNotIn('PRIVATE_TRACE_CANARY',json.dumps(d))
        self.assertNotIn(directory,json.dumps(d))
        self.assertNotIn('failure_diagnostics',json.dumps(out['public']))
        self.assertNotIn('PRIVATE_CONFIG_CANARY',json.dumps(out['public']))


if __name__=='__main__':unittest.main()
