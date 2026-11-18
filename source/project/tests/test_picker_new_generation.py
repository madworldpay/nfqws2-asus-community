"""New generation policy without invalidating historical single-round records."""
import json
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC


class NewGenerationTests(unittest.TestCase):
    def php(self, body):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [PHP, '-n', '-r', "umask(0077);require $argv[1].'/strategy-picker-runtime.php';" + body,
                 str(PUBLIC), directory], capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_new_preview_refuses_one_round_before_reading_or_mutating_runtime_state(self):
        value = self.php(r'''
        $r=(new ReflectionClass(NfqwsStrategyPickerRuntime::class))->newInstanceWithoutConstructor();
        $selection=NfqwsStrategyPickerRequest::selection(false,'all',true,null,'100000','1');
        try{$r->previewPlan($selection);$out='accepted';}catch(Throwable $e){$out=$e->getMessage();}
        echo json_encode($out);
        ''')
        self.assertEqual(value, 'invalid_request')

    def test_new_dispatch_defaults_generation_to_two_rounds_but_leaves_profile_comparison_single(self):
        value = self.php(r'''
        $method=new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'dispatch');$lines=file($method->getFileName());
        $body=implode('',array_slice($lines,$method->getStartLine()-1,$method->getEndLine()-$method->getStartLine()+1));
        eval('class NewGenerationDispatchFixture {
          public static function validateRequest($p){NfqwsStrategyPickerRuntime::validateRequest($p);}
          public function start(...$args){return $args;}
          public function previewPlan($selection){return $selection;}
        '.$body.'}');
        $r=new NewGenerationDispatchFixture;$base=['csrf_token'=>'x','goal'=>'all'];
        echo json_encode([
          $r->dispatch($base+['cmd'=>'pickerplan','search'=>'synthesis','extended'=>'0']),
          $r->dispatch($base+['cmd'=>'pickersynthesize','request_id'=>str_repeat('a',32),'consent'=>'test']),
          $r->dispatch($base+['cmd'=>'pickerplan','search'=>'profiles','extended'=>'0'])]);
        ''')
        self.assertIn('rounds', value[0])
        self.assertEqual(value[0]['rounds'], 2)
        # Missing count is resolved under the existing writer: a matching old
        # request keeps its stored count; a new generation defaults to two.
        self.assertIsNone(value[1][-1])
        self.assertNotIn('rounds', value[2])

    def test_million_pool_survives_server_selection_plan_and_json_record_without_clamping(self):
        value = self.php(r'''
        try{
          $selection=NfqwsStrategyPickerRequest::selection(false,'all',true,null,'1000000','2');
          $budget=NfqwsStrategyPickerBudget::choose(4,3000000,0);
          $choice=NfqwsStrategyPickerConcurrency::plan('1000000',$budget,['cores'=>4,'available_kib'=>3000000,'fd_soft'=>65535]);
          echo json_encode(['selection'=>$selection,'record'=>json_decode(json_encode(NfqwsStrategyPickerConcurrency::record($choice)),true),'pool'=>$choice['budget']['concurrency']]);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}
        ''')
        self.assertNotIn('error', value)
        self.assertEqual(value['selection']['concurrency'], '1000000')
        self.assertEqual(value['selection']['rounds'], 2)
        self.assertEqual(value['record']['requested'], '1000000')
        self.assertEqual(value['record']['effective'], 1000000)
        self.assertEqual(value['pool'], 1000000)
