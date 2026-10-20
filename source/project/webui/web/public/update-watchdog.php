<?php
require_once __DIR__.'/update-lifecycle.php';

/** Owns only its direct worker child. Never terminates an installer or daemon. */
final class AsusUpdateWatchdog
{
    public function __construct(private AsusUpdateStore $store,private int $owner=0) {}
    private function interrupt(string $id,string $code): void
    {
        $this->store->withRetryLock(function()use($id,$code){$job=$this->store->readOperation($id);
            if(in_array($job['state'],['preparing','applying'],true))$this->store->update($id,['state'=>'interrupted','code'=>$code]);
        });
    }
    private function boundary(string $id): bool
    {
        $raw=$this->store->readFile('operations/'.$id.'/boundary.json',1024);if($raw===null)return false;
        try{$value=json_decode($raw,true,4,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if($value!==['phase'=>'installing'])throw new RuntimeException('invalid_state');return true;
    }
    private function deadline(string $id,float $overall): float
    {
        $raw=$this->store->readFile('operations/'.$id.'/network.json',1024);if($raw===null)return $overall;
        try{$value=json_decode($raw,true,4,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(!is_array($value)||array_keys($value)!==['deadline']||($value['deadline']!==null&&(!is_numeric($value['deadline'])||!is_finite((float)$value['deadline'])||$value['deadline']<0)))throw new RuntimeException('invalid_state');
        return $value['deadline']===null?$overall:min($overall,(float)$value['deadline']);
    }
    /** argv is produced by trusted installed/staged code, never from HTTP. */
    public function run(string $id,array $argv,float $deadline): void
    {
        $job=$this->store->readOperation($id);if(!in_array($job['state'],['preparing','applying'],true)||$job['boot_id']!==AsusUpdateStore::boot())throw new RuntimeException('invalid_state');
        if(!is_finite($deadline)||$deadline<AsusUpdateStore::uptime()||$deadline>AsusUpdateStore::uptime()+300||count($argv)<1||count($argv)>64)throw new RuntimeException('invalid_state');
        foreach($argv as $arg)if(!is_string($arg)||strlen($arg)>8192||strpbrk($arg,"\r\n\0")!==false)throw new RuntimeException('invalid_state');
        $p=@proc_open($argv,[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',
            ['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C','LC_ALL'=>'C','HOME'=>'/']);
        if(!is_resource($p))throw new RuntimeException('launch_failed');$status=proc_get_status($p);$pid=(int)$status['pid'];$identity=AsusUpdateLifecycle::identity($pid);$reason='interrupted';
        try{
            $this->store->writeFile('operations/'.$id.'/guard.json',json_encode(['schema'=>1,'guardian'=>AsusUpdateLifecycle::identity(getmypid()),'child'=>$identity,'deadline'=>$deadline],JSON_THROW_ON_ERROR));
            // Both stream leases and proc_open descriptors close on exec. The
            // child's final preflight opens its own independent critical lease.
            while($status['running']){
                if(AsusUpdateStore::uptime()>=$this->deadline($id,$deadline)){
                    $f=null;try{$f=$this->store->lease('operations/'.$id.'/critical.lock');}
                    catch(RuntimeException $e){if($e->getMessage()!=='busy')throw $e;}
                    if($f!==null)try{
                        if(!$this->boundary($id)){
                            $this->store->writeFile('operations/'.$id.'/cancel.json',json_encode(['code'=>'timed_out'],JSON_THROW_ON_ERROR));$reason='timed_out';
                            $now=AsusUpdateLifecycle::identity($pid);
                            // Direct unreaped child + boot/start/uid continuity;
                            // exec can legitimately change its executable name.
                            if($identity!==null&&$now!==null&&$identity['start_ticks']===$now['start_ticks']&&$identity['boot_id']===$now['boot_id']&&$now['uid']===$this->owner){
                                proc_terminate($p,15);$end=AsusUpdateStore::uptime()+1;
                                do{usleep(10000);$status=proc_get_status($p);}while($status['running']&&AsusUpdateStore::uptime()<$end);
                                if($status['running'])proc_terminate($p,9);
                            }
                        }
                    }finally{flock($f,LOCK_UN);fclose($f);}
                }
                usleep(20000);$status=proc_get_status($p);
            }
        }finally{proc_close($p);$this->interrupt($id,$reason);}
    }
}
