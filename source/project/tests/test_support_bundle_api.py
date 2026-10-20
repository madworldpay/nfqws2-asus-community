import json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
from test_support_relay_validation import fixture,FILENAME

class BundleProofTests(unittest.TestCase):
    def test_proof_binds_every_byte_name_order_type_size_session_and_time(self):
        code='''require $argv[1].'/support-bundle.php';$raw=file_get_contents($argv[2]);$f=AsusSupportBundle::file('report',$argv[3],$raw);$dpi=AsusSupportBundle::file('dpi','NFQWS2_DPI_2026-10-15_12-00-00Z.json','{}');$files=[$f,$dpi];$key=str_repeat('a',64);$proof=AsusSupportBundle::issue($files,$key,1000);
        $out=[AsusSupportBundle::verify($proof,$files,$key,1000),AsusSupportBundle::verify($proof,$files,str_repeat('b',64),1000),AsusSupportBundle::verify($proof,$files,$key,1601),AsusSupportBundle::verify($proof,$files,$key,999)];
        foreach(['filename','type','byte_length','sha256','data_base64'] as $k){$b=$files;$b[1][$k]=$k==='byte_length'?3:'changed';$out[]=AsusSupportBundle::verify($proof,$b,$key,1001);}$out[]=AsusSupportBundle::verify($proof,array_reverse($files),$key,1001);echo json_encode($out);'''
        with tempfile.NamedTemporaryFile() as f:
            f.write(fixture());f.flush();r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),f.name,FILENAME],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');self.assertEqual(json.loads(r.stdout),[True]+[False]*9)

    def test_prepared_snapshot_survives_deleting_stored_result(self):
        from test_support_relay_bundle_validation import dpi_fixture
        import base64
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'report').write_bytes(fixture());(p/'dpi').write_bytes(dpi_fixture())
            code='''require $argv[1].'/support-bundle.php';$s=new AsusDpiStore($argv[2].'/state',(int)$argv[3]);$j=$s->reserve('11111111-1111-4111-8111-111111111111','run',['tests'=>[1,2]]);$s->update($j['id'],['state'=>'running']);$s->update($j['id'],['state'=>'partial','finished_at'=>time(),'result'=>file_get_contents($argv[2].'/dpi')]);
            $raw=file_get_contents($argv[2].'/report');$key=str_repeat('a',64);$proof=AsusReportProof::issue($raw,$argv[4],$key,time());$b=new AsusSupportBundle($s);$out=$b->prepare($raw,$argv[4],$proof,$j['id'],$key,time());$s->deleteResult($j['id']);echo json_encode([$out,AsusSupportBundle::verify($out['proof'],$out['files'],$key,time())]);'''
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),directory,str(os.getuid()),FILENAME],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');out,valid=json.loads(r.stdout);self.assertTrue(valid);self.assertEqual(base64.b64decode(out['files'][0]['data_base64']),fixture());self.assertEqual(base64.b64decode(out['files'][1]['data_base64']),dpi_fixture())
