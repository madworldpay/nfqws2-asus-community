import json,os,subprocess,tempfile,unittest
from test_dpi_normalize import PHP,PUBLIC

class GuardDiagnosticsTests(unittest.TestCase):
 def php(self,body):
  with tempfile.TemporaryDirectory() as tmp:
   code="umask(0077);require $argv[1].'/strategy-picker-runtime.php';$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$id=str_repeat('a',32);$s->write(['id'=>$id,'state'=>'running','phase'=>'discovering','profiles'=>[]]);$r=new NfqwsStrategyPickerRuntime($s);$m=new ReflectionMethod($r,'diagnoseGuard');"+body
   v=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),tmp,str(os.getuid())],capture_output=True,text=True)
  self.assertEqual(v.returncode,0,v.stderr+v.stdout);self.assertEqual(v.stderr,'');return json.loads(v.stdout)
 def test_first_guard_exception_is_bounded_and_preserved_without_rewriting_job(self):
  v=self.php("""$before=$s->read();try{throw new RuntimeException(str_repeat('x',16000));}catch(Throwable $e){$m->invoke($r,$id,$e);}$first=$s->read('failure-guard.json');$m->invoke($r,$id,new RuntimeException('secondary'));$after=$s->read('failure-guard.json');echo json_encode(['first'=>$first,'same'=>$first===$after,'job_unchanged'=>$before===$s->read(),'bytes'=>filesize($s->path('failure-guard.json'))]);""")
  self.assertTrue(v['same']);self.assertTrue(v['job_unchanged']);self.assertLessEqual(v['bytes'],4096)
  f=v['first'];self.assertEqual(f['id'],'a'*32);self.assertEqual(f['kind'],'guard_exception');self.assertEqual(f['class'],'RuntimeException');self.assertEqual(len(f['message']),512);self.assertEqual(f['phase'],'discovering');self.assertIsInstance(f['uptime'],(int,float));self.assertIsInstance(f['peak'],int)
 def test_stale_caller_cannot_replace_the_current_jobs_diagnostic(self):
  v=self.php("""$id2=str_repeat('b',32);$s->write(['id'=>$id2,'state'=>'running','profiles'=>[]]);$s->write(['id'=>$id2,'kind'=>'foreign'],'failure-guard.json');$before=$s->read('failure-guard.json');$m->invoke($r,$id,new RuntimeException('wrong job'));echo json_encode([$before===$s->read('failure-guard.json'),$s->read()['id']]);""")
  self.assertEqual(v,[True,'b'*32])
 def test_diagnostic_storage_failure_never_changes_job_or_throws(self):
  v=self.php("""$before=$s->read();mkdir($s->root.'/failure-guard.json',0700);$m->invoke($r,$id,new RuntimeException('original'));echo json_encode([$before===$s->read(),is_dir($s->root.'/failure-guard.json')]);""")
  self.assertEqual(v,[True,True])
 def test_current_job_replaces_the_previous_jobs_diagnostic(self):
  v=self.php("""$s->write(['id'=>str_repeat('b',32),'kind'=>'old'],'failure-guard.json');$m->invoke($r,$id,new RuntimeException('current'));echo json_encode($s->read('failure-guard.json'));""")
  self.assertEqual(v['id'],'a'*32);self.assertEqual(v['message'],'current')
 def fail_with_foreign_config(self,guard):
  return self.php("""$file=$argv[2].'/config';file_put_contents($file,'original');chmod($file,0600);$cfg=new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]);$j=$cfg->snapshot(false);$id=$j['id'];file_put_contents($file,'foreign');$r=new NfqwsStrategyPickerRuntime($s,$cfg);$fail=new ReflectionMethod($r,'fail');$fail->invoke($r,'interrupted'"""+(",$id" if guard else "")+""");echo json_encode(['job'=>$s->read(),'diagnostic'=>$s->read('failure-guard.json'),'bytes'=>file_get_contents($file)]);""")
 def test_guard_recovery_exception_keeps_the_cause_before_fail_swallows_it(self):
  v=self.fail_with_foreign_config(True)
  self.assertEqual(v['job']['state'],'recovery_required');self.assertEqual(v['job']['code'],'source_changed');self.assertEqual(v['bytes'],'foreign')
  self.assertIsNotNone(v['diagnostic'],'guard fail() path must retain its restore exception')
  self.assertEqual(v['diagnostic']['code'],'source_changed');self.assertEqual(v['diagnostic']['id'],v['job']['id'])
 def test_worker_recovery_behavior_does_not_create_a_guard_diagnostic(self):
  v=self.fail_with_foreign_config(False)
  self.assertEqual(v['job']['state'],'recovery_required');self.assertEqual(v['job']['code'],'source_changed');self.assertEqual(v['bytes'],'foreign');self.assertIsNone(v['diagnostic'])
