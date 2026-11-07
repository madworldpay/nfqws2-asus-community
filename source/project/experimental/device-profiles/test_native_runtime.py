import json
import os
from pathlib import Path
import subprocess
import unittest
import test_lab as lab

HERE=Path(__file__).resolve().parent
PHP=os.environ.get('PHP_TEST_BINARY','/usr/bin/php')


class NativeRuntime(unittest.TestCase):
    def call(self,operation,value):
        code='''require $argv[1].'/platform.php';require $argv[1].'/share-resources.php';require $argv[1].'/import-plan.php';
        require $argv[2].'/openwrt/config.php';$path=$argv[2].'/experimental/device-profiles/device-profiles-runtime.php';
        if(!is_file($path)){echo json_encode(['error'=>'missing_native_runtime']);exit;}
        require $path;$v=json_decode(stream_get_contents(STDIN),true);
        try{if($argv[3]==='validate'){NfqwsDeviceProfilesRuntime::validateRequest($v);$out=['valid'=>true];}
        else $out=['owned'=>NfqwsDeviceProfilesRuntime::ownedQueue($v['queue'],$v['instance'],$v['argv'],$v['bindings'])];
        echo json_encode($out,JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(lab.PUBLIC),str(HERE.parents[1]),operation],input=json.dumps(value),text=True,capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
        self.assertTrue(p.stdout.lstrip().startswith('{'),p.stdout)
        return json.loads(p.stdout)

    def test_apply_requires_saved_revision_exact_consent_and_bounded_fields(self):
        valid={'cmd':'deviceprofilesapply','csrf_token':'token','revision':'a'*64,'request_id':'b'*32,'consent':'apply','start_after':'1'}
        self.assertEqual(self.call('validate',valid),{'valid':True})
        for update in [{'consent':'yes'},{'start_after':'true'},{'extra':'x'},{'revision':'x'},{'request_id':[]},{'cmd':'deviceprofilesdeleteall'}]:
            with self.subTest(update=update):self.assertEqual(self.call('validate',valid|update),{'error':'invalid_request'})

    def test_queue_ownership_requires_procd_actual_argv_and_kernel_port_to_agree(self):
        command=['/usr/bin/nfqws2','--user=nobody','--qnum=41000','--filter-tcp=443']
        value={'queue':41000,'instance':{'running':True,'pid':1234,'command':command},'argv':command,'bindings':{'41000':1234}}
        self.assertEqual(self.call('ownership',value),{'owned':True})
        for update in [{'bindings':{'41000':999}},{'argv':['/bin/sh',*command]},{'instance':{'running':True,'pid':1234,'command':['/bin/sh',*command]}},{'instance':{'running':False,'pid':1234,'command':command}}]:
            with self.subTest(update=update):self.assertEqual(self.call('ownership',value|update),{'owned':False})

    def test_import_is_bounded_and_needs_explicit_lua_choice(self):
        value={'cmd':'deviceprofilesimport','csrf_token':'t','name':'Example','document':'{}','trusted_lua':'0'}
        self.assertEqual(self.call('validate',value),{'valid':True})
        for update in [{'trusted_lua':'yes'},{'document':'x'*4194305},{'name':'x'*257},{'document':{} }]:
            with self.subTest(update=str(update)[:80]):self.assertEqual(self.call('validate',value|update),{'error':'invalid_request'})

if __name__=='__main__':unittest.main()
