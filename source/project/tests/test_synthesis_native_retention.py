"""Real LOCAL depot in original trial/probe callbacks; guard/engine are doubles."""
import hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
from test_strategy_supplement import BASE,RECIPE

class SynthesisNativeRetentionTests(unittest.TestCase):
    def call(self,fault='',trials=1,external_before=True,sink=True,recipe=False):
        artifacts=os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifacts:root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=artifacts))
        else:
            temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        source=(PUBLIC/'strategy-picker-runtime.php').read_text();start=source.index('    private function probe(');end=source.index('    private function stopOwnedProbe()',start);probe=source[start:end]
        code=r'''require_once $argv[1].'/strategy-picker-runtime.php';
        require dirname($argv[1],3).'/tests/fixtures/picker-library.php';
        final class IntegratedTerminalDouble {public function idle(callable $fn):mixed{return $fn();}}
        final class IntegratedTrialHarness {
          use NfqwsStrategySynthesisRuntime;
          public array $events=[];public bool $lost=false;
          public function __construct(public $store,public $config,public $jobs,public string $root){}
          private function checkpoint():void {if($this->lost)throw new RuntimeException('guard_lost');}
          private function synthesisCustom(array $j):bool{return false;}
          private function phase(string $phase,array $extra=[]):void {$this->store->write(array_replace($this->store->read(),['phase'=>$phase],$extra));}
          private function service(string $action):void {$this->events[]='service-'.$action;}
          private function resetAuto(array $entry):void {$this->events[]='reset-AUTO-DOUBLE';}
          private function resourcesFingerprint():string{return hash_file('sha256',$this->root.'/resource');}
          private function candidate(array $entry):string{return NfqwsStrategyPickerConfig::candidate(base64_decode($this->store->read()['original'],true),$entry['config']);}
          private function probe(array $groups,?callable $sink=null,?AsusDpiJobs $jobs=null,?callable $before=null):array {return $this->sourceProbe($groups,$sink,$jobs??$this->jobs,$before);}
          public function run(array $entry,?array $recipe,?callable $sink,?callable $before):array {return $this->synthesisTrial($entry,'LOCAL integrated retained trial',$recipe,2,true,$sink,$before);}
        '''+probe.replace('private function probe(','private function sourceProbe(',1)+r'''}
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$root=$argv[2];$uid=(int)$argv[3];
        file_put_contents($root.'/config',$d['base']);chmod($root.'/config',0640);file_put_contents($root.'/resource','LOCAL resource');
        $parent=new NfqwsStrategyPickerState($root.'/picker',$uid,$root.'/profile-config');$config=new NfqwsStrategyPickerConfig($parent,$root.'/config',$uid);
        $j=$config->snapshot(false);$j=array_replace($j,['state'=>'running','phase'=>'measuring_1','request_id'=>str_repeat('b',32),
          'deadline'=>AsusUpdateStore::uptime()+120,'resources_sha256'=>hash_file('sha256',$root.'/resource'),
          'budget'=>['concurrency'=>2,'probe_seconds'=>30,'group_seconds'=>15]]);$parent->write($j);
        $store=new AsusDpiStore($root.'/dpi',$uid);$launches=[];$preflights=[];$observed=[];$sources=[];
        $native=['state'=>'completed','coverage'=>['domains'=>1,'tcp'=>1],
          'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>[['domain'=>'youtube.com','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'quic_ok']]]]],
            ['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'LOCAL_TCP','status'=>'ok']]]]]]];
        $body=$d['fault']==='malformed'?'{malformed native body':json_encode($native,JSON_THROW_ON_ERROR);
        $jobs=new AsusDpiJobs($store,['installed'=>fn()=>true,'available'=>fn()=>['available'=>true],'terminal_gate'=>new IntegratedTerminalDouble(),
          'launch'=>function($id,$kind)use($store,$parent,$root,$body,$d,&$launches){
            $db=json_decode(file_get_contents($root.'/dpi/jobs.json'),true);$request=$db['jobs'][$id]['request_id'];
            $prefix=$root.'/picker/native-'.$parent->read()['id'].'-'.$request;
            if($d['sink']){
              if(!is_file($prefix.'.intent.json'))throw new RuntimeException('MISSING_SOURCE_DEPOT_BEFORE_INPUT');
              $intent=json_decode(file_get_contents($prefix.'.intent.json'),true,32,JSON_THROW_ON_ERROR);
              foreach(['slot','capture']as $kind){$path=$root.'/picker/'.$intent[$kind]['name'];$s=lstat($path);
                if($s['ino']!==$intent[$kind]['metadata']['ino']||hash_file('sha256',$path)!==$intent[$kind]['sha256'])throw new RuntimeException('WRONG_RESERVED_INODE_BEFORE_INPUT');}
              $launches[]=['id'=>$id,'request'=>$request,'intent_sha256'=>hash_file('sha256',$prefix.'.intent.json')];
            }else $launches[]=['id'=>$id,'request'=>$request,'depot'=>'NOT_REQUESTED'];
            $store->update($id,['state'=>'running']);$store->update($id,['state'=>'completed','native'=>$body]);}]);
        $h=new IntegratedTrialHarness($parent,$config,$jobs,$root);
        $before=function(string $request,array $input)use($root,$parent,$h,$d,&$preflights){
          $path=$root.'/picker/native-'.$input['parent_id'].'-'.$request.'.intent.json';
          if(!is_file($path))throw new RuntimeException('MISSING_SOURCE_DEPOT_BEFORE_EXTERNAL_PREFLIGHT');
          $intent=json_decode(file_get_contents($path),true,32,JSON_THROW_ON_ERROR);
          $db=is_file($root.'/dpi/jobs.json')?json_decode(file_get_contents($root.'/dpi/jobs.json'),true):['jobs'=>[]];
          foreach($db['jobs']as $job)if($job['request_id']===$request)throw new RuntimeException('INPUT_ALREADY_CREATED_BEFORE_PREFLIGHT');
          $preflights[]=['request'=>$request,'input'=>$input,'intent'=>$intent,'jobs_before'=>count($db['jobs'])];
          if($d['fault']==='before_failure')throw new RuntimeException('EXTERNAL_PREFLIGHT_FAILURE');
          if($d['fault']==='guard')$h->lost=true;
          if($d['fault']==='return_true')return true;
          if($d['fault']==='return_false')return false;
          return null;
        };
        $sink=function(array $snapshot,array $input)use($root,$d,&$observed,&$sources){
          $path=$root.'/source-'.count($sources).'.json';file_put_contents($path,json_encode($snapshot,JSON_THROW_ON_ERROR));$sources[]=$path;
          $capture=$root.'/picker/native-'.$input['parent_id'].'-'.$snapshot['job']['request_id'].'.capture.json';
          if(!is_file($capture))throw new RuntimeException('MISSING_SOURCE_DEPOT_BEFORE_OBSERVER');
          $record=json_decode(file_get_contents($capture),true,32,JSON_THROW_ON_ERROR);
          if(($record['state']??null)!=='captured_unaccepted')throw new RuntimeException('SOURCE_NOT_CAPTURED_BEFORE_OBSERVER');
          $observed[]=['input'=>$input,'capture'=>$record,'source_file'=>$path];
          if($d['fault']==='observer')throw new RuntimeException('EXTERNAL_OBSERVER_FAILURE');
        };
        $out=['profiles'=>[]];try{
          $j=$parent->read();$j['library_namespace']='job-v1';$parent->write($j);
          $entry=pickerFixtureProfile($parent,$d['fault']==='stock');
          if($d['fault']==='missing_profile')$entry['id']='saved-0000000000000000';
          if($d['fault']==='malformed_profile')$entry['id']='saved-../123456789ab';
          if($d['fault']==='switched_profile'){$j=$parent->read();$j['trial_profile']='stock';$parent->write($j);}
          for($i=0;$i<$d['trials'];++$i){$recipe=$d['recipe']&&$i%2===1?$d['recipe_value']:null;
            $out['profiles'][]=$h->run($entry,$recipe,$d['sink']?$sink:null,$d['external_before']?$before:null);}
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $captures=[];foreach(glob($root.'/picker/native-*.capture.json')?:[]as $path)$captures[]=json_decode(file_get_contents($path),true,32,JSON_THROW_ON_ERROR);
        $db=is_file($root.'/dpi/jobs.json')?json_decode(file_get_contents($root.'/dpi/jobs.json'),true):['jobs'=>[]];
        echo json_encode($out+['preflights'=>$preflights,'observed'=>$observed,'sources'=>$sources,'launches'=>$launches,'captures'=>$captures,
          'db'=>$db,'parent'=>$parent->read(),'config'=>$config->raw(),'events'=>$h->events],JSON_THROW_ON_ERROR);'''
        data={'base':BASE,'recipe_value':RECIPE,'fault':fault,'trials':trials,'external_before':external_before,'sink':sink,'recipe':recipe}
        request=json.dumps(data).encode();(root/'php-r.private').write_text(code);(root/'request.private.json').write_bytes(request);(root/'original-probe-method.private').write_text(probe)
        result=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],input=request,capture_output=True,timeout=30)
        (root/'stdout.private').write_bytes(result.stdout);(root/'stderr.private').write_bytes(result.stderr)
        self.assertEqual((result.returncode,result.stderr),(0,b''),result.stdout.decode()+result.stderr.decode())
        return json.loads(result.stdout),root

    def rederive(self,value,root):
        for observer in value['observed']:
            record=observer['capture'];snapshot=json.loads(Path(observer['source_file']).read_text());data=(root/'picker'/record['slot']['name']).read_bytes()
            self.assertEqual(record['state'],'captured_unaccepted');self.assertIs(record['accepted'],False);self.assertEqual(hashlib.sha256(data).hexdigest(),record['slot']['sha256'])
            for kind in ['index','options','native']:
                a=record['artifacts'][kind];raw=snapshot[kind]['raw'].encode();self.assertEqual(data[a['offset']:a['offset']+a['bytes']],raw);self.assertEqual(hashlib.sha256(raw).hexdigest(),a['sha256'])
                self.assertEqual(a['source_metadata'],snapshot[kind]['metadata'])

    def test_diagnostics_bind_the_real_stock_or_saved_profile_to_the_sealed_measurement(self):
        for fault in ('stock',''):
            with self.subTest(fault=fault):
                result,_=self.call(fault=fault)
                self.assertNotIn('error',result)
                profile=result['profiles'][0]['id']
                if fault:self.assertEqual(profile,'stock')
                else:self.assertRegex(profile,r'^saved-[0-9a-f]{16}$')
                self.assertTrue(result['parent']['measured_results'][0]['document'])
                self.assertEqual([v['input']['profile_id'] for v in result['observed']],[profile]*3)
                self.assertTrue(all(v['state']=='captured_unaccepted' for v in result['captures']))

    def test_missing_malformed_or_switched_profile_is_refused_before_native_input(self):
        for fault,error in [('missing_profile','strategy_unavailable'),('malformed_profile','invalid_request'),('switched_profile','source_changed')]:
            with self.subTest(fault=fault):
                result,_=self.call(fault=fault)
                self.assertEqual(result.get('error'),error)
                self.assertEqual((result['launches'],result['captures']),([],[]))

    def test_two_real_trial_callback_chains_keep_six_frames_after_DPI_prunes_first_three(self):
        v,r=self.call(trials=2,recipe=True);self.assertNotIn('error',v);self.assertEqual(len(v['profiles']),2);self.assertEqual(len(v['launches']),6);self.assertEqual(len(v['observed']),6)
        self.assertEqual(len(v['db']['jobs']),3);self.assertEqual([p['jobs_before']for p in v['preflights']],[0,1,2,3,3,3]);self.assertEqual(v['config'],BASE)
        self.assertEqual([p['input']['recipe']for p in v['preflights'][:3]],[None]*3)
        for p in v['preflights'][3:]:self.assertRegex(p['input']['recipe'],r'^s-[a-f0-9]{16}$')
        self.rederive(v,r)

    def test_depot_is_real_even_without_an_external_preflight(self):
        v,r=self.call(external_before=False);self.assertNotIn('error',v);self.assertEqual(v['preflights'],[]);self.assertEqual(len(v['captures']),3);self.rederive(v,r)

    def test_external_observer_error_leaves_captured_original_buffers_and_stops_repeats(self):
        v,r=self.call(fault='observer');self.assertEqual(v.get('error'),'EXTERNAL_OBSERVER_FAILURE');self.assertEqual(len(v['launches']),1);self.assertEqual(len(v['observed']),1);self.assertEqual(v['profiles'],[]);self.rederive(v,r)

    def test_external_preflight_error_preserves_real_reservation_without_input(self):
        v,r=self.call(fault='before_failure');self.assertEqual(v.get('error'),'EXTERNAL_PREFLIGHT_FAILURE');self.assertEqual(v['launches'],[]);self.assertEqual(v['observed'],[])
        self.assertEqual(len(v['captures']),1);self.assertEqual(v['captures'][0]['state'],'capture_pending');self.assertEqual(v['db']['jobs'],[])

    def test_guard_loss_after_real_preallocation_refuses_before_input(self):
        v,r=self.call(fault='guard');self.assertEqual(v.get('error'),'guard_lost');self.assertEqual(v['launches'],[]);self.assertEqual(len(v['preflights']),1);self.assertEqual(v['captures'][0]['state'],'capture_pending')

    def test_malformed_native_JSON_is_retained_before_decode_and_never_scored(self):
        v,r=self.call(fault='malformed');self.assertIn('error',v);self.assertEqual(len(v['observed']),1);self.assertEqual(v['profiles'],[]);self.assertEqual(len(v['launches']),1);self.rederive(v,r)
        source=json.loads(Path(v['observed'][0]['source_file']).read_text());self.assertEqual(source['native']['raw'],'{malformed native body')

    def test_seventh_real_reservation_refuses_before_seventh_native_input(self):
        v,r=self.call(trials=3);self.assertEqual(v.get('error'),'output_limit');self.assertEqual(len(v['launches']),6);self.assertEqual(len(v['captures']),6);self.assertEqual(len(v['profiles']),2);self.rederive(v,r)

    def test_external_preflight_booleans_are_not_swallowed_by_real_reservation_wrapper(self):
        for fault in ['return_true','return_false']:
            with self.subTest(fault=fault):
                v,r=self.call(fault=fault);self.assertEqual(v.get('error'),'invalid_request');self.assertEqual(v['launches'],[]);self.assertEqual(v['captures'][0]['state'],'capture_pending')

    def test_ordinary_NULL_source_callback_does_not_create_a_depot(self):
        v,r=self.call(sink=False,external_before=False);self.assertNotIn('error',v);self.assertEqual(len(v['profiles']),1);self.assertEqual(len(v['launches']),3);self.assertEqual(v['captures'],[]);self.assertEqual(list((r/'picker').glob('native-*')),[])

if __name__=='__main__':unittest.main()
