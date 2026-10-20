"""Authenticated real route, proof/CAS/replay and common writer admission."""
import json,os,subprocess,unittest,urllib.parse
from test_share_router_http import ShareRouterTests
from test_import_plan import documents,selection,CURRENT
from test_dpi_normalize import PHP,PUBLIC

class ImportHttpTests(unittest.TestCase):
 login=ShareRouterTests.login
 request=ShareRouterTests.request
 change=ShareRouterTests.change
 def setUp(self):
  ShareRouterTests.setUp(self)
  root=self.base/'resources';root.chmod(0o755)
  for k in ['lists','lua','blobs']:(root/k).mkdir(mode=0o755);(root/k).chmod(0o755)
  (root/'nfqws2.conf').write_text(CURRENT)
  fixture="new AsusImportTransaction(new AsusImportStore(__DIR__.'/import-state',fileowner(__DIR__)),new AsusSmartDnsStore(__DIR__.'/dns-state',fileowner(__DIR__)),__DIR__.'/resources',__DIR__.'/resources/nfqws2.conf',fileowner(__DIR__))"
  for name in ['index.php','import-api.php']:
   p=self.base/name
   if p.exists():p.write_text(p.read_text().replace('new AsusImportTransaction()',fixture))
 def post(self,cmd,**extra):return {'cmd':cmd,'csrf_token':self.token,**extra}
 def prepare(self):return self.request(self.post('importprepare',documents=json.dumps(documents()),selection=json.dumps(selection())))
 def apply(self,p,id='a'*32):return self.request(self.post('importapply',documents=json.dumps(documents()),selection=json.dumps(selection()),proof=p,request_id=id))
 def test_auth_csrf_origin_and_exact_fields_before_any_write(self):
  self.assertEqual(self.request({'cmd':'importinspect','csrf_token':'x','documents':json.dumps(documents())})[0],401);self.token=self.login()
  p=self.post('importinspect',documents=json.dumps(documents()))
  self.assertEqual(self.request(p|{'csrf_token':'bad'})[0],403);self.origin='https://evil.invalid';self.assertEqual(self.request(p)[0],403);self.origin='http://localhost';self.assertEqual(self.request(p|{'root':'/etc'})[0],400)
  code,v=self.request(p);self.assertEqual(code,200);self.assertIn('NFQWS_ARGS',v['values']);self.assertFalse((self.base/'import-state').exists())
 def test_review_proof_tamper_then_apply_status_undo(self):
  self.token=self.login();code,p=self.prepare();self.assertEqual(code,200);self.assertTrue(p['ready']);self.assertTrue(p['proof'].startswith('im1.'));self.assertFalse((self.base/'import-state').exists())
  self.assertEqual(self.apply(p['proof']+'a')[0],403);self.assertEqual((self.base/'resources/nfqws2.conf').read_text(),CURRENT)
  code,v=self.apply(p['proof']);self.assertEqual((code,v['state']),(200,'committed'));self.assertEqual(self.apply(p['proof'])[1],v)
  code,s=self.request(self.post('importstatus'));self.assertEqual(code,200);self.assertTrue(s['can_undo']);self.assertTrue(s['undo_proof'].startswith('im1.'))
  code,v=self.request(self.post('importundo',id=s['id'],proof=s['undo_proof']));self.assertEqual((code,v['state']),(200,'undone'));self.assertEqual((self.base/'resources/nfqws2.conf').read_text(),CURRENT)
 def test_stale_proposal_and_updater_busy_never_write(self):
  self.token=self.login();_,p=self.prepare();f=self.base/'resources/nfqws2.conf';f.write_text(CURRENT+'# edit\n');self.assertEqual(self.apply(p['proof'])[0],409);self.assertEqual(f.read_text(),CURRENT+'# edit\n')
  _,p=self.prepare();(self.base/'update-busy').touch();self.assertEqual(self.apply(p['proof'])[0],409);self.assertFalse((self.base/'import-state/state.json').exists())
 def test_expired_proof_and_cross_session_denied(self):
  self.token=self.login();_,p=self.prepare();self.login('user-two');code,_=self.request(self.post('importapply',documents=json.dumps(documents()),selection=json.dumps(selection()),proof=p['proof'],request_id='a'*32),'user-two');self.assertEqual(code,403)
  script="require $argv[1].'/import-api.php';echo AsusImportProof::issue('apply',str_repeat('a',64),str_repeat('b',64),str_repeat('c',64),100);";q=subprocess.run([PHP,'-n','-r',script,str(PUBLIC)],capture_output=True,text=True);self.assertEqual(q.returncode,0,q.stdout+q.stderr)
  script="require $argv[1].'/import-api.php';echo AsusImportProof::verify($argv[2],'apply',str_repeat('b',64),str_repeat('c',64),701)===null?'expired':'BAD';";q=subprocess.run([PHP,'-n','-r',script,str(PUBLIC),q.stdout],capture_output=True,text=True);self.assertEqual(q.stdout,'expired')
 def test_common_writer_blocks_other_tab(self):
  self.token=self.login();_,p=self.prepare();root=self.base/'import-state';root.mkdir(mode=0o700);path=root/'writer.lock';path.touch(mode=0o600)
  import fcntl
  with path.open('r+')as f:
   fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);self.assertEqual(self.apply(p['proof'])[0],409)
  self.assertEqual(self.apply(p['proof'])[0],200)
 def test_real_cgi_upload_and_prepare(self):
  cgi=os.environ.get('PHP_CGI_TEST_BINARY')
  if not cgi:self.skipTest('matching CGI required')
  self.token=self.login();data=urllib.parse.urlencode(self.post('importprepare',documents=json.dumps(documents()),selection=json.dumps(selection())))
  env=os.environ|{'REDIRECT_STATUS':'200','SCRIPT_FILENAME':str(self.base/'index.php'),'REQUEST_METHOD':'POST','CONTENT_TYPE':'application/x-www-form-urlencoded','CONTENT_LENGTH':str(len(data.encode())),'HTTP_HOST':'localhost','HTTP_ORIGIN':'http://localhost','HTTP_COOKIE':'nfqws_asus_session='+self.sessions['user-one'],'QUERY_STRING':''}
  p=subprocess.run([cgi,'-n','-d','session.save_path='+str(self.base)],input=data,text=True,capture_output=True,env=env);self.assertEqual(p.returncode,0,p.stderr+p.stdout);head,body=p.stdout.split('\n\n',1);self.assertIn('Cache-Control: no-store',head);self.assertTrue(json.loads(body)['ready'])
 def test_existing_file_mutation_respects_import_writer_and_returns_closed_error(self):
  self.token=self.login();root=self.base/'import-state';root.mkdir(mode=0o700);path=root/'writer.lock';path.touch(mode=0o600)
  import fcntl
  with path.open('r+')as f:
   fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
   code,v=self.request(self.post('filesave',filename='nfqws2.conf',content='SHOULD_NOT_WRITE'))
   self.assertEqual((code,v),(409,{'error':'busy'}))
  self.assertEqual((self.base/'resources/nfqws2.conf').read_text(),CURRENT)
