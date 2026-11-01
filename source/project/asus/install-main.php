<?php
/** Trusted bootstrap coordinator. A pending own release finishes before latest. */
require_once __DIR__.'/app/update-worker.php';
require_once __DIR__.'/app/update-watchdog.php';
require_once __DIR__.'/app/update-github.php';
final class NfqwsAsusInstallMain
{
    private static function prepare(AsusUpdateStore $store):AsusUpdatePrepare
    {return new AsusUpdatePrepare($store,new AsusGithubUpdateSource(),['resources'=>__DIR__.'/resources'],file_get_contents(__DIR__.'/resources/update-release-key.pem'));}
    private static function stage(AsusUpdateStore $store,AsusUpdatePrepare $prepare,array $checked):array
    {
        if(($checked['state']??null)!=='available')throw new RuntimeException($checked['code']??'recovery_required');
        $lease=(new AsusUpdateGuard($store))->mutationLease();
        try{
            // A prior SSH may have ended after staging and before launching.
            // Replace its unapplied plan so this installer's trusted code runs.
            $store->withLock(function()use($store){
                $active=$store->status()['active'];
                $state=$active['state']??null;
                if(!in_array($state,['prepared','preparing'],true))return;
                if($state==='preparing'){
                    $since=$active['prepare_launch_uptime']??$active['created_uptime']??null;
                    if(!is_numeric($since)||!is_finite((float)$since)||AsusUpdateStore::uptime()-(float)$since<15)throw new RuntimeException('busy');
                }
                $work=$store->lease('operations/'.$active['id'].'/work.lock');
                try{
                    $raw=$store->readFile('operations/'.$active['id'].'/guard.json',4096);
                    $guard=$raw===null?[]:json_decode($raw,true,16,JSON_THROW_ON_ERROR);
                    if(!is_array($guard))throw new RuntimeException('invalid_state');
                    foreach([$active['identity']??null,$guard['guardian']??null,$guard['child']??null] as $identity){
                        if($identity!==null&&!is_array($identity))throw new RuntimeException('invalid_state');
                        if(is_array($identity)&&AsusUpdateLifecycle::alive($identity))throw new RuntimeException('busy');
                    }
                    $store->update($active['id'],['state'=>'interrupted','code'=>'interrupted']);
                }finally{flock($work,LOCK_UN);fclose($work);}
            });
            $job=$prepare->reserveCached($checked['candidate']['revision'],bin2hex(random_bytes(16)));$store->claimPrepare($job['id']);
        }
        finally{flock($lease,LOCK_UN);fclose($lease);}
        $job=$prepare->completePrepare($job['id'],function($id,$env)use($store){
            $family=$env['family']==='armv7'?'armv7':'aarch64';
            return AsusUpdateRuntime::stage($store->path('operations/'.$id.'/runtime'),['application'=>__DIR__.'/app','entry'=>__DIR__.'/worker.php','launcher'=>__DIR__.'/launchers/'.$family.'-opkg-launch','resources'=>__DIR__.'/resources']);
        });
        if($job['state']!=='prepared')throw new RuntimeException($job['code']??'install_failed');return $job;
    }
    private static function apply(AsusUpdateStore $store,array $job):array
    {
        $lease=(new AsusUpdateGuard($store))->mutationLease();
        try{$claim=$store->claimApply($job['id'],$job['revision'],bin2hex(random_bytes(16)));}
        finally{flock($lease,LOCK_UN);fclose($lease);}
        if(!$claim['launch'])throw new RuntimeException('busy');
        $runtime=AsusUpdateRuntime::load($store->path('operations/'.$job['id'].'/runtime'));
        if($runtime['digest']!==$job['runtime_digest'])throw new RuntimeException('runtime_changed');
        $p=proc_open(array_merge($runtime['argv'],['--','guard-apply',$job['id']]),[0=>['file','/dev/null','r'],1=>['file',__DIR__.'/coordinator.log','a'],2=>['file',__DIR__.'/coordinator.log','a']],$pipes,'/',['PATH'=>'/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C','LC_ALL'=>'C','HOME'=>'/']);
        if(!is_resource($p)||proc_close($p)!==0)throw new RuntimeException('install_failed');
        $job=$store->readOperation($job['id']);if($job['state']!=='succeeded')throw new RuntimeException($job['code']??'install_failed');return $job;
    }
    public static function run(array $args):int
    {
        try{
            if(count($args)!==1||!in_array($args[0],['prepare','check','describe','run','status'],true))return 2;
            $mode=$args[0];$local=new AsusUpdateStore(__DIR__);$store=new AsusUpdateStore();
            if($mode==='prepare'||$mode==='check'){
                $prepare=self::prepare($store);$checked=$prepare->check(true);
                if(!in_array($checked['state']??null,['current','available'],true))throw new RuntimeException($checked['code']??'recovery_required');
                if($mode==='check'){
                    if($checked['state']==='available'){$env=$prepare->environment();$path=__DIR__.'/check-package.ipk';$source=new AsusGithubUpdateSource();$source->download($checked['candidate']['package'],$path);AsusUpdatePackage::inspect($path,$checked['candidate'],$env['status'],$env['abi'],$env['machine'],$env['opt'],$env['owner']);}
                    echo 'Подпись и пакет проверены. Установка не запускалась.',"\n";return 0;
                }
                $job=$checked['state']==='current'?null:self::stage($store,$prepare,$checked);
                $local->writeFile('plan.json',json_encode(['checked'=>$checked,'job'=>$job],JSON_THROW_ON_ERROR));return 0;
            }
            $plan=json_decode($local->readFile('plan.json')??'',true,32,JSON_THROW_ON_ERROR);
            if($mode==='describe'){echo $plan['checked']['candidate']['action']??($plan['job']===null?'current':'install'),"\n",$plan['checked']['candidate']['package_version']??$plan['checked']['installed_version'],"\n";return 0;}
            if($mode==='status'){$result=json_decode($local->readFile('result.json')??'',true,32,JSON_THROW_ON_ERROR);echo $result['state'],"\n",$result['version']??'',"\n";return 0;}
            $job=$plan['job'];if($job===null){$local->writeFile('result.json',json_encode(['state'=>'succeeded','version'=>$plan['checked']['installed_version']],JSON_THROW_ON_ERROR));return 0;}
            $configure=($plan['checked']['candidate']['action']??null)==='configure';$job=self::apply($store,$job);
            if($configure){
                // The exact old release source must not leak into the next phase.
                $prepare=self::prepare($store);$checked=$prepare->check(true);
                if($checked['state']==='available'){
                    if(($checked['candidate']['action']??'install')!=='install')throw new RuntimeException('recovery_required');
                    $job=self::apply($store,self::stage($store,$prepare,$checked));
                }elseif($checked['state']!=='current')throw new RuntimeException($checked['code']??'install_failed');
            }
            $version=self::prepare($store)->environment()['installed'];
            $local->writeFile('result.json',json_encode(['state'=>'succeeded','version'=>$version,'id'=>$job['id']],JSON_THROW_ON_ERROR));return 0;
        }catch(Throwable $e){
            $code=AsusUpdatePrepare::code($e);if(isset($local))$local->writeFile('result.json',json_encode(['state'=>'failed','code'=>$code],JSON_THROW_ON_ERROR));
            file_put_contents('php://stderr','ASUS bootstrap: '.$code."\n");return 1;
        }
    }
}
exit(NfqwsAsusInstallMain::run([$nfqwsAsusMode]));
