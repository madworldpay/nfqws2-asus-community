"""The real synthesis trial owns the candidate for native and custom probes."""
import unittest
import test_picker_custom_supervisor as supervision


BOOT = r'''
require dirname($argv[1],3).'/tests/fixtures/picker-library.php';
final class SynthesisCustomTrialHarness {
 use NfqwsStrategySynthesisRuntime;
 use NfqwsStrategyPickerCustomRuntime;
 public array $events=[];
 public bool $on=false;
 public int $nativeCount=0;
 public bool $changeContext=false;
 public int $nativeTCP=1;
 public function __construct(public $store,public $config,public $check,public $transport,public $dns,public array $ctx,private array $entry){}
 private function resourcesFingerprint():string {return hash_file('sha256',dirname($this->store->root).'/trial-resource.list');}
 private function checkpoint():void {($this->check)();}
 private function customContext():array {return $this->ctx;}
 private function customSupervisor():NfqwsStrategyPickerCustomSupervisor {
  return new NfqwsStrategyPickerCustomSupervisor($this->store,fn()=>$this->customCheckpoint(),$this->transport,$this->dns);
 }
 private function phase(string $phase,array $extra=[]):void {
  $this->store->write(array_replace($this->store->read(),['phase'=>$phase],$extra));
 }
 private function service(string $action):void {
  $this->on=$action==='start';$this->events[]=['service',$action,hash('sha256',$this->config->raw())];
 }
 private function resetAuto(array $entry):void {$this->events[]=['reset'];}
 private function candidate(array $entry):string {
  return (new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'candidate'))->invoke(
   new NfqwsStrategyPickerRuntime($this->store,$this->config),$entry);
 }
 private function probe(array $groups):array {
  if(!$this->on)throw new RuntimeException('fixture_candidate_not_active');
  $this->nativeCount++;$this->events[]=['native',hash('sha256',$this->config->raw())];
  $c=$this->ctx;
  if($this->changeContext)$this->ctx['tun_observed']=true;
  $result=['state'=>'completed','context'=>['before'=>$c,'after'=>$c,'changed'=>false],
   'coverage'=>['domains'=>1,'tcp'=>1],
   'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>[
    ['domain'=>'www.youtube.com','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'quic_ok']]]]],
    ['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'control','status'=>$this->nativeTCP?'ok':'timeout']]]]]]];
  $choice=$this->store->read()['concurrency_choice']??null;
  if($choice!==null)$result['settings']=['config'=>['MAX_CONCURRENT'=>$choice['effective']]];
  return $result;
 }
 public function trial(string $name='fixture',?array $recipe=null,int $repeats=2,bool $warm=true):array {
  return $this->synthesisTrial($this->entry,$name,$recipe,$repeats,$warm);
 }
 public function peak():float {return $this->synthesisProbePeak;}
 public function canExplore(float $measuredPeak):bool {$this->synthesisProbePeak=$measuredPeak;return $this->synthesisTime();}
 public function admit():void {$this->synthesisAdmission();}
 public function rank(array $a,array $b,string $goal='all'):array {return $this->synthesisRank($a,$b,$goal);}
}
$ctx=['nfqws'=>'running','ark'=>'absent','tun_observed'=>false,
 'dns'=>['schema_version'=>1,'state'=>'known','sha256'=>str_repeat('c',64)]];
file_put_contents($root.'/nfqws2.conf',"NFQWS_ARGS=\"original\"\n");chmod($root.'/nfqws2.conf',0600);
$config=new NfqwsStrategyPickerConfig($s,$root.'/nfqws2.conf',$uid);
file_put_contents($root.'/trial-resource.list',"alpha.example.com\n");
$j=$config->snapshot(false);$j['resources_sha256']=hash_file('sha256',$root.'/trial-resource.list');$j['id']=$id;$j['state']='running';$j['phase']='discovering';
$j['deadline']=AsusUpdateStore::uptime()+2700.125;
$j['budget']=['probe_seconds'=>510,'group_seconds'=>240,'available_kib'=>65536];
$j['custom_hosts']=['alpha.example.com','beta.example.com'];$s->write($j);
$h=null;$baseTransport=$transport;
$combinedTransport=static function($args,$seconds,$input,$check)use($baseTransport,&$h,$s){
 if(!$h->on||hash('sha256',$h->config->raw())!==$s->read()['current'])
  throw new RuntimeException('fixture_candidate_not_active');
 $h->events[]=['custom',array_slice($args,-3,1)[0],$s->read()['current']];
 usleep(20000);return $baseTransport($args,$seconds,$input,$check);
};
$h=new SynthesisCustomTrialHarness($s,$config,$check,$combinedTransport,$dns,$ctx,pickerFixtureProfile($s));
'''


