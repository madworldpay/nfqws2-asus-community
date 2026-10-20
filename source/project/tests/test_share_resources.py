"""Explicit file copies must not follow links, race the source, or change router files."""
import base64,hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC

class ShareResourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'nfqws2';self.root.mkdir(mode=0o755)
        for kind in ['lists','lua','blobs']:(self.root/kind).mkdir(mode=0o755)
        (self.root/'lists/sites.list').write_text('image.tmdb.org\n')
        (self.root/'lua/custom.lua').write_text('function custom() return 1 end\n')
        (self.root/'blobs/hello.bin').write_bytes(b'\0\xff\x80BLOB\0')
    def tearDown(self):self.temp.cleanup()
    def call(self,action='inventory',data=None):
        code='''$file=$argv[1].'/share-resources.php';if(!is_file($file)){echo json_encode(['error'=>'missing_feature']);exit;}
        require $file;try{$r=new AsusShareResources($argv[2],(int)$argv[3]);$v=json_decode(stream_get_contents(STDIN),true);
        $out=match($argv[4]){'inventory'=>$r->inventory(),'read'=>$r->read($v['id'],$v['sha256']),'prepare'=>$r->prepare($v)};echo json_encode($out,JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid()),action],input=json.dumps(data),text=True,capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
    def inventory(self):
        v=self.call();self.assertNotIn('error',v);return v['files']
    def test_inventory_has_exact_hashes_and_no_absolute_paths(self):
        before={str(f):f.read_bytes() for f in self.root.rglob('*') if f.is_file()}
        v=self.call();self.assertNotIn('error',v);self.assertEqual(len(v['files']),3)
        self.assertNotIn(str(self.root),json.dumps(v));self.assertFalse(v['scan_truncated'])
        for f in v['files']:
            raw=(self.root/f['kind']/f['name']).read_bytes();self.assertEqual(f['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(f['byte_length'],len(raw));self.assertEqual(f['state'],'available')
        self.assertEqual(before,{str(f):f.read_bytes() for f in self.root.rglob('*') if f.is_file()})
    def test_prepare_only_selected_files_and_preserves_binary_exactly(self):
        rows=self.inventory();blob=next(x for x in rows if x['kind']=='blobs')
        v=self.call('prepare',[{'id':blob['id'],'source_sha256':blob['sha256']}]);self.assertNotIn('error',v);self.assertEqual(len(v),1)
        raw=base64.b64decode(v[0]['data_base64']);self.assertEqual(raw,b'\0\xff\x80BLOB\0');self.assertEqual(v[0]['sha256'],hashlib.sha256(raw).hexdigest());self.assertNotIn('sites.list',json.dumps(v))
    def test_text_edit_is_a_copy_and_keeps_source_hash(self):
        item=next(x for x in self.inventory() if x['kind']=='lists')
        raw=self.call('read',item);self.assertEqual(raw['encoding'],'utf8');self.assertEqual(raw['text'],'image.tmdb.org\n')
        v=self.call('prepare',[{'id':item['id'],'source_sha256':item['sha256'],'text':'edited.example\n'}]);self.assertNotIn('error',v)
        self.assertEqual(base64.b64decode(v[0]['data_base64']),b'edited.example\n');self.assertEqual(v[0]['source_sha256'],item['sha256']);self.assertEqual((self.root/'lists/sites.list').read_text(),'image.tmdb.org\n')
    def test_replaced_or_changed_source_is_refused_after_selection(self):
        item=self.inventory()[0];path=self.root/item['kind']/item['name'];path.write_bytes(b'changed')
        self.assertEqual(self.call('read',item)['error'],'source_changed')
        self.assertEqual(self.call('prepare',[{'id':item['id'],'source_sha256':item['sha256']}])['error'],'source_changed')
    def test_symlink_hardlink_fifo_and_symlink_parent_are_never_read(self):
        outside=Path(self.temp.name)/'PRIVATE_CANARY';outside.write_text('PRIVATE_CANARY')
        (self.root/'lists/link.list').symlink_to(outside);os.link(outside,self.root/'lists/hard.list');os.mkfifo(self.root/'lists/pipe.list')
        v=self.call();self.assertNotIn('error',v);self.assertEqual(len(v['files']),3);self.assertNotIn('PRIVATE_CANARY',json.dumps(v))
        (self.root/'lua/custom.lua').unlink();(self.root/'lua').rmdir();(self.root/'lua').symlink_to(outside.parent,target_is_directory=True)
        v=self.call();self.assertNotIn('error',v);self.assertEqual(len(v['files']),2);self.assertGreater(v['skipped'],0)
    def test_ids_and_selection_are_closed_and_duplicates_rejected(self):
        item=self.inventory()[0]
        for data in [[{'id':'../../etc/passwd','source_sha256':item['sha256']}],[{'id':item['id'],'source_sha256':item['sha256'],'path':'/etc/passwd'}],[{'id':item['id'],'source_sha256':item['sha256']}]*2]:
            self.assertIn('error',self.call('prepare',data))
    def test_large_file_and_aggregate_limit_are_explicit(self):
        (self.root/'lists/large.list').write_bytes(b'x'*262145)
        rows=self.inventory();large=next(x for x in rows if x['name']=='large.list');self.assertEqual(large['state'],'too_large')
        selected=[]
        for i in range(3):
            (self.root/f'blobs/part{i}.bin').write_bytes(bytes([i])*200000)
        for row in self.inventory():
            if row['name'].startswith('part'):selected.append({'id':row['id'],'source_sha256':row['sha256']})
        self.assertEqual(self.call('prepare',selected)['error'],'output_limit')

    def test_group_writable_parent_directory_is_not_a_trusted_source(self):
        (self.root/'lists').chmod(0o770)
        v=self.call();self.assertNotIn('error',v);self.assertEqual(len(v['files']),2);self.assertGreater(v['skipped'],0)

    def test_mutable_regular_list_remains_data_and_changed_hash_is_refused(self):
        path=self.root/'lists/sites.list';path.chmod(0o666)
        row=next(x for x in self.inventory() if x['name']=='sites.list')
        v=self.call('prepare',[{'id':row['id'],'source_sha256':row['sha256']}]);self.assertNotIn('error',v)
        path.write_text('changed\n');v=self.call('prepare',[{'id':row['id'],'source_sha256':row['sha256']}]);self.assertEqual(v.get('error'),'source_changed')

class ShareMountedRootTests(unittest.TestCase):
    def test_trusted_opt_boundary_is_pinned_but_untrusted_parent_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            parent=Path(d)/'writable';parent.mkdir(mode=0o777);parent.chmod(0o777)
            root=parent/'entware';root.mkdir(mode=0o755);(root/'etc').mkdir(mode=0o755);(root/'etc/file').write_text('exact')
            alias=Path(d)/'opt';alias.symlink_to(root,target_is_directory=True)
            code="""require $argv[1].'/share-read.php';$root=$argv[2];$owner=(int)$argv[4];$strict=new AsusShareRead($owner);$pinned=new AsusShareRead($owner,$root,$argv[3]);$out=['strict'=>$strict->directory($root.'/etc')];try{$out['data']=$pinned->bytes($root.'/etc/file',256);}catch(Throwable $e){$out['error']=$e->getMessage();}rename($root,$root.'-old');mkdir($root,0755);mkdir($root.'/etc',0755);file_put_contents($root.'/etc/file','exact');try{$pinned->bytes($root.'/etc/file',256);$out['swap_accepted']=true;}catch(Throwable $e){$out['swap_error']=$e->getMessage();}echo json_encode($out);"""
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(alias),str(os.getuid())],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr);v=json.loads(p.stdout);self.assertFalse(v['strict']);self.assertEqual(v.get('data'),'exact',v);self.assertEqual(v.get('swap_error'),'source_changed',v)
