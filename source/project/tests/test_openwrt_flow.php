<?php
require_once __DIR__.'/../openwrt/flow.php';
function expect(bool $yes,string $message):void{if(!$yes)throw new RuntimeException($message);}
function rejected(callable $f):void{try{$f();}catch(RuntimeException $e){return;}throw new RuntimeException('Foreign flow control accepted');}
$doc=json_decode(file_get_contents(__DIR__.'/fixtures/openwrt/fw4-offload.json'),true,512,JSON_THROW_ON_ERROR);
$plan=NfqwsNativeFlow::inspect($doc);
expect($plan['state']==='system'&&$plan['handle']===4,'recognize actual fw4 JSON');
expect($plan['definition']==='add flowtable inet fw4 ft { hook ingress priority 0; devices = { "eth0" }; counter; }','recreate only the recognized flowtable to clear existing accelerated flows');
expect(NfqwsNativeFlow::inspect(['nftables'=>[]])===['state'=>'none','handle'=>null,'definition'=>''],'no offload stays untouched');
$modified=$doc;
foreach($modified['nftables']as&$n)if(isset($n['rule'])&&$n['rule']['handle']===4){
 $n['rule']['expr']=[['jump'=>['target'=>'nfqws2_flow']]];
 $n['rule']['comment']='NFQWS2 native OpenWrt flow control';
}unset($n);
foreach(['nfqws2_flow','nfqws2_flow_scope','nfqws2_flow_add']as$name)$modified['nftables'][]=['chain'=>['family'=>'inet','table'=>'fw4','name'=>$name,'comment'=>'NFQWS2 native OpenWrt']];
expect(NfqwsNativeFlow::inspect($modified)['state']==='managed','owned hook recognized on reload');
$hardware=$doc;foreach($hardware['nftables']as&$n)if(isset($n['flowtable'])){$n['flowtable']['flags']=['offload'];$n['flowtable']['dev']=['eth0','eth1'];}unset($n);
expect(str_contains(NfqwsNativeFlow::inspect($hardware)['definition'],'"eth0", "eth1" }; counter; flags offload;'),'preserve hardware mode and all devices');
$unsafe=$doc;foreach($unsafe['nftables']as&$n)if(isset($n['flowtable']))$n['flowtable']['dev']='eth0"; flush ruleset';unset($n);
rejected(fn()=>NfqwsNativeFlow::inspect($unsafe));
$foreign=$modified;$foreign['nftables'][count($foreign['nftables'])-1]['chain']['comment']='Other program';
rejected(fn()=>NfqwsNativeFlow::inspect($foreign));
$custom=$doc;foreach($custom['nftables']as&$n)if(isset($n['rule'])&&$n['rule']['handle']===4)array_unshift($n['rule']['expr'],['counter'=>['packets'=>0,'bytes'=>0]]);unset($n);
rejected(fn()=>NfqwsNativeFlow::inspect($custom));
$duplicate=$doc;$duplicate['nftables'][]=$doc['nftables'][4];
rejected(fn()=>NfqwsNativeFlow::inspect($duplicate));
$bad=$doc;foreach($bad['nftables']as&$n)if(isset($n['rule'])&&$n['rule']['handle']===4)$n['rule']['handle']='4; flush ruleset';unset($n);
rejected(fn()=>NfqwsNativeFlow::inspect($bad));
echo "Native selective offload ownership checks passed\n";
