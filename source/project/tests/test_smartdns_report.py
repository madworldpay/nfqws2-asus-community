import json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
from test_smartdns_profile import profile,upstream
class SmartDnsReportTests(unittest.TestCase):
    def test_report_is_passive_distinguishes_missing_and_error_and_drops_private_strings(self):
        code=r'''$f=$argv[1].'/smartdns-report.php';if(!is_file($f)){echo json_encode(['error'=>'missing_projection']);exit;}require $f;
        $root=$argv[2];$owner=(int)$argv[3];$store=new AsusSmartDnsStore($root,$owner);$projection=new AsusSmartDnsReport($store,fn()=>['installed'=>true,'version'=>'48.4']);$out=['missing'=>$projection->collect(),'created'=>is_dir($root)];
        $p=json_decode(stream_get_contents(STDIN),true);$h=$store->saveDraft($p);$store->savePreview(['id'=>str_repeat('b',32),'profile_hash'=>$h,'baseline_hash'=>str_repeat('a',64),'expires_uptime'=>PHP_FLOAT_MAX]);$store->begin(str_repeat('c',32),$h,str_repeat('a',64));$backup=$store->backup(['candidate_profile'=>$p]);$store->transition(str_repeat('c',32),['applying'],['state'=>'confirmed','active'=>['profile'=>$p,'profile_hash'=>$h,'backup_id'=>$backup]]);
        $before=hash_file('sha256',$root.'/state.json');$out['managed']=$projection->collect();$out['unchanged']=$before===hash_file('sha256',$root.'/state.json');file_put_contents($root.'/state.json','broken');$out['error']=$projection->collect();echo json_encode($out);'''
        p=profile(upstream(label='PRIVATE_LABEL',protocol='doh',port=443,address='9.9.9.9',tls_name='private-tls.example',url='https://dns.example/PRIVATE_PATH?token=PRIVATE_TOKEN',domains=[{'name':'private-site.example','include_subdomains':True}]))
        with tempfile.TemporaryDirectory() as d:
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(Path(d)/'state'),str(os.getuid())],input=json.dumps(p),capture_output=True,text=True,timeout=5)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');out=json.loads(r.stdout)
            self.assertEqual(out['missing']['read_state'],'missing');self.assertFalse(out['created']);self.assertTrue(out['unchanged'])
            self.assertEqual(out['managed']['journal_state'],'confirmed');self.assertEqual(out['managed']['upstreams'][0]['protocol'],'doh')
            self.assertEqual(out['error']['read_state'],'unavailable');self.assertNotIn('PRIVATE_',json.dumps(out));self.assertNotIn('private-tls',json.dumps(out));self.assertNotIn('private-site',json.dumps(out));self.assertFalse(out['managed']['runtime_verified'])
if __name__=='__main__':unittest.main()
