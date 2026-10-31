"""Blob inventory and uploads use fixed resource storage and preserve exact data."""
import base64,hashlib,json,os,subprocess,tempfile,threading,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC

BINARY=b'\x00\xff\x80BLOB\r\n\x00'
FIELDS={'name','path','byte_length','sha256','state','format','label','bundled'}

class BlobStoreTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)/'nfqws2';self.root.mkdir(mode=0o755);(self.root/'blobs').mkdir(mode=0o755)
  (self.root/'nfqws2.conf').write_bytes(b'CONFIG_CANARY\n');self.catalog=Path(self.temp.name)/'catalog.json'
  self.catalog.write_text(json.dumps({'schema_version':1,'files':[]}));self.catalog.chmod(0o644)
 def call(self,action='inventory',payload=None,prelude=''):
  code='''$file=$argv[1].'/blob-store.php';if(!is_file($file)){echo json_encode(['error'=>'missing_feature']);exit;}require $file;
  try{$s=new AsusBlobStore($argv[2],(int)$argv[3],$argv[4]);$v=json_decode(stream_get_contents(STDIN),true);'''+prelude+'''
  echo json_encode($argv[5]==='upload'?$s->upload($v['name'],$v['data_base64'],$v['sha256']):$s->inventory(),JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
  p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid()),str(self.catalog),action],input=json.dumps(payload),capture_output=True,text=True,timeout=10)
  self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
 def upload(self,name='phone.bin',raw=BINARY,**changes):
  return self.call('upload',{'name':name,'data_base64':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest()}|changes)
 def test_binary_upload_preserves_bytes_and_inventory_is_read_only(self):
  row=self.upload();self.assertNotIn('error',row);self.assertEqual(set(row),FIELDS);self.assertEqual(row['name'],'phone.bin');self.assertEqual(row['path'],'/opt/etc/nfqws2/blobs/phone.bin');self.assertEqual(row['state'],'available');self.assertEqual(row['format'],'other');self.assertIsNone(row['label']);self.assertFalse(row['bundled'])
  path=self.root/'blobs/phone.bin';self.assertEqual(path.read_bytes(),BINARY);self.assertEqual(path.stat().st_nlink,1);self.assertEqual(path.stat().st_uid,os.getuid());self.assertEqual(path.stat().st_mode&0o777,0o644)
  before={p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()};v=self.call();self.assertEqual(v,{'files':[row],'skipped':0,'scan_truncated':False});self.assertNotIn(str(self.root),json.dumps(v));self.assertEqual(before,{p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
 def test_conflicting_name_keeps_original_and_identical_replay_reuses_file(self):
  (self.root/'blobs/phone.bin').write_bytes(b'original');v=self.upload();self.assertNotIn('error',v);self.assertEqual(v['name'],'phone-'+hashlib.sha256(BINARY).hexdigest()[:12]+'.bin');self.assertEqual((self.root/'blobs/phone.bin').read_bytes(),b'original');self.assertEqual(self.upload(),v);self.assertEqual(len(list((self.root/'blobs').iterdir())),2)
 def test_identical_requested_name_keeps_its_inode_and_metadata(self):
  path=self.root/'blobs/phone.bin';path.write_bytes(BINARY);path.chmod(0o600);before=path.stat();v=self.upload();self.assertNotIn('error',v);self.assertEqual(v['name'],'phone.bin');self.assertEqual(path.stat().st_ino,before.st_ino);self.assertEqual(path.stat().st_mode,before.st_mode)
 def test_invalid_bytes_hash_and_names_never_write_resources(self):
  cases=[('phone.bin',b'',{},'invalid_blob'),('phone.bin',b'x'*262145,{},'file_too_large'),('phone.bin',BINARY,{'sha256':'a'*64},'hash_mismatch'),('phone.bin',BINARY,{'data_base64':base64.b64encode(BINARY).decode()+'\n'},'invalid_blob'),('phone.bin',BINARY,{'data_base64':'AA=='},'hash_mismatch')]
  for name in ['../escape.bin','/tmp/escape.bin','a\\b.bin','hello.php','a\0.bin','a\n.bin','.hidden.bin','a'*129+'.bin']:
   cases.append((name,BINARY,{},'invalid_blob'))
  for name,raw,changes,error in cases:
   with self.subTest(name=name,error=error):self.assertEqual(self.upload(name,raw,**changes),{'error':error})
  self.assertEqual(list((self.root/'blobs').iterdir()),[]);self.assertEqual((self.root/'nfqws2.conf').read_bytes(),b'CONFIG_CANARY\n')
 def test_maximum_sized_binary_is_accepted(self):
  raw=bytes(range(256))*1024;v=self.upload(raw=raw);self.assertNotIn('error',v);self.assertEqual(v['byte_length'],262144);self.assertEqual((self.root/'blobs/phone.bin').read_bytes(),raw)
 def test_symlinks_hardlinks_fifos_and_unsafe_parents_are_refused(self):
  outside=Path(self.temp.name)/'private';outside.write_bytes(b'PRIVATE_CANARY')
  for kind in ['symlink','hardlink','fifo']:
   p=self.root/'blobs/phone.bin'
   if kind=='symlink':p.symlink_to(outside)
   elif kind=='hardlink':os.link(outside,p)
   else:os.mkfifo(p)
   with self.subTest(kind=kind):self.assertEqual(self.upload(),{'error':'source_changed'});v=self.call();self.assertEqual(v['files'],[]);self.assertEqual(v['skipped'],1)
   p.unlink()
  (self.root/'blobs').chmod(0o777);self.assertEqual(self.upload(),{'error':'resource_unavailable'});self.assertEqual(outside.read_bytes(),b'PRIVATE_CANARY')
 def test_symlink_resource_directory_cannot_be_created_through(self):
  outside=Path(self.temp.name)/'outside';outside.mkdir();(self.root/'blobs').rmdir();(self.root/'blobs').symlink_to(outside,target_is_directory=True)
  self.assertEqual(self.upload(),{'error':'resource_unavailable'});self.assertEqual(list(outside.iterdir()),[])
 def test_missing_blob_directory_is_created_without_changing_ancestor_modes(self):
  (self.root/'blobs').rmdir();mode=self.root.stat().st_mode;self.assertEqual(self.call(),{'files':[],'skipped':0,'scan_truncated':False});self.assertFalse((self.root/'blobs').exists());self.assertNotIn('error',self.upload());self.assertEqual(self.root.stat().st_mode,mode)
 def test_inventory_unknown_names_large_files_and_scan_limits_are_explicit(self):
  (self.root/'blobs/arbitrary.bin').write_bytes(BINARY);(self.root/'blobs/too-big.bin').write_bytes(b'x'*262145)
  rows=self.call()['files'];self.assertEqual(len(rows),2);large=next(x for x in rows if x['name']=='too-big.bin');self.assertEqual(large['state'],'too_large');self.assertIsNone(large['sha256']);self.assertEqual(large['format'],'other')
  for i in range(140):(self.root/f'blobs/item-{i:03}.bin').write_bytes(b'x')
  v=self.call();self.assertEqual(len(v['files']),128);self.assertTrue(v['scan_truncated'])
 def test_empty_leftover_file_is_unavailable_without_breaking_other_choices(self):
  (self.root/'blobs/empty.bin').write_bytes(b'');self.upload()
  v=self.call();self.assertNotIn('error',v);self.assertEqual(len(v['files']),2)
  row=next(x for x in v['files'] if x['name']=='empty.bin');self.assertEqual(row['state'],'unavailable');self.assertIsNone(row['sha256']);self.assertEqual(row['byte_length'],0)
  self.assertEqual(next(x for x in v['files'] if x['name']=='phone.bin')['state'],'available')
 def test_inventory_total_read_budget_is_bounded(self):
  for i in range(12):(self.root/f'blobs/item-{i:03}.bin').write_bytes(bytes([i])*262144)
  v=self.call();self.assertNotIn('error',v);self.assertTrue(v['scan_truncated']);self.assertTrue(any(x['state']=='unavailable' and x['sha256'] is None for x in v['files']))
 def test_inventory_racing_file_has_a_consistent_size_hash_and_read_budget(self):
  path=self.root/'blobs/changing.bin';small=b'A';large=b'B'*262144;path.write_bytes(small)
  stopped=threading.Event()
  def mutate():
   while not stopped.is_set():
    path.write_bytes(large);path.write_bytes(small)
  worker=threading.Thread(target=mutate);worker.start()
  code="require $argv[1].'/blob-store.php';$s=new AsusBlobStore($argv[2],(int)$argv[3],$argv[4]);$out=[];for($i=0;$i<1500;$i++)$out[]=$s->inventory();echo json_encode($out,JSON_THROW_ON_ERROR);"
  try:
   r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid()),str(self.catalog)],text=True,capture_output=True,timeout=20)
  finally:stopped.set();worker.join()
  self.assertEqual(r.returncode,0,r.stderr)
  valid={(len(raw),hashlib.sha256(raw).hexdigest())for raw in [small,large]}
  for inventory in json.loads(r.stdout):
   for row in inventory['files']:
    if row['state']=='available':self.assertIn((row['byte_length'],row['sha256']),valid)
 def test_catalog_labels_require_exact_trusted_hash_and_size(self):
  (self.root/'blobs/phone.bin').write_bytes(BINARY);catalog={'name':'official.bin','sha256':hashlib.sha256(BINARY).hexdigest(),'byte_length':len(BINARY),'format':'tls','label':{'ru':'Пример TLS','en':'TLS example'}};self.catalog.write_text(json.dumps({'schema_version':1,'files':[catalog]}))
  row=self.call()['files'][0];self.assertEqual(row['format'],'tls');self.assertEqual(row['label'],catalog['label']);self.assertTrue(row['bundled'])
  (self.root/'blobs/phone.bin').write_bytes(b'edited');row=self.call()['files'][0];self.assertEqual(row['format'],'other');self.assertIsNone(row['label']);self.assertFalse(row['bundled'])
  self.catalog.chmod(0o666);(self.root/'blobs/phone.bin').write_bytes(BINARY);row=self.call()['files'][0];self.assertEqual(row['format'],'other');self.assertFalse(row['bundled'])
 def test_catalog_is_optional_and_rejects_unknown_or_malformed_metadata(self):
  (self.root/'blobs/phone.bin').write_bytes(BINARY)
  for content in [None,'{broken',json.dumps({'schema_version':1,'files':[{'name':'x.bin','sha256':hashlib.sha256(BINARY).hexdigest(),'byte_length':len(BINARY),'format':'evil','label':{'ru':'x','en':'x'}}]})]:
   if content is None:self.catalog.unlink(missing_ok=True)
   else:self.catalog.write_text(content)
   self.assertEqual(self.call()['files'][0]['format'],'other')

 def test_browser_unicode_and_spaces_are_canonicalized_to_safe_ascii_names(self):
  for original,want in [('my client hello.bin','my-client-hello.bin'),('телефон.bin','blob.bin'),('A_hello.BIN','A_hello.BIN')]:
   with self.subTest(original=original):
    v=self.upload(original);self.assertNotIn('error',v);self.assertEqual(v['name'],want);self.assertEqual((self.root/'blobs'/want).read_bytes(),BINARY)
 def test_crash_stages_are_reclaimed_without_touching_the_existing_blob(self):
  p=self.root/'blobs/phone.bin';p.write_bytes(BINARY);p.chmod(0o644);before=p.stat();stage=self.root/('blobs/.blob-upload-phone.bin.'+'a'*32);os.link(p,stage)
  orphan=self.root/('blobs/.blob-upload-old.bin.'+'b'*32);orphan.write_bytes(b'incomplete');orphan.chmod(0o600)
  v=self.upload();self.assertNotIn('error',v);self.assertEqual(v['name'],'phone.bin');self.assertEqual(p.stat().st_nlink,1);self.assertEqual(p.stat().st_ino,before.st_ino);self.assertFalse(stage.exists());self.assertFalse(orphan.exists())
 def test_long_conflicting_names_are_still_safe_and_replayable(self):
  name='a'*124+'.bin';p=self.root/'blobs'/name;p.write_bytes(b'original');v=self.upload(name);self.assertNotIn('error',v);self.assertEqual(len(v['name']),128);self.assertEqual((self.root/'blobs'/v['name']).read_bytes(),BINARY);self.assertEqual(self.upload(name),v);self.assertEqual(p.read_bytes(),b'original')
 def test_replaced_pinned_entware_boundary_is_rejected(self):
  alias=Path(self.temp.name)/'opt';alias.symlink_to(self.root,target_is_directory=True)
  prelude="""$reader=new AsusShareRead((int)$argv[3],$argv[2],dirname($argv[2]).'/opt');$s=new AsusBlobStore($argv[2],(int)$argv[3],$argv[4],$reader);rename($argv[2],$argv[2].'-old');mkdir($argv[2],0755);mkdir($argv[2].'/blobs',0755);"""
  self.assertEqual(self.call('upload',{'name':'phone.bin','data_base64':base64.b64encode(BINARY).decode(),'sha256':hashlib.sha256(BINARY).hexdigest()},prelude),{'error':'resource_unavailable'});self.assertEqual(list((self.root/'blobs').iterdir()),[])
