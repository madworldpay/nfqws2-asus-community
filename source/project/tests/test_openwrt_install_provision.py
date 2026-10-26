"""Install missing prerequisites from a real signed, isolated native repository."""
import gzip,hashlib,json,os,shlex,subprocess,tempfile,unittest,uuid
from pathlib import Path
from test_openwrt_update_package import ROOT,builder,CACHE,APK_TOOL
C=os.environ.get('NFQWS_TEST_DOCKER')
@unittest.skipUnless(C and CACHE,'Requires isolated official OpenWrt and verified package tools')
class NativePrerequisites(unittest.TestCase):
 def sh(self,code,stdin=None,check=True):
  p=subprocess.run(['docker','exec','-i',C,'sh','-c',code],input=stdin,text=True,capture_output=True,timeout=30)
  if check:self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  return p
 def test_only_missing_signed_prerequisite_is_installed_without_changing_existing_versions(self):
  info=json.loads(subprocess.check_output(['docker','inspect',C]))[0];self.assertTrue(C.startswith('nfqws-openwrt'));self.assertNotEqual(info['HostConfig']['NetworkMode'],'host')
  apk='25'in C;fmt='apk'if apk else'ipk';base='/tmp/native-prereq-'+uuid.uuid4().hex;name='nfqws-bootstrap-prereq';version='1.0.0-'+('r'if apk else'')+'1'
  self.sh('umask 077; mkdir '+base+'; mkdir '+base+'/repo '+base+'/work')
  original=self.sh('cat '+('/etc/apk/repositories.d/distfeeds.list'if apk else'/etc/opkg/distfeeds.conf')).stdout
  before=self.sh('apk list --installed'if apk else"opkg list-installed").stdout
  installed=False;opkg_key=None
  try:
   with tempfile.TemporaryDirectory()as td:
    root=Path(td);stage=root/'stage';out=root/'out';out.mkdir();builder.write_files(stage,{'usr/share/nfqws2-bootstrap-prereq':(b'inert signed fixture',0o644)})
    if apk:
     self.assertTrue(APK_TOOL);key=root/'private.pem';pub=root/'public.pem';subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,capture_output=True);key.chmod(0o600);subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(pub)],check=True,capture_output=True)
     pkg=out/(name+'-'+version+'.apk');subprocess.run([APK_TOOL,'mkpkg','--info','name:'+name,'--info','version:'+version,'--info','arch:x86_64','--info','description:Inert prerequisite fixture','--files',str(stage),'--output',str(pkg),'--sign-key',str(key)],check=True,capture_output=True)
     keys=root/'keys';keys.mkdir();(keys/'fixture.pem').write_bytes(pub.read_bytes());index=out/'packages.adb';r=subprocess.run([APK_TOOL,'mkndx','--keys-dir',str(keys),'--sign-key',str(key),'--output',str(index),str(pkg)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
     for local,dest in [(pkg,base+'/repo/'+pkg.name),(index,base+'/repo/packages.adb'),(pub,'/etc/apk/keys/nfqws-bootstrap-fixture.pem')]:subprocess.run(['docker','cp',str(local),C+':'+dest],check=True,capture_output=True)
     self.sh('cat > /etc/apk/repositories.d/distfeeds.list','file://'+base+'/repo/packages.adb\n')
    else:
     control='Package: '+name+'\nVersion: '+version+'\nArchitecture: x86_64\nDescription: Inert prerequisite fixture\n'
     builder.write_files(stage,{'CONTROL/control':(control.encode(),0o644)})
     tool=builder.pinned_asset(builder.ASSETS['ipkg_build'],CACHE,True);subprocess.run(['fakeroot','sh',str(tool),str(stage),str(out)],check=True,capture_output=True);pkg=next(out.glob('*.ipk'))
     raw=control+'Filename: '+pkg.name+'\nSize: '+str(pkg.stat().st_size)+'\nSHA256sum: '+hashlib.sha256(pkg.read_bytes()).hexdigest()+'\n\n';(out/'Packages').write_text(raw);(out/'Packages.gz').write_bytes(gzip.compress(raw.encode()))
     for local in [pkg,out/'Packages',out/'Packages.gz']:subprocess.run(['docker','cp',str(local),C+':'+base+'/repo/'+local.name],check=True,capture_output=True)
     self.sh('usign -G -s '+base+'/private -p '+base+'/public; usign -S -s '+base+'/private -m '+base+'/repo/Packages -x '+base+'/repo/Packages.sig')
     opkg_key=self.sh('usign -F -p '+base+'/public').stdout.strip();self.assertRegex(opkg_key,r'^[a-f0-9]{16}$');self.sh('cp '+base+'/public /etc/opkg/keys/'+opkg_key)
     self.sh('cat > /etc/opkg/distfeeds.conf','src/gz nfqws_bootstrap_fixture file://'+base+'/repo\n')
    source=(ROOT/'openwrt/install-shell.sh').read_text()+'\n'+(ROOT/'openwrt/install-entry.sh').read_text()
    code=source+'\nNFQWS_NATIVE_WORK='+base+'/work\nNFQWS_NATIVE_FORMAT='+fmt+'\nNFQWS_NATIVE_DB='+('/lib/apk/db/installed'if apk else'/usr/lib/opkg/status')+'\nnfqws_native_provision '+name+'\n'
    self.sh('cat > '+base+'/run.sh',code);p=self.sh('sh '+base+'/run.sh',check=False)
    if p.returncode:self.fail(p.stdout+p.stderr+self.sh('cat '+base+'/work/job.log '+base+'/work/provision.plan 2>/dev/null',check=False).stdout)
    installed=True;self.sh('test -f /usr/share/nfqws2-bootstrap-prereq')
    after=self.sh('apk list --installed'if apk else'opkg list-installed').stdout
    filtered='\n'.join(line for line in after.splitlines()if not line.startswith(name+' 'if not apk else name+'-'))+'\n'
    self.assertEqual(filtered,before)
  finally:
   # This modifies only the isolated container, restores its original feed text
   # and removes only this signed inert fixture through its native manager.
   if installed:self.sh(('apk del 'if apk else'opkg remove ')+name)
   self.sh('cat > '+('/etc/apk/repositories.d/distfeeds.list'if apk else'/etc/opkg/distfeeds.conf'),original)
   self.sh('rm -f '+('/etc/apk/keys/nfqws-bootstrap-fixture.pem'if apk else('/etc/opkg/keys/'+opkg_key if opkg_key else base+'/absent-key')))
   self.sh('rm -rf '+base)
if __name__=='__main__':unittest.main()
