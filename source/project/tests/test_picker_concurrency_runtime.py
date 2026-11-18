"""The selected pool must survive API, journal, native options and evidence."""
import json
import os
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


class PickerConcurrencyRuntimeTests(unittest.TestCase):
    def php(self, body):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([PHP, '-n', '-r',
                "umask(0077);require $argv[1].'/strategy-picker-runtime.php';" + body,
                str(PUBLIC), directory, str(os.getuid())], capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    JOB = r'''
    function job($requested='32',$custom=false){
      $selection=NfqwsStrategyPickerRequest::selection(false,'all',true,
        $custom?['hosts'=>['example.com'],'only'=>false]:null,$requested);
      $domains=array_map(fn($n)=>'host'.$n.'.example.com',range(1,38));
      $auto=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(4,900000,0),count($domains));
      $plan=NfqwsStrategyPickerConcurrency::plan($requested,$auto,['cores'=>4,'available_kib'=>900000,'fd_soft'=>2048]);
      $budget=$custom?NfqwsStrategyPickerBudget::custom($plan['budget'],1):$plan['budget'];
      return $selection+['selection_sha256'=>NfqwsStrategyPickerRequest::digest($selection),
        'concurrency_choice'=>NfqwsStrategyPickerConcurrency::record($plan),'budget'=>$budget,'probe_domains'=>$domains];
    }
    '''

    def test_typed_pool_is_optional_for_all_three_starts_and_forbidden_elsewhere(self):
        r=self.php(r'''
        $out=[];foreach(['pickerstart','pickerextended','pickersynthesize']as $cmd){
          $base=['cmd'=>$cmd,'csrf_token'=>'x','request_id'=>str_repeat('a',32),'consent'=>'test'];
          foreach([null,'auto','2','1024',2,'02','1000001','',[],false]as $pool){
            $p=$base;if($pool!==null)$p['concurrency']=$pool;
            try{NfqwsStrategyPickerRuntime::validateRequest($p);$out[]='ready';}catch(Throwable $e){$out[]=$e->getMessage();}
          }
        }
        foreach([['cmd'=>'pickerstatus'],['cmd'=>'pickertargets','custom_sites'=>'example.com'],
          ['cmd'=>'pickerapply','id'=>str_repeat('b',32)],['cmd'=>'pickerexport','id'=>str_repeat('b',32)]]as $p){
          try{NfqwsStrategyPickerRuntime::validateRequest($p+['csrf_token'=>'x','concurrency'=>'2']);$out[]='accepted';}
          catch(Throwable $e){$out[]=$e->getMessage();}
        }echo json_encode($out);
        ''')
        self.assertEqual(r, (['ready']*4+['invalid_request']*6)*3+['invalid_request']*4)

    def test_recorded_manual_and_auto_choices_rederive_after_json_storage_round_trip(self):
        r=self.php(self.JOB+r'''
        $out=[];foreach(['auto','2','32','992']as $pool)foreach([false,true]as $custom){
          $j=json_decode(json_encode(job($pool,$custom)),true);
          $choice=NfqwsStrategyPickerConcurrency::job($j);
          $out[]=['requested'=>$choice['requested'],'effective'=>$choice['effective'],'budget'=>$j['budget']['concurrency']];
        }echo json_encode($out);
        ''')
        self.assertEqual(r,[dict(requested=p,effective=n,budget=n) for p,n in
                            [('auto',10),('2',2),('32',32),('992',992)] for _ in range(2)])

    def test_tampered_choice_budget_scope_or_selection_is_rejected_without_mutation(self):
        r=self.php(self.JOB+r'''
        $out=[];$good=job('992',true);
        foreach(['pool','requested','version','admission','memory','budget','deadline','scope','selection','missing','null','unknown']as $kind){
          $j=$good;
          switch($kind){
            case 'pool':$j['concurrency_choice']['effective']=991;break;
            case 'requested':$j['concurrency']='32';break;
            case 'version':$j['concurrency_choice']['policy_version']='other';break;
            case 'admission':$j['concurrency_choice']['admission']['fd_soft']='1023';break;
            case 'memory':$j['budget']['available_kib']='900000';break;
            case 'budget':$j['budget']['concurrency']=10;break;
            case 'deadline':$j['budget']['deadline_seconds']++;break;
            case 'scope':array_pop($j['probe_domains']);break;
            case 'selection':$j['selection_sha256']=str_repeat('f',64);break;
            case 'missing':unset($j['concurrency_choice']);break;
            case 'null':$j['concurrency_choice']=null;break;
            case 'unknown':$j['concurrency_choice']['unexpected']='x';break;
          }
          $before=$j;try{NfqwsStrategyPickerConcurrency::job($j);$out[]='accepted';}
          catch(Throwable $e){$out[]=$e->getMessage();}if($j!==$before)throw new RuntimeException('mutated');
        }echo json_encode($out);
        ''')
        self.assertEqual(r,['invalid_request']*12)

    def test_legacy_missing_choice_stays_auto_but_cannot_claim_manual_metadata(self):
        r=self.php(r'''
        $out=[NfqwsStrategyPickerConcurrency::job(['budget'=>['concurrency'=>4]])];
        foreach(['32',null,32,'032']as $pool){try{$out[]=NfqwsStrategyPickerConcurrency::job(['concurrency'=>$pool]);}
          catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);
        ''')
        self.assertEqual(r,[None]+['invalid_request']*4)

    def test_raw_native_pool_must_match_every_new_job_choice_without_coercion(self):
        r=self.php(self.JOB+r'''
        $out=[];foreach(['auto','32']as $pool){$j=job($pool);$n=$j['budget']['concurrency'];
          foreach([$n,(string)$n,$n+1,null]as $actual){try{
            NfqwsStrategyPickerConcurrency::verifyNative($j,['settings'=>['config'=>['MAX_CONCURRENT'=>$actual]]]);$out[]='ready';
          }catch(Throwable $e){$out[]=$e->getMessage();}}
        }NfqwsStrategyPickerConcurrency::verifyNative(['budget'=>['concurrency'=>4]],[]);echo json_encode($out);
        ''')
        self.assertEqual(r,(['ready']+['incomparable_result']*3)*2)

    def test_real_score_fingerprint_already_separates_pool_settings(self):
        r=self.php(r'''
        $base=['state'=>'completed','coverage'=>['domains'=>1,'tcp'=>1],
          'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>[
            ['domain'=>'youtube.com','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'quic_ok']]]]],
            ['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'control','status'=>'ok']]]]]]];
        $base['settings']=['config'=>['MAX_CONCURRENT'=>32]];$a=NfqwsStrategyPickerScore::measure($base);
        $base['settings']['config']['MAX_CONCURRENT']=33;$b=NfqwsStrategyPickerScore::measure($base);
        echo json_encode(['different'=>$a['targets']!==$b['targets'],
          'rank'=>NfqwsStrategyPickerScore::compare([$a,$a],[$b,$b])]);
        ''')
        self.assertTrue(r['different']);self.assertEqual(r['rank']['reason'],'incomparable_result')

    def test_resource_facts_use_strict_shared_proc_parsers(self):
        r=self.php(r'''
        $facts=NfqwsStrategyPickerConcurrency::readFacts();
        echo json_encode(['facts'=>$facts,'cores'=>AsusDpiLoadPolicy::cores(file_get_contents('/proc/stat')),
          'fd'=>AsusDpiLoadPolicy::fileDescriptors(file_get_contents('/proc/self/limits'))]);
        ''')
        self.assertEqual(r['facts']['cores'],r['cores']);self.assertGreater(r['facts']['available_kib'],0)
        self.assertEqual(r['facts']['fd_soft'],r['fd'])

    def test_production_dispatch_forwards_the_validated_choice_for_each_start_mode(self):
        r=self.php(r'''
        $method=new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'dispatch');
        $lines=file($method->getFileName());$body=implode('',array_slice($lines,$method->getStartLine()-1,$method->getEndLine()-$method->getStartLine()+1));
        eval('class DispatchPoolFixture {
          public static function validateRequest($p){NfqwsStrategyPickerRuntime::validateRequest($p);}
          public function start(...$args){return $args;}
        '.$body.'}');
        $r=new DispatchPoolFixture;$out=[];
        foreach(['pickerstart','pickerextended','pickersynthesize']as $cmd)foreach([null,'32']as $pool){
          $p=['cmd'=>$cmd,'csrf_token'=>'x','request_id'=>str_repeat('a',32),'consent'=>'test','goal'=>'youtube'];
          if($pool!==null)$p['concurrency']=$pool;$out[]=$r->dispatch($p);
        }echo json_encode($out);
        ''')
        self.assertEqual(r, [['a'*32,extended,'youtube',synthesis,None,pool,None]+([None] if synthesis else [])
                            for extended,synthesis in [(False,False),(True,False),(False,True)]
                            for pool in ['auto','32']])

    def test_status_reports_only_rederived_pool_metadata_and_blocks_corrupt_apply_flags(self):
        r=self.php(self.JOB+r'''
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$r=new NfqwsStrategyPickerRuntime($s);
        $j=job()+['id'=>str_repeat('a',32),'state'=>'completed','phase'=>'complete','profiles'=>[],
          'restored'=>true,'winner'=>'chosen','generated'=>null];
        $s->write(['id'=>$j['id'],'winner'=>'chosen','files'=>[]],'winner-auto.json');$s->write($j);
        $valid=$r->status()['job'];$j['budget']['concurrency']=31;$s->write($j);$bad=$r->status()['job'];
        unset($j['concurrency_choice'],$j['concurrency']);
        $j['selection_sha256']=NfqwsStrategyPickerRequest::digest(NfqwsStrategyPickerRequest::selection(false,'all',true));
        $s->write($j);$legacy=$r->status()['job'];
        echo json_encode(['valid'=>$valid,'bad'=>$bad,'legacy'=>$legacy]);
        ''')
        self.assertEqual(r['valid']['concurrency_choice']['requested'],'32')
        self.assertEqual(r['valid']['concurrency_choice']['effective'],32)
        self.assertTrue(r['valid']['concurrency_valid']);self.assertFalse(r['valid']['can_apply'])
        self.assertFalse(r['bad']['concurrency_valid']);self.assertFalse(r['bad']['can_apply'])
        self.assertFalse(r['bad']['can_export']);self.assertIsNone(r['bad']['concurrency_choice'])
        self.assertTrue(r['legacy']['concurrency_valid']);self.assertIsNone(r['legacy']['concurrency_choice'])

    def test_compact_runs_bind_the_verified_native_pool_and_legacy_scores_stay_unchanged(self):
        r=self.php(self.JOB+r'''
        $native=['state'=>'completed','coverage'=>['domains'=>1,'tcp'=>1],
          'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>[
            ['domain'=>'youtube.com','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'quic_ok']]]]],
            ['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'control','status'=>'ok']]]]]],
          'settings'=>['config'=>['MAX_CONCURRENT'=>32]]];
        $j=job();$score=NfqwsStrategyPickerConcurrency::measure($j,$native);$out=[];
        foreach(['valid','wrong','missing','extra']as $kind){$run=$score;
          if($kind==='wrong')$run['request_pool']['effective']=31;
          if($kind==='missing')unset($run['request_pool']);
          if($kind==='extra')$run['request_pool']['untrusted']='x';
          try{NfqwsStrategyPickerConcurrency::verifyRuns($j,[['runs'=>[$run,$run]]]);$out[]='ready';}
          catch(Throwable $e){$out[]=$e->getMessage();}
        }
        $legacy=NfqwsStrategyPickerConcurrency::measure([],$native);
        NfqwsStrategyPickerConcurrency::verifyRuns([],[['runs'=>[$legacy,$legacy]]]);
        echo json_encode(['metadata'=>$score['request_pool'],'checks'=>$out,
          'fingerprint_unchanged'=>$score['targets']===$legacy['targets'],
          'legacy_unchanged'=>$legacy===NfqwsStrategyPickerScore::measure($native)]);
        ''')
        self.assertEqual(r['metadata'],dict(policy_version='picker-concurrency-v1',requested='32',effective=32))
        self.assertEqual(r['checks'],['ready']+['incomparable_result']*3)
        self.assertTrue(r['fingerprint_unchanged']);self.assertTrue(r['legacy_unchanged'])

    def test_new_pool_evidence_cannot_be_demoted_to_an_unlabelled_legacy_report(self):
        r=self.php(self.JOB+r'''
        $out=[];foreach(['auto','32']as $pool){$j=job($pool);
          $j['profiles']=[['runs'=>[['request_pool'=>['policy_version'=>'picker-concurrency-v1',
            'requested'=>$pool,'effective'=>$j['budget']['concurrency']]]]]];
          unset($j['concurrency_choice'],$j['concurrency']);
          try{NfqwsStrategyPickerConcurrency::job($j);$out[]='accepted';}
          catch(Throwable $e){$out[]=$e->getMessage();}
        }echo json_encode($out);
        ''')
        self.assertEqual(r,['invalid_request']*2)


if __name__=='__main__':unittest.main()
