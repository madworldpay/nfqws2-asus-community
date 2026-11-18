"""Trial-to-original-probe capture plumbing; LOCAL files, modeled actors/engine.

No supplement post-plan trial, live collector, media test or native authority.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC
from test_strategy_supplement import BASE, RECIPE


class SynthesisNativeCallbackTests(unittest.TestCase):
    def setUp(self):
        artifacts = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifacts:
            self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=artifacts))
        else:
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            self.root = Path(temp.name)

    def call(self, fault='', ordinary=False, pair=False):
        runtime = (PUBLIC/'strategy-picker-runtime.php').read_text()
        start = runtime.index('    private function probe(')
        end = runtime.index('    private function stopOwnedProbe()', start)
        probe = runtime[start:end]
        # The exact original body is retained; only its name changes so that
        # this harness can inject its actual LOCAL AsusDpiJobs dependency.
        boot = r'''require_once $argv[1].'/strategy-picker-runtime.php';
        require dirname($argv[1],3).'/tests/fixtures/picker-library.php';
        $method=new ReflectionMethod('NfqwsStrategySynthesisRuntime','synthesisTrial');
        if($method->getNumberOfParameters()<6){echo json_encode(['missing_api'=>true]);exit;}
        final class TrialNativeGateDouble {public function idle(callable $fn):mixed{return $fn();}}
        final class TrialNativeHarness {
          use NfqwsStrategySynthesisRuntime;
          public array $events=[];
          public function __construct(public $store,public $config,public $jobs,public string $root){}
          private function checkpoint():void {$this->events[]='checkpoint';}
          private function synthesisCustom(array $j):bool{return false;}
          private function phase(string $phase,array $extra=[]):void {
            $this->events[]=$phase;$this->store->write(array_replace($this->store->read(),['phase'=>$phase],$extra));}
          private function service(string $action):void {$this->events[]='service-'.$action;}
          private function resetAuto(array $entry):void {$this->events[]='reset-model-AUTO';}
          private function resourcesFingerprint():string{return hash_file('sha256',$this->root.'/resource');}
          private function candidate(array $entry):string {
            return NfqwsStrategyPickerConfig::candidate(base64_decode($this->store->read()['original'],true),$entry['config']);}
          private function probe(array $groups,?callable $sink=null,?AsusDpiJobs $jobs=null,?callable $beforeNative=null):array{return $this->sourceProbe($groups,$sink,$jobs??$this->jobs,$beforeNative);}
          public function run(array $entry,?array $recipe,?callable $sink,bool $warm):array {
            return $this->synthesisTrial($entry,'LOCAL trial',$recipe,2,$warm,$sink);}
        '''+probe.replace('private function probe(', 'private function sourceProbe(', 1)+r'''}
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$root=$argv[2];$uid=(int)$argv[3];
        file_put_contents($root.'/config',$d['base']);chmod($root.'/config',0640);
        file_put_contents($root.'/resource','LOCAL resource fingerprint model');
        $parent=new NfqwsStrategyPickerState($root.'/picker',$uid,$root.'/profile-config');
        $config=new NfqwsStrategyPickerConfig($parent,$root.'/config',$uid);$j=$config->snapshot(false);
        $j=array_replace($j,['state'=>'running','phase'=>'measuring_1','request_id'=>str_repeat('b',32),
          'deadline'=>AsusUpdateStore::uptime()+120,'resources_sha256'=>hash_file('sha256',$root.'/resource'),
          'budget'=>['concurrency'=>2,'probe_seconds'=>30,'group_seconds'=>15]]);$parent->write($j);
        $s=new AsusDpiStore($root.'/dpi',$uid);$launches=[];$captures=[];$profiles=[];
        $native=['state'=>'completed','coverage'=>['domains'=>2,'tcp'=>1],
          'context'=>['before'=>['scope'=>'LOCAL DNS/scope model'],'after'=>['scope'=>'LOCAL DNS/scope model']],
          'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>[
            ['domain'=>'youtube.com','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'quic_ok'],
            ['domain'=>'target.example','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'quic_ok']]]]],
            ['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'LOCAL_TCP','status'=>'ok','port'=>443]]]]]]];
        if($d['fault']==='score')$native['context']['after']['scope']='CHANGED_CONTEXT_MODEL';
        $jobs=new AsusDpiJobs($s,['installed'=>fn()=>true,'available'=>fn()=>['available'=>true],
          'terminal_gate'=>new TrialNativeGateDouble(),
          'launch'=>function($id,$kind)use($s,$native,$d,&$launches){$launches[]=$id;
            $s->update($id,['state'=>'running']);$s->update($id,['state'=>'completed',
              'native'=>$d['fault']==='json'?'INVALID_NATIVE_JSON':json_encode($native)]);}]);
        $h=new TrialNativeHarness($parent,$config,$jobs,$root);
        $sink=function(array $snapshot,array $input)use($root,$parent,$config,$d,&$captures){
          // Actual local file capture/readback models only the transport sink.
          $path=$root.'/capture-'.count($captures).'.raw';$f=fopen($path,'xb');
          fwrite($f,$snapshot['native']['raw']);fflush($f);fsync($f);fclose($f);
          if(file_get_contents($path)!==$snapshot['native']['raw'])throw new RuntimeException('FIXTURE_CAPTURE_READBACK');
          $captures[]=['snapshot'=>$snapshot,'input'=>$input,'actual_config_sha256'=>hash('sha256',$config->raw())];
          if($d['fault']==='sink')throw new RuntimeException('FIXTURE_SINK_FAILURE');
          if($d['fault']==='parent'){$j=$parent->read();$j['request_id']='FOREIGN';$parent->write($j);}
        };
        $out=[];
        try{
          $entry=pickerFixtureProfile($parent);
          $profiles[]=$h->run($entry,null,$d['ordinary']?null:$sink,$d['fault']!=='score');
          if($d['pair'])$profiles[]=$h->run($entry,$d['recipe'],$sink,true);
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $out+=['profiles'=>$profiles,'captures'=>$captures,'launches'=>$launches,'events'=>$h->events,
          'parent'=>$parent->read(),'retained'=>$s->status(),'config'=>base64_encode($config->raw())];
        echo json_encode($out,JSON_THROW_ON_ERROR);
        '''
        request = json.dumps({'base': BASE, 'recipe': RECIPE, 'fault': fault,
                              'ordinary': ordinary, 'pair': pair}).encode()
        (self.root/'original-probe-method.private').write_text(probe)
        (self.root/'php-r.private').write_text(boot)
        (self.root/'request.private.json').write_bytes(request)
        result = subprocess.run([PHP, '-n', '-r', boot, str(PUBLIC), str(self.root), str(os.getuid())],
                                input=request, capture_output=True, timeout=30)
        (self.root/'stdout.private').write_bytes(result.stdout)
        (self.root/'stderr.private').write_bytes(result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        value = json.loads(result.stdout)
        self.assertFalse(value.get('missing_api'), 'missing original synthesis trial capture callback')
        return value

    def test_all_six_warm_and_measured_raws_survive_three_job_retention(self):
        value = self.call(pair=True)
        self.assertNotIn('error', value)
        self.assertEqual(len(value['profiles']), 2)
        self.assertEqual(len(value['captures']), 6)
        self.assertEqual(len(set(value['launches'])), 6)
        self.assertEqual(len(value['retained']['history']), 3)
        requests = []
        for index, capture in enumerate(value['captures']):
            snapshot, binding = capture['snapshot'], capture['input']
            requests.append(snapshot['job']['request_id'])
            raw = (self.root/f'capture-{index}.raw').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), snapshot['native']['sha256'])
            self.assertEqual(binding['config_sha256'], capture['actual_config_sha256'])
            self.assertEqual(binding['config_sha256'], value['profiles'][index//3]['config_sha256'])
            self.assertEqual(binding['parent_id'], value['parent']['id'])
            self.assertEqual(binding['parent_request_id'], 'b'*32)
            self.assertEqual(binding['warmup'], index%3 == 0)
            self.assertEqual(binding['repeat'], None if index%3 == 0 else index%3)
            self.assertEqual(binding['source'], 'current' if index<3 else 'synthesis')
            self.assertEqual(binding['resource_binding_scope'], 'existing_fingerprint_excludes_mutable_AUTO')
            self.assertNotIn('can_apply', binding)
            self.assertNotIn('accepted', binding)
        self.assertEqual(len(set(requests)), 6)
        self.assertNotEqual(value['profiles'][0]['config_sha256'], value['profiles'][1]['config_sha256'])
        self.assertEqual(len(value['profiles'][0]['runs']), 2)
        self.assertEqual(len(value['profiles'][1]['runs']), 2)

    def test_sink_failure_preserves_first_raw_and_aborts_without_next_repeat(self):
        value = self.call('sink')
        self.assertEqual(value['error'], 'FIXTURE_SINK_FAILURE')
        self.assertEqual(len(value['captures']), 1)
        self.assertEqual(len(value['launches']), 1)
        self.assertEqual(value['profiles'], [])

    def test_malformed_raw_is_captured_before_decode_rejection(self):
        value = self.call('json')
        self.assertIn('error', value)
        self.assertEqual((self.root/'capture-0.raw').read_bytes(), b'INVALID_NATIVE_JSON')
        self.assertEqual(len(value['launches']), 1)
        self.assertEqual(value['profiles'], [])

    def test_parent_post_callback_drift_preserves_capture_but_no_profile(self):
        value = self.call('parent')
        self.assertEqual(value['error'], 'source_changed')
        self.assertEqual(len(value['captures']), 1)
        self.assertEqual(len(value['launches']), 1)
        self.assertEqual(value['parent']['request_id'], 'FOREIGN')
        self.assertEqual(value['profiles'], [])

    def test_score_rejection_does_not_turn_capture_into_accepted_profile(self):
        value = self.call('score')
        self.assertEqual(value['error'], 'incomparable_result')
        self.assertEqual(len(value['captures']), 1)
        self.assertEqual(len(value['launches']), 1)
        self.assertEqual(value['profiles'], [])

    def test_optional_null_keeps_existing_trial_without_source_captures(self):
        value = self.call(ordinary=True)
        self.assertNotIn('error', value)
        self.assertEqual(value['captures'], [])
        self.assertEqual(len(value['launches']), 3)
        self.assertEqual(len(value['profiles'][0]['runs']), 2)


if __name__ == '__main__':
    unittest.main()
