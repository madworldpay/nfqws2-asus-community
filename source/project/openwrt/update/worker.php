<?php
// Fixed root CGI entry outside the public directory, copied into sealed staging.
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(2);
$args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);
if(count($args)!==2||!preg_match('/^[a-f0-9]{32}$/D',$args[1]??'')||!in_array($args[0],['check','prepare','apply','guard-check','guard-prepare','guard-apply','hook-verify','hook-capture','hook-postinstall','hook-apk-precommit'],true))exit(2);
[$mode,$id]=$args;umask(0077);$app=is_dir(__DIR__.'/app')?__DIR__.'/app':'/usr/share/nfqws2-web';
require_once $app.'/openwrt-update-worker.php';require_once $app.'/openwrt-package-quiesce.php';require_once $app.'/openwrt-apk-command.php';require_once $app.'/update-watchdog.php';require_once $app.'/update-check.php';
if(!NfqwsPlatform::native())exit(2);
try{
    $store=new AsusUpdateStore();$resources=is_dir(__DIR__.'/resources')?__DIR__.'/resources':'/usr/share/nfqws2';
    $prepare=new NfqwsOpenWrtUpdatePrepare($store,null,['resources'=>$resources],null,in_array($mode,['prepare','apply'],true)?new AsusUpdateDeadline($store,$id):null);
    $command=static fn(string $operation)=>['/usr/bin/php8-cgi','-d','register_argc_argv=1','-q','-f',__FILE__,'--',$operation,$id];
    if($mode==='guard-check'){(new AsusUpdateCheck($store,$prepare))->guard($id,$command('check'));exit(0);}
    if($mode==='check'){(new AsusUpdateCheck($store,$prepare))->complete($id);exit(0);}
    if($mode==='guard-prepare'){(new AsusUpdateWatchdog($store))->run($id,$command('prepare'),AsusUpdateStore::uptime()+240);exit(0);}
    if($mode==='guard-apply'){
        $runtime=NfqwsOpenWrtUpdateRuntime::load($store->path('operations/'.$id.'/runtime'));
        if(($store->readOperation($id)['runtime_digest']??null)!==$runtime['digest'])throw new RuntimeException('runtime_changed');
        (new AsusUpdateWatchdog($store))->run($id,$command('apply'),AsusUpdateStore::uptime()+240);exit(0);
    }
    if($mode==='prepare'){$prepare->completePrepare($id,fn($operation)=>NfqwsOpenWrtUpdateRuntime::stage($store->path('operations/'.$operation.'/runtime')));exit(0);}
    if($mode==='apply'){(new NfqwsOpenWrtUpdateWorker($store,$prepare))->apply($id);exit(0);}
    if($mode==='hook-apk-precommit'){
        $g=new NfqwsOpenWrtUpdateGuard($store);$end=AsusUpdateStore::uptime()+2;
        do{$t=$g->context($id);if($g->authorize('hook-prerm'))break;if(AsusUpdateStore::uptime()>=$end)throw new RuntimeException('busy');usleep(10000);}while(true);
        $manager=NfqwsOpenWrtApkCommand::manager();if($manager['identity']!==$t['manager'])throw new RuntimeException('invalid_state');
        $plan=NfqwsPlatform::run(NfqwsOpenWrtApkCommand::simulation($manager['argv']),30);
        if($plan['status']!==0||NfqwsOpenWrtApkCommand::affects(implode("\n",$plan['output']))!=='upgrade')throw new RuntimeException('dependency_change');
        (new NfqwsOpenWrtPackageQuiesce($store))->run('upgrade');exit(0);
    }
    $active=(new NfqwsOpenWrtUpdateHook($store))->run(substr($mode,5));exit($mode==='hook-postinstall'&&!$active?10:0);
}catch(Throwable $e){
    if(isset($store)&&str_starts_with($mode,'hook-')){try{$store->writeFile('operations/'.$id.'/preflight-error.json',json_encode(['code'=>AsusUpdatePrepare::code($e)],JSON_THROW_ON_ERROR));}catch(Throwable $ignored){}}
    file_put_contents('php://stderr',"Native update: ".AsusUpdatePrepare::code($e)."\n");exit(1);
}
