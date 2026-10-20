"""Real preparation pipeline from saved sources to one immutable reviewed snapshot."""
import base64,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
from test_dpi_saved_projector import SAMPLE_EN
from test_support_relay_validation import fixture,FILENAME

class SharePrepareTests(unittest.TestCase):
    def test_mixed_prepare_masks_identity_and_survives_originals_deleted_after_preview(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'native';source.mkdir();original=source/'dpi_detector_results-20261016-130000.txt';original.write_text(SAMPLE_EN);original.chmod(0o600)
            config=root/'config';config.write_text('NFQWS_ARGS="--filter-tcp=80"\n')
            data={'raw':fixture().decode(),'filename':FILENAME}
            code='''require $argv[1].'/share-api.php';class FixtureIO extends AsusReportIO {
                public function streamCommand(string $id,callable $consume,float $timeout=1.0):array{foreach(['productid=GT-BE19000AI','firmver=3006.102','buildno=9','extendno=0'] as $line)$consume($line);return ['state'=>'available'];}
                public function read(string $source,int $limit=262144):array{return ['state'=>'available','value'=>'4.19.294'];}}
                $d=$argv[2];$owner=(int)$argv[3];$input=json_decode(stream_get_contents(STDIN),true);$saved=new AsusDpiSavedStore($d.'/saved',$d.'/native',$owner);$r=$saved->refresh()['reports'][0];$key=str_repeat('a',64);$now=1000;
                $api=new AsusShareApi($saved,null,null,$d.'/config',['core'=>'1.3.1-asus6+b16','web'=>'0.1.4'],new AsusShareSource($d.'/identity',$owner,new FixtureIO()));
                $selection=['report'=>['raw'=>$input['raw'],'filename'=>$input['filename'],'proof'=>AsusReportProof::issue($input['raw'],$input['filename'],$key,$now)],'dpi'=>['kind'=>'saved','id'=>$r['id']],'strategy'=>['mode'=>'blocks','draft'=>['blocks'=>[['key'=>'NFQWS_ARGS','value'=>'--filter-tcp=443 --filter-ip=192.168.99.1']]],'context'=>['purpose'=>'video','operator'=>'Example ISP','region'=>'PRIVATE_LOCATION','share_location'=>false]],'link_installation'=>false];
                $prepared=$api->handle(['cmd'=>'shareprepare','csrf_token'=>'fixture','selection'=>json_encode($selection)],$key,$now);
                $saved->delete($r['id']);unlink($d.'/config');$valid=AsusShareBundle::verify($prepared['proof'],$prepared['files'],$key,$now+1,$prepared['source']);
                echo json_encode(['prepared'=>$prepared,'valid'=>$valid,'identity_created'=>is_dir($d.'/identity')]);'''
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),d,str(os.getuid())],input=json.dumps(data),capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');v=json.loads(p.stdout)
            self.assertTrue(v['valid']);self.assertFalse(v['identity_created']);self.assertFalse(original.exists())
            self.assertEqual([f['type'] for f in v['prepared']['files']],['report','dpi','strategy'])
            dpi=json.loads(base64.b64decode(v['prepared']['files'][1]['data_base64']));strategy=json.loads(base64.b64decode(v['prepared']['files'][2]['data_base64']))
            self.assertEqual(dpi['type'],'nfqws2_dpi_saved');self.assertNotIn('PRIVATE_CANARY',json.dumps(dpi));self.assertNotIn('region',strategy)
            self.assertIn('--filter-tcp=443',strategy['blocks'][0]['value']);self.assertNotIn('192.168.99.1',json.dumps(strategy))
            self.assertEqual(v['prepared']['source']['model'],'GT-BE19000AI');self.assertNotIn('installation_id',v['prepared']['source'])

    def test_legacy_dpi_attachment_uses_run_time_not_sharing_time(self):
        from test_support_relay_bundle_validation import dpi_fixture,DPI_FILENAME
        from nfqws_support.share import validate_share
        with tempfile.TemporaryDirectory() as d:
            code='''require $argv[1].'/share-api.php';class OldDpiIO extends AsusReportIO{public function streamCommand(string $id,callable $c,float $timeout=1):array{$c('productid=LOCAL');return ['state'=>'available'];}public function read(string $s,int $l=262144):array{return ['state'=>'available','value'=>'local'];}}
            $d=$argv[2];$owner=(int)$argv[3];$s=new AsusDpiStore($d.'/dpi',$owner);$j=$s->reserve('11111111-1111-4111-8111-111111111111','run',['tests'=>[2]]);$s->update($j['id'],['state'=>'running']);$s->update($j['id'],['state'=>'partial','result'=>stream_get_contents(STDIN)]);$api=new AsusShareApi(null,$s,null,'/missing',['core'=>'fixture','web'=>'fixture'],new AsusShareSource($d.'/identity',$owner,new OldDpiIO()));echo json_encode($api->handle(['cmd'=>'shareprepare','csrf_token'=>'fixture','selection'=>json_encode(['dpi'=>['kind'=>'legacy','id'=>$j['id']]])],str_repeat('a',64),1000));'''
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),d,str(os.getuid())],input=dpi_fixture(),capture_output=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);v=json.loads(p.stdout);self.assertEqual(v['files'][0]['filename'],DPI_FILENAME)
