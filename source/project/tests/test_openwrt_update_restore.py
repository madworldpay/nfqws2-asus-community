"""Exercise production restore against fixed native init paths in isolated rootfs."""
import json,os,shlex,subprocess,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];CONTAINER=os.environ.get('NFQWS_TEST_DOCKER')
@unittest.skipUnless(CONTAINER,'Requires isolated native rootfs')
class NativeRestore(unittest.TestCase):
 def sh(self,code,input=None):
  p=subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',code],input=input,text=True,capture_output=True,timeout=25);self.assertEqual(p.returncode,0,p.stdout+p.stderr);return p.stdout
 def case(self,mode,fail=False):
  self.assertTrue(CONTAINER.startswith('nfqws-openwrt'));self.assertNotEqual(json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]['HostConfig']['NetworkMode'],'host')
  base='/tmp/native-restore-'+uuid.uuid4().hex
  core='/usr/lib/nfqws2/nfqws2-native';web='/usr/lib/nfqws2-web/nfqws2-native-web'
  self.sh('test ! -e '+core+'; test ! -e '+web+'; umask 077; mkdir -p '+base+'/app /usr/lib/nfqws2 /usr/lib/nfqws2-web; cp '+shlex.quote(str(ROOT/'webui/web/public'))+'/*.php '+base+'/app/; chmod 644 '+base+'/app/*.php')
  self.addCleanup(lambda:self.sh('rm -f '+core+' '+web+' /etc/init.d/nfqws2-native /etc/init.d/nfqws2-native-web; rm -rf '+base))
  self.sh('cat > '+base+'/app/platform-profile.json','{"schema_version":1,"platform":"openwrt"}')
  state={'process_running':True,'nfqueue':{'state':'bound'},'capture':'active'}
  self.sh('cat > '+base+'/state',json.dumps(state))
  # Only the diagnostics boundary is inert; production service ownership,
  # native process execution and restore decision logic are exercised.
  stub='<?php final class NfqwsOpenWrtWeb { public static function diagnostics():array { return json_decode(file_get_contents('+json.dumps(base+'/state')+'),true); } }'
  self.sh('cat > '+base+'/app/openwrt-web.php',stub)
  core_script='#!/bin/sh\nprintf "%s\\n" "$1" >> '+base+'/calls\ncase "$1" in\nstop) '+('exit 1'if fail else 'printf %s '+shlex.quote(json.dumps({'process_running':False,'nfqueue':{'state':'unbound'},'capture':'stopped'}))+' > '+base+'/state')+';;\nstart) printf %s '+shlex.quote(json.dumps(state))+' > '+base+'/state;;\nenable|disable) :;;\n*) exit 1;;\nesac\n'
  self.sh('cat > '+core,core_script);self.sh('cat > '+web,'#!/bin/sh\nexit 0\n');self.sh('chmod 755 '+core+' '+web+'; ln -s '+core+' /etc/init.d/nfqws2-native; ln -s '+web+' /etc/init.d/nfqws2-native-web')
  script='<?php require '+json.dumps(base+'/app/openwrt-update-worker.php')+';$s=new AsusUpdateStore('+json.dumps(base+'/store')+');$w=new NfqwsOpenWrtUpdateWorker($s);$m=new ReflectionMethod($w,"restore");try{$v=$m->invoke($w,json_decode('+json.dumps(json.dumps({'mode':mode,'enabled':mode!='stopped','web_enabled':False,'web_running':False}))+',true));echo json_encode(["result"=>$v]);}catch(Throwable $e){echo json_encode(["error"=>$e->getMessage()]);}'
  self.sh('cat > '+base+'/restore.php',script);v=json.loads(self.sh('php-cli '+base+'/restore.php'));v['calls']=self.sh('cat '+base+'/calls').splitlines();return v
 def test_running_intent_rearms_capture_instead_of_trusting_stale_bound_marker(self):
  self.assertEqual(self.case('running'),{'result':'running','calls':['enable','stop','start']})
 def test_original_off_stops_unexpected_owned_runtime_without_starting(self):
  self.assertEqual(self.case('stopped'),{'result':'stopped','calls':['disable','stop']})
 def test_failed_stop_is_reported_and_never_falls_through_to_start(self):
  self.assertEqual(self.case('running',True),{'error':'core_stop_failed','calls':['enable','stop']})
if __name__=='__main__':unittest.main()
