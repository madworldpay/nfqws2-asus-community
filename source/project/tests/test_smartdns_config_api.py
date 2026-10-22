"""Closed HTTP inputs cannot become shell arguments, paths or hidden defaults."""
import json
import subprocess
import unittest
from test_dpi_normalize import PHP,PUBLIC
from test_smartdns_profile import profile


class SmartDnsConfigApiTests(unittest.TestCase):
    def validate(self,rows):
        code=r'''$f=$argv[1].'/smartdns-config-api.php';if(!is_file($f)){echo json_encode(['error'=>'missing_config_api']);exit;}
        require $f;$out=[];foreach(json_decode(stream_get_contents(STDIN),true) as $row){try{AsusSmartDnsConfigApi::validate($row);$out[]='ok';}catch(Throwable $e){$out[]=AsusSmartDnsConfigApi::error($e);}}echo json_encode($out);'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(rows),capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)

    def test_read_draft_validation_preview_and_connection_commands_have_exact_shapes(self):
        base={'csrf_token':'token'}
        rows=[base|{'cmd':c} for c in ['routercheckup','smartdnsconfigstatus']]
        rows+=[base|{'cmd':'smartdnsdraft','profile':json.dumps(profile())},
               base|{'cmd':'smartdnsvalidate','request_id':'a'*32,'profile_hash':'b'*64},
               base|{'cmd':'smartdnspreview','preview_id':'a'*32},
               base|{'cmd':'smartdnsapply','request_id':'a'*32,'preview_id':'b'*32,'profile_hash':'c'*64,'baseline_hash':'d'*64}]
        rows+=[base|{'cmd':c,'request_id':'a'*32} for c in ['smartdnsconfirm','smartdnsrollback']]
        self.assertEqual(self.validate(rows),['ok']*8)

    def test_unknown_arguments_paths_pollution_or_malformed_identifiers_are_rejected(self):
        base={'cmd':'smartdnsvalidate','csrf_token':'token','request_id':'a'*32,'profile_hash':'b'*64}
        rows=[base|{'path':'/tmp/caller-choice'},base|{'request_id':'../../outside'},base|{'profile_hash':[]},
              base|{'cmd':'smartdnsrestart'},base|{'csrf_token':{}},base|{'config':'server /tmp/command'},
              {'cmd':'smartdnsdraft','csrf_token':'token','profile':'[]'},
              {'cmd':'smartdnsdraft','csrf_token':'token','profile':'x'*65537}]
        out=self.validate(rows);self.assertIsInstance(out,list)
        for item in out:self.assertEqual(item['error'],'invalid_request')

    def test_profile_field_errors_are_specific_and_internal_errors_are_not_echoed(self):
        p=profile();p['upstreams'][0]['address']='resolver.example';p['upstreams'][0]['bootstrap']=[]
        out=self.validate([{'cmd':'smartdnsdraft','csrf_token':'token','profile':json.dumps(p)}])
        self.assertEqual(out,[{'error':'invalid_profile','field':'upstreams.0.bootstrap'}])
        code=r'''require $argv[1].'/smartdns-config-api.php';echo json_encode(AsusSmartDnsConfigApi::error(new RuntimeException('PRIVATE_URL_AND_PATH_CANARY')));'''
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0);self.assertNotIn('CANARY',r.stdout);self.assertEqual(json.loads(r.stdout),{'error':'internal_error'})

    def test_dns_hook_permissions_have_a_public_safe_error_code(self):
        code=r'''require $argv[1].'/smartdns-config-api.php';echo json_encode(AsusSmartDnsConfigApi::error(new RuntimeException('hook_permissions')));'''
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(json.loads(r.stdout),{'error':'hook_permissions'})


if __name__=='__main__':unittest.main()
