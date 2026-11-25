"""The generated native bootstrap verifies its own closed data without an installed app."""
import base64,importlib.util,json,os,re,subprocess,tempfile,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.environ.get('PHP_TEST_BINARY'),'Requires matching PHP and OpenSSL')
class NativeInstallBundle(unittest.TestCase):
 def test_upgrade_bridge_seals_more_than_160_files_for_the_installed_loader(self):
  spec=importlib.util.spec_from_file_location('native_install_bridge',ROOT/'openwrt/install-bundle.py')
  bundler=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundler)
  bridge=bundler.bridge()
  stager=re.search(r'=>\s*(NfqwsOpenWrt\w+Runtime)::stage\(',bridge).group(1)
  definitions=bridge[bridge.index('const NFQWS_NATIVE_INSTALL_KEY'):bridge.index('\ntry{\n    if(!NfqwsPlatform::native())')]
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);app=root/'app';app.mkdir();resources=root/'resources';resources.mkdir()
   for name in ['platform.php','update-store.php','openwrt-update-runtime.php',*(f'profile-{index}.php' for index in range(163))]:
    (app/name).write_text('<?php\n')
   (app/'platform-profile.json').write_text('{}')
   (root/'worker.php').write_text('<?php\n')
   for name in ['openwrt-package-manifest.schema.json','update-release-key.pem']:
    (resources/name).write_text('fixture')
   for path in [*app.iterdir(),*resources.iterdir(),root/'worker.php']:
    path.chmod(0o644)
   # The host fixture has no native /usr/bin/php8-cgi. Bind both implementations
   # to the same fixture executable and use its actual owner for both checks.
   owner=os.getuid()
   executable=root/'php8-cgi';executable.write_text('#!/bin/sh\n');executable.chmod(0o755)
   (root/'php-cgi').symlink_to(executable.name)
   def bind_interpreter(source):
    return (source.replace('/usr/bin/php8-cgi',str(executable))
                  .replace('/usr/bin/php-cgi',str(root/'php-cgi'))
                  .replace('self::regular($path,0,16777216)',f'self::regular($path,{owner},16777216)'))
   (root/'bridge.php').write_text('<?php\n'+bind_interpreter(definitions))
   installed=(ROOT/'webui/web/public/openwrt-update-runtime.php').read_text()
   installed=installed.replace("require_once __DIR__.'/update-store.php';\n",'')
   installed=installed.replace('foreach($files as $file)$add(',
                               "if(count($files)>160)throw new RuntimeException('runtime_limit');\n        foreach($files as $file)$add(",1)
   (root/'installed.php').write_text(bind_interpreter(installed))
   setup="""
   require $argv[1].'/update-prepare.php';
   require $argv[2].'/installed.php';
   require $argv[2].'/bridge.php';
   $dir=$argv[2];
   $stager=$argv[3];
   $owner=(int)$argv[4];
   $staged=$stager::stage($dir.'/runtime',[
       'application'=>$dir.'/app','resources'=>$dir.'/resources','entry'=>$dir.'/worker.php'],$owner);
   $loaded=NfqwsOpenWrtUpdateRuntime::load($dir.'/runtime',$owner);
   echo json_encode(['files'=>count($loaded['files']),'matches'=>$staged['digest']===$loaded['digest']]);
   """
   result=subprocess.run([os.environ['PHP_TEST_BINARY'],'-n','-r',setup,
                          str(ROOT/'webui/web/public'),str(root),stager,str(owner)],capture_output=True,text=True,timeout=15)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   self.assertEqual(json.loads(result.stdout),{'files':171,'matches':True})

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
   if container:=os.environ.get('NFQWS_TEST_DOCKER'):
    spec=json.loads(subprocess.check_output(['docker','inspect',container]))[0];self.assertTrue(container.startswith('nfqws-openwrt'));self.assertNotEqual(spec['HostConfig']['NetworkMode'],'host')
    remote='/tmp/native-bundle-'+uuid.uuid4().hex
    subprocess.run(['docker','exec',container,'mkdir','-m','700',remote],check=True,capture_output=True)
    try:
     for name in ['bundle.php','release.json','release.sig']:
      subprocess.run(['docker','cp',str(root/name),container+':'+remote+'/'+name],check=True,capture_output=True)
     p=subprocess.run(['docker','exec',container,'php-cli','-r',code,remote],text=True,capture_output=True,timeout=15)
     self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');self.assertEqual(json.loads(p.stdout),['install','invalid_signature'])
    finally:subprocess.run(['docker','exec',container,'rm','-rf',remote],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
