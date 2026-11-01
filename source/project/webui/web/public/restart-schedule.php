<?php
require_once __DIR__.'/platform.php';

/** Small package-independent setting; runtime deadlines stay in RAM. */
final class NfqwsRestartSchedule
{
    private string $directory;
    public function __construct(?string $directory=null,private int $owner=0,private mixed $scheduler=null,private ?string $runtime=null)
    {
        $configured=$directory??NfqwsPlatform::settings()['config'];
        // Resolve only Entware's trusted mount alias. Managed descendants are
        // still checked individually and cannot introduce further symlinks.
        if($directory===null&&str_starts_with($configured,'/opt/')){
            $base=realpath('/opt');if($base===false)throw new RuntimeException('invalid_state');
            $configured=rtrim($base,'/').substr($configured,4);
        }
        $this->directory=$configured;
    }
    public static function validate(array $post):void
    {
        $cmd=$post['cmd']??null;
        if(!in_array($cmd,['restartschedule','restartschedulesave'],true))throw new RuntimeException('invalid_request');
        $expected=$cmd==='restartschedule'?['cmd','csrf_token']:['cmd','csrf_token','enabled','interval_hours','watchdog_enabled'];
        $keys=array_keys($post);sort($keys);sort($expected);if($keys!==$expected)throw new RuntimeException('invalid_request');
        foreach($post as $value)if(!is_string($value)||strlen($value)>128)throw new RuntimeException('invalid_request');
        if($cmd==='restartschedulesave'&&(!in_array($post['enabled'],['0','1'],true)||!in_array($post['watchdog_enabled'],['0','1'],true)||
            !preg_match('/^[1-9][0-9]{0,2}$/D',$post['interval_hours'])||(int)$post['interval_hours']>168))throw new RuntimeException('invalid_request');
    }
    private function path():string
    {try{return NfqwsPlatform::guardFile($this->directory,'restart-schedule.conf',$this->owner);}catch(Throwable $e){throw new RuntimeException('invalid_state');}}
    private function record():array
    {
        $path=$this->path();clearstatcache(true,$path);$s=@lstat($path);
        if($s===false)return ['enabled'=>false,'interval_hours'=>24,'watchdog_enabled'=>false,'revision'=>null,'watchdog_revision'=>null];
        if(!is_file($path)||is_link($path)||$s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>256)throw new RuntimeException('invalid_state');
        $raw=@file_get_contents($path);
        if(!is_string($raw)||!preg_match('/\Aenabled=([01])\ninterval_hours=([1-9][0-9]{0,2})\nwatchdog_enabled=([01])\nrevision=([a-f0-9]{32})\nwatchdog_revision=([a-f0-9]{32})\n\z/D',$raw,$m)||(int)$m[2]>168)throw new RuntimeException('invalid_state');
        return ['enabled'=>$m[1]==='1','interval_hours'=>(int)$m[2],'watchdog_enabled'=>$m[3]==='1','revision'=>$m[4],'watchdog_revision'=>$m[5]];
    }
    public function read(bool $checkScheduler=true):array
    {
        $record=$this->record();$value=array_intersect_key($record,array_flip(['enabled','interval_hours','watchdog_enabled']));
        $available=!$checkScheduler||(($this->scheduler??fn()=>self::schedulerAvailable())());
        $value+=['watchdog_state'=>$record['watchdog_enabled']?'ready':'disabled','watchdog_attempts'=>0,'watchdog_next_seconds'=>null,'scheduler_available'=>$available];
        if(!$record['watchdog_enabled'])return $value;
        $directory=$this->runtime??(NfqwsPlatform::native()?'/var/run/nfqws2-native':'/tmp/nfqws2-asus');
        if(@lstat($directory)===false)return $value;
        try{$path=NfqwsPlatform::guardFile($directory,'watchdog-state',$this->owner);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        $s=@lstat($path);if($s===false)return $value;
        if($s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['size']>128)throw new RuntimeException('invalid_state');
        $raw=(string)file_get_contents($path);
        if(!preg_match('/\A([a-f0-9]{32}) ([0-3]) ([0-9]{1,10}) (ready|waiting|locked)\n\z/D',$raw,$m))throw new RuntimeException('invalid_state');
        if($m[1]!==$record['watchdog_revision'])return $value;
        if($m[4]==='locked'&&$m[2]!=='3')throw new RuntimeException('invalid_state');
        $value['watchdog_state']=$m[4];$value['watchdog_attempts']=(int)$m[2];
        if($m[4]==='waiting'){$uptime=(float)explode(' ',(string)file_get_contents('/proc/uptime'))[0];$value['watchdog_next_seconds']=max(0,(int)$m[3]-(int)$uptime);}
        return $value;
    }
    public function save(bool $enabled,int $hours,bool $watchdog):array
    {
        if($hours<1||$hours>168)throw new RuntimeException('invalid_request');
        $previous=$this->record();
        if(($enabled||$watchdog)&&!(($this->scheduler??fn()=>self::installScheduler())()))throw new RuntimeException('unsupported_scheduler');
        if(!$enabled&&!$watchdog&&$this->scheduler===null&&NfqwsPlatform::native()){
            // OFF is enforced by the stored flags in every worker invocation.
            // A broken cron manager must not prevent disabling recovery; an
            // entry that cannot be removed is inert after this save succeeds.
            try{self::nativeCron(false);}catch(Throwable $e){}
        }
        $value=['enabled'=>$enabled,'interval_hours'=>$hours,'watchdog_enabled'=>$watchdog];
        if($value===array_intersect_key($previous,$value)&&is_file($this->path()))return $this->read();
        $revision=($enabled===$previous['enabled']&&$hours===$previous['interval_hours'])?$previous['revision']:null;
        $watchdogRevision=$watchdog===$previous['watchdog_enabled']?$previous['watchdog_revision']:null;
        $raw='enabled='.($enabled?'1':'0')."\ninterval_hours=$hours\nwatchdog_enabled=".($watchdog?'1':'0')."\nrevision=".($revision??bin2hex(random_bytes(16)))."\nwatchdog_revision=".($watchdogRevision??bin2hex(random_bytes(16)))."\n";
        $path=$this->path();$tmp=NfqwsPlatform::guardFile($this->directory,'.restart-schedule-'.bin2hex(random_bytes(12)),$this->owner);
        $mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('invalid_state');
        try{if(fwrite($f,$raw)!==strlen($raw)||!fflush($f)||(function_exists('fsync')&&!fsync($f)))throw new RuntimeException('invalid_state');
            fclose($f);$f=null;$this->path();if(!@rename($tmp,$path))throw new RuntimeException('invalid_state');
        }finally{if(is_resource($f))fclose($f);if(is_file($tmp)&&!is_link($tmp))@unlink($tmp);}
        return $this->read();
    }
    private static function installScheduler():bool
    {
        if(!self::schedulerAvailable())return false;
        return NfqwsPlatform::native()?self::nativeCron(true):true;
    }
    private static function schedulerAvailable():bool
    {
        if(NfqwsPlatform::native())return is_executable('/etc/init.d/cron')&&is_executable('/usr/bin/crontab')&&NfqwsPlatform::run(['/etc/init.d/cron','running'],5)['status']===0;
        foreach(['/usr/sbin/cru','/usr/bin/cru','/sbin/cru','/bin/cru']as $path)if(is_executable($path))return NfqwsPlatform::run([$path,'l'],5)['status']===0;
        return false;
    }
    /** Only our exact tagged line is replaced; unrelated root jobs survive. */
    private static function nativeCron(bool $enabled):bool
    {
        $cron='/etc/init.d/cron';$crontab='/usr/bin/crontab';
        if(!is_executable($cron)||!is_executable($crontab))return !$enabled;
        if($enabled&&NfqwsPlatform::run([$cron,'running'],5)['status']!==0)return false;
        $directory='/etc/crontabs';$path=NfqwsPlatform::guardFile($directory,'root');$s=@lstat($path);$raw='';
        if($s!==false){if(!is_file($path)||is_link($path)||$s['uid']!==0||($s['mode']&0022)!==0||$s['nlink']!==1||$s['size']>65536)throw new RuntimeException('invalid_state');$raw=(string)file_get_contents($path);}
        $tag='# nfqws2-periodic-restart';$lines=[];
        foreach(explode("\n",rtrim($raw,"\n"))as $line)if($line!==''&&!str_ends_with($line,$tag))$lines[]=$line;
        if($enabled)$lines[]='* * * * * /usr/bin/php8-cgi -n -d register_argc_argv=1 -q -f /usr/lib/nfqws2/restart-schedule-worker.php >/dev/null 2>&1 '.$tag;
        $next=$lines?implode("\n",$lines)."\n":'';if($next===$raw)return true;
        $temp=NfqwsPlatform::guardFile($directory,'.nfqws2-restart-'.bin2hex(random_bytes(12)));
        $mask=umask(0077);try{$f=@fopen($temp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('invalid_state');
        try{if(fwrite($f,$next)!==strlen($next)||!fflush($f))throw new RuntimeException('invalid_state');fclose($f);$f=null;
            return NfqwsPlatform::run([$crontab,$temp],5)['status']===0;
        }finally{if(is_resource($f))fclose($f);@unlink($temp);}
    }
}
