<?php
require_once __DIR__.'/../webui/web/public/openwrt-update-package.php';
function check(bool $ok,string $why):void{if(!$ok)throw new RuntimeException($why);}
function rejects(callable $fn,string $code):void{try{$fn();}catch(RuntimeException $e){check($e->getMessage()===$code,$e->getMessage().' != '.$code);return;}throw new RuntimeException('accepted '.$code);}
$p=['series'=>'25.12','arch'=>'x86_64','format'=>'apk','version'=>'1.3.2-r72','filename'=>'nfqws2-native_1.3.2-r72_x86_64.apk','size'=>1000,'installed_size'=>65536,'sha256'=>str_repeat('a',64)];
$c=['package_version'=>$p['version'],'package'=>$p];$env=['platform'=>'openwrt','series'=>'25.12','arch'=>'x86_64','format'=>'apk'];
$record=['name'=>'nfqws2-native','version'=>$p['version'],'arch'=>'x86_64','depends'=>['libc','php8-cgi'],'installed_size'=>32768,'replaces'=>[],'conflicts'=>[]];
check(NfqwsOpenWrtUpdatePackage::metadata($record,$c,$env)===$record,'native metadata');
foreach([['name'=>'nfqws2-asus'],['version'=>'1.3.2-r71'],['arch'=>'arm_cortex-a9'],['depends'=>['!amneziawg']],['replaces'=>['another-tool']],['installed_size'=>65537]]as $delta)rejects(fn()=>NfqwsOpenWrtUpdatePackage::metadata(array_replace($record,$delta),$c,$env),'invalid_package');
foreach([['platform'=>'asus-entware'],['format'=>'ipk'],['arch'=>'arm_cortex-a9'],['series'=>'24.10']]as $delta)rejects(fn()=>NfqwsOpenWrtUpdatePackage::metadata($record,$c,array_replace($env,$delta)),'unsupported_abi');
check(NfqwsOpenWrtUpdatePackage::space(10000000,10000000,$p,1000,1000),'sufficient space');
rejects(fn()=>NfqwsOpenWrtUpdatePackage::space(65536,10000000,$p,1000,1000),'insufficient_space');
rejects(fn()=>NfqwsOpenWrtUpdatePackage::space(10000000,1000,$p,1000,1000),'insufficient_space');
rejects(fn()=>NfqwsOpenWrtUpdatePackage::space(INF,10000000,$p,1000,1000),'insufficient_space');
echo "Native package identity/dependency isolation and separate overlay/RAM checks passed\n";
