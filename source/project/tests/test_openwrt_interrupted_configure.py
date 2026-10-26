"""An actual OPKG configure retry keeps the interrupted transaction's service intent."""
import json,os,shlex,subprocess,tempfile,unittest,uuid
from pathlib import Path
from test_openwrt_update_package import ROOT,builder,CACHE
CONTAINER=os.environ.get('NFQWS_TEST_DOCKER24')or(os.environ.get('NFQWS_TEST_DOCKER')if'24'in os.environ.get('NFQWS_TEST_DOCKER','')else None)
@unittest.skipUnless(CONTAINER and CACHE,'Requires isolated native24 with official IPK tool')
class InterruptedNativeConfigure(unittest.TestCase):
 def sh(self,code,check=True):
  p=subprocess.run(['docker','exec',CONTAINER,'sh','-c',code],capture_output=True,text=True,timeout=25)
  if check:self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  return p
 def test_configure_retry_rebinds_dead_manager_and_restores_saved_running_intent(self):
  spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0];self.assertTrue(CONTAINER.startswith('nfqws-openwrt'));self.assertNotEqual(spec['HostConfig']['NetworkMode'],'host')
  self.assertNotIn('nfqws2-native - ',self.sh('opkg list-installed').stdout)
  base='/tmp/native-configure-'+uuid.uuid4().hex
  self.sh('umask 077; mkdir -p '+base+'/init '+base+'/state')
  self.addCleanup(lambda:self.sh('opkg remove nfqws2-native >/dev/null 2>&1 || :; rm -rf '+base,check=False))
  with tempfile.TemporaryDirectory()as td:
   r=Path(td);stage=r/'payload';out=r/'out';out.mkdir()
   library=(ROOT/'openwrt/package-lifecycle.sh').read_text().split('case "$NFQWS_PKG_ACTION" in')[0].replace('/etc/init.d/',base+'/init/')
   common='#!/bin/sh\numask 077\nNFQWS_PKG_FORMAT=ipk\n'+library+'\nnfqws_package_state_dir='+base+'/state\n'
   pre=common+'nfqws_package_service_state() { printf "enabled=1\\nrunning=1\\nweb_present=1\\nweb_enabled=1\\nweb_running=1\\n"; }\nnfqws_package_snapshot\n'
   post=common+'[ -f '+base+'/retry ] || exit 1\nnfqws_package_service() { '+base+'/init/$1 "$2"; }\nnfqws_package_defaults() { return 0; }\nnfqws_package_native_update() { [ "$1" != postinstall ] || return 10; }\nuci() { case "$*" in "-q get firewall.nfqws2_native.path") echo /usr/lib/nfqws2/firewall-hook.sh;; "-q get firewall.nfqws2_native") echo include;; *) return 1;; esac; }\nnfqws_package_postinstall\n'
   files={'CONTROL/control':(b'Package: nfqws2-native\nVersion: 1.3.2-72\nArchitecture: x86_64\nDescription: Inert interrupted configure fixture\n',0o644),'CONTROL/preinst':(pre.encode(),0o755),'CONTROL/postinst':(post.encode(),0o755),'usr/share/nfqws2/configure-fixture':(b'inert',0o644)}
   for name in ['nfqws2-native','nfqws2-native-web','nfqws2-native-dns','nfqws2-native-dns-resume']:
    f=r/name;f.write_text('#!/bin/sh\nprintf "%s:%s\\n" '+name+' "$1" >> '+base+'/calls\n');f.chmod(0o755);subprocess.run(['docker','cp',str(f),CONTAINER+':'+base+'/init/'+name],check=True,capture_output=True)
   builder.write_files(stage,files);tool=builder.pinned_asset(builder.ASSETS['ipkg_build'],CACHE,True);subprocess.run(['fakeroot','sh',str(tool),str(stage),str(out)],check=True,capture_output=True);subprocess.run(['docker','cp',str(next(out.glob('*.ipk'))),CONTAINER+':'+base+'/package.ipk'],check=True,capture_output=True)
  first=self.sh('opkg --nodeps install '+base+'/package.ipk',check=False);self.assertNotEqual(first.returncode,0)
  self.assertIn('unpacked',self.sh('opkg status nfqws2-native').stdout);self.sh('test -f '+base+'/state/state; touch '+base+'/retry')
  # The bootstrap may verify healthy system providers while repairing only
  # our known unfinished row; the normal updater keeps its strict default.
  code='require $argv[1];$e=["format"=>"ipk"];$db=NfqwsOpenWrtUpdateManager::installed($e,true);$a=NfqwsOpenWrtUpdateManager::argv($argv[2],$e,$db,["name"=>"nfqws2-native","depends"=>["libgcc"]],null,true,true);echo json_encode($a);'
  checked=self.sh('php-cli -r '+shlex.quote(code)+' '+shlex.quote(str(ROOT/'webui/web/public/openwrt-update-manager.php'))+' '+base+'/package.ipk',check=False)
  self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr);self.assertEqual(json.loads(checked.stdout),['/bin/opkg','--nodeps','--noaction','install',base+'/package.ipk'])
  retry=self.sh('opkg configure nfqws2-native',check=False);self.assertEqual(retry.returncode,0,retry.stdout+retry.stderr)
  self.assertIn('install user installed',self.sh('opkg status nfqws2-native').stdout)
  self.assertIn('nfqws2-native:start',self.sh('cat '+base+'/calls').stdout);self.assertIn('nfqws2-native-web:start',self.sh('cat '+base+'/calls').stdout)
  self.sh('test ! -e '+base+'/state/state')
if __name__=='__main__':unittest.main()
