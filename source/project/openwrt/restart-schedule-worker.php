<?php
// A fixed cron entry, outside the document root. No request-selected commands.
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD'])||
    !preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(2);
require_once '/usr/share/nfqws2-web/restart-schedule.php';
try{
    $settings=(new NfqwsRestartSchedule())->read(false);
    if(!$settings['enabled']&&!$settings['watchdog_enabled'])exit(0);
    require_once '/usr/share/nfqws2-web/update-guard.php';
    require_once '/usr/share/nfqws2-web/import-store.php';
    $lease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
    (new AsusImportStore())->locked(function(){
        // Serialize with imports, form saves and another minute tick. The init
        // action then uses procd's core mutex and rechecks the running process.
        $result=NfqwsPlatform::run(['/etc/init.d/nfqws2-native','scheduledrestart'],45);
        if($result['status']!==0)throw new RuntimeException('restart_failed');
    });
    exit(0);
}catch(Throwable $e){exit($e->getMessage()==='busy'?0:1);}
