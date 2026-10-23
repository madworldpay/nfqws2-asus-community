"""Only reviewed profile bytes become immutable signed cloud objects."""
import base64,copy,hashlib,json,os,pathlib,subprocess,tempfile,unittest
from test_dpi_normalize import PHP,PUBLIC,ROOT
from test_import_document import STRATEGY
from test_import_plan import documents


class ProfileCatalogPublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys=tempfile.TemporaryDirectory();cls.key=pathlib.Path(cls.keys.name)/'private.pem'
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(cls.key)],check=True,capture_output=True)
        cls.public=subprocess.check_output(['openssl','pkey','-in',str(cls.key),'-pubout'])

    @classmethod
    def tearDownClass(cls):cls.keys.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=pathlib.Path(self.tmp.name);self.profiles=self.base/'inputs';self.profiles.mkdir();self.out=self.base/'output'
        self.raw=json.dumps(STRATEGY,separators=(',',':')).encode();(self.profiles/'example.json').write_bytes(self.raw)
        self.meta={'schema_version':1,'revision':1,'profiles':[{'id':'example','title':'Original example','category':'global','provider':'','region':'','description':'Example strategy','attribution':'Example author','updated_at':'2026-10-23T12:00:00Z','revision':1,'min_build':68,'file':'example.json','source_sha256':hashlib.sha256(self.raw).hexdigest()}]}
        self.metadata=self.base/'approved.json'

    def publish(self,success=True):
        self.metadata.write_text(json.dumps(self.meta))
        r=subprocess.run(['python3',str(ROOT/'profile-catalog/publish.py'),'--metadata',str(self.metadata),'--profiles-dir',str(self.profiles),'--private-key',str(self.key),'--output',str(self.out),'--php',PHP],capture_output=True,text=True,timeout=20)
        if success:self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        else:self.assertNotEqual(r.returncode,0,r.stdout+r.stderr)
        return r

    def verified(self):
        pub=self.base/'public.pem';pub.write_bytes(self.public)
        code="require $argv[1].'/profile-catalog.php';echo json_encode(AsusProfileCatalog::verify(file_get_contents($argv[2]),file_get_contents($argv[3])),JSON_THROW_ON_ERROR);"
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.out/'catalog.json'),str(pub)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);return json.loads(r.stdout)

    def test_reviewed_bytes_are_signed_and_only_hash_named_profiles_are_served(self):
        self.publish();index=self.verified();entry=index['profiles'][0];digest=hashlib.sha256(self.raw).hexdigest()
        self.assertEqual(entry['title'],'Original example');self.assertEqual(entry['category'],'global');self.assertEqual(entry['sha256'],digest)
        self.assertEqual((self.out/'files'/f'{digest}.json').read_bytes(),self.raw)
        self.assertEqual({str(p.relative_to(self.out)) for p in self.out.rglob('*') if p.is_file()},{'catalog.json',f'files/{digest}.json'})
        self.assertNotIn('PRIVATE KEY',(self.out/'catalog.json').read_text())

    def test_missing_blob_file_and_alias_dependencies_are_not_signed(self):
        for operand in ['--lua-desync=fake:blob=missing_fixture_blob','--hostlist=/opt/etc/nfqws2/lists/missing.list','--hostlist=RESOURCE_99']:
            value=copy.deepcopy(STRATEGY);value['blocks'][0]['value']='--filter-tcp=443 '+operand
            raw=json.dumps(value).encode();(self.profiles/'example.json').write_bytes(raw);self.meta['profiles'][0]['source_sha256']=hashlib.sha256(raw).hexdigest()
            result=self.publish(False);self.assertIn('dependencies',result.stderr)
        self.assertFalse((self.out/'catalog.json').exists())

    def test_packaged_lua_and_engine_builtin_blob_are_self_contained(self):
        value=copy.deepcopy(STRATEGY);value['shared']['NFQWS_BASE_ARGS']='--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua'
        value['blocks'][0]['value']='--filter-tcp=443 --lua-desync=fake:blob=fake_default_tls'
        raw=json.dumps(value).encode();(self.profiles/'example.json').write_bytes(raw);self.meta['profiles'][0]['source_sha256']=hashlib.sha256(raw).hexdigest();self.publish()

    def test_dns_with_sites_and_fixed_records_uses_real_selective_plan(self):
        from test_import_plan import ImportPlanTests
        docs,_=ImportPlanTests().dns_input();value=json.loads(docs[0]);value['sources'][0]['profile']['records']=[{'name':'media.example.com','include_subdomains':False,'addresses':['203.0.113.10'],'checked_at':None}]
        raw=json.dumps(value).encode();(self.profiles/'example.json').write_bytes(raw);self.meta['profiles'][0]['source_sha256']=hashlib.sha256(raw).hexdigest();self.publish()

    def test_changed_unreviewed_input_does_not_replace_existing_catalog(self):
        self.publish();before=(self.out/'catalog.json').read_bytes()
        (self.profiles/'example.json').write_bytes(self.raw+b'\n');self.publish(False)
        self.assertEqual((self.out/'catalog.json').read_bytes(),before)

    def test_new_revision_keeps_previous_immutable_file(self):
        self.publish();old=hashlib.sha256(self.raw).hexdigest()
        v=copy.deepcopy(STRATEGY);v['blocks'][0]['value']='--filter-tcp=80';new=json.dumps(v).encode();(self.profiles/'example.json').write_bytes(new)
        self.meta['revision']=2;self.meta['profiles'][0].update(revision=2,source_sha256=hashlib.sha256(new).hexdigest());self.publish()
        self.assertEqual(self.verified()['revision'],2);self.assertEqual((self.out/'files'/f'{old}.json').read_bytes(),self.raw)
        self.assertEqual(len(list((self.out/'files').glob('*.json'))),2)

    def test_normalized_output_cannot_contain_private_inputs(self):
        self.out=self.base/'unused'/'..'/'inputs'
        self.publish(False)
        self.assertFalse((self.profiles/'catalog.json').exists())

    def test_lua_attachments_and_html_blobs_are_not_published(self):
        value=json.loads(documents()[1])
        for kind,data in [('lua',b'return 1\n'),('blobs',b'<!DOCTYPE html><html>Not a payload</html>')]:
            row=value['files'][0];row.update(kind=kind,name='example.lua' if kind=='lua' else 'example.bin',encoding='utf8' if kind=='lua' else 'base64',source_sha256=hashlib.sha256(data).hexdigest(),sha256=hashlib.sha256(data).hexdigest(),byte_length=len(data),data_base64=base64.b64encode(data).decode())
            value['files']=[row];value['audit'].update(scope='files_only',references=[])
            raw=json.dumps(value).encode();(self.profiles/'example.json').write_bytes(raw);self.meta['profiles'][0]['source_sha256']=hashlib.sha256(raw).hexdigest();result=self.publish(False)
            self.assertIn('Lua is supplied' if kind=='lua' else 'HTML page',result.stderr)
        self.assertFalse((self.out/'catalog.json').exists())

    def test_invalid_private_reports_and_identity_are_not_published(self):
        for value in [{'version':4,'files':[{'type':'report'}]},STRATEGY|{'private_key':'PRIVATE_CANARY'},STRATEGY|{'mode':'config','config':'ASUS_CLIENTS4="192.168.99.45"\nNFQWS_ARGS="--filter-tcp=443"\n','omitted_options':0}]:
            raw=json.dumps(value).encode();(self.profiles/'example.json').write_bytes(raw);self.meta['profiles'][0]['source_sha256']=hashlib.sha256(raw).hexdigest();self.publish(False)
        self.assertFalse((self.out/'catalog.json').exists())

    def test_path_traversal_symlinks_and_republishing_an_old_revision_are_rejected(self):
        self.meta['profiles'][0]['file']='../approved.json';self.publish(False)
        self.meta['profiles'][0]['file']='example.json';self.publish();before=(self.out/'catalog.json').read_bytes();self.publish(False)
        self.assertEqual((self.out/'catalog.json').read_bytes(),before)
        self.meta['revision']=2;(self.profiles/'example.json').unlink();(self.profiles/'example.json').symlink_to(self.metadata);self.publish(False)
