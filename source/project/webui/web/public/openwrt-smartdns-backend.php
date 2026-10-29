<?php
require_once __DIR__.'/openwrt-smartdns-resolver.php';
require_once __DIR__.'/openwrt-dns-probe.php';

/** procd-owned native engine, independently guarded from the browser and core. */
final class NfqwsOpenWrtSmartDnsBackend implements NfqwsSmartDnsBackend
{
    private const ROOT='/tmp/nfqws2-native-state/smartdns-runtime';
    private string $root;
    private NfqwsOpenWrtDnsmasqResolver $resolver;
    private NfqwsOpenWrtDnsmasqOverlay $overlay;
    public function __construct(private AsusSmartDnsStore $store,private AsusSmartDnsInstaller $installer,array $paths=[],private array $deps=[])
    {$this->root=$paths['native']??self::ROOT;$this->resolver=new NfqwsOpenWrtDnsmasqResolver();$this->overlay=new NfqwsOpenWrtDnsmasqOverlay();}
    private static function now():float{return (float)explode(' ',file_get_contents('/proc/uptime'))[0];}
    private static function boot():string{return trim(file_get_contents('/proc/sys/kernel/random/boot_id'));}
    private function directory():void
    {
        foreach([dirname($this->root),$this->root]as $path){
            if(!file_exists($path)&&!is_link($path)){NfqwsPlatform::guardFile(dirname($path),basename($path));$mask=umask(0077);try{$ok=@mkdir($path,0700);}finally{umask($mask);}if(!$ok)throw new RuntimeException('storage_unavailable');}
            $s=@lstat($path);$mode=$s['mode']??0;
            if(!$s||is_link($path)||!is_dir($path)||$s['uid']!==0||($mode&0022)!==0||$path===$this->root&&($mode&0777)!==0700)throw new RuntimeException('invalid_state');
        }
    }
    private function file(string $name):string{return NfqwsPlatform::guardFile($this->root,$name);}
    private function read():?array
    {
        if(!file_exists($this->root)&&!is_link($this->root))return null;$this->directory();$file=$this->file('state.json');$s=@lstat($file);if(!$s)return null;
        if($s['uid']!==0||($s['mode']&0777)!==0600||$s['size']>524288)throw new RuntimeException('invalid_state');
        $v=json_decode((string)file_get_contents($file),true,32);
        if(!is_array($v)||($v['schema']??null)!=='1'||!preg_match('/^[a-f0-9]{32}$/D',$v['request_id']??'')||!preg_match('/^[a-f0-9]{64}$/D',$v['profile_hash']??'')||
            !preg_match('/^[a-f0-9-]{36}$/D',$v['boot_id']??'')||!in_array($v['phase']??null,['prepared','awaiting_confirmation','confirmed','rolling_back','rolled_back','conflict'],true)||
            !is_numeric($v['deadline']??null)||!is_array($v['resolver']??null))throw new RuntimeException('invalid_state');
        foreach(['guard_pid','runtime_pid','guard_ticks','runtime_ticks']as $key)if(!is_string($v[$key]??null)||!preg_match('/^[0-9]{1,20}$/D',$v[$key]))throw new RuntimeException('invalid_state');
        if(!is_string($v['runtime_exe']??null)||!is_string($v['last_code']??null))throw new RuntimeException('invalid_state');return $v;
    }
    public function state():?array
    {
        $s=$this->read();if($s!==null&&$s['boot_id']!==self::boot()){$s['phase']='rolled_back';$s['runtime_pid']=$s['guard_pid']='0';$s['runtime_ticks']=$s['guard_ticks']='0';$s['runtime_exe']='';}return $s;
    }
    private function write(string $name,string $raw):void
    {
        $this->directory();$file=$this->file($name);$tmp=$this->file('.write-'.bin2hex(random_bytes(8)));$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(fwrite($f,$raw)!==strlen($raw)||!fflush($f)||!chmod($tmp,0600))throw new RuntimeException('storage_unavailable');}finally{fclose($f);}
        if(!rename($tmp,$file)){unlink($tmp);throw new RuntimeException('storage_unavailable');}
    }
    private function save(array $s):void{$this->write('state.json',json_encode($s,JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES)."\n");}
    private function locked(callable $fn,int $budget=8):mixed
    {
        $this->directory();$mask=umask(0077);try{$f=fopen($this->file('state.lock'),'c');}finally{umask($mask);}if(!$f)throw new RuntimeException('storage_unavailable');
        try{
            $end=hrtime(true)+min(8,max(0,$budget))*1000000000;
            while(!flock($f,LOCK_EX|LOCK_NB)){if(hrtime(true)>=$end)throw new RuntimeException('busy');usleep(20000);}
            return $fn($f);
        }finally{flock($f,LOCK_UN);fclose($f);}
    }
    private function checked(array $job):array
    {
        $s=$this->read();if($s===null||$s['boot_id']!==self::boot()||$s['request_id']!==($job['request_id']??null)||$s['profile_hash']!==($job['profile_hash']??null))throw new RuntimeException('invalid_state');return $s;
    }
    private function identity(array $s,string $kind):?array
    {
        if($s['boot_id']!==self::boot())return null;$identity=AsusDpiRuntime::identity((int)$s[$kind.'_pid']);
        if($identity===null||$identity['boot_id']!==$s['boot_id']||$identity['starttime']!==$s[$kind.'_ticks'])return null;
        $status=(string)@file_get_contents('/proc/'.$identity['pid'].'/status');if(!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',$status))return null;
        $argv=explode("\0",rtrim((string)@file_get_contents('/proc/'.$identity['pid'].'/cmdline'),"\0"));
        if($kind==='guard')return $argv===['/bin/sh','/usr/lib/nfqws2/smartdns/runtime.sh']?$identity:null;
        return $identity['exe']===$s['runtime_exe']&&$argv===[$s['runtime_exe'],'-f','-c',$this->root.'/runtime.conf','-p',$this->root.'/runtime.pid']?$identity:null;
    }
    public function baseline():array
    {
        $b=$this->resolver->collect();$engine=$this->installer->artifact()['sha256'];$b['hash']=hash('sha256',$b['hash'].$engine);return $b;
    }
    public function prepare(array $job,array $snapshot):void
    {
        $this->locked(function()use($job,$snapshot){
            $profile=$snapshot['candidate_profile']??null;$hash=$job['profile_hash']??'';$id=$job['request_id']??'';
            if(!is_array($profile)||!preg_match('/^[a-f0-9]{32}$/D',$id)||!is_string($hash)||!hash_equals(AsusSmartDnsProfile::hash($profile),$hash))throw new RuntimeException('invalid_state');
            $prior=$this->state();if($prior!==null&&($prior['phase']!=='rolled_back'||$this->identity($prior,'guard')!==null||$this->identity($prior,'runtime')!==null))throw new RuntimeException('busy');
            $baseline=$snapshot['baseline']??null;if(!is_array($baseline)||!is_string($baseline['config']??null)||!is_string($baseline['original']??null)||!is_string($baseline['text']??null))throw new RuntimeException('invalid_state');
            if(!AsusSmartDnsHook::profileRouting($baseline['text'],$profile))throw new RuntimeException('existing_dns_rules');
            // Conditional VPN DNS remains authoritative. Refuse overlapping
            // profile targets rather than claiming they were overridden.
            $conditional=preg_replace('/^[\t ]*server[\t ]*=[\t ]*\/([^\r\n]+)\/[^\r\n\/]*$/m','local=/$1/',$baseline['text']);
            if(!AsusSmartDnsHook::profileRouting($conditional,$profile))throw new RuntimeException('existing_dns_rules');
            if($this->overlay->routing($baseline)!=='external')throw new RuntimeException('hook_conflict');
            if(!$this->query(53,'example.com'))throw new RuntimeException('native_fallback_unavailable');
            $bundle=$this->installer->binaryDirectory();$digest=basename($bundle);if(!preg_match('/^[a-f0-9]{64}$/D',$digest))throw new RuntimeException('unsupported_binary');
            foreach(['udp','tcp']as $transport){$socket=@stream_socket_server($transport.'://127.0.0.1:6054',$errno,$error,STREAM_SERVER_BIND|($transport==='tcp'?STREAM_SERVER_LISTEN:0));if(!$socket)throw new RuntimeException('port_busy');fclose($socket);}
            $s=['schema'=>'1','request_id'=>$id,'profile_hash'=>$hash,'baseline_hash'=>$job['baseline_hash'],'boot_id'=>self::boot(),'phase'=>'prepared','deadline'=>sprintf('%.3f',self::now()+30),
                'guard_pid'=>'0','guard_ticks'=>'0','runtime_pid'=>'0','runtime_ticks'=>'0','runtime_exe'=>$bundle.'/smartdns','resolver'=>$baseline,'last_code'=>''];
            $config=AsusSmartDnsProfile::render($profile,6054)['config'].'address /nfqws-'.$id.'.example.net/1.0.0.1'."\n";
            $this->write('runtime.conf',$config);$this->save($s);
        });
    }
    /** A procd restart after owner loss restores fallback before ending its orphan. */
    public function launchSpec():?string
    {
        return $this->locked(function($lease){
            $s=$this->read();if($s===null||$s['boot_id']!==self::boot()||$s['phase']==='rolled_back')return null;
            if($s['phase']!=='prepared'||$s['guard_pid']!=='0'){
                if($this->identity($s,'guard')!==null)throw new RuntimeException('busy');
                $this->restoreState($s,'interrupted',$lease);$this->killRuntime($s);return null;
            }
            if(self::now()>=(float)$s['deadline']){$this->restoreState($s,'timed_out',$lease);return null;}
            $bundle=$this->installer->binaryDirectory();if($s['runtime_exe']!==$bundle.'/smartdns')throw new RuntimeException('invalid_state');
            return $s['request_id'].' '.basename($bundle);
        });
    }
    private function killRuntime(array $s):void
    {
        foreach(['-TERM','-KILL']as $signal){$identity=$this->identity($s,'runtime');if($identity===null)return;
            NfqwsPlatform::run(['/bin/busybox','kill',$signal,(string)$identity['pid']],2);$end=self::now()+2;
            do{if($this->identity($s,'runtime')===null)return;usleep(20000);}while(self::now()<$end);
        }
        if($this->identity($s,'runtime')!==null)throw new RuntimeException('runtime_stop_failed');
    }
    public function healthy():bool
    {
        try{$s=$this->state();return $s!==null&&in_array($s['phase'],['awaiting_confirmation','confirmed'],true)&&$this->identity($s,'guard')!==null&&$this->identity($s,'runtime')!==null&&AsusSmartDnsCandidate::ownsPorts((int)$s['runtime_pid'],6054);}catch(Throwable $e){return false;}
    }
    public function forwarding():string
    {try{$s=$this->state();if($s===null)return 'external';$current=$this->resolver->primary();if($current['instance']!==$s['resolver']['instance']||$current['config']!==$s['resolver']['config'])return 'external';return $this->overlay->routing($s['resolver']);}catch(Throwable $e){return 'unknown';}}
    public function lastCode(string $id):?string
    {$s=$this->state();return $s!==null&&$s['request_id']===$id&&$s['last_code']!==''?$s['last_code']:null;}
    /** Called only by the fixed CLI child of the procd shell owner. */
    public function ownerReady(string $id,int $guard,int $runtime):void
    {
        $this->locked(function()use($id,$guard,$runtime){$s=$this->read();if($s===null||$s['request_id']!==$id||$s['phase']!=='prepared')throw new RuntimeException('invalid_state');
            foreach(['guard'=>$guard,'runtime'=>$runtime]as $kind=>$pid){$v=AsusDpiRuntime::identity($pid);if($v===null)throw new RuntimeException('guard_unavailable');$s[$kind.'_pid']=(string)$pid;$s[$kind.'_ticks']=$v['starttime'];}
            if($this->identity($s,'guard')===null||$this->identity($s,'runtime')===null)throw new RuntimeException('guard_unavailable');$this->save($s);
        });
    }
    public function guard(array $job,array $profile):array
    {
        $s=$this->checked($job);if($s['phase']!=='prepared')throw new RuntimeException('invalid_state');
        $r=NfqwsPlatform::run(['/etc/init.d/nfqws2-native-dns','start'],5);if($r['status']!==0)throw new RuntimeException('guard_unavailable');
        $end=self::now()+7;$failure='guard_unavailable';
        do{$s=$this->checked($job);$guard=$this->identity($s,'guard');$runtime=$this->identity($s,'runtime');
            $failure='guard_unavailable';
            if($guard!==null&&$runtime!==null&&AsusSmartDnsCandidate::ownsPorts($runtime['pid'],6054)){
                // A verified live owner with no usable DNS answer is an
                // upstream validation failure, not a lost guardian.
                $failure='dns_validation_failed';
                if($this->query(6054,'example.com'))return ['guard_identity'=>$guard,'identity'=>$runtime];
            }usleep(20000);
        }while(self::now()<$end);
        try{if($this->restore($job,[])!==true||$this->stop($job)!==true)throw new RuntimeException('runtime_stop_failed');}catch(Throwable $e){throw new AsusSmartDnsUnresolvedGuard('guard_unavailable');}throw new RuntimeException($failure);
    }
    public function forward(array $job):array
    {
        return $this->locked(function($lease)use($job){$s=$this->checked($job);if($s['phase']!=='prepared'||$this->identity($s,'guard')===null||$this->identity($s,'runtime')===null)throw new RuntimeException('guard_unavailable');
            if(!hash_equals($job['baseline_hash'],$this->baseline()['hash']))throw new RuntimeException('stale_baseline');
            $this->resolver->transaction($s['resolver'],'forward',$s['request_id'],$lease);$s=$this->checked($job);
            if($s['phase']!=='awaiting_confirmation'||!$this->dns())throw new RuntimeException('dns_validation_failed');return ['deadline_uptime'=>(float)$s['deadline']];
        });
    }
    /** The child inherits the caller's held state lease; no lock re-acquisition. */
    private function resolverOwner(string $id,string $operation,string $instance):array
    {
        $fd=@stat('/proc/self/fd/9');$lock=@lstat($this->file('state.lock'));
        if(!$fd||!$lock||$fd['dev']!==$lock['dev']||$fd['ino']!==$lock['ino']||$lock['uid']!==0||($lock['mode']&0777)!==0600||$lock['nlink']!==1)throw new RuntimeException('invalid_state');
        $status=(string)file_get_contents('/proc/self/status');if(!preg_match('/^PPid:\s+([0-9]+)\s*$/m',$status,$m))throw new RuntimeException('invalid_state');
        $parent=explode("\0",rtrim((string)@file_get_contents('/proc/'.$m[1].'/cmdline'),"\0"));
        if($parent!==['/bin/sh','/usr/lib/nfqws2/smartdns/dnsmasq-transaction.sh',$id,$operation,$instance])throw new RuntimeException('invalid_state');
        $s=$this->read();if($s===null||$s['boot_id']!==self::boot()||$s['request_id']!==$id||$s['resolver']['instance']!==$instance||!in_array($operation,['forward','restore'],true)||$s['phase']!==($operation==='forward'?'prepared':'rolling_back'))throw new RuntimeException('invalid_state');
        return $s;
    }
    public function resolverPreflight(string $id,string $operation,string $instance):void
    {
        $s=$this->resolverOwner($id,$operation,$instance);$routing=$this->overlay->routing($s['resolver']);
        if($routing==='unknown'||$operation==='forward'&&$routing!=='external')throw new RuntimeException('hook_conflict');
    }
    public function resolverSwap(string $id,string $operation,string $instance,array $frame,string $nonce):void
    {
        $s=$this->resolverOwner($id,$operation,$instance);NfqwsOpenWrtDnsmasqResolver::validateCommit($frame,$instance,$s['resolver']['config'],$id.':'.$operation.':'.$nonce);
        $fresh=$this->baseline();$s['resolver']=$fresh['snapshot'];$this->save($s);
        if($operation==='forward'){
            if(!hash_equals($s['baseline_hash'],$fresh['hash']))throw new RuntimeException('stale_baseline');
            $this->overlay->apply($s['resolver']);$s['phase']='awaiting_confirmation';$s['deadline']=sprintf('%.3f',self::now()+90);$this->save($s);
        }
    }
    private function query(int $port,string $name,?string $expected=null):bool
    {
        foreach(['udp','tcp']as $transport){$r=NfqwsOpenWrtDnsProbe::query('127.0.0.1',$port,$name,'A',$transport);
            if(!$r['ok']||$r['rcode']!==0||$r['truncated']||!$r['answers']||$expected!==null&&$r['answers']!==[$expected])return false;}return true;
    }
    public function dns():bool
    {$s=$this->state();return $s!==null&&$this->query(53,'nfqws-'.$s['request_id'].'.example.net','1.0.0.1')&&$this->query(53,'example.com');}
    public function confirm(array $job):bool
    {
        return $this->locked(function()use($job){$s=$this->checked($job);if($s['phase']!=='awaiting_confirmation'||self::now()>=(float)$s['deadline']||!$this->healthy()||$this->forwarding()!=='managed'||!$this->dns())return false;
            $s['phase']='confirmed';$this->save($s);return true;});
    }
    private function restoreState(array $s,?string $reason,$lease):bool
    {
        if($s['phase']==='rolled_back')return true;$routing=$this->overlay->routing($s['resolver']);
        if($routing==='unknown'){$s['phase']='conflict';$s['last_code']='hook_conflict';$this->save($s);throw new RuntimeException('hook_conflict');}
        $restart=$routing==='managed'||$s['phase']!=='prepared';$s['phase']='rolling_back';if($reason!==null)$s['last_code']=$reason;$this->save($s);
        try{if($restart)$this->resolver->transaction($s['resolver'],'restore',$s['request_id'],$lease);if(!$this->query(53,'example.com'))throw new RuntimeException('dns_validation_failed');}
        catch(Throwable $e){
            $latest=$this->read();if($latest!==null&&$latest['request_id']===$s['request_id'])$s=$latest;
            $s['phase']='conflict';$s['last_code']=in_array($e->getMessage(),['hook_conflict','dns_restart_failed','primary_dns_unverified','dns_validation_failed'],true)?$e->getMessage():'invalid_state';$this->save($s);throw $e;
        }
        $latest=$this->read();if($latest!==null&&$latest['request_id']===$s['request_id'])$s=$latest;
        $s['phase']='rolled_back';$this->save($s);return true;
    }
    public function restore(array $job,array $snapshot):bool
    {
        return $this->locked(function($lease)use($job){$s=$this->read();
            if($s===null||$s['boot_id']!==self::boot()){
                if(($job['boot']??self::boot())===self::boot())throw new RuntimeException('invalid_state');
                $this->resolver->collect();return $this->query(53,'example.com');
            }
            return $this->restoreState($this->checked($job),null,$lease);
        });
    }
    public function stop(array $job):bool
    {
        $s=$this->read();if($s===null||$s['boot_id']!==self::boot())return ($job['boot']??self::boot())!==self::boot();
        $s=$this->checked($job);if($s['phase']!=='rolled_back')return false;
        $r=NfqwsPlatform::run(['/etc/init.d/nfqws2-native-dns','stop'],20);if($r['status']!==0)return false;
        // procd acknowledges service.delete before the owner/child exit.
        $end=self::now()+22;do{if($this->identity($s,'runtime')===null&&$this->identity($s,'guard')===null)return true;usleep(100000);}while(self::now()<$end);return false;
    }
    /** Runtime shell keeps its child alive until fallback DNS is verified. */
    public function ownerTick(string $id,bool $exiting=false):int
    {
        return $this->locked(function($lease)use($id,$exiting){$s=$this->read();if($s===null||$s['request_id']!==$id||$s['boot_id']!==self::boot())throw new RuntimeException('invalid_state');
            if($s['phase']==='rolled_back')return 1;
            $reason=$exiting?'interrupted':($this->identity($s,'runtime')===null?'runtime_lost':null);
            if($reason===null&&in_array($s['phase'],['prepared','awaiting_confirmation'],true)&&self::now()>=(float)$s['deadline'])$reason='timed_out';
            if($reason===null&&in_array($s['phase'],['confirmed','awaiting_confirmation'],true)&&$this->forwarding()!=='managed')$reason='hook_conflict';
            if($reason===null&&$s['phase']==='confirmed'&&!$this->resolver->sourcesUnchanged($s['resolver']))$reason='stale_baseline';
            if($reason!==null){$this->restoreState($s,$reason,$lease);return 1;}
            return $s['phase']==='confirmed'?10:0;
        },0);
    }
    public function canStop():bool
    {$s=$this->state();return $s===null||$s['phase']==='rolled_back';}
    public function dependencies():array
    {$out=[];foreach(['baseline','prepare','guard','forward','dns','confirm','restore','stop']as $name)$out[$name]=[$this,$name];$out['release']=static function(array $job):void{};return $out;}
}
