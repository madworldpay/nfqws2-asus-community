<?php
// CLI/CGI entry outside the document root. Arguments are fixed modes and IDs.
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true))exit(1);
$status=@file_get_contents('/proc/self/status');
if(!is_string($status)||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',$status))exit(1);
$arguments=$argv;array_shift($arguments);if(($arguments[0]??null)==='--')array_shift($arguments);
$mode=array_shift($arguments);
$app=is_dir(__DIR__.'/app')?__DIR__.'/app':'/opt/share/nfqws-asus-web';
require_once $app.'/update-worker.php';
require_once $app.'/update-watchdog.php';
require_once $app.'/update-check.php';
try{
    $store=new AsusUpdateStore();
    if($mode==='shell-authorize'){
        if(count($arguments)!==1)exit(1);
        exit((new AsusUpdateGuard($store))->authorize($arguments[0])?0:1);
    }
    if($mode==='shell-init'){
        if($arguments!==[])exit(1);
        try{$f=$store->lease('apply.lock',true);fclose($f);}catch(RuntimeException $e){if($e->getMessage()!=='busy')throw $e;}
        exit(0);
    }
    if($mode==='shell-check'){
        if($arguments!==[])exit(1);$f=(new AsusUpdateGuard($store))->mutationLease();fclose($f);exit(0);
    }
    if(count($arguments)!==1||!preg_match('/^[a-f0-9]{32}$/D',$arguments[0]))exit(1);$id=$arguments[0];
    if($mode==='guard-check'){
        $command=[PHP_BINARY,'-n','-d','extension=/opt/lib/php8/openssl.so','-d','register_argc_argv=1','-q','-f',__FILE__,'--','check',$id];
        (new AsusUpdateCheck($store))->guard($id,$command);exit(0);
    }
    if($mode==='check'){(new AsusUpdateCheck($store))->complete($id);exit(0);}
    if($mode==='guard-apply'){
        $runtime=AsusUpdateRuntime::load($store->path('operations/'.$id.'/runtime'));
        $job=$store->readOperation($id);if(($job['runtime_digest']??null)!==$runtime['digest'])exit(1);
        (new AsusUpdateWatchdog($store))->run($id,array_merge($runtime['argv'],['--','apply',$id]),AsusUpdateStore::uptime()+240);exit(0);
    }
    if($mode==='guard-prepare'){
        $command=[PHP_BINARY,'-n','-d','extension=/opt/lib/php8/openssl.so','-d','register_argc_argv=1','-q','-f',__FILE__,'--','prepare',$id];
        (new AsusUpdateWatchdog($store))->run($id,$command,AsusUpdateStore::uptime()+240);exit(0);
    }
    if($mode==='prepare'){
        (new AsusUpdatePrepare($store,null,[],null,new AsusUpdateDeadline($store,$id)))->completePrepare($id,fn(string $operation,array $environment)=>AsusUpdateRuntime::stage($store->path('operations/'.$operation.'/runtime')));exit(0);
    }
    if($mode==='apply'){(new AsusUpdateWorker($store,new AsusUpdatePrepare($store,null,[],null,new AsusUpdateDeadline($store,$id))))->apply($id);exit(0);}
    if($mode==='preflight'){
        try{(new AsusUpdateWorker($store))->preflight($id);exit(0);}
        catch(Throwable $e){$store->writeFile('operations/'.$id.'/preflight-error.json',json_encode(['code'=>AsusUpdatePrepare::code($e)],JSON_THROW_ON_ERROR));exit(1);}
    }
}catch(Throwable $e){exit(1);}exit(1);
