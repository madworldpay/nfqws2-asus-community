<?php
// Trusted bridge emitted by the installer; runs in a separate PHP process so
// the installed coordinator owns its own class definitions and sealed runtime.
if(isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(2);
$args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);if(count($args)!==1)exit(2);
umask(0077);require_once '/usr/share/nfqws2-web/openwrt-update-worker.php';require_once '/usr/share/nfqws2-web/openwrt-update-launch.php';require_once '/usr/share/nfqws2-web/update-dispatch.php';
try{
    if(!NfqwsPlatform::native())throw new RuntimeException('unsupported_abi');$local=new AsusUpdateStore($args[0]);
    $plan=json_decode($local->readFile('plan.json',262144)??'',true,32,JSON_THROW_ON_ERROR);
    if(($plan['action']??null)!=='upgrade'||($plan['installed']['state']??null)!=='installed')throw new RuntimeException('repair_required');
    $path=$plan['archive']??'';$expected=$args[0].'/work/'.($plan['candidate']['package']['filename']??'');if($path!==$expected)throw new RuntimeException('invalid_state');
    AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||!is_file($path)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==0600)throw new RuntimeException('invalid_state');
    $source=new NfqwsOpenWrtInstallLocalSource($plan);
    $store=new AsusUpdateStore();$prepare=new NfqwsOpenWrtUpdatePrepare($store,$source);$fresh=$prepare->check(true);
    if($fresh['state']!=='available'||$fresh['candidate']!==$plan['candidate'])throw new RuntimeException('stale_revision');
    $lease=(new NfqwsOpenWrtUpdateGuard($store))->mutationLease();
    try{$job=$prepare->reserveCached($fresh['candidate']['revision'],bin2hex(random_bytes(16)));$store->claimPrepare($job['id']);}finally{flock($lease,LOCK_UN);fclose($lease);}
    $job=$prepare->completePrepare($job['id'],fn($id)=>NfqwsOpenWrtUpdateRuntime::stage($store->path('operations/'.$id.'/runtime')));
    if($job['state']!=='prepared')throw new RuntimeException($job['code']??'install_failed');
    $job=(new AsusUpdateDispatch($store,$prepare))->apply($job['id'],$job['revision'],bin2hex(random_bytes(16)));
    if(!in_array($job['state'],['applying','succeeded'],true))throw new RuntimeException($job['code']??'launch_failed');
    $local->writeFile('result.json',json_encode(['state'=>'updating','id'=>$job['id']],JSON_THROW_ON_ERROR));exit(0);
}catch(Throwable $e){file_put_contents('php://stderr',"Native bootstrap coordinator: ".AsusUpdatePrepare::code($e)."\n");exit(1);}
