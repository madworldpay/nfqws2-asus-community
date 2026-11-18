"""Execute the actual admission trait at fixed fractional monotonic clocks."""
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC


CODE = r'''
require $argv[1].'/strategy-picker-runtime.php';
$source=substr(file_get_contents($argv[1].'/strategy-synthesis-runtime.php'),5);
$source=preg_replace('/^require_once [^\n]+;\n/m','',$source);
$source=str_replace('__DIR__',var_export($argv[1],true),$source);
$shim= <<<'PHP'
namespace AdmissionClockFixture;
use \RuntimeException;
use \NfqwsStrategyPickerBudget;
use \NfqwsStrategyPickerTargets;
use \NfqwsStrategyPickerRequest;
final class AsusUpdateStore {public static float $now;public static function uptime():float{return self::$now;}}
PHP;
eval($shim.$source);
$harness= <<<'PHP'
namespace AdmissionClockFixture;
final class Store {public function __construct(public array $value){}public function read():array{return $this->value;}}
final class Harness {
 use NfqwsStrategySynthesisRuntime;
 private Store $store;
 public function __construct(array $job){$this->store=new Store($job);}
 private function customCheckpoint():void{}
 public function admit():void{$this->synthesisAdmission();}
 public function state():array{return $this->store->read();}
}
PHP;
eval($harness);
$cases=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$out=[];
foreach($cases as $case){
 \AdmissionClockFixture\AsusUpdateStore::$now=(float)$case['now'];
 $base=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(4,3000000,0),38);
 $budget=NfqwsStrategyPickerBudget::custom($base,2);
 $job=['custom_hosts'=>['alpha.example.com','beta.example.com'],'budget'=>$budget,'deadline'=>$case['now']+$case['seconds']];
 $h=new \AdmissionClockFixture\Harness($job);$error=null;
 try{$h->admit();}catch(Throwable $e){$error=$e->getMessage();}
 $out[]=['error'=>$error,'same'=>$h->state()===$job];
}
echo json_encode($out,JSON_THROW_ON_ERROR);
'''


class DeadlinePrecisionTests(unittest.TestCase):
    def call(self, cases):
        result=subprocess.run([PHP,'-n','-r',CODE,str(PUBLIC)],input=json.dumps(cases),text=True,capture_output=True,timeout=10)
        self.assertEqual((result.returncode,result.stderr),(0,''),result.stdout)
        return json.loads(result.stdout)

    def assert_cases(self, seconds, expected, clocks):
        results=self.call([{'now':now,'seconds':seconds}for now in clocks])
        self.assertEqual(results,[{'error':expected,'same':True}for _ in clocks])

    def test_exact_upper_deadline_at_observed_fraction_is_admitted(self):
        # The full regression caught 20239.97 - 13759.97 > 6480 in PHP.
        self.assert_cases(6480,None,[13759.97,13760.01,12056.17,1234567.89])

    def test_exact_minimum_deadline_is_admitted_without_extra_time(self):
        self.assert_cases(6420,None,[13759.97,13760.01,12056.17,1234567.89])

    def test_excess_above_upper_bound_has_no_epsilon_allowance(self):
        for seconds in [6480.001,6481]:
            self.assert_cases(seconds,'stale_state',[13759.97,1234567.89])

    def test_below_minimum_does_not_borrow_time(self):
        for seconds in [6419.999,6419]:
            self.assert_cases(seconds,'timed_out',[13759.97,1234567.89])
