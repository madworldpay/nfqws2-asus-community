"""Mixed evidence is versioned end to end; old domain evidence keeps its bytes."""
import hashlib
import json
import unittest

import test_picker_custom_score as score_fixture
import test_picker_custom_supervisor as supervisor_fixture
import test_picker_custom_samples as samples_fixture
import test_picker_custom_joint as joint_fixture

POLICY='custom-public-targets-v2'
PROBE='php-openssl-pinned-public-targets-v2'
SCORE='custom-pinned-root-score-v2'


class Ipv4EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.score=score_fixture.CustomScoreTests('test_only_the_worst_complete_repeat_counts_toward_gain')
        self.supervisor=supervisor_fixture.CustomSupervisorTests('test_prepare_and_repeated_probes_bind_one_manifest_and_registered_descriptors')
        self.supervisor.setUp()
        self.samples=samples_fixture.CustomSamplesTests('test_fresh_capture_is_private_and_pair_is_rederived_from_committed_bytes')

    def envelope(self):
        v=self.score.envelope(['8.8.8.8','example.com'])
        return v|dict(schema_version=2,fingerprint=PROBE,target_policy_version=POLICY,
            targets=[dict(kind='ipv4',host='8.8.8.8'),dict(kind='domain',host='example.com')])

    def test_registered_supervisor_preserves_mixed_manifest_and_global_known_dns(self):
        out=self.supervisor.observe("$out['manifest']=$sup->prepare(['8.8.8.8','example.com']);$out['first']=$sup->probe();$out['second']=$sup->probe();")
        self.assertNotIn('error',out);self.assertEqual(out['dns_calls'],1)
        self.assertEqual(out['manifest']['schema_version'],2)
        self.assertEqual(out['manifest']['pins'][0],dict(host='8.8.8.8',answer=['8.8.8.8'],address='8.8.8.8'))
        self.assertEqual(out['first']['targets'],self.envelope()['targets'])
        self.assertEqual(out['first']['fingerprint'],PROBE)
        self.assertEqual(out['first']['manifest_sha256'],out['state']['custom_manifest_sha256'])
        self.assertEqual(len(out['probe_calls']),8);self.assertIsNone(out['state'].get('actuator'))
        self.assertIsNone(out['state'].get('custom_worker'));self.assertTrue(out['holders_alive'])
        bad=self.supervisor.observe("$sup->prepare(['8.8.8.8']);",context="return ['schema_version'=>1,'state'=>'unknown','sha256'=>null];")
        self.assertEqual(bad['error'],'dns_context_unknown');self.assertEqual(bad['transports'],[])

    def test_supervisor_rejects_version_target_and_literal_pin_substitution(self):
        for mutation in ["$v['targets'][0]['kind']='domain';", "$v['schema_version']=1;",
                         "$v['target_policy_version']='other';", "$v['pins'][0]['answer']=['1.1.1.1'];$v['pins'][0]['address']='1.1.1.1';"]:
            out=self.supervisor.observe("$sup->prepare(['8.8.8.8','example.com']);",output="if($args[count($args)-3]==='prepare'){$v=json_decode($v['output'],true);"+mutation+"$v=['status'=>0,'output'=>json_encode($v)];}")
            self.assertEqual(out.get('error'),'incomparable_result',out)
            self.assertNotIn('custom_manifest',out['state']);self.assertEqual(out['probe_calls'],[])

    def test_v2_score_preserves_each_ip_tls_cell_and_explicit_fingerprints(self):
        docs=[self.envelope()for _ in range(4)]
        self.score.status(docs[2],0);self.score.status(docs[3],0)
        scores=self.score.run_php(dict(samples=docs));self.assertIsInstance(scores,list,scores)
        self.assertEqual(scores[0]['schema_version'],2);self.assertEqual(scores[0]['fingerprint'],SCORE)
        self.assertEqual(scores[0]['probe_fingerprint'],PROBE)
        self.assertEqual(scores[0]['target_policy_version'],POLICY)
        self.assertEqual(scores[0]['target_identities'],self.envelope()['targets'])
        result=self.score.compare(docs);self.assertEqual(result['gain'],1);self.assertTrue(result['eligible'])
        self.score.status(docs[0],2);self.score.status(docs[1],2)
        self.assertEqual(self.score.compare(docs)['reason'],'custom_regression')

    def test_v2_score_rejects_demotion_and_403_tls_failure_are_not_root_access(self):
        bad=[]
        for patch in [dict(schema_version=1),dict(fingerprint='php-openssl-pinned-https-v1'),dict(target_policy_version='v1'),
            dict(targets=[dict(kind='domain',host='8.8.8.8'),dict(kind='domain',host='example.com')])]:
            bad.append(self.envelope()|patch)
        for v in bad:self.assertEqual(self.score.run_php(dict(samples=[v])),dict(error='incomparable_result'))
        doc=self.envelope();self.score.status(doc,0,403);self.score.status(doc,1,None,'tls_error')
        scores=self.score.run_php(dict(samples=[doc]));self.assertIsInstance(scores,list,scores)
        self.assertEqual([x['root_ok']for x in scores[0]['cells']],[False]*4)
        self.assertEqual([x['responded']for x in scores[0]['cells']],[True,False,False,False])
        docs=[self.envelope()for _ in range(4)]
        for field,value in [('schema_version',1),('target_identities',[]),('target_policy_version','v1')]:
            self.assertEqual(self.score.compare(docs,patch=[[3,field,value]])['reason'],'incomparable_result')

    def test_legacy_domain_score_keeps_exact_original_shape_fingerprints_and_bytes(self):
        doc=self.score.envelope();raw=json.dumps(doc,separators=(',',':'),ensure_ascii=False)
        expected=dict(schema_version=1,fingerprint='custom-pinned-root-score-v1',probe_fingerprint=doc['fingerprint'],
            hosts=doc['hosts'],dns_context=doc['dns_context'],context_sha256='c'*64,manifest_sha256=doc['manifest_sha256'],
            sample_id='0'*31+'1',sample_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            cells=[dict(host=r['host'],tls=r['tls'],outcome='connection_error',http_status=None,responded=False,root_ok=False)
                for r in doc['observations']])
        fields=[expected['fingerprint'],expected['probe_fingerprint'],expected['hosts'],expected['dns_context'],
            expected['context_sha256'],expected['manifest_sha256']]
        expected['targets']=hashlib.sha256(json.dumps(fields,separators=(',',':')).encode()).hexdigest()
        result=self.score.run_php(dict(samples=[doc]))
        self.assertEqual(json.dumps(result[0],separators=(',',':')),json.dumps(expected,separators=(',',':')))

    def initial(self):
        return """$j=$s->read();$manifest=['schema_version'=>2,'hosts'=>['8.8.8.8','example.com'],'dns_context'=>$dns,
 'target_policy_version'=>'custom-public-targets-v2','targets'=>[['kind'=>'ipv4','host'=>'8.8.8.8'],['kind'=>'domain','host'=>'example.com']],
 'pins'=>[['host'=>'8.8.8.8','answer'=>['8.8.8.8'],'address'=>'8.8.8.8'],['host'=>'example.com','answer'=>['8.8.8.8'],'address'=>'8.8.8.8']],
 'policy'=>NfqwsIdna::POLICY,'fingerprint'=>AsusDpiSiteCheckProbe::MIXED_PINNED_FINGERPRINT];
 $j['custom_manifest']=$manifest;$j['custom_hosts']=$manifest['hosts'];
 $j['custom_manifest_sha256']=hash('sha256',json_encode($manifest,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR));$s->write($j);"""

    def probe(self,mutation=''):
        return """$j=$s->read();$m=$j['custom_manifest'];$rows=[];$r=AsusDpiSiteCheck::response('response');$r['http_status']=200;
 foreach($m['hosts']as $host)foreach(['tls12','tls13']as $tls)$rows[]=['host'=>$host,'tls'=>$tls,'response'=>$r];
 $e=['schema_version'=>2,'hosts'=>$m['hosts'],'dns_context'=>$dns,'fingerprint'=>$m['fingerprint'],
 'target_policy_version'=>$m['target_policy_version'],'targets'=>$m['targets'],'observations'=>$rows,'manifest_sha256'=>$j['custom_manifest_sha256']];
 """+mutation+"return $e;"

    def test_committed_v2_samples_rederive_scores_and_remain_available_in_the_archive(self):
        out=self.samples.observe(initial=self.initial(),probe=self.probe(),body="""
 $out['a']=$samples->capture('candidate',$config,1,$contextSha,$probe);
 $out['b']=$samples->capture('candidate',$config,2,$contextSha,$probe);
 $out['loaded']=$samples->load($id,$out['a']['sample_id']);$out['pair']=$samples->pair($id,'candidate');
 $j=$s->read();$j['state']='completed';$j['restored']=true;$s->write($j);
 """+self.samples.retire_runtime()+"""
 $archive=new NfqwsStrategyPickerState($s->root.'/job-'.$id,(int)$argv[3],$s->configDirectory);
 $out['archived']=$archive->read();
 $out['retained_pair']=$samples->pair($id,'candidate');""")
        self.assertNotIn('error',out);self.assertEqual(out['a']['schema_version'],2)
        self.assertEqual(out['loaded']['document']['schema_version'],2)
        self.assertEqual(out['loaded']['score'],out['a']);self.assertEqual(out['pair'],[out['a'],out['b']])
        self.assertEqual(out['archived']['custom_sample_refs'],out['state']['custom_sample_refs'])
        self.assertEqual(out['retained_pair'],[out['a'],out['b']])
        self.assertEqual(len(out['files']),2)
        for ref in out['archived']['custom_sample_refs']:
            name='custom-'+out['state']['id']+'-'+ref['id']+'.json'
            self.assertEqual(out['files'][name]['sha256'],ref['sha256'])

    def test_v2_artifact_cannot_substitute_valid_domain_envelope_or_a_forged_type(self):
        for mutation in ["$e['targets'][0]['kind']='domain';", "$e['schema_version']=1;",
                         "$e['target_policy_version']='other';", """$e=['schema_version'=>1,'hosts'=>['example.com'],'dns_context'=>$dns,
 'fingerprint'=>AsusDpiSiteCheckProbe::PINNED_FINGERPRINT,'manifest_sha256'=>$j['custom_manifest_sha256'],
 'observations'=>[['host'=>'example.com','tls'=>'tls12','response'=>$r],['host'=>'example.com','tls'=>'tls13','response'=>$r]]];"""]:
            out=self.samples.observe(initial=self.initial(),probe=self.probe(mutation),body="$samples->capture('candidate',$config,1,$contextSha,$probe);")
            self.assertEqual(out.get('error'),'incomparable_result',out);self.assertEqual(out['files'],[])
            self.assertIsNone(out['state'].get('custom_sample_pending'));self.assertEqual(out['state'].get('custom_sample_refs',[]),[])

    def test_coherently_rehashed_artifact_demotion_still_fails_manifest_version_binding(self):
        out=self.samples.observe(initial=self.initial(),probe=self.probe(),body="""
 $a=$samples->capture('candidate',$config,1,$contextSha,$probe);
 $j=$s->read();$ref=$j['custom_sample_refs'][0];$file=$s->root.'/custom-'.$id.'-'.$a['sample_id'].'.json';
 $v=json_decode(file_get_contents($file),true);$v['schema_version']=1;
 $raw=json_encode($v,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);file_put_contents($file,$raw);
 $j['custom_sample_refs'][0]['bytes']=strlen($raw);$j['custom_sample_refs'][0]['sha256']=hash('sha256',$raw);$s->write($j);
 $samples->load($id,$a['sample_id']);""")
        self.assertEqual(out.get('error'),'storage_unavailable',out);self.assertEqual(len(out['files']),1)
        self.assertEqual(len(out['state']['custom_sample_refs']),1)

    def test_mixed_pending_sigkill_recovery_never_publishes_partial_evidence(self):
        for stage in ['empty','complete']:
            with self.subTest(stage=stage):
                out=self.samples.observe(initial=self.initial(),probe=self.probe(),kill_stage=stage,
                    recovery=self.samples.terminal_recovery("$samples->recoverPending($j['id']);$samples->recoverPending($j['id']);"))
                self.assertNotIn('error',out);self.assertEqual(out['file_count'],0)
                self.assertIsNone(out['state'].get('custom_sample_pending'));self.assertFalse(out['state'].get('custom_sample_refs'))
                self.assertEqual(out['load'],'incomparable_result')

    def test_joint_adapter_rederives_mixed_artifacts_and_protects_native_controls(self):
        for regress in [False,True]:
            body=joint_fixture.SETUP+"$a['custom_runs']=$make('baseline',$blocked);$b['custom_runs']=$make('candidate',$probe);"
            if regress:body+="foreach($b['runs']as &$run)$run['metrics']['tls13']['ok']=9;unset($run);"
            out=self.samples.observe(initial=self.initial(),probe=self.probe(),body=body+"$out['rank']=$joint->compare($a,$b,'all',true);")
            self.assertNotIn('error',out);self.assertEqual(out['rank']['eligible'],not regress)
            if not regress:self.assertEqual(out['rank']['custom']['minimum']['root_ok'],dict(ok=4,total=4))


if __name__=='__main__':unittest.main()
