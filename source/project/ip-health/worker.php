<?php
/** Fixed root-only CLI/CGI entry; no environment-selected paths or HTTP mode. */
declare(strict_types=1);
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(1);
require_once '/opt/share/nfqws-asus-web/ip-health-runtime.php';
$args=$argv;array_shift($args);if(($args[0]??null)==='--')array_shift($args);$mode=array_shift($args);
$private='/tmp/nfqws2-asus/ip-health-private';$public='/tmp/nfqws2-asus-ip-health';
$store=new NfqwsIpHealthStore();$runtime=new NfqwsIpHealthRuntime($store,$private,$public);
try{
    if($mode==='enabled'){if($args!==[])exit(1);exit($store->view()['enabled']?0:1);}
    if($mode==='module'){if($args!==[])exit(1);exit(extension_loaded('sockets')&&function_exists('socket_create')?0:1);}
    if($mode==='inactive'){
        if(count($args)!==1||!in_array($args[0],['core_stopped','socket_unavailable','multiwan_unsupported','queue_in_use','starting','unavailable'],true))exit(1);
        $runtime->inactive($args[0],time());exit(0);
    }
    if($mode==='available'){
        if(count($args)!==1)exit(1);$ready=(new NfqwsIpHealthProbe())->availability($args[0]);
        if(!$ready)$runtime->inactive('socket_unavailable',time());exit($ready?0:1);
    }
    if($mode==='owned-pids'){
        if($args!==[])exit(1);foreach($runtime->ownedPids(__FILE__,PHP_BINARY) as $pid)echo $pid,"\n";exit(0);
    }
    if($mode==='prepare'){
        if(count($args)!==6)exit(1);[$core,$observer,$queue,$interface,$ipv6,$generation]=$args;
        foreach([$core,$observer,$queue] as $number)if(!preg_match('/^[1-9][0-9]{0,9}$/D',$number))exit(1);
        if(!in_array($ipv6,['0','1'],true)||!preg_match('/^[A-Za-z0-9_.:-]{1,15}$/D',$interface)||!preg_match('/^[a-f0-9]{64}$/D',$generation))exit(1);
        $status=(string)@file_get_contents('/proc/'.$core.'/status');if(!preg_match('/^Uid:\s+\d+\s+(\d+)/m',$status,$m))exit(1);
        $facts=['schema_version'=>1,'boot_id'=>trim((string)@file_get_contents('/proc/sys/kernel/random/boot_id')),
            'core_pid'=>(int)$core,'core_start_ticks'=>NfqwsIpHealthRuntime::startTicks((string)@file_get_contents('/proc/'.$core.'/stat')),
            'observer_pid'=>(int)$observer,'observer_start_ticks'=>NfqwsIpHealthRuntime::startTicks((string)@file_get_contents('/proc/'.$observer.'/stat')),
            'queue'=>(int)$queue,'interface'=>$interface,'generation'=>$generation,'ipv6'=>$ipv6==='1','engine_uid'=>(int)$m[1]];
        $runtime->writePrivate('runtime.json',$facts);$runtime->liveFacts();exit(0);
    }
    if($mode==='healthy'){
        if(count($args)!==2)exit(1);$facts=$runtime->liveFacts();$pids=$runtime->ownedPids(__FILE__,PHP_BINARY);
        exit($facts['generation']===$args[0]&&$facts['core_pid']===(int)$args[1]&&count($pids)===2?0:1);
    }
    if($mode!=='loop'||$args!==[])exit(1);
    $runtime->liveFacts();$lock=$private.'/worker.lock';$s=@lstat($lock);
    if($s&&(($s['mode']&0170000)!==0100000||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']!==0))exit(1);
    $mask=umask(0077);try{$f=@fopen($lock,$s?'r+e':'x+e');}finally{umask($mask);}if(!$f)exit(1);
    $a=fstat($f);$b=lstat($lock);if($a['ino']!==$b['ino']||$a['dev']!==$b['dev']||!flock($f,LOCK_EX|LOCK_NB))exit(0);
    $runtime->writePrivate('worker.json',['pid'=>getmypid(),'start_ticks'=>NfqwsIpHealthRuntime::startTicks((string)file_get_contents('/proc/self/stat')),'boot_id'=>trim((string)file_get_contents('/proc/sys/kernel/random/boot_id'))]);
    while(true){$runtime->tick(time());$runtime->liveFacts();usleep(1000000);}
}catch(Throwable $e){$runtime->inactive($e->getMessage()==='core_stopped'?'core_stopped':'unavailable',time());exit(1);}
