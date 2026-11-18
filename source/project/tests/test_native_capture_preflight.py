"""Pre-input capture hook: actual LOCAL jobs/files, guard/retainer doubles.

No real ROOT capture reservation/provider or MAIN input is implemented here.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC
from test_strategy_supplement import BASE


class NativeCapturePreflightTests(unittest.TestCase):
    def setUp(self):
        artifacts = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifacts:
            self.temp = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=artifacts))
        else:
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            self.temp = Path(temp.name)
        self.count = 0

    def call(self, fault='', return_data=None, with_sink=True):
        self.count += 1
        root = self.temp/str(self.count); root.mkdir(mode=0o700)
        runtime = (PUBLIC/'strategy-picker-runtime.php').read_text()
        start = runtime.index('    private function probe(')
        end = runtime.index('    private function stopOwnedProbe()', start)
        probe = runtime[start:end]
        code = r'''require_once $argv[1].'/strategy-picker-runtime.php';
        require dirname($argv[1],3).'/tests/fixtures/picker-library.php';
        if((new ReflectionMethod('NfqwsStrategySynthesisRuntime','synthesisTrial'))->getNumberOfParameters()<7){
          echo json_encode(['missing_api'=>true]);exit;}
        final class PreflightGateDouble {public function idle(callable $fn):mixed{return $fn();}}
        final class PreflightTrialHarness {
          use NfqwsStrategySynthesisRuntime;
          public array $events=[];public bool $guardLost=false;
          public function __construct(public $store,public $config,public $jobs,public string $root){}
          private function checkpoint():void {$this->events[]='checkpoint';if($this->guardLost)throw new RuntimeException('guard_lost');}
          private function synthesisCustom(array $j):bool{return false;}
          private function phase(string $p,array $extra=[]):void {$this->events[]=$p;$this->store->write(array_replace($this->store->read(),['phase'=>$p],$extra));}
          private function service(string $action):void {$this->events[]='service-'.$action;}
          private function resetAuto(array $entry):void {$this->events[]='reset-model-AUTO';}
          private function resourcesFingerprint():string{return hash_file('sha256',$this->root.'/resource');}
          private function candidate(array $entry):string{return NfqwsStrategyPickerConfig::candidate(base64_decode($this->store->read()['original'],true),$entry['config']);}
          private function probe(array $groups,?callable $sink=null,?AsusDpiJobs $jobs=null,?callable $before=null):array {
            return $this->sourceProbe($groups,$sink,$jobs??$this->jobs,$before);}
          public function run(array $entry,?callable $sink,callable $before):array {
            return $this->synthesisTrial($entry,'LOCAL preflight trial',null,2,true,$sink,$before);}
        '''+probe.replace('private function probe(', 'private function sourceProbe(', 1)+r'''}
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$root=$argv[2];$uid=(int)$argv[3];
        file_put_contents($root.'/config',$d['base']);chmod($root.'/config',0640);file_put_contents($root.'/resource','LOCAL resource');
        $parent=new NfqwsStrategyPickerState($root.'/picker',$uid,$root.'/profile-config');$config=new NfqwsStrategyPickerConfig($parent,$root.'/config',$uid);
        $j=$config->snapshot(false);$j=array_replace($j,['state'=>'running','phase'=>'measuring_1','request_id'=>str_repeat('b',32),
          'deadline'=>AsusUpdateStore::uptime()+120,'resources_sha256'=>hash_file('sha256',$root.'/resource'),'budget'=>['concurrency'=>2,'probe_seconds'=>30,'group_seconds'=>15]]);$parent->write($j);
        $s=new AsusDpiStore($root.'/dpi',$uid);$launches=[];$intents=[];$captures=[];
        $native=['state'=>'completed','coverage'=>['domains'=>1,'tcp'=>1],
          'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>[
            ['domain'=>'youtube.com','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'quic_ok']]]]],
            ['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'LOCAL_TCP','status'=>'ok']]]]]]];
        $jobs=new AsusDpiJobs($s,['installed'=>fn()=>true,'available'=>fn()=>['available'=>true],'terminal_gate'=>new PreflightGateDouble(),
          'launch'=>function($id,$kind)use($root,$s,$native,&$launches){
            $db=json_decode(file_get_contents($root.'/dpi/jobs.json'),true);$request=$db['jobs'][$id]['request_id'];
            $raw=file_get_contents($root.'/native-intent-'.$request.'.json');$intent=json_decode($raw,true);
            if($intent['native_request']!==$request)throw new RuntimeException('FIXTURE_MISSING_PREFLIGHT_INTENT');
            $launches[]=['id'=>$id,'request'=>$request,'intent_sha256'=>hash('sha256',$raw)];
            $s->update($id,['state'=>'running']);$s->update($id,['state'=>'completed','native'=>json_encode($native)]);}]);
        $h=new PreflightTrialHarness($parent,$config,$jobs,$root);
        $before=function(string $request,array $input)use($root,$parent,$h,$d,&$intents){
          // This is the future retainer's explicit DOUBLE. The file, fsync,
          // directory fsync and readback below are actual LOCAL operations.
          $db=is_file($root.'/dpi/jobs.json')?json_decode(file_get_contents($root.'/dpi/jobs.json'),true):['jobs'=>[]];
          $value=['native_request'=>$request,'input'=>$input,'jobs_before_input'=>count($db['jobs'])];
          $raw=json_encode($value,JSON_THROW_ON_ERROR);$path=$root.'/native-intent-'.$request.'.json';
          $mask=umask(0077);try{$f=fopen($path,'xb');}finally{umask($mask);}
          fwrite($f,$raw);fflush($f);fsync($f);fclose($f);$dir=fopen($root,'r');fsync($dir);fclose($dir);
          if(file_get_contents($path)!==$raw)throw new RuntimeException('FIXTURE_INTENT_READBACK');
          $intents[]=$value+['sha256'=>hash('sha256',$raw)];$h->events[]='preflight';
          if($d['fault']==='failure')throw new RuntimeException('FIXTURE_CAPTURE_UNAVAILABLE');
          if($d['fault']==='guard')$h->guardLost=true;
          if($d['fault']==='config')file_put_contents($root.'/config','FOREIGN_CONFIG');
          if($d['fault']==='resource')file_put_contents($root.'/resource','FOREIGN_RESOURCE');
          if($d['fault']==='parent'){$j=$parent->read();$j['request_id']='FOREIGN_REQUEST';$parent->write($j);}
          return $d['return_data'];
        };
        $sink=function(array $snapshot,array $input)use($root,&$captures){
          $request=$snapshot['job']['request_id'];$intent=json_decode(file_get_contents($root.'/native-intent-'.$request.'.json'),true);
          if($intent['input']!==$input)throw new RuntimeException('FIXTURE_INTENT_CONTEXT_MISMATCH');
          $path=$root.'/captured-'.$request.'.raw';$f=fopen($path,'xb');fwrite($f,$snapshot['native']['raw']);fflush($f);fsync($f);fclose($f);
          if(file_get_contents($path)!==$snapshot['native']['raw'])throw new RuntimeException('FIXTURE_CAPTURE_READBACK');
          $captures[]=['snapshot'=>$snapshot,'input'=>$input];
        };
        $out=[];try{$out['profile']=$h->run(pickerFixtureProfile($parent),$d['with_sink']?$sink:null,$before);}
        catch(Throwable $e){$out['error']=$e->getMessage();}
        $db=is_file($root.'/dpi/jobs.json')?json_decode(file_get_contents($root.'/dpi/jobs.json'),true):['jobs'=>[]];
        echo json_encode($out+['intents'=>$intents,'captures'=>$captures,'launches'=>$launches,'events'=>$h->events,
          'parent'=>$parent->read(),'db'=>$db,'config'=>$config->raw(),'resource'=>file_get_contents($root.'/resource')],JSON_THROW_ON_ERROR);'''
        request = json.dumps({'base': BASE, 'fault': fault, 'return_data': return_data, 'with_sink': with_sink}).encode()
        (root/'original-probe-method.private').write_text(probe)
        (root/'php-r.private').write_text(code); (root/'request.private.json').write_bytes(request)
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(root), str(os.getuid())],
                                input=request, capture_output=True, timeout=30)
        (root/'stdout.private').write_bytes(result.stdout); (root/'stderr.private').write_bytes(result.stderr)
        self.assertEqual((result.returncode, result.stderr), (0, b''), result.stdout.decode()+result.stderr.decode())
        value = json.loads(result.stdout)
        self.assertFalse(value.get('missing_api'), 'missing trial -> original probe pre-input capture hook')
        return value, root

    def refused(self, fault, expected):
        value, root = self.call(fault)
        self.assertEqual(value.get('error'), expected, value)
        self.assertNotIn('profile', value)
        self.assertEqual(len(value['intents']), 1)
        self.assertEqual(value['captures'], []); self.assertEqual(value['launches'], [])
        self.assertEqual(value['db']['jobs'], [])
        self.assertEqual(len(list(root.glob('native-intent-*.json'))), 1)
        return value

    def test_each_warm_and_measured_input_has_its_own_durable_preflight_before_reserve(self):
        value, root = self.call()
        self.assertNotIn('error', value)
        self.assertEqual(len(value['profile']['runs']), 2)
        self.assertEqual(len(value['intents']), 3); self.assertEqual(len(value['launches']), 3)
        self.assertEqual(len(value['captures']), 3)
        self.assertEqual([v['jobs_before_input'] for v in value['intents']], [0, 1, 2])
        self.assertEqual([v['input']['repeat'] for v in value['intents']], [None, 1, 2])
        self.assertEqual([v['input']['warmup'] for v in value['intents']], [True, False, False])
        for intent, launch, capture in zip(value['intents'], value['launches'], value['captures']):
            self.assertEqual(intent['native_request'], launch['request'])
            self.assertEqual(intent['sha256'], launch['intent_sha256'])
            self.assertEqual(intent['native_request'], capture['snapshot']['job']['request_id'])
            self.assertEqual(intent['input'], capture['input'])
            raw = (root/('captured-'+intent['native_request']+'.raw')).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), capture['snapshot']['native']['sha256'])
        self.assertEqual(value['config'], BASE)

    def test_preflight_IO_failure_preserves_intent_without_any_native_input(self):
        self.refused('failure', 'FIXTURE_CAPTURE_UNAVAILABLE')

    def test_guard_loss_after_preflight_IO_refuses_before_any_native_input(self):
        self.refused('guard', 'guard_lost')

    def test_config_drift_during_preflight_is_preserved_and_no_native_input_occurs(self):
        value = self.refused('config', 'source_changed')
        self.assertEqual(value['config'], 'FOREIGN_CONFIG')

    def test_resource_drift_during_preflight_is_preserved_and_no_native_input_occurs(self):
        value = self.refused('resource', 'source_changed')
        self.assertEqual(value['resource'], 'FOREIGN_RESOURCE')

    def test_parent_drift_during_preflight_is_preserved_and_no_native_input_occurs(self):
        value = self.refused('parent', 'source_changed')
        self.assertEqual(value['parent']['request_id'], 'FOREIGN_REQUEST')

    def test_preflight_without_the_native_sink_refuses_before_service_actions(self):
        value, _ = self.call(with_sink=False)
        self.assertEqual(value.get('error'), 'invalid_request')
        self.assertEqual(value['intents'], []); self.assertEqual(value['launches'], [])
        self.assertFalse(any(v.startswith('service-') for v in value['events']))

    def test_preflight_returned_booleans_are_not_input_authority(self):
        for result in (True, False):
            with self.subTest(result=result):
                value, _ = self.call(return_data=result)
                self.assertEqual(value.get('error'), 'invalid_request')
                self.assertEqual(value['launches'], []); self.assertEqual(value['captures'], [])
                self.assertEqual(value['db']['jobs'], [])


if __name__ == '__main__':
    unittest.main()
