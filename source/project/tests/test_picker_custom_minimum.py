"""Exploratory minima are distinct from a verified two-run comparison."""
import unittest
import test_picker_custom_samples as owned


class CustomMinimumTests(unittest.TestCase):
    def observe(self, body):
        return owned.CustomSamplesTests().observe(body=body)

    def test_two_runs_require_each_custom_protocol_cell_in_both_observations(self):
        r=self.observe(r'''
        $a=$samples->capture('candidate',$config,1,$contextSha,$probe);
        $changed=static function()use($probe){$v=$probe();$v['observations'][1]['response']['http_status']=403;return $v;};
        $b=$samples->capture('candidate',$config,2,$contextSha,$changed);
        $out['minimum']=NfqwsStrategyPickerCustomScore::minimum([$a,$b]);
        ''')
        self.assertNotIn('error',r)
        m=r['minimum']
        self.assertEqual(m['root_ok'],{'ok':1,'total':2})
        self.assertEqual(m['responded'],{'ok':2,'total':2})
        self.assertEqual([x['root_ok']for x in m['cells']],[True,False])
        self.assertEqual(m['repeats'],2)

    def test_one_run_is_exploratory_and_cannot_be_compared_as_a_verified_pair(self):
        r=self.observe(r'''
        $a=$samples->capture('candidate',$config,1,$contextSha,$probe);
        $out['minimum']=NfqwsStrategyPickerCustomScore::minimum([$a]);
        $out['rank']=NfqwsStrategyPickerCustomScore::compare([$a],[$a]);
        ''')
        self.assertNotIn('error',r)
        self.assertEqual(r['minimum']['repeats'],1)
        self.assertEqual(r['minimum']['root_ok'],{'ok':2,'total':2})
        self.assertFalse(r['rank']['eligible'])
        self.assertEqual(r['rank']['reason'],'incomparable_result')

    def test_missing_duplicate_forged_or_changed_target_rows_never_form_a_minimum(self):
        for expression in ["[]","[$a,$a]","[$a,$a,$a]","['named'=>$a]","[$a,$bad]","[$a,$foreign]"]:
            with self.subTest(expression=expression):
                r=self.observe(r'''
                $a=$samples->capture('candidate',$config,1,$contextSha,$probe);
                $bad=$a;$bad['sample_id']=str_repeat('f',32);$bad['cells'][0]['root_ok']=false;
                $foreign=NfqwsStrategyPickerCustomScore::measure($probe(),str_repeat('d',64),str_repeat('e',32));
                $out['minimum']=NfqwsStrategyPickerCustomScore::minimum('''+expression+');')
                self.assertEqual(r.get('error'),'incomparable_result')


if __name__=='__main__':unittest.main()
