<?php
require_once __DIR__.'/update-store.php';

/** Only trusted worker code supplies paths; HTTP never supplies a command. */
final class AsusUpdateLifecycle
{
    public function __construct(private array $options=[]) {}
    public static function identity(int $pid): ?array
    {
        if($pid<2)return null;$stat=@file_get_contents('/proc/'.$pid.'/stat');$exe=@readlink('/proc/'.$pid.'/exe');$status=@file_get_contents('/proc/'.$pid.'/status');
        if(!is_string($stat)||!is_string($exe)||!is_string($status)||!preg_match('/^\d+ \(.*\) (.*)$/sD',trim($stat),$m))return null;$fields=preg_split('/\s+/',trim($m[1]));
        if(($fields[0]??'Z')==='Z'||!preg_match('/^[0-9]+$/D',$fields[19]??'')||!preg_match('/^Uid:\s+([0-9]+)/m',$status,$uid))return null;
        return ['pid'=>$pid,'start_ticks'=>$fields[19],'boot_id'=>AsusUpdateStore::boot(),'exe'=>$exe,'uid'=>(int)$uid[1]];
    }
    public static function alive(array $identity): bool
    {return isset($identity['pid'])&&is_int($identity['pid'])&&self::identity($identity['pid'])===$identity;}
    private function stateFile(string $name,int $cap=64): ?string
    {
        $run=$this->options['run']??'/tmp/nfqws2-asus';AsusUpdateStore::noLinks($run);$dir=@lstat($run);if(!$dir)return null;$owner=$this->options['owner']??0;
        if(($dir['mode']&0170000)!==0040000||$dir['uid']!==$owner||($dir['mode']&0777)!==0700)throw new RuntimeException('invalid_state');$p=$run.'/'.$name;AsusUpdateStore::noLinks($p);$s=@lstat($p);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>$cap)throw new RuntimeException('invalid_state');$f=@fopen($p,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$opened=fstat($f);$value=stream_get_contents($f,$cap+1);$after=fstat($f);clearstatcache(true,$p);$now=@lstat($p);$stable=static fn($v)=>array_intersect_key($v,array_fill_keys(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime'],true));if($stable($opened)!==$stable($s)||!is_string($value)||strlen($value)>$cap||$stable($opened)!==$stable($after)||!$now||$stable($now)!==$stable($opened))throw new RuntimeException('invalid_state');return $value;}finally{fclose($f);}
    }
    private function artifact(string $directory,string $name,string $raw,int $mode,?string $temporary=null):array
    {
        $owner=$this->options['owner']??0;AsusUpdateStore::noLinks($directory);$s=@lstat($directory);
        if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $path=$directory.'/'.$name;AsusUpdateStore::noLinks($path);$before=@lstat($path);
        if($before&&(($before['mode']&0170000)!==0100000||$before['uid']!==$owner||$before['nlink']!==1||($before['mode']&0777)!==$mode))throw new RuntimeException('invalid_state');
        $tmp=$directory.'/'.($temporary??('.write-'.bin2hex(random_bytes(12))));$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('insufficient_space');
        try{if(fwrite($f,$raw)!==strlen($raw)||!fflush($f)||!fsync($f)||!chmod($tmp,$mode)||!rename($tmp,$path))throw new RuntimeException('insufficient_space');}
        finally{fclose($f);if(file_exists($tmp))unlink($tmp);}
        return ['mode'=>$mode,'size'=>strlen($raw),'sha256'=>hash('sha256',$raw)];
    }
    public function checkpoint(string $directory):array
    {
        $intent=$this->intent();if($intent['mode']==='running'&&!$intent['enabled'])throw new RuntimeException('invalid_state');AsusUpdateStore::noLinks($directory);if(file_exists($directory)||is_link($directory))throw new RuntimeException('invalid_state');
        $parent=@lstat(dirname($directory));$owner=$this->options['owner']??0;
        if(!$parent||($parent['mode']&0170000)!==0040000||$parent['uid']!==$owner||($parent['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $contents=[];$files=[];
        foreach(['runtime.conf','enabled','started','watchdog-state'] as $name){$raw=$this->stateFile($name,$name==='runtime.conf'?8388608:64);if($raw!==null){$contents[$name]=$raw;$files[$name]=['mode'=>0600,'size'=>strlen($raw),'sha256'=>hash('sha256',$raw)];}}
        if($intent['mode']==='running'&&!isset($files['runtime.conf'])||$this->intent()!==$intent)throw new RuntimeException('invalid_state');
        $value=['schema'=>1,'intent'=>$intent,'files'=>$files];$raw=json_encode($value,JSON_THROW_ON_ERROR);$manifest=['mode'=>0600,'size'=>strlen($raw),'sha256'=>hash('sha256',$raw)];
        $planned=$files+['snapshot.json'=>$manifest];foreach($planned as $name=>$meta)$planned['.stage-'.$name]=$meta;
        $mask=umask(0077);try{if(!mkdir($directory,0700))throw new RuntimeException('insufficient_space');}finally{umask($mask);}
        // Persist bounded ownership before writing the potentially8MiB RAM
        // config. A killed copy has only these exact reclaimable paths.
        $this->artifact($directory,'staging.json',json_encode(['files'=>$planned],JSON_THROW_ON_ERROR),0600);
        foreach($contents as $name=>$bytes)$this->artifact($directory,$name,$bytes,0600,'.stage-'.$name);
        $this->artifact($directory,'snapshot.json',$raw,0600,'.stage-snapshot.json');
        $this->artifact($directory,'cleanup-index.json',json_encode(['files'=>$files+['snapshot.json'=>$manifest]],JSON_THROW_ON_ERROR),0600);
        if(!unlink($directory.'/staging.json'))throw new RuntimeException('invalid_state');return $value;
    }

    public function checkpointState(string $directory):array
    {
        $owner=$this->options['owner']??0;AsusUpdateStore::noLinks($directory);$dir=@lstat($directory);
        if(!$dir||($dir['mode']&0170000)!==0040000||$dir['uid']!==$owner||($dir['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $read=function(string $name,int $cap,int $mode=0600)use($directory,$owner):string{$path=$directory.'/'.$name;AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0777)!==$mode||$s['size']>$cap)throw new RuntimeException('invalid_state');$f=@fopen($path,'rb');if(!$f)throw new RuntimeException('invalid_state');try{$raw=stream_get_contents($f,$cap+1);if(!is_string($raw)||strlen($raw)>$cap)throw new RuntimeException('invalid_state');return $raw;}finally{fclose($f);}};
        $v=json_decode($read('snapshot.json',4096),true,16,JSON_THROW_ON_ERROR);
        if(!is_array($v)||array_keys($v)!==['schema','intent','files']||$v['schema']!==1||!is_array($v['intent'])||array_keys($v['intent'])!==['mode','process','enabled']||!in_array($v['intent']['mode'],['running','waiting_for_wan','stopped'],true)||!is_bool($v['intent']['enabled'])||!is_array($v['files'])||array_diff(array_keys($v['files']),['runtime.conf','enabled','started','watchdog-state']))throw new RuntimeException('invalid_state');
        foreach($v['files'] as $name=>$meta){if(!is_array($meta)||array_keys($meta)!==['mode','size','sha256']||$meta['mode']!==0600||!is_int($meta['size'])||!is_string($meta['sha256']))throw new RuntimeException('invalid_state');$raw=$read($name,$name==='runtime.conf'?8388608:64);if(strlen($raw)!==$meta['size']||!hash_equals($meta['sha256'],hash('sha256',$raw)))throw new RuntimeException('invalid_state');}
        return $v;
    }
    public function restoreCheckpoint(string $directory):string
    {
        $v=$this->checkpointState($directory);$run=$this->options['run']??'/tmp/nfqws2-asus';
        if($this->intent()['mode']!=='stopped')throw new RuntimeException('intent_mismatch');
        if($v['intent']['mode']==='stopped'){
            foreach($v['files'] as $name=>$meta)$this->artifact($run,$name,file_get_contents($directory.'/'.$name),0600);
            if($this->intent()['mode']!=='stopped')throw new RuntimeException('intent_mismatch');return 'stopped';
        }
        if(!isset($v['files']['runtime.conf']))throw new RuntimeException('invalid_state');
        $init=$this->options['core_init']??AsusUpdateStore::installed('etc/init.d/S51nfqws2');AsusUpdateStore::noLinks($init);$s=@lstat($init);
        if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==($this->options['owner']??0)||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>65536)throw new RuntimeException('invalid_state');
        $raw=file_get_contents($init);$needle="CONFFILE=/opt/etc/nfqws2/nfqws2.conf\n";if(substr_count($raw,$needle)!==1)throw new RuntimeException('invalid_state');
        $starter=$this->artifact($directory,'core-start',str_replace($needle,'CONFFILE='.escapeshellarg($directory.'/runtime.conf')."\n",$raw),0700);
        $manifest=['mode'=>0600,'size'=>filesize($directory.'/snapshot.json'),'sha256'=>hash_file('sha256',$directory.'/snapshot.json')];
        $this->artifact($directory,'cleanup-index.json',json_encode(['files'=>$v['files']+['snapshot.json'=>$manifest,'core-start'=>$starter]],JSON_THROW_ON_ERROR),0600);
        $active=new self(array_replace($this->options,['core_init'=>$directory.'/core-start']));return $active->restore($v['intent']);
    }
    public function intent(): array
    {
        $raw=$this->stateFile('pid');$enabled=$this->stateFile('enabled')!==null;$identity=null;
        if($raw!==null&&preg_match('/^[1-9][0-9]{0,9}$/D',trim($raw))){$candidate=self::identity((int)trim($raw));$engine=realpath($this->options['engine']??'/opt/usr/bin/nfqws2');
            if($candidate!==null&&$engine!==false&&in_array($candidate['exe'],[$engine,$engine.' (deleted)'],true))$identity=$candidate;
        }
        $latched=false;
        if($identity===null&&$this->stateFile('watchdog-state')!==null){
            require_once __DIR__.'/restart-schedule.php';
            $settings=(new NfqwsRestartSchedule($this->options['config']??null,$this->options['owner']??0,null,$this->options['run']??'/tmp/nfqws2-asus'))->read(false);
            // The third attempt may have become ready briefly, then exited
            // before the next tick could write locked. Its budget is spent.
            $latched=$settings['watchdog_enabled']&&$settings['watchdog_attempts']>=3;
        }
        return ['mode'=>$identity!==null?'running':($enabled&&!$latched?'waiting_for_wan':'stopped'),'process'=>$identity,'enabled'=>$enabled];
    }
    private function command(string $component,string $action,bool $exitStatus=false): bool|int
    {
        if(!in_array($component,['core','web'],true)||!in_array($action,['start','stop','status'],true))throw new RuntimeException('invalid_state');$path=$this->options[$component.'_init']??(AsusUpdateStore::installed('etc/init.d').'/'.($component==='core'?'S51nfqws2':'S81nfqws-asus-web'));
        AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==($this->options['owner']??0)||$s['nlink']!==1||($s['mode']&0022)!==0||!is_executable($path))throw new RuntimeException('invalid_state');
        $p=@proc_open([$path,$action],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin:/opt/bin','LANG'=>'C','LC_ALL'=>'C']);if(!is_resource($p))return $exitStatus?-1:false;
        $first=proc_get_status($p);$identity=self::identity((int)$first['pid']);$deadline=microtime(true)+($this->options['service_timeout']??45);$status=$first;$exit=null;$timedOut=false;
        try{while(true){if(!$status['running']){$exit=$status['exitcode'];break;}if(microtime(true)>=$deadline){$timedOut=true;
                    // Signal only our own unreaped child, never the daemon PID.
                    $now=self::identity((int)$first['pid']);if($identity!==null&&$now!==null&&$now['start_ticks']===$identity['start_ticks']&&$now['boot_id']===$identity['boot_id'])proc_terminate($p,15);
                    $end=microtime(true)+1;do{usleep(10000);$status=proc_get_status($p);}while($status['running']&&microtime(true)<$end);
                    if($status['running'])proc_terminate($p,9);break;
                }usleep(20000);$status=proc_get_status($p);}
        }finally{$closed=proc_close($p);if($exit===null||$exit<0)$exit=$closed;}
        return $exitStatus?($timedOut?-1:$exit):(!$timedOut&&$exit===0);
    }
    public function stop(bool $always=false): void
    {
        $this->stopTerminal();
        if(!$always&&$this->intent()['mode']==='stopped')return;
        if(!$this->command('core','stop')||$this->intent()['mode']!=='stopped')throw new RuntimeException('core_stop_failed');
    }
    public function restore(array $intent): string
    {
        if(!in_array($intent['mode']??null,['running','waiting_for_wan','stopped'],true))throw new RuntimeException('invalid_state');
        if($intent['mode']==='stopped'){if($this->intent()['mode']!=='stopped')throw new RuntimeException('intent_mismatch');return 'stopped';}
        if(!$this->command('core','start'))throw new RuntimeException('core_start_failed');$state=$this->intent()['mode'];if($state==='stopped')throw new RuntimeException('core_start_failed');return $state;
    }
    public function webStop(): void
    {$this->stopTerminal();if(!$this->command('web','stop'))throw new RuntimeException('web_stop_failed');}
    private function stopTerminal(): void
    {
        require_once __DIR__.'/dpi-terminal-lifecycle.php';
        (new AsusDpiTerminalLifecycle($this->options['terminal_root']??null,$this->options['owner']??0))->stop();
    }
    public function webRunning():bool
    {
        $status=$this->command('web','status',true);if($status===0)return true;
        if($status!==1)throw new RuntimeException('web_stop_failed');
        // S81 also returns 1 for runtime/ABI errors. Only call that OFF after
        // ruling out our actual daemon, including an old ABI or missing PID.
        try{
            $run=$this->options['web_run']??'/tmp/nfqws-asus-web';$owner=$this->options['owner']??0;AsusUpdateStore::noLinks($run);$dir=@lstat($run);
            if($dir&&(($dir['mode']&0170000)!==0040000||$dir['uid']!==$owner||($dir['mode']&0777)!==0700))throw new RuntimeException('invalid_state');
            $pid=$run.'/pid';AsusUpdateStore::noLinks($pid);$meta=@lstat($pid);
            if($meta){
                if(($meta['mode']&0170000)!==0100000||$meta['uid']!==$owner||$meta['nlink']!==1||($meta['mode']&0777)!==0600||$meta['size']>64)throw new RuntimeException('invalid_state');
                $raw=@file_get_contents($pid);if(!is_string($raw)||!preg_match('/^[1-9][0-9]{0,9}\s*$/D',$raw))throw new RuntimeException('invalid_state');
                if(is_dir('/proc/'.(int)trim($raw))&&self::identity((int)trim($raw))===null)throw new RuntimeException('invalid_state');
            }
            $opt=realpath('/opt')?:'/opt';$paths=isset($this->options['web_engine'])?[$this->options['web_engine']]:[$opt.'/libexec/nfqws-asus-web/lighttpd',$opt.'/libexec/nfqws-asus-web/armv7-2.6/lighttpd',$opt.'/libexec/nfqws-asus-web/armv7-3.2/lighttpd'];
            $engines=[];foreach($paths as $path)$engines[]=realpath($path)?:$path;
            $processes=glob('/proc/[0-9]*/exe');if(!is_array($processes)||count($processes)>8192)throw new RuntimeException('invalid_state');
            foreach($processes as $exe){
                $binary=@readlink($exe);if(!is_string($binary))continue;$binary=preg_replace('/ \(deleted\)$/D','',$binary);
                if(!in_array($binary,$engines,true))continue;$process=self::identity((int)basename(dirname($exe)));if($process===null)throw new RuntimeException('invalid_state');
                $f=@fopen(dirname($exe).'/cmdline','rb');if(!$f)throw new RuntimeException('invalid_state');try{$raw=stream_get_contents($f,4097);}finally{fclose($f);}
                if(!is_string($raw)||$raw===''||strlen($raw)>4096)throw new RuntimeException('invalid_state');$args=explode("\0",rtrim($raw,"\0"));
                foreach($args as $i=>$arg)if($arg==='-f'&&($args[$i+1]??null)===$run.'/lighttpd.conf')throw new RuntimeException('invalid_state');
            }
        }catch(Throwable $e){throw new RuntimeException('web_stop_failed');}
        return false;
    }
    public function web(): void
    {if(!$this->command('web','start')||!$this->command('web','status'))throw new RuntimeException('web_start_failed');}
}
