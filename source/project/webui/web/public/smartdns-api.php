<?php
require_once __DIR__.'/smartdns-install.php';

/** A separate install job; DPI cancellation and result deletion cannot affect this runtime. */
final class AsusSmartDnsJobs
{
    private AsusSmartDnsInstaller $installer;
    public function __construct(?AsusSmartDnsInstaller $installer=null,private array $deps=[]){$this->installer=$installer??new AsusSmartDnsInstaller();}
    private static function uptime(): float{return (float)explode(' ',file_get_contents('/proc/uptime'))[0];}
    private static function boot(): string{return trim(file_get_contents('/proc/sys/kernel/random/boot_id'));}
    private function locked(callable $fn): mixed
    {
        $path=$this->installer->directory().'/job.lock';$s=@lstat($path);if($s&&(($s['mode']&0170000)!==0100000||$s['nlink']!==1||$s['uid']!==fileowner(dirname($path))))throw new RuntimeException('invalid_state');
        $f=@fopen($path,'c');if(!$f)throw new RuntimeException('invalid_state');chmod($path,0600);
        try{if(!flock($f,LOCK_EX))throw new RuntimeException('busy');return $fn();}finally{flock($f,LOCK_UN);fclose($f);}
    }
    private function read(): ?array
    {
        $path=$this->installer->directory().'/job.json';$s=@lstat($path);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['nlink']!==1||$s['uid']!==fileowner(dirname($path))||($s['mode']&0777)!==0600||$s['size']>4096)throw new RuntimeException('invalid_state');
        $v=json_decode(file_get_contents($path),true,8,JSON_THROW_ON_ERROR);
        if(!is_array($v)||!preg_match('/^[a-f0-9]{32}$/D',$v['id']??'')||!in_array($v['state']??null,['queued','running','completed','failed','interrupted'],true)||!is_numeric($v['started_uptime']??null))throw new RuntimeException('invalid_state');return $v;
    }
    private function write(array $job): void
    {
        $root=$this->installer->directory();$tmp=$root.'/.job-'.bin2hex(random_bytes(12));$f=@fopen($tmp,'xb');if(!$f)throw new RuntimeException('invalid_state');chmod($tmp,0600);
        try{$raw=json_encode($job,JSON_THROW_ON_ERROR);if(fwrite($f,$raw)!==strlen($raw)||!fflush($f))throw new RuntimeException('insufficient_space');}finally{fclose($f);}
        if(is_link($root.'/job.json')||!rename($tmp,$root.'/job.json')){unlink($tmp);throw new RuntimeException('invalid_state');}
    }
    private function reconcile(?array $job): ?array
    {
        if($job!==null&&in_array($job['state'],['queued','running'],true)){
            $worker=($job['identity']??null)!==null&&AsusDpiRuntime::identity($job['identity']['pid'])===$job['identity'];
            $guard=false;$path=$this->installer->directory().'/guard-'.$job['id'];$s=@lstat($path);
            if($s&&($s['mode']&0170000)===0100000&&$s['nlink']===1&&$s['uid']===fileowner(dirname($path))&&$s['size']<256){
                $parts=explode(' ',trim(file_get_contents($path)));
                if(count($parts)===3&&preg_match('/^[0-9]+$/D',$parts[0])&&preg_match('/^[0-9]+$/D',$parts[1])){
                    $now=AsusDpiRuntime::identity((int)$parts[0]);$guard=$now!==null&&$now['starttime']===$parts[1]&&$now['boot_id']===$parts[2];
                }
            }
            // Time alone is never permission to replace a live owner. The
            // monotonic guardian terminates its own worker before this changes.
            $lost=$job['boot']!==self::boot()||(!$worker&&!$guard&&($job['state']==='running'||self::uptime()-$job['started_uptime']>10));
            if($lost){$job['state']='interrupted';$job['code']='interrupted';$this->write($job);}
        }return $job;
    }
    public function start(string $id): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');
        [$job,$launch]=$this->locked(function()use($id){
            $old=$this->reconcile($this->read());if(($old['id']??null)===$id)return [$old,false];
            if($old!==null&&in_array($old['state'],['queued','running'],true))throw new RuntimeException('busy');
            $cap=isset($this->deps['available'])?($this->deps['available'])():$this->installer->availability();if(!$cap['available'])throw new RuntimeException($cap['code']);
            $job=['id'=>$id,'state'=>'queued','code'=>null,'boot'=>self::boot(),'started_uptime'=>self::uptime(),'identity'=>null];$this->write($job);return [$job,true];
        });
        if($launch){try{
            if(isset($this->deps['launch']))($this->deps['launch'])($id);
            else{$bb=AsusDpiRuntime::busybox();$p=@proc_open([$bb,'start-stop-daemon','-S','-b','-p',$this->installer->directory().'/unused.pid','-x',$bb,'--','sh',NfqwsPlatform::translate('/opt/lib/nfqws2-asus/smartdns/worker.sh'),$id],
                [0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C']);
                if(!is_resource($p)||proc_close($p)!==0)throw new RuntimeException('launch_failed');}
        }catch(Throwable $e){$this->locked(function()use(&$job){$job['state']='failed';$job['code']='launch_failed';$this->write($job);});throw new RuntimeException('launch_failed');}}
        return self::publicJob($job);
    }
    private static function publicJob(?array $job): ?array
    {return $job===null?null:['id'=>$job['id'],'state'=>$job['state'],'code'=>$job['code']];}
    public function status(): array
    {
        $job=$this->locked(fn()=>$this->reconcile($this->read()));
        return ['available'=>$this->installer->availability(),'installed'=>$this->installer->installed(),'version'=>$this->installer->artifact()['version'],
            'external_detected'=>NfqwsPlatform::native()?is_file('/etc/config/smartdns'):is_file('/opt/etc/init.d/S50smartdns')||is_file('/opt/etc/smartdns/smartdns.conf'),'job'=>self::publicJob($job)];
    }
    public function work(string $id): void
    {
        $this->locked(function()use($id){$job=$this->read();if(($job['id']??null)!==$id||$job['state']!=='queued')throw new RuntimeException('invalid_state');
            $job['state']='running';$job['identity']=AsusDpiRuntime::identity(getmypid());if($job['identity']===null)throw new RuntimeException('unsupported_runtime');$this->write($job);});
        $lease=null;$state='failed';$code='failed';
        try{require_once __DIR__.'/update-guard.php';$guard=new AsusUpdateGuard(new AsusUpdateStore());$deadline=self::uptime()+1;
            // Page reload/status polling briefly holds the updater journal.
            // Retry only lease acquisition, never replay the installation.
            do{try{$lease=$guard->mutationLease();break;}
                catch(RuntimeException $e){if($e->getMessage()!=='busy'||self::uptime()>=$deadline)throw $e;usleep(10000);}
            }while(true);
            $this->installer->install($id);$state='completed';$code=null;}
        catch(Throwable $e){$code=AsusSmartDnsInstaller::code($e->getMessage());}
        finally{if(is_resource($lease)){flock($lease,LOCK_UN);fclose($lease);}}
        $this->locked(function()use($id,$state,$code){$job=$this->read();if(($job['id']??null)===$id&&$job['state']==='running'){$job['state']=$state;$job['code']=$code;$this->write($job);}});
    }
}
final class AsusSmartDnsApi
{
    public static function validate(array $post): void
    {
        $install=($post['cmd']??null)==='smartdnsinstall';if(!$install&&($post['cmd']??null)!=='smartdnsstatus')throw new RuntimeException('invalid_request');
        $expected=$install?['cmd','csrf_token','request_id','consent']:['cmd','csrf_token'];$keys=array_keys($post);sort($keys);sort($expected);if($keys!==$expected)throw new RuntimeException('invalid_request');
        foreach($post as $v)if(!is_string($v))throw new RuntimeException('invalid_request');
        if($install){if(!preg_match('/^[a-f0-9]{32}$/D',$post['request_id']))throw new RuntimeException('invalid_request');if($post['consent']!=='install')throw new RuntimeException('consent_required');}
    }
    public static function dispatch(array $post): array
    {self::validate($post);$jobs=new AsusSmartDnsJobs();return $post['cmd']==='smartdnsinstall'?['job'=>$jobs->start($post['request_id'])]:$jobs->status();}
}
