<?php
declare(strict_types=1);
require_once __DIR__.'/smartdns-config-api.php';
require_once __DIR__.'/smartdns-candidate.php';
require_once __DIR__.'/update-guard.php';

/** Manage the companion resolver on loopback. KeeneticOS owns the LAN DNS settings. */
final class NfqwsKeeneticSmartDns
{
    private const PORT=6054;
    private const CONFIG='keenetic-runtime.conf';
    private const PID='keenetic-runtime.pid';

    private static function process(?string $dir): ?array
    {
        if ($dir===null) return null;
        $file=$dir.'/'.self::PID;
        clearstatcache(true,$file);
        $s=@lstat($file);
        if (!$s) return null;
        if (($s['mode']&0170000)!==0100000 || $s['nlink']!==1 || $s['uid']!==0 || $s['size']>32)
            throw new RuntimeException('invalid_state');
        $raw=trim((string)file_get_contents($file));
        if (!preg_match('/^[1-9][0-9]{0,8}$/D',$raw)) return null;
        $identity=AsusDpiRuntime::identity((int)$raw);
        if ($identity===null) return null;
        $bundle=(new AsusSmartDnsInstaller())->binaryDirectory();
        $args=explode("\0",(string)@file_get_contents('/proc/'.$raw.'/cmdline',false,null,0,2048));
        if ($identity['exe']!==realpath($bundle.'/smartdns') ||
            !in_array($dir.'/'.self::CONFIG,$args,true) || !in_array($file,$args,true)) return null;
        return $identity;
    }

    private static function runtime(?string $dir): string
    {
        $process=self::process($dir);
        if ($process!==null)
            return AsusSmartDnsCandidate::ownsPorts($process['pid'],self::PORT) ? 'running' : 'unknown';
        $scan=(new AsusReportIO())->dnsProcesses();
        if (in_array('smartdns',$scan['names'],true)) return 'external';
        return $scan['state']==='available' ? 'stopped' : 'unknown';
    }

    private static function view(AsusSmartDnsStore $store): array
    {
        $draft=$store->draft();
        $enabled=$store->keeneticProfile();
        return ['status'=>$store->status(),'draft'=>$draft,'active_profile'=>$enabled,
            'draft_hash'=>$draft===null ? null : AsusSmartDnsProfile::hash($draft),
            'keenetic_profile_hash'=>$enabled===null ? null : AsusSmartDnsProfile::hash($enabled),
            'keenetic_runtime'=>self::runtime($store->directory())];
    }

    private static function stopProcess(string $dir): void
    {
        $process=self::process($dir);
        if ($process===null) return;
        if (AsusDpiRuntime::identity($process['pid'])!==$process) throw new RuntimeException('stale_state');
        NfqwsPlatform::run([NfqwsPlatform::busybox(),'kill','-TERM',(string)$process['pid']],2);
        for ($i=0;$i<40;$i++) {
            if (AsusDpiRuntime::identity($process['pid'])!==$process) return;
            usleep(100000);
        }
        throw new RuntimeException('runtime_stop_failed');
    }

    private static function startProcess(AsusSmartDnsStore $store,array $profile): void
    {
        $dir=$store->directory(true);
        $config=AsusSmartDnsProfile::render($profile,self::PORT)['config'];
        $state=self::runtime($dir);
        if ($state==='running' && hash_equals(hash('sha256',$config),(string)@hash_file('sha256',$dir.'/'.self::CONFIG))) return;
        if ($state!=='stopped') throw new RuntimeException('busy');
        $bundle=(new AsusSmartDnsInstaller())->binaryDirectory();
        $path=$dir.'/'.self::CONFIG;
        $tmp=$path.'.'.bin2hex(random_bytes(8));
        $mask=umask(0077);
        try {
            if (file_put_contents($tmp,$config)!==strlen($config) || !rename($tmp,$path))
                throw new RuntimeException('storage_unavailable');
        } finally {umask($mask); if (is_file($tmp)) unlink($tmp);}
        // The upstream binary loads its own relative musl interpreter from the bundle.
        $result=NfqwsPlatform::run([NfqwsPlatform::busybox(),'sh','-c',
            'cd "$1" && exec ./smartdns -c "$2" -p "$3" </dev/null >/dev/null 2>&1',
            'smartdns',$bundle,$path,$dir.'/'.self::PID],6);
        for ($i=0;$i<35;$i++) {
            $process=self::process($dir);
            if ($process!==null && AsusSmartDnsCandidate::ownsPorts($process['pid'],self::PORT)) return;
            if ($result['status']!==0) break;
            usleep(100000);
        }
        self::stopProcess($dir);
        throw new RuntimeException('launch_failed');
    }

    private static function write(callable $work): mixed
    {
        $lease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
        try {
            $tx=new AsusImportTransaction();
            return $tx->writer(function () use ($tx,$work) {$tx->recover(); return $work();});
        } finally {if (is_resource($lease)) {flock($lease,LOCK_UN);fclose($lease);}}
    }

    public static function dispatch(array $post,AsusSmartDnsStore $store): array
    {
        if ($post['cmd']==='smartdnsconfigstatus') return self::view($store);
        return self::write(function () use ($post,$store) {
            switch ($post['cmd']) {
                case 'smartdnsdraft':
                    return ['profile_hash'=>$store->saveDraft(AsusSmartDnsConfigApi::profile($post['profile']))];
                case 'smartdnskeeneticstart':
                    $profile=$store->draft();
                    if ($profile===null || !hash_equals(AsusSmartDnsProfile::hash($profile),$post['profile_hash']))
                        throw new RuntimeException('stale_draft');
                    self::startProcess($store,$profile);
                    try {$store->setKeeneticProfile($profile);}
                    catch (Throwable $e) {self::stopProcess($store->directory()); throw $e;}
                    break;
                case 'smartdnskeeneticstop':
                    $dir=$store->directory();
                    if ($dir!==null) self::stopProcess($dir);
                    $store->setKeeneticProfile(null);
                    break;
                default: throw new RuntimeException('unsupported_runtime');
            }
            return self::view($store);
        });
    }

    public static function boot(string $action): void
    {
        if (NfqwsPlatform::current()!=='keenetic-entware' || !in_array($action,['start','stop'],true))
            throw new RuntimeException('unsupported_runtime');
        $store=new AsusSmartDnsStore();
        if ($store->keeneticProfile()===null) return;
        self::write(function () use ($store,$action) {
            $profile=$store->keeneticProfile();
            if ($profile===null) return;
            if ($action==='start') self::startProcess($store,$profile);
            else self::stopProcess($store->directory());
        });
    }
}

if (isset($argv[0],$argv[1]) && empty($_SERVER['REQUEST_METHOD']) &&
    realpath($argv[0])===__FILE__) {
    try {NfqwsKeeneticSmartDns::boot($argv[1]);}
    catch (Throwable $e) {error_log('Keenetic SmartDNS: '.$e->getMessage());exit(1);}
}
