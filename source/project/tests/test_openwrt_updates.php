<?php
require_once __DIR__.'/../webui/web/public/openwrt-update-manifest.php';
function check(bool $ok,string $why):void{if(!$ok)throw new RuntimeException($why);}
function rejects(callable $fn,string $code):void{try{$fn();}catch(RuntimeException $e){check($e->getMessage()===$code,$e->getMessage().' != '.$code);return;}throw new RuntimeException('accepted '.$code);}
$key=openssl_pkey_new(['private_key_bits'=>3072,'private_key_type'=>OPENSSL_KEYTYPE_RSA]);
$public=openssl_pkey_get_details($key)['key'];
function signed(array|string $v):array{global $key;$raw=is_string($v)?$v:json_encode($v,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);openssl_sign($raw,$sig,$key,OPENSSL_ALGO_SHA256);return [$raw,base64_encode($sig)];}
function verify(array|string $v):array{global $public;[$raw,$sig]=signed($v);return NfqwsOpenWrtPackageManifest::verify($raw,$sig,$public);}
$m=['schema_version'=>1,'platform'=>'openwrt','package'=>'nfqws2-native','core_version'=>'1.3.2','web_version'=>'0.1.4','build'=>72,'notes'=>'Native update','packages'=>[]];
foreach(['24.10'=>'ipk','25.12'=>'apk']as $series=>$format)foreach(['arm_cortex-a9','x86_64']as $arch){$v='1.3.2-'.($format==='apk'?'r':'').'72';$m['packages'][]=['series'=>$series,'arch'=>$arch,'format'=>$format,'version'=>$v,'filename'=>"nfqws2-native_{$v}_{$arch}.{$format}",'size'=>12345,'installed_size'=>65536,'sha256'=>str_repeat('a',64)];}
$v=verify($m);check(count($v['packages'])===4,'complete matrix');
$id=['platform'=>'openwrt','series'=>'24.10','arch'=>'arm_cortex-a9','format'=>'ipk'];
$c=NfqwsOpenWrtPackageManifest::candidate($v,$id,'1.3.2-66',66);
check($c['package_version']==='1.3.2-72'&&$c['package']['arch']==='arm_cortex-a9'&&$c['build']===72,'wrong native candidate');
$apk=$id;$apk['series']='25.12';$apk['format']='apk';
check(NfqwsOpenWrtPackageManifest::candidate($v,$apk,'1.3.2-r66',66)['package_version']==='1.3.2-r72','APK identity');
check(NfqwsOpenWrtPackageManifest::candidate($v,$id,'1.3.2-72',72)===null,'same release');
check(NfqwsOpenWrtPackageManifest::candidate($v,$id,'1.3.3-71',71)===null,'signed core downgrade');
check(NfqwsOpenWrtPackageManifest::candidate($v,$id,'1.3.2-73',73)===null,'older build');
$missing=$id;$missing['arch']='mips_24kc';rejects(fn()=>NfqwsOpenWrtPackageManifest::candidate($v,$missing,'1.3.2-66',66),'unsupported_package');
foreach([['platform'=>'asus-entware'],['format'=>'apk'],['series'=>'SNAPSHOT']]as $delta)rejects(fn()=>NfqwsOpenWrtPackageManifest::candidate($v,array_replace($id,$delta),'1.3.2-66',66),'unsupported_abi');
rejects(fn()=>NfqwsOpenWrtPackageManifest::candidate($v,$id,'1.3.2-asus6+b66',66),'unsupported_version');
foreach([['platform'=>'asus-entware'],['package'=>'nfqws2-asus'],['url'=>'https://untrusted.invalid'],['build'=>true],['build'=>73]]as $delta)rejects(fn()=>verify(array_replace($m,$delta)),'invalid_manifest');
foreach([['format'=>'apk'],['arch'=>'x86_64'],['series'=>'25.12'],['version'=>'1.3.2-71'],['filename'=>'nfqws2-asus_1.3.2-asus6+b72_armv7.ipk'],['sha256'=>str_repeat('z',64)],['size'=>33554433],['installed_size'=>134217729]]as $delta){$bad=$m;$bad['packages'][0]=array_replace($bad['packages'][0],$delta);rejects(fn()=>verify($bad),'invalid_manifest');}
$bad=$m;$bad['packages'][]=$m['packages'][0];rejects(fn()=>verify($bad),'invalid_manifest');
[$raw,$sig]=signed($m);rejects(fn()=>NfqwsOpenWrtPackageManifest::verify($raw.' ',$sig,$public),'invalid_signature');
rejects(fn()=>AsusPackageManifest::verify($raw,$sig,$public),'invalid_manifest');
rejects(fn()=>verify(substr($raw,0,-1).',"build":72}'),'invalid_manifest');
echo "Native signed release identity, architecture/series/format isolation and downgrade checks passed\n";
