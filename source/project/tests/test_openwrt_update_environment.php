<?php
require_once __DIR__.'/../webui/web/public/openwrt-update-environment.php';
function check(bool $ok,string $why):void{if(!$ok)throw new RuntimeException($why);}
function rejects(callable $fn,string $code):void{try{$fn();}catch(RuntimeException $e){check($e->getMessage()===$code,$e->getMessage().' != '.$code);return;}throw new RuntimeException('accepted '.$code);}
$release="DISTRIB_ID='OpenWrt'\nDISTRIB_RELEASE='24.10.8'\nDISTRIB_TARGET='bcm53xx/generic'\nDISTRIB_ARCH='arm_cortex-a9'\n";
$profile=['platform'=>'openwrt','series'=>'24.10','arch'=>'arm_cortex-a9','format'=>'ipk','version'=>'1.3.2-23','application_build'=>71,'engine'=>'arm'];
$record=['name'=>'nfqws2-native','version'=>'1.3.2-23','arch'=>'arm_cortex-a9'];
$r=NfqwsOpenWrtUpdateEnvironment::resolve($release,$profile,$record);
check($r['arch']==='arm_cortex-a9'&&$r['installed']==='1.3.2-23'&&$r['build']===71&&$r['manager']==='/bin/opkg','native IPK environment');
$apk=$profile;$apk['series']='25.12';$apk['format']='apk';$apk['version']='1.3.2-r23';$apkRecord=$record;$apkRecord['version']=$apk['version'];
check(NfqwsOpenWrtUpdateEnvironment::resolve(str_replace('24.10.8','25.12.6',$release),$apk,$apkRecord)['manager']==='/usr/bin/apk','native APK environment');
foreach([['platform'=>'asus-entware'],['series'=>'25.12'],['arch'=>'x86_64'],['format'=>'apk']]as $delta)rejects(fn()=>NfqwsOpenWrtUpdateEnvironment::resolve($release,array_replace($profile,$delta),$record),'unsupported_abi');
foreach([['name'=>'nfqws2-asus'],['arch'=>'armv7'],['version'=>'1.3.2-24']]as $delta)rejects(fn()=>NfqwsOpenWrtUpdateEnvironment::resolve($release,$profile,array_replace($record,$delta)),'version_mismatch');
rejects(fn()=>NfqwsOpenWrtUpdateEnvironment::resolve($release."DISTRIB_ARCH='x86_64'\n",$profile,$record),'unsupported_abi');
rejects(fn()=>NfqwsOpenWrtUpdateEnvironment::resolve(str_replace('24.10.8','SNAPSHOT',$release),$profile,$record),'unsupported_abi');
foreach(['install ok installed','install user installed','hold ok installed','install prefer,user installed']as $status){$p="Package: nfqws2-native\nVersion: 1.3.2-23\nArchitecture: arm_cortex-a9\nStatus: $status\n";check(NfqwsOpenWrtUpdateEnvironment::opkgRecord($p)===$record,'valid opkg flags');}
rejects(fn()=>NfqwsOpenWrtUpdateEnvironment::opkgRecord("Package: nfqws2-native\nVersion: 1.3.2-23\nArchitecture: arm_cortex-a9\nStatus: install ok unpacked\n"),'pending_packages');
echo "Native firmware/package-manager identity and healthy package flags passed\n";
