"""Typed identity and actual owned mixed trials, independent of HTTP authentication."""
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC
import test_synthesis_custom_trial as trials
import test_picker_custom_observation as observation_fixture


SETUP=r'''
$selection=NfqwsStrategyPickerRequest::selection(false,'all',true,['hosts'=>['8.8.8.8','alpha.example.com'],'only'=>true]);
$domains=['www.youtube.com'];$automatic=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(4,3000000,0),1);
$choice=NfqwsStrategyPickerConcurrency::plan('auto',$automatic,[]);
$j=array_replace($s->read(),$selection,['selection_sha256'=>NfqwsStrategyPickerRequest::digest($selection),
 'concurrency_choice'=>NfqwsStrategyPickerConcurrency::record($choice),'probe_domains'=>$domains,
 'budget'=>NfqwsStrategyPickerBudget::custom($choice['budget'],2)]);$s->write($j);
'''

CONTROL=r'''
$control=$h->trial('current',null,2,false);$control['rank']=['eligible'=>false,'reason'=>'baseline','gain'=>0];
$j=$s->read();$j['profiles']=[$control];$s->write($j);
'''


class Ipv4RuntimeTests(unittest.TestCase):
    def php(self,body):
        r=subprocess.run([PHP,'-n','-r',"require $argv[1].'/strategy-picker-runtime.php';"+body,str(PUBLIC)],capture_output=True,text=True,timeout=8)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def observe(self,body,**kwargs):
        return trials.SynthesisCustomTrialTests().observe(SETUP+body,**kwargs)

    def test_internal_mixed_selection_has_versioned_typed_digest_and_old_domain_digest_is_exact(self):
        out=self.php(r'''$v=NfqwsStrategyPickerRequest::selection(false,'all',true,['hosts'=>['example.com','8.8.8.8'],'only'=>true],'32');
 $old=NfqwsStrategyPickerRequest::selection(false,'all',true,['hosts'=>['example.com'],'only'=>true]);
 echo json_encode(['mixed'=>$v,'digest'=>NfqwsStrategyPickerRequest::digest($v),'old'=>$old,
 'old_exact'=>NfqwsStrategyPickerRequest::digest($old)===hash('sha256',json_encode([1,NfqwsIdna::POLICY,$old],JSON_THROW_ON_ERROR))]);''')
        self.assertEqual(out['mixed']['custom_target_policy'],'custom-public-targets-v2')
        self.assertEqual(out['mixed']['custom_targets'],[dict(kind='ipv4',host='8.8.8.8'),dict(kind='domain',host='example.com')])
        self.assertTrue(out['old_exact']);self.assertNotIn('custom_targets',out['old'])

    def test_mixed_retry_refuses_missing_typed_identity_policy_scope_and_pool_demotion(self):
        out=self.php(r'''$v=NfqwsStrategyPickerRequest::selection(false,'all',true,['hosts'=>['8.8.8.8','example.com'],'only'=>true],'32');
 $j=$v+['request_id'=>str_repeat('a',32),'selection_sha256'=>NfqwsStrategyPickerRequest::digest($v)];$out=[];
 $out[]=NfqwsStrategyPickerRequest::retry($j,str_repeat('a',32),$v);
 foreach(['custom_targets','custom_target_policy','concurrency']as $key){$bad=$j;unset($bad[$key]);try{NfqwsStrategyPickerRequest::retry($bad,str_repeat('a',32),$v);$out[]='accepted';}catch(Throwable $e){$out[]=$e->getMessage();}}
 $out[]=NfqwsStrategyPickerRequest::custom('8.8.8.8','1');
 echo json_encode($out);''')
        self.assertEqual(out,[True,'request_conflict','request_conflict','request_conflict',dict(hosts=['8.8.8.8'],only=True)])

    def test_literal_job_cannot_be_demoted_by_removing_all_new_metadata(self):
        out=self.php(r'''$v=NfqwsStrategyPickerRequest::selection(false,'all',true,['hosts'=>['8.8.8.8'],'only'=>true]);
 unset($v['custom_target_policy'],$v['custom_targets']);$out=[];
 try{NfqwsStrategyPickerRequest::digest($v);$out[]='accepted';}catch(Throwable $e){$out[]=$e->getMessage();}
 try{NfqwsStrategyPickerConcurrency::job($v);$out[]='accepted';}catch(Throwable $e){$out[]=$e->getMessage();}
 echo json_encode($out);''')
        self.assertEqual(out,['invalid_request','invalid_request'])

    def test_mixed_current_control_then_scoped_matrix_share_exact_candidate_intervals(self):
        out=self.observe(CONTROL+r'''$recipe=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];
 $out['current']=$control;$out['matrix']=$h->trial('matrix',$recipe,1,false);''')
        self.assertNotIn('error',out);p=out['matrix'];self.assertEqual(p['custom_runs'][0]['schema_version'],2)
        self.assertIn('custom_scope',p['components']);self.assertIn('--ipset-ip=8.8.8.8',p['variant']['NFQWS_ARGS_CUSTOM'])
        self.assertEqual(p['components']['custom_scope']['protected_domains'],['alpha.example.com','www.youtube.com'])
        self.assertEqual(out['dns_calls'],1);self.assertEqual(len(out['state']['custom_sample_refs']),3)
        self.assertEqual(out['raw'],'NFQWS_ARGS="original"\n');self.assertFalse(out['on'])
        self.assertEqual(p['recipe'],'s-'+self.program_key(p['components'])[:16])

    def program_key(self,recipe):
        out=self.php("echo json_encode(NfqwsStrategySynthesis::key(json_decode("+json.dumps(json.dumps(recipe))+",true)));")
        return out

    def test_mixed_scope_requires_current_control_before_any_candidate_switch(self):
        out=self.observe("$h->trial('zero',NfqwsStrategySynthesis::blank(),1,false);")
        self.assertEqual(out.get('error'),'incomparable_result',out);self.assertEqual(out['transports'],[])
        self.assertEqual(out['state']['current'],out['state']['original_sha256'])

    def test_owned_joint_observation_rederives_manifest_and_only_canonical_discovery_rules(self):
        body=CONTROL+observation_fixture.SETUP+r'''
 $out['profile']=$h->trial('matrix',$recipe,1,false);$out['observation']=$joint->observation($out['profile']);'''
        out=self.observe(body);self.assertNotIn('error',out)
        self.assertEqual(out['observation']['custom_manifest'],out['state']['custom_manifest'])
        self.assertEqual(out['observation']['recipe'],out['profile']['components'])
        bad=self.observe(CONTROL+observation_fixture.SETUP+r'''
 $p=$h->trial('matrix',$recipe,1,false);$p['components']['overrides'][1]['component']=['method'=>'fake'];$joint->observation($p);''')
        self.assertEqual(bad.get('error'),'incomparable_result')

    def test_mixed_current_or_scoped_recipe_metadata_tampering_cannot_guide_trial(self):
        for mutation in ["$j=$s->read();unset($j['custom_targets']);$s->write($j);",
            "$j=$s->read();unset($j['concurrency_choice']);$s->write($j);",
            "$j=$s->read();$j['custom_manifest']['pins'][0]['address']='1.1.1.1';$s->write($j);"]:
            out=self.observe(CONTROL+mutation+"$h->trial('zero',NfqwsStrategySynthesis::blank(),1,false);")
            self.assertIn(out.get('error'),['invalid_request','stale_state','incomparable_result','storage_unavailable'],out)
            self.assertEqual(len(out['transports']),3)  # Only completed CURRENT prepare + two probes.

    def test_native_tcp_sni_controls_are_shielded_and_chunked_as_well_as_domain_controls(self):
        out=self.php(r'''require $argv[1].'/strategy-picker-custom-worker.php';
 $m=NfqwsStrategyPickerCustomWorker::prepareDocument(['8.8.8.8'],str_repeat('d',64));
 $m+=['pins'=>[['host'=>'8.8.8.8','answer'=>['8.8.8.8'],'address'=>'8.8.8.8']],
 'policy'=>NfqwsIdna::POLICY,'fingerprint'=>AsusDpiSiteCheckProbe::MIXED_PINNED_FINGERPRINT];
 $hosts=array_map(static fn($i)=>'cdn-'.$i.'.example.net',range(1,150));
 $r=NfqwsStrategySynthesis::forTargets(NfqwsStrategySynthesis::blank(),$m,$hosts);
 echo json_encode(['protected'=>count($r['custom_scope']['protected_domains']),'groups'=>array_map(static fn($x)=>count($x['domains']??[]),$r['overrides'])]);''')
        self.assertEqual(out,dict(protected=150,groups=[128,22,0]))


if __name__=='__main__':unittest.main()
