<?php
/** Closed local entrypoint; no source URL, key, package or command arguments. */
final class NfqwsOpenWrtInstallMain
{
    public static function run(array $args):int
    {
        if(isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))return 2;
        if(count($args)!==2||!in_array($args[0],['prepare','describe','run','status'],true))return 2;
        [$mode,$work]=$args;umask(0077);$local=new AsusUpdateStore($work);
        try{
            if($mode==='prepare'){$r=(new NfqwsOpenWrtInstallPrepare($work.'/work'))->run();$local->writeFile('plan.json',json_encode($r,JSON_THROW_ON_ERROR));return 0;}
            $r=json_decode($local->readFile('plan.json',262144)??'',true,32,JSON_THROW_ON_ERROR);
            if($mode==='describe'){
                if(!in_array($r['action']??null,['install','upgrade','configure','current','repair_required'],true))throw new RuntimeException('invalid_state');
                echo $r['action'],"\n",$r['candidate']['package_version'],"\n",implode(' ',$r['missing']),"\n";return 0;
            }
            if($mode==='status'){
                $result=json_decode($local->readFile('result.json')??'',true,32,JSON_THROW_ON_ERROR);
                if(($result['state']??null)==='updating'){
                    $updates=new AsusUpdateStore('/tmp/nfqws2-native-state/updates');$updates->reconcile(AsusUpdateStore::boot(),AsusUpdateStore::uptime());$job=$updates->readOperation($result['id']);
                    echo $job['state'],"\n",$job['code']??'',"\n";return 0;
                }echo $result['state']??'failed',"\n";return 0;
            }
            $r=NfqwsOpenWrtInstallExecute::prepared($work);
            if($r['action']==='upgrade'){
                if(($r['installed']['state']??null)!=='installed')throw new RuntimeException('repair_required');
                $local->writeFile('update.php',NFQWS_NATIVE_INSTALL_BRIDGE);
                $p=proc_open(['/usr/bin/php8-cgi','-d','register_argc_argv=1','-q','-f',$work.'/update.php','--',$work],[0=>['file','/dev/null','r'],1=>['file',$work.'/coordinator.log','a'],2=>['file',$work.'/coordinator.log','a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C','LC_ALL'=>'C','HOME'=>'/']);
                if(!is_resource($p)||proc_close($p)!==0)throw new RuntimeException('install_failed');
            }else{$result=NfqwsOpenWrtInstallExecute::direct($work);$local->writeFile('result.json',json_encode($result,JSON_THROW_ON_ERROR));}
            return 0;
        }catch(Throwable $e){file_put_contents('php://stderr',"NFQWS2 OpenWrt: ".$e->getMessage()."\n");return 1;}
    }
}
$args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);exit(NfqwsOpenWrtInstallMain::run($args));
