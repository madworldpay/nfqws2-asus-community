"""Production native worker with real OPKG transactions and isolated service boundaries."""
import json,os,shlex,subprocess,tempfile,unittest,uuid
from pathlib import Path
from test_openwrt_update_package import ROOT,builder,CACHE,APK_TOOL
CONTAINER=os.environ.get('NFQWS_TEST_DOCKER')
@unittest.skipUnless(CONTAINER and CACHE,'Requires isolated24 native PHP and official IPK tool')
class NativeUpdateWorker(unittest.TestCase):
 def sh(self,code,input=None,check=True):
  p=subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',code],input=input,text=True,capture_output=True,timeout=40)
  if check:self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  return p.stdout
 def run_case(self,case,mode='running'):
  self.assertTrue((ROOT/'webui/web/public/openwrt-update-worker.php').exists(),'production native apply worker missing')
  fmt='apk'if'25'in CONTAINER else'ipk';series='25.12'if fmt=='apk'else'24.10';v=lambda n:'1.3.2-'+('r'if fmt=='apk'else'')+str(n)
  self.assertTrue(CONTAINER.startswith('nfqws-openwrt'));self.assertNotEqual(json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]['HostConfig']['NetworkMode'],'host')
  self.assertNotIn('nfqws2-native - ',self.sh('opkg list-installed'))if fmt=='ipk'else self.assertEqual(json.loads(self.sh('apk query --installed --format json --fields name nfqws2-native')),[]);self.sh('test ! -e /usr/share/nfqws2/platform.json')
  base='/tmp/native-apply-'+uuid.uuid4().hex;self.addCleanup(lambda:self.sh(('opkg remove'if fmt=='ipk'else'apk del --network=no')+' nfqws2-native >/dev/null 2>&1; if [ -f /usr/share/nfqws2/worker-fixture ]; then case "$(cat /usr/share/nfqws2/worker-fixture)" in 71|72) rm -f /usr/share/nfqws2/worker-fixture /usr/share/nfqws2/platform.json;; esac; fi; rm -rf '+base,check=False))
  self.sh('umask 077; mkdir -p '+base+'/source/app '+base+'/source/resources '+base+'/system/etc/nfqws2; printf %s latest-settings > '+base+'/system/etc/nfqws2/nfqws2.conf; cp '+shlex.quote(str(ROOT/'webui/web/public'))+'/*.php '+base+'/source/app/; chmod 644 '+base+'/source/app/*.php')
  self.sh('printf %s '+shlex.quote('{"schema_version":1,"platform":"openwrt"}')+' > '+base+'/source/app/platform-profile.json; printf %s '+case+' > '+base+'/case')
  intent={'mode':mode,'enabled':mode!='stopped','web_enabled':True,'web_running':True};self.sh('cat > '+base+'/intent.json',json.dumps(intent))
  self.sh('cp '+shlex.quote(str(ROOT/'updates/openwrt-package-manifest.schema.json'))+' '+base+'/source/resources/openwrt-package-manifest.schema.json')
  worker='''<?php
require __DIR__.'/app/openwrt-update-worker.php';$s=new AsusUpdateStore(dirname(__DIR__,3));$id=basename(dirname(__DIR__));$base=dirname(__DIR__,4);$mode=$argv[count($argv)-2];
if($mode==='hook-apk-precommit'){require __DIR__.'/app/openwrt-package-quiesce.php';(new NfqwsOpenWrtPackageQuiesce($s))->run('upgrade');exit(0);}
if(str_starts_with($mode,'hook-')){try{$active=(new NfqwsOpenWrtUpdateHook($s,['root'=>$base.'/system','journal'=>$base.'/pkgstate/state']))->run(substr($mode,5));exit($mode==='hook-postinstall'&&!$active?10:0);}catch(Throwable $e){file_put_contents($base.'/hook-error',$e->getMessage());exit(1);}}
class WorkerFixtureSource implements AsusUpdateSource{public function __construct(public string $p){}public function manifest():array{return ['json'=>file_get_contents($this->p.'/manifest.json'),'signature'=>file_get_contents($this->p.'/manifest.sig')];}public function download(array $p,string $destination):void{copy($this->p.'/update.ipk',$destination);chmod($destination,0600);}}
$env=['platform'=>'openwrt','series'=>'24.10','arch'=>'x86_64','format'=>'ipk','installed'=>'1.3.2-71','build'=>71,'root'=>$base.'/system','resources'=>__DIR__.'/resources','ram_free'=>1000000000,'overlay_free'=>1000000000];$prepare=new NfqwsOpenWrtUpdatePrepare($s,new WorkerFixtureSource($base),$env,file_get_contents(__DIR__.'/resources/update-release-key.pem'));
$services=['root'=>$base.'/system','intent'=>fn()=>json_decode(file_get_contents($base.'/intent.json'),true),'restore'=>function($intent)use($base){file_put_contents($base.'/restored',json_encode($intent));return $intent['mode'];},'dns_resume'=>function()use($base){file_put_contents($base.'/dns-resumed','resumed');return ['state'=>'confirmed'];},'web_health'=>fn()=>true];
echo json_encode((new NfqwsOpenWrtUpdateWorker($s,$prepare,$services))->apply($id));
'''
  if fmt=='apk':worker=worker.replace("'series'=>'24.10'","'series'=>'25.12'").replace("'format'=>'ipk'","'format'=>'apk'").replace('1.3.2-71','1.3.2-r71').replace('update.ipk','update.apk')
  self.sh('cat > '+base+'/source/worker.php',worker)
  with tempfile.TemporaryDirectory()as td:
   root=Path(td);out=root/'out';out.mkdir();key=root/'key.pem';pub=root/'pub.pem'
   subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,capture_output=True);key.chmod(0o600);subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(pub)],check=True,capture_output=True)
   for src,dest in [(key,'private.pem'),(pub,'public.pem')]:subprocess.run(['docker','cp',str(src),CONTAINER+':'+base+'/'+dest],check=True,capture_output=True)
   self.sh('chmod 600 '+base+'/private.pem '+base+'/public.pem')
   tool=builder.pinned_asset(builder.ASSETS['ipkg_build'],CACHE,True)if fmt=='ipk'else None
   library=(ROOT/'openwrt/package-lifecycle.sh').read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
   hook='#!/bin/sh\numask 077\nNFQWS_PKG_FORMAT='+fmt+'\n'+library+'\nnfqws_package_updates_dir='+base+'/store\nnfqws_package_state_dir='+base+'/pkgstate\n'
   pre=hook+'\nnfqws_package_service_state() { printf "enabled='+('1'if mode!='stopped'else'0')+'\\nrunning='+('1'if mode!='stopped'else'0')+'\\nweb_present=1\\nweb_enabled=1\\nweb_running=1\\n"; }\nnfqws_package_service_owner() { return 0; }\nnfqws_package_dns_control() { return 0; }\nnfqws_package_service() { return 0; }\nnfqws_package_snapshot && nfqws_package_stop_services_internal upgrade || exit 1\n'
   if case=='before-write-settings':pre+='printf %s changed-by-hook > '+base+'/system/etc/nfqws2/nfqws2.conf\n'
   if case in ['before-write','before-write-settings']:pre+='exit 1\n'
   post=hook+'\nnfqws_package_native_update postinstall || exit 1\n'
   if case=='after-write':post+='exit 1\n'
   if case=='settings-changed':post+='printf %s changed-by-hook > '+base+'/system/etc/nfqws2/nfqws2.conf\n'
   for version in [71,72]:
    stage=root/str(version);profile=builder.native_metadata(series,'x86_64',version);profile={k:profile[k]for k in ['series','arch','engine','format','version','application_build']}|{'platform':'openwrt'}
    files={'usr/share/nfqws2/platform.json':(json.dumps(profile).encode(),0o644),'usr/share/nfqws2/worker-fixture':(str(version).encode(),0o644)}
    if fmt=='ipk':
     files['CONTROL/control']=(f'Package: nfqws2-native\nVersion: {v(version)}\nArchitecture: x86_64\nDescription: Inert native worker fixture\n'.encode(),0o644)
     if version==72:files|={'CONTROL/preinst':(pre.encode(),0o755),'CONTROL/postinst':(post.encode(),0o755)}
     builder.write_files(stage,files);subprocess.run(['fakeroot','sh',str(tool),str(stage),str(out)],check=True,capture_output=True);pkg=next(out.glob('*-'+str(version)+'_*.ipk'))
    else:
     self.assertTrue(APK_TOOL,'Requires official native APK SDK')
     files['usr/lib/nfqws2/update/quiesce.sh']=(pre.encode(),0o755)
     names=['/'+name for name in files]+['/lib/apk/packages/nfqws2-native.list'];files['lib/apk/packages/nfqws2-native.list']=(('\n'.join(names)+'\n').encode(),0o644);builder.write_files(stage,files)
     sdk=Path(APK_TOOL).parent.parent;env={**os.environ,'STAGING_DIR_HOST':str(sdk),'SOURCE_DATE_EPOCH':'0'};env.pop('LD_PRELOAD',None);pkg=out/('nfqws-'+str(version)+'.apk')
     args=[str(sdk/'bin/fakeroot'),str(APK_TOOL),'mkpkg','--info','name:nfqws2-native','--info','version:'+v(version),'--info','arch:x86_64','--info','license:MIT','--info','description:Inert native worker fixture','--files',str(stage),'--output',str(pkg),'--sign-key',str(key)]
     if version==72:
      for name,content in [('pre-upgrade',pre),('post-upgrade',post)]:
       script=root/name;script.write_text(content);args+=['--script',name+':'+str(script)]
     subprocess.run(args,check=True,env=env,capture_output=True)
    subprocess.run(['docker','cp',str(pkg),CONTAINER+':'+base+('/old.'+fmt if version==71 else'/update.'+fmt)],check=True,capture_output=True)
  if fmt=='ipk':self.sh('opkg --nodeps install '+base+'/old.ipk; chmod 600 '+base+'/update.ipk')
  else:self.sh('mkdir -m 700 '+base+'/keys; cp '+base+'/public.pem '+base+'/keys/fixture.pem; apk add --network=no --cache=no --repositories-file /dev/null --keys-dir '+base+'/keys '+base+'/old.apk; chmod 600 '+base+'/update.apk')
  setup='''<?php
$p=$argv[1];require $p.'/source/app/openwrt-update-prepare.php';require $p.'/source/app/openwrt-update-runtime.php';$s=new AsusUpdateStore($p.'/store');
$key=openssl_pkey_get_private(file_get_contents($p.'/private.pem'));$public=file_get_contents($p.'/public.pem');file_put_contents($p.'/source/resources/update-release-key.pem',$public);
$record=['series'=>'24.10','arch'=>'x86_64','format'=>'ipk','version'=>'1.3.2-72','filename'=>'nfqws2-native_1.3.2-72_x86_64.ipk','size'=>filesize($p.'/update.ipk'),'installed_size'=>1048576,'sha256'=>hash_file('sha256',$p.'/update.ipk')];$raw=json_encode(['schema_version'=>1,'platform'=>'openwrt','package'=>'nfqws2-native','core_version'=>'1.3.2','web_version'=>'0.1.4','build'=>72,'notes'=>'Fixture update','packages'=>[$record]]);openssl_sign($raw,$sig,$key,OPENSSL_ALGO_SHA256);file_put_contents($p.'/manifest.json',$raw);file_put_contents($p.'/manifest.sig',base64_encode($sig));
class SetupSource implements AsusUpdateSource{function __construct(public string $p){}function manifest():array{return ['json'=>file_get_contents($this->p.'/manifest.json'),'signature'=>file_get_contents($this->p.'/manifest.sig')];}function download(array $p,string $destination):void{copy($this->p.'/update.ipk',$destination);chmod($destination,0600);}}
$env=['platform'=>'openwrt','series'=>'24.10','arch'=>'x86_64','format'=>'ipk','installed'=>'1.3.2-71','build'=>71,'root'=>$p.'/system','resources'=>$p.'/source/resources','ram_free'=>1000000000,'overlay_free'=>1000000000];$prepare=new NfqwsOpenWrtUpdatePrepare($s,new SetupSource($p),$env,$public);$check=$prepare->check(true);if($check['state']!=='available')throw new RuntimeException(json_encode($check));$j=$prepare->reserveCached($check['candidate']['revision'],str_repeat('a',32));$j=$prepare->completePrepare($j['id'],fn($id)=>NfqwsOpenWrtUpdateRuntime::stage($s->path('operations/'.$id.'/runtime'),['application'=>$p.'/source/app','resources'=>$p.'/source/resources','entry'=>$p.'/source/worker.php']));if($j['state']!=='prepared')throw new RuntimeException(json_encode($j));$s->claimApply($j['id'],$j['revision'],str_repeat('b',32));echo $j['id'];
'''
  if fmt=='apk':setup=setup.replace("'series'=>'24.10'","'series'=>'25.12'").replace("'format'=>'ipk'","'format'=>'apk'").replace('1.3.2-71','1.3.2-r71').replace('1.3.2-72','1.3.2-r72').replace('update.ipk','update.apk').replace('nfqws2-native_1.3.2-r72_x86_64.ipk','nfqws2-native_1.3.2-r72_x86_64.apk')
  self.sh('cat > '+base+'/setup.php',setup);ident=self.sh('php-cli '+base+'/setup.php '+base).strip()
  result=json.loads(self.sh(base+'/store/operations/'+ident+'/runtime/run.sh apply '+ident));result['restore']=json.loads(self.sh('cat '+base+'/restored'))if self.sh('test -f '+base+'/restored; echo $?').strip()=='0'else None;result['dns_resumed']=self.sh('test -f '+base+'/dns-resumed; echo $?').strip()=='0';result['manager_log']=self.sh('cat '+base+'/store/operations/'+ident+'/manager.log 2>/dev/null',check=False);result['hook_error']=self.sh('cat '+base+'/hook-error 2>/dev/null',check=False);result['native_record']=self.sh('opkg status nfqws2-native'if fmt=='ipk'else'apk query --installed --format json nfqws2-native',check=False);result['payload']=self.sh('cat /usr/share/nfqws2/worker-fixture');result['config']=self.sh('cat '+base+'/system/etc/nfqws2/nfqws2.conf');return result
 def test_real_native_upgrade_verifies_version_settings_and_running_intent(self):
  r=self.run_case('ok');self.assertEqual(r['state'],'succeeded',r);self.assertEqual(r['payload'],'72');self.assertEqual(r['core_state'],'running');self.assertTrue(r['settings_verified']);self.assertTrue(r['dns_resumed']);self.assertEqual(r['config'],'latest-settings')
 def test_stopped_service_stays_stopped_after_successful_upgrade(self):
  r=self.run_case('ok','stopped');self.assertEqual(r['state'],'succeeded',r);self.assertEqual(r['core_state'],'stopped');self.assertFalse(r['restore']['enabled'])
 def test_manager_failure_before_replacement_restores_exact_old_application(self):
  r=self.run_case('before-write');self.assertEqual(r['state'],'failed',r);self.assertEqual(r['payload'],'71');self.assertIsNotNone(r['restore'],r);self.assertEqual(r['restore']['mode'],'running');self.assertTrue(r['dns_resumed']);self.assertEqual(r['config'],'latest-settings')
 def test_failed_preinstall_cannot_restart_old_files_with_changed_settings(self):
  r=self.run_case('before-write-settings');self.assertEqual(r['state'],'failed',r);self.assertEqual(r['payload'],'71');self.assertEqual(r['code'],'settings_changed');self.assertIsNone(r['restore']);self.assertEqual(r['config'],'changed-by-hook')
 def test_partial_native_failure_never_starts_replaced_application(self):
  r=self.run_case('after-write');self.assertEqual(r['state'],'failed',r);self.assertEqual(r['payload'],'72');self.assertIsNone(r['restore']);self.assertFalse(r['dns_resumed']);self.assertEqual(r['config'],'latest-settings')
 def test_settings_change_is_reported_without_overwriting_it(self):
  r=self.run_case('settings-changed');self.assertEqual(r['state'],'failed',r);self.assertEqual(r['code'],'settings_changed');self.assertIsNone(r['restore']);self.assertEqual(r['config'],'changed-by-hook')
if __name__=='__main__':unittest.main()
