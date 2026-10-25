<?php
require_once __DIR__.'/../webui/web/public/import-config.php';
require_once __DIR__.'/../openwrt/config.php';
function expect(bool $yes,string $message): void {if(!$yes)throw new RuntimeException($message);}
function rejected(callable $f): void {try{$f();}catch(RuntimeException $e){return;}throw new RuntimeException('Unsafe input accepted');}

$text=<<<'CONF'
ISP_INTERFACE=""
NFQUEUE_NUM=300
USER=nobody
IPV6_ENABLED=1
TCP_PORTS=80,443
UDP_PORTS=443
ASUS_CLIENT_MODE=include
ASUS_CLIENTS4="192.168.87.10 192.168.87.20"
MODE_LIST="--hostlist=/etc/nfqws2/lists/user.list"
NFQWS_EXTRA_ARGS="$MODE_LIST"
NFQWS_BASE_ARGS="--lua-init=@/etc/nfqws2/lua/zapret-lib.lua"
NFQWS_ARGS="--filter-tcp=443 --lua-desync=multisplit:pos=1"
CONF;
$parsed=NfqwsNativeConfig::parse($text);
expect($parsed['NFQUEUE_NUM']==='300','queue value');
expect($parsed['NFQWS_EXTRA_ARGS']==='--hostlist=/etc/nfqws2/lists/user.list','known expansion');
expect($parsed['ASUS_CLIENTS4']==='192.168.87.10 192.168.87.20','author client selection');
expect($parsed['NFQWS_ARGS_QUIC']==='','missing block stays disabled');
rejected(fn()=>NfqwsNativeConfig::parse($text."\nUSER=\$(id)\n"));
rejected(fn()=>NfqwsNativeConfig::parse(str_replace('USER=nobody','USER="`id`"',$text)));
rejected(fn()=>NfqwsNativeConfig::parse(str_replace('ISP_INTERFACE=""','ISP_INTERFACE="$MODE_LIST"',$text)));
rejected(fn()=>NfqwsNativeConfig::parse($text."\ntouch /tmp/should-not-exist\n"));
foreach(['--daemon','--daem','-daemon','--uid=0','--qnum=99','--pidfile=/tmp/other','@/tmp/other','--intercept=0','--dry-run']as$option){
    rejected(fn()=>NfqwsNativeConfig::parse(str_replace('--filter-tcp=443 --lua-desync=multisplit:pos=1',$option,$text)));
}
$literal=NfqwsNativeConfig::shell($parsed);
expect(str_contains($literal,"ASUS_CLIENTS4='192.168.87.10 192.168.87.20'"),'quoted shell data');
expect(!str_contains($literal,'$MODE_LIST'),'no unresolved expansions');
$danger=$parsed;$danger['NFQWS_ARGS']="--filter-tcp=443 ' ; echo pwned";
expect(str_contains(NfqwsNativeConfig::shell($danger),"'\\''"),'single quotes are data, never commands');
echo "Native configuration parsing checks passed\n";
