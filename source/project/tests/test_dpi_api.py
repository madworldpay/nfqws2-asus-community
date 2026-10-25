from pathlib import Path
import json
import subprocess
import test_auth_api as auth_api
from test_support_mail_api import SupportMailApiTests

class DpiApiTests(SupportMailApiTests):
    def setUp(self):
        super().setUp()
        for name in ['dpi-api.php','dpi-jobs.php','dpi-install.php','openwrt-dpi.php','dpi-runtime.php','dpi-store.php','dpi-catalog.php','dpi-normalize.php','dpi-options.php','support-json-schema.php']:
            src=auth_api.ROOT/'webui/web/public'/name
            if src.exists():(self.base/name).write_text(src.read_text())
        (self.base/'dpi-jobs.php').write_text('''<?php
        class AsusDpiJobs {
          static function code($c){return 'invalid_request';}
          function status(){return ['active'=>null,'history'=>[]];}
          function startRun($id,$tests,$heavy){file_put_contents(__DIR__.'/dpi-called',json_encode([$tests,$heavy]));return ['id'=>str_repeat('a',32),'state'=>'queued'];}
          function startInstall($id,$yes){file_put_contents(__DIR__.'/dpi-called','install');return ['id'=>str_repeat('a',32),'state'=>'queued'];}
          function stop($id){return ['id'=>$id,'state'=>'stopping'];}
          function deleteResult($id){}
        }''')
    def test_dpi_auth_csrf_origin_exact_fields_and_no_network_on_status(self):
        p={'cmd':'dpistatus','csrf_token':'bad'};self.assertEqual(self.request(p)[0],401)
        token=self.login();p['csrf_token']=token
        self.assertEqual(self.request(p),(200,{'active':None,'history':[]}));self.assertFalse((self.base/'dpi-called').exists())
        for extra in ['url','path','command','proxy','interface','tests']:
            self.assertEqual(self.request(p|{extra:'PRIVATE_CANARY'})[0],400)
        self.assertEqual(self.request(p|{'csrf_token':'bad'})[0],403)
        self.origin='https://evil.invalid';self.assertEqual(self.request(p)[0],403)
    def test_install_and_run_validation(self):
        token=self.login();base={'csrf_token':token,'request_id':'11111111-1111-4111-8111-111111111111'}
        for consent in ['','run','true']:
            self.assertEqual(self.request(base|{'cmd':'dpiinstall','consent':consent})[0],400)
        self.assertEqual(self.request(base|{'cmd':'dpiinstall','consent':'install'})[0],200)
        p=base|{'cmd':'dpistart','tests':'12','heavy_consent':''};self.assertEqual(self.request(p),(410,{'error':'workflow_changed','field':None}))
        self.assertEqual((self.base/'dpi-called').read_text(),'install')
        for value in ['', '11','21','7','1,2','/tmp/x',' 12']:
            self.assertEqual(self.request(p|{'tests':value})[0],400)
        self.assertEqual(self.request(p|{'tests':['1','2']})[0],400)
        self.assertEqual(self.request(base|{'cmd':'dpistop','job_id':'../../x'})[0],400)
    def test_options_json_is_bounded_and_malformed_input_does_not_launch(self):
        token=self.login();p={'csrf_token':token,'request_id':'11111111-1111-4111-8111-111111111111','cmd':'dpistart','tests':'12','heavy_consent':''}
        self.assertEqual(self.request(p|{'options':'{"profile":"ru"}'})[0],410)
        self.assertFalse((self.base/'dpi-called').exists())
        for value in ['[]','null','{','{"profile":"ru","profile":"global"}','x'*131073]:
            self.assertEqual(self.request(p|{'options':value})[0],400)
            self.assertFalse((self.base/'dpi-called').exists())
