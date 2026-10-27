"""A signed catalog never turns a selection into an arbitrary download."""
import base64, copy, hashlib, json, os, pathlib, subprocess, tempfile, unittest
from test_dpi_normalize import PHP, PUBLIC


class ProfileCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = pathlib.Path(cls.tmp.name)
        cls.key = cls.base/'key.pem'
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(cls.key)],check=True,capture_output=True)
        cls.public = subprocess.check_output(['openssl','pkey','-in',str(cls.key),'-pubout'],text=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def manifest(self):
        return {'schema_version':1,'revision':1,'profiles':[{'id':'example-profile','title':'Example','category':'global','provider':'','region':'','description':'Example preset','attribution':'Example author','updated_at':'2026-10-23T12:00:00Z','revision':1,'min_build':68,'size':2,'sha256':hashlib.sha256(b'{}').hexdigest()}]}

    def signed(self, manifest=None, raw=None):
        raw = (json.dumps(self.manifest() if manifest is None else manifest,separators=(',',':')) if raw is None else raw).encode()
        signature = subprocess.check_output(['openssl','dgst','-sha256','-sign',str(self.key)],input=raw)
        return json.dumps({'manifest':base64.b64encode(raw).decode(),'signature':base64.b64encode(signature).decode()})

    def call(self,envelope,public=None):
        code="""$f=$argv[1].'/profile-catalog.php';if(!is_file($f)){echo json_encode(['error'=>'missing_feature']);exit;}require $f;$v=json_decode(stream_get_contents(STDIN),true);try{echo json_encode(AsusProfileCatalog::verify($v['envelope'],$v['key']),JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps({'envelope':envelope,'key':self.public if public is None else public}),text=True,capture_output=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def test_signed_catalog_retains_original_title_category_and_attribution(self):
        self.assertEqual(self.call(self.signed()),self.manifest())

    def test_tampering_wrong_signature_and_private_or_wrong_size_key_are_rejected(self):
        envelope=json.loads(self.signed());envelope['manifest']=base64.b64encode(b'{"revision":999}').decode()
        self.assertEqual(self.call(json.dumps(envelope))['error'],'catalog_signature')
        envelope=json.loads(self.signed());envelope['signature']=base64.b64encode(b'\0'*384).decode()
        self.assertEqual(self.call(json.dumps(envelope))['error'],'catalog_signature')
        self.assertIn('error',self.call(self.signed(),self.key.read_text()))
        self.assertIn('error',self.call(self.signed(),'not a key'))

    def test_closed_fields_duplicate_keys_and_oversize_never_become_catalog(self):
        bad=[self.signed(raw='{"schema_version":1,"schema_version":1,"revision":1,"profiles":[]}'),self.signed(raw=' '*65537),' '*131073]
        v=self.manifest();v['profiles'][0]['url']='https://evil.invalid/profile';bad.append(self.signed(v))
        v=self.manifest();v['profiles'].append(copy.deepcopy(v['profiles'][0]));bad.append(self.signed(v))
        for envelope in bad:
            with self.subTest(length=len(envelope)):self.assertIn('error',self.call(envelope))

    def test_ids_hashes_sizes_dates_and_groups_are_bounded(self):
        for field,value in [('id','../profile'),('sha256','A'*64),('size',4194305),('size',0),('category','arbitrary'),('updated_at','tomorrow')]:
            v=self.manifest();v['profiles'][0][field]=value
            with self.subTest(field=field,value=value):self.assertIn('error',self.call(self.signed(v)))
        v=self.manifest();v['profiles']*=129;self.assertIn('error',self.call(self.signed(v)))

    def transport(self,fixture,body):
        code="""$f=$argv[1].'/profile-catalog-transport.php';if(!is_file($f)){echo json_encode(['error'=>'missing_feature']);exit;}require $f;$v=json_decode(stream_get_contents(STDIN),true);$calls=[];$read=function($url,$cap,$deadline)use(&$v,&$calls){$calls[]=$url;if(!isset($v['responses'][$url]))throw new RuntimeException('catalog_unavailable');$r=$v['responses'][$url];if(is_array($r))throw new RuntimeException($r['error']);return $r;};try{$t=new AsusProfileCatalogTransport($v['key'],$read,$argv[2],(int)$argv[3],fn()=>1000,68);"""+body+"""}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage(),'calls'=>$calls]);}"""
        with tempfile.TemporaryDirectory() as directory:
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),directory+'/cache',str(os.getuid())],input=json.dumps({'key':self.public,**fixture}),capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def test_only_selected_immutable_file_is_loaded_and_verified_index_is_cached(self):
        # The imported document remains ordinary input to the existing parser.
        from test_import_document import STRATEGY
        raw=json.dumps(STRATEGY);v=self.manifest();v['profiles'][0].update(size=len(raw.encode()),sha256=hashlib.sha256(raw.encode()).hexdigest())
        origin='https://mad13mansprofy13.asuscomm.com:5443/nfqws-profiles/v1/'
        responses={origin+'catalog.json':self.signed(v),origin+'files/'+v['profiles'][0]['sha256']+'.json':raw}
        out=self.transport({'responses':responses},"$t->catalog();$raw=$t->document('example-profile','"+v['profiles'][0]['sha256']+"');echo json_encode(['document'=>$raw,'calls'=>$calls]);")
        self.assertEqual(out.get('document'),raw,out);self.assertEqual(out['calls'],list(responses))

    def test_unknown_selection_changed_hash_bad_profile_and_oversize_are_rejected(self):
        origin='https://mad13mansprofy13.asuscomm.com:5443/nfqws-profiles/v1/';v=self.manifest();digest=v['profiles'][0]['sha256']
        for ident,sha in [('../escape',digest),('example-profile','a'*64),('unknown',digest)]:
            out=self.transport({'responses':{origin+'catalog.json':self.signed(v)}},"$t->document("+json.dumps(ident)+","+json.dumps(sha)+");echo '{}';")
            self.assertIn('error',out);self.assertFalse(any('/files/' in url for url in out.get('calls',[])))
        for raw in ['{}','xx','x'*4194305]:
            out=self.transport({'responses':{origin+'catalog.json':self.signed(v),origin+'files/'+digest+'.json':raw}},"$t->document('example-profile','"+digest+"');echo '{}';")
            self.assertIn('error',out)

    def test_corrupted_regular_cache_is_refetched_without_trusting_its_contents(self):
        origin='https://mad13mansprofy13.asuscomm.com:5443/nfqws-profiles/v1/'
        out=self.transport({'responses':{origin+'catalog.json':self.signed()}},"$t->catalog();file_put_contents($argv[2].'/catalog.json','corrupt');$index=$t->catalog();echo json_encode(['revision'=>$index['revision'],'calls'=>$calls]);")
        self.assertEqual(out.get('revision'),1,out);self.assertEqual(len(out['calls']),2)

    def test_newer_minimum_build_and_cache_symlink_never_download_profile(self):
        origin='https://mad13mansprofy13.asuscomm.com:5443/nfqws-profiles/v1/';v=self.manifest();v['profiles'][0]['min_build']=69;sha=v['profiles'][0]['sha256']
        out=self.transport({'responses':{origin+'catalog.json':self.signed(v)}},"$t->document('example-profile','"+sha+"');echo '{}';")
        self.assertEqual(out['error'],'catalog_version');self.assertEqual(out['calls'],[origin+'catalog.json'])
        out=self.transport({'responses':{origin+'catalog.json':self.signed()}},"$t->catalog();unlink($argv[2].'/catalog.json');symlink(__FILE__,$argv[2].'/catalog.json');$t->catalog();echo '{}';")
        self.assertEqual(out['error'],'catalog_unavailable');self.assertEqual(len(out['calls']),1)

    def test_expired_index_rejects_stale_selection_and_signed_revision_rollback(self):
        origin='https://mad13mansprofy13.asuscomm.com:5443/nfqws-profiles/v1/';old=self.manifest();new=self.manifest();new['revision']=2;new['profiles'][0]['sha256']='a'*64
        body="$t->catalog();$v['responses']['"+origin+"catalog.json']=$v['next'];touch($argv[2].'/catalog.json',0);"
        out=self.transport({'responses':{origin+'catalog.json':self.signed(old)},'next':self.signed(new)},body+"$t->document('example-profile','"+old['profiles'][0]['sha256']+"');echo '{}';")
        self.assertEqual(out['error'],'catalog_changed');self.assertFalse(any('/files/' in url for url in out['calls']))
        out=self.transport({'responses':{origin+'catalog.json':self.signed(new)},'next':self.signed(old)},body+"$t->catalog();echo '{}';")
        self.assertEqual(out['error'],'catalog_changed')

