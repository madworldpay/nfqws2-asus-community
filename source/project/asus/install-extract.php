<?php
// Generated trusted bytes are extracted only into the installer's private work.
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(2);
$args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);
if(count($args)!==2||!in_array($args[0],['extract','prepare','check','describe','run','status'],true))exit(2);
[$nfqwsAsusMode,$nfqwsAsusWork]=$args;
try{
    umask(0077);
    for($p=$nfqwsAsusWork;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');
    $s=@lstat($nfqwsAsusWork);if(!$s||!is_dir($nfqwsAsusWork)||$s['uid']!==0||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
    // Bulk extraction and the included coordinator use their existing bounded
    // I/O/guardian deadlines, not the CGI interpreter's cumulative CPU timer.
    set_time_limit(0);
    // Entware may configure CGI for tiny HTTP requests (for example 8M).
    // Give only this validated root bootstrap a bounded allowance; retain
    // larger/unlimited limits and leave php.ini and HTTP requests unchanged.
    $memoryLimit=ini_parse_quantity((string)ini_get('memory_limit'));
    if($memoryLimit>0&&$memoryLimit<33554432&&ini_set('memory_limit','32M')===false)throw new RuntimeException('unsupported_runtime');
    $files=json_decode(gzdecode(base64_decode(NFQWS_ASUS_INSTALL_FILES,true)),true,32,JSON_THROW_ON_ERROR);
    foreach($files as $name=>$item){
        if(!preg_match('~^(?:[a-zA-Z0-9_+.-]+/)*[a-zA-Z0-9_+.-]+$~D',$name)||in_array('..',explode('/',$name),true))throw new RuntimeException('invalid_state');
        $path=$nfqwsAsusWork.'/'.$name;$data=base64_decode($item['data'],true);$mode=$item['mode'];
        $directories=[];for($p=dirname($path);$p!==$nfqwsAsusWork;$p=dirname($p))$directories[]=$p;
        foreach(array_reverse($directories) as $p){if(!file_exists($p)&&!mkdir($p,0700))throw new RuntimeException('invalid_state');$d=lstat($p);if(is_link($p)||!is_dir($p)||$d['uid']!==0||($d['mode']&0777)!==0700)throw new RuntimeException('invalid_state');}
        clearstatcache(true,$path);$s=@lstat($path);
        if(!$s){$f=fopen($path,'xb');if(!$f)throw new RuntimeException('invalid_state');try{if(fwrite($f,$data)!==strlen($data)||!fflush($f)||!chmod($path,$mode))throw new RuntimeException('invalid_state');}finally{fclose($f);}clearstatcache(true,$path);$s=lstat($path);}
        if(is_link($path)||!is_file($path)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==$mode||$s['size']!==strlen($data)||!hash_equals(hash('sha256',$data),(string)hash_file('sha256',$path)))throw new RuntimeException('runtime_changed');
    }
    // Embedded copies are no longer needed once every extracted byte matches.
    unset($files,$data,$item);
    if($nfqwsAsusMode==='extract')exit(0);
    require $nfqwsAsusWork.'/main.php';
}catch(Throwable $e){file_put_contents('php://stderr','ASUS bootstrap: '.$e->getMessage()."\n");exit(1);}
