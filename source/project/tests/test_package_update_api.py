"""Authentication/consent boundary around privileged package operations."""
import json
import re
from pathlib import Path
import unittest
import test_support_mail_api as mail_fixtures

ROOT=Path(__file__).resolve().parents[1]


class PackageUpdateApiTests(unittest.TestCase):
    def setUp(self):
        self.http=mail_fixtures.SupportMailApiTests('test_mail_status_auth_exact_fields_csrf_and_origin');self.http.setUp();self.addCleanup(self.http.doCleanups)
        self.base=self.http.base
        index=self.base/'index.php';index.write_text(re.sub(r'function nfqwsInstalledVersion\(\): string\s*\{.*?\n\}',"function nfqwsInstalledVersion(): string { return '1.3.1-asus6+b10'; }",index.read_text(),flags=re.S))
        api=ROOT/'webui/web/public/update-api.php'
        if api.is_file():(self.base/'update-api.php').write_text(api.read_text())
        (self.base/'update-dispatch.php').write_text('''<?php
        class AsusUpdateStore {function status(){return ['active'=>null,'history'=>[]];}}
        class AsusUpdatePrepare {static function code($e){return $e->getMessage();}}
        class AsusUpdateDispatch {
          function __construct($s){} function prepare($rev,$req){return $this->record('prepare');}
          function apply($id,$rev,$req){return $this->record('apply');}function status($id){return $this->record('status');}
          function record($action){file_put_contents(__DIR__.'/update-called',$action);return ['id'=>str_repeat('a',32),'revision'=>str_repeat('b',64),'state'=>'prepared','package_version'=>'1.3.1-asus6+b11','identity'=>['exe'=>'PRIVATE_PATH'],'intent'=>['mode'=>'stopped','process'=>['pid'=>999]]];}
        }
        class AsusUpdateCheck {function __construct($s){}function request($force){file_put_contents(__DIR__.'/update-called','check');return ['state'=>'available','code'=>null,'candidate'=>null,'installed_version'=>'1.3.1-asus6+b10'];}function status(){return ['state'=>'checking','code'=>null,'candidate'=>null,'installed_version'=>'1.3.1-asus6+b10'];}}
        ''')
        (self.base/'update-check.php').write_text('<?php require_once __DIR__."/update-dispatch.php";')
    def request(self,params):return self.http.request(params)
    def test_check_and_status_expose_only_the_shared_four_package_fields(self):
        package={'family':'arm_cortex-a9','filename':'nfqws2-native_1.3.2-72_arm_cortex-a9.ipk','size':1000,'sha256':'a'*64,'format':'ipk','series':'24.10','installed_size':2000,'internal':'PRIVATE_INTERNAL'}
        candidate={'revision':'b'*64,'package_version':'1.3.2-72','build':72,'notes':'Update','package':package}
        path=self.base/'update-dispatch.php';path.write_text(path.read_text().replace("'candidate'=>null", "'candidate'=>json_decode('"+json.dumps(candidate)+"',true)"))
        token=self.http.login()
        for command,fields in [('packageupdatecheck',{'force':'0'}),('packageupdatestatus',{'operation_id':''})]:
            code,value=self.request({'cmd':command,'csrf_token':token}|fields);self.assertEqual(code,200,value)
            checked=value if command=='packageupdatecheck'else value['check']
            self.assertEqual(set(checked['candidate']['package']),{'family','filename','size','sha256'})
            self.assertNotIn('PRIVATE_INTERNAL',json.dumps(value))

    def test_new_commands_require_login(self):
        for cmd in ['packageupdatecheck','packageupdateprepare','packageupdateapply','packageupdatestatus']:
            self.assertEqual(self.request({'cmd':cmd,'csrf_token':'bad'})[0],401)
    def test_check_requires_csrf_same_origin_and_exact_fields(self):
        token=self.http.login();p={'cmd':'packageupdatecheck','csrf_token':token,'force':'0'}
        self.assertEqual(self.request(p)[0],200)
        for key in ['url','path','command','token']:
            self.assertEqual(self.request(p|{key:'PRIVATE_CANARY'})[0],400)
        self.assertEqual(self.request(p|{'csrf_token':'bad'})[0],403)
        self.http.origin='https://evil.invalid';self.assertEqual(self.request(p)[0],403)
    def test_password_disabled_keeps_csrf_origin_and_explicit_consent(self):
        token=self.http.login();self.assertEqual(self.http.change('',token)[0],200)
        code,data=self.request({'cmd':'status'});self.assertEqual(code,200)
        p={'cmd':'packageupdatecheck','csrf_token':data['csrf_token'],'force':'0'}
        self.assertEqual(self.request(p|{'csrf_token':'bad'})[0],403)
        self.assertEqual(self.request(p)[0],200)
        self.http.origin='https://evil.invalid';self.assertEqual(self.request(p)[0],403)
        self.http.origin='http://localhost'
        apply={'cmd':'packageupdateapply','csrf_token':data['csrf_token'],'operation_id':'a'*32,'revision':'b'*64,'request_id':'c'*32,'consent':''}
        self.assertEqual(self.request(apply)[0],400)
        self.assertEqual(self.request(apply|{'consent':'install'})[0],200)
    def test_apply_requires_explicit_exact_consent_and_revision(self):
        token=self.http.login();p={'cmd':'packageupdateapply','csrf_token':token,'operation_id':'a'*32,'revision':'b'*64,'request_id':'c'*32,'consent':'install'}
        for key in ['operation_id','revision','request_id','consent']:
            self.assertEqual(self.request(p|{key:'wrong'})[0],400)
        self.assertFalse((self.base/'update-called').exists());code,value=self.request(p);self.assertEqual(code,200)
        self.assertEqual(value['service_intent'],'stopped');self.assertNotIn('PRIVATE_PATH',json.dumps(value));self.assertNotIn('identity',value)
    def test_status_is_read_only_and_operation_projection_hides_process_paths(self):
        token=self.http.login();p={'cmd':'packageupdatestatus','csrf_token':token,'operation_id':'a'*32}
        code,value=self.request(p);self.assertEqual(code,200);self.assertNotIn('PRIVATE_PATH',json.dumps(value));self.assertEqual(value['operation']['id'],'a'*32)
    def test_running_update_blocks_ordinary_mutations_but_status_remains_available(self):
        token=self.http.login();(self.base/'update-busy').touch();before=self.http.auth.read_bytes()
        for params in [{'cmd':'start'},{'cmd':'restart'},{'cmd':'filesave','filename':'nfqws2.conf','content':'changed'},{'cmd':'password','password':'new','confirmation':'new','csrf_token':token}]:
            self.assertEqual(self.request(params)[0],409)
        self.assertEqual(self.http.auth.read_bytes(),before);self.assertEqual(self.request({'cmd':'status'})[0],200)


if __name__=='__main__':unittest.main()
