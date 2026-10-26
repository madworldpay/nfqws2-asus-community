<?php
require_once __DIR__.'/../webui/web/public/resource-paths.php';
require_once __DIR__.'/../webui/web/public/import-plan.php';
function check(bool $ok,string $label):void{if(!$ok)throw new RuntimeException($label);}
foreach(['/opt/etc/nfqws2/lists/demo.list','/etc/nfqws2/lists/demo.list']as $path){
 check(NfqwsResourcePaths::canonical($path)==='/opt/etc/nfqws2/lists/demo.list','portable resource identity');
}
foreach(['/etc/shadow','/etc/nfqws2/lists/../nfqws2.conf','/opt/etc/nfqws2/lists/a/b.list','/etc/nfqws2/lists/..']as $path)
 check(NfqwsResourcePaths::canonical($path)===null,'no arbitrary path normalization');
$tokens=['--hostlist=/opt/etc/nfqws2/lists/demo.list','--lua-init','@/opt/etc/nfqws2/lua/zapret-lib.lua',
 '--blob=demo:@/opt/etc/nfqws2/blobs/demo.bin','--comment=/opt/etc/nfqws2/lists/demo.list'];
$native=NfqwsResourcePaths::arguments($tokens,'openwrt');
check($native[0]==='--hostlist=/etc/nfqws2/lists/demo.list'&&$native[2]==='@/etc/nfqws2/lua/zapret-lib.lua'&&$native[3]==='--blob=demo:@/etc/nfqws2/blobs/demo.bin','only recognized file operands are rebound');
check($native[4]===$tokens[4],'comments and arbitrary text are not path operands');
check(NfqwsResourcePaths::arguments($native,'asus-entware')===$tokens,'path round trip');

$debug=NfqwsResourcePaths::arguments(['--debug=@/opt/var/log/nfqws2.log','--comment=/opt/var/log/nfqws2.log','--debug=syslog'],'openwrt');
check($debug===['--debug=@/var/log/nfqws2.log','--comment=/opt/var/log/nfqws2.log','--debug=syslog'],'managed debug operand follows native filesystem');
check(NfqwsResourcePaths::arguments(['--debug','@/var/log/nfqws2.log'],'asus-entware')===['--debug','@/opt/var/log/nfqws2.log'],'managed debug reverse path');

check(NfqwsResourcePaths::arguments(['--hostlist-auto-debug=/opt/var/log/nfqws2.log'],'openwrt')===['--hostlist-auto-debug=/var/log/nfqws2.log'],'auto-hostlist journal follows native filesystem');

$blocks=[['key'=>'NFQWS_ARGS','value'=>'--filter-tcp=443 --lua-desync=fake:blob=demo'],['key'=>'NFQWS_ARGS_QUIC','value'=>'']];
$shared='--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua --blob=demo:@/opt/etc/nfqws2/blobs/demo.bin';
// A full-config export carries intentional empty assignments. A blocks-only
// export, by its existing schema, contains non-empty contributed blocks.
$strategy=['type'=>'nfqws2_strategy','schema_version'=>2,'versions'=>['core'=>'1.3.2-1','web'=>'0.1.4'],
 'purpose'=>'Portable fixture','operator'=>'Example ISP','comment'=>'','mode'=>'config',
 'config'=>'ISP_INTERFACE="eth999"'."\n".'NFQWS_BASE_ARGS="'.$shared.'"'."\n".'NFQWS_ARGS="'.$blocks[0]['value'].'"'."\n".'NFQWS_ARGS_QUIC=""'."\n",
 'omitted_options'=>0,'dependencies'=>[]];
$document=AsusImportDocument::read([json_encode($strategy,JSON_THROW_ON_ERROR)]);
$selection=['blocks'=>$blocks,'shared'=>[['key'=>'NFQWS_BASE_ARGS','value'=>$shared]],
 'ports'=>[],'files'=>[],'dns'=>[],'allow_shared_impact'=>true,'allow_incomplete'=>false,'trusted_lua'=>false];
