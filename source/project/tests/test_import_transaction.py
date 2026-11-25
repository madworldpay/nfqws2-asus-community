"""Real journal/CAS/crash recovery; no service execution is reachable."""
import base64,hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_import_plan import documents,selection,CURRENT,BLOB
from test_import_document import PHP,PUBLIC
from test_smartdns_profile import profile

class ImportTransactionTests(unittest.TestCase):
 def test_measured_activation_uses_ordinary_commit_and_undo(self):
  for fail in (False,True):
   with self.subTest(fail=fail),tempfile.TemporaryDirectory() as directory:
    root=self.fixture(directory)
    code="""require $argv[1].'/import-api.php';$r=$argv[2];$owner=(int)$argv[3];$fail=$argv[4]==='1';
    $dns=new AsusSmartDnsStore($r.'/dns',$owner);$file=$r.'/resources/nfqws2.conf';
    $tx=new AsusImportTransaction(new AsusImportStore($r.'/journal',$owner),$dns,$r.'/resources',$file,$owner);
    $api=new AsusImportApi($tx,fn()=>null,$dns);$original=file_get_contents($file);$events=[];
    try{$receipt=$api->applyMeasured(json_decode(stream_get_contents(STDIN),true),str_repeat('d',32),fn()=>null,
      function(bool $applying)use($file,$original,$fail,&$events){
        $events[]=[$applying,file_get_contents($file)===$original];
        if($fail&&$applying)throw new RuntimeException('service_start_failed');
      });$error=null;$where=null;}catch(Throwable $e){$error=$e->getMessage();$where=basename($e->getFile()).':'.$e->getLine();}
    echo json_encode(['events'=>$events,'error'=>$error,'where'=>$where,'status'=>$tx->status(),'original'=>file_get_contents($file)===$original]);"""
    run=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid()),str(int(fail))],
                       input=json.dumps(documents()),capture_output=True,text=True,timeout=12)
    self.assertEqual((run.returncode,run.stderr),(0,''),run.stdout+run.stderr)
    got=json.loads(run.stdout)
    self.assertEqual(got['events'],[[True,False],[False,True]] if fail else [[True,False]],got)
    self.assertEqual(got['error'],'service_start_failed' if fail else None)
    self.assertEqual(got['original'],fail)
    self.assertEqual(got['status']['state'],'undone' if fail else 'committed')

 def test_existing_imported_blob_beyond_inventory_limit_is_reused(self):
  with tempfile.TemporaryDirectory() as directory:
   root=self.fixture(directory)
   for i in range(128):
    (root/'resources/lists'/f'list-{i}.txt').write_text('example.org\n')
   target=root/'resources/blobs/imported'/(hashlib.sha256(BLOB).hexdigest()+'.bin')
   target.parent.mkdir(mode=0o755)
   target.write_bytes(BLOB)
   edited_lua=b'function imported() return 2 end\n'
   lua=root/'resources/lua/imported'/(hashlib.sha256(edited_lua).hexdigest()+'.lua')
   lua.parent.mkdir(mode=0o755)
   lua.write_bytes(edited_lua)
   originals={path:path.stat() for path in (target,lua)}
   picks=selection(files=[{'id':'1'*32},{'id':'2'*32,'text':edited_lua.decode()}])
   row=self.call(root,[self.prep(picks),['apply','a'*32],['undo','a'*32]])
   self.assertEqual({f['kind']:f['reuse'] for f in row[0]['value']['files']},{'blobs':True,'lua':True})
   self.assertEqual(row[1]['value']['state'],'committed')
   self.assertEqual(row[2]['value']['state'],'undone')
   for path,before in originals.items():
    self.assertEqual((path.stat().st_ino,path.stat().st_ctime_ns),(before.st_ino,before.st_ctime_ns))

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
 def list_prep(self):
  v=json.loads(documents()[1]);row=v['files'][0];raw=b'NEW\n';sha=hashlib.sha256(raw).hexdigest();row.update(kind='lists',name='replace.list',encoding='utf8',data_base64=base64.b64encode(raw).decode(),byte_length=len(raw),sha256=sha,source_sha256=sha,aliases=[]);v['files']=[row];v['audit'].update(scope='files_only',references=[])
  return ['prepare',[json.dumps(v)],selection(blocks=[],shared=[],files=[{'id':row['id']}],trusted_lua=False)]
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
    code='''require $argv[1].'/import-transaction.php';$r=$argv[2];$u=(int)$argv[3];$v=json_decode(stream_get_contents(STDIN),true);$s=new AsusSmartDnsStore($r.'/dns',$u);$t=new AsusImportTransaction(new AsusImportStore($r.'/journal',$u),$s,$r.'/resources',$r.'/resources/nfqws2.conf',$u);$p=$t->prepare($v['docs'],$v['sel']);if($v['mode']==='config')file_put_contents($r.'/resources/nfqws2.conf','EDIT');elseif($v['mode']==='target'){$path=$r.'/resources/blobs/'.$p['files'][0]['target_name'];mkdir(dirname($path),0755);file_put_contents($path,'OTHER');}else $s->saveDraft($v['profile']);try{$t->apply($p,str_repeat('b',32));echo 'BAD';}catch(Throwable $e){echo $e->getMessage();}'''
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

 def test_strategy_import_keeps_personal_auto_list(self):
  strategy=json.loads(documents()[0])
  block=strategy['blocks'][0]
  block['value']='--filter-tcp=443 --hostlist-auto=RESOURCE_1'
  strategy['shared']={}
  strategy['dependencies']=[{'id':'RESOURCE_1','kind':'file','included':True}]
  resource=json.loads(self.list_prep()[1][0])
  row=resource['files'][0];row.update(name='auto.list',aliases=['RESOURCE_1'])
  sel=selection(blocks=[{'key':block['key'],'value':block['value']}],shared=[],files=[{'id':row['id']}])
  prep=['prepare',[json.dumps(strategy),json.dumps(resource)],sel]
  def identity(path):
   st=path.stat()
   return (st.st_dev,st.st_ino,st.st_uid,st.st_gid,st.st_mode,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
  for existing in (True,False):
   with self.subTest(existing=existing),tempfile.TemporaryDirectory() as directory:
    root=self.fixture(directory);auto=root/'resources/lists/auto.list'
    if existing:
     auto.write_bytes(b'learned.example\n');before=identity(auto)
    prepared,saved=self.call(root,[prep,['apply','9'*32]])
    self.assertTrue(prepared['value']['ready'],prepared['value']['problems'])
    self.assertEqual(saved['value']['state'],'committed')
    self.assertEqual(auto.read_bytes(),b'learned.example\n' if existing else b'')
    if existing:
     self.assertEqual(identity(auto),before)
     self.assertTrue(prepared['value']['kept_auto_list'])
     self.assertNotIn('auto.list',[f['name'] for f in prepared['value']['files']])
    self.assertIn('--hostlist-auto=/opt/etc/nfqws2/lists/auto.list',(root/'resources/nfqws2.conf').read_text())
    self.assertEqual(self.call(root,[['undo','9'*32]])[0]['value']['state'],'undone')
    if existing:self.assertEqual(identity(auto),before)
    else:self.assertFalse(auto.exists())
    self.assertFalse(auto.with_suffix('.list.new').exists())

 def test_same_name_replacement_and_undo_preserve_bytes_and_mode(self):
  from test_import_plan import BLOB
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);f=r/'resources/lists/replace.list';f.write_bytes(b'ORIGINAL');f.chmod(0o640)
   out=self.call(r,[self.list_prep(),['apply','a'*32]]);self.assertEqual(out[-1]['value']['state'],'committed',out);self.assertEqual(f.read_bytes(),b'NEW\n');self.assertEqual(f.stat().st_mode&0o777,0o640);self.assertEqual([x.name for x in f.parent.iterdir()],['replace.list'])
   out=self.call(r,[['undo','a'*32]]);self.assertEqual(out[-1]['value']['state'],'undone',out);self.assertEqual(f.read_bytes(),b'ORIGINAL');self.assertEqual(f.stat().st_mode&0o777,0o640)
 def test_replacement_death_and_undo_death_restore_existing_file(self):
  for phase in ['journal','stage_0','linked_0','file_0','committing','config','committed']:
   with self.subTest(phase=phase),tempfile.TemporaryDirectory()as d:
    r=self.fixture(d);f=r/'resources/lists/replace.list';f.write_bytes(b'OLD');f.chmod(0o644)
    self.call(r,[self.list_prep(),['apply','a'*32]],crash=phase);out=self.call(r,[['recover']]);expected='committed'if phase in ['committing','config','committed']else'rolled_back';self.assertEqual(out[-1]['value']['state'],expected,out)
    if expected=='committed':self.call(r,[['undo','a'*32]],crash='undo_file_0');self.call(r,[['recover']])
    self.assertEqual(f.read_bytes(),b'OLD');self.assertEqual(f.stat().st_mode&0o777,0o644)
 def test_replacement_undo_refuses_later_file_edit(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);f=r/'resources/lists/replace.list';f.write_bytes(b'OLD');self.call(r,[self.list_prep(),['apply','a'*32]]);f.write_bytes(b'USER EDIT')
   out=self.call(r,[['undo','a'*32]]);self.assertEqual(out,[{'error':'source_changed'}]);self.assertEqual(f.read_bytes(),b'USER EDIT')

 def test_preexisting_unsafe_resource_is_never_replaced(self):
  for mode in ['symlink','hardlink','fifo']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as d:
    r=self.fixture(d);outside=r/'outside';outside.write_bytes(b'KEEP');target=r/'resources/blobs/imported'/ (hashlib.sha256(__import__('test_import_plan').BLOB).hexdigest()+'.bin');target.parent.mkdir()
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
   r=self.fixture(d);f=r/'resources/lists/replace.list';f.write_bytes(b'OLD');f.chmod(0o666);self.call(r,[self.list_prep(),['apply','a'*32]]);f.chmod(0o600);before=f.read_bytes()
   out=self.call(r,[['undo','a'*32]]);self.assertEqual(out,[{'error':'source_changed'}]);self.assertEqual(f.read_bytes(),before);self.assertEqual(f.stat().st_mode&0o777,0o600)
