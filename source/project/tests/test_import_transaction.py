"""Real journal/CAS/crash recovery; no service execution is reachable."""
import hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_import_plan import documents,selection,CURRENT
from test_import_document import PHP,PUBLIC
from test_smartdns_profile import profile

class ImportTransactionTests(unittest.TestCase):
 def fixture(self,d):
  root=Path(d);resources=root/'resources';resources.mkdir(mode=0o755);resources.chmod(0o755);(resources/'nfqws2.conf').write_text(CURRENT)
  for k in ['lists','lua','blobs']:(resources/k).mkdir(mode=0o755);(resources/k).chmod(0o755)
  return root
 def call(self,root,ops,crash=None):
  code='''require $argv[1].'/import-transaction.php';$v=json_decode(stream_get_contents(STDIN),true);$r=$argv[2];$uid=(int)$argv[3];$store=new AsusImportStore($r.'/journal',$uid);$dns=new AsusSmartDnsStore($r.'/dns',$uid);$tx=new AsusImportTransaction($store,$dns,$r.'/resources',$r.'/resources/nfqws2.conf',$uid,['checkpoint'=>function($s)use($v){if(($v['crash']??null)===$s)exit(77);}]);$out=[];$p=null;foreach($v['ops']as $op){try{switch($op[0]){case 'prepare':$p=$tx->prepare($op[1],$op[2]);$x=$p;break;case 'apply':$x=$tx->apply($p,$op[1]);break;case 'draft':$x=$dns->draft();break;case 'setdraft':$x=$dns->saveDraft($op[1]);break;case 'status':$x=$tx->status();break;case 'recover':$x=$tx->recover();break;case 'undo':$x=$tx->undo($op[1]);break;default:throw new RuntimeException('bad_test');}$out[]=['value'=>$x];}catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}}echo json_encode($out,JSON_THROW_ON_ERROR);'''
  p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],input=json.dumps({'ops':ops,'crash':crash}),capture_output=True,text=True,timeout=12)
  if crash:self.assertEqual(p.returncode,77,p.stdout+p.stderr);return None
  self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
 def prep(self,sel=None):return ['prepare',documents(),selection()if sel is None else sel]
 def test_read_only_status_and_prepare_then_apply_undo_exact_bytes(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);out=self.call(r,[['status'],self.prep()]);self.assertFalse((r/'journal').exists());self.assertFalse((r/'dns').exists());self.assertTrue(out[1]['value']['ready'])
   out=self.call(r,[self.prep(),['apply','a'*32],['apply','a'*32],['status']]);self.assertEqual(out[1],out[2]);self.assertEqual(out[1]['value']['state'],'committed');self.assertNotEqual((r/'resources/nfqws2.conf').read_text(),CURRENT);self.assertEqual(len(list((r/'resources/blobs').iterdir())),1)
   for f in (r/'journal').iterdir():self.assertEqual(f.stat().st_mode&0o777,0o600)
   out=self.call(r,[['undo','a'*32],['undo','a'*32]]);self.assertEqual(out[0],out[1]);self.assertEqual(out[0]['value']['state'],'undone');self.assertEqual((r/'resources/nfqws2.conf').read_text(),CURRENT);self.assertEqual(list((r/'resources/blobs').iterdir()),[])
 def test_changed_config_file_or_dns_refuses_before_writing(self):
  for mode in ['config','target','draft']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as d:
    r=self.fixture(d);p=self.call(r,[self.prep()])[0]['value']
    # Prepare and mutate inside one PHP process so the proposal really is stale.
    code='''require $argv[1].'/import-transaction.php';$r=$argv[2];$u=(int)$argv[3];$v=json_decode(stream_get_contents(STDIN),true);$s=new AsusSmartDnsStore($r.'/dns',$u);$t=new AsusImportTransaction(new AsusImportStore($r.'/journal',$u),$s,$r.'/resources',$r.'/resources/nfqws2.conf',$u);$p=$t->prepare($v['docs'],$v['sel']);if($v['mode']==='config')file_put_contents($r.'/resources/nfqws2.conf','EDIT');elseif($v['mode']==='target')file_put_contents($r.'/resources/blobs/'.$p['files'][0]['target_name'],'OTHER');else $s->saveDraft($v['profile']);try{$t->apply($p,str_repeat('b',32));echo 'BAD';}catch(Throwable $e){echo $e->getMessage();}'''
    q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(r),str(os.getuid())],input=json.dumps({'docs':documents(),'sel':selection(),'mode':mode,'profile':profile()}),capture_output=True,text=True);self.assertEqual(q.returncode,0,q.stderr);self.assertEqual(q.stdout,'source_changed');self.assertFalse((r/'journal/state.json').exists())
 def test_death_each_boundary_reconciles_owned_changes(self):
  for phase in ['journal','file_0','file_1','draft','committing','config','committed']:
   with self.subTest(phase=phase),tempfile.TemporaryDirectory()as d:
    r=self.fixture(d);self.call(r,[self.prep(),['apply','a'*32]],crash=phase);out=self.call(r,[['recover']]);expected='committed'if phase in ['config','committed']else'rolled_back';self.assertEqual(out[0]['value']['state'],expected,out)
    if expected=='committed':self.call(r,[['undo','a'*32]])
    self.assertEqual((r/'resources/nfqws2.conf').read_text(),CURRENT);self.assertEqual(list((r/'resources/blobs').iterdir()),[])
 def test_undo_conflict_does_not_overwrite_user_edit(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);self.call(r,[self.prep(),['apply','a'*32]]);f=r/'resources/nfqws2.conf';f.write_text(f.read_text()+'# user edit\n');before=f.read_bytes();out=self.call(r,[['undo','a'*32]]);self.assertEqual(out,[{'error':'source_changed'}]);self.assertEqual(f.read_bytes(),before)
 def test_dns_is_draft_only_and_undo_restores_absence(self):
  from test_import_plan import ImportPlanTests
  docs,sel=ImportPlanTests().dns_input()
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);out=self.call(r,[['prepare',docs,sel],['apply','a'*32],['draft'],['undo','a'*32],['draft']]);self.assertEqual(out[1]['value']['state'],'committed');self.assertIsNotNone(out[2]['value']);self.assertIsNone(out[4]['value']);self.assertEqual((r/'resources/nfqws2.conf').read_text(),CURRENT)
 def test_history_bounded_and_changed_request_id_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);ops=[]
   for i in range(5):ops.extend([self.prep(selection(blocks=[],shared=[],files=[{'id':'1'*32}])),['apply',f'{i:032x}']])
   out=self.call(r,ops);self.assertEqual(out[-1]['value']['state'],'committed');state=json.loads((r/'journal/state.json').read_text());self.assertLessEqual(len(state['history']),3);self.assertLessEqual(sum(f.stat().st_size for f in(r/'journal').iterdir()),8388608)
   out=self.call(r,[self.prep(),['apply',f'{4:032x}']]);self.assertEqual(out[-1],{'error':'request_conflict'})
 def test_links_fifo_and_bad_owner_modes_rejected(self):
  for mode in ['symlink','hardlink','fifo','writable_parent']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as d:
    r=self.fixture(d);f=r/'resources/nfqws2.conf'
    if mode=='symlink':f.unlink();f.symlink_to(r/'outside')
    elif mode=='hardlink':os.link(f,r/'outside')
    elif mode=='fifo':f.unlink();os.mkfifo(f)
    else:(r/'resources').chmod(0o777)
    out=self.call(r,[self.prep()]);self.assertIn('error',out[0]);self.assertFalse((r/'journal').exists())
 def test_dns_cas_error_rolls_back_all_new_files(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);code='''require $argv[1].'/import-transaction.php';$r=$argv[2];$u=(int)$argv[3];$v=json_decode(stream_get_contents(STDIN),true);$t=new AsusImportTransaction(new AsusImportStore($r.'/journal',$u),new AsusSmartDnsStore($r.'/dns',$u),$r.'/resources',$r.'/resources/nfqws2.conf',$u,['checkpoint'=>function($s){if($s==='file_0')throw new RuntimeException('insufficient_space');}]);try{$t->apply($t->prepare($v[0],$v[1]),str_repeat('a',32));}catch(Throwable $e){echo $e->getMessage();}''';p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(r),str(os.getuid())],input=json.dumps([documents(),selection()]),capture_output=True,text=True);self.assertEqual(p.stdout,'insufficient_space');self.assertEqual((r/'resources/nfqws2.conf').read_text(),CURRENT);self.assertEqual(list((r/'resources/blobs').iterdir()),[])

 def test_stage_link_and_undo_death_are_recoverable(self):
  for phase in ['stage_0','linked_0','config_stage']:
   with self.subTest(phase=phase),tempfile.TemporaryDirectory()as d:
    r=self.fixture(d);self.call(r,[self.prep(),['apply','a'*32]],crash=phase);out=self.call(r,[['recover']]);self.assertEqual(out[0]['value']['state'],'rolled_back');self.assertEqual((r/'resources/nfqws2.conf').read_text(),CURRENT);self.assertFalse(list((r/'resources').glob('.import-*')));self.assertFalse(list((r/'resources/blobs').iterdir()))
  for phase in ['undoing','undo_config','undo_draft','undo_file_0']:
   with self.subTest(phase=phase),tempfile.TemporaryDirectory()as d:
    r=self.fixture(d);self.call(r,[self.prep(),['apply','a'*32]]);self.call(r,[['undo','a'*32]],crash=phase);out=self.call(r,[['recover']]);self.assertEqual(out[0]['value']['state'],'undone');self.assertEqual((r/'resources/nfqws2.conf').read_text(),CURRENT)
 def test_recovery_preserves_unrelated_edit_and_evidence(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);self.call(r,[self.prep(),['apply','a'*32]],crash='file_0');(r/'resources/nfqws2.conf').write_text('USER EDIT');out=self.call(r,[['recover']]);self.assertEqual(out,[{'error':'restore_required'}]);self.assertEqual((r/'resources/nfqws2.conf').read_text(),'USER EDIT');self.assertEqual(len(list((r/'resources/blobs').iterdir())),1);self.assertEqual(json.loads((r/'journal/state.json').read_text())['current']['state'],'restore_required')
 def test_two_alias_files_with_identical_target_are_written_once(self):
  docs=documents();v=json.loads(docs[1]);v['files'][1]={**v['files'][0],'id':'2'*32,'aliases':['RESOURCE_2']};v['files'][0]['aliases']=['RESOURCE_1'];v['audit']['references']=[];v['audit']['scope']='files_only';sel=selection(blocks=[],shared=[],trusted_lua=False)
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);out=self.call(r,[['prepare',[json.dumps(v)],sel],['apply','a'*32],['undo','a'*32]]);self.assertEqual(out[1]['value']['state'],'committed');self.assertEqual((r/'resources/nfqws2.conf').read_text(),CURRENT);self.assertFalse(list((r/'resources/blobs').iterdir()))

 def test_same_name_replacement_and_undo_preserve_bytes_and_mode(self):
  from test_import_plan import BLOB
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);f=r/'resources/blobs/hello.bin';f.write_bytes(b'ORIGINAL');f.chmod(0o640)
   out=self.call(r,[self.prep(),['apply','a'*32]]);self.assertEqual(out[-1]['value']['state'],'committed',out);self.assertEqual(f.read_bytes(),BLOB);self.assertEqual(f.stat().st_mode&0o777,0o640);self.assertEqual([x.name for x in f.parent.iterdir()],['hello.bin'])
   out=self.call(r,[['undo','a'*32]]);self.assertEqual(out[-1]['value']['state'],'undone',out);self.assertEqual(f.read_bytes(),b'ORIGINAL');self.assertEqual(f.stat().st_mode&0o777,0o640)
 def test_replacement_death_and_undo_death_restore_existing_file(self):
  for phase in ['journal','stage_0','linked_0','file_0','committing','config','committed']:
   with self.subTest(phase=phase),tempfile.TemporaryDirectory()as d:
    r=self.fixture(d);f=r/'resources/blobs/hello.bin';f.write_bytes(b'OLD');f.chmod(0o644)
    self.call(r,[self.prep(),['apply','a'*32]],crash=phase);out=self.call(r,[['recover']]);expected='committed'if phase in ['config','committed']else'rolled_back';self.assertEqual(out[-1]['value']['state'],expected,out)
    if expected=='committed':self.call(r,[['undo','a'*32]],crash='undo_file_0');self.call(r,[['recover']])
    self.assertEqual(f.read_bytes(),b'OLD');self.assertEqual(f.stat().st_mode&0o777,0o644)
 def test_replacement_undo_refuses_later_file_edit(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);f=r/'resources/blobs/hello.bin';f.write_bytes(b'OLD');self.call(r,[self.prep(),['apply','a'*32]]);f.write_bytes(b'USER EDIT')
   out=self.call(r,[['undo','a'*32]]);self.assertEqual(out,[{'error':'source_changed'}]);self.assertEqual(f.read_bytes(),b'USER EDIT')

 def test_preexisting_unsafe_resource_is_never_replaced(self):
  for mode in ['symlink','hardlink','fifo']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as d:
    r=self.fixture(d);outside=r/'outside';outside.write_bytes(b'KEEP');target=r/'resources/blobs/hello.bin'
    if mode=='symlink':target.symlink_to(outside)
    elif mode=='hardlink':os.link(outside,target)
    else:os.mkfifo(target)
    out=self.call(r,[self.prep(),['apply','a'*32]]);self.assertIn('error',out[-1]);self.assertEqual(outside.read_bytes(),b'KEEP');self.assertFalse((r/'journal/state.json').exists())
 def test_old_new_file_journal_can_still_undo_after_upgrade(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);self.call(r,[self.prep(),['apply','a'*32]]);path=r/'journal/state.json';v=json.loads(path.read_text())
   for f in v['current']['files']:f.pop('before',None);f.pop('metadata',None)
   path.write_text(json.dumps(v));out=self.call(r,[['undo','a'*32]]);self.assertEqual(out[-1]['value']['state'],'undone');self.assertFalse(list((r/'resources/blobs').iterdir()))

 def test_replacement_undo_preserves_later_permission_edit(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);f=r/'resources/blobs/hello.bin';f.write_bytes(b'OLD');f.chmod(0o666);self.call(r,[self.prep(),['apply','a'*32]]);f.chmod(0o600);before=f.read_bytes()
   out=self.call(r,[['undo','a'*32]]);self.assertEqual(out,[{'error':'source_changed'}]);self.assertEqual(f.read_bytes(),before);self.assertEqual(f.stat().st_mode&0o777,0o600)