$inventory=['files'=>[
 ['id'=>str_repeat('a',32),'kind'=>'lua','name'=>'zapret-lib.lua','state'=>'available','sha256'=>hash('sha256','lua'),'byte_length'=>3,'bundled_lua'=>true],
 ['id'=>str_repeat('b',32),'kind'=>'blobs','name'=>'demo.bin','state'=>'available','sha256'=>hash('sha256','blob'),'byte_length'=>4],
],'scan_truncated'=>false,'skipped'=>0];
$before="ISP_INTERFACE=\"wan.20\"\nNFQUEUE_NUM=300\nASUS_CLIENTS4=\"192.168.87.10\"\nNFQWS_BASE_ARGS=\"\"\nNFQWS_ARGS=\"--filter-tcp=80\"\nNFQWS_ARGS_QUIC=\"--filter-udp=443\"\n";
$plan=AsusImportPlan::prepare($document,$selection,$before,$inventory,null,'openwrt');
check($plan['ready'],'native proposal is ready without false bundled-Lua consent');
check(str_contains($plan['config'],'@/etc/nfqws2/lua/zapret-lib.lua')&&!str_contains($plan['config'],'/opt/'),'native installed resource paths');
check(AsusImportConfig::parse($plan['config'])['NFQWS_ARGS_QUIC']==='','author-disabled block stays disabled');
check(str_contains($plan['config'],'ISP_INTERFACE="wan.20"')&&str_contains($plan['config'],'ASUS_CLIENTS4="192.168.87.10"'),'local uplink/client identity remains local');
$strategy['config']=str_replace('/opt/etc/nfqws2/','/etc/nfqws2/',$strategy['config']);
$document=AsusImportDocument::read([json_encode($strategy,JSON_THROW_ON_ERROR)]);$selection['shared'][0]['value']=$document['values']['NFQWS_BASE_ARGS'];
$plan=AsusImportPlan::prepare($document,$selection,$before,$inventory,null,'asus-entware');
check($plan['ready']&&str_contains($plan['config'],'@/opt/etc/nfqws2/lua/zapret-lib.lua'),'native JSON can return to Entware');
// Exported log destinations are anonymized, not downloadable input resources.
foreach(['openwrt','asus-entware']as $profile){
 $strategy['config'].="\nMODE_AUTO=\"--hostlist-auto-debug=RESOURCE_11\"\nNFQWS_EXTRA_ARGS=\"--debug @RESOURCE_14\"\n";
 $document=AsusImportDocument::read([json_encode($strategy,JSON_THROW_ON_ERROR)]);
 $selection['shared']=[];foreach($document['values']as $key=>$value)if(in_array($key,AsusImportConfig::SHARED,true))$selection['shared'][]=['key'=>$key,'value'=>$value];
 $plan=AsusImportPlan::prepare($document,$selection,$before,$inventory,null,$profile);
 check($plan['ready'],'redacted output logs are not missing input resources: '.json_encode($plan['problems']));
 $values=AsusImportConfig::parse($plan['config']);$log=NfqwsPlatform::translate('/opt/var/log/nfqws2.log',$profile);
 check($values['MODE_AUTO']==='--hostlist-auto-debug='.$log,'auto-hostlist output log is local');
 check($values['NFQWS_EXTRA_ARGS']==='--debug @'.$log,'debug output log is local');
 $original=$selection['blocks'][0]['value'];$selection['blocks'][0]['value'].=' --hostlist=RESOURCE_11';
 $missing=AsusImportPlan::prepare($document,$selection,$before,$inventory,null,$profile);
 check(!$missing['ready']&&in_array('unresolved_file',array_column($missing['problems'],'code'),true),'log mapping cannot resolve a missing input file');
 $selection['blocks'][0]['value']=$original;
 $strategy['config']=strstr($strategy['config'],"\nMODE_AUTO=",true);
}
echo "Portable native/Entware imports, author intent and resource boundaries passed\n";
