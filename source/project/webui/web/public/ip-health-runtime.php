<?php
declare(strict_types=1);
require_once __DIR__.'/ip-health-controller.php';

/** Fixed root facts are separate from the engine user's untrusted RAM events. */
final class NfqwsIpHealthRuntime
{
    private NfqwsIpHealthProbe $probe;
    private $lease;
    public function __construct(private NfqwsIpHealthStore $store,private string $privateDir,private string $runDir,
        private string $proc='/proc',private string $engine='/opt/usr/bin/nfqws2',private int $owner=0,
        ?NfqwsIpHealthProbe $probe=null,?callable $lease=null)
    {
        $this->probe=$probe??new NfqwsIpHealthProbe();
        $this->lease=$lease??function(){require_once __DIR__.'/update-guard.php';return (new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();};
    }
    private function directory(string $path,int $uid,int $mode):void
    {
        for($p=$path;$p!=='/';$p=dirname($p)){
            $s=@lstat($p);if(!$s||($s['mode']&0170000)!==0040000||!in_array($s['uid'],[0,$this->owner,$uid],true)||(($s['mode']&0022)!==0&&!($s['uid']===0&&($s['mode']&01000)!==0)))throw new RuntimeException('invalid_state');
        }
        $s=lstat($path);if($s['uid']!==$uid||($s['mode']&0777)!==$mode)throw new RuntimeException('invalid_state');
    }
    private function read(string $path,int $uid,int $limit,bool $consume=false):string
    {
        clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$uid||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>$limit)throw new RuntimeException('invalid_state');
        $f=@fopen($path,$consume?'r+b':'rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$a=fstat($f);if($s['ino']!==$a['ino']||$s['dev']!==$a['dev']||$a['size']>$limit)throw new RuntimeException('invalid_state');
            $raw=stream_get_contents($f,$limit+1);if(!is_string($raw)||strlen($raw)>$limit)throw new RuntimeException('invalid_state');
            if($consume&&(!ftruncate($f,0)||!fflush($f)))throw new RuntimeException('invalid_state');return $raw;
        }finally{fclose($f);}
    }
    public static function startTicks(string $stat):?string
    {$end=strrpos($stat,') ');if($end===false)return null;$fields=preg_split('/\s+/',substr($stat,$end+2));$ticks=$fields[19]??null;return is_string($ticks)&&preg_match('/^[0-9]{1,20}$/D',$ticks)?$ticks:null;}
    private function identity(int $pid,string $ticks,int $uid,?int $queue=null):bool
    {
        if($pid<2||self::startTicks((string)@file_get_contents($this->proc.'/'.$pid.'/stat'))!==$ticks)return false;
        // ASUS commonly exposes the mounted Entware tree through /opt.
        $binary=realpath($this->engine);$exe=@readlink($this->proc.'/'.$pid.'/exe');if($binary===false||$exe!==$binary)return false;
        $status=(string)@file_get_contents($this->proc.'/'.$pid.'/status');if(!preg_match('/^Uid:\s+\d+\s+(\d+)/m',$status,$m)||(int)$m[1]!==$uid)return false;
        if($queue!==null){$args=explode("\0",(string)@file_get_contents($this->proc.'/'.$pid.'/cmdline'));if(!in_array('--qnum='.$queue,$args,true))return false;}
        return true;
    }
    private function facts(bool $live=true):array
    {
        $this->directory($this->privateDir,$this->owner,0700);$this->directory($this->runDir,$this->owner,0755);
        $v=json_decode($this->read($this->privateDir.'/runtime.json',$this->owner,4096),true,16,JSON_THROW_ON_ERROR);
        $keys=is_array($v)?array_keys($v):[];sort($keys);$expected=['schema_version','boot_id','core_pid','core_start_ticks','observer_pid','observer_start_ticks','queue','interface','generation','ipv6','engine_uid'];sort($expected);
        if($keys!==$expected||$v['schema_version']!==1||!is_string($v['boot_id'])||!preg_match('/^[a-f0-9-]{36}$/D',$v['boot_id'])||!is_int($v['core_pid'])||!is_int($v['observer_pid'])||!is_int($v['queue'])||$v['queue']<1||$v['queue']>65535||!is_string($v['interface'])||!preg_match('/^[A-Za-z0-9_.:-]{1,15}$/D',$v['interface'])||!is_string($v['generation'])||!preg_match('/^[a-f0-9]{64}$/D',$v['generation'])||!is_bool($v['ipv6'])||!is_int($v['engine_uid'])||$v['engine_uid']<0)throw new RuntimeException('invalid_state');
        foreach(['core_start_ticks','observer_start_ticks'] as $key)if(!is_string($v[$key])||!preg_match('/^[0-9]{1,20}$/D',$v[$key]))throw new RuntimeException('invalid_state');
        if(trim((string)@file_get_contents($this->proc.'/sys/kernel/random/boot_id'))!==$v['boot_id'])throw new RuntimeException('core_stopped');
        if(!$live)return $v;
        if(!$this->identity($v['core_pid'],$v['core_start_ticks'],$v['engine_uid']))throw new RuntimeException('core_stopped');
        if(!$this->identity($v['observer_pid'],$v['observer_start_ticks'],$v['engine_uid'],$v['queue']))throw new RuntimeException('unavailable');
        $queues=(string)@file_get_contents($this->proc.'/net/netfilter/nfnetlink_queue');if(strlen($queues)>65536)throw new RuntimeException('queue_in_use');$found=0;
        foreach(explode("\n",trim($queues)) as $line){$row=preg_split('/\s+/',trim($line));if(($row[0]??null)===(string)$v['queue']){if(($row[1]??null)!==(string)$v['observer_pid'])throw new RuntimeException('queue_in_use');$found++;}}
        if($found!==1)throw new RuntimeException('queue_in_use');return $v;
    }
    public function liveFacts():array{return $this->facts();}
    public function writePrivate(string $name,array $value):void
    {
        if(!in_array($name,['runtime.json','worker.json'],true))throw new RuntimeException('invalid_state');
        $this->directory($this->privateDir,$this->owner,0700);$path=$this->privateDir.'/'.$name;
        if(@lstat($path)!==false)$this->read($path,$this->owner,4096);
        $raw=json_encode($value,JSON_THROW_ON_ERROR);if(strlen($raw)>4096)throw new RuntimeException('invalid_state');
        $tmp=$this->privateDir.'/.write-'.bin2hex(random_bytes(12));$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('invalid_state');
        try{if(fwrite($f,$raw)!==strlen($raw)||!fflush($f))throw new RuntimeException('invalid_state');fclose($f);$f=null;
            if(@lstat($path)!==false)$this->read($path,$this->owner,4096);if(!rename($tmp,$path))throw new RuntimeException('invalid_state');
        }finally{if(is_resource($f))fclose($f);if(is_file($tmp))unlink($tmp);}
    }
    /** Stop authorizes only identities registered by this protected worker. */
    public function ownedPids(string $entry,string $php):array
    {
        $out=[];
        try{$v=$this->facts(false);if($this->identity($v['observer_pid'],$v['observer_start_ticks'],$v['engine_uid'],$v['queue']))$out[]=$v['observer_pid'];}catch(Throwable $e){}
        try{
            $this->directory($this->privateDir,$this->owner,0700);$v=json_decode($this->read($this->privateDir.'/worker.json',$this->owner,4096),true,8,JSON_THROW_ON_ERROR);
            if(!is_array($v)||array_keys($v)!==['pid','start_ticks','boot_id']||!is_int($v['pid'])||$v['pid']<2||!is_string($v['start_ticks'])||!is_string($v['boot_id']))return $out;
            $prefix=$this->proc.'/'.$v['pid'];$args=explode("\0",(string)@file_get_contents($prefix.'/cmdline'));
            $sameEntry=false;$canonicalEntry=realpath($entry);foreach($args as $arg)if($canonicalEntry!==false&&realpath($arg)===$canonicalEntry)$sameEntry=true;
            if(trim((string)@file_get_contents($this->proc.'/sys/kernel/random/boot_id'))===$v['boot_id']&&self::startTicks((string)@file_get_contents($prefix.'/stat'))===$v['start_ticks']&&@readlink($prefix.'/exe')===realpath($php)&&$sameEntry&&in_array('loop',$args,true)&&preg_match('/^Uid:\s+\d+\s+'.preg_quote((string)$this->owner,'/').'\s/m',(string)@file_get_contents($prefix.'/status')))$out[]=$v['pid'];
        }catch(Throwable $e){}return $out;
    }
    private function events(array $facts,int $now):array
    {
        $this->directory($this->runDir.'/events',$facts['engine_uid'],0700);
        $raw=$this->read($this->runDir.'/events/events.log',$facts['engine_uid'],262144,true);$out=[];
        foreach(array_slice(explode("\n",$raw),0,4096) as $line){
            if(!preg_match('/^(silent|reply)\|([0-9]{10})\|([0-9a-f:.]{2,45})\|([0-9]{1,5})\|([a-z0-9.-]{0,253})$/D',$line,$m))continue;
            $at=(int)$m[2];$ip=NfqwsIpHealthStore::publicIp($m[3]);if($ip!==$m[3]||$at<$now-60||$at>$now+2)continue;
            $out[]=['kind'=>$m[1],'at'=>$at,'ip'=>$ip,'client_port'=>(int)$m[4],'host'=>$m[5]];if(count($out)>=512)break;
        }return $out;
    }
    public function inactive(string $code,int $now):void
    {
        try{$this->store->publishInactive($now);$this->store->runtimeStatus($code==='core_stopped'?'stopped':'unavailable',$code,$now);}catch(Throwable $e){}
    }
    public function tick(int $now):void
    {
        $lease=null;
        try{
            if(!NfqwsIpHealthStore::saneTime($now))throw new RuntimeException('clock_unavailable');
            $facts=$this->facts();if(!$this->probe->availability($facts['interface']))throw new RuntimeException('socket_unavailable');
            $lease=($this->lease)();$events=$this->events($facts,$now);
            // Renew before bounded probes, then revalidate all runtime facts.
            $this->store->publishManifest($now,$facts['generation']);
            (new NfqwsIpHealthController($this->store,$this->probe))->tick($now,$facts['generation'],$facts['interface'],$events);
            if($this->facts()!==$facts)throw new RuntimeException('invalid_state');
            $this->store->runtimeStatus('active',null,$now,'router_udp');$this->store->publishManifest($now,$facts['generation']);
        }catch(Throwable $e){$code=in_array($e->getMessage(),['core_stopped','queue_in_use','clock_unavailable','socket_unavailable'],true)?$e->getMessage():($e->getMessage()==='busy'?'update_busy':'unavailable');$this->inactive($code,$now);}
        finally{if(is_resource($lease)){flock($lease,LOCK_UN);fclose($lease);}}
    }
}
