"""Real authenticated blob route: closed requests, admission locks, exact bytes."""
import base64,fcntl,hashlib,json,os,subprocess,unittest,urllib.parse
import test_share_router_http as share_http
from test_blob_store import BINARY,FIELDS
from test_dpi_normalize import PHP

class BlobHttpTests(unittest.TestCase):
 login=share_http.ShareRouterTests.login
 request=share_http.ShareRouterTests.request
 change=share_http.ShareRouterTests.change
 def setUp(self):
  share_http.ShareRouterTests.setUp(self);root=self.base/'resources';root.chmod(0o755);(root/'blobs').mkdir(mode=0o755);(root/'nfqws2.conf').write_bytes(b'CONFIG_CANARY\n')
  fixture="new AsusImportTransaction(new AsusImportStore(__DIR__.'/import-state',fileowner(__DIR__)),new AsusSmartDnsStore(__DIR__.'/dns-state',fileowner(__DIR__)),__DIR__.'/resources',__DIR__.'/resources/nfqws2.conf',fileowner(__DIR__))"
  for name in ['index.php','blob-api.php']:
   p=self.base/name
   if p.exists():p.write_text(p.read_text().replace('new AsusBlobStore()',"new AsusBlobStore(__DIR__.'/resources',fileowner(__DIR__),__DIR__.'/missing-catalog.json')").replace('new AsusImportTransaction()',fixture))
 def post(self,cmd='blobinventory',**extra):return {'cmd':cmd,'csrf_token':self.token,**extra}
 def upload(self,**extra):return self.post('blobupload',name='phone.bin',data_base64=base64.b64encode(BINARY).decode(),sha256=hashlib.sha256(BINARY).hexdigest())|extra
 def test_login_csrf_origin_and_closed_fields_precede_storage(self):
  self.assertEqual(self.request({'cmd':'blobinventory','csrf_token':'x'})[0],401);self.token=self.login()
  for p in [self.post(csrf_token='bad'),self.upload(csrf_token='bad')]:self.assertEqual(self.request(p)[0],403)
  self.origin='https://evil.invalid'
  for p in [self.post(),self.upload()]:self.assertEqual(self.request(p)[0],403)
  self.origin='http://localhost'
  for p in [self.post(root='/etc'),self.upload(path='/etc/evil'),self.upload(name=['bad']),self.upload(sha256='bad'),self.post(csrf_token=['x'])]:self.assertEqual(self.request(p)[0],400)
  self.assertFalse((self.base/'import-state').exists());self.assertEqual(list((self.base/'resources/blobs').iterdir()),[])
 def test_inventory_has_closed_response_and_does_not_take_mutation_locks(self):
  self.token=self.login();(self.base/'resources/blobs/arbitrary.bin').write_bytes(BINARY);(self.base/'update-busy').touch();code,v=self.request(self.post());self.assertEqual(code,200);self.assertEqual(set(v),{'files','skipped','scan_truncated'});self.assertEqual(set(v['files'][0]),FIELDS);self.assertFalse((self.base/'import-state').exists());self.assertFalse((self.base/'dns-state').exists())
 def test_upload_keeps_exact_data_and_never_saves_config_or_starts_service(self):
  self.token=self.login();code,v=self.request(self.upload());self.assertEqual(code,200);self.assertEqual(set(v),{'file'});self.assertEqual(set(v['file']),FIELDS);self.assertEqual((self.base/'resources/blobs/phone.bin').read_bytes(),BINARY);self.assertEqual((self.base/'resources/nfqws2.conf').read_bytes(),b'CONFIG_CANARY\n');self.assertFalse((self.base/'dns-state/draft.json').exists());self.assertFalse((self.base/'sent-share.json').exists());self.assertEqual(self.request(self.upload())[1],v)
 def test_update_lease_and_common_panel_writer_block_upload(self):
  self.token=self.login();(self.base/'update-busy').touch();self.assertEqual(self.request(self.upload()),(409,{'error':'busy'}));(self.base/'update-busy').unlink();root=self.base/'import-state';root.mkdir(mode=0o700,exist_ok=True);p=root/'writer.lock';p.touch(mode=0o600)
  with p.open('r+')as f:
   fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);self.assertEqual(self.request(self.upload()),(409,{'error':'busy'}))
  self.assertEqual(list((self.base/'resources/blobs').iterdir()),[]);self.assertEqual(self.request(self.upload())[0],200)
 def test_unrecoverable_import_blocks_upload_before_new_blob(self):
  self.token=self.login();root=self.base/'import-state';root.mkdir(mode=0o700);job={'id':'a'*32,'state':'restore_required','request_digest':'b'*64,'before':'c'*64,'after':'d'*64,'files':[]};p=root/'state.json';p.write_text(json.dumps({'schema_version':1,'current':job,'history':[]}));p.chmod(0o600)
  self.assertEqual(self.request(self.upload()),(409,{'error':'restore_required'}));self.assertEqual(list((self.base/'resources/blobs').iterdir()),[])
 def test_anonymous_panel_still_requires_its_own_csrf_session(self):
  self.token=self.login();self.change('',self.token);self.token=self.request({'cmd':'login'},'visitor')[1]['csrf_token'];self.assertEqual(self.request(self.upload(),'other')[0],403);self.assertEqual(self.request(self.upload(),'visitor')[0],200)
 def test_real_cgi_upload_with_binary_payload(self):
  cgi=os.environ.get('PHP_CGI_TEST_BINARY')
  if not cgi:self.skipTest('matching CGI runtime required')
  self.token=self.login();data=urllib.parse.urlencode(self.upload());env=os.environ|{'REDIRECT_STATUS':'200','SCRIPT_FILENAME':str(self.base/'index.php'),'REQUEST_METHOD':'POST','CONTENT_TYPE':'application/x-www-form-urlencoded','CONTENT_LENGTH':str(len(data.encode())),'HTTP_HOST':'localhost','HTTP_ORIGIN':'http://localhost','HTTP_COOKIE':'nfqws_asus_session='+self.sessions['user-one'],'QUERY_STRING':''};p=subprocess.run([cgi,'-n','-d','session.save_path='+str(self.base)],input=data,text=True,capture_output=True,env=env);self.assertEqual(p.returncode,0,p.stderr+p.stdout);head,body=p.stdout.split('\n\n',1);self.assertIn('Cache-Control: no-store',head);self.assertEqual(json.loads(body)['file']['byte_length'],len(BINARY));self.assertEqual((self.base/'resources/blobs/phone.bin').read_bytes(),BINARY)

 def test_pending_import_is_reconciled_before_accepting_the_new_blob(self):
  self.token=self.login();root=self.base/'import-state';root.mkdir(mode=0o700);before=hashlib.sha256(b'CONFIG_CANARY\n').hexdigest();job={'id':'a'*32,'state':'prepared','request_digest':'b'*64,'before':before,'after':'d'*64,'files':[],'dns_changed':False};p=root/'state.json';p.write_text(json.dumps({'schema_version':1,'current':job,'history':[]}));p.chmod(0o600)
  code,v=self.request(self.upload());self.assertEqual(code,200);self.assertEqual(v['file']['name'],'phone.bin');self.assertEqual(json.loads(p.read_text())['current']['state'],'rolled_back');self.assertEqual((self.base/'resources/nfqws2.conf').read_bytes(),b'CONFIG_CANARY\n')
