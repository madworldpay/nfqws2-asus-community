"""Runtime composition uses actual registered leaf processes and committed bytes."""
import json
import unittest
from test_dpi_normalize import PUBLIC
import test_picker_custom_supervisor as supervision


BOOT = r'''
require_once $argv[1].'/strategy-picker-custom-runtime.php';
final class RuntimeCustomHarness {
 use NfqwsStrategyPickerCustomRuntime;
 public function __construct(public $store,public $check,public $transport,public $dns,public array $ctx,public int $ram=65536){}
 private function checkpoint():void {($this->check)();}
 private function budget():array {return ['available_kib'=>$this->ram];}
 private function customContext():array {return $this->ctx;}
 private function customSupervisor():NfqwsStrategyPickerCustomSupervisor {
  return new NfqwsStrategyPickerCustomSupervisor($this->store,fn()=>$this->customCheckpoint(),$this->transport,$this->dns);
 }
 public function capture(string $role,int $repeat,string $context):array {return $this->customSample($role,$repeat,$context);}
}
$ctx=['nfqws'=>'running','ark'=>'absent','tun_observed'=>false,'dns'=>['schema_version'=>1,'state'=>'known','sha256'=>str_repeat('c',64)]];
$sorted=$ctx;ksort($sorted);$ctxsha=hash('sha256',json_encode($sorted,JSON_THROW_ON_ERROR));
$j=$s->read();$j['boot']=AsusUpdateStore::boot();$j['current']=str_repeat('b',64);$j['deadline']=AsusUpdateStore::uptime()+900.125;
$j['custom_hosts']=['alpha.example.com','beta.example.com','delta.example.com','epsilon.example.com','gamma.example.com'];$s->write($j);
$h=new RuntimeCustomHarness($s,$check,$transport,$dns,$ctx);
'''


class CustomRuntimeTests(unittest.TestCase):
    def observe(self, body='', **kwargs):
        self.assertTrue((PUBLIC/'strategy-picker-custom-runtime.php').is_file(),
                        'Runtime custom measurement caller is not implemented')
        return supervision.CustomSupervisorTests().observe(body=BOOT+body, **kwargs)

    def test_five_hosts_two_actual_captures_keep_one_manifest_and_private_detail(self):
        out=self.observe(r'''
        $out['first']=$h->capture('control',1,$ctxsha);$out['second']=$h->capture('control',2,$ctxsha);
        $samples=new NfqwsStrategyPickerCustomSamples($s,$check,fn()=>$ctx,$uid);
        $out['pair']=$samples->pair($id,'control');$out['loaded']=$samples->load($id,$out['first']['sample_id']);
        $out['runtime_method_private']=(new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'customSample'))->isPrivate();
        ''')
        self.assertNotIn('error',out)
        self.assertTrue(out['runtime_method_private'])
        self.assertEqual(out['dns_calls'],5)
        self.assertEqual(len(out['probe_calls']),20)
        self.assertEqual(len(out['transports']),3)
        self.assertEqual(len(out['state']['custom_sample_refs']),2)
        self.assertIsInstance(out['state']['deadline'],float)
        self.assertNotEqual(out['first']['sample_id'],out['second']['sample_id'])
        self.assertEqual(out['first']['targets'],out['second']['targets'])
        self.assertEqual(out['first']['manifest_sha256'],out['state']['custom_manifest_sha256'])
        self.assertEqual(out['loaded']['score'],out['first'])
        self.assertEqual(out['pair'],[out['first'],out['second']])
        self.assertEqual(len(out['first']['cells']),10)
        self.assertTrue(all(c['responded'] and not c['root_ok'] for c in out['first']['cells']))
        self.assertTrue(all(x['config_sha256']=='b'*64 for x in out['state']['custom_sample_refs']))
        self.assertIsNone(out['state'].get('actuator'))
        self.assertIsNone(out['state'].get('custom_worker'))
        self.assertTrue(out['holders_alive'])

    def test_low_reported_memory_does_not_skip_dns_or_registered_capture(self):
        out=self.observe("$h->ram=1024;$out['sample']=$h->capture('control',1,$ctxsha);")
        self.assertNotIn('error',out)
        self.assertEqual(out['dns_calls'],5)
        self.assertEqual(len(out['transports']),2)
        self.assertIn('custom_manifest',out['state'])
        self.assertNotIn('custom_sample_pending',out['state'])

    def test_prepare_and_probe_require_two_child_budgets_and_restoration_reserve(self):
        out=self.observe("$j=$s->read();$j['deadline']=AsusUpdateStore::uptime()+299.5;$s->write($j);$h->capture('control',1,$ctxsha);")
        self.assertEqual(out['error'],'timed_out')
        self.assertEqual(out['transports'],[])
        self.assertEqual(out['dns_calls'],0)

    def test_existing_manifest_phase_refuses_short_budget_without_losing_first_sample(self):
        out=self.observe("$out['first']=$h->capture('control',1,$ctxsha);$j=$s->read();$j['deadline']=AsusUpdateStore::uptime()+209.5;$s->write($j);$h->capture('control',2,$ctxsha);")
        self.assertEqual(out['error'],'timed_out')
        self.assertEqual(len(out['transports']),2)
        self.assertEqual(len(out['probe_calls']),10)
        self.assertEqual(len(out['state']['custom_sample_refs']),1)

    def test_native_context_disagreement_refuses_before_custom_resolution(self):
        out=self.observe("$h->capture('control',1,str_repeat('d',64));")
        self.assertEqual(out['error'],'incomparable_result')
        self.assertEqual(out['dns_calls'],0)
        self.assertEqual(out['transports'],[])

    def test_context_change_between_repeats_does_not_publish_second_sample(self):
        out=self.observe("$out['first']=$h->capture('control',1,$ctxsha);$h->ctx['tun_observed']=true;$h->capture('control',2,$ctxsha);")
        self.assertEqual(out['error'],'incomparable_result')
        self.assertEqual(len(out['probe_calls']),10)
        self.assertEqual(len(out['state']['custom_sample_refs']),1)

    def test_invalid_runtime_arguments_do_not_start_resolution(self):
        for role,repeat,context in [('invalid/role',1,'c'*64),('control',0,'c'*64),('control',1,'bad')]:
            with self.subTest(role=role,repeat=repeat,context=context):
                out=self.observe('$h->capture('+json.dumps(role)+','+str(repeat)+','+json.dumps(context)+');')
                self.assertEqual(out['error'],'invalid_request')
                self.assertEqual(out['dns_calls'],0)
                self.assertEqual(out['transports'],[])

    def test_public_custom_request_activation_remains_closed_until_joint_mode_is_complete(self):
        out=self.observe("NfqwsStrategyPickerRuntime::validateRequest(['cmd'=>'pickersynthesize','csrf_token'=>'csrf','request_id'=>str_repeat('e',32),'consent'=>'test','custom_hosts'=>'alpha.example.com']);")
        self.assertEqual(out['error'],'invalid_request')
        self.assertEqual(out['transports'],[])


if __name__=='__main__':unittest.main()
