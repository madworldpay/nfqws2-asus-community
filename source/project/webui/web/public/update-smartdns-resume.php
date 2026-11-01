<?php
/** Root updater only. Caller holds the exclusive apply lease throughout. */
final class AsusUpdateSmartDnsResume
{
    private string $php;
    private string $script;
    private string $exe;
    private string $argv;
    private string $boot;
    private int $owner;
    private int $limit;
    private float $seconds;
    public function __construct(array $trusted=[])
    {
        $this->php=$trusted['php']??'/opt/bin/php-cgi';$this->script=$trusted['script']??'/opt/lib/nfqws2-asus/smartdns/control.php';
        $this->owner=$trusted['owner']??0;$this->limit=$trusted['max_processes']??4096;$this->seconds=$trusted['seconds']??4.0;
        $exe=realpath($this->php);
        if(!is_string($exe)||!is_executable($exe)||!is_int($this->owner)||$this->owner<0||!is_int($this->limit)||$this->limit<1||$this->limit>4096||$this->seconds<=0||$this->seconds>5||str_contains($this->php,"\0")||str_contains($this->script,"\0"))self::fail();
        $this->exe=$exe;$this->argv=implode("\0",[$this->php,'-n','-d','register_argc_argv=1','-q','-f',$this->script,'--','resume'])."\0";
        $this->boot=$this->boot();
    }
    private static function fail(): never {throw new RuntimeException('dns_resume_stop_failed');}
    private static function now(): float
    {
        // hrtime(true) is a float on ARM32. Keep deadlines in seconds so no
        // nanosecond timestamp or duration is coerced into a 32-bit integer.
        $time=hrtime();return (float)$time[0]+$time[1]/1.0e9;
    }
    private function boot(): string
    {
        $value=@file_get_contents('/proc/sys/kernel/random/boot_id',false,null,0,65);
        if(!is_string($value)||!preg_match('/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/D',trim($value)))self::fail();return trim($value);
    }
    private function identity(int $pid): ?array
    {
        if($pid<2||$pid===getmypid())return null;
        $base='/proc/'.$pid;
        // This exact CLI invocation excludes HTTP CGI workers and other PHP jobs.
        $argv=@file_get_contents($base.'/cmdline',false,null,0,strlen($this->argv)+1);
        if($argv!==$this->argv)return null;
        $status=@file_get_contents($base.'/status',false,null,0,8193);$stat=@file_get_contents($base.'/stat',false,null,0,4097);$exe=@readlink($base.'/exe');
        if(!is_string($status)||!is_string($stat)||!is_string($exe)){clearstatcache(true,$base);if(!is_dir($base))return null;self::fail();}
        if(strlen($status)>8192||strlen($stat)>4096||strlen($exe)>4096)self::fail();
        $uid=preg_quote((string)$this->owner,'/');
        if(!preg_match('/^Uid:\s+'.$uid.'\s+'.$uid.'\s+'.$uid.'\s+'.$uid.'\s*$/m',$status)||!in_array($exe,[$this->exe,$this->exe.' (deleted)'],true))return null;
        if(!preg_match('/^'.$pid.' \(.*\) (.*)$/sD',trim($stat),$match))self::fail();$fields=preg_split('/\s+/',trim($match[1]));
        if(in_array($fields[0]??'Z',['Z','X'],true))return null;
        if(!preg_match('/^[1-9][0-9]{0,19}$/D',$fields[19]??'')||$this->boot()!==$this->boot)self::fail();
        return ['pid'=>$pid,'start_ticks'=>$fields[19],'boot_id'=>$this->boot,'exe'=>$exe,'uid'=>$this->owner];
    }
    private function scan(float $deadline): array
    {
        $dir=@opendir('/proc');if(!$dir)self::fail();$processes=0;$entries=0;$matches=[];
        try{while(($name=readdir($dir))!==false){
            if(++$entries>$this->limit+512||self::now()>=$deadline)self::fail();
            if(!preg_match('/^[1-9][0-9]{0,9}$/D',$name))continue;
            if(++$processes>$this->limit)self::fail();$identity=$this->identity((int)$name);
            if($identity!==null){$matches[]=$identity;if(count($matches)>8)self::fail();}
        }}finally{closedir($dir);}return $matches;
    }
    private function terminate(array $identity,float $deadline): void
    {
        // Legacy kernels lack pidfd. Recheck the full identity immediately
        // before signalling; procfs plus kill cannot make that check atomic.
        if($this->identity($identity['pid'])!==$identity)return;
        $p=@proc_open(['/bin/kill','-TERM',(string)$identity['pid']],
            [0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes,'/',['PATH'=>'/usr/bin:/bin','LANG'=>'C']);
        if(!is_resource($p))self::fail();$exit=null;$end=min($deadline,self::now()+.5);
        try{do{$status=proc_get_status($p);if(!$status['running']){$exit=$status['exitcode'];break;}if(self::now()>=$end){proc_terminate($p,9);self::fail();}usleep(10000);}while(true);}
        finally{$closed=proc_close($p);if($exit===null||$exit<0)$exit=$closed;}
        if($exit!==0&&$this->identity($identity['pid'])===$identity)self::fail();
        while($this->identity($identity['pid'])===$identity){if(self::now()>=$deadline)self::fail();usleep(20000);}
    }
    public function quiesce(): array
    {
        $deadline=self::now()+$this->seconds;$matched=0;
        for($round=0;$round<3;$round++){
            $identities=$this->scan($deadline);if(!$identities)return ['matched'=>$matched,'stopped'=>$matched];
            $matched+=count($identities);if($matched>8)self::fail();
            foreach($identities as $identity)$this->terminate($identity,$deadline);
        }
        self::fail();
    }
}
