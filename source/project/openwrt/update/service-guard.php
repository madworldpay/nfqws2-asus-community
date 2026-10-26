<?php
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(2);
$args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);$mode=array_shift($args);
if(!in_array($mode,['authorize','init','check'],true)||($mode==='init'?$args!==[]:(count($args)!==1||!in_array($args[0],$mode==='authorize'?['core-start','core-stop','web-start','web-stop']:['core-start','core-stop','web-start','web-stop','read'],true))))exit(2);
require_once '/usr/share/nfqws2-web/openwrt-update-guard.php';
if(!NfqwsPlatform::native())exit(2);
try{
    $store=new AsusUpdateStore();$guard=new NfqwsOpenWrtUpdateGuard($store);
    if($mode==='authorize')exit($guard->authorize($args[0])?0:1);
    if($mode==='init'){try{$f=$store->lease('apply.lock',true);fclose($f);}catch(RuntimeException $e){if($e->getMessage()!=='busy')throw $e;}exit(0);}
    $f=$guard->mutationLease();
    if(in_array($args[0],['core-start','web-start'],true)){
        require_once '/usr/share/nfqws2-web/openwrt-update-environment.php';require_once '/usr/share/nfqws2-web/openwrt-update-manager.php';
        $environment=NfqwsOpenWrtUpdateEnvironment::collect();NfqwsOpenWrtUpdateManager::installed($environment,false,true);
    }
    flock($f,LOCK_UN);fclose($f);exit(0);
}catch(Throwable $e){exit(1);}
