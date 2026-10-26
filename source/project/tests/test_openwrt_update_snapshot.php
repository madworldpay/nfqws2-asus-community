<?php
$module=dirname(__DIR__).'/webui/web/public/openwrt-update-snapshot.php';
function ok($v,$m){if(!$v)throw new RuntimeException($m);}function fails(callable $f,$c){try{$f();}catch(RuntimeException $e){ok($e->getMessage()===$c,$e->getMessage());return;}throw new RuntimeException('unsafe snapshot accepted');}
ok(is_file($module),'native config backup missing');require $module;
$root=sys_get_temp_dir().'/native-snapshot-'.bin2hex(random_bytes(8));mkdir($root,0700);$system=$root.'/system';mkdir($system,0700);
function put($p,$v){if(!is_dir(dirname($p)))mkdir(dirname($p),0700,true);file_put_contents($p,$v);chmod($p,0600);}
put($system.'/etc/nfqws2/nfqws2.conf','current config');put($system.'/etc/nfqws2/lists/auto.list','latest learned host');put($system.'/etc/nfqws2/lua/stock.lua','old stock');put($system.'/etc/nfqws2/lua/custom.lua','operator edit');put($system.'/etc/nfqws2-web/auth.json','anonymous explicitly selected');put($system.'/etc/config/nfqws2-web','custom listener');
put($system.'/elsewhere','do not follow');symlink('../../elsewhere',$system.'/etc/nfqws2/custom-link');
$b=['resources'=>['lua/stock.lua'=>['bytes'=>9,'sha256'=>hash('sha256','old stock')]]];put($system.'/usr/share/nfqws2/report-baseline.json',json_encode($b));
$profile=['schema_version'=>1,'upstreams'=>[['id'=>'main','label'=>'DNS','protocol'=>'udp','address'=>'8.8.8.8','port'=>53,'tls_name'=>'','url'=>'','bootstrap'=>[],'default'=>true,'domains'=>[]]],'records'=>[]];
require_once dirname(__DIR__).'/webui/web/public/smartdns-profile.php';
$intent=['schema_version'=>1,'profile'=>$profile,'profile_hash'=>AsusSmartDnsProfile::hash($profile),'engine_sha'=>str_repeat('a',64),'source_request_id'=>str_repeat('b',32)];put($system.'/etc/nfqws2-web/smartdns/resume-intent.json',json_encode($intent));
$snapshot=$root.'/backup';$v=NfqwsOpenWrtUpdateSnapshot::capture($snapshot,$system,getmyuid());
$prune=json_decode(file_get_contents($snapshot.'/snapshot.json'),true);ok(isset($prune['files']['native-snapshot.json']),'native backup manifest must be safely prunable');
ok(file_get_contents($snapshot.'/etc/nfqws2/lists/auto.list')==='latest learned host','captures current state at boundary');ok(!file_exists($snapshot.'/elsewhere')&&!is_link($snapshot.'/etc/nfqws2/custom-link'),'custom link recorded without following');
ok(NfqwsOpenWrtUpdateSnapshot::verify($snapshot,$system,getmyuid()),'untouched settings verified');
put($system.'/etc/nfqws2/lua/stock.lua','new stock');$b['resources']['lua/stock.lua']=['bytes'=>9,'sha256'=>hash('sha256','new stock')];put($system.'/usr/share/nfqws2/report-baseline.json',json_encode($b));
ok(NfqwsOpenWrtUpdateSnapshot::verify($snapshot,$system,getmyuid()),'updated stock allowed');
$intent['source_request_id']=str_repeat('c',32);$intent['engine_sha']=str_repeat('d',64);put($system.'/etc/nfqws2-web/smartdns/resume-intent.json',json_encode($intent));
ok(NfqwsOpenWrtUpdateSnapshot::verify($snapshot,$system,getmyuid()),'fresh DNS validation changes journal identity while retaining user consent');
$changed=$intent;$changed['profile']['upstreams'][0]['label']='different user setting';$changed['profile_hash']=AsusSmartDnsProfile::hash($changed['profile']);put($system.'/etc/nfqws2-web/smartdns/resume-intent.json',json_encode($changed));fails(fn()=>NfqwsOpenWrtUpdateSnapshot::verify($snapshot,$system,getmyuid()),'settings_changed');put($system.'/etc/nfqws2-web/smartdns/resume-intent.json',json_encode($intent));
put($system.'/etc/nfqws2/lua/custom.lua','overwritten edit');fails(fn()=>NfqwsOpenWrtUpdateSnapshot::verify($snapshot,$system,getmyuid()),'settings_changed');put($system.'/etc/nfqws2/lua/custom.lua','operator edit');
unlink($system.'/etc/nfqws2/custom-link');symlink('/different',$system.'/etc/nfqws2/custom-link');fails(fn()=>NfqwsOpenWrtUpdateSnapshot::verify($snapshot,$system,getmyuid()),'settings_changed');
// No automatic restoration overwrites an administrator's concurrent settings.
ok(file_get_contents($system.'/etc/nfqws2/lua/custom.lua')==='operator edit','verification is read only');
echo "PASS: latest native config backup, stock changes, operator edits and links\n";
