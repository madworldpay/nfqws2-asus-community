"""A real native opkg descendant must recheck the system before capturing settings."""
import json,os,shlex,subprocess,tempfile,unittest,uuid
from pathlib import Path
import test_openwrt_update_package as fixtures
ROOT=fixtures.ROOT;CONTAINER=os.environ.get('NFQWS_TEST_DOCKER');CACHE=os.environ.get('NFQWS_TEST_SMARTDNS_CACHE')
@unittest.skipUnless(CONTAINER and CACHE,'Requires isolated native24 rootfs')
class NativeUpdateHook(unittest.TestCase):
 def sh(self,code,input=None):
  r=subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',code],input=input,text=True,capture_output=True,timeout=25);self.assertEqual(r.returncode,0,r.stdout+r.stderr);return r.stdout
 def run_case(self,case):
  self.assertTrue((ROOT/'webui/web/public/openwrt-update-hook.php').exists(),'native manager hook missing')
  self.assertTrue(CONTAINER.startswith('nfqws-openwrt'));self.assertNotEqual(json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]['HostConfig']['NetworkMode'],'host')
  format='apk'if '25' in CONTAINER else 'ipk'
  if format=='ipk':self.assertNotIn('nfqws2-native - ',self.sh('opkg list-installed'))
  else:self.assertEqual(json.loads(self.sh('apk query --installed --format json --fields name nfqws2-native')),[])
  base='/tmp/native-manager-hook-'+uuid.uuid4().hex;self.addCleanup(lambda:self.sh('rm -rf '+base));self.sh('umask 077; mkdir -p '+base+'/source/app '+base+'/source/resources '+base+'/system/etc/nfqws2; printf %s latest-settings > '+base+'/system/etc/nfqws2/nfqws2.conf')
  self.sh('cp '+shlex.quote(str(ROOT/'webui/web/public'))+'/*.php '+base+'/source/app/; chmod 644 '+base+'/source/app/*.php; printf %s '+shlex.quote('{"schema_version":1,"platform":"openwrt"}')+' > '+base+'/source/app/platform-profile.json')
  for name,dst in [('openwrt-package-manifest.schema.json','openwrt-package-manifest.schema.json'),('trusted-release-key.pem','update-release-key.pem')]:self.sh('cp '+shlex.quote(str(ROOT/'updates'/name))+' '+base+'/source/resources/'+dst)
  self.sh('printf %s '+case+' > '+base+'/case; printf %s '+format+' > '+base+'/format')
  worker='''<?php
require __DIR__.'/app/openwrt-update-hook.php';
$s=new AsusUpdateStore(dirname(__DIR__,3));$id=basename(dirname(__DIR__));$base=dirname(__DIR__,4);$format=trim(file_get_contents($base.'/format'));$managerPath=$format==='apk'?'/usr/bin/apk':'/bin/opkg';$g=new NfqwsOpenWrtUpdateGuard($s);$mode=$argv[count($argv)-2];
if(in_array($mode,['hook-verify','hook-capture','hook-apk-precommit','hook-postinstall'],true)){$h=new NfqwsOpenWrtUpdateHook($s,['root'=>$base.'/system','journal'=>$base.'/journal']);$mode==='hook-apk-precommit'?($h->run('verify')&&$h->run('capture')):$h->run(substr($mode,5));if($g->authorize('core-start')||$g->authorize('web-start'))throw new RuntimeException('installer phase must not start services');if($mode==='hook-postinstall')file_put_contents($base.'/postinstall','deferred');
if($mode==='hook-apk-precommit'){require __DIR__.'/app/openwrt-apk-command.php';$m=NfqwsOpenWrtApkCommand::manager();$t=$g->context($id);if($m['identity']!==$t['manager'])throw new RuntimeException('wrong real manager');$plan=NfqwsPlatform::run(NfqwsOpenWrtApkCommand::simulation($m['argv']),10);if($plan['status']!==0||NfqwsOpenWrtApkCommand::affects(implode("\\n",$plan['output']))!=='upgrade')throw new RuntimeException('locked read-only APK simulation failed');}
exit(0);}
$lease=$s->lease('apply.lock');$worker=AsusUpdateLifecycle::identity(getmypid());$ticket=['schema'=>1,'id'=>$id,'boot_id'=>AsusUpdateStore::boot(),'worker'=>$worker,'manager'=>null,'phase'=>'installing','format'=>$format,'intent'=>['mode'=>'stopped']];$s->writeFile('native-transaction.json',json_encode($ticket));$s->update($id,['identity'=>$worker]);
$db=NfqwsOpenWrtUpdateManager::installed(['format'=>$format]);unset($db['nfqws2-native']);if(trim(file_get_contents($base.'/case'))==='changed')$db['operator-new-package']='1';
$s->writeFile('operations/'.$id.'/native-preflight.json',json_encode(['installed'=>$db]));
if($format==='apk'){require __DIR__.'/app/openwrt-apk-trust.php';NfqwsOpenWrtApkTrust::stage($base.'/keys',file_get_contents($base.'/fixture-public.pem'));}
$commit=null;if($format==='apk'){require __DIR__.'/app/openwrt-apk-commit.php';$commit=NfqwsOpenWrtApkCommit::install($s,$id);}
$args=$format==='ipk'?['/bin/opkg','--nodeps','install',$base.'/package.ipk']:['/usr/bin/apk','add','--network=no','--cache=no','--repositories-file','/dev/null','--keys-dir',$base.'/keys',$base.'/package.apk'];
$p=proc_open($args,[0=>['file','/dev/null','r'],1=>['file',$base.'/manager.log','a'],2=>['file',$base.'/manager.log','a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin']);$status=proc_get_status($p);$pid=$status['pid'];
$end=microtime(true)+1;do{$manager=AsusUpdateLifecycle::identity($pid);if(($manager['exe']??null)===realpath($managerPath))break;usleep(1000);}while(microtime(true)<$end);
$ticket['manager']=$manager;$s->writeFile('native-transaction.json',json_encode($ticket));
if(trim(file_get_contents($base.'/case'))==='delayed')usleep(200000);
file_put_contents($base.'/journal','manager='.$ticket['boot_id'].':'.$pid.':'.$manager['start_ticks']."\\nenabled=0\\nrunning=0\\nweb_present=1\\nweb_enabled=1\\nweb_running=0\\n");chmod($base.'/journal',0600);
$exit=proc_close($p);if($commit!==null&&trim(file_get_contents($base.'/case'))!=='abandoned'&&!NfqwsOpenWrtApkCommit::remove($commit))throw new RuntimeException('gate cleanup failed');echo json_encode(['exit'=>$exit,'backup'=>is_file($s->path('operations/'.$id.'/backup/etc/nfqws2/nfqws2.conf')),'config'=>file_get_contents($base.'/system/etc/nfqws2/nfqws2.conf'),'payload'=>is_file('/usr/share/nfqws2/hook-fixture')]);
'''
  self.sh('cat > '+base+'/source/worker.php',worker)
  setup='require $argv[1]."/openwrt-update-guard.php";$s=new AsusUpdateStore($argv[2]."/store");$r=str_repeat("a",64);$j=$s->reserve($r,str_repeat("b",32),["revision"=>$r,"package_version"=>"1.3.2-72"]);$v=NfqwsOpenWrtUpdateRuntime::stage($s->path("operations/".$j["id"]."/runtime"),["application"=>$argv[1],"resources"=>$argv[2]."/source/resources","entry"=>$argv[2]."/source/worker.php"]);$s->update($j["id"],["state"=>"prepared","runtime_digest"=>$v["digest"]]);$s->claimApply($j["id"],$r,str_repeat("c",32));echo $j["id"];'
  ident=self.sh('php-cli -r '+shlex.quote(setup)+' '+base+'/source/app '+base)
  with tempfile.TemporaryDirectory()as td:
   stage=Path(td)/'payload';out=Path(td)/'out';out.mkdir();meta='Package: nfqws2-native\nVersion: 1.3.2-72\nArchitecture: x86_64\nDescription: Native manager hook fixture\n'
   posthook=('#!/bin/sh\n'+(ROOT/'openwrt/package-lifecycle.sh').read_text().split('case "$NFQWS_PKG_ACTION" in')[0]+'\nnfqws_package_updates_dir='+base+'/store\nnfqws_package_native_update postinstall\n').encode() if case in ['postinstall','uncaptured']else b'#!/bin/sh\nexit 0\n'
   hook='#!/bin/sh\n'+(ROOT/'openwrt/package-lifecycle.sh').read_text().split('case "$NFQWS_PKG_ACTION" in')[0]+'\nnfqws_package_updates_dir='+base+'/store\nnfqws_package_native_update verify && nfqws_package_native_update capture\n'
   if case=='uncaptured':hook=hook.replace(' && nfqws_package_native_update capture','')
   fixtures.builder.write_files(stage,{'usr/share/nfqws2/hook-fixture':(b'inert',0o644)})
   if format=='ipk':
    fixtures.builder.write_files(stage,{'CONTROL/control':(meta.encode(),0o644),'CONTROL/preinst':(hook.encode(),0o755),'CONTROL/postinst':(posthook,0o755)})
    tool=fixtures.builder.pinned_asset(fixtures.builder.ASSETS['ipkg_build'],CACHE,True);subprocess.run(['fakeroot','sh',str(tool),str(stage),str(out)],check=True,capture_output=True);package=next(out.glob('*.ipk'))
   else:
    key=Path(td)/'key.pem';pub=Path(td)/'public.pem';subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,capture_output=True);key.chmod(0o600);subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(pub)],check=True,capture_output=True)
    target=fixtures.builder.native_metadata('25.12','x86_64',72);target['dependencies']=[];package=fixtures.builder.build_apk(target,stage,{'preinst':hook.encode(),'postinst':posthook,'prerm':b'#!/bin/sh\nexit 0\n','postrm':b'#!/bin/sh\nexit 0\n'},CACHE,out,True,key)
    self.sh('cat > '+base+'/fixture-public.pem',pub.read_text())
   subprocess.run(['docker','cp',str(package),CONTAINER+':'+base+'/package.'+format],check=True,capture_output=True)
  try:
   result=json.loads(self.sh(base+'/store/operations/'+ident+'/runtime/run.sh apply '+ident))
   if case=='postinstall':self.sh('test -f '+base+'/postinstall')
   if case=='uncaptured':self.sh('test ! -e '+base+'/postinstall')
   if case=='abandoned':
    self.assertEqual(format,'apk');self.sh('rm -rf '+base+'/store/operations/'+ident+'/runtime')
    self.assertEqual(self.sh('/etc/apk/commit_hooks.d/00-nfqws2-native-'+ident+' pre-commit'),'')
    token=self.sh('cat '+base+'/store/operations/'+ident+'/apk-commit.json')
    self.addCleanup(lambda:self.sh('php-cli -r '+shlex.quote('require $argv[1];NfqwsOpenWrtApkCommit::remove(json_decode($argv[2],true));')+' '+shlex.quote(str(ROOT/'webui/web/public/openwrt-apk-commit.php'))+' '+shlex.quote(token)))
    code='require $argv[1]."/openwrt-apk-commit.php";$s=new AsusUpdateStore($argv[2]);$s->update($argv[3],["state"=>"failed","code"=>"interrupted"]);for($n=1;$n<=2;$n++){$r=str_repeat("d",64);$j=$s->reserve($r,str_pad(dechex($n),32,"0",STR_PAD_LEFT),["revision"=>$r,"package_version"=>"1.3.2-r72"]);$s->update($j["id"],["state"=>"failed","code"=>"interrupted"]);} '
    self.sh('php-cli -r '+shlex.quote(code)+' '+base+'/source/app '+base+'/store '+ident)
    self.sh('test ! -e /etc/apk/commit_hooks.d/00-nfqws2-native-'+ident);result['abandoned_gate_inert']=True
   return result
  finally:self.sh(('opkg remove'if format=='ipk'else'apk del --network=no')+' nfqws2-native >/dev/null 2>&1 || :')
 def test_real_manager_descendant_captures_current_settings_under_its_lock(self):
  r=self.run_case('ok');self.assertEqual(r,{'exit':0,'backup':True,'config':'latest-settings','payload':True})
 def test_controlled_postinstall_requires_actual_quiesced_transaction(self):
  r=self.run_case('postinstall');self.assertEqual(r,{'exit':0,'backup':True,'config':'latest-settings','payload':True})
 def test_postinstall_without_capture_cannot_authorize_deferred_service_restore(self):
  if '25' in CONTAINER:self.skipTest('APK scoped precommit already guarantees capture')
  r=self.run_case('uncaptured');self.assertNotEqual(r['exit'],0);self.assertFalse(r['backup']);self.assertEqual(r['config'],'latest-settings')
 def test_hook_waits_for_its_parent_journal_publication(self):
  r=self.run_case('delayed');self.assertEqual(r,{'exit':0,'backup':True,'config':'latest-settings','payload':True})
 def test_abandoned_apk_gate_is_inert_even_after_runtime_cleanup(self):
  if '25' not in CONTAINER:self.skipTest('APK-specific global commit gate')
  r=self.run_case('abandoned');self.assertEqual(r['exit'],0);self.assertTrue(r['abandoned_gate_inert'])
 def test_system_package_drift_aborts_before_config_capture(self):
  r=self.run_case('changed');self.assertNotEqual(r['exit'],0);self.assertFalse(r['backup']);self.assertEqual(r['config'],'latest-settings');self.assertFalse(r['payload'],'a denied operation must not replace package payload')
if __name__=='__main__':unittest.main()
