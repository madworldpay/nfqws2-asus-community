import json
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC


class ServicePriorityTests(unittest.TestCase):
    def php(self, body):
        fixture = r"""
        function measurement(array $working):array {
            $hosts=array_merge(...array_values(NfqwsStrategyPickerGoals::DOMAINS));
            for($i=0;$i<24;$i++)$hosts[]='secondary'.$i.'.example.com';
            $domains=[];
            foreach($hosts as $host){
                $ok=in_array($host,$working,true);
                $domains[]=['domain'=>$host,'http'=>'failed','tls12'=>$ok?'ok':'failed',
                    'tls13'=>$ok?'ok':'failed','quic'=>'failed'];
            }
            $native=['state'=>'completed','coverage'=>['domains'=>count($domains),'tcp'=>1],
                'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>$domains]]],
                    ['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'control','status'=>'failed']]]]]]];
            return NfqwsStrategyPickerScore::measure($native);
        }
        function candidates():array {
            $primary=array_merge(...array_values(NfqwsStrategyPickerGoals::DOMAINS));
            $secondary=[];for($i=0;$i<24;$i++)$secondary[]='secondary'.$i.'.example.com';
            $focused=NfqwsStrategySynthesis::blank();$focused['tls']=['method'=>'multisplit','pos'=>'1,midsld'];
            $other=NfqwsStrategySynthesis::blank();$other['tls']=['method'=>'multidisorder','pos'=>'host+1'];
            return [$primary,$secondary,$focused,$other];
        }
        """
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [PHP, '-n', '-r', "umask(0077);require $argv[1].'/strategy-synthesis.php';" + fixture + body,
                 str(PUBLIC), folder], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_all_includes_each_priority_service_before_secondary_targets(self):
        result = self.php(r"""
        $stock=['secondary.example.com','youtube.com'];
        echo json_encode(['actual'=>NfqwsStrategyPickerGoals::probeDomains($stock,'all'),
            'primary'=>array_merge(...array_values(NfqwsStrategyPickerGoals::DOMAINS))]);
        """)
        self.assertEqual(result['actual'][:len(result['primary'])], result['primary'])
        self.assertEqual(result['actual'][-1], 'secondary.example.com')
        self.assertEqual(len(result['actual']), len(set(result['actual'])))

    def test_all_assembly_refinement_and_retest_prefer_the_four_services(self):
        result = self.php(r"""
        [$primary,$secondary,$focused,$other]=candidates();$zero=measurement([]);
        $rows=[['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$zero,$zero]],
            ['recipe'=>$focused,'runs'=>[measurement($primary)]],
            ['recipe'=>$other,'runs'=>[measurement($secondary)]]];
        $assembled=NfqwsStrategySynthesis::assemble($rows,'all');
        $retest=NfqwsStrategySynthesis::bestForRetest($rows,'all');
        $refined=NfqwsStrategySynthesis::refine($rows,['max_repeats'=>4],'all');
        echo json_encode(['base'=>$assembled['tls'],'expected'=>$focused['tls'],
            'retested'=>in_array($focused,$retest,true),
            'feedback_preserves_primary'=>count(array_filter($refined,fn($r)=>
                $r['tls']===$focused['tls']&&($r['http']['method']!=='pass'||$r['quic']['method']!=='pass')))>0]);
        """)
        self.assertEqual(result['base'], result['expected'])
        self.assertTrue(result['retested'])
        self.assertTrue(result['feedback_preserves_primary'])

    def test_current_improvement_search_prioritizes_service_gain(self):
        result = self.php(r"""
        [$primary,$secondary,$focused,$other]=candidates();$zero=measurement([]);
        foreach([&$focused,&$other]as &$r){$r['basis']='current';
            $r['overrides']=[['protocol'=>'tls','domains'=>array_merge($primary,$secondary),'component'=>$r['tls']]];
            $r['tls']=['method'=>'pass'];}unset($r);
        $ranked=NfqwsStrategySynthesis::bestImprovements([
            ['recipe'=>$other,'runs'=>[measurement($secondary)]],
            ['recipe'=>$focused,'runs'=>[measurement($primary)]]],['runs'=>[$zero,$zero]],'all',1);
        echo json_encode(['actual'=>$ranked[0]??null,'expected'=>$focused]);
        """)
        self.assertEqual(result['actual'], result['expected'])

    def test_all_does_not_trade_working_instagram_for_secondary_gains(self):
        result = self.php(r"""
        [$primary,$secondary]=candidates();$before=measurement($primary);
        $after=measurement(array_merge(array_values(array_diff($primary,
            NfqwsStrategyPickerGoals::DOMAINS['instagram'])),$secondary));
        echo json_encode(NfqwsStrategyPickerScore::compare([$before,$before],[$after,$after],'all'));
        """)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['reason'], 'goal_regression')

    def test_main_services_keeps_a_whole_repeated_candidate_for_final_verification(self):
        result = self.php(r"""
        function loseTls(array $run,string $host,string $protocol):array {
            $run['domains'][$host][$protocol]=false;
            $run['metrics'][$protocol]['ok']--;
            $service=NfqwsStrategyPickerGoals::service($host);
            if($service!==null)$run['services'][$service][$protocol]['ok']--;
            if($host==='www.youtube.com')$run['youtube'][$protocol]=false;
            return $run;
        }
        [$primary,$secondary,$focused,$other]=candidates();
        $goal='youtube,discord,instagram';$blank=NfqwsStrategySynthesis::blank();
        $full=measurement(array_merge($primary,$secondary));
        $control=['runs'=>[loseTls($full,'www.youtube.com','tls12'),$full]];
        $safeForServices=loseTls($full,$secondary[0],'tls13');
        $discordLoss=loseTls($full,'discord.com','tls13');
        $rows=[['recipe'=>$blank,'runs'=>[$full,$full]],
            ['recipe'=>$other,'runs'=>[$discordLoss,$discordLoss]],
            ['recipe'=>$focused,'runs'=>[$safeForServices,$safeForServices]]];
        $finalists=NfqwsStrategySynthesis::finalists($rows,[],$control,$goal);
        $priorities=method_exists(NfqwsStrategySynthesis::class,'mainServicesCandidate')?
            NfqwsStrategySynthesis::mainServicesCandidate($rows,$control,1):null;
        $scoped=method_exists(NfqwsStrategySynthesis::class,'youtubeScopedCandidate')?
            NfqwsStrategySynthesis::youtubeScopedCandidate($rows,$control):null;
        $rows[2]['runs']=[$safeForServices];
        echo json_encode(['nominated'=>$finalists,'focused'=>$focused,'blank'=>$blank,
            'single'=>NfqwsStrategySynthesis::finalists($rows,[],$control,$goal),
            'discovery'=>$priorities,'scoped'=>$scoped,
            'strict_rank'=>NfqwsStrategySynthesis::improvementCompare($control['runs'],[$safeForServices,$safeForServices],$goal)]);
        """)
        self.assertEqual(result['nominated'], [result['focused']])
        self.assertEqual(result['discovery'], result['focused'])
        self.assertEqual(result['scoped'], result['blank'] | {'overrides': [{
            'protocol': 'tls', 'domains': ['youtube.com', 'www.youtube.com'],
            'component': result['focused']['tls'],
        }]})
        self.assertEqual(result['single'], [])
        self.assertFalse(result['strict_rank']['eligible'])
        self.assertEqual(result['strict_rank']['reason'], 'tls_regression')

    def test_main_services_does_not_scope_youtube_when_the_control_is_already_complete(self):
        result = self.php(r"""
        [$primary,$secondary,$focused]=candidates();$measured=measurement(array_merge($primary,$secondary));
        echo json_encode(NfqwsStrategySynthesis::youtubeScopedCandidate(
            [['recipe'=>$focused,'runs'=>[$measured]]],['runs'=>[$measured,$measured]]));
        """)
        self.assertIsNone(result)

    def test_main_services_prefers_a_rejected_finalist_with_services_intact(self):
        result = self.php(r"""
        [$primary,$secondary,$preserves,$loses]=candidates();
        $preserves['http']=['method'=>'http_methodeol'];
        $rejected=fn($reason)=>['eligible'=>false,'reason'=>$reason,'gain'=>0];
        // Build 112 round 2 had these two rejected outcomes. The variant with
        // aggregate QUIC loss kept all selected services, including YouTube.
        $a=NfqwsStrategySynthesis::finalistPriority($rejected('protocol_regression'),$rejected('tls_regression'),$preserves,true);
        $b=NfqwsStrategySynthesis::finalistPriority($rejected('goal_regression'),$rejected('goal_regression'),$loses,true);
        $oldA=NfqwsStrategySynthesis::finalistPriority($rejected('protocol_regression'),$rejected('tls_regression'),$preserves,false);
        $oldB=NfqwsStrategySynthesis::finalistPriority($rejected('goal_regression'),$rejected('goal_regression'),$loses,false);
        echo json_encode(['summary_preserves_services'=>$a>$b,'other_modes_keep_order'=>$oldA<$oldB,
            'rejected_flags'=>[$a[0],$b[0]]]);
        """)
        self.assertEqual(result, {'summary_preserves_services': True,
                                  'other_modes_keep_order': True, 'rejected_flags': [0, 0]})

    def test_restored_round_winner_gets_a_fresh_finalist_slot(self):
        result = self.php(r"""
        require $argv[1].'/strategy-synthesis-runtime.php';
        [$primary,$secondary]=candidates();
        $goal='youtube,discord,instagram';
        $champion=NfqwsStrategySynthesis::blank();
        $champion['tls']=['method'=>'multisplit','pos'=>'1,midsld'];
        $champion['overrides']=[['protocol'=>'http','domains'=>['youtube.com'],'component'=>['method'=>'http_hostcase']]];
        $key=NfqwsStrategySynthesis::key($champion);
        $store=new NfqwsStrategyPickerState($argv[2].'/series',getmyuid());
        $store->write(['id'=>str_repeat('b',32),'request_id'=>str_repeat('c',32),'rounds'=>2,'goal'=>$goal,
            'profiles'=>[],'skipped'=>[],'budget'=>['small'=>true,'max_repeats'=>4],'deadline'=>null]);
        $worker=new class($store,$goal,$champion,$key,$primary,$secondary){
            use NfqwsStrategySynthesisRuntime { synthesisRound as private realRound; }
            public array $discovery=[];
            public array $final=[];
            public function __construct(private $store,private $goal,private $champion,private $key,private $primary,private $secondary){}
            public function run(){
                try{$this->synthesisWork();}catch(RuntimeException $e){if($e->getMessage()!=='fixture_done')throw $e;}
            }
            private function checkpoint():void{}
            private function assertOriginal():void{}
            private function preflight():void{}
            private function synthesisTime():bool{return true;}
            private function phase(string $phase,array $extra=[]):void{
                $this->store->write(array_replace($this->store->read(),$extra,['phase'=>$phase]));
            }
            private function synthesisRound(?array $previousWinner=null):void{
                if($this->store->read()['series']['current']===2){$this->realRound($previousWinner);return;}
                $recipe='s-'.substr($this->key,0,16);
                $rank=['eligible'=>true,'reason'=>'improved','gain'=>2];
                $score=measurement(array_merge($this->primary,$this->secondary));
                $this->phase('restoring',['restored'=>true,'winner'=>'r1-kit:'.$recipe,'generated'=>'r1-kit:'.$recipe,
                    'profiles'=>[['id'=>'r1-kit','recipe'=>$recipe,'components'=>$this->champion,'source'=>'synthesis',
                        'sample_type'=>'repeated','rank'=>$rank,'runs'=>[$score,$score]]],
                    'matrix'=>['tested'=>24],
                    'synthesis_memory'=>$this->synthesisMemory([$this->champion],null,[$this->key]),
                    'generation'=>['verified'=>true,'from_zero'=>$rank,'versus_current'=>$rank,'versus_stock'=>$rank]]);
            }
            private function library(){return new class{
                public function capture($name){return ['id'=>'r2-original','name'=>$name];}
                public function entry($id){return ['id'=>$id,'config'=>[]];}
                public function stock($template,$packaged){return $this->entry('stock');}
                public function synthesis($scope){return ['id'=>'r2-kit'];}
            };}
            private function synthesisTrial(array $entry,string $name,?array $recipe,int $repeats,bool $warm=false,
                ?callable $onNative=null,?callable $beforeNative=null):array{
                if(str_starts_with($name,'Собранная стратегия')){
                    $this->final=[$entry['id'],$recipe,$repeats,$warm];
                    throw new RuntimeException('fixture_done');
                }
                if($recipe!==null&&$repeats===1)$this->discovery[]=NfqwsStrategySynthesis::key($recipe);
                $ok=$recipe===null||$recipe===NfqwsStrategySynthesis::blank()?[]:array_merge($this->primary,$this->secondary);
                return ['id'=>$entry['id'],'name'=>$name,'source'=>$recipe===null?'current':'synthesis',
                    'recipe'=>$recipe===null?null:'s-'.substr(NfqwsStrategySynthesis::key($recipe),0,16),
                    'components'=>$recipe,'runs'=>array_fill(0,$repeats,measurement($ok))];
            }
        };
        $worker->run();
        echo json_encode(['final'=>$worker->final,'champion'=>$champion,'in_discovery'=>in_array($key,$worker->discovery,true),
            'r1_restored'=>$store->round(1)->read()['restored']]);
        """)
        self.assertEqual(result['final'], ['r2-kit', result['champion'], 2, True])
        self.assertFalse(result['in_discovery'])
        self.assertTrue(result['r1_restored'])

    def test_promoting_a_measured_pair_keeps_its_artifact_and_real_attempts(self):
        result = self.php(r"""
        require $argv[1].'/strategy-synthesis-runtime.php';
        $store=new NfqwsStrategyPickerState($argv[2].'/series',getmyuid());
        $ref=['id'=>str_repeat('a',32)];
        $p=['id'=>'kit','name'=>'Earlier paired measurement','recipe'=>'s-1234','sample_type'=>'repeated',
            'runs'=>[['measurement'=>1],['measurement'=>2]],'measured_reference'=>$ref];
        $earlier=['id'=>'kit','name'=>'Real discovery','recipe'=>'s-1234','runs'=>[['measurement'=>0]]];
        $store->write(['profiles'=>[$earlier],'measured_results'=>[['reference'=>$ref,'document'=>['original'=>'doc']]]]);
        $worker=new class($store){
            use NfqwsStrategySynthesisRuntime;
            public function __construct(private $store){}
            public function record(array $profile,array $rank,bool $promote=false):void{
                $this->synthesisRecord($profile,$rank,$promote);
            }
        };
        $worker->record($p,['eligible'=>false,'reason'=>'retested','gain'=>0]);
        $worker->record($p,['eligible'=>true,'reason'=>'improved','gain'=>2],true);
        $state=$store->read();
        echo json_encode(['name'=>$state['profiles'][0]['name'],'previous'=>array_column($state['profiles'][0]['previous_attempts'],'name'),
            'rank'=>$state['profiles'][0]['rank'],'measurement'=>$state['measured_results']]);
        """)
        self.assertEqual(result['previous'], ['Real discovery'])
        self.assertEqual(result['name'], 'Earlier paired measurement')
        self.assertEqual(result['rank'], {'eligible': True, 'reason': 'improved', 'gain': 2})
        self.assertEqual(len(result['measurement']), 1)
        self.assertEqual(result['measurement'][0]['document'], {'original': 'doc'})
        self.assertEqual(result['measurement'][0]['rank'], result['rank'])

    def test_finalist_reuse_checks_round_config_context_and_auto_bytes(self):
        result = self.php(r"""
        require $argv[1].'/strategy-synthesis-runtime.php';
        $store=new NfqwsStrategyPickerState($argv[2].'/series',getmyuid());
        $id=str_repeat('b',32);
        $binding=['request_id'=>str_repeat('c',32),'resources_sha256'=>str_repeat('d',64)];
        $job=$binding+['id'=>$id,'series'=>['current'=>2]];
        $store->write($job);
        [,, $recipe]=candidates();
        $entry=['id'=>'kit','config'=>['NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/user.list --hostlist-exclude=/tmp/exclude.list']];
        $config=NfqwsStrategySynthesis::bind($recipe,$entry['config']);
        $raw=json_encode($config,JSON_THROW_ON_ERROR);
        $score=['targets'=>str_repeat('e',64),'context_sha256'=>str_repeat('f',64)];
        $profile=['id'=>'kit','name'=>'Paired candidate','sample_type'=>'repeated','variant'=>$config,
            'config_sha256'=>hash('sha256',$raw),'runs'=>[$score,$score]];
        $ref=$store->createMeasuredResult(['job_id'=>$id,'kind'=>'measurement','round'=>2,
            'profile'=>$profile,'native_config_base64'=>base64_encode($raw),'binding'=>$binding]);
        $job['measured_results']=[['id'=>$ref['id'],'reference'=>$ref,'round'=>2,
            'name'=>$profile['name'],'sample_type'=>'repeated','document'=>null]];
        $store->write($job);
        $worker=new class($store){
            use NfqwsStrategySynthesisRuntime;
            public array $auto=['lists/synthesis-auto.list'=>'previous'];
            public function __construct(private $store){}
            private function checkpoint():void{}
            private function assertOriginal():void{}
            private function candidate(array $entry):string{return json_encode($entry['config'],JSON_THROW_ON_ERROR);}
            private function synthesisFinalistAuto(array $entry,array $job):array{return $this->auto;}
            public function read(array $retest,array $entry,array $recipe,array $controls):?array{
                return $this->synthesisReuseFinalist($retest,$entry,$recipe,$controls);
            }
        };
        $saved=$profile+['measured_reference'=>$ref];
        $memo=['profile'=>$saved,'entry'=>$entry,'resources'=>$binding['resources_sha256'],'auto'=>$worker->auto];
        $control=['runs'=>[$score,$score]];
        $same=$worker->read($memo,$entry,$recipe,[$control])===$saved;
        $badContext=$control;$badContext['runs'][0]['context_sha256']=str_repeat('0',64);
        $contextRefused=$worker->read($memo,$entry,$recipe,[$badContext])===null;
        $changed=$recipe;$changed['tls']['pos']='host+1';
        $configRefused=$worker->read($memo,$entry,$changed,[$control])===null;
        $worker->auto['lists/synthesis-auto.list']='changed';
        $autoRefused=$worker->read($memo,$entry,$recipe,[$control])===null;
        $worker->auto=$memo['auto'];
        $job['series']['current']=3;$store->write($job);
        try{$worker->read($memo,$entry,$recipe,[$control]);$oldRound=false;}
        catch(RuntimeException $error){$oldRound=$error->getMessage()==='source_changed';}
        echo json_encode([$same,$contextRefused,$configRefused,$autoRefused,$oldRound]);
        """)
        self.assertEqual(result, [True] * 5)


if __name__ == '__main__':
    unittest.main()
