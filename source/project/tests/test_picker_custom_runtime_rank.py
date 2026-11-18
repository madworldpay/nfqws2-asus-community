"""Final runtime ranking checks both native controls and actual custom samples."""
import unittest
import test_synthesis_custom_trial as trials


RESPONSE=r'''
$j=(new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]))->read();
if(($j['active_recipe']['tls']['method']??null)==='multidisorder')$r['http_status']=200;
'''


class CustomRuntimeRankTests(unittest.TestCase):
    def observe(self, body):
        return trials.SynthesisCustomTrialTests().observe(r'''
        $matrix=NfqwsStrategySynthesis::matrix(['max_repeats'=>4]);
        $methodA=$matrix['initial'][0];$methodB=$matrix['initial'][1];
        '''+body,leaf_response=RESPONSE)

    def test_custom_only_final_gain_requires_two_real_root_successes_per_host(self):
        r=self.observe(r'''
        $a=$h->trial('baseline',null,2,false);$b=$h->trial('final',$methodB,2,false);
        $j=$s->read();$j['custom_only']=true;$s->write($j);$out['rank']=$h->rank($a,$b);
        ''')
        self.assertNotIn('error',r)
        self.assertTrue(r['rank']['eligible'])
        self.assertEqual(r['rank']['gain'],4)
        self.assertEqual(r['rank']['native']['gain'],0)
        self.assertEqual(r['rank']['custom']['minimum']['root_ok'],{'ok':4,'total':4})

    def test_native_gain_cannot_pay_for_custom_regression(self):
        r=self.observe(r'''
        $h->nativeTCP=0;$a=$h->trial('baseline',$methodB,2,false);
        $h->nativeTCP=1;$b=$h->trial('final',$methodA,2,false);$out['rank']=$h->rank($a,$b);
        ''')
        self.assertNotIn('error',r)
        self.assertFalse(r['rank']['eligible'])
        self.assertEqual(r['rank']['reason'],'custom_regression')

    def test_native_gain_with_equal_custom_cells_depends_on_custom_only_or_joint_mode(self):
        r=self.observe(r'''
        $h->nativeTCP=0;$a=$h->trial('baseline',null,2,false);
        $h->nativeTCP=1;$b=$h->trial('final',$methodA,2,false);
        $j=$s->read();$j['custom_only']=true;$s->write($j);$out['only']=$h->rank($a,$b);
        $j['custom_only']=false;$s->write($j);$out['joint']=$h->rank($a,$b);
        ''')
        self.assertNotIn('error',r)
        self.assertFalse(r['only']['eligible'])
        self.assertTrue(r['joint']['eligible'])
        self.assertEqual(r['joint']['gain'],1)

    def test_edited_program_or_replayed_sample_cannot_produce_a_final_winner(self):
        for mutation in ["$b['variant']['NFQWS_ARGS'].=' --lua-desync=drop';",
                         "$b['components']=$methodA;","$b['custom_runs'][1]=$b['custom_runs'][0];"]:
            with self.subTest(mutation=mutation):
                r=self.observe("$a=$h->trial('baseline',null,2,false);$b=$h->trial('final',$methodB,2,false);"+mutation+"$out['rank']=$h->rank($a,$b);")
                self.assertNotIn('error',r)
                self.assertFalse(r['rank']['eligible'])
                self.assertEqual(r['rank']['reason'],'incomparable_result')

    def test_native_only_ranking_keeps_ordinary_scoring_without_custom_artifacts(self):
        r=self.observe(r'''
        $j=$s->read();unset($j['custom_hosts']);$s->write($j);
        $h->nativeTCP=0;$a=$h->trial('baseline',null,2,false);
        $h->nativeTCP=1;$b=$h->trial('final',$methodA,2,false);$out['rank']=$h->rank($a,$b);
        ''')
        self.assertNotIn('error',r)
        self.assertTrue(r['rank']['eligible'])
        self.assertEqual(r['rank']['gain'],1)
        self.assertEqual(r['transports'],[])


if __name__=='__main__':unittest.main()
