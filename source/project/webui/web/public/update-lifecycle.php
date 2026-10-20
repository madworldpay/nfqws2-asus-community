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
    private function stateFile(string $name): ?string
    {
        $run=$this->options['run']??'/tmp/nfqws2-asus';AsusUpdateStore::noLinks($run);$dir=@lstat($run);if(!$dir)return null;$owner=$this->options['owner']??0;
        if(($dir['mode']&0170000)!==0040000||$dir['uid']!==$owner||($dir['mode']&0777)!==0700)throw new RuntimeException('invalid_state');$p=$run.'/'.$name;AsusUpdateStore::noLinks($p);$s=@lstat($p);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>64)throw new RuntimeException('invalid_state');$value=@file_get_contents($p);if(!is_string($value))throw new RuntimeException('invalid_state');return $value;
    }
    public function intent(): array
    {
        $raw=$this->stateFile('pid');$enabled=$this->stateFile('enabled')!==null;$identity=null;
        if($raw!==null&&preg_match('/^[1-9][0-9]{0,9}$/D',trim($raw))){$candidate=self::identity((int)trim($raw));$engine=realpath($this->options['engine']??'/opt/usr/bin/nfqws2');
            if($candidate!==null&&$engine!==false&&in_array($candidate['exe'],[$engine,$engine.' (deleted)'],true))$identity=$candidate;
        }
        return ['mode'=>$identity!==null?'running':($enabled?'waiting_for_wan':'stopped'),'process'=>$identity,'enabled'=>$enabled];
    }
    private function command(string $component,string $action): bool
    {
        if(!in_array($component,['core','web'],true)||!in_array($action,['start','stop','status'],true))throw new RuntimeException('invalid_state');$path=$this->options[$component.'_init']??(AsusUpdateStore::installed('etc/init.d').'/'.($component==='core'?'S51nfqws2':'S81nfqws-asus-web'));
        AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==($this->options['owner']??0)||$s['nlink']!==1||($s['mode']&0022)!==0||!is_executable($path))throw new RuntimeException('invalid_state');
        $p=@proc_open([$path,$action],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin:/opt/bin','LANG'=>'C','LC_ALL'=>'C']);if(!is_resource($p))return false;
        $first=proc_get_status($p);$identity=self::identity((int)$first['pid']);$deadline=microtime(true)+($this->options['service_timeout']??45);$status=$first;$exit=null;$timedOut=false;
        try{while(true){if(!$status['running']){$exit=$status['exitcode'];break;}if(microtime(true)>=$deadline){$timedOut=true;
                    // Signal only our own unreaped child, never the daemon PID.
                    $now=self::identity((int)$first['pid']);if($identity!==null&&$now!==null&&$now['start_ticks']===$identity['start_ticks']&&$now['boot_id']===$identity['boot_id'])proc_terminate($p,15);
                    $end=microtime(true)+1;do{usleep(10000);$status=proc_get_status($p);}while($status['running']&&microtime(true)<$end);
                    if($status['running'])proc_terminate($p,9);break;
                }usleep(20000);$status=proc_get_status($p);}
        }finally{$closed=proc_close($p);if($exit===null||$exit<0)$exit=$closed;}
        return !$timedOut&&$exit===0;
    }
    public function stop(): void
    {
        if($this->intent()['mode']==='stopped')return;
        if(!$this->command('core','stop')||$this->intent()['mode']!=='stopped')throw new RuntimeException('core_stop_failed');
    }
    public function restore(array $intent): string
    {
        if(!in_array($intent['mode']??null,['running','waiting_for_wan','stopped'],true))throw new RuntimeException('invalid_state');
        if($intent['mode']==='stopped'){if($this->intent()['mode']!=='stopped')throw new RuntimeException('intent_mismatch');return 'stopped';}
        if(!$this->command('core','start'))throw new RuntimeException('core_start_failed');$state=$this->intent()['mode'];if($state==='stopped')throw new RuntimeException('core_start_failed');return $state;
    }
    public function web(): void
    {if(!$this->command('web','start')||!$this->command('web','status'))throw new RuntimeException('web_start_failed');}
}
