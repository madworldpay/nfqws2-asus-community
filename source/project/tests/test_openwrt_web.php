<?php
require_once __DIR__.'/../webui/web/public/platform.php';
require_once __DIR__.'/../webui/web/public/asus.php';
require_once __DIR__.'/../webui/web/public/openwrt-web.php';
function expect(bool $ok,string $message):void{if(!$ok)throw new RuntimeException($message);}
function rejected(callable $fn):void{try{$fn();}catch(RuntimeException $e){return;}throw new RuntimeException('Unsafe platform input accepted');}
expect(NfqwsPlatform::settings('asus-entware')['root']==='/opt','existing ASUS root');
expect(NfqwsPlatform::settings('openwrt')['root']==='','native root');
rejected(fn()=>NfqwsPlatform::settings('other'));
expect(NfqwsPlatform::translate('/opt/etc/nfqws2/lists/user.list','openwrt')==='/etc/nfqws2/lists/user.list','native resources');
expect(NfqwsPlatform::translate('/opt/etc/nfqws-asus-web/auth.json','openwrt')==='/etc/nfqws2-web/auth.json','private web settings');
expect(NfqwsPlatform::translate('/opt/share/nfqws2-asus/dpi-catalog.json','openwrt')==='/usr/share/nfqws2/dpi-catalog.json','shared catalogs');
expect(NfqwsPlatform::translate('/opt/etc/nfqws2/lists/user.list','asus-entware')==='/opt/etc/nfqws2/lists/user.list','ASUS paths stay unchanged');
rejected(fn()=>NfqwsPlatform::translate('/opt/not-a-known-runtime/thing','openwrt'));
rejected(fn()=>NfqwsPlatform::translate('/opt/etc/nfqws2/../../shadow','openwrt'));
expect(NfqwsPlatform::serviceCommand('start','openwrt')===['/etc/init.d/nfqws2-native','start'],'native start');
expect(NfqwsPlatform::serviceCommand('status','openwrt')===['/usr/lib/nfqws2/control.sh','status'],'native queue-aware status');
expect(NfqwsPlatform::serviceCommand('stop','asus-entware')===['/opt/etc/init.d/S51nfqws2','stop'],'ASUS stop');
rejected(fn()=>NfqwsPlatform::serviceCommand('start; reboot','openwrt'));
$wan=NfqwsOpenWrtWeb::wanFromDump(['interface'=>[
 ['interface'=>'wan','up'=>true,'proto'=>'pppoe','l3_device'=>'pppoe-wan','route'=>[['target'=>'0.0.0.0','mask'=>0]],'ipv4-address'=>[['address'=>'198.51.100.9']]],
 ['interface'=>'wan2','up'=>true,'proto'=>'dhcp','l3_device'=>'eth0.20','route'=>[['target'=>'0.0.0.0','mask'=>0]],'ipv4-address'=>[['address'=>'192.0.2.9']]],
 ['interface'=>'lan','up'=>true,'proto'=>'static','l3_device'=>'br-lan','route'=>[],'ipv4-address'=>[['address'=>'192.168.87.1']]],
 ['interface'=>'vpn','up'=>true,'proto'=>'wireguard','l3_device'=>'wg0','route'=>[['target'=>'0.0.0.0','mask'=>0]],'ipv4-address'=>[['address'=>'10.0.0.1']]],
]]);
expect($wan['state']==='available'&&$wan['addresses']===[['interface'=>'pppoe-wan','address'=>'198.51.100.9'],['interface'=>'eth0.20','address'=>'192.0.2.9']],'current multi-WAN facts without VPN/LAN');
expect(NfqwsOpenWrtWeb::wanFromDump([])['state']==='unavailable','no guessed WAN');
$dir=sys_get_temp_dir().'/nfqws-platform-'.bin2hex(random_bytes(8));mkdir($dir,0700);
try{
 $file=$dir.'/profile.json';file_put_contents($file,json_encode(['schema_version'=>1,'platform'=>'openwrt']));chmod($file,0600);$owner=fileowner($file);
 expect(NfqwsPlatform::readProfile($file,$owner)==='openwrt','trusted profile');
 symlink($file,$dir.'/alias.json');rejected(fn()=>NfqwsPlatform::readProfile($dir.'/alias.json',$owner));unlink($dir.'/alias.json');
 chmod($file,0666);rejected(fn()=>NfqwsPlatform::readProfile($file,$owner));chmod($file,0600);
 file_put_contents($file,'{"schema_version":1,"platform":"untrusted"}');rejected(fn()=>NfqwsPlatform::readProfile($file,$owner));
 $resource=$dir.'/data.list';file_put_contents($resource,'example.org');chmod($resource,0600);
 expect(NfqwsPlatform::guardFile($dir,'data.list',$owner)===$resource,'regular scoped file');
 symlink('/etc/passwd',$dir.'/alias.list');rejected(fn()=>NfqwsPlatform::guardFile($dir,'alias.list',$owner));unlink($dir.'/alias.list');
 symlink($dir,$dir.'/alias-dir');rejected(fn()=>NfqwsPlatform::guardFile($dir.'/alias-dir','data.list',$owner));unlink($dir.'/alias-dir');
 rejected(fn()=>NfqwsPlatform::guardFile($dir,'../passwd',$owner));
 $hash=crypt('native-router-password','$6$nfqws-native$');
 file_put_contents($dir.'/passwd','root:x:0:0:root:/root:/bin/ash'."\n");
 file_put_contents($dir.'/shadow','root:'.$hash.':0:0:99999:7:::'."\n");
 file_put_contents($dir.'/auth.json','{"mode":"system","username":"root","password_hash":""}');
 $native=asusWebReadAuth($dir.'/auth.json',$dir.'/passwd',$dir.'/shadow','openwrt');
 expect(is_array($native)&&asusWebAuthenticate('root','native-router-password',$native),'native system account without a packaged fallback');
 expect(asusWebReadAuth($dir.'/auth.json',$dir.'/passwd',$dir.'/shadow','asus-entware')===null,'ASUS fallback contract unchanged');
 file_put_contents($dir.'/shadow','root::0:0:99999:7:::'."\n");
 expect(asusWebReadAuth($dir.'/auth.json',$dir.'/passwd',$dir.'/shadow','openwrt')===null,'unset root password must not open panel');
 foreach(['passwd','shadow','auth.json']as $name)unlink($dir.'/'.$name);
 unlink($resource);
}finally{@unlink($dir.'/profile.json');@rmdir($dir);}
echo "Native/ASUS web platform boundaries passed\n";
