"""Whole-series admission and exploration protect an entire final verification."""
import unittest
import test_synthesis_custom_trial as trials


POLICY=r'''
$j=$s->read();$base=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(4,3000000,0),38);
$j['budget']=NfqwsStrategyPickerBudget::custom($base,count($j['custom_hosts']));
$j['deadline']=AsusUpdateStore::uptime()+$j['budget']['deadline_seconds'];$s->write($j);
'''


class CustomSeriesBudgetTests(unittest.TestCase):
    def observe(self, body):
        return trials.SynthesisCustomTrialTests().observe(body)

    def test_exploration_reserves_one_whole_final_trial_independently_of_measured_speed(self):
        r=self.observe(r'''
        $out['prepared']=$h->trial('prepare',null,1,false);$j=$s->read();
        $j['deadline']=AsusUpdateStore::uptime()+2890;$s->write($j);$out['short']=$h->canExplore(.001);
        $j['deadline']=AsusUpdateStore::uptime()+2930;$s->write($j);$out['enough']=$h->canExplore(10000);
        ''')
        self.assertNotIn('error',r)
        self.assertFalse(r['short'])
        self.assertTrue(r['enough'])

    def test_legacy_exploration_keeps_its_existing_measured_peak_policy(self):
        r=self.observe(r'''
        $j=$s->read();unset($j['custom_hosts']);$j['deadline']=AsusUpdateStore::uptime()+400;$s->write($j);
        $out['fast']=$h->canExplore(10);$out['slow']=$h->canExplore(100);
        ''')
        self.assertNotIn('error',r)
        self.assertTrue(r['fast'])
        self.assertFalse(r['slow'])

    def test_registered_composite_policy_admits_without_mutating_job_or_config(self):
        r=self.observe(POLICY+r'''
        $before=$s->read();$h->admit();$out['same']=$s->read()===$before;
        ''')
        self.assertNotIn('error',r)
        self.assertTrue(r['same'])
        self.assertEqual(r['events'],[])
        self.assertEqual(r['state']['current'],r['state']['original_sha256'])

    def test_short_budget_or_unregistered_policy_refuses_before_source_or_service_changes(self):
        for mutation,expected in [
            ("$j['deadline']=AsusUpdateStore::uptime()+6419;",'timed_out'),
            ("unset($j['budget']['custom']);",'stale_state'),
            ("$j['budget']['custom']['max_hosts']=5;",'stale_state'),
            ("$j['deadline']=AsusUpdateStore::uptime()+7000;",'stale_state')]:
            with self.subTest(mutation=mutation):
                r=self.observe(POLICY+"$j=$s->read();"+mutation+"$s->write($j);$h->admit();")
                self.assertEqual(r.get('error'),expected)
                self.assertEqual(r['state']['current'],r['state']['original_sha256'])
                self.assertEqual(r['transports'],[])


if __name__=='__main__':unittest.main()
