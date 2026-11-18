import json, os, shlex, shutil, subprocess, tempfile, unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC


class SynthesisTests(unittest.TestCase):
    def php(self, body):
        with tempfile.TemporaryDirectory() as folder:
            r = subprocess.run([PHP, '-n', '-r', "umask(0077);require $argv[1].'/strategy-synthesis.php';" + body,
                                str(PUBLIC), folder], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(r.stderr, '')
        return json.loads(r.stdout)

    def test_expanded_common_primitives_are_reachable_without_a_saved_strategy(self):
        r=self.php(r"""$m=new ReflectionMethod(NfqwsStrategySynthesis::class,'components');$out=[];
        foreach(['http','tls','quic']as $p)$out[$p]=$m->invoke(null,$p,['max_repeats'=>6]);echo json_encode($out);""")
        self.assertIn('http_methodeol',{x['method'] for x in r['http']})
        self.assertIn('syndata',{x['method'] for x in r['http']})
        self.assertIn('syndata',{x['method'] for x in r['tls']})
        self.assertIn('tls_client_hello_clone',{x['method'] for x in r['tls']})
        self.assertIn('send',{x['method'] for x in r['quic']})
        self.assertTrue(any(x.get('host')=='mail.ru' for x in r['http']))
        self.assertTrue(any(x.get('seqovl')==664 for x in r['tls']))
        self.assertTrue(any(x.get('fooling')=='ts1500' for x in r['tls']))
        self.assertTrue({3,5}.issubset({x.get('repeats',1) for x in r['quic']}))
        self.assertTrue(all(x.get('repeats',1)<=6 for rows in r.values() for x in rows))

    def test_available_package_payloads_build_a_valid_independent_queue(self):
        # Actual MAIN stopped before its first candidate when the empty kit
        # supplied all package blobs. A TLS blob had reached http_methodeol.
        r=self.php(r"""$out=[];$ids=array_keys(NfqwsStrategySynthesis::packagedPayloads());
        foreach([[],['tls_google'],['quic_google'],$ids]as $available){
          $budget=['max_repeats'=>6,'synthesis_payloads'=>$available];
          $queue=NfqwsStrategySynthesis::queue($budget);
          foreach($queue as $recipe)NfqwsStrategySynthesis::compile($recipe);
          $out[]=['count'=>count($queue),'protocols'=>array_values(array_unique(array_merge(...array_map(
            fn($r)=>array_keys(array_filter(array_intersect_key($r,array_flip(['http','tls','quic'])),
              fn($c)=>$c!==['method'=>'pass'])),$queue))))];
        }echo json_encode($out);""")
        self.assertEqual([x['count'] for x in r],[24]*4)
        self.assertTrue(all(set(x['protocols'])=={'http','tls','quic'} for x in r))

    def test_later_series_preserves_old_rounds_and_uses_its_own_archives(self):
        # Only device operations and one round's measurements are doubled.
        # The actual series controller/state writer must archive and select
        # two rounds without overwriting a previous series' round-1/round-2.
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',getmyuid());$old=[];
        foreach([1,2]as $n){$part=new NfqwsStrategyPickerState($s->root.'/round-'.$n,getmyuid());
          $s->write(['id'=>str_repeat('a',32)]);$part->write(['id'=>str_repeat('a',32),'old'=>$n]);
          $old[$n]=hash_file('sha256',$part->path('state.json'));}
        $h=new class($s){use NfqwsStrategySynthesisRuntime;
          public function __construct(private $store){}public function run(){$this->synthesisWork();}
          private function checkpoint():void{}private function assertOriginal():void{}private function preflight():void{}
          private function phase(string $p,array $e=[]):void{$this->store->write(array_replace($this->store->read(),$e,['phase'=>$p]));}
          private function synthesisRound():void{$j=$this->store->read();$this->phase('restoring',[
            'restored'=>true,'profiles'=>[],'winner'=>null,'generation'=>['verified'=>true,
            'versus_current'=>['eligible'=>false,'reason'=>'no_improvement','gain'=>0]],
            'generated'=>'round-'.$j['series']['current']]);}
        };
        $jobs=[];foreach(['b','c']as $char){$s->write(['id'=>str_repeat($char,32),'rounds'=>2,'goal'=>'all']);
          $h->run();$jobs[]=$s->read();}
        $unchanged=true;foreach($old as $n=>$sha){$part=new NfqwsStrategyPickerState($s->root.'/round-'.$n,getmyuid());
          $unchanged=$unchanged&&hash_file('sha256',$part->path('state.json'))===$sha;}
        echo json_encode(['jobs'=>$jobs,'old_unchanged'=>$unchanged]);""")
        self.assertTrue(r['old_unchanged'])
        for job in r['jobs']:
            self.assertEqual(job['series']['completed'],2)
            self.assertEqual(job['series']['selected'],1)
            self.assertEqual(job['generated'],'round-1')

    def test_optional_packaged_payloads_are_bound_to_the_fresh_empty_kit(self):
        r=self.php(r"""$base=['NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/user.list --hostlist-exclude=/tmp/exclude.list',
        'NFQWS_BASE_ARGS'=>'--blob=synthesis_tls_iana:@/tmp/owned/blobs/tls_clienthello_iana_org.bin'];
        $r=NfqwsStrategySynthesis::blank();$r['tls']=['method'=>'fake','payload'=>'tls_iana','tls_mod'=>'google','repeats'=>2];
        $bound=NfqwsStrategySynthesis::bind($r,$base);$base['NFQWS_BASE_ARGS']='';
        try{NfqwsStrategySynthesis::bind($r,$base);$missing='accepted';}catch(Throwable $e){$missing=$e->getMessage();}
        echo json_encode([$bound,$missing,NfqwsStrategySynthesis::availablePayloads($base)]);""")
        self.assertIn('blob=synthesis_tls_iana',r[0]['NFQWS_ARGS'])
        self.assertIn('tls_mod=rnd,dupsid,sni=www.google.com',r[0]['NFQWS_ARGS'])
        self.assertEqual(r[1],'synthesis_payload_unavailable')
        self.assertEqual(r[2],[])

    def test_compiled_packet_local_clone_exports_without_a_phantom_external_blob(self):
        # Real compiler/export/import. These fixture Lua bytes are not run;
        # native syntax and real package-byte checks are separate tests.
        r=self.php(r"""require $argv[1].'/strategy-picker-runtime.php';$root=$argv[2];$hashes=[];
        foreach(['lists','lua','blobs']as $kind)mkdir($root.'/'.$kind);
        foreach(['lua/zapret-lib.lua'=>'fixture lib','lua/zapret-antidpi.lua'=>'fixture antidpi',
          'lists/synthesis-user.list'=>"youtube.com\n",'lists/synthesis-auto.list'=>'','lists/synthesis-exclude.list'=>"t.me\n"]as $name=>$raw){
          file_put_contents($root.'/'.$name,$raw);chmod($root.'/'.$name,0644);$hashes[$name]=hash('sha256',$raw);}
        $base=['NFQWS_BASE_ARGS'=>'--lua-init=@'.$root.'/lua/zapret-lib.lua --lua-init=@'.$root.'/lua/zapret-antidpi.lua',
          'NFQWS_EXTRA_ARGS'=>'--hostlist='.$root.'/lists/synthesis-user.list --hostlist-auto='.$root.'/lists/synthesis-auto.list --hostlist-exclude='.$root.'/lists/synthesis-exclude.list',
          'NFQWS_ARGS_IPSET'=>'','TCP_PORTS'=>'80,443','UDP_PORTS'=>'443'];
        $recipe=NfqwsStrategySynthesis::blank();$recipe['tls']=['method'=>'tls_client_hello_clone','fooling'=>'seq','repeats'=>2];
        $entry=['files'=>$hashes,'mutable_files'=>['lists/synthesis-auto.list'],'config'=>NfqwsStrategySynthesis::bind($recipe,$base),'synthesis_recipe'=>$recipe];
        $seed=NfqwsStrategyPickerResources::snapshotMutable($entry,$root,getmyuid());$bundle=NfqwsStrategySynthesisExport::bundle($entry,$root,$seed,getmyuid());
        $doc=AsusImportDocument::read([$bundle['raw']]);echo json_encode([$doc['dependencies'],$doc['values']['NFQWS_ARGS']]);""")
        self.assertTrue(r[0])
        self.assertTrue(all(x['included'] for x in r[0]))
        self.assertIn('--lua-desync=tls_client_hello_clone:',r[1])

    @unittest.skipUnless(os.environ.get('NFQWS_TEST_ENGINE_DIR'),'Requires pinned MAIN engine')
    def test_expanded_family_programs_parse_in_actual_MAIN_engine(self):
        # Real compiler and selected MAIN binary; no service or network input.
        programs=self.php(r"""$m=new ReflectionMethod(NfqwsStrategySynthesis::class,'components');$out=[];
        foreach(['http','tls','quic']as $p)foreach($m->invoke(null,$p,['max_repeats'=>6])as $c){
          $r=NfqwsStrategySynthesis::blank();$r[$p]=$c;$out[]=NfqwsStrategySynthesis::compile($r);}
        echo json_encode($out);""")
        self.assertTrue(any('--lua-desync=syndata' in x['NFQWS_ARGS'] for x in programs))
        root=Path(os.environ['NFQWS_TEST_ENGINE_DIR'])
        prefix=[str(Path(os.environ['NFQWS_TEST_QEMU_DIR'])/'qemu-aarch64'),str(root/'nfqws2-aarch64')]
        for i,program in enumerate(programs):
            args=' --new '.join(program[k] for k in ['NFQWS_ARGS','NFQWS_ARGS_QUIC'])
            result=subprocess.run(prefix+['--qnum=0','--dry-run','--ipcache-hostname',
                '--lua-init=@'+str(root/'lua/zapret-lib.lua'),'--lua-init=@'+str(root/'lua/zapret-antidpi.lua'),
                *shlex.split(args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,str(i)+result.stdout+result.stderr)

    def test_preselected_round_count_binds_plan_retry_and_preserves_single_run_identity(self):
        r=self.php(r"""require $argv[1].'/strategy-picker-runtime.php';$out=[];
        try{$one=NfqwsStrategyPickerRequest::selection(false,'all',true,null,'100000','1');
          $three=NfqwsStrategyPickerRequest::selection(false,'all',true,null,'100000','3');
          $old=$three+['request_id'=>str_repeat('a',32)];
          try{NfqwsStrategyPickerRequest::retry($old,str_repeat('a',32),$one);$retry='accepted';}catch(Throwable $e){$retry=$e->getMessage();}
          $out=['one'=>$one,'three'=>$three,'different'=>NfqwsStrategyPickerRequest::digest($one)!==NfqwsStrategyPickerRequest::digest($three),'retry'=>$retry];
          foreach(['0','01','11','2.0',2]as $n){try{NfqwsStrategyPickerRequest::selection(false,'all',true,null,'100000',$n);$out['invalid'][]='accepted';}catch(Throwable $e){$out['invalid'][]=$e->getMessage();}}
        }catch(Throwable $e){$out=['error'=>$e->getMessage()];}echo json_encode($out);""")
        self.assertNotIn('error',r)
        self.assertNotIn('rounds',r['one'])
        self.assertEqual(r['three']['rounds'],3)
        self.assertTrue(r['different'])
        self.assertEqual(r['retry'],'request_conflict')
        self.assertEqual(r['invalid'],['invalid_request']*5)

    def test_runtime_accepts_all_ten_targets_already_admitted_by_the_request(self):
        r=self.php(r"""require $argv[1].'/strategy-picker-runtime.php';$r=new NfqwsStrategyPickerRuntime();$m=new ReflectionMethod($r,'synthesisCustom');$out=[];
        foreach([10,11]as $count){$hosts=[];for($i=0;$i<$count;$i++)$hosts[]='host'.$i.'.example.com';sort($hosts);
          try{$out[]=$m->invoke($r,['custom_hosts'=>$hosts,'custom_only'=>false]);}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,[True,'invalid_request'])

    def test_current_basis_trial_preserves_working_protocols_and_old_rule_suffix(self):
        # Break caught: rebuilding all blocks from blank destroys the measured
        # original HTTP/QUIC while testing one scoped TLS improvement.
        r = self.php(r"""$base=[
          'NFQWS_BASE_ARGS'=>'--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua',
          'NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/user.list --hostlist-auto=/tmp/auto.list --hostlist-exclude=/tmp/exclude.list',
          'NFQWS_ARGS'=>'--filter-tcp=80,443 --lua-desync=hostfakesplit:host=original.example',
          'NFQWS_ARGS_QUIC'=>'--filter-udp=443 --lua-desync=fake:repeats=10',
          'NFQWS_ARGS_UDP'=>'--filter-udp=3478 --lua-desync=fake:repeats=6',
          'NFQWS_ARGS_CUSTOM'=>'--filter-tcp=443 --hostlist-domains=working.example --lua-desync=multisplit:pos=2',
          'NFQWS_ARGS_IPSET'=>'--ipset=/tmp/original.list','TCP_PORTS'=>'80,443','UDP_PORTS'=>'443,3478'];
        $recipe=NfqwsStrategySynthesis::blank();$recipe['basis']='current';
        $recipe['overrides']=[['protocol'=>'tls','domains'=>['failed.example'],
          'component'=>['method'=>'multisplit','pos'=>'midsld']]];
        try{$out=NfqwsStrategySynthesis::bind($recipe,$base);echo json_encode(['out'=>$out,'base'=>$base]);}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}""")
        self.assertNotIn('error', r)
        for key, value in r['base'].items():
            if key != 'NFQWS_ARGS_CUSTOM':
                self.assertEqual(r['out'][key], value, key)
        added, suffix = r['out']['NFQWS_ARGS_CUSTOM'].split(' --new ', 1)
        self.assertEqual(suffix, r['base']['NFQWS_ARGS_CUSTOM'])
        self.assertIn('--filter-tcp=443 --filter-l7=tls', added)
        self.assertIn('--hostlist-domains=failed.example', added)
        self.assertIn('--hostlist-exclude=/tmp/exclude.list', added)
        self.assertIn('--hostlist-exclude-domains=t.me,telegram.org,telegram.me,telesco.pe', added)
        self.assertNotIn('--filter-tcp=80 ', added)
        self.assertNotIn('--filter-udp=', added)

    def test_saturated_coverage_does_not_starve_http_or_quic(self):
        # Real completed-round method memory: a global novelty sort fills the
        # next queue with TLS and drops every HTTP trial.
        memory=json.loads((Path(__file__).parent/'fixtures/synthesis-saturated-method-memory.json').read_text())
        payload=json.dumps(json.dumps(memory,separators=(',',':')))
        r=self.php('$m=json_decode('+payload+",true);echo json_encode(NfqwsStrategySynthesis::queue(['max_repeats'=>6],$m['recipes'],$m['explored']));")
        self.assertEqual(len(r),24)
        for protocol in ['http','tls','quic']:
            distinct={json.dumps(x[protocol],sort_keys=True) for x in r if x[protocol]!={'method':'pass'}}
            self.assertGreaterEqual(len(distinct),4,protocol)
        # Fresh method families may displace a previously measured exact recipe.
        # Protocol coverage must retain method diversity, not one fixed seed.
        self.assertGreaterEqual(len({x['http']['method'] for x in r if x['http']['method']!='pass'}),3)

    def test_feedback_can_explore_http_without_discarding_measured_tls(self):
        # Break caught: feedback changes only TLS/QUIC even when HTTP is weak.
        r=self.php(r"""$s=['targets'=>'same','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>1]),
          'domains'=>['www.youtube.com'=>array_fill_keys(['http','tls12','tls13','quic'],false)]];
        $tls=NfqwsStrategySynthesis::blank();$tls['tls']=['method'=>'multisplit','pos'=>'midsld'];$a=$s;
        foreach(['tls12','tls13']as $p){$a['metrics'][$p]['ok']=1;$a['domains']['www.youtube.com'][$p]=true;}
        echo json_encode(NfqwsStrategySynthesis::refine([['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$s,$s]],
          ['recipe'=>$tls,'runs'=>[$a]]],['max_repeats'=>6]));""")
        http=[x for x in r if x['http']!={'method':'pass'}]
        self.assertTrue(http)
        self.assertTrue(all(x['tls']=={'method':'multisplit','pos':'midsld'} for x in http))

    def test_http_search_includes_host_split_timestamp_family(self):
        r=self.php("echo json_encode(NfqwsStrategySynthesis::queue(['max_repeats'=>6]));")
        self.assertTrue(any(x['http']['method']=='hostfakesplit' and x['http'].get('fooling')=='ts' for x in r))

    def test_runtime_uses_observation_feedback_before_search_budget_is_exhausted(self):
        # External service/Detector are doubles; queue, memory and refinement
        # execute real code. No actual device or acceptance flag is inferred.
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());
        $s->write(['id'=>str_repeat('b',32),'goal'=>'all','profiles'=>[],'skipped'=>[],
          'budget'=>['max_repeats'=>6,'small'=>false,'busy'=>false]]);
        $h=new class($s){use NfqwsStrategySynthesisRuntime;public array $measured=[];
          public function __construct(private $store){}
          public function run(){try{$this->synthesisRound();}catch(Throwable $e){if($e->getMessage()!=='cancelled')throw $e;}}
          private function synthesisAdmission():void{}
          private function checkpoint():void{}
          private function synthesisTime():bool{return true;}
          private function phase(string $phase,array $extra=[]):void{$this->store->write(array_replace($this->store->read(),$extra,['phase'=>$phase]));}
          private function library(){return new class{public function capture($name){return ['id'=>'original','name'=>$name];}public function entry($id){return ['id'=>$id];}public function synthesis($scope){return ['id'=>'fresh'];}};}
          private function synthesisTrial(array $entry,string $name,?array $recipe,int $repeats,bool $warm=false,?callable $onNative=null,?callable $beforeNative=null):array{
            if(str_starts_with($name,'Вариант обхода')){$this->measured[]=$recipe;if(count($this->measured)===13)throw new RuntimeException('cancelled');}
            $run=['targets'=>'same','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>1]),
              'domains'=>['www.youtube.com'=>array_fill_keys(['http','tls12','tls13','quic'],false)]];
            foreach(['http','tls','quic']as $p)if($recipe!==null&&$recipe[$p]!==['method'=>'pass'])foreach($p==='tls'?['tls12','tls13']:[$p]as $column){$run['metrics'][$column]['ok']=1;$run['domains']['www.youtube.com'][$column]=true;}
            return ['id'=>$entry['id'],'name'=>$name,'source'=>$recipe===null?'current':'synthesis','recipe'=>$recipe===null?null:'s-'.substr(NfqwsStrategySynthesis::key($recipe),0,16),'components'=>$recipe,'runs'=>array_fill(0,$repeats,$run)];
          }};$h->run();echo json_encode($h->measured);""")
        self.assertEqual(len(r),13)
        self.assertGreaterEqual(sum(r[-1][p]!={'method':'pass'} for p in ['http','tls','quic']),2)

    def feedback_case(self, archived=False):
        # Real scheduler/refinement and state writer. Only external library,
        # service and Detector observations are fixtures, never actual quality.
        code=r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $score=static function($recipe){$r=['targets'=>'same','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>1]),
          'domains'=>['www.youtube.com'=>array_fill_keys(['http','tls12','tls13','quic'],false)]];
          foreach(['http','tls','quic']as $p)if($recipe[$p]!==['method'=>'pass'])foreach($p==='tls'?['tls12','tls13']:[$p]as $column){$r['metrics'][$column]['ok']=1;$r['domains']['www.youtube.com'][$column]=true;}return $r;};
        $b=['max_repeats'=>6,'synthesis_payloads'=>[]];$blank=NfqwsStrategySynthesis::blank();
        $observations=[['recipe'=>$blank,'runs'=>[$score($blank),$score($blank)]]];
        foreach(array_slice(NfqwsStrategySynthesis::queue($b),0,12)as $recipe)$observations[]=['recipe'=>$recipe,'runs'=>[$score($recipe)]];
        $prior=NfqwsStrategySynthesis::refine($observations,$b)[0];$key=NfqwsStrategySynthesis::key($prior);
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());
        $s->write(['id'=>str_repeat('b',32),'goal'=>'all','profiles'=>[],'skipped'=>[],'budget'=>['max_repeats'=>6,'small'=>false],
          'synthesis_memory'=>['version'=>'picker-recipe-memory-v1','knowledge_version'=>NfqwsStrategySynthesis::VERSION,
            'scope'=>['goal'=>'all','custom_hosts'=>[],'custom_only'=>false],'recipes'=>[],'explored'=>[$key]]]);
        if(ARCHIVED_CONTEXT){
          $j=$s->read();$old=$j['synthesis_memory'];$j['rounds']=3;
          $j['series']=['archive_version'=>2,'total'=>3,'current'=>3,'completed'=>2,'selected'=>null,'runs'=>[]];
          $j['synthesis_memory']['explored']=array_map(fn($n)=>hash('sha256','newer-'.$n),range(1,64));$s->write($j);
          foreach([1,2]as $number)$s->round($number)->write(['id'=>$j['id'],'state'=>'completed','restored'=>true,
            'series_round'=>$number,'goal'=>'all','synthesis_memory'=>$number===1?$old:$j['synthesis_memory']]);
        }
        $h=new class($s,$score){use NfqwsStrategySynthesisRuntime;public array $measured=[];
          public function __construct(private $store,private $score){}
          public function run(){try{$this->synthesisRound();}catch(Throwable $e){if($e->getMessage()!=='cancelled')throw $e;}}
          private function synthesisAdmission():void{}private function checkpoint():void{}
          private function synthesisTime():bool{return true;}
          private function phase(string $p,array $e=[]):void{$this->store->write(array_replace($this->store->read(),$e,['phase'=>$p]));}
          private function library(){return new class{public function capture($name){return ['id'=>'original','name'=>$name];}public function entry($id){return ['id'=>$id];}public function synthesis($scope){return ['id'=>'fresh'];}};}
          private function synthesisTrial(array $entry,string $name,?array $recipe,int $repeats,bool $warm=false,?callable $onNative=null,?callable $beforeNative=null):array{
            if(str_starts_with($name,'Вариант обхода')){$this->measured[]=NfqwsStrategySynthesis::key($recipe);if(count($this->measured)===13)throw new RuntimeException('cancelled');}
            return ['id'=>$entry['id'],'name'=>$name,'source'=>$recipe===null?'current':'synthesis',
              'recipe'=>$recipe===null?null:'s-'.substr(NfqwsStrategySynthesis::key($recipe),0,16),
              'components'=>$recipe,'runs'=>array_fill(0,$repeats,($this->score)($recipe??NfqwsStrategySynthesis::blank()))];
          }};$h->run();echo json_encode(['prior'=>$key,'measured'=>$h->measured]);"""
        return self.php(code.replace('ARCHIVED_CONTEXT','true' if archived else 'false'))

    def test_feedback_does_not_reintroduce_a_program_measured_in_a_previous_round(self):
        r=self.feedback_case()
        self.assertEqual(len(r['measured']),13)
        self.assertNotIn(r['prior'],r['measured'])
        self.assertEqual(len(set(r['measured'])),13)

    def test_series_archives_keep_duplicates_excluded_after_the_64_key_memory_rolls(self):
        r=self.feedback_case(archived=True)
        self.assertEqual(len(r['measured']),13)
        self.assertNotIn(r['prior'],r['measured'])
        self.assertEqual(len(set(r['measured'])),13)

    def test_search_queue_keeps_a_leader_and_reserves_single_protocol_exploration(self):
        # Break caught: eight old leaders plus the same mixed seeds consume
        # the next round without isolating effects or exploring new families.
        r = self.php(r"""$b=['max_repeats'=>6];$h=array_slice(NfqwsStrategySynthesis::matrix($b)['initial'],0,8);
        $q=NfqwsStrategySynthesis::queue($b,$h);
        $next=NfqwsStrategySynthesis::queue($b,$h,array_map([NfqwsStrategySynthesis::class,'key'],$q));
        echo json_encode(['queue'=>$q,'history'=>$h,'next'=>$next]);""")
        self.assertEqual(len(r['queue']), 24)
        self.assertEqual(r['queue'][0], r['history'][0])
        fresh = [x for x in r['queue'] if x not in r['history']]
        self.assertGreaterEqual(len(fresh), 16)
        for recipe in fresh:
            self.assertEqual(sum(recipe[p] != {'method': 'pass'} for p in ['http', 'tls', 'quic']), 1)
        self.assertTrue(any(x['tls']['method'] == 'fake' for x in fresh))
        self.assertGreaterEqual(len({x['tls']['method'] for x in fresh if x['tls']['method']!='pass'}),2)
        self.assertTrue(any(x['tls']['method'] == 'fakeddisorder' for x in fresh+r['next']))
        self.assertTrue(any(x['http']['method'] == 'http_methodeol' for x in fresh))

    def test_search_queue_uses_prior_coverage_to_expand_the_next_round(self):
        # Break caught: replaying the same fixed initial seeds every round.
        r = self.php(r"""$b=['max_repeats'=>6];$has=method_exists(NfqwsStrategySynthesis::class,'queue');
        $a=$has?NfqwsStrategySynthesis::queue($b):NfqwsStrategySynthesis::matrix($b)['initial'];
        $seen=array_map([NfqwsStrategySynthesis::class,'key'],$a);
        $z=$has?NfqwsStrategySynthesis::queue($b,[],$seen):NfqwsStrategySynthesis::matrix($b)['initial'];
        echo json_encode(['a'=>$seen,'next'=>array_map([NfqwsStrategySynthesis::class,'key'],$z)]);""")
        self.assertEqual(len(set(r['next'])), 24)
        self.assertGreaterEqual(len(set(r['next']) - set(r['a'])), 12)

    def test_next_search_queue_excludes_measured_programs_including_retained_leaders(self):
        # Previously old programs only moved behind fresh ones, while retained
        # leaders were inserted first. They still spent the next search budget.
        r=self.php(r"""$b=['max_repeats'=>6,'synthesis_payloads'=>array_keys(NfqwsStrategySynthesis::packagedPayloads())];
        $first=NfqwsStrategySynthesis::queue($b);$old=array_map([NfqwsStrategySynthesis::class,'key'],$first);
        $next=NfqwsStrategySynthesis::queue($b,array_slice($first,0,4),$old);
        echo json_encode(['old'=>$old,'next'=>array_map([NfqwsStrategySynthesis::class,'key'],$next)]);""")
        self.assertTrue(r['next'])
        self.assertLessEqual(len(r['next']),24)
        self.assertEqual(len(r['next']),len(set(r['next'])))
        self.assertFalse(set(r['old']) & set(r['next']))

    def test_current_basis_search_targets_only_failed_protocol_cells(self):
        # Break caught: a TLS failure must not replace working HTTP/QUIC or
        # create an override for a destination that already passed both runs.
        r = self.php(r"""$ok=['http'=>true,'tls12'=>true,'tls13'=>true,'quic'=>true];
        $bad=$ok;$bad['tls13']=false;$s=['targets'=>'same','domains'=>[
          'working.example'=>$ok,'failed.example'=>$bad]];$control=['runs'=>[$s,$s]];
        $q=method_exists(NfqwsStrategySynthesis::class,'queue')?
          NfqwsStrategySynthesis::queue(['max_repeats'=>6],[],[],$control):
          NfqwsStrategySynthesis::matrix(['max_repeats'=>6])['initial'];
        echo json_encode(array_values(array_filter($q,fn($x)=>($x['basis']??null)==='current')));""")
        self.assertGreaterEqual(len(r), 3)
        for recipe in r:
            self.assertEqual(len(recipe['overrides']), 1)
            self.assertEqual(recipe['overrides'][0]['protocol'], 'tls')
            self.assertEqual(recipe['overrides'][0]['domains'], ['failed.example'])

    def test_current_basis_quality_cannot_trade_working_http_for_tls_gain(self):
        # Break caught: a positive total score can hide a lost working protocol.
        r = self.php(r"""$m=array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>2,'total'=>3]);
        $a=['targets'=>'same','metrics'=>$m,'youtube'=>array_fill_keys(['http','tls12','tls13','quic'],true)];
        $b=$a;$b['metrics']['http']['ok']=1;$b['metrics']['tls12']['ok']=3;$b['metrics']['tls13']['ok']=3;
        $c=method_exists(NfqwsStrategySynthesis::class,'improvementCompare')?
          NfqwsStrategySynthesis::improvementCompare([$a,$a],[$b,$b]):
          NfqwsStrategyPickerScore::compare([$a,$a],[$b,$b]);echo json_encode($c);""")
        self.assertFalse(r['eligible'])
        self.assertEqual(r['reason'], 'protocol_regression')

    def test_current_basis_memory_keeps_method_without_old_base_or_destination(self):
        # Break caught: a protected recipe cannot carry an old base/host into
        # a new trial, and must not lose the useful method when scope is stripped.
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());$s->write(['goal'=>'all']);
        $r=NfqwsStrategySynthesis::blank();$r['basis']='current';$r['overrides']=[
          ['protocol'=>'tls','domains'=>['previous.example'],'component'=>['method'=>'fakeddisorder','pos'=>'midsld','fooling'=>'seq']]];
        $h=new class($s){use NfqwsStrategySynthesisRuntime;public function __construct(private $store){}
          public function remember($r){return $this->synthesisMemory([$r]);}};
        echo json_encode($h->remember($r));""")
        self.assertEqual(len(r['recipes']), 1)
        self.assertEqual(r['recipes'][0]['tls'], {'method':'fakeddisorder','pos':'midsld','fooling':'seq'})
        self.assertNotIn('basis', r['recipes'][0])
        self.assertEqual(r['recipes'][0]['overrides'], [])

    def test_restored_history_keeps_bounded_search_coverage_without_score_authority(self):
        # Break caught: every next round forgets tested branches and replays
        # the same seeds even though the archived attempt was restored.
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());$s->write(['goal'=>'all']);
        $recipe=NfqwsStrategySynthesis::blank();$recipe['tls']=['method'=>'fakeddisorder','pos'=>'midsld','fooling'=>'seq'];
        $key=NfqwsStrategySynthesis::key($recipe);$id=str_repeat('a',32);$old=new NfqwsStrategyPickerState($s->root.'/job-'.$id,(int)getmyuid());
        $old->write(['id'=>$id,'goal'=>'all','state'=>'failed','restored'=>true,'search'=>'synthesis','profiles'=>[],
          'synthesis_memory'=>['version'=>'picker-recipe-memory-v1','knowledge_version'=>NfqwsStrategySynthesis::VERSION,
          'scope'=>['goal'=>'all','custom_hosts'=>[],'custom_only'=>false],'recipes'=>[$recipe],'explored'=>[$key]]]);
        $before=hash_file('sha256',$old->path('state.json'));
        $h=new class($s){use NfqwsStrategySynthesisRuntime;public function __construct(private $store){}
          public function collect(){$r=$this->synthesisHistoryRecipes('all');return ['recipes'=>$r,'explored'=>$this->synthesisExplored??[]];}};
        echo json_encode($h->collect()+['key'=>$key,'original_unchanged'=>hash_file('sha256',$old->path('state.json'))===$before]);""")
        self.assertEqual(r['explored'], [r['key']])
        self.assertEqual(len(r['recipes']), 1)
        self.assertTrue(r['original_unchanged'])

    def test_improvement_retest_selection_prefers_no_loss_and_distinct_protocols(self):
        # Break caught: a large TLS gain can promote an HTTP regression, or
        # several similar TLS candidates can exclude the useful HTTP candidate.
        r=self.php(r"""$s=['targets'=>'same','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>2,'total'=>3]),
          'youtube'=>array_fill_keys(['http','tls12','tls13','quic'],true),'domains'=>[]];$control=['runs'=>[$s,$s]];
        $recipes=[];foreach([['tls','multisplit'],['tls','fakeddisorder'],['http','http_methodeol']]as [$p,$method]){
          $r=NfqwsStrategySynthesis::blank();$r['basis']='current';$c=['method'=>$method];
          if($p==='tls')$c+=['pos'=>'midsld'];$r['overrides']=[['protocol'=>$p,'domains'=>['failed.example'],'component'=>$c]];$recipes[]=$r;}
        $bad=$s;$bad['metrics']['http']['ok']=1;$bad['metrics']['tls12']['ok']=3;$bad['metrics']['tls13']['ok']=3;
        $tls=$s;$tls['metrics']['tls13']['ok']=3;$http=$s;$http['metrics']['http']['ok']=3;
        $rows=[['recipe'=>$recipes[0],'runs'=>[$bad]],['recipe'=>$recipes[1],'runs'=>[$tls]],['recipe'=>$recipes[2],'runs'=>[$http]]];
        $q=method_exists(NfqwsStrategySynthesis::class,'bestImprovements')?
          NfqwsStrategySynthesis::bestImprovements($rows,$control,'all',2):NfqwsStrategySynthesis::bestForRetest($rows,'all',false,2);
        echo json_encode($q);""")
        self.assertEqual(len(r), 2)
        self.assertEqual({x.get('basis') for x in r}, {'current'})
        self.assertEqual({x['overrides'][0]['component']['method'] for x in r}, {'fakeddisorder','http_methodeol'})

    def test_runtime_measures_new_candidates_using_empty_entry(self):
        # Network/service operations alone are doubled; the actual trait,
        # scheduler, state writer and recipe validation choose the entry.
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());
        $s->write(['id'=>str_repeat('b',32),'goal'=>'all','profiles'=>[],'skipped'=>[],
          'budget'=>['small'=>false,'max_repeats'=>6],'deadline'=>null]);
        $h=new class($s){use NfqwsStrategySynthesisRuntime;public array $trials=[];
          public function __construct(private $store){}
          public function run(){try{$this->synthesisWork();}catch(Throwable $e){if($e->getMessage()!=='cancelled')throw $e;}}
          private function synthesisAdmission():void{}private function checkpoint():void{}
          private function restore():void{}
          private function synthesisTime():bool{return true;}
          private function phase(string $p,array $e=[]):void{$this->store->write(array_replace($this->store->read(),$e,['phase'=>$p]));}
          private function library(){return new class{
            public function capture($n){return ['id'=>'captured-original','name'=>$n];}
            public function entry($id){return ['id'=>$id];}
            public function synthesis($scope){return ['id'=>'empty-infrastructure'];}};}
          private function synthesisTrial(array $entry,string $name,?array $recipe,int $repeats,bool $warm=false,?callable $onNative=null,?callable $beforeNative=null):array{
            if($recipe!==null&&$recipe!==NfqwsStrategySynthesis::blank()){
              $this->trials[]=['entry'=>$entry['id'],'recipe'=>$recipe];if(count($this->trials)>=24)throw new RuntimeException('cancelled');}
            $ok=['http'=>true,'tls12'=>true,'tls13'=>true,'quic'=>true];$bad=$ok;$bad['tls13']=false;
            $run=['targets'=>'fresh','domains'=>['working.example'=>$ok,'failed.example'=>$bad],
              'youtube'=>$ok,'metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>2,'total'=>3])];
            return ['id'=>$entry['id'],'recipe'=>$recipe===null?'control':NfqwsStrategySynthesis::key($recipe),
              'components'=>$recipe,'runs'=>array_fill(0,$repeats,$run)];
          }};$h->run();echo json_encode($h->trials);""")
        self.assertEqual(len(r), 24)
        protected = [x for x in r if x['recipe'].get('basis') == 'current']
        self.assertEqual(protected, [])
        self.assertTrue(all(x['entry'] == 'empty-infrastructure' for x in r))

    def test_finalists_combine_only_repeated_nonregressing_current_improvements(self):
        # Break caught: mixing current-basis observations into the empty-base
        # assembler loses the original; one-pass results cannot seed a finalist.
        r=self.php(r"""$s=['targets'=>'same','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>2,'total'=>3]),
          'youtube'=>array_fill_keys(['http','tls12','tls13','quic'],true),'domains'=>[]];$control=['runs'=>[$s,$s]];
        $rows=[];foreach([['tls','fakeddisorder','tls13'],['http','http_methodeol','http']]as [$p,$method,$column]){
          $recipe=NfqwsStrategySynthesis::blank();$recipe['basis']='current';$c=['method'=>$method];if($p==='tls')$c['pos']='midsld';
          $recipe['overrides']=[['protocol'=>$p,'domains'=>['failed.example'],'component'=>$c]];$v=$s;$v['metrics'][$column]['ok']=3;
          $rows[]=['recipe'=>$recipe,'runs'=>[$v,$v]];}
        $zero=$s;foreach($zero['metrics']as &$m)$m['ok']=0;unset($m);$independent=[['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$zero,$zero]]];
        $has=method_exists(NfqwsStrategySynthesis::class,'finalists');
        $q=$has?NfqwsStrategySynthesis::finalists($independent,$rows,$control):[NfqwsStrategySynthesis::assemble($independent)];
        foreach($rows as &$row)$row['runs']=array_slice($row['runs'],0,1);unset($row);
        $single=$has?NfqwsStrategySynthesis::finalists($independent,$rows,$control):$q;
        echo json_encode(['finalists'=>$q,'single'=>$single]);""")
        self.assertEqual(r['finalists'][0].get('basis'), 'current')
        self.assertEqual({x['protocol'] for x in r['finalists'][0]['overrides']}, {'http', 'tls'})
        self.assertTrue(all(x.get('basis') != 'current' for x in r['single']))

    def test_runtime_retests_independent_leaders_and_keeps_empty_basis_in_final(self):
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());
        $s->write(['id'=>str_repeat('b',32),'goal'=>'all','profiles'=>[],'skipped'=>[],
          'budget'=>['small'=>false,'max_repeats'=>6],'deadline'=>null]);
        $h=new class($s){use NfqwsStrategySynthesisRuntime;public array $retested=[];public $final=null;
          public function __construct(private $store){}
          public function run(){try{$this->synthesisWork();}catch(Throwable $e){if($e->getMessage()!=='cancelled')throw $e;}}
          private function synthesisAdmission():void{}private function checkpoint():void{}private function restore():void{}
          private function synthesisTime():bool{return true;}
          private function phase(string $p,array $e=[]):void{$this->store->write(array_replace($this->store->read(),$e,['phase'=>$p]));}
          private function library(){return new class{
            public function capture($n){return ['id'=>'captured-original','name'=>$n];}
            public function entry($id){return ['id'=>$id];}
            public function synthesis($scope){return ['id'=>'empty-infrastructure'];}};}
          private function synthesisTrial(array $entry,string $name,?array $recipe,int $repeats,bool $warm=false,?callable $onNative=null,?callable $beforeNative=null):array{
            if(str_starts_with($name,'Собранная стратегия')){$this->final=['entry'=>$entry['id'],'recipe'=>$recipe];throw new RuntimeException('cancelled');}
            if($recipe!==null&&$repeats===2&&$recipe!==NfqwsStrategySynthesis::blank())$this->retested[]=$recipe;
            $ok=['http'=>true,'tls12'=>true,'tls13'=>true,'quic'=>true];$bad=$ok;$bad['tls13']=false;
            $metrics=array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>2,'total'=>3]);
            if($recipe!==null){
              foreach($metrics as &$v)$v['ok']=($recipe['basis']??null)==='current'?2:1;unset($v);
              $metrics['tls13']['ok']=3;
              if($recipe===NfqwsStrategySynthesis::blank()){foreach($metrics as &$v)$v['ok']=0;unset($v);}
            }
            $run=['targets'=>'fresh','domains'=>['working.example'=>$ok,'failed.example'=>$bad],
              'youtube'=>$ok,'metrics'=>$metrics];
            return ['id'=>$entry['id'],'recipe'=>$recipe===null?'control':'s-'.substr(NfqwsStrategySynthesis::key($recipe),0,16),
              'components'=>$recipe,'runs'=>array_fill(0,$repeats,$run)];
          }};$h->run();echo json_encode(['retested'=>$h->retested,'final'=>$h->final]);""")
        self.assertGreaterEqual(len(r['retested']), 1)
        self.assertTrue(all(x.get('basis') != 'current' for x in r['retested']))
        self.assertEqual(r['final']['entry'], 'empty-infrastructure')
        self.assertNotEqual(r['final']['recipe'].get('basis'), 'current')

    def test_matrix_contains_large_independent_bounded_parameter_space(self):
        r = self.php("echo json_encode([NfqwsStrategySynthesis::matrix(['small'=>true,'busy'=>false,'max_repeats'=>4]),NfqwsStrategySynthesis::matrix(['small'=>false,'busy'=>false,'max_repeats'=>6])]);")
        self.assertGreater(r[0]['space_size'], 1000)
        self.assertLess(r[0]['max_trials'], r[1]['max_trials'])
        self.assertEqual(len(r[0]['initial']), 10)
        for m in r:
            self.assertTrue(m['independent_of_catalog'])
            self.assertEqual(m['knowledge_version'], 'zapret2-1.0.7-v4')

    def test_updated_matrix_covers_incoming_TLS_window_and_multi_position_candidates(self):
        r=self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4,'small'=>true]);$out=['version'=>$m['knowledge_version'],'initial'=>$m['initial'],'rules'=>[]];foreach($m['initial']as $recipe)$out['rules'][]=NfqwsStrategySynthesis::bind($recipe,['NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/user.list --hostlist-auto=/tmp/auto.list --hostlist-exclude=/tmp/exclude.list','NFQWS_BASE_ARGS'=>'--lua-init=@/tmp/zapret-lib.lua']);echo json_encode($out);""")
        window=[c for c in r['rules'] if 'wssize:wsize=1:scale=1:dir=out' in c['NFQWS_ARGS']]
        self.assertTrue(window)
        self.assertEqual(r['version'],'zapret2-1.0.7-v4')
        for c in window:
            self.assertIn('--ipcache-hostname',c['NFQWS_BASE_ARGS'])
            tls=c['NFQWS_ARGS'].split(' --new ')[-1]
            self.assertIn('--payload=all',tls)
            self.assertNotIn('--filter-l7=tls',tls)
            self.assertIn('--payload=tls_client_hello',tls)
            self.assertNotIn('forced_cutoff=no',tls)
            self.assertIn('--hostlist-exclude=/tmp/exclude.list',c['NFQWS_EXTRA_ARGS'])
            self.assertNotIn('wssize',c['NFQWS_ARGS_QUIC'])
        self.assertTrue(any('pos=1,sniext+1,host+1,midsld-2,midsld,midsld+2,endhost-1' in c['NFQWS_ARGS'] for c in r['rules']))

    def test_best_measured_method_families_are_collected_for_fresh_repetition(self):
        r=self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$s=['targets'=>'same','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>3]),'domains'=>[]];$o=[['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$s,$s]]];foreach([['http'],['tcp','tls12','tls13'],['quic']]as $i=>$columns){$a=$s;foreach($columns as $c)$a['metrics'][$c]['ok']=3;$o[]=['recipe'=>$m['initial'][$i],'runs'=>[$a]];}echo json_encode(['best'=>NfqwsStrategySynthesis::bestForRetest($o),'expected'=>array_merge([NfqwsStrategySynthesis::assemble($o)],array_slice($m['initial'],0,3))]);""")
        self.assertEqual(r['best'],r['expected'])

    def test_retained_history_supplies_only_validated_recipes_for_new_measurements(self):
        r=self.php("""require $argv[1].'/strategy-synthesis-runtime.php';$u=(int)getmyuid();$s=new NfqwsStrategyPickerState($argv[2].'/picker',$u);$s->write(['goal'=>'all']);$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$score=['targets'=>'old-context','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>1,'total'=>1]),'domains'=>[]];$id=str_repeat('a',32);$history=new NfqwsStrategyPickerState($s->root.'/job-'.$id,$u);$old=['id'=>$id,'state'=>'completed','restored'=>true,'search'=>'synthesis','profiles'=>[['components'=>$m['initial'][0],'runs'=>[$score]]]];$history->write($old);$hash=hash_file('sha256',$history->path('state.json'));$h=new class($s){use NfqwsStrategySynthesisRuntime;public function __construct(private $store){}public function collect(){return $this->synthesisHistoryRecipes('all');}};echo json_encode(['recipes'=>$h->collect(),'expected'=>[$m['initial'][0]],'old_unchanged'=>hash_file('sha256',$history->path('state.json'))===$hash,'new_unchanged'=>$s->read()===['goal'=>'all']]);""")
        self.assertEqual(r['recipes'],r['expected'])
        self.assertTrue(r['old_unchanged'])
        self.assertTrue(r['new_unchanged'])

    def test_next_round_keeps_leader_memory_without_spending_search_on_its_duplicate(self):
        # The previous recipe remains a proposal in memory. Its actual old
        # measurement also marks it explored, so the next search starts fresh.
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());
        $s->write(['id'=>str_repeat('b',32),'goal'=>'all','profiles'=>[],
            'budget'=>['small'=>true,'max_repeats'=>4],'deadline'=>null]);
        $recipe=['http'=>['method'=>'http_hostcase'],'tls'=>['method'=>'multisplit','pos'=>'midsld'],
            'quic'=>['method'=>'fake','repeats'=>2],'overrides'=>[]];
        $score=['targets'=>'preceding-round','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>1,'total'=>1]),'domains'=>[]];
        $id=str_repeat('a',32);$old=new NfqwsStrategyPickerState($s->root.'/job-'.$id,(int)getmyuid());
        $old->write(['id'=>$id,'goal'=>'all','state'=>'completed','restored'=>true,'search'=>'synthesis',
            'profiles'=>[['components'=>$recipe,'runs'=>[$score,$score]]]]);
        $before=hash_file('sha256',$old->path('state.json'));
        $h=new class($s){
            use NfqwsStrategySynthesisRuntime;
            public $first=null;
            public function __construct(private $store){}
            public function run(){try{$this->synthesisWork();}catch(Throwable $e){if($e->getMessage()!=='cancelled')throw $e;}}
            private function synthesisAdmission():void{}
            private function checkpoint():void{}
            private function synthesisTime():bool{return true;}
            private function phase(string $phase,array $extra=[]):void{$this->store->write(array_replace($this->store->read(),$extra,['phase'=>$phase]));}
            private function library(){return new class{
                public function capture($name){return ['id'=>'current','name'=>$name];}
                public function entry($id){return ['id'=>$id];}
                public function synthesis($scope){return ['id'=>'fresh'];}
            };}
            private function synthesisTrial(array $entry,string $name,?array $recipe,int $repeats,bool $warm=false,?callable $onNative=null,?callable $beforeNative=null):array{
                if($recipe!==null&&$recipe!==NfqwsStrategySynthesis::blank()){$this->first=$recipe;throw new RuntimeException('cancelled');}
                $score=['targets'=>'fresh-round','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>1]),'domains'=>[]];
                return ['id'=>$entry['id'],'recipe'=>$recipe===null?'control':'zero','runs'=>[$score,$score]];
            }
        };
        $h->run();echo json_encode(['first'=>$h->first,'previous'=>$recipe,'memory'=>$s->read()['synthesis_memory']??null,
            'old_unchanged'=>hash_file('sha256',$old->path('state.json'))===$before]);""")
        self.assertNotEqual(r['first'],r['previous'])
        self.assertEqual(r['memory']['recipes'][0]['tls'],{'method':'multisplit','pos':'midsld'})
        self.assertTrue(r['old_unchanged'])

    def test_current_series_memory_survives_saturated_older_archives(self):
        # Break caught: full old archives must not evict the just-finished
        # round's finite proposals and explored keys before the next queue.
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());
        $fresh=['http'=>['method'=>'http_domcase'],'tls'=>['method'=>'fake','fooling'=>'ack','repeats'=>4],
          'quic'=>['method'=>'fake','repeats'=>6],'overrides'=>[]];
        $recent=[];for($i=0;$i<24;$i++)$recent[]=hash('sha256','just-finished-round-'.$i);
        $scope=['goal'=>'all','custom_hosts'=>[],'custom_only'=>false];
        $current=['goal'=>'all','synthesis_memory'=>['version'=>'picker-recipe-memory-v1',
          'knowledge_version'=>NfqwsStrategySynthesis::VERSION,'scope'=>$scope,'recipes'=>[$fresh],'explored'=>$recent]];
        $s->write($current);$currentHash=hash_file('sha256',$s->path('state.json'));
        $oldKeys=[];for($i=0;$i<64;$i++)$oldKeys[]=hash('sha256','older-job-'.$i);
        $recipes=array_slice(NfqwsStrategySynthesis::matrix(['max_repeats'=>6])['initial'],0,8);
        $id=str_repeat('a',32);$archive=new NfqwsStrategyPickerState($s->root.'/job-'.$id,(int)getmyuid());
        $archive->write(['id'=>$id,'goal'=>'all','state'=>'failed','restored'=>true,'search'=>'synthesis','profiles'=>[],
          'synthesis_memory'=>['version'=>'picker-recipe-memory-v1','knowledge_version'=>NfqwsStrategySynthesis::VERSION,
          'scope'=>$scope,'recipes'=>$recipes,'explored'=>$oldKeys]]);
        $oldHash=hash_file('sha256',$archive->path('state.json'));
        $h=new class($s){use NfqwsStrategySynthesisRuntime;public function __construct(private $store){}
          public function collect(){$recipes=$this->synthesisHistoryRecipes('all');return ['recipes'=>$recipes,'explored'=>$this->synthesisExplored];}};
        echo json_encode($h->collect()+['fresh'=>$fresh,'recent'=>$recent,
          'old_unchanged'=>hash_file('sha256',$archive->path('state.json'))===$oldHash,
          'current_unchanged'=>hash_file('sha256',$s->path('state.json'))===$currentHash]);""")
        self.assertEqual(r['recipes'][0],r['fresh'])
        self.assertEqual(r['explored'][:24],r['recent'])
        self.assertEqual(len(r['recipes']),8)
        self.assertEqual(len(r['explored']),64)
        self.assertTrue(r['old_unchanged'])
        self.assertTrue(r['current_unchanged'])

    def test_restored_failed_rounds_carry_the_preceding_leader_without_stale_scores(self):
        # Break caught: eight newer unsuccessful attempts must not crowd the
        # last useful recipe out of the bounded history window.
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());$s->write(['goal'=>'all']);
        $recipe=['http'=>['method'=>'http_hostcase'],'tls'=>['method'=>'multisplit','pos'=>'midsld'],
            'quic'=>['method'=>'fake','repeats'=>2],'overrides'=>[]];
        $memory=['version'=>'picker-recipe-memory-v1','knowledge_version'=>NfqwsStrategySynthesis::VERSION,
            'scope'=>['goal'=>'all','custom_hosts'=>[],'custom_only'=>false],'recipes'=>[$recipe]];
        $hashes=[];
        for($i=1;$i<=9;$i++){
            $id=str_pad(dechex($i),32,'0',STR_PAD_LEFT);$h=new NfqwsStrategyPickerState($s->root.'/job-'.$id,(int)getmyuid());
            $h->write(['id'=>$id,'state'=>'failed','restored'=>true,'search'=>'synthesis','profiles'=>[],
                'synthesis_memory'=>$memory]);$hashes[$h->path('state.json')]=hash_file('sha256',$h->path('state.json'));touch($h->root,1000+$i);
        }
        $h=new class($s){use NfqwsStrategySynthesisRuntime;public function __construct(private $store){}public function collect(){return $this->synthesisHistoryRecipes('all');}};
        $recipes=$h->collect();$unchanged=true;foreach($hashes as $path=>$sha)$unchanged=$unchanged&&hash_file('sha256',$path)===$sha;
        echo json_encode(['recipes'=>$recipes,'unchanged'=>$unchanged,'current'=>$s->read()]);""")
        self.assertEqual(len(r['recipes']),1)
        self.assertEqual(r['recipes'][0]['tls'],{'method':'multisplit','pos':'midsld'})
        self.assertNotIn('runs',r['recipes'][0])
        self.assertTrue(r['unchanged'])
        self.assertEqual(r['current'],{'goal':'all'})

    def test_carry_forward_keeps_successful_ipv4_methods_without_old_scope_authority(self):
        # Break caught: removing an old target manifest must not also discard
        # the method that succeeded specifically for its IPv4 destination.
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';require $argv[1].'/strategy-picker-custom-worker.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());
        $hosts=['8.8.8.8','example.com'];$s->write(['goal'=>'all','custom_hosts'=>$hosts,'custom_only'=>true]);
        $manifest=NfqwsStrategyPickerCustomWorker::prepareDocument($hosts,str_repeat('d',64));
        $manifest+=['pins'=>[['host'=>'8.8.8.8','answer'=>['8.8.8.8'],'address'=>'8.8.8.8'],
            ['host'=>'example.com','answer'=>['8.8.8.8'],'address'=>'8.8.8.8']],
            'policy'=>NfqwsIdna::POLICY,'fingerprint'=>AsusDpiSiteCheckProbe::MIXED_PINNED_FINGERPRINT];
        $recipe=NfqwsStrategySynthesis::forTargets(NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0],$manifest,['example.com']);
        foreach($recipe['overrides']as &$rule)if(isset($rule['addresses']))$rule['component']=['method'=>'multidisorder','pos'=>'host+1'];unset($rule);
        $before=json_encode($recipe);$h=new class($s){use NfqwsStrategySynthesisRuntime;public function __construct(private $store){}public function remember($recipes){return $this->synthesisMemory($recipes);}};
        echo json_encode(['memory'=>$h->remember([$recipe]),'input_unchanged'=>json_encode($recipe)===$before]);""")
        self.assertEqual([x['tls'] for x in r['memory']['recipes']],
                         [{'method':'multisplit','pos':'1,midsld'},
                          {'method':'multidisorder','pos':'host+1'}])
        self.assertTrue(all('custom_scope' not in x and x['overrides']==[] for x in r['memory']['recipes']))
        self.assertTrue(r['input_unchanged'])

    def test_carry_forward_keeps_domain_exception_methods_without_previous_hosts(self):
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());$s->write(['goal'=>'all']);
        $recipe=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];
        $recipe['overrides']=[['protocol'=>'tls','domains'=>['previous-private.example.com'],
            'component'=>['method'=>'multidisorder','pos'=>'host+1']]];
        $h=new class($s){use NfqwsStrategySynthesisRuntime;public function __construct(private $store){}public function remember($recipes){return $this->synthesisMemory($recipes);}};
        echo json_encode($h->remember([$recipe]));""")
        self.assertEqual([x['tls'] for x in r['recipes']],
                         [{'method':'multisplit','pos':'1,midsld'},
                          {'method':'multidisorder','pos':'host+1'}])
        self.assertTrue(all(x['overrides']==[] for x in r['recipes']))
        self.assertNotIn('previous-private.example.com',json.dumps(r))

    def test_ipv4_zero_control_is_not_relabelled_as_a_best_candidate(self):
        # Break caught: retesting the scoped pass-through overwrites its
        # zero_baseline record and makes the completed report unexportable.
        r=self.php(r"""require $argv[1].'/strategy-picker-custom-worker.php';
        $hosts=['8.8.8.8','example.com'];$manifest=NfqwsStrategyPickerCustomWorker::prepareDocument($hosts,str_repeat('d',64));
        $manifest+=['pins'=>[['host'=>'8.8.8.8','answer'=>['8.8.8.8'],'address'=>'8.8.8.8'],
            ['host'=>'example.com','answer'=>['8.8.8.8'],'address'=>'8.8.8.8']],
            'policy'=>NfqwsIdna::POLICY,'fingerprint'=>AsusDpiSiteCheckProbe::MIXED_PINNED_FINGERPRINT];
        $zero=NfqwsStrategySynthesis::forTargets(NfqwsStrategySynthesis::blank(),$manifest,['example.com']);
        $candidate=NfqwsStrategySynthesis::forTargets(NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0],$manifest,['example.com']);
        $score=['targets'=>'same','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>1]),'domains'=>[]];
        $good=$score;foreach(['tls12','tls13']as $key)$good['metrics'][$key]['ok']=1;
        $out=NfqwsStrategySynthesis::bestForRetest([['recipe'=>$zero,'runs'=>[$score,$score]],['recipe'=>$candidate,'runs'=>[$good,$good]]]);
        echo json_encode(['zero'=>$zero,'candidates'=>$out]);""")
        self.assertTrue(r['candidates'])
        self.assertNotIn(r['zero'],r['candidates'])

    def test_different_custom_targets_do_not_inherit_a_preceding_targets_memory(self):
        r=self.php(r"""require $argv[1].'/strategy-synthesis-runtime.php';
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());
        $s->write(['goal'=>'all','custom_hosts'=>['new.example.com'],'custom_only'=>true]);
        $id=str_repeat('a',32);$h=new NfqwsStrategyPickerState($s->root.'/job-'.$id,(int)getmyuid());
        $recipe=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];
        $h->write(['id'=>$id,'state'=>'failed','restored'=>true,'search'=>'synthesis','profiles'=>[],
            'goal'=>'all','custom_hosts'=>['old.example.com'],'custom_only'=>true,
            'synthesis_memory'=>['version'=>'picker-recipe-memory-v1','knowledge_version'=>NfqwsStrategySynthesis::VERSION,
                'scope'=>['goal'=>'all','custom_hosts'=>['old.example.com'],'custom_only'=>true],'recipes'=>[$recipe]]]);
        $before=hash_file('sha256',$h->path('state.json'));
        $runtime=new class($s){use NfqwsStrategySynthesisRuntime;public function __construct(private $store){}public function collect(){return $this->synthesisHistoryRecipes('all');}};
        echo json_encode(['recipes'=>$runtime->collect(),'old_unchanged'=>hash_file('sha256',$h->path('state.json'))===$before]);""")
        self.assertEqual(r['recipes'],[])
        self.assertTrue(r['old_unchanged'])

    def test_repeated_recipe_has_one_current_result_and_preserves_previous_attempt(self):
        r=self.php("""require $argv[1].'/strategy-synthesis-runtime.php';$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)getmyuid());$s->write(['profiles'=>[]]);$h=new class($s){use NfqwsStrategySynthesisRuntime;public function __construct(private $store){}public function record($p){$this->synthesisRecord($p,['reason'=>'retested']);}};$h->record(['id'=>'saved-'.str_repeat('a',16),'recipe'=>'s-'.str_repeat('b',16),'runs'=>[['actual'=>'first']]]);$h->record(['id'=>'saved-'.str_repeat('a',16),'recipe'=>'s-'.str_repeat('b',16),'runs'=>[['actual'=>'repeated']]]);echo json_encode($s->read()['profiles']);""")
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['runs'],[{'actual':'repeated'}])
        self.assertEqual(r[0]['previous_attempts'][0]['runs'],[{'actual':'first'}])

    def test_equal_target_measurements_prefer_better_measured_controls_before_cost(self):
        r=self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$hosts=['www.youtube.com','a.example.com','b.example.com'];$s=['targets'=>'same','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>3]),'domains'=>array_fill_keys($hosts,array_fill_keys(['http','tls12','tls13','quic'],false))];$cheap=$s;$cheap['domains']['www.youtube.com']['tls12']=true;$cheap['domains']['www.youtube.com']['tls13']=true;foreach(['tcp','tls12','tls13']as $key)$cheap['metrics'][$key]['ok']=1;$strong=$cheap;foreach($hosts as $host){$strong['domains'][$host]['tls12']=true;$strong['domains'][$host]['tls13']=true;}foreach(['tcp','tls12','tls13']as $key)$strong['metrics'][$key]['ok']=3;$o=[['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$s,$s]],['recipe'=>$m['initial'][0],'runs'=>[$cheap]],['recipe'=>$m['initial'][4],'runs'=>[$strong]]];$result=NfqwsStrategySynthesis::assemble($o,'youtube');echo json_encode([$result['tls'],$m['initial'][4]['tls']]);""")
        self.assertEqual(r[0],r[1])

    def test_selected_goal_remains_first_even_when_another_component_has_more_control_success(self):
        r=self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$hosts=['www.youtube.com','a.example.com','b.example.com'];$s=['targets'=>'same','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>3]),'domains'=>array_fill_keys($hosts,array_fill_keys(['http','tls12','tls13','quic'],false))];$focused=$s;$focused['domains']['www.youtube.com']['tls12']=true;$focused['domains']['www.youtube.com']['tls13']=true;foreach(['tcp','tls12','tls13']as $key)$focused['metrics'][$key]['ok']=1;$other=$focused;$other['domains']['www.youtube.com']['tls12']=false;foreach(['a.example.com','b.example.com']as $host){$other['domains'][$host]['tls12']=true;$other['domains'][$host]['tls13']=true;}$other['metrics']['tcp']['ok']=3;$other['metrics']['tls12']['ok']=2;$other['metrics']['tls13']['ok']=3;$result=NfqwsStrategySynthesis::assemble([['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$s,$s]],['recipe'=>$m['initial'][0],'runs'=>[$focused]],['recipe'=>$m['initial'][4],'runs'=>[$other]]],'youtube');echo json_encode([$result['tls'],$m['initial'][0]['tls']]);""")
        self.assertEqual(r[0],r[1])

    def test_equal_target_and_control_measurements_still_prefer_lower_packet_cost(self):
        r=self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$s=['targets'=>'same','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>1,'total'=>1]),'domains'=>['www.youtube.com'=>array_fill_keys(['http','tls12','tls13','quic'],true)]];$result=NfqwsStrategySynthesis::assemble([['recipe'=>$m['initial'][4],'runs'=>[$s]],['recipe'=>$m['initial'][0],'runs'=>[$s]]],'youtube');echo json_encode([$result['tls'],$m['initial'][0]['tls']]);""")
        self.assertEqual(r[0],r[1])

    def test_reported_parameter_grid_is_the_product_of_declared_axes(self):
        r=self.php("echo json_encode(NfqwsStrategySynthesis::matrix(['max_repeats'=>4,'small'=>true]));")
        import math
        self.assertEqual(r['space_size'],math.prod(len(axis)for axis in r['dimensions'].values()))
        self.assertEqual(r.get('space_kind'),'factorized_grid')

    def test_embedded_cost_weights_prefer_lower_packet_work_on_equal_measurements(self):
        r=self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$s=['targets'=>'a','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>1,'total'=>2]),'domains'=>[]];$a=$s;foreach($a['metrics']as &$v)$v['ok']=2;unset($v);$costly=$m['initial'][4];$cheap=$m['initial'][0];$out=NfqwsStrategySynthesis::assemble([['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$s,$s]],['recipe'=>$costly,'runs'=>[$a]],['recipe'=>$cheap,'runs'=>[$a]]]);echo json_encode([$out['tls']===$cheap['tls'],NfqwsStrategySynthesis::cost($cheap)<NfqwsStrategySynthesis::cost($costly)]);""")
        self.assertEqual(r,[True,True])

    def test_compile_from_empty_has_no_inherited_rules_or_external_blobs(self):
        r = self.php("$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4,'small'=>true]);$out=[];foreach($m['initial']as $recipe)$out[]=NfqwsStrategySynthesis::compile($recipe);echo json_encode($out);")
        for rules in r:
            raw = ' '.join(rules.values())
            self.assertNotIn('/opt/', raw)
            self.assertNotIn('circular', raw)
            self.assertNotIn('mtproto', raw)
            self.assertNotIn('--lua-init', raw)
            self.assertIn('--filter-tcp=443', raw)
            self.assertIn('--filter-udp=443', raw)
        self.assertTrue(any('--lua-desync=multisplit' in x['NFQWS_ARGS'] for x in r))
        self.assertTrue(any('--lua-desync=fake:blob=fake_default_tls' in x['NFQWS_ARGS'] for x in r))

    def test_untrusted_parameters_never_reach_cli(self):
        r = self.php("$out=[];foreach([['method'=>'multisplit','pos'=>'2 --lua-init=evil'],['method'=>'fake','repeats'=>999],['method'=>'drop'],['method'=>'fake','fooling'=>'tcp_ack=-1:luaexec=evil'],['method'=>'pass','path'=>'/etc/shadow']]as $c){try{NfqwsStrategySynthesis::compile(['http'=>['method'=>'pass'],'tls'=>$c,'quic'=>['method'=>'pass']]);$out[]='accepted';}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);")
        self.assertEqual(r, ['invalid_synthesis_recipe'] * 5)

    def test_pass_through_is_a_real_zero_method_control(self):
        r = self.php("echo json_encode(NfqwsStrategySynthesis::compile(NfqwsStrategySynthesis::blank()));")
        self.assertEqual(' '.join(r.values()).count('--lua-desync=pass'), 3)
        self.assertNotIn('--lua-desync=fake', ' '.join(r.values()))

    def test_generated_rules_do_not_process_untested_ipv6(self):
        r=self.php("$r=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];$r['overrides']=[['protocol'=>'tls','domains'=>['discord.com'],'component'=>['method'=>'multidisorder']]];echo json_encode(NfqwsStrategySynthesis::compile($r));")
        profiles=' --new '.join(x for x in [r['NFQWS_ARGS_CUSTOM'],r['NFQWS_ARGS'],r['NFQWS_ARGS_QUIC']] if x).split(' --new ')
        for profile in profiles:self.assertIn('--filter-l3=ipv4',profile)

    def test_real_startup_scopes_every_http_tls_quic_profile_and_override(self):
        r=self.php("""$r=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];$r['overrides']=[['protocol'=>'tls','domains'=>['discord.com'],'component'=>['method'=>'multidisorder']]];echo json_encode(NfqwsStrategySynthesis::bind($r,['NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/user.list --hostlist-auto=/tmp/auto.list --hostlist-exclude=/tmp/exclude.list','NFQWS_BASE_ARGS'=>'','NFQWS_ARGS_IPSET'=>'']));""")
        import re
        common=(PUBLIC.parents[2]/'core/etc/init.d/common').read_text()
        function=re.search(r'^_startup_args\(\) \{.*?^\}',common,re.M|re.S).group()
        script='\n'.join(k+'='+shlex.quote(v) for k,v in r.items())+'\nLOG_LEVEL=0\nUSER=nobody\nNFQUEUE_NUM=300\n'+function+'\n_startup_args\n'
        p=subprocess.run(['/bin/sh'],input=script,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        profiles=[x.strip() for x in p.stdout.split('--new')]
        self.assertEqual(len(profiles),4)
        for profile in profiles:
            self.assertEqual(profile.count('--hostlist-exclude=/tmp/exclude.list'),1)
            if '--hostlist-domains=discord.com' in profile:
                self.assertNotIn('--hostlist-auto=',profile)
            else:
                self.assertEqual(profile.count('--hostlist-auto=/tmp/auto.list'),1)

    def test_feedback_assembles_distinct_protocol_winners_not_a_ready_profile(self):
        r = self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4,'small'=>true]);
        $a=['targets'=>'same','metrics'=>['tcp'=>['ok'=>1,'total'=>2],'http'=>['ok'=>0,'total'=>2],'tls12'=>['ok'=>0,'total'=>2],'tls13'=>['ok'=>0,'total'=>2],'quic'=>['ok'=>0,'total'=>2]],'domains'=>['youtube.com'=>['http'=>false,'tls12'=>false,'tls13'=>false,'quic'=>false]]];
        $o=[['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$a,$a]]];
        foreach([0,1,2]as $i){$s=$a;foreach([['http'],['tcp','tls12','tls13'],['quic']][$i]as $p)$s['metrics'][$p]['ok']=2;
        $o[]=['recipe'=>$m['initial'][$i],'runs'=>[$s]];}
        $r=NfqwsStrategySynthesis::assemble($o,'all');echo json_encode([$r['http']===$o[1]['recipe']['http'],$r['tls']===$o[2]['recipe']['tls'],$r['quic']===$o[3]['recipe']['quic']]);""")
        self.assertEqual(r, [True, True, True])

    def test_mismatched_or_missing_target_evidence_is_ignored(self):
        r = self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$s=['targets'=>'a','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>1]),'domains'=>[]];$foreign=$s;$foreign['targets']='b';foreach($foreign['metrics']as &$v)$v['ok']=1;unset($v);echo json_encode(NfqwsStrategySynthesis::assemble([['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$s,$s]],['recipe'=>$m['initial'][0],'runs'=>[$foreign]]],'all'));""")
        self.assertEqual(r, {'http': {'method': 'pass'}, 'tls': {'method': 'pass'}, 'quic': {'method': 'pass'}, 'overrides': []})

    def test_refinement_uses_feedback_and_never_retests_the_same_program(self):
        r = self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4,'small'=>true]);$s=['targets'=>'a','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>1,'total'=>2]),'domains'=>[]];$a=$s;foreach(['tcp','tls12','tls13']as $p)$a['metrics'][$p]['ok']=2;$o=[['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$s,$s]],['recipe'=>$m['initial'][0],'runs'=>[$a]]];echo json_encode(NfqwsStrategySynthesis::refine($o,['max_repeats'=>4,'small'=>true]));""")
        self.assertGreater(len(r), 0)
        keys = [json.dumps(x, sort_keys=True) for x in r]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(any(x['tls'].get('fake') or x['tls'].get('pos') != '1,midsld' for x in r))

    def test_host_overrides_combine_complementary_working_methods(self):
        r = self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$s=['targets'=>'a','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>2]),'domains'=>['youtube.com'=>['http'=>false,'tls12'=>false,'tls13'=>false,'quic'=>false],'discord.com'=>['http'=>false,'tls12'=>false,'tls13'=>false,'quic'=>false]]];$o=[['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$s,$s]]];foreach([0,1]as $i){$a=$s;$a['metrics']['tls12']['ok']=1;$a['metrics']['tls13']['ok']=1;$host=$i===0?'youtube.com':'discord.com';$a['domains'][$host]['tls12']=true;$a['domains'][$host]['tls13']=true;$o[]=['recipe'=>$m['initial'][$i],'runs'=>[$a]];}$recipe=NfqwsStrategySynthesis::assemble($o,'all');echo json_encode([$recipe,NfqwsStrategySynthesis::compile($recipe)]);""")
        self.assertGreater(len(r[0]['overrides']), 0)
        self.assertIn('--hostlist-domains=discord.com', r[1]['NFQWS_ARGS_CUSTOM'])
        self.assertNotIn('--hostlist-auto', r[1]['NFQWS_ARGS_CUSTOM'])

    def test_telegram_domains_never_get_generated_overrides(self):
        r = self.php("try{NfqwsStrategySynthesis::compile(['http'=>['method'=>'pass'],'tls'=>['method'=>'pass'],'quic'=>['method'=>'pass'],'overrides'=>[['protocol'=>'tls','domains'=>['t.me'],'component'=>['method'=>'multisplit']]]]);echo json_encode(false);}catch(Throwable $e){echo json_encode($e->getMessage());}")
        self.assertEqual(r, 'invalid_synthesis_recipe')

    def test_parent_override_never_shadows_a_more_specific_child(self):
        r=self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$hosts=['a-very-long-unrelated.example.net','example.com','child.example.com','one.invalid','two.invalid','three.invalid'];$s=['targets'=>'a','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>6]),'domains'=>array_fill_keys($hosts,array_fill_keys(['http','tls12','tls13','quic'],false))];$o=[['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$s,$s]]];foreach([['one.invalid','two.invalid','three.invalid'],['a-very-long-unrelated.example.net','example.com'],['child.example.com']]as $i=>$solved){$a=$s;$a['metrics']['tls12']['ok']=count($solved);$a['metrics']['tls13']['ok']=count($solved);foreach($solved as $host){$a['domains'][$host]['tls12']=true;$a['domains'][$host]['tls13']=true;}$o[]=['recipe'=>$m['initial'][$i],'runs'=>[$a]];}echo json_encode(NfqwsStrategySynthesis::assemble($o)['overrides']);""")
        child=next(i for i,x in enumerate(r) if 'child.example.com' in x['domains'])
        parent=next(i for i,x in enumerate(r) if 'example.com' in x['domains'])
        self.assertLess(child,parent)

    def test_parent_override_keeps_child_that_needs_the_general_component(self):
        r=self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);$hosts=['example.com','child.example.com','one.invalid','two.invalid'];$s=['targets'=>'a','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>0,'total'=>4]),'domains'=>array_fill_keys($hosts,array_fill_keys(['http','tls12','tls13','quic'],false))];$o=[['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$s,$s]]];foreach([['child.example.com','one.invalid','two.invalid'],['example.com']]as $i=>$solved){$a=$s;$a['metrics']['tls12']['ok']=count($solved);$a['metrics']['tls13']['ok']=count($solved);foreach($solved as $host){$a['domains'][$host]['tls12']=true;$a['domains'][$host]['tls13']=true;}$o[]=['recipe'=>$m['initial'][$i],'runs'=>[$a]];}echo json_encode(NfqwsStrategySynthesis::assemble($o)['overrides']);""")
        self.assertIn('child.example.com',[d for x in r for d in x['domains']])
        self.assertEqual(r[0]['component']['method'],'multisplit')

    def test_native_target_path_becomes_host_but_never_a_cli_operand(self):
        r=self.php("""echo json_encode([NfqwsStrategySynthesis::host('x.com/i/api/1.1/graphql/user_flow.json'),NfqwsStrategySynthesis::host('https://user:password@evil.test/path'),NfqwsStrategySynthesis::host('evil.test/ --lua-init=bad')]);""")
        self.assertEqual(r,['x.com',None,None])

    def test_a_stable_tun_change_between_runs_invalidates_comparison(self):
        r=self.php("""$row=['domain'=>'youtube.com','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'timeout'];$c=['nfqws'=>'running','ark'=>'absent','tun_observed'=>false];$d=['state'=>'completed','coverage'=>['domains'=>1,'tcp'=>1],'context'=>['before'=>$c,'after'=>$c,'changed'=>false],'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>[$row]]]],['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'a','status'=>'timeout']]]]]]];$a=NfqwsStrategyPickerScore::measure($d);$d['context']['before']['tun_observed']=true;$d['context']['after']['tun_observed']=true;$d['groups'][1]['document']['results']['tcp16'][0]['status']='ok';$b=NfqwsStrategyPickerScore::measure($d);echo json_encode(NfqwsStrategyPickerScore::compare([$a,$a],[$b,$b]));""")
        self.assertFalse(r['eligible']);self.assertEqual(r['reason'],'incomparable_result')

    def test_synthesis_http_accepts_no_custom_matrix_or_program(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$base=['cmd'=>'pickersynthesize','csrf_token'=>'x','request_id'=>str_repeat('a',32),'consent'=>'test','goal'=>'youtube'];$out=[];foreach([$base,$base+['recipe'=>'anything'],$base+['matrix'=>'https://evil.test']]as $p){try{NfqwsStrategyPickerRuntime::validateRequest($p);$out[]='ok';}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,['ok','invalid_request','invalid_request'])

    def test_tracker_addition_extends_only_generated_tls_and_preserves_excludes(self):
        r=self.php("""$r=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];$r['overrides']=[['protocol'=>'tls','domains'=>['discord.com'],'component'=>['method'=>'multidisorder']]];$c=NfqwsStrategySynthesis::bind($r,['NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/user.list --hostlist-auto=/tmp/auto.list --hostlist-exclude=/tmp/exclude.list']);$a=NfqwsStrategySynthesis::torrentSites($c,$r);echo json_encode([$c,$a,NfqwsStrategySynthesis::torrentSites($a,$r)]);""")
        before,after,twice=r
        self.assertEqual(after,twice)
        for key in before:
            if key!='NFQWS_ARGS':self.assertEqual(before[key],after[key])
        old_http,old_tls=before['NFQWS_ARGS'].split(' --new ')
        http,tls=after['NFQWS_ARGS'].split(' --new ')
        self.assertEqual(http,old_http)
        self.assertTrue(tls.startswith(old_tls+' '))
        self.assertIn('--hostlist-domains=nnmclub.to,rutracker.org,rutor.info,tapochek.net',tls)
        self.assertEqual(after['NFQWS_EXTRA_ARGS'],before['NFQWS_EXTRA_ARGS'])

    def test_tracker_addition_refuses_unknown_program_and_pass_through_tls(self):
        r=self.php("""$r=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];$base=['NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/user.list --hostlist-exclude=/tmp/exclude.list'];$c=NfqwsStrategySynthesis::bind($r,$base);$c['NFQWS_ARGS'].=' --lua-desync=drop';$out=[];foreach([[$c,$r],[NfqwsStrategySynthesis::bind(NfqwsStrategySynthesis::blank(),$base),NfqwsStrategySynthesis::blank()]]as [$c,$r]){try{NfqwsStrategySynthesis::torrentSites($c,$r);$out[]='accepted';}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,['torrent_sites_incompatible']*2)

    def test_tracker_addition_normalizes_legacy_comment_without_changing_rules(self):
        r=self.php("""$r=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];$plain=NfqwsStrategySynthesis::bind($r,['NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/user.list --hostlist-exclude=/tmp/exclude.list']);$old=$plain;$old['NFQWS_ARGS'].=' --hostlist-domains=nnmclub.to,rutracker.org,rutor.info,tapochek.net --comment=nfqws2-synthesis-trackers-beta';$new=NfqwsStrategySynthesis::torrentSites($old,$r);echo json_encode([$old,$new,NfqwsStrategySynthesis::torrentSites($new,$r)]);""")
        old,new,twice=r
        self.assertEqual(new,twice)
        self.assertEqual(new['NFQWS_ARGS'],old['NFQWS_ARGS'].removesuffix('-beta'))
        self.assertEqual({k:v for k,v in old.items()if k!='NFQWS_ARGS'},{k:v for k,v in new.items()if k!='NFQWS_ARGS'})

    def test_tracker_http_option_is_strict_and_only_available_for_export_or_apply(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$out=[];foreach(['pickerexport','pickerapply','pickercancel']as $cmd)foreach(['0','1','true','yes']as $value){try{NfqwsStrategyPickerRuntime::validateRequest(['cmd'=>$cmd,'csrf_token'=>'x','id'=>str_repeat('a',32),'torrent_sites'=>$value]);$out[]='ok';}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,['ok','ok','invalid_request','invalid_request']*2+['invalid_request']*4)

    def test_tracker_offer_checks_the_actual_stored_program_after_an_upgrade(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$s=new NfqwsStrategyPickerState($argv[2].'/state',getmyuid());$id=str_repeat('a',32);$recipe=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];$c=NfqwsStrategySynthesis::bind($recipe,['NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/user.list --hostlist-exclude=/tmp/exclude.list']);$key='saved:s-key';$j=['id'=>$id,'state'=>'completed','restored'=>true,'winner'=>null,'generated'=>$key,'generation'=>['verified'=>true],'profiles'=>[['id'=>'saved','recipe'=>'s-key','components'=>$recipe,'variant'=>$c]]];$s->write(['id'=>$id,'generated'=>$key,'files'=>[]],'generated-auto.json');$s->write($j);$runtime=new NfqwsStrategyPickerRuntime($s);$out=[$runtime->status()['job']['can_add_torrent_sites']];$j['profiles'][0]['variant']['NFQWS_ARGS']=str_replace('--filter-l3=ipv4 ','',$c['NFQWS_ARGS']);$s->write($j);$out[]=$runtime->status()['job']['can_add_torrent_sites'];echo json_encode($out);""")
        self.assertEqual(r,[True,False])

    def test_applied_tracker_notice_keeps_base_measurements_separate(self):
        node=os.environ.get('NODE_BINARY') or shutil.which('node')
        if not node:self.skipTest('Node runtime is unavailable')
        script="""import {addonNotice} from './picker.js';console.log(JSON.stringify([addonNotice({state:'applied',torrent_sites:true},'ru'),addonNotice({state:'applied',torrent_sites:false},'ru'),addonNotice({state:'applied',torrent_sites:true},'en'),addonNotice({state:'failed',torrent_sites:true},'ru'),addonNotice({state:'applying',torrent_sites:true},'ru')]));"""
        r=subprocess.run([str(node),'--input-type=module','-e',script],cwd=PUBLIC/'strategy-picker',capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        ru,none,en,failed,pending=json.loads(r.stdout)
        self.assertNotRegex(ru+' '+en,r'(?i)beta|бета');self.assertIn('без дополнения',ru);self.assertEqual(none,'');self.assertIn('base strategy',en);self.assertEqual(failed,'');self.assertEqual(pending,'')

    def test_ui_does_not_describe_failed_or_cancelled_search_as_a_completed_recommendation(self):
        node=os.environ.get('NODE_BINARY') or shutil.which('node')
        if not node:self.skipTest('Node runtime is unavailable')
        script="""import {jobView} from './picker.js';console.log(JSON.stringify(['failed','cancelled','recovery_required','running','completed'].map(state=>jobView({state,phase:'complete',restored:true,winner:'stale'},'ru'))));"""
        r=subprocess.run([str(node),'--input-type=module','-e',script],cwd=PUBLIC/'strategy-picker',capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        failed,cancelled,recovery,active,completed=json.loads(r.stdout)
        self.assertIn('не завершён',failed['phase']);self.assertIn('не завершён',failed['noWinner'])
        self.assertIn('Остановлен пользователем',cancelled['phase']);self.assertIn('не подтверждено',recovery['phase'])
        self.assertTrue(all(not x['showWinner']for x in [failed,cancelled,recovery,active]))
        self.assertEqual(active['noWinner'],'');self.assertTrue(completed['showWinner'])

    def test_start_confirmation_names_the_exact_service_set_and_search_mode(self):
        node=os.environ.get('NODE_BINARY') or shutil.which('node')
        if not node:self.skipTest('Node runtime is unavailable')
        script="""import {selectionDescription,searchDescription} from './picker.js';const goals=['youtube','discord','instagram','youtube,discord','youtube,instagram','discord,instagram','youtube,discord,instagram','all'];console.log(JSON.stringify({rows:goals.map(goal=>selectionDescription(goal,'synthesis','ru')),profiles:selectionDescription('discord','profiles','en'),generator:searchDescription('synthesis','ru'),catalog:searchDescription('profiles','ru')}));"""
        r=subprocess.run([str(node),'--input-type=module','-e',script],cwd=PUBLIC/'strategy-picker',capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);v=json.loads(r.stdout)
        self.assertRegex(v['generator'],r'(?i)бета')
        self.assertNotRegex(v['profiles']+' '+v['catalog'],r'(?i)beta|бета')
        for row,names in zip(v['rows'],[['YouTube'],['Discord'],['Instagram'],['YouTube','Discord'],['YouTube','Instagram'],['Discord','Instagram'],['YouTube','Discord','Instagram'],['все сервисы']]):
            self.assertIn('Разработать стратегию',row)
            for name in names:self.assertIn(name,row)
        self.assertIn('existing profiles',v['profiles']);self.assertIn('Discord',v['profiles'])
        self.assertIn('Каталог готовых стратегий не требуется',v['generator']);self.assertIn('каталога',v['catalog'])
        self.assertNotIn('ему не нужен',v['catalog'])

    def test_export_is_one_importable_bundle_with_exact_dependencies_only(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$root=$argv[2];foreach(['lists','lua','blobs']as $kind)mkdir($root.'/'.$kind);$files=['lua/zapret-lib.lua'=>'std lib','lua/zapret-antidpi.lua'=>'std antidpi','lists/synthesis-user.list'=>"youtube.com\\n",'lists/synthesis-auto.list'=>'','lists/synthesis-exclude.list'=>"t.me\\n",'lists/personal.list'=>'MUST_NOT_EXPORT'];$hashes=[];foreach($files as $name=>$raw){file_put_contents($root.'/'.$name,$raw);chmod($root.'/'.$name,0644);$hashes[$name]=hash('sha256',$raw);}$entry=['files'=>$hashes,'mutable_files'=>['lists/synthesis-auto.list'],'config'=>NfqwsStrategySynthesis::compile(NfqwsStrategySynthesis::blank())+['NFQWS_BASE_ARGS'=>'--lua-init=@'.$root.'/lua/zapret-lib.lua --lua-init=@'.$root.'/lua/zapret-antidpi.lua','NFQWS_EXTRA_ARGS'=>'--hostlist='.$root.'/lists/synthesis-user.list --hostlist-auto='.$root.'/lists/synthesis-auto.list --hostlist-exclude='.$root.'/lists/synthesis-exclude.list','NFQWS_ARGS_IPSET'=>'','TCP_PORTS'=>'80,443','UDP_PORTS'=>'443']];$seed=NfqwsStrategyPickerResources::snapshotMutable($entry,$root,getmyuid());$b=NfqwsStrategySynthesisExport::bundle($entry,$root,$seed,getmyuid());$doc=AsusImportDocument::read([$b['raw']]);$r=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];$entry['config']=NfqwsStrategySynthesis::bind($r,$entry['config']);$entry['synthesis_recipe']=$r;$addon=NfqwsStrategySynthesisExport::bundle($entry,$root,$seed,getmyuid(),true);$adoc=AsusImportDocument::read([$addon['raw']]);echo json_encode([count($doc['resources']),array_column($doc['resources'],'name'),strpos($b['raw'],'MUST_NOT_EXPORT')===false,array_column($doc['dependencies'],'included'),count($adoc['resources']),array_column($adoc['dependencies'],'included'),in_array('--comment=nfqws2-synthesis-trackers',explode(' ',$adoc['values']['NFQWS_ARGS']),true),preg_match('/beta|бета/iu',base64_decode(json_decode($addon['raw'],true)['files'][0]['data_base64']))===0]);""")
        self.assertEqual(r[0],5)
        self.assertNotIn('personal.list',r[1])
        self.assertTrue(r[2]);self.assertTrue(all(r[3]));self.assertEqual(r[4],5);self.assertTrue(all(r[5]));self.assertTrue(r[6]);self.assertTrue(r[7])

    @unittest.skipUnless(os.environ.get('NFQWS_TEST_ENGINE_DIR'),'Requires pinned MAIN engine')
    def test_bound_window_override_registers_exclusion_once_in_actual_MAIN_engine(self):
        # Break caught: inserting exclusions before both payload phases makes
        # the pinned engine reject the repeated hostlist within one profile.
        program=self.php(r"""$r=NfqwsStrategySynthesis::blank();
        $r['tls']=['method'=>'multisplit','pos'=>'1,midsld','fake'=>true,'fooling'=>'seq','repeats'=>2];
        $r['quic']=['method'=>'fake','repeats'=>2];$r['overrides']=[
          ['protocol'=>'tls','domains'=>['www.youtube.com'],'component'=>['method'=>'multidisorder',
          'pos'=>'1,sniext+1,host+1,midsld-2,midsld,midsld+2,endhost-1','window'=>1]],
          ['protocol'=>'tls','domains'=>['browserleaks.com'],'component'=>['method'=>'pass']],
          ['protocol'=>'quic','domains'=>['holod.media','www.facebook.com'],'component'=>['method'=>'fake','fooling'=>'autottl','repeats'=>6]],
          ['protocol'=>'quic','domains'=>['www.youtube.com'],'component'=>['method'=>'fake','repeats'=>6]]];
        echo json_encode(NfqwsStrategySynthesis::bind($r,['NFQWS_BASE_ARGS'=>'',
          'NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/nfqws-test-user.list --hostlist-exclude=/tmp/nfqws-test-exclude.list']));""")
        root=Path(os.environ['NFQWS_TEST_ENGINE_DIR'])
        binary=root/'nfqws2-aarch64'
        with binary.open('rb') as f:
            elf=f.read(20)
        self.assertEqual(elf[:6],b'\x7fELF\x02\x01')
        self.assertEqual(int.from_bytes(elf[18:20],'little'),183)  # ELF EM_AARCH64
        prefix=[str(Path(os.environ['NFQWS_TEST_QEMU_DIR'])/'qemu-aarch64'),str(binary)]
        args=' --new '.join([program['NFQWS_ARGS_CUSTOM'],
            program['NFQWS_ARGS']+' '+program['NFQWS_EXTRA_ARGS'],
            program['NFQWS_ARGS_QUIC']+' '+program['NFQWS_EXTRA_ARGS']])
        with tempfile.TemporaryDirectory() as directory:
            for name,contents in [('user','www.youtube.com\n'),('exclude','telegram.org\n')]:
                path=Path(directory)/(name+'.list');path.write_text(contents)
                args=args.replace('/tmp/nfqws-test-'+name+'.list',str(path))
            run=subprocess.run(prefix+['--qnum=0','--dry-run','--ipcache-hostname',
                '--lua-init=@'+str(root/'lua/zapret-lib.lua'),
                '--lua-init=@'+str(root/'lua/zapret-antidpi.lua')]+shlex.split(args),
                capture_output=True,text=True,timeout=20)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        window_profile=program['NFQWS_ARGS_CUSTOM'].split(' --new ')[0]
        self.assertEqual(window_profile.count('--hostlist-exclude='),1)
        self.assertIn('--payload=all',window_profile)
        self.assertIn('--payload=tls_client_hello',window_profile)

    @unittest.skipUnless(os.environ.get('NFQWS_TEST_ENGINE_DIR'),'Requires pinned engine')
    def test_new_from_scratch_queue_parses_in_the_actual_MAIN_engine(self):
        programs=self.php(r"""$cell=['http'=>false,'tls12'=>false,'tls13'=>false,'quic'=>false];$sample=['domains'=>['failed.example'=>$cell]];
        $base=['NFQWS_ARGS'=>'--filter-tcp=80,443 --lua-desync=multisplit:pos=2','NFQWS_ARGS_QUIC'=>'--filter-udp=443 --lua-desync=fake:repeats=4',
          'NFQWS_ARGS_CUSTOM'=>'','NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/nfqws-test-user.list --hostlist-exclude=/tmp/nfqws-test-exclude.list'];
        $out=[];foreach(NfqwsStrategySynthesis::queue(['max_repeats'=>6],[],[],null)as $recipe)$out[]=NfqwsStrategySynthesis::bind($recipe,$base);
        echo json_encode($out);""")
        root=Path(os.environ['NFQWS_TEST_ENGINE_DIR']);family=os.environ.get('NFQWS_TEST_ENGINE_FAMILY','x86_64')
        self.assertIn(family,['x86_64','aarch64'])
        prefix=([str(Path(os.environ['NFQWS_TEST_QEMU_DIR'])/'qemu-aarch64')] if family=='aarch64' else [])+[str(root/('nfqws2-'+family))]
        self.assertEqual(len(programs),24)
        with tempfile.TemporaryDirectory() as directory:
            for name in ['user','exclude']:
                (Path(directory)/(name+'.list')).write_text('failed.example\n')
            for i,program in enumerate(programs):
                args=' --new '.join(program[k] for k in ['NFQWS_ARGS_CUSTOM','NFQWS_ARGS','NFQWS_ARGS_QUIC'] if program.get(k))
                for name in ['user','exclude']:
                    args=args.replace('/tmp/nfqws-test-'+name+'.list',str(Path(directory)/(name+'.list')))
                flags=['--ipcache-hostname'] if '--ipcache-hostname' in program.get('NFQWS_BASE_ARGS','') else []
                run=subprocess.run(prefix+['--qnum=0','--dry-run',
                    '--lua-init=@'+str(root/'lua/zapret-lib.lua'),'--lua-init=@'+str(root/'lua/zapret-antidpi.lua'),
                    *flags,*shlex.split(args)],capture_output=True,text=True,timeout=20)
                self.assertEqual(run.returncode,0,str(i)+run.stdout+run.stderr)

    @unittest.skipUnless(os.environ.get('NFQWS_TEST_ENGINE_DIR'),'Requires pinned engine')
    def test_matrix_and_feedback_programs_parse_in_the_actual_engine(self):
        programs=self.php("""$m=NfqwsStrategySynthesis::matrix(['max_repeats'=>6]);$out=[];foreach($m['initial']as $r){$p=NfqwsStrategySynthesis::compile($r);$out[]=$p;if($r['tls']['method']==='pass')continue;$c=NfqwsStrategySynthesis::bind($r,['NFQWS_EXTRA_ARGS'=>'--hostlist=/tmp/nfqws-test-user.list --hostlist-exclude=/tmp/nfqws-test-exclude.list']);$a=NfqwsStrategySynthesis::torrentSites($c,$r);$p['NFQWS_ARGS']=explode(' --new ',$a['NFQWS_ARGS'])[1];$out[]=$p;}$s=['targets'=>'a','metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>1,'total'=>2]),'domains'=>[]];foreach(NfqwsStrategySynthesis::refine([['recipe'=>$m['initial'][0],'runs'=>[$s]]],['max_repeats'=>6])as $r)$out[]=NfqwsStrategySynthesis::compile($r);echo json_encode($out);""")
        root=Path(os.environ['NFQWS_TEST_ENGINE_DIR']);engine=root/'nfqws2-x86_64'
        families={'x86_64':None}
        qemu=os.environ.get('NFQWS_TEST_QEMU_DIR')
        if qemu:families.update({'armv7':'arm','aarch64':'aarch64','mips':'mips','mipsel':'mipsel','mips64':'mips64','x86':'i386'})
        only=os.environ.get('NFQWS_TEST_ENGINE_FAMILY')
        if only:
            self.assertIn(only,families);families={only:families[only]}
        for family,emulator in families.items():
            prefix=([str(Path(qemu)/('qemu-'+emulator))] if emulator else [])+[str(root/('nfqws2-'+family))]
            for i,p in enumerate(programs):
                args=' --new '.join(x for x in [p['NFQWS_ARGS_CUSTOM'],p['NFQWS_ARGS'],p['NFQWS_ARGS_QUIC']] if x)
                run=subprocess.run(prefix+['--qnum=0','--dry-run','--lua-init=@'+str(root/'lua/zapret-lib.lua'),'--lua-init=@'+str(root/'lua/zapret-antidpi.lua')]+shlex.split(args),capture_output=True,text=True,timeout=20)
                self.assertEqual(run.returncode,0,family+' '+str(i)+run.stdout+run.stderr)


if __name__ == '__main__':
    unittest.main()
