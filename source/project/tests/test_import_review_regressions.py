"""Final whole-change review findings, each reproduced before the fix pass."""
import base64,copy,hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
import test_import_plan as f
import test_import_transaction as txf
from test_import_document import PHP,PUBLIC

class ImportReviewTests(unittest.TestCase):
 def plan(self,*args,**kw):return f.ImportPlanTests().call(*args,**kw)
 def test_unavailable_local_reference_never_gets_ready_or_unbound_cas(self):
  for state in ['too_large','unavailable']:
   with self.subTest(state=state):
    s=f.selection(blocks=[{'key':'NFQWS_ARGS','value':'--hostlist=/opt/etc/nfqws2/lists/big.list'}],shared=[],files=[])
    docs=f.documents();v=json.loads(docs[0]);v['shared']={};docs[0]=json.dumps(v)
    p=self.plan(s,docs=docs,inventory={'files':[{'id':'a'*32,'kind':'lists','name':'big.list','state':state,'sha256':None,'byte_length':300000}],'scan_truncated':False});self.assertFalse(p['ready']);self.assertIn('unresolved_file',[r['code']for r in p['problems']])
 def test_editing_shared_removes_original_identity_and_file_requirements(self):
  docs=f.documents();v=json.loads(docs[0]);v['shared']['NFQWS_BASE_ARGS']='--ipset-ip=NETWORK_9';docs[0]=json.dumps(v)
  s=f.selection(blocks=[{'key':'NFQWS_ARGS','value':'--filter-tcp=443'}],shared=[{'key':'NFQWS_BASE_ARGS','value':'--ipset-ip=192.0.2.2'}],files=[])
  p=self.plan(s,docs=docs);self.assertTrue(p['ready'],p['problems'])
  p=self.plan(f.selection(blocks=[{'key':'NFQWS_ARGS','value':'--filter-tcp=443'}],shared=[{'key':'NFQWS_BASE_ARGS','value':''}],files=[]));self.assertTrue(p['ready'],p['problems']);self.assertEqual(p['required']['files'],[])
 def test_global_replacement_audits_retained_blob_use(self):
  current=f.CURRENT.replace('NFQWS_BASE_ARGS=""','NFQWS_BASE_ARGS="--blob=original:0x1234"').replace('--filter-udp=443','--filter-udp=443 --lua-desync=fake:blob=original')
  docs=f.documents();v=json.loads(docs[0]);v['shared']['NFQWS_BASE_ARGS']='--blob=new:0x5678';docs[0]=json.dumps(v)
  p=self.plan(f.selection(blocks=[{'key':'NFQWS_ARGS','value':'--filter-tcp=443'}],shared=[{'key':'NFQWS_BASE_ARGS','value':'--blob=new:0x5678'}],files=[]),docs=docs,current=current);self.assertFalse(p['ready']);self.assertIn('unresolved_blob',[r['code']for r in p['problems']])
 def test_lua_completeness_needs_separate_acknowledgment(self):
  p=self.plan(f.selection(files=[{'id':'1'*32},{'id':'2'*32,'text':'dofile("/opt/etc/nfqws2/lua/missing-helper.lua")'}],allow_incomplete=False));self.assertFalse(p['ready']);self.assertIn('lua_dependencies_unchecked',[w['kind']for w in p['warnings']]);self.assertIn('incomplete_analysis',[r['code']for r in p['problems']])
 def test_undo_does_not_delete_file_changed_after_initial_check(self):
  helper=txf.ImportTransactionTests()
  with tempfile.TemporaryDirectory()as d:
   root=helper.fixture(d);helper.call(root,[helper.prep(),['apply','a'*32]])
   code='''require $argv[1].'/import-transaction.php';$r=$argv[2];$u=(int)$argv[3];$t=new AsusImportTransaction(new AsusImportStore($r.'/journal',$u),new AsusSmartDnsStore($r.'/dns',$u),$r.'/resources',$r.'/resources/nfqws2.conf',$u,['checkpoint'=>function($phase)use($r){if($phase==='undo_config')foreach(glob($r.'/resources/blobs/*')as $f)file_put_contents($f,'USER CHANGE');}]);try{echo json_encode($t->undo(str_repeat('a',32)));}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
   q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],capture_output=True,text=True);self.assertEqual(q.returncode,0,q.stderr);out=json.loads(q.stdout);self.assertIn(out.get('error'),['restore_required','source_changed']);self.assertEqual([v.read_text()for v in(root/'resources/blobs').iterdir()],['USER CHANGE'])
 def test_imported_auto_hostlist_retains_service_write_access(self):
  docs=f.documents();v=json.loads(docs[0]);v['blocks'][0]['value']='--hostlist-auto=RESOURCE_1';v['shared']={};docs[0]=json.dumps(v);r=json.loads(docs[1]);r['files'][0]['kind']='lists';r['files'][0]['name']='learn.list';r['files'][0]['encoding']='utf8';r['files'][0]['data_base64']='';r['files'][0]['sha256']=r['files'][0]['source_sha256']=hashlib.sha256(b'').hexdigest();r['files'][0]['byte_length']=0;docs[1]=json.dumps(r)
  sel=f.selection(blocks=[{'key':'NFQWS_ARGS','value':'--hostlist-auto=RESOURCE_1'}],shared=[],files=[{'id':'1'*32}],trusted_lua=False)
  helper=txf.ImportTransactionTests()
  with tempfile.TemporaryDirectory()as d:
   root=helper.fixture(d);out=helper.call(root,[['prepare',docs,sel],['apply','a'*32]]);self.assertEqual(out[-1]['value']['state'],'committed');file=next((root/'resources/lists').iterdir());self.assertTrue(file.stat().st_mode&0o002,'preserved service USER needs auto-list write access');helper.call(root,[['undo','a'*32]])

 def test_unavailable_reference_cannot_borrow_selected_file_id(self):
  docs=f.documents();v=json.loads(docs[0]);v['shared']={};docs[0]=json.dumps(v)
  p=self.plan(f.selection(blocks=[{'key':'NFQWS_ARGS','value':'--hostlist=/opt/etc/nfqws2/lists/big.list'}],shared=[],files=[{'id':'1'*32}]),docs=docs,inventory={'files':[{'id':'1'*32,'kind':'lists','name':'big.list','state':'too_large','sha256':None,'byte_length':300000}],'scan_truncated':False});self.assertFalse(p['ready'])