class SynthesisCustomTrialTests(unittest.TestCase):
    def observe(self, body='', **kwargs):
        out = supervision.CustomSupervisorTests().observe(body=BOOT+body+r'''
        $out['events']=$h->events;$out['native_count']=$h->nativeCount;
        $out['raw']=$config->raw();$out['on']=$h->on;$out['peak']=$h->peak();
        ''', **kwargs)
        return out

    def test_actual_registered_custom_samples_remain_inside_one_candidate_interval(self):
        r=self.observe("$out['profile']=$h->trial();")
        self.assertNotIn('error',r)
        p=r['profile']
        self.assertEqual(len(p.get('custom_runs',[])),2)
        self.assertEqual(len(p['runs']),2)
        self.assertEqual(r['native_count'],3)
        self.assertEqual(len(r['probe_calls']),8)
        self.assertEqual(r['dns_calls'],2)
        refs=r['state']['custom_sample_refs']
        self.assertEqual([x['repeat']for x in refs],[1,2])
        self.assertTrue(all(x['role']==p['custom_role']for x in refs))
        self.assertTrue(all(x['config_sha256']==p['config_sha256']for x in refs))
        self.assertTrue(all(a['context_sha256']==b['context_sha256']for a,b in zip(p['runs'],p['custom_runs'])))
        self.assertEqual([e[0]for e in r['events']],
                         ['service','reset','service','native','native','custom','custom','native','custom','service'])
        self.assertTrue(all(e[-1]==p['config_sha256']for e in r['events']if e[0]in ['native','custom']))
        self.assertEqual(r['raw'],'NFQWS_ARGS="original"\n')
        self.assertFalse(r['on'])
        self.assertFalse(r['state']['restored'])
        self.assertGreaterEqual(r['peak'],.04)

    def test_trial_roles_are_unique_even_when_current_and_zero_share_an_entry_id(self):
        r=self.observe("$out['a']=$h->trial('same',null,2,false);$out['b']=$h->trial('same',NfqwsStrategySynthesis::blank(),2,false);")
        self.assertNotIn('error',r)
        self.assertEqual(len(r['state'].get('custom_sample_refs',[])),4)
        self.assertNotEqual(r['a']['custom_role'],r['b']['custom_role'])
        self.assertEqual(r['a']['id'],r['b']['id'])
        self.assertNotEqual(r['a']['config_sha256'],r['b']['config_sha256'])
        self.assertEqual(len(r['transports']),5)

    def test_exploratory_trial_measures_custom_once_without_claiming_a_repeated_result(self):
        r=self.observe("$out['profile']=$h->trial('explore',NfqwsStrategySynthesis::blank(),1,false);")
        self.assertNotIn('error',r)
        self.assertEqual(len(r['profile'].get('custom_runs',[])),1)
        self.assertEqual(r['profile']['sample_type'],'exploratory')
        self.assertEqual([x['repeat']for x in r['state']['custom_sample_refs']],[1])

    def test_fixed_only_trial_preserves_native_path_without_custom_artifacts(self):
        r=self.observe("$j=$s->read();unset($j['custom_hosts']);$j['budget']['available_kib']=24576;$s->write($j);$out['profile']=$h->trial();")
        self.assertNotIn('error',r)
        self.assertNotIn('custom_runs',r['profile'])
        self.assertEqual(r['native_count'],3)
        self.assertEqual(r['transports'],[])
        self.assertNotIn('custom_manifest',r['state'])

    def test_custom_memory_admission_precedes_any_service_or_config_mutation(self):
        r=self.observe("$j=$s->read();$j['budget']['available_kib']=0;$s->write($j);$h->admit();$out['profile']=$h->trial();")
        self.assertEqual(r.get('error'),'insufficient_memory')
        self.assertEqual(r['transports'],[])
        # Errors exit the observe body; the absence of a switched journal proves the boundary.
        self.assertEqual(r['state']['current'],r['state']['original_sha256'])
        self.assertEqual(r['state']['phase'],'discovering')

    def test_custom_context_changed_after_native_does_not_publish_a_sample(self):
        r=self.observe("$h->changeContext=true;$out['profile']=$h->trial('ctx',null,1,false);")
        self.assertEqual(r.get('error'),'incomparable_result')
        self.assertEqual(r['transports'],[])
        self.assertNotIn('custom_sample_refs',r['state'])

    def test_trial_budget_accounts_full_native_custom_children_and_restore_before_switch(self):
        # Native3x(510+30cleanup), prepare90, probes2x90, service3x60, restore120.
        r=self.observe("$j=$s->read();$j['deadline']=AsusUpdateStore::uptime()+2189.5;$s->write($j);$out['profile']=$h->trial();")
        self.assertEqual(r.get('error'),'timed_out')
        self.assertEqual(r['state']['current'],r['state']['original_sha256'])
        self.assertEqual(r['state']['phase'],'discovering')
        self.assertEqual(r['transports'],[])

    def test_invalid_repeat_count_is_rejected_before_candidate_or_dns_work(self):
        for repeats in [0,3]:
            with self.subTest(repeats=repeats):
                r=self.observe(f"$out['profile']=$h->trial('invalid',null,{repeats},false);")
                self.assertEqual(r.get('error'),'invalid_request')
                self.assertEqual(r['state']['current'],r['state']['original_sha256'])
                self.assertEqual(r['transports'],[])

    def test_telegram_custom_hosts_are_excluded_before_switching_or_resolution(self):
        for host in ['t.me','telegram.org','web.telegram.org','telesco.pe']:
            with self.subTest(host=host):
                r=self.observe("$j=$s->read();$j['custom_hosts']=['"+host+"'];$s->write($j);$h->trial();")
                self.assertEqual(r.get('error'),'invalid_request')
                self.assertEqual(r['state']['current'],r['state']['original_sha256'])
                self.assertEqual(r['transports'],[])
                self.assertEqual(r['dns_calls'],0)


if __name__=='__main__':unittest.main()
