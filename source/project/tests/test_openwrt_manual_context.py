"""A manual DNS exception requires both the native manager and fixed quiesce controller."""
import json,os,shlex,subprocess,tempfile,unittest,uuid
from pathlib import Path
import test_openwrt_update_package as f
ROOT=f.ROOT;CONTAINER=os.environ.get('NFQWS_TEST_DOCKER');CACHE=os.environ.get('NFQWS_TEST_SMARTDNS_CACHE')
@unittest.skipUnless(CONTAINER and CACHE,'Requires isolated native rootfs and official package tools')
class ManualNativeContext(unittest.TestCase):
 def sh(self,code,input=None,check=True):
  p=subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',code],input=input,text=True,capture_output=True,timeout=25)
  if check:self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  return p.stdout
 def run_case(self,case,production=False):
  self.assertTrue((ROOT/'webui/web/public/openwrt-manual-context.php').exists(),'manual controller proof missing')
  self.assertTrue(CONTAINER.startswith('nfqws-openwrt'));self.assertNotEqual(json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]['HostConfig']['NetworkMode'],'host')
  fmt='apk'if'25'in CONTAINER else'ipk'
  if fmt=='ipk':self.assertNotIn('nfqws2-native - ',self.sh('opkg list-installed'))
  else:self.assertEqual(json.loads(self.sh('apk query --installed --format json --fields name nfqws2-native')),[])
  self.sh('test ! -e /tmp/nfqws2-native-package')
  base='/tmp/native-manual-'+uuid.uuid4().hex;entry='/usr/lib/nfqws2/update/quiesce.php'
  self.sh('test ! -e '+entry);self.addCleanup(lambda:self.sh('rm -rf '+base,check=False))
  self.sh('umask 077; mkdir -p '+base+'/app /usr/lib/nfqws2/update; cp '+shlex.quote(str(ROOT/'webui/web/public'))+'/*.php '+base+'/app/; chmod 644 '+base+'/app/*.php; printf %s '+shlex.quote('{"schema_version":1,"platform":"openwrt"}')+' > '+base+'/app/platform-profile.json')
  self.sh('printf %s '+case+' > '+base+'/case')
  helper='''<?php
require __DIR__.'/app/update-guard.php';require __DIR__.'/app/openwrt-manual-context.php';$store=new AsusUpdateStore(__DIR__.'/store');$g=new AsusUpdateGuard($store);if(trim(file_get_contents(__DIR__.'/case'))==='stale-ui'){require __DIR__.'/app/openwrt-update-hook.php';$t=['schema'=>1,'id'=>str_repeat('d',32),'boot_id'=>AsusUpdateStore::boot(),'worker'=>['pid'=>2147483647,'start_ticks'=>'1','boot_id'=>AsusUpdateStore::boot(),'exe'=>'/usr/bin/php8-cgi','uid'=>0],'manager'=>null,'phase'=>'installing','format'=>is_file('/usr/bin/apk')?'apk':'ipk','intent'=>['mode'=>'stopped']];$store->writeFile('native-transaction.json',json_encode($t));if((new NfqwsOpenWrtUpdateHook($store))->run('verify'))throw new RuntimeException('dead UI hook must stay inert');}$manager=NfqwsOpenWrtManualContext::manager();if(!in_array($manager['format'],['ipk','apk'],true)||$manager['identity']['uid']!==0)throw new RuntimeException('wrong native manager frame');$authorized=$g->authorize('dns-restore');$blocked=false;try{$f=$g->mutationLease();fclose($f);}catch(RuntimeException $e){$blocked=$e->getMessage()==='busy';}echo json_encode(['authorized'=>$authorized,'ordinary_blocked'=>$blocked]);
'''
  self.sh('cat > '+base+'/probe.php',helper)
  controller="<?php\nrequire "+json.dumps(base+"/app/update-guard.php")+";$s=new AsusUpdateStore("+json.dumps(base+'/store')+");$f=$s->lease('apply.lock');$p=proc_open(['/usr/bin/php8-cgi','-d','register_argc_argv=1','-q','-f',"+json.dumps(base+'/probe.php')+"],[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes);$raw=stream_get_contents($pipes[1]);$error=stream_get_contents($pipes[2]);fclose($pipes[1]);fclose($pipes[2]);$exit=proc_close($p);if($exit!==0)throw new RuntimeException($error.$raw);file_put_contents("+json.dumps(base+'/result.json')+",$raw);"
  if production:
   script='/usr/lib/nfqws2/update/quiesce.sh';self.sh('test ! -e '+script)
   self.sh('cat > '+script,'#!/bin/sh\n/usr/bin/php8-cgi -d register_argc_argv=1 -q -f '+base+'/probe.php > '+base+'/result.json\n');self.sh('chmod 755 '+script);self.addCleanup(lambda:self.sh('rm -f '+script,check=False))
   controller=(ROOT/'openwrt/update/quiesce.php').read_text().replace('/usr/share/nfqws2-web',base+'/app').replace('new AsusUpdateStore()', 'new AsusUpdateStore('+json.dumps(base+'/store')+')')
  if production and case=='unsafe-wrapper':controller=controller.replace('<?php', '<?php file_put_contents('+json.dumps(base+'/entry-started')+',"started");',1)
  self.sh('cat > '+entry,controller);self.sh('chmod 644 '+entry)
  self.addCleanup(lambda:self.sh('rm -f '+entry,check=False))
  if case in ['unsafe-controller-dir','unsafe-wrapper']:
   original=self.sh('php-cli -r '+shlex.quote('echo decoct(fileperms($argv[1])&0777);')+' /usr/lib/nfqws2/update').strip();self.sh('chmod 777 /usr/lib/nfqws2/update');self.addCleanup(lambda:self.sh('chmod '+original+' /usr/lib/nfqws2/update',check=False))
  library=(ROOT/'openwrt/package-lifecycle.sh').read_text().split('case "$NFQWS_PKG_ACTION" in')[0]
  body='#!/bin/sh\numask 077\n'+library+'\nNFQWS_PKG_FORMAT='+fmt+'\nnfqws_package_snapshot || exit 1\n'
  body+='/usr/bin/php8-cgi -d register_argc_argv=1 -q -f '+base+'/probe.php > '+base+'/outside.json\n'
  if case=='stale':body+="sed -i 's/^manager=.*/manager=stale:2:3/' /tmp/nfqws2-native-package/state\n"
  if case=='unsafe':body+='chmod 666 /tmp/nfqws2-native-package/state\n'
  if production and case=='busy':
   holder='<?php require __DIR__."/app/update-store.php";$s=new AsusUpdateStore(__DIR__."/store");$f=$s->lease("apply.lock",true);file_put_contents(__DIR__."/ready","ready");$end=microtime(true)+5;while(!is_file(__DIR__."/release")&&microtime(true)<$end)usleep(10000);'
   self.sh('cat > '+base+'/holder.php',holder)
   body+='/usr/bin/php8-cgi -d register_argc_argv=1 -q -f '+base+'/holder.php & holder=$!\nwhile [ ! -f '+base+'/ready ]; do sleep 1; done\n'
  body+=(('nfqws_package_stop_services upgrade'+(' 2> '+base+'/controller.error'if case=='busy'else'')+'\n')if production else'/usr/bin/php8-cgi -d register_argc_argv=1 -q -f '+entry+' -- upgrade\n')
  if production and case=='unsafe-wrapper':body+='code=$?; printf %s "$code" > '+base+'/exit; exit 0\n'
  if production and case=='busy':body+='code=$?; printf %s "$code" > '+base+'/exit; touch '+base+'/release; wait "$holder"; exit 0\n'

  with tempfile.TemporaryDirectory()as td:
   stage=Path(td)/'payload';out=Path(td)/'out';out.mkdir();target=f.builder.native_metadata('25.12'if fmt=='apk'else'24.10','x86_64',72);target['dependencies']=[]
   f.builder.write_files(stage,{'usr/share/nfqws2/manual-context-fixture':(b'inert',0o644)})
   if fmt=='ipk':
    f.builder.write_files(stage,{'CONTROL/control':(b'Package: nfqws2-native\nVersion: 1.3.2-72\nArchitecture: x86_64\nDescription: Inert manual context fixture\n',0o644),'CONTROL/preinst':(body.encode(),0o755)})
    tool=f.builder.pinned_asset(f.builder.ASSETS['ipkg_build'],CACHE,True);subprocess.run(['fakeroot','sh',str(tool),str(stage),str(out)],check=True,capture_output=True);pkg=next(out.glob('*.ipk'))
   else:
    key=Path(td)/'key.pem';pub=Path(td)/'public.pem';subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,capture_output=True);key.chmod(0o600);subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(pub)],check=True,capture_output=True)
    hooks={name:b'#!/bin/sh\nexit 0\n'for name in ['preinst','postinst','prerm','postrm']};hooks['preinst']=body.encode();pkg=f.builder.build_apk(target,stage,hooks,CACHE,out,True,key);self.sh('mkdir -m 700 '+base+'/keys; cat > '+base+'/keys/fixture.pem',pub.read_text())
   subprocess.run(['docker','cp',str(pkg),CONTAINER+':'+base+'/package.'+fmt],check=True,capture_output=True)
  try:
   command='opkg --nodeps install '+base+'/package.ipk'if fmt=='ipk'else'apk add --network=no --cache=no --repositories-file /dev/null --keys-dir '+base+'/keys '+base+'/package.apk'
   self.sh(command)
   if production and case=='unsafe-wrapper':return {'refused':self.sh('cat '+base+'/exit').strip()!='0','entry_started':self.sh('test -e '+base+'/entry-started; printf %s $?').strip()=='0'}
   if production and case=='busy':
    self.sh('test ! -e '+base+'/result.json');self.assertIn('busy',self.sh('cat '+base+'/controller.error'));return {'busy':self.sh('cat '+base+'/exit').strip()!='0'}
   outside=json.loads(self.sh('cat '+base+'/outside.json'));inside=json.loads(self.sh('cat '+base+'/result.json'));self.assertFalse(outside['authorized'],'manager alone cannot bypass updater lease');return inside
  finally:
   self.sh(('opkg remove'if fmt=='ipk'else'apk del --network=no')+' nfqws2-native >/dev/null 2>&1 || :',check=False)
   self.sh('rm -rf /tmp/nfqws2-native-package',check=False)
 def test_exact_controller_restores_dns_while_ordinary_mutations_stay_blocked(self):
  self.assertEqual(self.run_case('ok'),{'authorized':True,'ordinary_blocked':True})
 def test_manual_recovery_can_ignore_a_dead_ui_ticket_without_sh_lease_deadlock(self):
  self.assertEqual(self.run_case('stale-ui'),{'authorized':True,'ordinary_blocked':True})
 def test_writable_controller_parent_cannot_grant_the_exception(self):
  self.assertEqual(self.run_case('unsafe-controller-dir'),{'authorized':False,'ordinary_blocked':True})
 def test_unprotected_manager_journal_cannot_authorize_controller(self):
  self.assertEqual(self.run_case('unsafe'),{'authorized':False,'ordinary_blocked':True})
 def test_stale_manager_journal_cannot_authorize_even_the_fixed_controller(self):
  self.assertEqual(self.run_case('stale'),{'authorized':False,'ordinary_blocked':True})
if __name__=='__main__':unittest.main()
