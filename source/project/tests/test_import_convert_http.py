"""Text conversion uses the real authenticated read-only import route."""
import json,os,subprocess,unittest,urllib.parse
import test_import_http as import_http
from test_import_keenetic import FULL,PUBLIC
class ImportConvertHttpTests(unittest.TestCase):
 setUp=import_http.ImportHttpTests.setUp
 login=import_http.ImportHttpTests.login
 request=import_http.ImportHttpTests.request
 change=import_http.ImportHttpTests.change
 def post(self,**extra):return {'cmd':'importconvert','csrf_token':self.token,'text':FULL}|extra
 def test_auth_csrf_origin_closed_fields_and_read_only_conversion(self):
  self.assertEqual(self.request({'cmd':'importconvert','csrf_token':'x','text':FULL})[0],401);self.token=self.login();self.assertEqual(self.request(self.post(csrf_token='bad'))[0],403);self.origin='https://evil.invalid';self.assertEqual(self.request(self.post())[0],403);self.origin='http://localhost'
  for change in [{'root':'/private'},{'text':[]},{'text':'x'*65537},{'csrf_token':[]}]:self.assertEqual(self.request(self.post(**change))[0],400)
  (self.base/'update-busy').touch();before=(self.base/'resources/nfqws2.conf').read_bytes();code,v=self.request(self.post());self.assertEqual(code,200);self.assertEqual(set(v),{'document'});self.assertEqual(json.loads(v['document'])['schema_version'],2);self.assertFalse((self.base/'import-state').exists());self.assertFalse((self.base/'dns-state').exists());self.assertEqual((self.base/'resources/nfqws2.conf').read_bytes(),before);code,v=self.request({'cmd':'importinspect','csrf_token':self.token,'documents':json.dumps([v['document']])});self.assertEqual(code,200);self.assertIn('NFQWS_ARGS_CUSTOM',v['values'])
 def test_unsupported_input_has_a_closed_human_mappable_error(self):
  self.token=self.login();self.assertEqual(self.request(self.post(text='--filter-tcp=443 --dpi-desync=fake')),(400,{'error':'unsupported_keenetic_strategy'}));self.assertFalse((self.base/'import-state').exists())
 def test_real_cgi_multiline_paste_remains_only_an_in_memory_document(self):
  cgi=os.environ.get('PHP_CGI_TEST_BINARY')
  if not cgi:self.skipTest('matching CGI required')
  self.token=self.login();data=urllib.parse.urlencode(self.post(text=(PUBLIC.parents[2]/'core/etc/nfqws2/nfqws2.conf').read_text()));env=os.environ|{'REDIRECT_STATUS':'200','SCRIPT_FILENAME':str(self.base/'index.php'),'REQUEST_METHOD':'POST','CONTENT_TYPE':'application/x-www-form-urlencoded','CONTENT_LENGTH':str(len(data.encode())),'HTTP_HOST':'localhost','HTTP_ORIGIN':'http://localhost','HTTP_COOKIE':'nfqws_asus_session='+self.sessions['user-one'],'QUERY_STRING':''};p=subprocess.run([cgi,'-n','-d','session.save_path='+str(self.base)],input=data,capture_output=True,text=True,env=env);self.assertEqual(p.returncode,0,p.stdout+p.stderr);head,body=p.stdout.split('\n\n',1);self.assertIn('Cache-Control: no-store',head);v=json.loads(body);self.assertEqual(set(v),{'document'});self.assertEqual(json.loads(v['document'])['mode'],'config');self.assertIn('--out-range=<n2',json.loads(v['document'])['config']);self.assertFalse((self.base/'import-state').exists());self.assertFalse((self.base/'dns-state').exists())
