"""Exercise actual supervisor code with a namespace-local deterministic clock only."""
from pathlib import Path
import json,os,subprocess,tempfile,unittest
from test_dpi_normalize import PHP, PUBLIC
P=PUBLIC
SOURCE=PUBLIC/'strategy-picker-custom-supervisor.php'
class CustomDeadlineTests(unittest.TestCase):
 def observe(self,deadline,clock):
  code=r'''umask(0077);require $argv[1].'/strategy-picker-custom-worker.php';
$source=file_get_contents($argv[2]);$source=str_replace('__DIR__',var_export($argv[1],true),substr($source,5));
$prefix='namespace DeadlineClock; use \\Closure; use \\RuntimeException; use \\Throwable; use \\stdClass; use \\NfqwsStrategyPickerBudget; use \\NfqwsStrategyPickerState; use \\NfqwsStrategyPickerCustomWorker; use \\NfqwsPlatform; use \\AsusSupportSchema; use \\AsusDpiDnsContext; class AsusUpdateStore{public static array $clock=[];public static function uptime():float{if(count(self::$clock)>1)return array_shift(self::$clock);return self::$clock[0];}}';
eval($prefix.$source);DeadlineClock\AsusUpdateStore::$clock=json_decode($argv[5],true);
$s=new NfqwsStrategyPickerState($argv[3].'/picker',(int)$argv[6]);$id=str_repeat('a',32);$hard=(float)$argv[4];
$s->write(['id'=>$id,'state'=>'running','deadline'=>$hard,'actuator'=>null]);$seen=[];
$transport=static function($args,$seconds,$input,$checkpoint)use($s,&$seen){$seen[]=['seconds'=>$seconds,'descriptor'=>$s->read()['custom_worker']];return ['status'=>0,'output'=>'{}'];};
$sup=new DeadlineClock\NfqwsStrategyPickerCustomSupervisor($s,static function(){},$transport);
try{(new ReflectionMethod($sup,'run'))->invoke($sup,'prepare',['schema_version'=>1,'hosts'=>['example.com'],'dns_context'=>str_repeat('c',64)],$id);$error=null;}catch(Throwable $e){$error=$e->getMessage();}
echo json_encode(['error'=>$error,'seen'=>$seen,'remaining_descriptor'=>$s->read()['custom_worker']??null]);'''
  with tempfile.TemporaryDirectory()as d:r=subprocess.run([PHP,'-n','-r',code,str(P),str(SOURCE),d,str(deadline),json.dumps(clock),str(os.getuid())],capture_output=True,text=True,timeout=5)
  self.assertEqual(r.returncode,0,r.stderr+r.stdout);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
 def test_near_deadline_never_persists_a_worker_deadline_beyond_its_job(self):
  out=self.observe(100.999,[99.5,99.9,100.5]);self.assertIsNone(out['error']);self.assertEqual(out['seen'][0]['seconds'],1)
  self.assertLessEqual(out['seen'][0]['descriptor']['deadline'],100.999);self.assertAlmostEqual(out['seen'][0]['descriptor']['deadline'],100.9)
  self.assertIsNone(out['remaining_descriptor'])
 def test_ninety_second_limit_uses_the_same_clock_sample_as_remaining_budget(self):
  out=self.observe(300,[0.0,0.0,1.0]);self.assertIsNone(out['error']);self.assertEqual(out['seen'][0]['seconds'],90)
  self.assertEqual(out['seen'][0]['descriptor']['deadline'],90);self.assertIsNone(out['remaining_descriptor'])
 def test_subsecond_remaining_time_refuses_before_launch_or_descriptor_write(self):
  out=self.observe(100.9,[100.0,100.5,100.6]);self.assertEqual(out['error'],'timed_out');self.assertEqual(out['seen'],[]);self.assertIsNone(out['remaining_descriptor'])
if __name__=='__main__':unittest.main()
