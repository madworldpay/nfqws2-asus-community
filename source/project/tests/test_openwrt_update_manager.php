<?php
$module=dirname(__DIR__).'/webui/web/public/openwrt-update-manager.php';
function check($v,$message){if(!$v)throw new RuntimeException($message);}
function rejects(callable $fn,string $expected){try{$fn();}catch(RuntimeException $e){check($e->getMessage()===$expected,$e->getMessage().' != '.$expected);return;}throw new RuntimeException('accepted unsafe manager plan');}
check(is_file($module),'native manager contract is not implemented');require $module;
$ipk="Package: libc\nVersion: 1.2.5-r1\nStatus: hold user,prefer installed\n\nPackage: nfqws2-native\nVersion: 1.3.2-71\nStatus: install user installed\n\nPackage: old\nVersion: 1\nStatus: deinstall ok config-files\n";
$db=NfqwsOpenWrtUpdateManager::database($ipk,'ipk');check($db===['libc'=>'1.2.5-r1','nfqws2-native'=>'1.3.2-71'],'native installed state');
check(NfqwsOpenWrtUpdateManager::database(str_replace('hold user,prefer installed','install hold installed',$ipk),'ipk')===$db,'native hold flag is healthy');
$apk="C:Q1abc\nP:libc\nV:1.2.5-r1\nA:x86_64\n\nP:nfqws2-native\nV:1.3.2-r71\nA:x86_64\n";
check(NfqwsOpenWrtUpdateManager::database($apk,'apk')===['libc'=>'1.2.5-r1','nfqws2-native'=>'1.3.2-r71'],'native apk database');
check(NfqwsOpenWrtUpdateManager::database(str_replace('install user installed','install ok half-installed',$ipk),'ipk',true)===['libc'=>'1.2.5-r1'],'only own transition may be ignored under manager hook');
foreach(['unpacked','half-installed','half-configured']as $status)rejects(fn()=>NfqwsOpenWrtUpdateManager::database(str_replace('hold user,prefer installed','install ok '.$status,$ipk),'ipk'),'pending_packages');
check(NfqwsOpenWrtUpdateManager::database(str_replace('A:x86_64',"A:x86_64\nf:S",$apk),'apk')===NfqwsOpenWrtUpdateManager::database($apk,'apk'),'APK digest format flag is healthy');
foreach(['f','s','fS','sS']as $flag)rejects(fn()=>NfqwsOpenWrtUpdateManager::database(str_replace('P:libc','f:'.$flag."\nP:libc",$apk),'apk'),'pending_packages');
rejects(fn()=>NfqwsOpenWrtUpdateManager::database($apk."\nP:libc\nV:2\n",'apk'),'pending_packages');
$foreignBroken=str_replace('P:libc',"f:s\nP:libc",$apk);
check(NfqwsOpenWrtUpdateManager::database($foreignBroken,'apk',false,true)===['nfqws2-native'=>'1.3.2-r71'],'ordinary service health is scoped to our own package');
rejects(fn()=>NfqwsOpenWrtUpdateManager::database(str_replace('P:nfqws2-native',"f:s\nP:nfqws2-native",$apk),'apk',false,true),'pending_packages');
$record=['name'=>'nfqws2-native','version'=>'1.3.2-72','depends'=>['libc']];$env=['format'=>'ipk'];
$args=NfqwsOpenWrtUpdateManager::argv('/tmp/private/package.ipk',$env,$db,$record);
check($args===['/bin/opkg','--nodeps','install','/tmp/private/package.ipk'],'opkg updates only application after dependency checks');
// Missing and virtual dependencies require the real native provider database; exercised by NativeVirtualDependencies.
$env=['format'=>'apk'];$record['version']='1.3.2-r72';
$args=NfqwsOpenWrtUpdateManager::argv('/tmp/private/package.apk',$env,$db,$record,'/tmp/private/keys');
check($args===['/usr/bin/apk','add','--network=no','--cache=no','--repositories-file','/dev/null','--keys-dir','/tmp/private/keys','/tmp/private/package.apk'],'apk reads only installed packages and signed application, without changing world constraints');
rejects(fn()=>NfqwsOpenWrtUpdateManager::argv('/tmp/private/package.apk',$env,$db,$record),'invalid_signature');
check(NfqwsOpenWrtUpdateManager::plan("Installing nfqws2-native (1.3.2-72) to root...\n",'ipk',array_replace($record,['version'=>'1.3.2-72'])),'ipk install plan');
$warning="Multiple packages (nfqws2-native and nfqws2-native) providing same name marked HOLD or PREFER. Using latest.\n";
$retry=$warning."Upgrading nfqws2-native on root from 1.3.2-34 to 1.3.2-72...\n";
check(NfqwsOpenWrtUpdateManager::plan($retry,'ipk',array_replace($record,['version'=>'1.3.2-72'])),'retained absent own row warning must not block a verified one-app upgrade');
rejects(fn()=>NfqwsOpenWrtUpdateManager::plan(str_replace('and nfqws2-native','and foreign-provider',$retry),'ipk',array_replace($record,['version'=>'1.3.2-72'])),'dependency_change');

check(NfqwsOpenWrtUpdateManager::plan("Upgrading nfqws2-native on root from 1.3.2-71 to 1.3.2-72...\n",'ipk',array_replace($record,['version'=>'1.3.2-72'])),'ipk upgrade plan');
check(NfqwsOpenWrtUpdateManager::plan("(1/1) Upgrading nfqws2-native (1.3.2-r71 -> 1.3.2-r72)\nOK: 37.5 MiB in 197 packages\n",'apk',$record),'apk upgrade plan');
foreach(["(1/2) Upgrading php8-cgi (1 -> 2)\n(2/2) Installing nfqws2-native (1.3.2-r72)\n","(1/1) Purging dnsmasq (1)\n",'UNKNOWN output']as $bad)rejects(fn()=>NfqwsOpenWrtUpdateManager::plan($bad,'apk',$record),'dependency_change');
rejects(fn()=>NfqwsOpenWrtUpdateManager::plan("Installing libc (2) to root...\nInstalling nfqws2-native (1.3.2-72) to root...\n",'ipk',$record),'dependency_change');
echo "PASS: native manager state, dependency and application-only plan contracts\n";
