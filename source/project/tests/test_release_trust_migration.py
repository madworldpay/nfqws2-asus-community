"""A bootstrap trust change stays local to one sealed native transaction."""
import importlib.util,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PHP=os.environ.get('PHP_NATIVE_TEST_BINARY') or shutil.which('php')

class ReleaseTrustMigration(unittest.TestCase):
 def test_installer_carries_trust_to_both_prepare_and_sealed_worker(self):
  spec=importlib.util.spec_from_file_location('trust_bundle',ROOT/'openwrt/install-bundle.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  bridge=m.bridge()
  self.assertIn('NFQWS_NATIVE_INSTALL_KEY',bridge)
  self.assertIn('NFQWS_NATIVE_INSTALL_DISCOVERY',bridge)
  self.assertIn("['resources'=>$trust['resources']]",bridge)
  self.assertIn("/runtime'),$trust)",bridge)

 @unittest.skipUnless(PHP,'native PHP required')
 def test_overlay_keeps_installed_key_and_discovery_unchanged(self):
  module=ROOT/'openwrt/install-trust.php';self.assertTrue(module.exists(),'Native trust migration needs an operation-local immutable resource overlay')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);app=root/'installed';app.mkdir(mode=0o700)
   (app/'update-github.php').write_text('<?php // old feed');(app/'platform-profile.json').write_text('{}')
   (app/'worker.php').write_text('<?php // installed worker')
   for file in app.iterdir():file.chmod(0o644)
   program="require $argv[1].'/webui/web/public/update-store.php';require $argv[1].'/openwrt/install-trust.php';$s=new AsusUpdateStore($argv[2],(int)$argv[4]);$v=NfqwsOpenWrtInstallTrust::stage($s,'NEW KEY','NEW SCHEMA','<?php // new feed',$argv[3],(int)$argv[4]);echo json_encode($v);"
   call=lambda:subprocess.run([PHP,'-n','-r',program,str(ROOT),str(root/'private'),str(app),str(os.getuid())],capture_output=True,text=True,timeout=10)
   r=call();self.assertEqual(r.returncode,0,r.stdout+r.stderr);v=json.loads(r.stdout)
   self.assertEqual((Path(v['application'])/'update-github.php').read_text(),'<?php // new feed')
   self.assertEqual((Path(v['resources'])/'update-release-key.pem').read_text(),'NEW KEY')
   self.assertEqual((app/'update-github.php').read_text(),'<?php // old feed')
   self.assertEqual((Path(v['application'])/'worker.php').read_text(),'<?php // installed worker')
   self.assertEqual((Path(v['resources'])/'update-release-key.pem').stat().st_mode&0o777,0o600)
   (app/'evil.php').symlink_to(app/'worker.php')
   bad=call();self.assertNotEqual(bad.returncode,0)

if __name__=='__main__':unittest.main()
