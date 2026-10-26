"""The generated native bootstrap verifies its own closed data without an installed app."""
import base64,importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.environ.get('PHP_TEST_BINARY'),'Requires matching PHP and OpenSSL')
class NativeInstallBundle(unittest.TestCase):
 def test_standalone_bundle_verifies_signature_target_and_tamper_without_source_tree(self):
  module=ROOT/'openwrt/install-bundle.py';self.assertTrue(module.exists(),'Native bootstrap must carry a deterministic standalone trusted verifier')
  spec=importlib.util.spec_from_file_location('native_install_bundle',module);bundler=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundler)
  with tempfile.TemporaryDirectory()as td:
   root=Path(td);key=root/'private.pem';public=root/'public.pem'
   subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,capture_output=True);key.chmod(0o600);subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(public)],check=True,capture_output=True)
   bundle=bundler.render(public.read_bytes());self.assertEqual(bundle,bundler.render(public.read_bytes()));(root/'bundle.php').write_bytes(bundle)
   record={'series':'24.10','arch':'arm_cortex-a9','format':'ipk','version':'1.3.2-72','filename':'nfqws2-native_1.3.2-72_arm_cortex-a9.ipk','size':1024,'installed_size':2048,'sha256':'a'*64}
   raw=json.dumps({'schema_version':1,'platform':'openwrt','package':'nfqws2-native','core_version':'1.3.2','web_version':'0.1.4','build':72,'notes':'Fixture','packages':[record]},separators=(',',':')).encode();signature=subprocess.run(['openssl','dgst','-sha256','-sign',str(key)],input=raw,capture_output=True,check=True).stdout
   (root/'release.json').write_bytes(raw);(root/'release.sig').write_bytes(base64.b64encode(signature))
   code='require $argv[1]."/bundle.php";file_put_contents($argv[1]."/schema.json",NFQWS_NATIVE_INSTALL_SCHEMA);$release="DISTRIB_RELEASE=\x2724.10.8\x27\\nDISTRIB_ARCH=\x27arm_cortex-a9\x27\\nDISTRIB_TARGET=\x27bcm53xx/generic\x27\\n";foreach([false,true]as $tamper){try{$r=NfqwsOpenWrtInstallPlan::select(file_get_contents($argv[1]."/release.json").($tamper?" ":""),file_get_contents($argv[1]."/release.sig"),NFQWS_NATIVE_INSTALL_KEY,$release,null,$argv[1]."/schema.json");$out[]=$r["action"];}catch(RuntimeException $e){$out[]=$e->getMessage();}}echo json_encode($out);'
   r=subprocess.run([os.environ['PHP_TEST_BINARY'],'-n','-r',code,str(root)],cwd=root,text=True,capture_output=True,timeout=15)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');self.assertEqual(json.loads(r.stdout),['install','invalid_signature'])
if __name__=='__main__':unittest.main()
