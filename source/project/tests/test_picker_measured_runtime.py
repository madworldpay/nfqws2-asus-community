"""Actual synthesis trial/State/Config and export bytes, local files only.

Service, Detector and native resource-admission context are explicit doubles.
These tests provide no actual device, restore or measured quality receipt.
"""
import json,os,subprocess,tempfile,unittest
from test_dpi_normalize import PHP,PUBLIC

CODE=r'''
umask(0077);require $argv[1].'/strategy-picker-runtime.php';$root=$argv[2];$uid=(int)$argv[3];$late=$argv[4]==='late';
foreach(['lists','lua','blobs']as $kind)mkdir($root.'/'.$kind);
$files=['lua/zapret-lib.lua'=>'LOCAL fixture library, never executed','lua/zapret-antidpi.lua'=>'LOCAL fixture antidpi, never executed',
 'lists/user.list'=>"youtube.com\n",'lists/AUTO'=>'','lists/exclude.list'=>"t.me\n"];$hashes=[];
foreach($files as $name=>$bytes){file_put_contents($root.'/'.$name,$bytes);chmod($root.'/'.$name,0644);$hashes[$name]=hash('sha256',$bytes);}
$values=NfqwsStrategySynthesis::compile(NfqwsStrategySynthesis::blank())+[
 'NFQWS_BASE_ARGS'=>'--lua-init=@'.$root.'/lua/zapret-lib.lua --lua-init=@'.$root.'/lua/zapret-antidpi.lua',
 'NFQWS_EXTRA_ARGS'=>'--hostlist='.$root.'/lists/user.list --hostlist-auto='.$root.'/lists/AUTO --hostlist-exclude='.$root.'/lists/exclude.list',
 'NFQWS_ARGS_IPSET'=>'','TCP_PORTS'=>'80,443','UDP_PORTS'=>'443'];
$entry=['id'=>'saved-0123456789abcdef','name'=>'Local measured program','files'=>$hashes,'mutable_files'=>['lists/AUTO'],'config'=>$values];
$configPath=$root.'/config';file_put_contents($configPath,NfqwsStrategyPickerConfig::candidate("# LOCAL original\n",$values));chmod($configPath,0664);
$s=new NfqwsStrategyPickerState($root.'/picker',$uid);$cfg=new NfqwsStrategyPickerConfig($s,$configPath,$uid);$j=$cfg->snapshot(false);
$j+=['request_id'=>str_repeat('b',32),'profiles'=>[],'budget'=>['concurrency'=>2],'resources_sha256'=>str_repeat('c',64),'goal'=>'all',
 'search'=>'synthesis','rounds'=>2,'series'=>['current'=>1,'total'=>2]];$j['state']='running';$j['phase']='discovering';$s->write($j);$id=$j['id'];
$h=new class($s,$cfg,$root,$late){use NfqwsStrategySynthesisRuntime;
 public int $stops=0;private int $trial=0;
 public function __construct(private $store,private $config,private string $root,private bool $late){}
 public function run(array $entry):array{
  $profile=$this->synthesisTrial($entry,'Local measured program',null,2,false);
  $this->synthesisRecord($profile,['eligible'=>false,'reason'=>'baseline','gain'=>0]);
  return $profile;
 }
 private function checkpoint():void{} // LOCAL source guard double, no live admission.
 private function resourcesFingerprint():string{return str_repeat('c',64);} // LOCAL immutable-resource context double.
 private function phase(string $phase,array $extra=[]):void{$this->store->write(array_replace($this->store->read(),$extra,['phase'=>$phase]));}
 private function service(string $action):void{if($action==='stop'&&++$this->stops===4&&$this->late)throw new RuntimeException('service_stop_failed');} // LOCAL actuator double.
 private function resetAuto(array $entry):void{$this->trial++;file_put_contents($this->root.'/lists/AUTO','');}
 private function candidate(array $entry):string{return NfqwsStrategyPickerConfig::candidate(base64_decode($this->store->read()['original'],true),$entry['config']);}
 private function probe(array $groups):array{ // LOCAL Detector data double; not a quality observation.
  file_put_contents($this->root.'/lists/AUTO','learned-round-'.$this->trial.".example\n");
  return ['state'=>'completed','coverage'=>['domains'=>1,'tcp'=>1],'groups'=>[
   ['group'=>2,'document'=>['results'=>['domain_inspection'=>[['domain'=>'youtube.com','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'quic_ok']]]]],
   ['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'LOCAL-FIXTURE','status'=>'ok']]]]]]];
 }
 private function synthesisMeasuredBundle(array $entry,array $profile):array{
  // The library-admission context is doubled here, while the snapshot,
  // exporter and import document are the real implementations over local files.
  $entry['config']=$profile['variant'];$seed=NfqwsStrategyPickerResources::snapshotMutable($entry,$this->root,$this->store->owner());
  $selection=NfqwsStrategyPickerRequest::selection(false,'all',true,
   NfqwsStrategyPickerRequest::custom('8.8.8.8','0'),'auto','2');
  $plan=NfqwsStrategyPickerConcurrency::plan('auto',NfqwsStrategyPickerBudget::coverDomains(
   NfqwsStrategyPickerBudget::choose(2,262144,0.0),1),[]);
  $mixed=array_replace($this->store->read(),$selection,['probe_domains'=>['youtube.com'],
   'budget'=>NfqwsStrategyPickerBudget::custom($plan['budget'],1),
   'concurrency_choice'=>NfqwsStrategyPickerConcurrency::record($plan),
   'selection_sha256'=>NfqwsStrategyPickerRequest::digest($selection)]);
  try{
   NfqwsStrategySynthesisExport::bundle($entry,$this->root,$seed,$this->store->owner(),false,$mixed);
   throw new RuntimeException('unscoped_generation_accepted');
  }catch(RuntimeException $e){if($e->getMessage()!=='synthesis_unverified')throw $e;}
  return NfqwsStrategySynthesisExport::measuredControl($entry,$this->root,$seed,$this->store->owner(),$mixed,$profile);
 }
};
$out=[];try{
 $h->run($entry);
 $next=$s->read();$next['series']['current']=2;$next['profiles']=[];$s->write($next);
 $h->run($entry);
}catch(Throwable $e){$out['late_error']=$e->getMessage();}
$cfg->restore();$j=$s->read();$j['state']='failed';$j['restored']=true;$j['code']=$out['late_error']??'LOCAL later failure';$s->write($j);$out['catalog']=$j['measured_results']??[];$out['documents']=[];
$picker=new NfqwsStrategyPickerRuntime($s,$cfg);
$select=static fn($command,$item,$job=null,$extra=[])=>$picker->dispatch($extra+['cmd'=>$command,'id'=>$job??$id,'result'=>$item,'csrf_token'=>'local-fixture']);
$expectError=static function($call){try{$call();return null;}catch(RuntimeException $e){return $e->getMessage();}};
foreach($out['catalog']as $item){
 $ref=$item['reference'];$artifact=$s->measuredResult($ref,$id);$view=$select('pickerresult',$item['id']);$document=null;$auto=[];
 if($view['can_export']){
  $export=$select('pickerexport',$item['id']);
  if(hash('sha256',$export['raw'])!==$export['sha256'])throw new RuntimeException('export_checksum');
  $document=AsusImportDocument::read([$export['raw']]);
 }else $out['unsealed_export']=$expectError(fn()=>$select('pickerexport',$item['id']));
 foreach($document['resources']??[]as $resource)if(str_contains($resource['name'],'AUTO'))$auto[]=base64_decode($resource['data_base64'],true);
 $out['documents'][]=['artifact'=>$artifact,'view'=>$view,'AUTO'=>$auto];}
$first=$out['catalog'][0]['id']??str_repeat('0',32);
$out['foreign_job']=$expectError(fn()=>$select('pickerresult',$first,str_repeat('9',32)));
$out['unmeasured_modifier']=$expectError(fn()=>$select('pickerexport',$first,null,['torrent_sites'=>'1']));
if(!$late&&count($out['catalog'])===2){
 $swapped=$j;$swapped['measured_results'][0]['document']=$j['measured_results'][1]['document'];$s->write($swapped);
 $out['wrong_document']=$expectError(fn()=>$select('pickerexport',$first));$s->write($j);
}
$out['actual_local_original_restored']=$cfg->raw()===base64_decode($s->read()['original'],true);echo json_encode($out,JSON_THROW_ON_ERROR);
'''

