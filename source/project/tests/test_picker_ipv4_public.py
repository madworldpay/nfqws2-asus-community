"""The mixed public request must preserve the proven internal typed scope."""
import json
import os
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


class Ipv4PublicTests(unittest.TestCase):
    def php(self, body):
        with tempfile.TemporaryDirectory() as directory:
            p=subprocess.run([PHP,'-n','-r',"umask(0077);require $argv[1].'/strategy-picker-runtime.php';require_once $argv[1].'/strategy-picker-targets.php';"+body,
                str(PUBLIC),directory,str(os.getuid())],capture_output=True,text=True,timeout=12)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)

    def test_public_preview_request_and_planning_identity_agree_without_dns_or_state(self):
        r=self.php(r'''
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$r=new NfqwsStrategyPickerRuntime($s);
        $raw="https://8.8.8.8/private?secret=NO_EXPORT\nEXAMPLE.COM.\nhttps://1.1.1.1/";
        $p=$r->dispatch(['cmd'=>'pickertargets','csrf_token'=>'fixture','custom_sites'=>$raw]);
        $custom=NfqwsStrategyPickerRequest::custom($raw,'1');
        $selection=NfqwsStrategyPickerRequest::selection(false,'all',true,$custom,'32');
        $plan=(new ReflectionMethod($r,'planSelection'))->invoke($r,$selection);
        echo json_encode(['preview'=>$p,'custom'=>$custom,'selection'=>$selection,'plan'=>$plan,
          'no_state'=>!file_exists($s->root)]);
        ''')
        self.assertTrue(r['preview']['valid']);self.assertEqual(r['preview']['schema_version'],2)
        self.assertEqual(r['custom'],dict(hosts=['1.1.1.1','8.8.8.8','example.com'],only=True))
        self.assertEqual(r['selection']['custom_target_policy'],'custom-public-targets-v2')
        self.assertEqual([x['kind']for x in r['selection']['custom_targets']],['ipv4','ipv4','domain'])
        self.assertEqual(r['plan']['budget']['concurrency'],32);self.assertTrue(r['no_state'])
        self.assertNotIn('NO_EXPORT',json.dumps(r));self.assertNotIn('private?',json.dumps(r))

    def test_same_canonical_mixed_retry_binds_pool_mode_goal_and_target_identity(self):
        r=self.php(r'''
        $make=fn($raw,$only,$goal='all',$pool='32')=>NfqwsStrategyPickerRequest::selection(false,$goal,true,
          NfqwsStrategyPickerRequest::custom($raw,$only),$pool);
        $a=$make("EXAMPLE.COM\n8.8.8.8",'0');$j=$a+['request_id'=>str_repeat('a',32),
          'selection_sha256'=>NfqwsStrategyPickerRequest::digest($a)];$out=[];
        foreach([$make("https://8.8.8.8/path?token=secret\nexample.com.",'0'),
          $make("example.com\n1.1.1.1",'0'),$make("example.com\n8.8.8.8",'1'),
          $make("example.com\n8.8.8.8",'0','youtube'),$make("example.com\n8.8.8.8",'0','all','64')]as $v){
          try{$out[]=NfqwsStrategyPickerRequest::retry($j,str_repeat('a',32),$v);}
          catch(Throwable $e){$out[]=$e->getMessage();}}
        echo json_encode($out);
        ''')
        self.assertEqual(r,[True]+['request_conflict']*4)

    def test_public_boundary_rejects_complete_bad_sets_and_never_echoes_urls(self):
        r=self.php(r'''
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$r=new NfqwsStrategyPickerRuntime($s);$out=[];
        foreach(['192.168.1.1','127.0.0.1','100.64.0.1','192.31.196.1','198.51.100.1','224.0.0.1',
          '8.8.8.8/32','008.8.8.8','https://user:SECRET@8.8.8.8/','[::1]','8.8.8.8:443','t.me',
          implode("\n",array_map(fn($i)=>"site$i.example.com",range(1,9)))."\n8.8.8.8",str_repeat(' ',4096).'8.8.8.8']as $bad){
          $raw="example.com\n".$bad;
          try{$p=$r->dispatch(['cmd'=>'pickertargets','csrf_token'=>'fixture','custom_sites'=>$raw]);}
          catch(Throwable $e){$p=['valid'=>false,'hosts'=>[],'code'=>$e->getMessage()];}
          try{NfqwsStrategyPickerRequest::custom($raw,'1');$code='accepted';}catch(Throwable $e){$code=$e->getMessage();}
          $out[]=['preview'=>$p,'request'=>$code];
        }echo json_encode($out);
        ''')
        for row in r:
            self.assertFalse(row['preview']['valid']);self.assertEqual(row['preview']['hosts'],[])
            self.assertEqual(row['request'],'invalid_custom_targets')
        self.assertNotIn('SECRET',json.dumps(r));self.assertNotIn('user:',json.dumps(r))

    def test_public_domain_contract_remains_exact_and_cannot_receive_typed_overrides(self):
        r=self.php(r'''
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$r=new NfqwsStrategyPickerRuntime($s);
        $raw="https://BÜCHER.de/path\nEXAMPLE.COM.";
        $p=['cmd'=>'pickertargets','csrf_token'=>'fixture','custom_sites'=>$raw];$old=NfqwsStrategyPickerTargets::inspect($raw);
        $out=['exact'=>$r->dispatch($p)===$old];
        foreach(['custom_targets','target_policy_version','pins','resolver','custom_scope']as $k){
          try{$r->dispatch($p+[$k=>'spoof']);$out[$k]='accepted';}catch(Throwable $e){$out[$k]=$e->getMessage();}}
        echo json_encode($out);
        ''')
        self.assertTrue(r.pop('exact'));self.assertEqual(list(r.values()),['invalid_request']*5)


if __name__=='__main__':unittest.main()
