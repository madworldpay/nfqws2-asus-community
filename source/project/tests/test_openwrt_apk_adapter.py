"""The installed APK gate vetoes own file replacement, without touching other packages."""
import json,os,shlex,subprocess,tempfile,unittest,uuid
from pathlib import Path
from test_openwrt_update_package import ROOT,APK_CONTAINER,APK_TOOL
@unittest.skipUnless(APK_CONTAINER and APK_TOOL,'Requires isolated native25 and official SDK APK')
class NativeApkAdapter(unittest.TestCase):
 def sh(self,code,input=None,check=True):
  p=subprocess.run(['docker','exec','-i',APK_CONTAINER,'sh','-c',code],input=input,text=True,capture_output=True,timeout=30)
  if check:self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  return p
 def setUp(self):
  self.assertTrue((ROOT/'openwrt/update/apk-precommit.php').exists(),'native APK precommit adapter missing')
  spec=json.loads(subprocess.check_output(['docker','inspect',APK_CONTAINER]))[0];self.assertTrue(APK_CONTAINER.startswith('nfqws-openwrt'));self.assertNotEqual(spec['HostConfig']['NetworkMode'],'host')
  self.assertEqual(json.loads(self.sh('apk query --installed --format json --fields name nfqws2-native').stdout),[])
  self.base='/tmp/native-apk-adapter-'+uuid.uuid4().hex;self.hook='/lib/apk/commit_hooks.d/10-nfqws2-native';self.entry='/usr/lib/nfqws2/update/apk-precommit.php';self.quiesce='/usr/lib/nfqws2/update/quiesce.php';self.file='/usr/share/nfqws2/apk-gate-fixture'
  self.sh('test ! -e '+self.hook+'; test ! -e '+self.entry+'; test ! -e '+self.quiesce)
  self.sh('umask 077; mkdir -p '+self.base+'/app '+self.base+'/keys /usr/lib/nfqws2/update /lib/apk/commit_hooks.d; cp '+shlex.quote(str(ROOT/'webui/web/public'))+'/*.php '+self.base+'/app/; chmod 644 '+self.base+'/app/*.php; printf %s '+shlex.quote('{"schema_version":1,"platform":"openwrt"}')+' > '+self.base+'/app/platform-profile.json')
  self.addCleanup(self.cleanup)
  with tempfile.TemporaryDirectory()as td:
   r=Path(td);key=r/'key.pem';pub=r/'pub.pem';subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,capture_output=True);key.chmod(0o600);subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(pub)],check=True,capture_output=True)
   self.sh('cat > '+self.base+'/keys/fixture.pem',pub.read_text())
   sdk=Path(APK_TOOL).parent.parent;env={**os.environ,'STAGING_DIR_HOST':str(sdk),'SOURCE_DATE_EPOCH':'0'};env.pop('LD_PRELOAD',None)
   for package,version in [('nfqws2-native','1.3.2-r71'),('nfqws2-native','1.3.2-r72'),('nfqws-native-unrelated-fixture','1')]:
    files=r/(package+version);leaf=files/self.file.lstrip('/')if package=='nfqws2-native'else files/'usr/share/nfqws2/unrelated-gate-fixture';leaf.parent.mkdir(parents=True);leaf.write_text(version);out=r/(package+version+'.apk')
    args=[str(sdk/'bin/fakeroot'),str(APK_TOOL),'mkpkg','--info','name:'+package,'--info','version:'+version,'--info','arch:x86_64','--info','license:MIT','--info','description:Inert APK callback fixture','--files',str(files),'--output',str(out),'--sign-key',str(key)]
    subprocess.run(args,check=True,env=env,capture_output=True);subprocess.run(['docker','cp',str(out),APK_CONTAINER+':'+self.base+'/'+out.name],check=True,capture_output=True)
  self.command='apk add --network=no --cache=no --repositories-file /dev/null --keys-dir '+self.base+'/keys '
  self.sh(self.command+self.base+'/nfqws2-native1.3.2-r71.apk')
  entry=(ROOT/'openwrt/update/apk-precommit.php').read_text().replace('/usr/share/nfqws2-web',self.base+'/app').replace('new AsusUpdateStore()', 'new AsusUpdateStore('+json.dumps(self.base+'/store')+')')
  self.sh('cat > '+self.entry,entry);self.sh('cat > '+self.hook,(ROOT/'openwrt/update/apk-precommit.sh').read_text());self.sh('chmod 755 '+self.hook+'; chmod 644 '+self.entry)
  leaf='<?php $a=$argv;file_put_contents('+json.dumps(self.base+'/stopped')+',end($a));exit(is_file('+json.dumps(self.base+'/deny')+')?1:0);'
  self.sh('cat > '+self.quiesce,leaf);self.sh('chmod 644 '+self.quiesce)
 def cleanup(self):
  self.sh('rm -f '+self.hook+' '+self.entry+' '+self.quiesce,check=False)
  self.sh('apk del --network=no nfqws2-native >/dev/null 2>&1 || :',check=False)
  self.sh('apk del --network=no nfqws-native-unrelated-fixture >/dev/null 2>&1 || :',check=False)
  self.sh('rm -rf '+self.base,check=False)
 def test_stop_failure_keeps_old_payload_and_version(self):
  self.sh('touch '+self.base+'/deny');p=self.sh(self.command+self.base+'/nfqws2-native1.3.2-r72.apk',check=False)
  self.assertNotEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(self.sh('cat '+self.file).stdout,'1.3.2-r71');self.assertEqual(self.sh('cat '+self.base+'/stopped').stdout,'upgrade')
  self.assertEqual(json.loads(self.sh('apk query --installed --format json --fields version nfqws2-native').stdout)[0]['version'],'1.3.2-r71')
 def test_successful_upgrade_quiesces_before_replace(self):
  self.sh(self.command+self.base+'/nfqws2-native1.3.2-r72.apk');self.assertEqual(self.sh('cat '+self.file).stdout,'1.3.2-r72');self.assertEqual(self.sh('cat '+self.base+'/stopped').stdout,'upgrade')
 def test_remove_failure_keeps_installed_payload(self):
  self.sh('touch '+self.base+'/deny');p=self.sh('apk del --network=no nfqws2-native',check=False);self.assertNotEqual(p.returncode,0);self.assertEqual(self.sh('cat '+self.file).stdout,'1.3.2-r71');self.assertEqual(self.sh('cat '+self.base+'/stopped').stdout,'remove')
 def test_unrelated_package_does_not_call_quiesce(self):
  self.sh('touch '+self.base+'/deny');self.sh(self.command+self.base+'/nfqws-native-unrelated-fixture1.apk');self.sh('test ! -e '+self.base+'/stopped');self.assertEqual(self.sh('cat '+self.file).stdout,'1.3.2-r71')
 def test_direct_http_or_cli_call_cannot_impersonate_native_manager(self):
  p=self.sh('/usr/bin/php8-cgi -d register_argc_argv=1 -q -f '+self.entry,check=False);self.assertNotEqual(p.returncode,0);self.sh('test ! -e '+self.base+'/stopped')
if __name__=='__main__':unittest.main()
