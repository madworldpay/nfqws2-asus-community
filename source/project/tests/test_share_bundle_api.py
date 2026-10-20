import base64,hashlib,json,subprocess,unittest,uuid
from test_dpi_normalize import PHP,PUBLIC
from test_support_relay_validation import fixture,FILENAME
from test_support_relay_bundle_validation import dpi_fixture,DPI_FILENAME

STRATEGY={'type':'nfqws2_strategy','schema_version':1,'mode':'blocks','versions':{'core':'1.3.1-asus6+b16','web':'0.1.4'},'blocks':[{'key':'NFQWS_ARGS','value':'--filter-tcp=443 --dpi-desync=fake'}],'purpose':'YouTube','operator':'Example ISP','comment':'','dependencies':[]}
def share_files(kinds=('report','dpi','strategy')):
    data={'report':(FILENAME,fixture()),'dpi':(DPI_FILENAME,dpi_fixture()),'strategy':('NFQWS2_STRATEGY_2026-10-16_10-00-00Z.json',json.dumps(STRATEGY).encode())}
    return [{'type':k,'filename':data[k][0],'byte_length':len(data[k][1]),'sha256':hashlib.sha256(data[k][1]).hexdigest(),'data_base64':base64.b64encode(data[k][1]).decode()} for k in kinds]

class ShareBundleTests(unittest.TestCase):
    def call(self,files,body):
        code='''require $argv[1].'/share-bundle.php';$files=json_decode(stream_get_contents(STDIN),true);$key=str_repeat('a',64);try{'''+body+'''}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(files),text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)

    def test_every_nonempty_combination_is_independent(self):
        for kinds in [('report',),('dpi',),('strategy',),('report','dpi'),('report','strategy'),('dpi','strategy'),('report','dpi','strategy')]:
            with self.subTest(kinds=kinds):
                v=self.call(share_files(kinds),'$v=AsusShareBundle::prepare($files,$key,1000);echo json_encode([$v,AsusShareBundle::verify($v["proof"],$v["files"],$key,1001)]);')
                self.assertTrue(v[1]);self.assertEqual([f['type'] for f in v[0]['files']],list(kinds))

    def test_proof_binds_bytes_names_order_session_and_time(self):
        v=self.call(share_files(),'''$p=AsusShareBundle::prepare($files,$key,1000)['proof'];$out=[];
        $out[]=AsusShareBundle::verify($p,$files,str_repeat('b',64),1000);$out[]=AsusShareBundle::verify($p,$files,$key,1601);
        $out[]=AsusShareBundle::verify($p,array_reverse($files),$key,1000);
        foreach(['filename','type','byte_length','sha256','data_base64'] as $k){$changed=$files;$changed[0][$k]=$k==='byte_length'?2:'tampered';$out[]=AsusShareBundle::verify($p,$changed,$key,1000);}echo json_encode($out);''')
        self.assertEqual(v,[False]*8)

    def test_duplicate_reordered_unknown_or_arbitrary_file_refused(self):
        for files in [[],share_files(('dpi','report')),share_files(('strategy','strategy')),share_files()+share_files(('dpi',))]:
            self.assertIn('error',self.call(files,'echo json_encode(AsusShareBundle::prepare($files,$key,1000));'))
        files=share_files(('strategy',));files[0]['type']='arbitrary'
        self.assertIn('error',self.call(files,'echo json_encode(AsusShareBundle::prepare($files,$key,1000));'))

    def test_envelope_checks_uuid_and_canonical_encoding(self):
        sid=str(uuid.uuid4())
        v=self.call(share_files(),f'''$raw=json_encode(['version'=>3,'submission_id'=>'{sid}','files'=>$files]);$v=AsusShareBundle::envelope($raw,'{sid}');echo json_encode($v);''')
        self.assertEqual(v['version'],3)
        files=share_files(('strategy',));files[0]['data_base64']+='\n'
        self.assertIn('error',self.call(files,'echo json_encode(AsusShareBundle::prepare($files,$key,1000));'))

    def test_source_metadata_and_optional_link_are_part_of_reviewed_proof(self):
        v=self.call(share_files(('strategy',)),'''$s=['model'=>'GT-BE19000AI','firmware'=>['firmver'=>'3006.102','buildno'=>'9','extendno'=>'0'],'kernel'=>'4.19.294','versions'=>['core'=>'1.3.1-asus6+b16','web'=>'0.1.4'],'installation_id'=>str_repeat('c',32)];
        $p=AsusShareBundle::prepare($files,$key,1000,$s);$out=[$p,AsusShareBundle::verify($p['proof'],$files,$key,1000,$s)];
        $s['installation_id']=str_repeat('d',32);$out[]=AsusShareBundle::verify($p['proof'],$files,$key,1000,$s);
        unset($s['installation_id']);$out[]=AsusShareBundle::verify($p['proof'],$files,$key,1000,$s);echo json_encode($out);''')
        self.assertIn('source',v[0]);self.assertEqual(v[1:],[True,False,False])
