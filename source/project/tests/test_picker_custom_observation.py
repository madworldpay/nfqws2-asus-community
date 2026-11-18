"""Assembler input is reconstructed from actual trial bytes and its program."""
import unittest
import test_synthesis_custom_trial as trials


SETUP=r'''
$recipe=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][0];
require_once $argv[1].'/strategy-picker-custom-joint.php';
$samples=new NfqwsStrategyPickerCustomSamples($s,$check,static fn()=>$ctx,$uid);
$joint=new NfqwsStrategyPickerCustomJoint($samples,$id,base64_decode($s->read()['original'],true));
'''


class CustomObservationTests(unittest.TestCase):
    def observe(self, body):
        return trials.SynthesisCustomTrialTests().observe(SETUP+body)

    def test_exploratory_observation_binds_real_program_variant_and_committed_sample(self):
        r=self.observe("$out['profile']=$h->trial('matrix',$recipe,1,false);$out['observation']=$joint->observation($out['profile']);")
        self.assertNotIn('error',r)
        self.assertEqual(r['observation']['recipe'],r['profile']['components'])
        self.assertEqual(r['observation']['runs'],r['profile']['runs'])
        self.assertEqual(r['observation']['custom_runs'],r['profile']['custom_runs'])
        self.assertEqual(len(r['observation']['custom_runs']),1)

    def test_repeated_observation_requires_two_independently_executed_samples(self):
        r=self.observe("$out['profile']=$h->trial('zero',NfqwsStrategySynthesis::blank(),2,false);$out['observation']=$joint->observation($out['profile']);")
        self.assertNotIn('error',r)
        self.assertEqual(len(r['observation']['custom_runs']),2)
        self.assertNotEqual(*[x['sample_id']for x in r['observation']['custom_runs']])

    def test_edited_variant_recipe_config_role_or_compact_cells_cannot_guide_assembly(self):
        for mutation in ["$p['variant']['NFQWS_ARGS'].=' --lua-desync=drop';",
                         "$p['components']=NfqwsStrategySynthesis::matrix(['max_repeats'=>4])['initial'][1];",
                         "$p['config_sha256']=str_repeat('f',64);","$p['custom_role']='other';",
                         "$p['custom_runs'][0]['cells'][0]['root_ok']=true;",
                         "unset($p['variant']);","unset($p['components']);"]:
            with self.subTest(mutation=mutation):
                r=self.observe("$p=$h->trial('matrix',$recipe,1,false);"+mutation+"$out['observation']=$joint->observation($p);")
                self.assertEqual(r.get('error'),'incomparable_result')

    def test_repeated_label_or_missing_custom_run_never_promotes_exploratory_data(self):
        for mutation in ["$p['sample_type']='repeated';","$p['custom_runs']=[];","unset($p['sample_type']);"]:
            with self.subTest(mutation=mutation):
                r=self.observe("$p=$h->trial('matrix',$recipe,1,false);"+mutation+"$joint->observation($p);")
                self.assertEqual(r.get('error'),'incomparable_result')


if __name__=='__main__':unittest.main()
