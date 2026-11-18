"""Mixed-target parsing with exact legacy domain-v1 compatibility."""
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC


class PickerIpv4TargetTests(unittest.TestCase):
    def php(self, body):
        r=subprocess.run([PHP,'-n','-r',"require $argv[1].'/strategy-picker-core.php';require $argv[1].'/strategy-picker-targets.php';"+body,
            str(PUBLIC)],capture_output=True,text=True,timeout=8)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)

    def test_internal_mixed_targets_keep_ip_identity_and_deduplicate_root_urls(self):
        r=self.php(r'''
        echo json_encode(NfqwsStrategyPickerTargets::inspectMixed("8.8.8.8\nhttps://8.8.8.8/private?token=secret\nEXAMPLE.COM.\nhttps://1.1.1.1/"));
        ''')
        self.assertTrue(r['valid']);self.assertEqual(r['hosts'],['8.8.8.8','example.com','1.1.1.1'])
        self.assertEqual(r['schema_version'],2)
        self.assertEqual(r['target_policy_version'],'custom-public-targets-v2')
        self.assertEqual(r['targets'],[dict(kind=k,host=h)for k,h in [('ipv4','8.8.8.8'),('domain','example.com'),('ipv4','1.1.1.1')]])
        self.assertNotIn('secret',json.dumps(r));self.assertNotIn('private',json.dumps(r))

    def test_domain_only_internal_parsing_is_byte_identical_to_existing_domain_contract(self):
        r=self.php(r'''
        $text="https://BÜCHER.de/path\nEXAMPLE.COM.\nexample.com";
        $old=NfqwsStrategyPickerTargets::inspect($text);$new=NfqwsStrategyPickerTargets::inspectMixed($text);
        echo json_encode(['identical'=>json_encode($old)===json_encode($new),'result'=>$new]);
        ''')
        self.assertTrue(r['identical']);self.assertNotIn('schema_version',r['result'])

    def test_special_use_and_alternative_numeric_forms_never_produce_partial_targets(self):
        r=self.php(r'''
        $out=[];foreach(['192.168.1.1','192.168.2.41','127.0.0.1','10.0.0.1','100.64.0.1','169.254.1.1',
          '198.18.0.1','198.51.100.1','203.0.113.1','224.0.0.1','255.255.255.255','0.0.0.0',
          '8.8.8','008.8.8.8','0x8.8.8.8','134744072','8.8.8.8.','８.８.８.８','https://[2001:4860:4860::8888]/',
          '8.8.8.8:443','https://8.8.8.8:','8.8.8.8/32','https://user@8.8.8.8/']as $bad){
          $v=NfqwsStrategyPickerTargets::inspectMixed("example.com\n".$bad);$out[]=['valid'=>$v['valid'],'hosts'=>$v['hosts'],'errors'=>$v['errors']];
        }echo json_encode($out);
        ''')
        self.assertEqual(len(r),23)
        for x in r:
            self.assertFalse(x['valid']);self.assertEqual(x['hosts'],[]);self.assertEqual(x['errors'][0]['line'],2)

    def test_combined_ten_limit_preserves_legacy_fingerprint_and_request_plan(self):
        r=self.php(r'''
        $five="example.com\n8.8.8.8\n1.1.1.1\na.org\nb.org";
        $ten=$five."\nc.org\nd.org\ne.org\nf.org\ng.org";
        $a=NfqwsStrategyPickerTargets::inspectMixed($five);
        $b=NfqwsStrategyPickerTargets::inspectMixed("b.org\n1.1.1.1\nexample.com\nhttps://8.8.8.8/\na.org");
        $custom=NfqwsStrategyPickerRequest::custom($ten,'1');
        echo json_encode(['five'=>$a,'same_digest'=>$a['sha256']===$b['sha256'],
          'ten'=>NfqwsStrategyPickerTargets::inspectMixed($ten),'request'=>$custom,
          'budget'=>NfqwsStrategyPickerBudget::custom(['available_kib'=>100000,'probe_seconds'=>510],10),
          'eleven'=>NfqwsStrategyPickerTargets::inspectMixed($ten."\nh.org")]);
        ''')
        self.assertTrue(r['five']['valid']);self.assertTrue(r['same_digest'])
        self.assertTrue(r['ten']['valid']);self.assertEqual(len(r['ten']['hosts']),10)
        self.assertEqual(r['request']['hosts'],sorted(r['ten']['hosts']));self.assertEqual(r['budget']['custom']['max_hosts'],10)
        self.assertFalse(r['eleven']['valid']);self.assertEqual(r['eleven']['errors'],[dict(line=11,code='too_many_hosts')])

    def test_legacy_domain_validator_stays_closed_while_public_requests_use_the_mixed_chain(self):
        r=self.php(r'''
        $out=[];foreach(['8.8.8.8','https://1.1.1.1/']as $raw){
          $out[]=NfqwsStrategyPickerTargets::inspect($raw)['valid'];
          $out[]=NfqwsStrategyPickerRequest::custom($raw,'1');
        }echo json_encode($out);
        ''')
        self.assertEqual(r,[False,dict(hosts=['8.8.8.8'],only=True),False,dict(hosts=['1.1.1.1'],only=True)])


if __name__=='__main__':unittest.main()
