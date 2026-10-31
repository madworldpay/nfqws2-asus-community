"""Exercise real update lease integration and platform-selected logical paths."""
import base64,fcntl,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
import test_blob_store as blob_tests
from test_dpi_normalize import PHP,PUBLIC

class BlobApiTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.root=self.base/'resources';self.root.mkdir(mode=0o755);(self.root/'blobs').mkdir(mode=0o755)
 def call(self,body,payload=None,public=PUBLIC):
  script="require $argv[1].'/blob-api.php';$owner=(int)$argv[3];$base=$argv[2];try{$post=json_decode(stream_get_contents(STDIN),true);"+body+"}catch(Throwable $e){echo json_encode(['error'=>AsusBlobApi::error($e)]);}"
  p=subprocess.run([PHP,'-n','-r',script,str(public),str(self.base),str(os.getuid())],input=json.dumps(payload),text=True,capture_output=True,timeout=15);self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
 def test_real_update_exclusive_apply_lease_blocks_upload_and_then_releases(self):
  updates=self.base/'updates';updates.mkdir(mode=0o700);(updates/'operations').mkdir(mode=0o700);lock=updates/'apply.lock';lock.touch(mode=0o600)
  body="""$store=new AsusBlobStore($base.'/resources',$owner,$base.'/missing.json');$tx=new AsusImportTransaction(new AsusImportStore($base.'/import',$owner),new AsusSmartDnsStore($base.'/dns',$owner),$base.'/resources',$base.'/resources/nfqws2.conf',$owner);$api=new AsusBlobApi($store,$tx,fn()=>(new AsusUpdateGuard(new AsusUpdateStore($base.'/updates',$owner),$owner))->mutationLease());echo json_encode($api->handle($post));"""
  payload={'cmd':'blobupload','csrf_token':'x','name':'phone.bin','data_base64':base64.b64encode(blob_tests.BINARY).decode(),'sha256':'a1766f7ba1326ee4ba2b545edcbe5e05971dabdea11eabb4c26b56fb7c55116f'}
  with lock.open('r+')as f:
   fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);self.assertEqual(self.call(body,payload),{'error':'busy'})
  self.assertFalse((self.base/'import').exists());self.assertEqual(list((self.root/'blobs').iterdir()),[]);v=self.call(body,payload);self.assertNotIn('error',v);self.assertEqual((self.root/'blobs/phone.bin').read_bytes(),blob_tests.BINARY)
 def test_closed_request_types_and_error_codes_do_not_expose_exceptions(self):
  for post in [{'cmd':'blobupload','csrf_token':'x','name':'a.bin','data_base64':[],'sha256':'a'*64},{'cmd':'blobinventory','csrf_token':'x','root':'/private'},{'cmd':'blobinventory','csrf_token':[]}]:
   self.assertEqual(self.call('AsusBlobApi::validate($post);echo json_encode(["accepted"=>true]);',post),{'error':'invalid_request'})
  self.assertEqual(self.call("throw new RuntimeException('/PRIVATE_CANARY');"),{'error':'storage_unavailable'})
 def test_native_platform_returns_native_logical_paths_for_inventory_and_upload(self):
  public=self.base/'public';public.mkdir(mode=0o755)
  for p in PUBLIC.glob('*.php'):shutil.copyfile(p,public/p.name)
  # Match the isolated fixture's trusted owner, as other store constructors do.
  platform=public/'platform.php';platform.write_text(platform.read_text().replace('self::readProfile($file);','self::readProfile($file,fileowner(__DIR__));'))
  profile=public/'platform-profile.json';profile.write_text('{"schema_version":1,"platform":"openwrt"}');profile.chmod(0o644)
  body="""$store=new AsusBlobStore($base.'/resources',$owner,$base.'/missing.json');$row=$store->upload('native.bin','QQ==','559aead08264d5795d3909718cdd05abd49572e84fe55590eef31a88a08fdffd');echo json_encode([$row,$store->inventory()]);"""
  v=self.call(body,public=public);self.assertIsInstance(v,list);self.assertEqual(v[0]['path'],'/etc/nfqws2/blobs/native.bin');self.assertEqual(v[1]['files'][0],v[0]);self.assertNotIn(str(self.root),json.dumps(v))
 def test_package_catalog_uses_the_pinned_entware_alias_on_writable_usb_mounts(self):
  mount=self.base/'usb';mount.mkdir(mode=0o777);mount.chmod(0o777);entware=mount/'entware';entware.mkdir(mode=0o755);(entware/'etc').mkdir(mode=0o755);resources=entware/'etc/nfqws2';resources.mkdir(mode=0o755);(resources/'blobs').mkdir(mode=0o755);(resources/'blobs/example.bin').write_bytes(b'A');(entware/'share').mkdir(mode=0o755);shared=entware/'share/nfqws2-asus';shared.mkdir(mode=0o755)
  catalog=shared/'blob-catalog.json';catalog.write_text(json.dumps({'schema_version':1,'files':[{'name':'official.bin','byte_length':1,'sha256':'559aead08264d5795d3909718cdd05abd49572e84fe55590eef31a88a08fdffd','format':'tls','label':{'ru':'TLS пример','en':'TLS example'}}]}));catalog.chmod(0o644)
  alias=self.base/'opt';alias.symlink_to(entware,target_is_directory=True);public=self.base/'public';public.mkdir(mode=0o755)
  for p in PUBLIC.glob('*.php'):shutil.copyfile(p,public/p.name)
  # Substitute only the trusted platform's fixed mount/share paths for this host.
  p=public/'platform.php';p.write_text(p.read_text().replace("'root'=>'/opt'","'root'=>'"+str(alias)+"'").replace("'share'=>'/opt/share/nfqws2-asus'","'share'=>'"+str(alias)+"/share/nfqws2-asus'"))
  body="""$alias=$base.'/opt';$entware=realpath($alias);$reader=new AsusShareRead($owner,$entware,$alias);$store=new AsusBlobStore($entware.'/etc/nfqws2',$owner,null,$reader);echo json_encode($store->inventory());"""
  v=self.call(body,public=public);self.assertNotIn('error',v);self.assertEqual(v['files'][0]['format'],'tls');self.assertTrue(v['files'][0]['bundled']);self.assertEqual(v['files'][0]['label']['en'],'TLS example')
