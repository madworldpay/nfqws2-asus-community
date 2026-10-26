<?php
if (!in_array(PHP_SAPI,['cli','cgi-fcgi'],true) || isset($_SERVER['REQUEST_METHOD'])) exit(1);
$uid=@file_get_contents('/proc/self/status');
if (!is_string($uid) || !preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',$uid)) exit(1);
$args=$argv;array_shift($args);if (($args[0]??null)==='--') array_shift($args);
if (count($args)!==1 || !in_array($args[0],['status','rollback','upgrade','remove','resume'],true)) exit(2);
require_once '/opt/share/nfqws-asus-web/smartdns-lifecycle.php';
$lease=null;$resumeLock=null;
try {
    $mode=$args[0];$store=new AsusSmartDnsStore();$backend=new AsusSmartDnsNativeBackend($store,new AsusSmartDnsInstaller());$jobs=new AsusSmartDnsConfigJobs($store,$backend);
    if ($mode==='status') {echo json_encode(['status'=>$jobs->status(),'resume_saved'=>$store->intent()!==null],JSON_THROW_ON_ERROR)."\n";exit(0);}
    // Fresh package installation/startup is entirely inert without prior consent.
    if ($mode==='resume' && $store->intent()===null) exit(0);
    $updates=new AsusUpdateGuard(new AsusUpdateStore());
    $authorized=in_array($mode,['upgrade','remove'],true) && $updates->authorize('dns-restore');
    if (!$authorized) {
        $end=hrtime(true)+($mode==='resume'?60000000000:1000000000);
        do {
            try {$lease=$updates->mutationLease();break;}
            catch (Throwable $e) {if ($e->getMessage()!=='busy' || hrtime(true)>=$end) throw $e;usleep(100000);}
        } while (true);
    }
    $lifecycle=new AsusSmartDnsLifecycle($store,$backend);
    if ($mode==='resume') {
        $path=$store->directory(false).'/resume.lock';$s=@lstat($path);
        if ($s && (($s['mode']&0170000)!==0100000 || $s['uid']!==0 || $s['nlink']!==1 || ($s['mode']&0777)!==0600)) throw new RuntimeException('invalid_state');
        $mask=umask(0077);try {$resumeLock=@fopen($path,'c');}finally {umask($mask);}
        if (!is_resource($resumeLock) || !flock($resumeLock,LOCK_EX|LOCK_NB)) throw new RuntimeException('busy');
        $result=$lifecycle->resume();
    } elseif (in_array($mode,['upgrade','remove'],true)) $result=$lifecycle->stop($mode);
    else {
        $jobs->reconcile();$job=$store->transaction();
        if ($job===null) {$result=$jobs->status();if ($jobs->blocksUpdate()) throw new RuntimeException('invalid_state');}
        else $result=(new AsusSmartDnsConnection($store,$backend->dependencies()))->rollback($job['request_id']);
        if (in_array($result['state'],['rolled_back','idle'],true)) $store->saveIntent(null);
    }
    echo json_encode($result,JSON_THROW_ON_ERROR)."\n";
    $ok=in_array($result['state'],['idle','rolled_back','confirmed','preview_ready','failed'],true);
    if (!$ok) exit(1);
} catch (Throwable $e) {
    $allowed=['busy','invalid_state','dns_restore_failed','storage_unavailable','guard_unavailable','timed_out','stale_baseline','baseline_unavailable'];
    echo json_encode(['error'=>in_array($e->getMessage(),$allowed,true)?$e->getMessage():'unavailable'])."\n";exit(1);
} finally {foreach ([$resumeLock,$lease] as $f) if (is_resource($f)) {flock($f,LOCK_UN);fclose($f);}}
