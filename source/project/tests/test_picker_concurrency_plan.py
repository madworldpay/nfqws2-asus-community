"""Read-only UI planning and final admission must describe the same work."""
import json
import os
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


class PickerConcurrencyPlanTests(unittest.TestCase):
    def php(self, body):
        with tempfile.TemporaryDirectory() as directory:
            p=subprocess.run([PHP,'-n','-r',"umask(0077);require $argv[1].'/strategy-picker-runtime.php';"+body,
                str(PUBLIC),directory,str(os.getuid())],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)

    def test_read_only_plan_has_a_closed_typed_contract_and_no_consent_or_request_id(self):
        r=self.php(r'''
        $base=['cmd'=>'pickerplan','csrf_token'=>'x','search'=>'synthesis','extended'=>'0','goal'=>'all','concurrency'=>'32'];
        $out=[];foreach([$base,$base+['custom_sites'=>'example.com','custom_only'=>'1'],
          $base+['consent'=>'test'],$base+['request_id'=>str_repeat('a',32)],
          array_replace($base,['search'=>'other']),array_replace($base,['extended'=>'true']),
          array_replace($base,['search'=>'profiles'])+['custom_sites'=>'example.com','custom_only'=>'0'],
          array_replace($base,['concurrency'=>32])]as $p){
          try{NfqwsStrategyPickerRuntime::validateRequest($p);$out[]='ready';}catch(Throwable $e){$out[]=$e->getMessage();}
        }echo json_encode($out);
        ''')
        self.assertEqual(r,['ready']*2+['invalid_request']*6)

    def test_plan_hash_is_optional_only_for_start_commands_and_never_coerced(self):
        r=self.php(r'''
        $out=[];foreach(['pickerstart','pickerextended','pickersynthesize']as $cmd){
          $base=['cmd'=>$cmd,'csrf_token'=>'x','request_id'=>str_repeat('a',32),'consent'=>'test'];
          foreach([str_repeat('a',64),str_repeat('A',64),'',str_repeat('a',63),null,[]]as $hash){
            try{NfqwsStrategyPickerRuntime::validateRequest($base+['plan_sha256'=>$hash]);$out[]='ready';}
            catch(Throwable $e){$out[]=$e->getMessage();}
          }
        }try{NfqwsStrategyPickerRuntime::validateRequest(['cmd'=>'pickerstatus','csrf_token'=>'x','plan_sha256'=>str_repeat('a',64)]);$out[]='accepted';}
        catch(Throwable $e){$out[]=$e->getMessage();}echo json_encode($out);
        ''')
        self.assertEqual(r,(['ready']+['invalid_request']*5)*3+['invalid_request'])

    def test_same_planner_produces_full_custom_budgets_without_creating_state(self):
        r=self.php(r'''
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$r=new NfqwsStrategyPickerRuntime($s);
        $m=new ReflectionMethod($r,'planSelection');$out=[];
        foreach(['2','32']as $pool){$selection=NfqwsStrategyPickerRequest::selection(false,'all',true,['hosts'=>['example.com'],'only'=>true],$pool);
          $p=$m->invoke($r,$selection);$out[]=['choice'=>$p['concurrency_choice'],'budget'=>$p['budget'],'domains'=>count($p['probe_domains'])];}
        echo json_encode(['plans'=>$out,'no_state'=>!file_exists($s->root)]);
        ''')
        self.assertTrue(r['no_state'])
        self.assertEqual([x['budget']['concurrency']for x in r['plans']],[2,32])
        self.assertEqual([x['budget']['deadline_seconds']for x in r['plans']],[14760,6480])
        self.assertTrue(all(x['domains']==40 and x['budget']['domain_count']==40 and x['budget']['custom']['max_hosts']==1 for x in r['plans']))

    def test_plan_binding_ignores_ram_jitter_but_covers_policy_scope_config_resources_and_boot(self):
        r=self.php(r'''
        $selection=NfqwsStrategyPickerRequest::selection(false,'all',true,null,'32');
        $b=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(4,900000,0),38);
        $p=NfqwsStrategyPickerConcurrency::plan('32',$b,['cores'=>4,'available_kib'=>900000,'fd_soft'=>2048]);
        $bind=fn($s,$p,$config,$resources,$boot)=>NfqwsStrategyPickerConcurrency::binding($s,$p['budget'],NfqwsStrategyPickerConcurrency::record($p),$config,$resources,$boot);
        $base=$bind($selection,$p,str_repeat('a',64),str_repeat('b',64),str_repeat('c',64));$out=[];
        $jitter=$p;$jitter['budget']['load']=.1;$jitter['budget']['available_kib']=850000;$jitter['admission']['available_kib']=850000;
        $out[]=$base===$bind($selection,$jitter,str_repeat('a',64),str_repeat('b',64),str_repeat('c',64));
        foreach(['selection','effective','budget','config','resources','boot']as $kind){
          $s=$selection;$x=$p;$config=str_repeat('a',64);$resources=str_repeat('b',64);$boot=str_repeat('c',64);
          if($kind==='selection')$s['goal']='youtube';if($kind==='effective')$x['effective']=33;
          if($kind==='budget')$x['budget']['max_repeats']=4;if($kind==='config')$config=str_repeat('d',64);
          if($kind==='resources')$resources=str_repeat('d',64);if($kind==='boot')$boot=str_repeat('d',64);
          $out[]=$base!==$bind($s,$x,$config,$resources,$boot);
        }echo json_encode($out);
        ''')
        self.assertEqual(r,[True]*7)


if __name__=='__main__':unittest.main()
