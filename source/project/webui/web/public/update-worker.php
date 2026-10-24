<?php
require_once __DIR__.'/update-prepare.php';
require_once __DIR__.'/update-runtime.php';
require_once __DIR__.'/update-guard.php';
require_once __DIR__.'/smartdns-lifecycle.php';

/** Root-only staged implementation. There is no HTTP entry or command input. */
final class AsusUpdateWorker
{
    private AsusUpdatePrepare $prepare;
    private AsusUpdateLifecycle $lifecycle;
    public function __construct(private AsusUpdateStore $store,?AsusUpdatePrepare $prepare=null,?AsusUpdateLifecycle $lifecycle=null,private array $options=[])
    {$this->prepare=$prepare??new AsusUpdatePrepare($store);$this->lifecycle=$lifecycle??new AsusUpdateLifecycle();}
    private function owner(): int {return $this->options['owner']??0;}
    private function dnsJobs(): AsusSmartDnsConfigJobs
    {return new AsusSmartDnsConfigJobs($this->options['dns_store']??new AsusSmartDnsStore(),$this->options['dns_backend']??null);}
    private function assertDnsUpdateReady(): void
    {
        // The exclusive updater lease is already held. Dead processes alone
        // cannot release an unresolved native DNS transaction.
        $jobs=$this->dnsJobs();$jobs->reconcile();
        if ($jobs->blocksUpdate()) throw new RuntimeException('dns_restore_required');
    }
    private function guard(): AsusUpdateGuard {return new AsusUpdateGuard($this->store,$this->owner(),$this->options['opkg']??'/opt/bin/opkg');}
    private function writeTicket(array $ticket): void
    {$this->store->writeFile('transaction.json',json_encode($ticket,JSON_THROW_ON_ERROR));}
    private function ticket(string $id,string $phase,array $patch=[]): array
    {return $this->store->withLock(function()use($id,$phase,$patch){$t=$this->guard()->context($id);$t=array_replace($t,$patch,['phase'=>$phase]);$this->writeTicket($t);return $t;});}
    private function validate(string $id,bool $fresh): array
    {
        $job=$this->store->readOperation($id);if($job['state']!=='applying'||$job['boot_id']!==AsusUpdateStore::boot())throw new RuntimeException('interrupted');
        $base='operations/'.$id;$runtime=$this->store->path($base.'/runtime');$closure=AsusUpdateRuntime::load($runtime,$this->owner());
        if(!is_string($job['runtime_digest']??null)||!hash_equals($job['runtime_digest'],$closure['digest']))throw new RuntimeException('runtime_changed');
        $env=$this->prepare->environment();$manifest=AsusPackageManifest::verify($this->store->readFile($base.'/manifest.json')??'',
            $this->store->readFile($base.'/manifest.sig')??'',file_get_contents($runtime.'/resources/update-release-key.pem'));
        $candidate=AsusPackageManifest::candidate($manifest,$env['family'],$env['installed']);
        $saved=json_decode($this->store->readFile($base.'/candidate.json')??'',true,32,JSON_THROW_ON_ERROR);
        if($candidate===null||$candidate!==$saved||$candidate['revision']!==$job['revision'])throw new RuntimeException('stale_revision');
        if($fresh){$check=$this->prepare->check(true);if($check['state']!=='available'||$check['candidate']!==$candidate)throw new RuntimeException('stale_revision');}
        AsusUpdatePackage::inspect($this->store->path($base.'/package.ipk'),$candidate,$env['status'],$env['abi'],$env['machine']);
        AsusUpdateSnapshot::verify($env['opt'],$this->store->path($base.'/backup'),$this->owner());
        AsusUpdatePackage::space($env['free'],0,0,0);return [$env,$candidate];
    }
    /** Native launcher owns the opkg POSIX mutex throughout this child check. */
    public function preflight(string $id): void
    {
        $f=$this->store->lease('operations/'.$id.'/critical.lock');
        try{
            $t=$this->guard()->context($id);if($t['phase']!=='validating'||$t['installer']!==null)throw new RuntimeException('invalid_state');
            if($this->store->readFile('operations/'.$id.'/cancel.json',1024)!==null)throw new RuntimeException('timed_out');
            $raw=$this->store->readFile('operations/'.$id.'/guard.json',4096);$guard=$raw===null?null:json_decode($raw,true,16,JSON_THROW_ON_ERROR);
            if(!is_array($guard)||($guard['child']??null)!==$t['worker']||!is_numeric($guard['deadline']??null)||AsusUpdateStore::uptime()>=$guard['deadline'])throw new RuntimeException('timed_out');
            [$env,$candidate]=$this->validate($id,false);
            $status=@file_get_contents('/proc/self/status');if(!is_string($status)||!preg_match('/^PPid:\s+([0-9]+)/m',$status,$m))throw new RuntimeException('invalid_state');
            $installer=AsusUpdateLifecycle::identity((int)$m[1]);$expected=$this->store->path('operations/'.$id.'/runtime/update-launch');
            if($installer===null||$installer['exe']!==$expected||$installer['uid']!==$this->owner())throw new RuntimeException('invalid_state');
            $intent=$this->lifecycle->intent();
            // Sticky boundary is serialized with guardian cancellation. From
            // here neither the worker nor opkg may be killed by that deadline.
            $this->store->writeFile('operations/'.$id.'/boundary.json',json_encode(['phase'=>'installing'],JSON_THROW_ON_ERROR));
            $this->ticket($id,'stopping',['installer'=>$installer,'intent'=>$intent]);
            $this->store->update($id,['intent'=>$intent,'phase'=>'stopping']);
            $this->assertDnsUpdateReady();
            (new AsusSmartDnsLifecycle(new AsusSmartDnsStore()))->stop('upgrade');
            $this->lifecycle->stop();
            $this->ticket($id,'installing');$this->store->update($id,['phase'=>'installing']);
        }finally{flock($f,LOCK_UN);fclose($f);}
    }
    private function install(string $id): void
    {
        $p=@proc_open([$this->store->path('operations/'.$id.'/runtime/update-launch'),$id],
            [0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',
            ['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C','LC_ALL'=>'C']);
        if(!is_resource($p))throw new RuntimeException('launch_failed');$exit=null;
        try{do{$status=proc_get_status($p);if(!$status['running']){$exit=$status['exitcode'];break;}usleep(25000);}while(true);}
        finally{$closed=proc_close($p);if($exit===null||$exit<0)$exit=$closed;}
        if($exit!==0){
            $raw=$this->store->readFile('operations/'.$id.'/preflight-error.json',1024);
            if($raw!==null){$value=json_decode($raw,true,4,JSON_THROW_ON_ERROR);throw new RuntimeException($value['code']??'install_failed');}
            if($exit===73&&$this->store->readFile('operations/'.$id.'/boundary.json',1024)===null)throw new RuntimeException('opkg_busy');
            throw new RuntimeException('install_failed');
        }
    }
    private function webHealth(): bool
    {
        if(isset($this->options['web_health']))return (bool)($this->options['web_health'])();
        $run=$this->options['web_run']??'/tmp/nfqws-asus-web';AsusUpdateStore::noLinks($run);$dir=@lstat($run);
        $path=$run.'/lighttpd.conf';AsusUpdateStore::noLinks($path);$file=@lstat($path);
        if(!$dir||($dir['mode']&0170000)!==0040000||$dir['uid']!==$this->owner()||($dir['mode']&0777)!==0700||!$file||($file['mode']&0170000)!==0100000||$file['uid']!==$this->owner()||$file['nlink']!==1||($file['mode']&0777)!==0600||$file['size']>16384)throw new RuntimeException('invalid_state');
        // The staged Entware PHP deliberately runs without optional extensions.
        // Validate a literal IPv4 bind without requiring php8-mod-filter.
        $octet='(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])';
        $config=@file_get_contents($path);if(!is_string($config)||preg_match_all('/^server\.bind\s*=\s*"([^"\r\n]+)"\s*$/m',$config,$matches)!==1||preg_match('~^'.$octet.'(?:\.'.$octet.'){3}$~D',$matches[1][0])!==1)throw new RuntimeException('invalid_state');
        $address=$matches[1][0];$port=$this->options['health_port']??90;if(!is_int($port)||$port<1||$port>65535)throw new RuntimeException('invalid_state');
        $end=AsusUpdateStore::uptime()+10;
        do{$errno=0;$error='';$socket=@stream_socket_client('tcp://'.$address.':'.$port,$errno,$error,1,STREAM_CLIENT_CONNECT);
            if(is_resource($socket)){stream_set_timeout($socket,1);fwrite($socket,"GET / HTTP/1.0\r\nHost: ".$address.':'.$port."\r\nConnection: close\r\n\r\n");$line=fgets($socket,1024);fclose($socket);if(is_string($line)&&preg_match('~^HTTP/1\.[01] 200 ~',$line))return true;}
            usleep(100000);
        }while(AsusUpdateStore::uptime()<$end);return false;
    }
    public function apply(string $id): array
    {
        $apply=$this->store->lease('apply.lock');
        try{return $this->store->withOperationLock($id,function()use($id){
            $job=$this->store->readOperation($id);if($job['state']!=='applying')return $job;$ticket=false;
            try{
                $this->assertDnsUpdateReady();
                $identity=AsusUpdateLifecycle::identity(getmypid());$runtime=$this->store->path('operations/'.$id.'/runtime').'/';
                if($identity===null||$identity['uid']!==$this->owner()||!str_starts_with($identity['exe'],$runtime)||($identity['exe']!==$runtime.'php'&&!preg_match('~^lib/ld[a-zA-Z0-9_.-]+$~D',substr($identity['exe'],strlen($runtime)))))throw new RuntimeException('invalid_state');
                $this->writeTicket(['schema'=>1,'id'=>$id,'boot_id'=>AsusUpdateStore::boot(),'worker'=>$identity,'installer'=>null,'phase'=>'validating','intent'=>['mode'=>'stopped']]);$ticket=true;
                $this->store->update($id,['identity'=>$identity,'phase'=>'validating']);
                [$env,$candidate]=$this->validate($id,true);
                $this->install($id);
                $after=$this->prepare->environment();if($after['installed']!==$candidate['package_version'])throw new RuntimeException('version_mismatch');
                AsusUpdateSnapshot::verify($env['opt'],$this->store->path('operations/'.$id.'/backup'),$this->owner(),true);
                $t=$this->ticket($id,'starting');$this->store->update($id,['phase'=>'verifying','installed_version'=>$after['installed'],'settings_verified'=>true]);
                $this->lifecycle->web();if(!$this->webHealth())throw new RuntimeException('web_health_failed');
                $core=$this->lifecycle->restore($t['intent']);
                $this->ticket($id,'finished');return $this->store->update($id,['state'=>'succeeded','code'=>null,'phase'=>'finished','core_state'=>$core]);
            }catch(Throwable $e){
                if($ticket){try{$this->ticket($id,'finished');}catch(Throwable $ignored){}}
                return $this->store->update($id,['state'=>'failed','code'=>AsusUpdatePrepare::code($e)]);
            }
        });}finally{flock($apply,LOCK_UN);fclose($apply);}
    }
}
