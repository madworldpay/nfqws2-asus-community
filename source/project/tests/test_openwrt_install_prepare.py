"""Native bootstrap checks signed IPK/APK and only reports truly missing prerequisites."""
import base64,hashlib,json,os,shlex,subprocess,tempfile,unittest,uuid
from pathlib import Path
from test_openwrt_update_package import ROOT,builder,CACHE,APK_TOOL
import importlib.util
CONTAINER=os.environ.get('NFQWS_TEST_DOCKER')
@unittest.skipUnless(CONTAINER and CACHE,'Requires isolated native rootfs and official package tools')
class NativeInstallPreparation(unittest.TestCase):
 def sh(self,code,input=None,check=True):
  p=subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',code],input=input,text=True,capture_output=True,timeout=25)
  if check:self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  return p
 def run_case(self,corrupt):
  self.assertTrue((ROOT/'openwrt/install-prepare.php').exists(),'First install needs shared native signature/archive/dependency preparation without an installed panel')
  spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0];self.assertTrue(CONTAINER.startswith('nfqws-openwrt'));self.assertNotEqual(spec['HostConfig']['NetworkMode'],'host')
  fmt='apk'if'25'in CONTAINER else'ipk';series='25.12'if fmt=='apk'else'24.10';version='1.3.2-'+('r'if fmt=='apk'else'')+'72'
  base='/tmp/native-first-prepare-'+uuid.uuid4().hex;self.sh('umask 077; mkdir '+base);self.addCleanup(lambda:self.sh('rm -rf '+base))
  spec=importlib.util.spec_from_file_location('bootstrap_bundle',ROOT/'openwrt/install-bundle.py');bundler=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundler)
  self.sh('cat > '+base+'/bundle.php',bundler.render().decode())
  self.sh('printf %s '+shlex.quote('{"schema_version":1,"platform":"openwrt"}')+' > '+base+'/platform-profile.json; chmod 600 '+base+'/bundle.php '+base+'/platform-profile.json')
  marker=base+'/hook-executed';target=builder.native_metadata(series,'x86_64',72);target['dependencies']=['libc','libgcc','nfqws-bootstrap-absent-fixture']
  with tempfile.TemporaryDirectory()as td:
   root=Path(td);stage=root/'payload';out=root/'out';out.mkdir();key=root/'private.pem';pub=root/'public.pem'
   subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,capture_output=True);key.chmod(0o600);subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(pub)],check=True,capture_output=True)
   hooks={name:('#!/bin/sh\ntouch '+marker+'\n').encode()for name in ['preinst','postinst','prerm','postrm']}
   files={'usr/share/nfqws2/bootstrap-preparation-fixture':(b'inert',0o644)}
   if fmt=='ipk':
    meta='Package: nfqws2-native\nVersion: '+version+'\nArchitecture: x86_64\nDepends: '+', '.join(target['dependencies'])+'\nDescription: Inert bootstrap fixture\n'
    files|={'CONTROL/control':(meta.encode(),0o644),**{'CONTROL/'+name:(body,0o755)for name,body in hooks.items()}};builder.write_files(stage,files);tool=builder.pinned_asset(builder.ASSETS['ipkg_build'],CACHE,True);subprocess.run(['fakeroot','sh',str(tool),str(stage),str(out)],check=True,capture_output=True);pkg=next(out.glob('*.ipk'))
   else:
    self.assertTrue(APK_TOOL,'Requires official native APK SDK');builder.write_files(stage,files);pkg=builder.build_apk(target,stage,hooks,CACHE,out,True,key)
   rec={'series':series,'arch':'x86_64','format':fmt,'version':version,'filename':pkg.name,'size':pkg.stat().st_size,'installed_size':1048576,'sha256':hashlib.sha256(pkg.read_bytes()).hexdigest()}
   raw=json.dumps({'schema_version':1,'platform':'openwrt','package':'nfqws2-native','core_version':'1.3.2','web_version':'0.1.4','build':72,'notes':'Fixture','packages':[rec]},separators=(',',':')).encode();sig=subprocess.run(['openssl','dgst','-sha256','-sign',str(key)],input=raw,capture_output=True,check=True).stdout
   self.sh('cat > '+base+'/manifest.json',raw.decode());self.sh('cat > '+base+'/manifest.sig',base64.b64encode(sig).decode())
   for local,name in [(pkg,'source.package'),(pub,'public.pem')]:subprocess.run(['docker','cp',str(local),CONTAINER+':'+base+'/'+name],check=True,capture_output=True)
  code='''require $argv[1];$base=$argv[2];class BootstrapFixtureSource implements AsusUpdateSource{function __construct(public string $p,public bool $bad){}function manifest():array{return ['json'=>file_get_contents($this->p.'/manifest.json'),'signature'=>file_get_contents($this->p.'/manifest.sig')];}function download(array $p,string $dest):void{copy($this->p.'/source.package',$dest);chmod($dest,0600);if($this->bad){$raw=file_get_contents($dest);$raw[10]=chr(ord($raw[10])^1);file_put_contents($dest,$raw);}}}
$e=NfqwsOpenWrtUpdateEnvironment::firmware(file_get_contents('/etc/openwrt_release'));$before=NfqwsOpenWrtUpdateManager::raw($e);try{$r=(new NfqwsOpenWrtInstallPrepare($base.'/work',new BootstrapFixtureSource($base,$argv[3]==='bad'),file_get_contents($base.'/public.pem'),$argv[4]))->run();$out=['action'=>$r['action'],'format'=>$r['firmware']['format'],'missing'=>$r['missing']];}catch(RuntimeException $ex){$out=['error'=>$ex->getMessage()];}if($before!==NfqwsOpenWrtUpdateManager::raw($e))throw new RuntimeException('bootstrap preparation changed package database');echo json_encode($out);'''
  command='php-cli -r '+shlex.quote(code)+' '+shlex.quote(base+'/bundle.php')+' '+base+' '+('bad'if corrupt else'ok')+' '+shlex.quote(str(ROOT/'updates/openwrt-package-manifest.schema.json'))
  result=self.sh(command);self.sh('test ! -e '+marker);return json.loads(result.stdout)
 def test_first_install_prepares_without_hooks_or_package_mutations_and_resolves_native_virtual_providers(self):
  self.assertEqual(self.run_case(False),{'action':'install','format':'apk'if'25'in CONTAINER else'ipk','missing':['nfqws-bootstrap-absent-fixture']})
 def test_corrupted_download_never_reaches_native_hooks(self):
  self.assertEqual(self.run_case(True),{'error':'download_hash'})
if __name__=='__main__':unittest.main()
