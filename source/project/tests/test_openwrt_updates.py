"""Native signed prepare with a real opkg dry run, never service changes."""
import json,os,shlex,subprocess,tempfile,unittest,uuid
from pathlib import Path
import test_openwrt_update_package as fixtures
ROOT=fixtures.ROOT;CONTAINER=os.environ.get('NFQWS_TEST_DOCKER24')or(os.environ.get('NFQWS_TEST_DOCKER')if'24'in os.environ.get('NFQWS_TEST_DOCKER','')else None);CACHE=os.environ.get('NFQWS_TEST_SMARTDNS_CACHE')
@unittest.skipUnless(os.environ.get('PHP_TEST_BINARY'),'Requires matching PHP with OpenSSL')
class NativeDiscoveryContracts(unittest.TestCase):
 def test_first_install_and_signed_update_share_exact_native_target_and_downgrade_rules(self):
  for filename in ['test_openwrt_update_environment.php','test_openwrt_updates.php']:
   with self.subTest(filename=filename):
    p=subprocess.run([os.environ['PHP_TEST_BINARY'],'-n','-f',str(ROOT/'tests'/filename)],capture_output=True,text=True,timeout=15)
    self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');self.assertIn('passed',p.stdout)
@unittest.skipUnless(CONTAINER and CACHE,'Requires isolated native24 rootfs and official ipkg tool')
class NativePreparation(unittest.TestCase):
 def sh(self,code,input=None):
  r=subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',code],input=input,text=True,capture_output=True,timeout=25);self.assertEqual(r.returncode,0,r.stdout+r.stderr);return r.stdout
 def setUp(self):
  self.assertTrue(CONTAINER.startswith('nfqws-openwrt'));self.assertNotEqual(json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]['HostConfig']['NetworkMode'],'host')
  self.base='/tmp/native-prepare-'+uuid.uuid4().hex;self.addCleanup(lambda:self.sh('rm -rf '+self.base));self.sh('umask 077; mkdir '+self.base)
  with tempfile.TemporaryDirectory()as td:
   root=Path(td);stage=root/'payload';out=root/'out';out.mkdir()
   raw='Package: nfqws2-native\nVersion: 1.3.2-72\nArchitecture: x86_64\nDepends: libc, php8-cgi\nMaintainer: madworldpay\nDescription: Inert fixture\n'
   fixtures.builder.write_files(stage,{'CONTROL/control':(raw.encode(),0o644),'CONTROL/preinst':(('#!/bin/sh\ntouch '+self.base+'/hook\n').encode(),0o755),'usr/share/nfqws2/inert':(b'inert',0o644)})
   tool=fixtures.builder.pinned_asset(fixtures.builder.ASSETS['ipkg_build'],CACHE,True);subprocess.run(['fakeroot','sh',str(tool),str(stage),str(out)],check=True,capture_output=True)
   subprocess.run(['docker','cp',str(next(out.glob('*.ipk'))),CONTAINER+':'+self.base+'/source.ipk'],check=True,capture_output=True)
  self.sh('chown 0:0 '+self.base+'/source.ipk; chmod 600 '+self.base+'/source.ipk')
 def call(self,case):
  script='''<?php
$p=$argv[1];$case=$argv[2];$app=$argv[3];
if(!is_file($app.'/openwrt-update-prepare.php'))throw new RuntimeException('native prepare missing');
require $app.'/openwrt-update-prepare.php';require $app.'/update-check.php';require $app.'/update-dispatch.php';
class NativeFixtureSource implements AsusUpdateSource{public array $raw;public ?bool $leaseBlocked=null;public function __construct(public string $file){}public function manifest():array{return $this->raw;}public function download(array $p,string $destination):void{$s=new AsusUpdateStore(dirname($destination,3));try{$f=$s->lease('apply.lock');$this->leaseBlocked=false;flock($f,LOCK_UN);fclose($f);}catch(RuntimeException $e){if($e->getMessage()!=='busy')throw $e;$this->leaseBlocked=true;}copy($this->file,$destination);chmod($destination,0600);}}
$config=$p.'/openssl.cnf';file_put_contents($config,"[req]\ndistinguished_name=req_dn\n[req_dn]\n");$key=openssl_pkey_new(['private_key_bits'=>3072,'private_key_type'=>OPENSSL_KEYTYPE_RSA,'config'=>$config]);$public=openssl_pkey_get_details($key)['key'];
$record=['series'=>'24.10','arch'=>'x86_64','format'=>'ipk','version'=>'1.3.2-72','filename'=>'nfqws2-native_1.3.2-72_x86_64.ipk','size'=>filesize($p.'/source.ipk'),'installed_size'=>1048576,'sha256'=>hash_file('sha256',$p.'/source.ipk')];
if($case==='wrong_target')$record['arch']='mips_24kc';if($case==='wrong_target')$record['filename']='nfqws2-native_1.3.2-72_mips_24kc.ipk';
if($case==='corrupt')$record['sha256']=str_repeat('f',64);
$m=['schema_version'=>1,'platform'=>'openwrt','package'=>'nfqws2-native','core_version'=>'1.3.2','web_version'=>'0.1.4','build'=>72,'notes'=>'Native update','packages'=>[$record]];
$json=json_encode($m);openssl_sign($json,$signature,$key,OPENSSL_ALGO_SHA256);$source=new NativeFixtureSource($p.'/source.ipk');$source->raw=['json'=>$json,'signature'=>base64_encode($signature)];
if($case==='signature')$source->raw['json'].=' ';
$env=['platform'=>'openwrt','series'=>'24.10','arch'=>'x86_64','format'=>'ipk','installed'=>'1.3.2-71','build'=>71,'owner'=>0,'overlay_free'=>1000000000,'ram_free'=>$case==='low_ram'?1:1000000000];
$s=new AsusUpdateStore($p.'/store');$prepare=new NfqwsOpenWrtUpdatePrepare($s,$source,$env,$public);$check=$prepare->check(true);$result=['check'=>$check];
if($check['state']==='available'){$j=$prepare->reserveCached($check['candidate']['revision'],str_repeat('a',32));$again=$prepare->reserveCached($check['candidate']['revision'],str_repeat('a',32));if($again['id']!==$j['id'])throw new RuntimeException('idempotence');$f=$case==='busy'?$s->lease('apply.lock'):null;$stageBlocked=null;$result['operation']=$prepare->completePrepare($j['id'],function()use($s,&$stageBlocked){try{$x=$s->lease('apply.lock');$stageBlocked=false;flock($x,LOCK_UN);fclose($x);}catch(RuntimeException $e){if($e->getMessage()!=='busy')throw $e;$stageBlocked=true;}return ['digest'=>str_repeat('a',64)];});if(is_resource($f)){flock($f,LOCK_UN);fclose($f);}$result['download_lease']=$source->leaseBlocked;$result['stage_lease']=$stageBlocked;$result['cached']=(new AsusUpdateCheck($s,$prepare))->status();$result['dispatch']=(new AsusUpdateDispatch($s,$prepare))->status($j['id']);}
echo json_encode($result);
'''
  self.sh('cat > '+self.base+'/probe.php',script)
  raw=self.sh('php-cli '+self.base+'/probe.php '+self.base+' '+case+' '+shlex.quote(str(ROOT/'webui/web/public')));self.sh('test ! -e '+self.base+'/hook');return json.loads(raw)
 def test_signed_native_candidate_prepares_idempotently_without_installing(self):
  r=self.call('ok');self.assertEqual(r['check']['state'],'available');self.assertEqual(r['operation']['state'],'prepared',r);self.assertEqual(r['cached']['state'],'available');self.assertEqual(r['dispatch']['state'],'prepared')
 def test_preparation_blocks_package_replacement_during_download_and_runtime_copy(self):
  r=self.call('lease');self.assertEqual(r['operation']['state'],'prepared',r);self.assertIs(r['download_lease'],True);self.assertIs(r['stage_lease'],True)
 def test_active_package_mutation_refuses_prepare_before_download(self):
  r=self.call('busy');self.assertEqual(r['operation']['state'],'failed',r);self.assertEqual(r['operation']['code'],'busy');self.assertIsNone(r['download_lease']);self.assertIsNone(r['stage_lease'])
 def test_corrupt_download_fails_before_hooks(self):
  r=self.call('corrupt');self.assertEqual(r['operation']['state'],'failed');self.assertEqual(r['operation']['code'],'download_hash')
 def test_low_ram_fails_before_package_download(self):
  r=self.call('low_ram');self.assertEqual(r['operation']['code'],'insufficient_space')
 def test_wrong_target_and_signature_do_not_reserve_operations(self):
  for case,code in [('wrong_target','unsupported_package'),('signature','invalid_signature')]:
   with self.subTest(case=case):
    r=self.call(case);self.assertEqual(r['check']['state'],'failed');self.assertEqual(r['check']['code'],code);self.assertNotIn('operation',r)
