<?php
require_once __DIR__.'/../webui/web/public/openwrt-resource-upgrade.php';
$mask=umask(0022);
function check(bool $ok,string $why):void{if(!$ok)throw new RuntimeException($why);}
function rejects(callable $fn):void{try{$fn();}catch(RuntimeException $e){return;}throw new RuntimeException('unsafe resource accepted');}
$root=sys_get_temp_dir().'/nfqws-stock-'.bin2hex(random_bytes(8));mkdir($root,0700);
foreach(['active','defaults']as $base)foreach(['lua','blobs']as $kind)mkdir($root.'/'.$base.'/'.$kind,0755,true);
$baseline=['resources'=>[]];
foreach(['lua/stock.lua'=>['old','new','old'],'lua/edited.lua'=>['original','updated','my edit'],'blob/test.bin'=>["old\0blob","new\0blob","old\0blob"]]as $key=>[$old,$new,$current]){
 $path=preg_replace('~^blob/~','blobs/',$key);
 file_put_contents($root.'/active/'.$path,$current);file_put_contents($root.'/defaults/'.$path,$new);
 $baseline['resources'][$key]=['bytes'=>strlen($old),'sha256'=>hash('sha256',$old)];
}
file_put_contents($root.'/active/lua/custom.lua','mine');
$previous=$root.'/old-baseline.json';file_put_contents($previous,json_encode($baseline));chmod($previous,0600);
$apply=fn()=>NfqwsOpenWrtResourceUpgrade::apply($previous,$root.'/defaults',$root.'/active',getmyuid());
try{
 $changed=$apply();sort($changed);check($changed===['blob/test.bin','lua/stock.lua'],'wrong update set');
 check(file_get_contents($root.'/active/lua/stock.lua')==='new','stock Lua did not update');
 check(file_get_contents($root.'/active/blobs/test.bin')==="new\0blob",'binary blob did not update');
 check(file_get_contents($root.'/active/lua/edited.lua')==='my edit','custom edit overwritten');
 check(file_get_contents($root.'/active/lua/custom.lua')==='mine','custom file overwritten');
 check($apply()===[],'repeat must be inert');
 unlink($root.'/active/lua/stock.lua');symlink($root.'/active/lua/custom.lua',$root.'/active/lua/stock.lua');check($apply()===[],'operator links must be left alone');
 check(file_get_contents($root.'/active/lua/custom.lua')==='mine','link target changed');
 unlink($root.'/active/lua/stock.lua');file_put_contents($root.'/active/lua/stock.lua','old');
 $bad=$baseline;$bad['resources']['lua/edited.lua']['sha256']='bad';file_put_contents($previous,json_encode($bad));rejects($apply);
 check(file_get_contents($root.'/active/lua/stock.lua')==='old','bad manifest must fail before any mutation');
 echo "Native stock resource updates preserve user edits, binary content and CAS boundaries\n";
}finally{
 foreach(['active','defaults']as $base){foreach(['lua','blobs']as $kind){foreach(glob($root.'/'.$base.'/'.$kind.'/*')as $p)unlink($p);rmdir($root.'/'.$base.'/'.$kind);}rmdir($root.'/'.$base);}
 unlink($previous);rmdir($root);umask($mask);
}
