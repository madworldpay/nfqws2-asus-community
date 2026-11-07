<?php
require_once __DIR__.'/device-profiles-paths.php';
/** Private bounded JSON, atomic on one filesystem, with an owned writer lock. */
final class NfqwsDeviceProfilesState
{
    public function __construct(public readonly string $root,private int $owner=0){}
    private function directory():void
    {
        clearstatcache(true,$this->root);
        if(@lstat($this->root)===false){
            NfqwsDeviceProfilesPaths::guard(dirname($this->root),basename($this->root),$this->owner);
            $mask=umask(0077);try{if(!mkdir($this->root,0700))throw new RuntimeException('storage_unavailable');}finally{umask($mask);}
        }
        $s=lstat($this->root);
        if(!is_dir($this->root)||is_link($this->root)||$s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('storage_unavailable');
    }
    public function path(string $name):string
    {
        if(!preg_match('/^(?:(?:active|job|last-good|install|pending|actor-work|actor-guard)\.json|runtime\.lock|unused-(?:work|guard)\.pid|\.stage-[a-f0-9]{32})$/D',$name))throw new RuntimeException('invalid_request');
        $this->directory();return NfqwsDeviceProfilesPaths::guard($this->root,$name,$this->owner);
    }
    public function read(string $name):?array
    {
        $path=$this->path($name);clearstatcache(true,$path);$s=@lstat($path);if(!$s)return null;
        if($s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['size']>1048576)throw new RuntimeException('storage_unavailable');
        $v=json_decode((string)file_get_contents($path),true,32,JSON_THROW_ON_ERROR);
        if(!is_array($v))throw new RuntimeException('storage_unavailable');return $v;
    }
    public function write(string $name,?array $value):void
    {
        $path=$this->path($name);$this->read($name);
        if($value===null){if(file_exists($path)&&!unlink($path))throw new RuntimeException('storage_unavailable');return;}
        $data=json_encode($value,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
        if(strlen($data)>1048576)throw new RuntimeException('runtime_limit');
        $temp=$this->path('.stage-'.bin2hex(random_bytes(16)));$mask=umask(0077);
        try{$f=fopen($temp,'xb');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('storage_unavailable');
        try{
            if(fwrite($f,$data)!==strlen($data)||!fflush($f)||(function_exists('fsync')&&!fsync($f)))throw new RuntimeException('insufficient_space');
            fclose($f);$f=null;$this->path($name);
            if(!rename($temp,$path))throw new RuntimeException('storage_unavailable');
        }finally{if(is_resource($f))fclose($f);if(file_exists($temp))unlink($temp);}
    }
    public function locked(callable $fn):mixed
    {
        $path=$this->path('runtime.lock');$mask=umask(0077);try{$f=fopen($path,'c+b');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('storage_unavailable');
        try{
            $open=fstat($f);clearstatcache(true,$path);$named=lstat($path);
            if(!$open||!$named||$open['uid']!==$this->owner||($open['mode']&0777)!==0600||$open['nlink']!==1||$open['ino']!==$named['ino']||$open['dev']!==$named['dev'])throw new RuntimeException('storage_unavailable');
            if(!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');return $fn();
        }finally{flock($f,LOCK_UN);fclose($f);}
    }
}

/** Runs beneath the native package service lease; actuators verify real state. */
final class NfqwsDeviceProfilesTransaction
{
    public function __construct(private NfqwsDeviceProfilesState $store,private array $driver){}
    private function call(string $name,mixed ...$args):mixed{return ($this->driver[$name])(...$args);}
    private function record(array &$job,string $phase,array $extra=[]):void
    {$job=array_replace($job,['phase'=>$phase,'updated_at'=>time()],$extra);$this->store->write('job.json',$job);}
    public static function error(Throwable $error):string
    {
        $code=$error->getMessage();return preg_match('/^[a-z][a-z0-9_]{0,63}$/D',$code)?$code:'runtime_failed';
    }
    public function execute(array $job,array $desired,bool $startAfter):array
    {
        return $this->store->locked(function()use($job,$desired,$startAfter){
            $before=$this->store->read('active.json');$wasRunning=(bool)$this->call('running');$mutated=false;
            $job+=['before_active'=>$before,'desired'=>$desired,'was_running'=>$wasRunning,'start_after'=>$startAfter];
            try{
                $this->record($job,'validating',['state'=>'running','code'=>null,'original_code'=>null,'recovered'=>null]);
                $this->call('validate',$desired);
                if($this->store->read('active.json')!==$before)throw new RuntimeException('source_changed');
                $this->record($job,'stopping');$mutated=true;$this->call('stop');
                if($this->store->read('active.json')!==$before)throw new RuntimeException('source_changed');
                $this->record($job,'applying');$this->store->write('active.json',$desired);
                if($startAfter){$this->record($job,'starting');$this->call('start');$this->record($job,'checking');$this->call('check');}
                $this->store->write('last-good.json',$desired);
                $this->record($job,'finished',['state'=>'succeeded','code'=>null,'original_code'=>null,'recovered'=>null]);
            }catch(Throwable $error){
                $original=self::error($error);$failedPhase=$job['phase'];$recovered=null;$code=$original;
                if($mutated){
                    try{
                        $this->record($job,'restoring',['original_code'=>$original]);
                        $active=$this->store->read('active.json');
                        if($active!==$before&&$active!==$desired)throw new RuntimeException('source_changed');
                        $this->call('stop');$this->store->write('active.json',$before);
                        if($wasRunning){$this->call('start');$this->call('check');}
                        elseif($this->call('running'))throw new RuntimeException('restore_state_failed');
                        $recovered=true;
                    }catch(Throwable $restoreError){$code='recovery_required';$recovered=false;}
                }
                $this->record($job,$failedPhase,['state'=>'failed','code'=>$code,'original_code'=>$original,'recovered'=>$recovered]);
            }
            return $job;
        });
    }
    public static function project(?array $job):?array
    {
        return $job===null?null:array_intersect_key($job,array_flip(['id','state','phase','code','original_code','recovered','revision','started_at','updated_at']));
    }
    public function recover(array $job):array
    {
        return $this->store->locked(function()use($job){
            $current=$this->store->read('job.json');
            if(($current['id']??null)!==($job['id']??null))throw new RuntimeException('invalid_request');
            if(!in_array($current['state']??null,['queued','running'],true))return $current;
            $job=$current;$original=$job['original_code']??'worker_interrupted';
            if(!array_key_exists('before_active',$job)){
                $this->record($job,'queued',['state'=>'failed','code'=>'worker_start_failed','original_code'=>'worker_start_failed','recovered'=>null]);return $job;
            }
            try{
                $active=$this->store->read('active.json');
                if($active!==$job['before_active']&&$active!==$job['desired'])throw new RuntimeException('source_changed');
                $this->record($job,'restoring',['original_code'=>$original]);
                $this->call('stop');$this->store->write('active.json',$job['before_active']);
                if($job['was_running']){$this->call('start');$this->call('check');}
                elseif($this->call('running'))throw new RuntimeException('restore_state_failed');
                $this->record($job,'restoring',['state'=>'failed','code'=>$original,'original_code'=>$original,'recovered'=>true]);
            }catch(Throwable $error){
                $this->record($job,'restoring',['state'=>'failed','code'=>'recovery_required','original_code'=>$original,'recovered'=>false]);
            }
            return $job;
        });
    }
}