@unittest.skipUnless(fixtures.APK_CONTAINER and CACHE and fixtures.APK_TOOL,'Requires signed native APK fixture')
class NativeApkPreparation(fixtures.NativeApkPreflight):
 test_signed_apk_metadata_is_read_by_native_tool_without_running_hooks=None
 test_missing_key_cannot_be_bypassed_by_archive_reader=None
 test_signed_wrong_package_revision_is_rejected=None
 def test_native_apk_preparation_uses_scoped_keyring_and_native_plan(self):
  import base64,hashlib
  v='1.3.2-r72';record={'series':'25.12','arch':'x86_64','format':'apk','version':v,'filename':self.pkg.name,'size':self.pkg.stat().st_size,'installed_size':1048576,'sha256':hashlib.sha256(self.pkg.read_bytes()).hexdigest()}
  raw=json.dumps({'schema_version':1,'platform':'openwrt','package':'nfqws2-native','core_version':'1.3.2','web_version':'0.1.4','build':72,'notes':'Native update','packages':[record]},separators=(',',':')).encode()
  signature=subprocess.run(['openssl','dgst','-sha256','-sign',str(self.root/'private.pem')],input=raw,capture_output=True,check=True).stdout
  self.sh('cat > '+self.remote+'/manifest.json',raw.decode());self.sh('cat > '+self.remote+'/manifest.sig',base64.b64encode(signature).decode())
  script="require $argv[1].'/openwrt-update-prepare.php';$p=$argv[2];class NativeApkSource implements AsusUpdateSource{public function __construct(public string $p){}public function manifest():array{return ['json'=>file_get_contents($this->p.'/manifest.json'),'signature'=>file_get_contents($this->p.'/manifest.sig')];}public function download(array $p,string $file):void{copy($this->p.'/package.apk',$file);chmod($file,0600);}}$s=new AsusUpdateStore($p.'/store');$env=['platform'=>'openwrt','series'=>'25.12','arch'=>'x86_64','format'=>'apk','installed'=>'1.3.2-r71','build'=>71,'overlay_free'=>1000000000,'ram_free'=>1000000000];$prepare=new NfqwsOpenWrtUpdatePrepare($s,new NativeApkSource($p),$env,file_get_contents($p.'/public.pem'));$checked=$prepare->check(true);if($checked['state']!=='available')throw new RuntimeException(json_encode($checked));$job=$prepare->reserveCached($checked['candidate']['revision'],str_repeat('a',32));echo json_encode($prepare->completePrepare($job['id'],fn()=>['digest'=>str_repeat('a',64)]));"
  result=self.sh('php-cli -r '+shlex.quote(script)+' '+shlex.quote(str(ROOT/'webui/web/public'))+' '+self.remote)
  self.assertEqual(json.loads(result.stdout)['state'],'prepared',result.stdout);self.sh('test ! -e '+self.marker)

if __name__=='__main__':unittest.main()
