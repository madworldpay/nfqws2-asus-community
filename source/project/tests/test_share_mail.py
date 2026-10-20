import json,os,subprocess,tempfile,unittest,uuid
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
from test_share_bundle_api import share_files

class ShareMailTests(unittest.TestCase):
    def call(self,config,body):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'operator.json';p.write_text(json.dumps(config));p.chmod(0o600)
            code='''require $argv[1].'/support-mail.php';try{$m=new AsusSupportMail($argv[2],'/missing-test-ca',(int)$argv[3]);'''+body+'''}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(p),str(os.getuid())],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def test_v3_flag_is_opt_in_and_existing_availability_contract_unchanged(self):
        config={'enabled':False,'url':''}
        v=self.call(config,'echo json_encode([$m->availability(),$m->shareAvailability()]);')
        self.assertIsInstance(v,list,v)
        self.assertEqual(v[0],{'configured':False,'code':'not_configured','dpi_attachments':False})
        self.assertEqual(v[1],{'configured':False,'code':'not_configured','dpi_attachments':False,'sharing_v3':False,'sharing_v4':False})
        config={'enabled':True,'url':'https://relay.invalid/nfqws-support/v1/reports','sharing_v3_enabled':True}
        self.assertEqual(self.call(config,'echo json_encode($m->shareAvailability());')['code'],'https_unavailable')
        config['sharing_v3_enabled']='yes'
        self.assertEqual(self.call(config,'echo json_encode($m->shareAvailability());')['code'],'invalid_config')
    def test_unconfigured_sender_and_location_never_make_request(self):
        sid=str(uuid.uuid4());wire=json.dumps({'version':3,'submission_id':sid,'files':share_files(('strategy',))})
        literal=json.dumps(wire).replace('\\u','\\u')
        # Pass JSON in a PHP single-quoted literal, never a shell command.
        escaped=wire.replace('\\','\\\\').replace("'","\\'")
        v=self.call({'enabled':False,'url':''},f"echo json_encode([$m->sendShare('{escaped}','{sid}'),$m->location()]);")
        self.assertIsInstance(v,list,v)
        self.assertEqual(v[0]['state'],'failed_safe');self.assertEqual(v[0]['code'],'not_configured')
        self.assertEqual(v[1],{'available':False,'code':'not_configured'})
        self.assertEqual(self.call({'enabled':False,'url':''},f"echo json_encode($m->sendShare('{{}}','{sid}'));" )['state'],'invalid')

    def test_v4_flag_is_separate_and_defaults_to_false(self):
        v=self.call({'enabled':False,'url':''},'echo json_encode($m->shareAvailability());')
        self.assertIs(v.get('sharing_v4'),False)
        config={'enabled':True,'url':'https://relay.invalid/nfqws-support/v1/reports','sharing_v3_enabled':True,'sharing_v4_enabled':True}
        self.assertEqual(self.call(config,'echo json_encode($m->shareAvailability());')['code'],'https_unavailable')
        config['sharing_v4_enabled']='yes'
        self.assertEqual(self.call(config,'echo json_encode($m->shareAvailability());')['code'],'invalid_config')
