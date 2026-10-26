<?php
$module=dirname(__DIR__).'/openwrt/install-state.php';
function ok($v,$why){if(!$v)throw new RuntimeException($why);}function denied($f,$why){try{$f();}catch(RuntimeException $e){ok($e->getMessage()===$why,$e->getMessage().' != '.$why);return;}throw new RuntimeException('unsafe installed bootstrap state');}
ok(is_file($module),'native bootstrap must distinguish actual absent, healthy and unfinished package state');require $module;
$env=['platform'=>'openwrt','series'=>'24.10','arch'=>'arm_cortex-a9','format'=>'ipk'];
$base="Package: libc\nVersion: 1\nStatus: install hold installed\n\n";
$record="Package: nfqws2-native\nVersion: 1.3.2-66\nArchitecture: arm_cortex-a9\nStatus: install user installed\n\n";
$profile=['platform'=>'openwrt','series'=>'24.10','arch'=>'arm_cortex-a9','format'=>'ipk','version'=>'1.3.2-66','application_build'=>66];
function parsed($raw,$profile){global $env;return NfqwsOpenWrtInstallState::parse($raw,$env,$profile===null?null:json_encode($profile));}
ok(parsed($base,null)===null,'first install has no invented package');
$want=['name'=>'nfqws2-native','version'=>'1.3.2-66','arch'=>'arm_cortex-a9','format'=>'ipk','state'=>'installed','build'=>66];
ok(parsed($base.$record,$profile)===$want,'healthy native row and profile agree');
foreach([['install user installed','installed'],['hold hold installed','installed'],['deinstall user installed','recovery_pending'],['install user unpacked','unpacked']]as [$status,$state]){ok(parsed($base.str_replace('install user installed',$status,$record),$profile)['state']===$state,'state '.$status);}
ok(parsed($base.$record,null)['state']==='broken','missing payload identity cannot claim healthy');
ok(parsed($base.$record,array_replace($profile,['version'=>'1.3.2-65']))['state']==='broken','stale payload identity cannot claim healthy');
$old=str_replace(['1.3.2-66','install user installed'],['1.3.2-65','deinstall user not-installed'],$record);
ok(parsed($base.$old.$record,$profile)===$want,'superseded absent own row ignored');
denied(fn()=>parsed(str_replace('hold installed','user unpacked',$base).$record,$profile),'pending_packages');
denied(fn()=>parsed($base.$record.$record,$profile),'pending_packages');
denied(fn()=>parsed($base.str_replace('arm_cortex-a9','x86_64',$record),$profile),'unsupported_version');
$env['series']='25.12';$env['format']='apk';$profile['series']='25.12';$profile['format']='apk';$profile['version']='1.3.2-r66';
$apk="P:libc\nV:1\nf:S\n\nP:nfqws2-native\nV:1.3.2-r66\nA:arm_cortex-a9\nf:S\n\n";
ok(parsed($apk,$profile)['state']==='installed','native APK healthy checksum marker');
ok(parsed(str_replace("A:arm_cortex-a9\nf:S","A:arm_cortex-a9\nf:s",$apk),$profile)['state']==='broken','failed APK script is not current');
echo "PASS: actual native own state, profile identity and unrelated pending-package refusal\n";
