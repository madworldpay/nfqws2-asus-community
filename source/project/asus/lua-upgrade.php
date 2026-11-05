<?php
// Package-manager-only CAS publication; existing owner edits remain conffiles.
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(1);
$args=$argv;array_shift($args);if(($args[0]??null)==='--')array_shift($args);if($args!==[])exit(2);
$previous='/opt/var/lib/nfqws2-asus/lua-upgrade/previous-baseline.json';
if(!file_exists($previous)&&!is_link($previous))exit(0);
require_once '/opt/share/nfqws-asus-web/openwrt-resource-upgrade.php';
try{
    // This factory tree contains Lua only; ASUS blob seeding remains independent.
    NfqwsOpenWrtResourceUpgrade::apply($previous,'/opt/share/nfqws2-asus/factory','/opt/etc/nfqws2',0,'/opt');
    $sidecars=dirname($previous).'/sidecar-snapshot/names';
    NfqwsOpenWrtResourceUpgrade::cleanupOpkgSidecars($sidecars,'/opt/share/nfqws2-asus/factory','/opt/etc/nfqws2',0,'/opt');
    NfqwsOpenWrtResourceUpgrade::finishOpkgSidecars($sidecars,0,'/opt');
    if(!unlink($previous))throw new RuntimeException('storage_unavailable');
}catch(Throwable $e){file_put_contents('php://stderr',"ASUS stock Lua could not be updated: ".$e->getMessage()."\n");exit(1);}
