<?php
require_once __DIR__.'/update-worker.php';

/** Short HTTP coordination; detached children perform all network/installation. */
final class AsusUpdateDispatch
{
    private NfqwsUpdatePreparation $prepare;
    public function __construct(private AsusUpdateStore $store,?NfqwsUpdatePreparation $prepare=null,private array $options=[])
    {$this->prepare=$prepare??new AsusUpdatePrepare($store);}
    private function guard(): AsusUpdateGuard
    {return new AsusUpdateGuard($this->store,$this->options['owner']??0,$this->options['opkg']??'/opt/bin/opkg');}
    private function executable(string $path,int $owner): void
    {
        AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0022)!==0||!is_executable($path))throw new RuntimeException('invalid_state');
    }
    private function launch(string $id,string $kind): void
    {
        $busybox=$this->options['busybox']??AsusUpdateStore::installed('libexec/nfqws2-asus/busybox');$this->executable($busybox,0);
        if($kind==='apply'){
            $runtime=AsusUpdateRuntime::load($this->store->path('operations/'.$id.'/runtime'),$this->options['owner']??0);
            if($runtime['digest']!==($this->store->readOperation($id)['runtime_digest']??null))throw new RuntimeException('runtime_changed');
            $entry=$this->store->path('operations/'.$id.'/runtime/run.sh');
        }elseif($kind==='prepare')$entry=AsusUpdateStore::installed('lib/nfqws2-asus/update/worker.sh');else throw new RuntimeException('invalid_state');
        $this->executable($entry,$this->options['owner']??0);
        // The claim and all short/shared locks have been released before this
        // fork. Closing the browser cannot close this detached worker's lifetime.
        $p=@proc_open([$busybox,'start-stop-daemon','-S','-b','-p',$this->store->path('operations/'.$id.'/unused-guard.pid'),'-x',$busybox,'--','sh',$entry,$id],
            [0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',
            ['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C','LC_ALL'=>'C','HOME'=>'/']);
        if(!is_resource($p)||proc_close($p)!==0)throw new RuntimeException('launch_failed');
    }
    private function launchOrInterrupt(string $id,string $kind): void
    {
        try{$this->launch($id,$kind);}catch(Throwable $e){$job=$this->store->readOperation($id);if(in_array($job['state'],['preparing','applying'],true))$this->store->update($id,['state'=>'interrupted','code'=>AsusUpdatePrepare::code($e)]);}
    }
    public function prepare(string $revision,string $requestId): array
    {
        $f=$this->guard()->mutationLease();try{$job=$this->prepare->reserveCached($revision,$requestId);$launch=$this->store->claimPrepare($job['id']);}finally{flock($f,LOCK_UN);fclose($f);}
        if($launch)$this->launchOrInterrupt($job['id'],'prepare');return $this->store->readOperation($job['id']);
    }
    public function apply(string $id,string $revision,string $requestId): array
    {
        $job=$this->store->readOperation($id);
        if(($job['apply_request_id']??null)===$requestId){if($job['revision']!==$revision)throw new RuntimeException('request_conflict');return $this->status($id);}
        $f=$this->guard()->mutationLease();try{$claim=$this->store->claimApply($id,$revision,$requestId);}finally{flock($f,LOCK_UN);fclose($f);}
        if($claim['launch'])$this->launchOrInterrupt($id,'apply');return $this->store->readOperation($id);
    }
    public function status(string $id): array
    {
        $this->store->reconcile(AsusUpdateStore::boot(),AsusUpdateStore::uptime());$job=$this->store->readOperation($id);
        if(!in_array($job['state'],['preparing','applying'],true))return $job;
        $raw=$this->store->readFile('operations/'.$id.'/guard.json',4096);$guard=$raw===null?null:json_decode($raw,true,16,JSON_THROW_ON_ERROR);
        foreach([$job['identity']??null,$guard['guardian']??null,$guard['child']??null] as $identity)if(is_array($identity)&&AsusUpdateLifecycle::alive($identity))return $job;
        $since=$job['state']==='preparing'?($job['prepare_launch_uptime']??$job['created_uptime']):($job['apply_uptime']??$job['created_uptime']);
        if(AsusUpdateStore::uptime()-$since<15&&!isset($job['identity']))return $job;
        return $this->store->update($id,['state'=>'interrupted','code'=>'interrupted']);
    }
}
