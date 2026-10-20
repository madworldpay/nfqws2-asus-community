import json, subprocess, unittest
from test_dpi_normalize import PHP,PUBLIC

class DpiNativeTests(unittest.TestCase):
    def call(self,raw,group=2):
        code="if(!is_file($argv[1].'/dpi-native.php')){echo '{\"error\":\"missing\"}';exit;}require $argv[1].'/dpi-native.php';try{echo json_encode(AsusDpiNative::group($argv[2],(int)$argv[3]));}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),raw,str(group)],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
    def test_local_result_retains_original_fields_and_unknown_values(self):
        v={'schema_version':1,'version':'5.0.0-alpha.21','results':{'domain_inspection':[{'domain':'private.example','resolved':'10.0.0.1','http':'ok','http_detail':'http_200','extra':'LOCAL_ONLY'}]}}
        r=self.call(json.dumps(v));self.assertNotIn('error',r);self.assertEqual(r['document'],v)
    def test_rejects_duplicate_keys_wrong_group_and_nonfinite_data(self):
        for raw in ['{"schema_version":1,"schema_version":1,"results":{"domain_inspection":[]}}','{"schema_version":1,"results":{"tcp16":[]}}','{"schema_version":1,"results":{"domain_inspection":[1e999]}}']:
            with self.subTest(raw=raw):self.assertIn('error',self.call(raw))
