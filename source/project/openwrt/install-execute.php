<?php
require_once __DIR__.'/install-prepare.php';

/** Root bootstrap execution. Healthy upgrades use the installed sealed worker. */
final class NfqwsOpenWrtInstallExecute
{
    public static function prepared(string $work,?string $key=null,?string $schema=null):array
    {
        $local=new AsusUpdateStore($work);$raw=$local->readFile('plan.json',262144);
        if($raw===null)throw new RuntimeException('invalid_state');$saved=json_decode($raw,true,32,JSON_THROW_ON_ERROR);
        $firmware=NfqwsOpenWrtUpdateEnvironment::firmware((string)file_get_contents('/etc/openwrt_release'));
        $plan=NfqwsOpenWrtInstallPlan::select($saved['manifest']??'',$saved['signature']??'',$key??NFQWS_NATIVE_INSTALL_KEY,(string)file_get_contents('/etc/openwrt_release'),NfqwsOpenWrtInstallState::read($firmware),$schema??$work.'/work/native-schema.json');
        foreach(['action','firmware','candidate','installed']as $name)if(($saved[$name]??null)!==$plan[$name])throw new RuntimeException('stale_revision');
        if(!in_array($plan['action'],['current','repair_required'],true)){
            $path=$saved['archive']??null;if(!is_string($path)||$path!==$work.'/work/'.$plan['candidate']['package']['filename'])throw new RuntimeException('invalid_state');
            $record=NfqwsOpenWrtUpdatePackage::inspect($path,$plan['candidate'],$firmware,$saved['keys']??null);
            if($record!==($saved['record']??null))throw new RuntimeException('invalid_package');
            if(NfqwsOpenWrtUpdateManager::missing($firmware,$record['depends'],true))throw new RuntimeException('missing_dependencies');
        }
        return $saved;
    }
    /** No execution deadline: a native manager must finish its own transaction. */
    private static function manager(array $argv,string $log):int
    {
        $p=@proc_open($argv,[0=>['file','/dev/null','r'],1=>['file',$log,'a'],2=>['file',$log,'a']],$pipes,'/',
            ['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C','LC_ALL'=>'C','HOME'=>'/']);
        if(!is_resource($p))throw new RuntimeException('launch_failed');return proc_close($p);
    }
    public static function direct(string $work,?string $key=null,?string $schema=null):array
    {
        $plan=self::prepared($work,$key,$schema);$action=$plan['action'];
        // An installed payload can own DNS/services. Its sealed coordinator is
        // mandatory; never fall through to a less protected raw upgrade.
        if(!in_array($action,['install','configure'],true))throw new RuntimeException('repair_required');
        $store=new AsusUpdateStore('/tmp/nfqws2-native-state/updates');$store->reconcile(AsusUpdateStore::boot(),AsusUpdateStore::uptime());
        if($store->status()['active']!==null||NfqwsOpenWrtManualContext::activeManager()!==null)throw new RuntimeException('busy');
        $environment=$plan['firmware'];$before=NfqwsOpenWrtUpdateManager::installed($environment,true);
        if($action==='configure')$argv=['/bin/opkg','configure','nfqws2-native'];
        else{
            $argv=NfqwsOpenWrtUpdateManager::argv($plan['archive'],$environment,$before,$plan['record'],$plan['keys'],true,true);
            $simulation=NfqwsPlatform::run($argv,30);
            if($simulation['status']!==0)throw new RuntimeException('dependency_change');
            NfqwsOpenWrtUpdateManager::plan(implode("\n",$simulation['output']),$environment['format'],$plan['record']);
            $argv=NfqwsOpenWrtUpdateManager::argv($plan['archive'],$environment,$before,$plan['record'],$plan['keys'],false,true);
        }
        if(self::manager($argv,$work.'/manager.log')!==0)throw new RuntimeException('install_failed');
        $own=NfqwsOpenWrtInstallState::read($environment);$after=NfqwsOpenWrtUpdateManager::installed($environment,true);
        if($after!==$before)throw new RuntimeException('dependency_change');
        if(($own['version']??null)!==$plan['candidate']['package_version']||($own['state']??null)!=='installed'||($own['build']??null)!==$plan['candidate']['build'])throw new RuntimeException('version_mismatch');
        return ['state'=>'installed','version'=>$own['version']];
    }
}
