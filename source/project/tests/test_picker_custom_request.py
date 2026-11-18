"""Typed custom generation and request retries must identify the same work."""
import json
import os
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


class CustomRequestTests(unittest.TestCase):
    def php(self, body):
        with tempfile.TemporaryDirectory() as directory:
            code="umask(0077);require $argv[1].'/strategy-picker-runtime.php';"+body
            result=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),directory,str(os.getuid())],
                                  capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stderr,'')
        return json.loads(result.stdout)

    def test_preview_returns_canonical_hosts_without_creating_a_job_or_resolving_dns(self):
        r=self.php(r'''
        $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$r=new NfqwsStrategyPickerRuntime($s);
        $out=$r->dispatch(['cmd'=>'pickertargets','csrf_token'=>'x','custom_sites'=>"BÜCHER.de\nhttps://example.com/private?secret=value\nEXAMPLE.COM."]);
        echo json_encode(['preview'=>$out,'no_state'=>!file_exists($argv[2].'/picker')]);
        ''')
        self.assertTrue(r['no_state'])
        self.assertEqual(r['preview']['hosts'],['xn--bcher-kva.de','example.com'])
        self.assertTrue(r['preview']['valid'])
        self.assertNotIn('secret',json.dumps(r))

    def test_preview_reports_line_errors_and_returns_no_partially_usable_hosts(self):
        r=self.php(r'''
        $r=new NfqwsStrategyPickerRuntime(new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]));
        echo json_encode($r->dispatch(['cmd'=>'pickertargets','csrf_token'=>'x',
          'custom_sites'=>"example.com\nfoo.local\nhttps://t.me/private\ntelegram.org\nother.com"]));
        ''')
        self.assertFalse(r['valid']);self.assertEqual(r['hosts'],[])
        self.assertEqual(r['errors'],[{'line':2,'code':'invalid_hostname'},
                                     {'line':3,'code':'telegram_excluded'},{'line':4,'code':'telegram_excluded'}])

    def test_typed_pair_is_allowed_only_for_synthesis_and_limits_input_bytes(self):
        r=self.php(r'''
        $base=['cmd'=>'pickersynthesize','csrf_token'=>'x','request_id'=>str_repeat('a',32),'consent'=>'test','goal'=>'all'];
        $pair=['custom_sites'=>str_repeat(' ',4085).'example.com','custom_only'=>'1'];$out=[];
        foreach([$base+$pair,array_replace($base,['cmd'=>'pickerstart'])+$pair,$base+['custom_sites'=>'example.com'],
          $base+['custom_only'=>'0'],$base+array_replace($pair,['custom_sites'=>str_repeat(' ',4086).'example.com']),
          $base+array_replace($pair,['custom_only'=>'true']),$base+array_replace($pair,['custom_sites'=>['example.com']]) ]as $p){
          try{NfqwsStrategyPickerRuntime::validateRequest($p);$out[]='accepted';}catch(Throwable $e){$out[]=$e->getMessage();}
        }echo json_encode($out);
        ''')
        self.assertEqual(r,['accepted']+['invalid_request']*6)

    def test_canonical_selection_never_persists_raw_urls_and_rejects_unsafe_modes(self):
        r=self.php(r'''
        $c=NfqwsStrategyPickerRequest::custom("https://BÜCHER.de/path?token=secret\nexample.com\nEXAMPLE.COM.",'0');
        $out=['selection'=>NfqwsStrategyPickerRequest::selection(false,'instagram,youtube',true,$c),'bad'=>[]];
        foreach([[false,'all',false,$c],[true,'all',true,$c],[false,'all',true,['hosts'=>['127.0.0.1'],'only'=>false]],
          [false,'all',true,['hosts'=>['example.com'],'only'=>'1']],[false,'youtube',true,['hosts'=>['example.com'],'only'=>true]]]as $args){
          try{NfqwsStrategyPickerRequest::selection(...$args);$out['bad'][]='accepted';}catch(Throwable $e){$out['bad'][]=$e->getMessage();}
        }echo json_encode($out);
        ''')
        self.assertEqual(r['selection'],{'search':'synthesis','extended':False,'goal':'youtube,instagram',
                                        'custom_hosts':['example.com','xn--bcher-kva.de'],'custom_only':False})
        self.assertEqual(r['bad'],['invalid_request']*5)
        self.assertNotIn('secret',json.dumps(r))

    def test_retry_accepts_only_the_same_canonical_semantics_and_never_old_digest_drift(self):
        r=self.php(r'''
        $a=NfqwsStrategyPickerRequest::selection(false,'all',true,NfqwsStrategyPickerRequest::custom("example.com\nbücher.de",'0'));
        $old=$a+['request_id'=>str_repeat('a',32)];$old['selection_sha256']=NfqwsStrategyPickerRequest::digest($a);
        $same=NfqwsStrategyPickerRequest::selection(false,'all',true,NfqwsStrategyPickerRequest::custom("https://XN--BCHER-KVA.DE/path\nEXAMPLE.COM.",'0'));
        $out=['same'=>NfqwsStrategyPickerRequest::retry($old,str_repeat('a',32),$same),
          'new'=>NfqwsStrategyPickerRequest::retry($old,str_repeat('b',32),$same),'bad'=>[]];
        foreach([array_replace($a,['goal'=>'youtube']),array_replace($a,['custom_only'=>true]),
          array_replace($a,['custom_hosts'=>['other.com']]),['search'=>'profiles','extended'=>false,'goal'=>'all']]as $changed){
          try{NfqwsStrategyPickerRequest::retry($old,str_repeat('a',32),$changed);$out['bad'][]='accepted';}catch(Throwable $e){$out['bad'][]=$e->getMessage();}
        }
        $old['selection_sha256']=str_repeat('f',64);
        try{NfqwsStrategyPickerRequest::retry($old,str_repeat('a',32),$same);$out['bad'][]='accepted';}catch(Throwable $e){$out['bad'][]=$e->getMessage();}
        echo json_encode($out);
        ''')
        self.assertTrue(r['same']);self.assertFalse(r['new'])
        self.assertEqual(r['bad'],['request_conflict']*5)

    def test_legacy_retry_rederives_goal_search_and_extended_instead_of_accepting_request_id_alone(self):
        r=self.php(r'''
        $old=['request_id'=>str_repeat('a',32),'search'=>'profiles','extended'=>false,'goal'=>'youtube'];$out=[];
        foreach([[false,'youtube',false],[false,'discord',false],[true,'youtube',false],[false,'youtube',true]]as $args){
          try{$out[]=NfqwsStrategyPickerRequest::retry($old,str_repeat('a',32),NfqwsStrategyPickerRequest::selection(...$args));}catch(Throwable $e){$out[]=$e->getMessage();}
        }echo json_encode($out);
        ''')
        self.assertEqual(r,[True,'request_conflict','request_conflict','request_conflict'])

    def test_ten_sites_are_allowed_and_invalid_input_fails_before_start(self):
        r=self.php(r'''
        $ten=implode("\n",array_map(fn($i)=>"site$i.example.com",range(1,10)));
        $out=[];foreach(['',$ten,$ten."\nsite11.example.com",'cdn.telegram.org',"example.com\n\xff.com"]as $raw){
          try{NfqwsStrategyPickerRequest::custom($raw,'0');$out[]='accepted';}catch(Throwable $e){$out[]=$e->getMessage();}
        }echo json_encode($out);
        ''')
        self.assertEqual(r,['invalid_custom_targets','accepted']+['invalid_custom_targets']*3)


if __name__=='__main__':unittest.main()