class MeasuredRuntimeTests(unittest.TestCase):
    def run_fixture(self,late=False):
        with tempfile.TemporaryDirectory(prefix='measured-trial-',dir=os.environ.get('TMPDIR'))as folder:
            p=subprocess.run([str(PHP),'-n','-r',CODE,str(PUBLIC),folder,str(os.getuid()),'late'if late else'normal'],capture_output=True,text=True,timeout=25)
            self.assertEqual((p.returncode,p.stderr),(0,''),p.stdout+p.stderr);return json.loads(p.stdout)
    def test_each_measured_trial_keeps_its_own_AUTO_document_after_later_trial_and_failure(self):
        v=self.run_fixture();self.assertEqual(len(v['catalog']),2,'Complete trials did not preserve selectable own snapshots')
        self.assertEqual(v['documents'][0]['AUTO'],['learned-round-1.example\n'])
        self.assertEqual(v['documents'][1]['AUTO'],['learned-round-2.example\n'])
        self.assertEqual([x['view']['round'] for x in v['documents']],[1,2])
        self.assertTrue(v['actual_local_original_restored']);self.assertNotEqual(v['catalog'][0]['reference'],v['catalog'][1]['reference'])
        self.assertNotIn('variant',v['documents'][0]['view']['profile'])
        self.assertEqual(v['documents'][0]['view']['profile']['rank']['reason'],'baseline')
        self.assertEqual(v['wrong_document'],'source_changed')
        self.assertEqual(v['foreign_job'],'stale_state')
        self.assertEqual(v['unmeasured_modifier'],'invalid_request')
    def test_failure_of_service_stop_after_completed_measurements_keeps_the_result(self):
        v=self.run_fixture(late=True);self.assertEqual(v['late_error'],'service_stop_failed');self.assertEqual(len(v['catalog']),2,'Late actuator failure erased a fully measured result')
        self.assertEqual(v['documents'][0]['AUTO'],['learned-round-1.example\n'])
        self.assertEqual(v['documents'][1]['AUTO'],[],'An uncertain stop must not grant an AUTO snapshot')
        self.assertIsNone(v['catalog'][1]['document']);self.assertEqual(len(v['documents'][1]['artifact']['profile']['runs']),2)
        self.assertEqual(v['unsealed_export'],'synthesis_unverified')
        self.assertTrue(v['actual_local_original_restored'])

if __name__=='__main__':unittest.main()
