<?php
// The installer stages this fixed entry with its own source, key and verifier.
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(2);
// Only this root, non-HTTP worker opts out of CGI CPU time; the guardian still
// bounds pre-install work and respects the native manager critical boundary.
set_time_limit(0);
$args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);$mode=array_shift($args);
require_once __DIR__.'/app/update-worker.php';
require_once __DIR__.'/app/update-watchdog.php';
require_once __DIR__.'/app/update-github.php';
try{
    umask(0077);$store=new AsusUpdateStore();$key=file_get_contents(__DIR__.'/resources/update-release-key.pem');
    $id=$args[0]??null;if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id))exit(2);
    if($mode==='preflight'){
        if(count($args)!==2||!in_array($args[1],['install','configure','rollback','rollback-verify'],true))exit(2);
        try{$prepare=new AsusUpdatePrepare($store,new AsusGithubUpdateSource(),['resources'=>__DIR__.'/resources'],$key);(new AsusUpdateWorker($store,$prepare))->preflight($id,$args[1]);exit(0);}
        catch(Throwable $e){$store->writeFile('operations/'.$id.'/preflight-error.json',json_encode(['code'=>AsusUpdatePrepare::code($e)],JSON_THROW_ON_ERROR));exit(1);}
    }
    if(count($args)!==1)exit(2);
    $runtime=AsusUpdateRuntime::load(__DIR__);if($runtime['digest']!==($store->readOperation($id)['runtime_digest']??null))throw new RuntimeException('runtime_changed');
    if($mode==='rollback-finalize'){(new AsusUpdateWorker($store))->rollbackFinalize($id);exit(0);}
    if($mode==='guard-apply'){
        (new AsusUpdateWatchdog($store))->run($id,array_merge($runtime['argv'],['--','apply',$id]),AsusUpdateStore::uptime()+240);exit(0);
    }
    if($mode==='apply'){
        $prepare=new AsusUpdatePrepare($store,new AsusGithubUpdateSource(),['resources'=>__DIR__.'/resources'],$key,new AsusUpdateDeadline($store,$id));
        $job=(new AsusUpdateWorker($store,$prepare))->apply($id);exit($job['state']==='succeeded'?0:1);
    }
}catch(Throwable $e){file_put_contents('php://stderr','ASUS bootstrap worker: '.AsusUpdatePrepare::code($e)."\n");}exit(1);
