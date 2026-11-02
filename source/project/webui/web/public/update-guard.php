<?php
require_once __DIR__.'/update-lifecycle.php';

/** Protected process/phase proof, never an HTTP flag or inherited descriptor. */
final class AsusUpdateGuard
{
    public function __construct(private AsusUpdateStore $store,private int $owner=0,private string $opkg='/opt/bin/opkg') {}
    private static function keys(array $value,array $expected): bool
    {$keys=array_keys($value);sort($keys);sort($expected);return $keys===$expected;}
    private function identityShape(mixed $value,string $boot): bool
    {
        return is_array($value)&&self::keys($value,['pid','start_ticks','boot_id','exe','uid'])&&is_int($value['pid'])&&$value['pid']>1&&$value['pid']<=2147483647&&is_string($value['start_ticks'])&&preg_match('/^[1-9][0-9]{0,19}$/D',$value['start_ticks'])&&$value['boot_id']===$boot&&is_string($value['exe'])&&str_starts_with($value['exe'],'/')&&strlen($value['exe'])<4096&&strpbrk($value['exe'],"\r\n\0")===false&&$value['uid']===$this->owner;
    }
    private function ticket(): ?array
    {
        $raw=$this->store->readFile('transaction.json',16384);if($raw===null)return null;
        try{$t=json_decode($raw,true,16,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(!is_array($t)||!self::keys($t,['schema','id','boot_id','worker','installer','phase','intent'])||$t['schema']!==1||!is_string($t['id'])||!preg_match('/^[a-f0-9]{32}$/D',$t['id'])||!is_string($t['boot_id'])||!preg_match('/^[a-zA-Z0-9-]{8,64}$/D',$t['boot_id'])||!$this->identityShape($t['worker'],$t['boot_id'])||($t['installer']!==null&&!$this->identityShape($t['installer'],$t['boot_id']))||!in_array($t['phase'],['validating','stopping','installing','starting','finished'],true)||!is_array($t['intent'])||!in_array($t['intent']['mode']??null,['running','waiting_for_wan','stopped'],true)||array_diff(array_keys($t['intent']),['mode','process','enabled'])!==[])throw new RuntimeException('invalid_state');return $t;
    }
    private function worker(array $ticket): bool
    {
        $identity=$ticket['worker'];$prefix=$this->store->path('operations/'.$ticket['id'].'/runtime').'/';
        if(!str_starts_with($identity['exe'],$prefix))return false;$file=substr($identity['exe'],strlen($prefix));if($file!=='php'&&!preg_match('~^lib/ld[a-zA-Z0-9_.-]+$~D',$file))return false;
        return AsusUpdateLifecycle::alive($identity);
    }
    private function installer(array $ticket): bool
    {
        $old=$ticket['installer'];if($old===null)return false;$now=AsusUpdateLifecycle::identity($old['pid']);if($now===null)return false;
        foreach(['pid','start_ticks','boot_id','uid'] as $k)if($now[$k]!==$old[$k])return false;
        $allowed=[$this->store->path('operations/'.$ticket['id'].'/runtime/update-launch')];$opkg=realpath($this->opkg);if($opkg!==false)$allowed[]=$opkg;
        return in_array($now['exe'],$allowed,true)&&in_array($old['exe'],$allowed,true);
    }
    public static function ancestor(int $wanted): bool
    {
        $pid=getmypid();$seen=[];for($i=0;$i<16&&$pid>1;$i++){if($pid===$wanted)return true;if(isset($seen[$pid]))return false;$seen[$pid]=true;
            $s=@file_get_contents('/proc/'.$pid.'/status');if(!is_string($s)||!preg_match('/^PPid:\s+([0-9]+)/m',$s,$m))return false;$pid=(int)$m[1];
        }return false;
    }
    public function authorize(string $action): bool
    {
        if(NfqwsPlatform::native()){require_once __DIR__.'/openwrt-update-guard.php';return (new NfqwsOpenWrtUpdateGuard($this->store,$this->owner))->authorize($action);}
        if(!in_array($action,['core-start','core-stop','web-start','web-stop','hook-prerm','hook-postinst','dns-restore'],true))throw new RuntimeException('invalid_request');
        $t=$this->ticket();if($t===null||$t['boot_id']!==AsusUpdateStore::boot())return false;
        $worker=$this->worker($t)&&self::ancestor($t['worker']['pid']);$installer=$this->installer($t)&&self::ancestor($t['installer']['pid']);
        return match($action){
            'core-start'=>$worker&&$t['phase']==='starting'&&$t['intent']['mode']!=='stopped',
            'core-stop'=>$worker&&$installer&&$t['phase']==='stopping',
            'hook-prerm','hook-postinst'=>$installer&&$t['phase']==='installing',
            'web-start'=>($installer&&$t['phase']==='installing')||($worker&&$t['phase']==='starting'),
            'web-stop'=>$installer&&$t['phase']==='installing',
            'dns-restore'=>($worker&&$installer&&$t['phase']==='stopping')||($installer&&$t['phase']==='installing'),
        };
    }
    /** Only the staged worker and its descendants may advance this ticket. */
    public function context(string $id): array
    {
        if(NfqwsPlatform::native()){require_once __DIR__.'/openwrt-update-guard.php';return (new NfqwsOpenWrtUpdateGuard($this->store,$this->owner))->context($id);}
        $t=$this->ticket();if($t===null||$t['id']!==$id||$t['boot_id']!==AsusUpdateStore::boot()||!$this->worker($t)||!self::ancestor($t['worker']['pid']))throw new RuntimeException('invalid_state');return $t;
    }
    /** Caller holds exclusive apply/work/critical leases. No orphan ON replay. */
    public function recover(string $id,array $original,array $installer):array
    {
        return $this->store->withRetryLock(function()use($id,$original,$installer){
            $boot=AsusUpdateStore::boot();$t=$this->ticket();$job=$this->store->readOperation($id);
            $raw=$this->store->readFile('operations/'.$id.'/guard.json',4096);$g=$raw===null?null:json_decode($raw,true,16,JSON_THROW_ON_ERROR);
            $current=AsusUpdateLifecycle::identity(getmypid());
            if($t===null||$t['id']!==$id||$t['boot_id']!==$boot||$job['state']!=='applying'||$job['boot_id']!==$boot||!in_array($t['phase'],['validating','stopping','installing'],true)||
                !$this->identityShape($original,$boot)||!$this->identityShape($installer,$boot)||$t['worker']!==$original||($t['installer']!==null&&$t['installer']!==$installer)||
                !is_array($g)||!self::keys($g,['schema','guardian','child','deadline'])||$g['schema']!==1||!is_numeric($g['deadline'])||!is_finite((float)$g['deadline'])||$g['deadline']<0||!$this->identityShape($g['guardian'],$boot)||!$this->identityShape($g['child'],$boot)||
                ($job['identity']??null)!==$g['guardian']||!$this->worker(['id'=>$id,'worker'=>$g['guardian']])||!self::ancestor($g['guardian']['pid'])||$g['guardian']['pid']===getmypid()||
                $current===null||!$this->identityShape($current,$boot)||!$this->worker(['id'=>$id,'worker'=>$current])||
                $installer['exe']!==$this->store->path('operations/'.$id.'/runtime/update-launch'))throw new RuntimeException('recovery_required');
            foreach(['pid','start_ticks','boot_id','uid'] as $key)if($g['child'][$key]!==$original[$key])throw new RuntimeException('recovery_required');
            foreach([$original,$installer] as $old){$now=AsusUpdateLifecycle::identity($old['pid']);if($now!==null){$same=true;foreach(['pid','start_ticks','boot_id','uid'] as $key)if($now[$key]!==$old[$key])$same=false;if($same)throw new RuntimeException('busy');}}
            if($this->store->readFile('operations/'.$id.'/boundary.json',1024)!==null||$this->store->readFile('operations/'.$id.'/rollback-finalized.json',1024)!==null)throw new RuntimeException('recovery_required');
            $t=array_replace($t,['worker'=>$current,'installer'=>null,'phase'=>'stopping']);$this->store->writeFile('transaction.json',json_encode($t,JSON_THROW_ON_ERROR));return $t;
        });
    }
    /** Private failure journal only: closed proof states, never process details. */
    public function diagnostic(string $id):array
    {
        if(NfqwsPlatform::native())return ['ticket'=>'unsupported'];
        try{$t=$this->ticket();}catch(Throwable $e){return ['ticket'=>'invalid'];}
        if($t===null)return ['ticket'=>'missing'];
        $prefix=$this->store->path('operations/'.$t['id'].'/runtime').'/';
        $worker=AsusUpdateLifecycle::identity($t['worker']['pid']);
        $installer=$t['installer']===null?null:AsusUpdateLifecycle::identity($t['installer']['pid']);
        $opkg=realpath($this->opkg);
        $kind=function(?array $identity)use($prefix,$opkg):string{
            if($identity===null)return 'missing';$exe=$identity['exe'];
            if($exe===$prefix.'update-launch')return 'launcher';if($opkg!==false&&$exe===$opkg)return 'opkg';
            if($exe===$prefix.'php')return 'php';if(str_starts_with($exe,$prefix.'lib/ld'))return 'loader';return 'other';
        };
        return ['ticket'=>'present','operation_matches'=>$t['id']===$id,'boot_matches'=>$t['boot_id']===AsusUpdateStore::boot(),'phase'=>$t['phase'],
            'worker_alive'=>$this->worker($t),'worker_ancestor'=>self::ancestor($t['worker']['pid']),'worker_executable'=>$kind($worker),
            'installer_alive'=>$this->installer($t),'installer_ancestor'=>$t['installer']!==null&&self::ancestor($t['installer']['pid']),
            'installer_executable'=>$kind($installer),'recorded_installer_executable'=>$kind($t['installer'])];
    }
    /** Caller holds this shared lease for its entire ordinary mutation. */
    public function mutationLease()
    {
        if(NfqwsPlatform::native()){require_once __DIR__.'/openwrt-update-guard.php';return (new NfqwsOpenWrtUpdateGuard($this->store,$this->owner))->mutationLease();}
        $f=$this->store->lease('apply.lock',true);
        try{$t=$this->ticket();if($t!==null&&$t['boot_id']===AsusUpdateStore::boot()&&($this->worker($t)||$this->installer($t)))throw new RuntimeException('busy');
            $this->store->reconcile(AsusUpdateStore::boot(),AsusUpdateStore::uptime());
            $job=$this->store->status()['active'];if(($job['state']??null)==='applying'){
                $identity=$job['identity']??null;
                if(is_array($identity)&&AsusUpdateLifecycle::alive($identity)||$identity===null&&AsusUpdateStore::uptime()-($job['apply_uptime']??$job['created_uptime'])<15)throw new RuntimeException('busy');
                $code=$this->store->readFile('operations/'.$job['id'].'/quiesce.json')!==null&&$this->store->readFile('operations/'.$job['id'].'/boundary.json',1024)===null?'recovery_required':'interrupted';
                $this->store->update($job['id'],['state'=>'interrupted','code'=>$code]);
            }return $f;
        }catch(Throwable $e){flock($f,LOCK_UN);fclose($f);throw $e;}
    }
}
