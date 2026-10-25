<?php
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD']))exit(2);
$status=(string)@file_get_contents('/proc/self/status');if(!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',$status))exit(2);
$args=$argv;array_shift($args);if(($args[0]??null)==='--')array_shift($args);$operation=array_shift($args);
require_once '/usr/share/nfqws2-web/smartdns-native.php';
$b=AsusSmartDnsNativeBackend::create(new AsusSmartDnsStore(),new AsusSmartDnsInstaller());
if(!$b instanceof NfqwsOpenWrtSmartDnsBackend)exit(2);
try{
    if($operation==='launch'&&$args===[]){$spec=$b->launchSpec();if($spec!==null)echo $spec,"\n";exit(0);}
    if($operation==='can-stop'&&$args===[])exit($b->canStop()?0:2);
    $id=array_shift($args);if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id))exit(2);
    if(in_array($operation,['resolver-preflight','resolver-swap'],true)&&count($args)===2){
        [$mode,$instance]=$args;if(!in_array($mode,['forward','restore'],true)||!preg_match('/^[A-Za-z0-9_]{1,64}$/D',$instance))exit(2);
        if($operation==='resolver-preflight')$b->resolverPreflight($id,$mode,$instance);
        else{$raw=file_get_contents('php://stdin',false,null,0,65537);$frame=is_string($raw)&&strlen($raw)<=65536?json_decode($raw,true,32):null;if(!is_array($frame))throw new RuntimeException('invalid_state');$b->resolverSwap($id,$mode,$instance,$frame);}
        exit(0);
    }
    if($operation==='ready'&&count($args)===2){
        foreach($args as $pid)if(!preg_match('/^[1-9][0-9]{0,9}$/D',$pid)||(float)$pid>2147483647)exit(2);
        if(!preg_match('/^PPid:\s+'.$args[0].'\s*$/m',$status))exit(2);
        $b->ownerReady($id,(int)$args[0],(int)$args[1]);exit(0);
    }
    if(in_array($operation,['tick','exit'],true)&&$args===[])exit($b->ownerTick($id,$operation==='exit'));
    exit(2);
}catch(Throwable $e){if($e->getMessage()==='busy')exit(3);file_put_contents('php://stderr',"Native SmartDNS: ".$e->getMessage()."\n");exit(2);}
