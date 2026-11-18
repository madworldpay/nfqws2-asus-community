import json
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC


class ServicePriorityTests(unittest.TestCase):
    def php(self, body):
        fixture = r"""
        function measurement(array $working):array {
            $hosts=array_merge(...array_values(NfqwsStrategyPickerGoals::DOMAINS));
            for($i=0;$i<24;$i++)$hosts[]='secondary'.$i.'.example.com';
            $domains=[];
            foreach($hosts as $host){
                $ok=in_array($host,$working,true);
                $domains[]=['domain'=>$host,'http'=>'failed','tls12'=>$ok?'ok':'failed',
                    'tls13'=>$ok?'ok':'failed','quic'=>'failed'];
            }
            $native=['state'=>'completed','coverage'=>['domains'=>count($domains),'tcp'=>1],
                'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>$domains]]],
                    ['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'control','status'=>'failed']]]]]]];
            return NfqwsStrategyPickerScore::measure($native);
        }
        function candidates():array {
            $primary=array_merge(...array_values(NfqwsStrategyPickerGoals::DOMAINS));
            $secondary=[];for($i=0;$i<24;$i++)$secondary[]='secondary'.$i.'.example.com';
            $focused=NfqwsStrategySynthesis::blank();$focused['tls']=['method'=>'multisplit','pos'=>'1,midsld'];
            $other=NfqwsStrategySynthesis::blank();$other['tls']=['method'=>'multidisorder','pos'=>'host+1'];
            return [$primary,$secondary,$focused,$other];
        }
        """
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [PHP, '-n', '-r', "umask(0077);require $argv[1].'/strategy-synthesis.php';" + fixture + body,
                 str(PUBLIC), folder], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_all_includes_each_priority_service_before_secondary_targets(self):
        result = self.php(r"""
        $stock=['secondary.example.com','youtube.com'];
        echo json_encode(['actual'=>NfqwsStrategyPickerGoals::probeDomains($stock,'all'),
            'primary'=>array_merge(...array_values(NfqwsStrategyPickerGoals::DOMAINS))]);
        """)
        self.assertEqual(result['actual'][:len(result['primary'])], result['primary'])
        self.assertEqual(result['actual'][-1], 'secondary.example.com')
        self.assertEqual(len(result['actual']), len(set(result['actual'])))

    def test_all_assembly_refinement_and_retest_prefer_the_four_services(self):
        result = self.php(r"""
        [$primary,$secondary,$focused,$other]=candidates();$zero=measurement([]);
        $rows=[['recipe'=>NfqwsStrategySynthesis::blank(),'runs'=>[$zero,$zero]],
            ['recipe'=>$focused,'runs'=>[measurement($primary)]],
            ['recipe'=>$other,'runs'=>[measurement($secondary)]]];
        $assembled=NfqwsStrategySynthesis::assemble($rows,'all');
        $retest=NfqwsStrategySynthesis::bestForRetest($rows,'all');
        $refined=NfqwsStrategySynthesis::refine($rows,['max_repeats'=>4],'all');
        echo json_encode(['base'=>$assembled['tls'],'expected'=>$focused['tls'],
            'retested'=>in_array($focused,$retest,true),
            'feedback_preserves_primary'=>count(array_filter($refined,fn($r)=>
                $r['tls']===$focused['tls']&&($r['http']['method']!=='pass'||$r['quic']['method']!=='pass')))>0]);
        """)
        self.assertEqual(result['base'], result['expected'])
        self.assertTrue(result['retested'])
        self.assertTrue(result['feedback_preserves_primary'])

    def test_current_improvement_search_prioritizes_service_gain(self):
        result = self.php(r"""
        [$primary,$secondary,$focused,$other]=candidates();$zero=measurement([]);
        foreach([&$focused,&$other]as &$r){$r['basis']='current';
            $r['overrides']=[['protocol'=>'tls','domains'=>array_merge($primary,$secondary),'component'=>$r['tls']]];
            $r['tls']=['method'=>'pass'];}unset($r);
        $ranked=NfqwsStrategySynthesis::bestImprovements([
            ['recipe'=>$other,'runs'=>[measurement($secondary)]],
            ['recipe'=>$focused,'runs'=>[measurement($primary)]]],['runs'=>[$zero,$zero]],'all',1);
        echo json_encode(['actual'=>$ranked[0]??null,'expected'=>$focused]);
        """)
        self.assertEqual(result['actual'], result['expected'])

    def test_all_does_not_trade_working_instagram_for_secondary_gains(self):
        result = self.php(r"""
        [$primary,$secondary]=candidates();$before=measurement($primary);
        $after=measurement(array_merge(array_values(array_diff($primary,
            NfqwsStrategyPickerGoals::DOMAINS['instagram'])),$secondary));
        echo json_encode(NfqwsStrategyPickerScore::compare([$before,$before],[$after,$after],'all'));
        """)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['reason'], 'goal_regression')


if __name__ == '__main__':
    unittest.main()
