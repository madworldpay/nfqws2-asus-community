<?php
$module=dirname(__DIR__).'/openwrt/install-plan.php';
function ok($v,$why){if(!$v)throw new RuntimeException($why);}
function refused($f,$code){try{$f();}catch(RuntimeException $e){ok($e->getMessage()===$code,$e->getMessage().' != '.$code);return;}throw new RuntimeException('unsafe bootstrap plan accepted');}
ok(is_file($module),'native bootstrap must choose an explicit safe first-install/update/recovery action');require $module;
$key=openssl_pkey_new(['private_key_bits'=>3072,'private_key_type'=>OPENSSL_KEYTYPE_RSA]);$public=openssl_pkey_get_details($key)['key'];
$m=['schema_version'=>1,'platform'=>'openwrt','package'=>'nfqws2-native','core_version'=>'1.3.2','web_version'=>'0.1.4','build'=>72,'notes'=>'Fixture','packages'=>[]];
foreach(['24.10'=>'ipk','25.12'=>'apk']as $series=>$format){$version='1.3.2-'.($format==='apk'?'r':'').'72';$m['packages'][]=['series'=>$series,'arch'=>'arm_cortex-a9','format'=>$format,'version'=>$version,'filename'=>'nfqws2-native_'.$version.'_arm_cortex-a9.'.$format,'size'=>1234,'installed_size'=>4567,'sha256'=>str_repeat('a',64)];}
$raw=json_encode($m);openssl_sign($raw,$sig,$key,OPENSSL_ALGO_SHA256);$signature=base64_encode($sig);
$release="DISTRIB_RELEASE='24.10.8'\nDISTRIB_ARCH='arm_cortex-a9'\nDISTRIB_TARGET='bcm53xx/generic'\n";
$own=['name'=>'nfqws2-native','version'=>'1.3.2-66','arch'=>'arm_cortex-a9','format'=>'ipk','state'=>'installed','build'=>66];
function plan($own=null,$releaseOverride=null){global $raw,$signature,$public,$release;return NfqwsOpenWrtInstallPlan::select($raw,$signature,$public,$releaseOverride??$release,$own);}
ok(plan()['action']==='install','fresh installation');ok(plan($own)['action']==='upgrade','ordinary upgrade');
foreach([['version'=>'1.3.2-72','build'=>72,'state'=>'installed','want'=>'current'],['version'=>'1.3.2-72','build'=>71,'state'=>'installed','want'=>'repair_required'],['version'=>'1.3.2-72','build'=>72,'state'=>'unpacked','want'=>'configure'],['version'=>'1.3.2-72','build'=>72,'state'=>'recovery_pending','want'=>'repair_required'],['version'=>'1.3.2-66','build'=>66,'state'=>'recovery_pending','want'=>'upgrade']]as $c){$want=$c['want'];unset($c['want']);ok(plan(array_replace($own,$c))['action']===$want,'known own native recovery policy '.$want);}
refused(fn()=>plan(array_replace($own,['version'=>'1.3.2-73','build'=>73])),'unsupported_version');
foreach([['name'=>'nfqws2-asus'],['arch'=>'x86_64'],['format'=>'apk'],['state'=>'unknown'],['version'=>'1.3.2-asus6+b66']]as $c)refused(fn()=>plan(array_replace($own,$c)),'unsupported_version');
$apkRelease=str_replace('24.10.8','25.12.6',$release);ok(plan(null,$apkRelease)['candidate']['package']['format']==='apk','fresh native APK');
$apkOwn=['name'=>'nfqws2-native','version'=>'1.3.2-r72','arch'=>'arm_cortex-a9','format'=>'apk','state'=>'broken','build'=>72];ok(plan($apkOwn,$apkRelease)['action']==='repair_required','broken same-version APK cannot claim current');
refused(fn()=>NfqwsOpenWrtInstallPlan::select($raw.' ',$signature,$public,$release,null),'invalid_signature');
refused(fn()=>plan(null,str_replace('arm_cortex-a9','mips_24kc',$release)),'unsupported_package');
echo "PASS: signed native bootstrap target, current/upgrades and explicit unfinished-package actions\n";
