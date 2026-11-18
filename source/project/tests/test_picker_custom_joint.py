"""Joint rankings re-derive custom evidence from the exact owned artifacts."""
import unittest
from test_dpi_normalize import PUBLIC
import test_picker_custom_samples as owned


SETUP = r'''
require_once $argv[1].'/strategy-picker-custom-joint.php';
$blocked=static function()use($probe){$v=$probe();foreach($v['observations']as &$row)$row['response']['http_status']=403;return $v;};
$make=static function($role,$callback)use($samples,$config,$contextSha){return [
 $samples->capture($role,$config,1,$contextSha,$callback),$samples->capture($role,$config,2,$contextSha,$callback)];};
$m=['tcp'=>['ok'=>10,'total'=>20],'http'=>['ok'=>10,'total'=>20],
 'tls12'=>['ok'=>10,'total'=>20],'tls13'=>['ok'=>10,'total'=>20],'quic'=>['ok'=>10,'total'=>20]];
$native=['metrics'=>$m,'targets'=>str_repeat('e',64),'context_sha256'=>$contextSha,
 'youtube'=>['http'=>true,'tls12'=>true,'tls13'=>true,'quic'=>true]];
$a=['custom_role'=>'baseline','config_sha256'=>$config,'runs'=>[$native,$native]];
$b=['custom_role'=>'candidate','config_sha256'=>$config,'runs'=>[$native,$native]];
$joint=new NfqwsStrategyPickerCustomJoint($samples,$id);
'''


class CustomJointTests(unittest.TestCase):
    def observe(self, body):
        self.assertTrue((PUBLIC/'strategy-picker-custom-joint.php').is_file(),
                        'Joint custom/native evidence ranking is not implemented')
        out=owned.CustomSamplesTests().observe(body=SETUP+body)
        self.assertNotIn('error',out)
        return out['rank']

    def test_custom_gain_with_equal_native_controls_is_eligible(self):
        r=self.observe("$a['custom_runs']=$make('baseline',$blocked);$b['custom_runs']=$make('candidate',$probe);$out['rank']=$joint->compare($a,$b,'all',true);")
        self.assertTrue(r['eligible']);self.assertEqual(r['gain'],2)
        self.assertEqual(r['native']['gain'],0)
        self.assertEqual(r['custom']['minimum']['root_ok'],{'ok':2,'total':2})

    def test_native_gain_without_custom_gain_depends_on_selected_mode(self):
        setup="$a['custom_runs']=$make('baseline',$blocked);$b['custom_runs']=$make('candidate',$blocked);foreach($b['runs']as &$run)$run['metrics']['tcp']['ok']=11;unset($run);"
        for custom_only in [True,False]:
            with self.subTest(custom_only=custom_only):
                r=self.observe(setup+"$out['rank']=$joint->compare($a,$b,'all',"+str(custom_only).lower()+");")
                self.assertEqual(r['eligible'],not custom_only)
                self.assertEqual(r['gain'],0 if custom_only else 1)

    def test_custom_regression_cannot_be_offset_by_native_gain(self):
        r=self.observe("$a['custom_runs']=$make('baseline',$probe);$b['custom_runs']=$make('candidate',$blocked);foreach($b['runs']as &$run)$run['metrics']['tcp']['ok']=20;unset($run);$out['rank']=$joint->compare($a,$b,'all',false);")
        self.assertFalse(r['eligible']);self.assertEqual(r['reason'],'custom_regression')

    def test_any_native_control_metric_regression_refuses_custom_gain(self):
        for protocol in ['tcp','http','quic','tls12','tls13']:
            with self.subTest(protocol=protocol):
                r=self.observe("$a['custom_runs']=$make('baseline',$blocked);$b['custom_runs']=$make('candidate',$probe);foreach($b['runs']as &$run)$run['metrics']['"+protocol+"']['ok']=9;unset($run);$out['rank']=$joint->compare($a,$b,'all',true);")
                self.assertFalse(r['eligible'])
                self.assertIn(r['reason'],['native_regression','tls_regression'])

    def test_changed_compact_rows_config_role_or_context_cannot_create_a_winner(self):
        changes=["$b['config_sha256']=str_repeat('d',64);",
                 "$b['custom_role']='baseline';",
                 "$b['custom_runs'][0]['cells'][0]['root_ok']=false;",
                 "$b['runs'][0]['context_sha256']=str_repeat('d',64);",
                 "$b['custom_runs'][1]=$b['custom_runs'][0];"]
        for change in changes:
            with self.subTest(change=change):
                r=self.observe("$a['custom_runs']=$make('baseline',$blocked);$b['custom_runs']=$make('candidate',$probe);"+change+"$out['rank']=$joint->compare($a,$b,'all',false);")
                self.assertFalse(r['eligible']);self.assertEqual(r['reason'],'incomparable_result')

    def test_missing_or_partial_repeats_never_qualify(self):
        for change in ["unset($b['custom_runs'][1]);","unset($b['runs'][1]);","unset($b['custom_runs']);"]:
            with self.subTest(change=change):
                r=self.observe("$a['custom_runs']=$make('baseline',$blocked);$b['custom_runs']=$make('candidate',$probe);"+change+"$out['rank']=$joint->compare($a,$b,'all',false);")
                self.assertFalse(r['eligible']);self.assertEqual(r['reason'],'incomparable_result')


if __name__=='__main__':unittest.main()
