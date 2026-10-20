import json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC

class ShareSourceTests(unittest.TestCase):
    def call(self,root,body):
        code="require $argv[1].'/share-source.php';try{$s=new AsusShareSource($argv[2],(int)$argv[3]);"+body+"}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def test_opt_out_does_not_create_identity_and_opt_in_survives_new_session(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'identity'
            self.assertEqual(self.call(root,'echo json_encode($s->identity(false));'),None)
            self.assertFalse(root.exists())
            a=self.call(root,'echo json_encode($s->identity(true));');b=self.call(root,'echo json_encode($s->identity(true));')
            self.assertRegex(a,'^[a-f0-9]{32}$');self.assertEqual(a,b)
            self.assertEqual(root.stat().st_mode&0o777,0o700)
            self.assertEqual((root/'id').stat().st_mode&0o777,0o600)
            self.assertEqual(self.call(root,'echo json_encode($s->identity(false));'),None)
            self.assertEqual(self.call(Path(d)/'other','echo json_encode($s->identity(true));')==a,False)
    def test_links_and_corrupt_or_public_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'identity';root.mkdir(mode=0o700);p=root/'id';p.write_text('a'*32);p.chmod(0o644)
            self.assertIn('error',self.call(root,'echo json_encode($s->identity(true));'))
            p.chmod(0o600);p.write_text('not-an-id')
            self.assertIn('error',self.call(root,'echo json_encode($s->identity(true));'))
            p.unlink();target=Path(d)/'target';target.write_text('a'*32);target.chmod(0o600);p.symlink_to(target)
            self.assertIn('error',self.call(root,'echo json_encode($s->identity(true));'));self.assertEqual(target.read_text(),'a'*32)
    def test_platform_projection_contains_no_hardware_or_network_identity(self):
        with tempfile.TemporaryDirectory() as d:
            body="""$nv=['productid'=>'GT-BE19000AI','firmver'=>'3006.102','buildno'=>'9','extendno'=>'0','serial_no'=>'SERIAL_CANARY','lan_hwaddr'=>'aa:bb:cc:dd:ee:ff','wan0_ipaddr'=>'198.51.100.4'];
            echo json_encode(AsusShareSource::platform($nv,'4.19.294',['core'=>'1.3.1-asus6+b16','web'=>'0.1.4']));"""
            v=self.call(Path(d)/'identity',body)
            self.assertEqual(v['model'],'GT-BE19000AI');self.assertEqual(v['firmware']['buildno'],'9')
            self.assertEqual(set(v),{'model','firmware','kernel','versions'})
            self.assertNotIn('CANARY',json.dumps(v));self.assertNotIn('198.51',json.dumps(v))
            bad=self.call(Path(d)/'identity',"echo json_encode(AsusShareSource::platform(['productid'=>'my-home-secret','firmver'=>'bad secret'],'private-hostname',[]));")
            self.assertEqual(bad['model'],'ASUS-unknown');self.assertIsNone(bad['kernel']);self.assertIsNone(bad['firmware']['firmver'])
