<?php
require_once __DIR__.'/smartdns-connect.php';
require_once __DIR__.'/smartdns-baseline.php';
require_once __DIR__.'/smartdns-candidate.php';

/** Trusted native recovery files. Paths/dependencies are local fixtures only. */
final class AsusSmartDnsNativeBackend
{
    private array $paths;
    private int $owner;
    private const FIELDS=['schema','request_id','boot_id','phase','deadline','guard_pid','guard_ticks','runtime_pid','runtime_ticks','runtime_exe','hook_created','profile_hash'];
    private const CODE=['native-state.sh','native-common.sh','primary-dns.sh','recovery.sh','lifecycle.sh','forwarding.awk','hook-edit.awk'];
    public function __construct(private AsusSmartDnsStore $store,private AsusSmartDnsInstaller $installer,array $paths=[],private array $deps=[])
    {
        $this->paths=$paths+['native'=>'/jffs/nfqws2-asus-smartdns','hook'=>'/jffs/scripts/dnsmasq.postconf'];
        $library=$paths['library']??AsusDpiStore::optPath('/lib/nfqws2-asus/smartdns');
        $this->paths['library']=realpath($library)?:$library;
        $this->owner=$deps['owner']??0;
    }
    private function safePath(string $path): void
    {
        for ($p=$path;$p!=='/' && $p!=='.';$p=dirname($p)) if (is_link($p)) throw new RuntimeException('invalid_state');
    }
    private function regular(string $path,int $limit,bool $private=false): array
    {
        $this->safePath($path);clearstatcache(true,$path);$s=@lstat($path);
        if (!$s || ($s['mode']&0170000)!==0100000 || $s['uid']!==$this->owner || $s['nlink']!==1 || ($s['mode']&0022)!==0 || ($private && ($s['mode']&0777)!==0600) || $s['size']>$limit) throw new RuntimeException('invalid_state');
        return $s;
    }
    private function readExact(string $path,int $limit): string
    {
        $before=$this->regular($path,$limit);$raw=@file_get_contents($path);
        if (!is_string($raw) || strlen($raw)!==$before['size']) throw new RuntimeException('storage_unavailable');
        $after=$this->regular($path,$limit);
        foreach (['dev','ino','size'] as $key) if ($after[$key]!==$before[$key]) throw new RuntimeException('invalid_state');
        return $raw;
    }
    private function directory(string $path,bool $create=false,bool $private=true): void
    {
        $this->safePath($path);
        if ($create && !file_exists($path)) {
            $mask=umask(0077);try {$ok=@mkdir($path,0700);}finally {umask($mask);}
            if (!$ok) throw new RuntimeException('insufficient_space');
        }
        $s=@lstat($path);
        if (!$s || ($s['mode']&0170000)!==0040000 || $s['uid']!==$this->owner || ($s['mode']&0022)!==0 || ($private && ($s['mode']&0777)!==0700)) throw new RuntimeException('invalid_state');
    }
    private static function validState(array $s): bool
    {
        $keys=array_keys($s);sort($keys);$want=self::FIELDS;sort($want);
        if ($keys!==$want || $s['schema']!=='1') return false;
        foreach ($s as $v) if (!is_string($v) || strpbrk($v,"\0\t\r\n")!==false) return false;
        if (!preg_match('/^[a-f0-9]{32}$/D',$s['request_id']) || !preg_match('/^[a-f0-9]{64}$/D',$s['profile_hash']) || !preg_match('/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/D',$s['boot_id'])) return false;
        if (!in_array($s['phase'],['prepared','awaiting_confirmation','confirmed','rolling_back','rolled_back','conflict'],true) || !preg_match('/^[0-9]{1,16}\.[0-9]{3}$/D',$s['deadline']) || !in_array($s['hook_created'],['0','1'],true)) return false;
        foreach (['guard','runtime'] as $name) {
            $pid=$s[$name.'_pid'];$ticks=$s[$name.'_ticks'];
            if (!preg_match('/^(?:0|[1-9][0-9]{0,9})$/D',$pid) || (float)$pid>2147483647 || $pid==='1' || !preg_match('/^[0-9]{1,20}$/D',$ticks) || ($pid==='0' && $ticks!=='0') || ($pid!=='0' && $ticks==='0')) return false;
        }
        if ($s['runtime_pid']==='0' ? $s['runtime_exe']!=='' : (!str_starts_with($s['runtime_exe'],'/') || strlen($s['runtime_exe'])>4096)) return false;
        if (in_array($s['phase'],['awaiting_confirmation','confirmed'],true) && ($s['runtime_pid']==='0' || $s['guard_pid']==='0')) return false;
        return true;
    }
    public function state(): ?array
    {
        $root=$this->paths['native'];$this->safePath($root);
        if (!file_exists($root)) return null;
        $this->directory($root);$this->regular($root.'/state',16384,true);
        $raw=@file_get_contents($root.'/state');
        if (!is_string($raw) || !str_ends_with($raw,"\n") || str_contains($raw,"\0")) throw new RuntimeException('invalid_state');
        $values=[];
        foreach (explode("\n",substr($raw,0,-1)) as $line) {
            $parts=explode("\t",$line);
            if (count($parts)!==2 || array_key_exists($parts[0],$values)) throw new RuntimeException('invalid_state');
            $values[$parts[0]]=$parts[1];
        }
        if (!self::validState($values)) throw new RuntimeException('invalid_state');
        return $values;
    }
    private function write(string $path,string $raw,int $mode): void
    {
        $this->safePath($path);
        if (file_exists($path)) $this->regular($path,262144);
        $tmp=dirname($path).'/.native-'.bin2hex(random_bytes(12));$mask=umask(0077);
        try {$f=@fopen($tmp,'xb');}finally {umask($mask);}
        if (!$f) throw new RuntimeException('insufficient_space');
        try {
            if (@fwrite($f,$raw)!==strlen($raw) || !@fflush($f) || function_exists('fsync') && !@fsync($f) || !@chmod($tmp,$mode)) throw new RuntimeException('insufficient_space');
            fclose($f);$f=null;
            if (!@rename($tmp,$path)) throw new RuntimeException('invalid_state');
        } finally {if (is_resource($f)) fclose($f);if (is_file($tmp)) unlink($tmp);}
    }
    private function files(): array
    {
        $library=$this->paths['library'];$this->directory($library,false,false);
        try {$tools=json_decode($this->readExact($library.'/tools.json',4096),true,8,JSON_THROW_ON_ERROR);}
        catch (Throwable $e) {throw new RuntimeException('unsupported_binary');}
        $probe=$this->readExact($library.'/dns-probe',131072);
        if (($tools['schema_version']??null)!==1 || !is_string($tools['dns_probe_sha256']??null) || !preg_match('/^[a-f0-9]{64}$/D',$tools['dns_probe_sha256']) || !hash_equals($tools['dns_probe_sha256'],hash('sha256',$probe))) throw new RuntimeException('unsupported_binary');
        $files=['dns-probe'=>$probe,'owned-block'=>AsusSmartDnsHook::BLOCK,'state.lock'=>''];
        foreach (self::CODE as $name) {
            $code=$this->readExact($library.'/'.$name,262144);
            if ($code==='' || str_contains($code,"\0") || str_ends_with($name,'.sh') && !str_starts_with($code,"#!/bin/sh\n")) throw new RuntimeException('unsupported_binary');
            $files[$name]=$code;
        }
        return $files;
    }
    private function recoveryStorage(string $parent): bool
    {
        if (isset($this->deps['recovery_storage'])) return ($this->deps['recovery_storage'])()===true;
        $canonical=realpath($parent);$raw=isset($this->deps['mounts'])?($this->deps['mounts'])():@file_get_contents('/proc/mounts');$selected=null;
        if ($canonical===false || !is_string($raw) || strlen($raw)>262144) return false;
        foreach (explode("\n",$raw) as $line) {
            $v=preg_split('/\s+/',trim($line));if (count($v)<4) continue;
            $decode=static fn($s)=>preg_replace_callback('/\\\\(040|011|012|134)/',static fn($m)=>chr(octdec($m[1])),$s);
            $path=$decode($v[1]);
            if (($canonical===$path || str_starts_with($canonical,rtrim($path,'/').'/')) && ($selected===null || strlen($path)>strlen($selected['path'])))
                $selected=['path'=>$path,'device'=>$decode($v[0]),'type'=>$v[2],'options'=>explode(',',$v[3])];
        }
        if ($selected===null || !in_array('rw',$selected['options'],true) || in_array('ro',$selected['options'],true)) return false;
        if (in_array($selected['type'],['jffs2','ubifs'],true)) return true;
        $device=isset($this->deps['canonical_device'])?($this->deps['canonical_device'])($selected['device']):(realpath($selected['device'])?:$selected['device']);
        return in_array($selected['type'],['ext2','ext3','ext4','f2fs'],true) && is_string($device) && (bool)preg_match('~^/dev/mmcblk[0-9]+p[0-9]+$~D',$device);
    }
    public function prepare(array $job,array $snapshot): void
    {
        $id=$job['request_id']??null;$hash=$job['profile_hash']??null;$profile=$snapshot['candidate_profile']??null;
        if (!is_string($id) || !preg_match('/^[a-f0-9]{32}$/D',$id) || !is_string($hash) || !is_array($profile) || !hash_equals(AsusSmartDnsProfile::hash($profile),$hash)) throw new RuntimeException('invalid_state');
        $root=$this->paths['native'];$prior=$this->state();
        if ($prior!==null && $prior['phase']!=='rolled_back') throw new RuntimeException('busy');
        if ($prior!==null) {
            // A completed restore can precede the old guardian's final tick.
            // Do not replace its state/scripts while it still owns that state.
            $end=self::clock()+3;
            while ($this->identity($prior,'guard')!==null) {
                if (self::clock()>=$end) throw new RuntimeException('busy');
                usleep(20000);
            }
            if ($this->identity($prior,'runtime')!==null) throw new RuntimeException('invalid_state');
        }
        $files=$this->files();
        $hook=$snapshot['baseline']['hook']??null;
        if (!is_array($hook) || !in_array($hook['state']??null,['available','missing'],true) || !is_string($hook['value']??null)) throw new RuntimeException('invalid_state');
        AsusSmartDnsHook::install($hook['value']);$files['hook-original']=$hook['value'];
        $config=$snapshot['baseline']['config']??null;
        if (!is_array($config) || ($config['state']??null)!=='available' || !is_string($config['value']??null)) throw new RuntimeException('invalid_state');
        if (!AsusSmartDnsHook::profileRouting($config['value'],$profile)) throw new RuntimeException('existing_dns_rules');
        $parent=dirname($root);$this->safePath($parent);
        if (!$this->recoveryStorage($parent)) throw new RuntimeException('recovery_unavailable');
        $space=isset($this->deps['space'])?($this->deps['space'])($parent):@disk_free_space($parent);
        if (!is_numeric($space) || $space<array_sum(array_map('strlen',$files))+262144) throw new RuntimeException('insufficient_space');
        // The caller explicitly requested Connect. Test the original DNS
        // before creating any recovery state, launching an engine or hook.
        $baselineReady=false;
        if (isset($this->deps['baseline_dns'])) $baselineReady=($this->deps['baseline_dns'])()===true;
        else {
            $reply=$this->run([$this->paths['library'].'/dns-probe','127.0.0.1','53','example.com','A','udp','2500'],3);
            try {$dns=json_decode($reply['out'],true,12,JSON_THROW_ON_ERROR);}catch (Throwable $e) {$dns=null;}
            $answers=$dns['answers']??null;
            $baselineReady=$reply['exit']===0 && ($dns['ok']??null)===true && ($dns['rcode']??null)===0 && ($dns['truncated']??null)===false && is_array($answers) && array_is_list($answers) && count($answers)>0 && count($answers)<=64;
            if ($baselineReady) foreach ($answers as $address) if (!is_string($address) || ($packed=@inet_pton($address))===false || strlen($packed)!==4) {$baselineReady=false;break;}
        }
        if (!$baselineReady) throw new RuntimeException('native_fallback_unavailable');
        if (isset($this->deps['primary_dns'])) $primaryReady=($this->deps['primary_dns'])()===true;
        else {
            $primary=$this->run(['/bin/sh',$this->paths['library'].'/primary-dns.sh','identity'],3);
            $primaryReady=$primary['exit']===0 && (bool)preg_match('/^[1-9][0-9]{0,9} [1-9][0-9]{0,19}\n$/D',$primary['out']);
        }
        if (!$primaryReady) throw new RuntimeException('primary_dns_unverified');
        $state=['schema'=>'1','request_id'=>$id,'boot_id'=>trim(file_get_contents('/proc/sys/kernel/random/boot_id')),'phase'=>'prepared','deadline'=>'0.000',
            'guard_pid'=>'0','guard_ticks'=>'0','runtime_pid'=>'0','runtime_ticks'=>'0','runtime_exe'=>'',
            'hook_created'=>($snapshot['baseline']['hook']['state']??null)==='missing'?'1':'0','profile_hash'=>$hash];
        if (!self::validState($state)) throw new RuntimeException('invalid_state');
        $files['state']='';foreach (self::FIELDS as $key) $files['state'].=$key."\t".$state[$key]."\n";
        $stage=$root.'.prepare-'.$id;
        if (file_exists($stage) || is_link($stage)) throw new RuntimeException('invalid_state');
        $this->directory($stage,true);
        try {
            foreach ($files as $name=>$raw) $this->write($stage.'/'.$name,$raw,str_ends_with($name,'.sh') || $name==='dns-probe'?0700:0600);
            if ($prior===null) {
                if (file_exists($root) || is_link($root) || !@rename($stage,$root)) throw new RuntimeException('invalid_state');
            } else {
                // Prior DNS is already restored. Install state last; an
                // interrupted code refresh cannot mark forwarding as active.
                foreach (array_keys($files) as $name) {
                    if ($name==='state.lock') continue;
                    if (file_exists($root.'/'.$name)) $this->regular($root.'/'.$name,262144);
                    if (!@rename($stage.'/'.$name,$root.'/'.$name)) throw new RuntimeException('invalid_state');
                }
            }
        } finally {
            if (is_dir($stage) && !is_link($stage)) {
                foreach (array_keys($files) as $name) if (is_file($stage.'/'.$name) && !is_link($stage.'/'.$name)) unlink($stage.'/'.$name);
                @rmdir($stage);
            }
        }
    }
    private function identity(array $state,string $kind): ?array
    {
        $pid=(int)$state[$kind.'_pid'];$v=AsusDpiRuntime::identity($pid);
        if ($v===null || $v['boot_id']!==$state['boot_id'] || $v['starttime']!==$state[$kind.'_ticks']) return null;
        $status=@file_get_contents('/proc/'.$pid.'/status');
        if (!is_string($status) || !preg_match('/^Uid:\s+'.$this->owner.'\s+'.$this->owner.'\s+'.$this->owner.'\s+'.$this->owner.'\s*$/m',$status)) return null;
        if ($kind==='runtime' && $v['exe']!==$state['runtime_exe'] && $v['exe']!==$state['runtime_exe'].' (deleted)') return null;
        return $v;
    }
    public function baseline(): array
    {
        if (isset($this->deps['baseline'])) return ($this->deps['baseline'])();
        return (new AsusSmartDnsBaseline(new AsusReportIO(),$this->installer,['managed_identity'=>function(){
            $state=$this->state();
            if ($state===null || $state['phase']==='rolled_back' || $state['runtime_exe']!==$this->installer->binaryDirectory().'/smartdns') return null;
            return $this->identity($state,'runtime');
        }]))->collect();
    }
    public function healthy(): bool
    {
        $s=$this->state();
        if ($s===null || !in_array($s['phase'],['awaiting_confirmation','confirmed'],true) || !is_executable($s['runtime_exe'])) return false;
        $runtime=$this->identity($s,'runtime');$guard=$this->identity($s,'guard');
        if ($runtime===null || $guard===null || !AsusSmartDnsCandidate::ownsPorts($runtime['pid'],6054)) return false;
        $cmd=explode("\0",rtrim((string)@file_get_contents('/proc/'.$guard['pid'].'/cmdline'),"\0"));
        return $cmd===['/bin/sh',$this->paths['native'].'/recovery.sh','guard',$s['request_id']];
    }
    public function lastCode(string $id): ?string
    {
        if (!preg_match('/^[a-f0-9]{32}$/D',$id)) throw new RuntimeException('invalid_request');
        $path=$this->paths['native'].'/recovery.log';
        if (!file_exists($path) && !is_link($path)) return null;
        $raw=$this->readExact($path,65536);$code=null;
        $allowed=['timed_out','runtime_lost','interrupted','hook_conflict','primary_dns_unverified','dns_restart_failed','dns_validation_failed','runtime_stop_failed','invalid_state'];
        foreach (explode("\n",$raw) as $line) if (preg_match('/^[0-9]+\.[0-9]{3} ([a-f0-9]{32}) ([a-z_]{1,64})$/D',$line,$m) && $m[1]===$id && in_array($m[2],$allowed,true)) $code=$m[2];
        return $code;
    }
    private function checkedJob(array $job): array
    {
        $s=$this->state();
        if ($s===null || $s['request_id']!==($job['request_id']??null) || $s['profile_hash']!==($job['profile_hash']??null)) throw new RuntimeException('invalid_state');
        return $s;
    }
    private function run(array $arguments,float $seconds=35): array
    {
        $p=@proc_open($arguments,[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes,'/',['PATH'=>'/usr/bin:/bin','LANG'=>'C']);
        if (!is_resource($p)) throw new RuntimeException('guard_unavailable');
        foreach ($pipes as $pipe) stream_set_blocking($pipe,false);
        $end=self::clock()+$seconds;$out='';$err='';$done=false;$exit=null;
        try {
            do {
                $out.=stream_get_contents($pipes[1],8193-strlen($out));$err.=stream_get_contents($pipes[2],8193-strlen($err));
                if (strlen($out)>8192 || strlen($err)>8192) throw new RuntimeException('output_limit');
                $s=proc_get_status($p);
                if (!$s['running']) {$exit=$s['exitcode'];$done=true;break;}
                if (self::clock()>=$end) throw new RuntimeException('timed_out');
                usleep(10000);
            } while (true);
            $out.=stream_get_contents($pipes[1],8193-strlen($out));
            if (strlen($out)>8192) throw new RuntimeException('output_limit');
            return ['exit'=>$exit,'out'=>$out];
        } finally {
            if (!$done) {proc_terminate($p,15);usleep(100000);$s=proc_get_status($p);if ($s['running']) proc_terminate($p,9);}
            foreach ($pipes as $pipe) fclose($pipe);
            proc_close($p);
        }
    }
    private static function clock(): float { $time=hrtime();return $time[0]+$time[1]/1e9; }
    private function control(string $operation,array $job): array
    {
        if (!in_array($operation,['forward','confirm','rollback','dns'],true)) throw new RuntimeException('invalid_request');
        $this->checkedJob($job);
        $end=self::clock()+($operation==='rollback'?15:2);
        do {
            $r=$this->run(['/bin/sh',$this->paths['native'].'/recovery.sh',$operation,$job['request_id']]);
            // Exit3 means the native state lock was not acquired; no state,
            // hook or service action has run. Never replay another exit code.
            if ($r['exit']!==3 || self::clock()>=$end) return $r;
            usleep(10000);
        } while (true);
    }
    public function guard(array $job,array $profile): array
    {
        $state=$this->checkedJob($job);
        if ($state['phase']!=='prepared' || $state['guard_pid']!=='0' || $state['runtime_pid']!=='0') throw new RuntimeException('invalid_state');
        try {
            $bundle=$this->installer->binaryDirectory();$digest=basename($bundle);
            if (!preg_match('/^[a-f0-9]{64}$/D',$digest) || !hash_equals($job['profile_hash'],AsusSmartDnsProfile::hash($profile))) throw new RuntimeException('invalid_state');
            $jobs=$this->store->directory(true).'/jobs';$this->directory($jobs,true);$run=$jobs.'/'.$job['request_id'];
            if (file_exists($run) || is_link($run)) throw new RuntimeException('invalid_state');
            $this->directory($run,true);$this->write($run.'/runtime.conf',AsusSmartDnsProfile::render($profile,6054)['config'],0600);$this->write($run.'/engine.digest',$digest."\n",0600);
            if (isset($this->deps['launch'])) ($this->deps['launch'])($job['request_id']);
            else {
                $r=$this->run([AsusDpiRuntime::BUSYBOX,'start-stop-daemon','-S','-b','-p',$run.'/guardian-launch.pid','-x','/bin/sh','--',$this->paths['native'].'/recovery.sh','guard',$job['request_id']],3);
                if ($r['exit']!==0) throw new RuntimeException('guard_unavailable');
            }
            $end=self::clock()+8;
            do {
                $state=$this->checkedJob($job);$guard=$this->identity($state,'guard');$runtime=$this->identity($state,'runtime');
                if ($guard!==null && $runtime!==null && $runtime['exe']===$bundle.'/smartdns') {
                    $ready=$this->paths['native'].'/ready';
                    if (is_file($ready)) {
                        $this->regular($ready,512,true);$proof=explode(' ',trim(file_get_contents($ready)));
                        $cmd=explode("\0",rtrim((string)@file_get_contents('/proc/'.$guard['pid'].'/cmdline'),"\0"));
                        if ($proof===[$job['request_id'],(string)$guard['pid'],$guard['starttime'],$guard['boot_id']] && $cmd===['/bin/sh',$this->paths['native'].'/recovery.sh','guard',$job['request_id']] && AsusSmartDnsCandidate::ownsPorts($runtime['pid'],6054))
                            return ['guard_identity'=>$guard,'identity'=>$runtime];
                    }
                }
                if (in_array($state['phase'],['conflict','rolled_back'],true)) throw new RuntimeException('guard_unavailable');
                usleep(20000);
            } while (self::clock()<$end);
            throw new RuntimeException('guard_unavailable');
        } catch (Throwable $error) {
            try {$cleanup=$this->control('rollback',$job);if ($cleanup['exit']!==0 || $this->checkedJob($job)['phase']!=='rolled_back') throw new RuntimeException('guard_unavailable');}
            catch (Throwable $cleanupError) {throw new AsusSmartDnsUnresolvedGuard('guard_unavailable');}
            throw $error;
        }
    }
    public function forward(array $job): array
    {
        if (!hash_equals($job['baseline_hash'],$this->baseline()['hash'])) throw new RuntimeException('stale_baseline');
        $r=$this->control('forward',$job);
        if ($r['exit']!==0) {
            $code=trim($r['out']);
            throw new RuntimeException(in_array($code,['hook_conflict','primary_dns_unverified','dns_restart_failed','dns_validation_failed','guard_unavailable','invalid_state'],true)?$code:'connection_failed');
        }
        $state=$this->checkedJob($job);
        if ($state['phase']!=='awaiting_confirmation') throw new RuntimeException('invalid_state');
        return ['deadline_uptime'=>(float)$state['deadline']];
    }
    public function dns(): bool
    {
        $job=$this->store->transaction();return $job!==null && $this->control('dns',$job)['exit']===0;
    }
    public function confirm(array $job): bool
    {
        $state=$this->checkedJob($job);$runtime=$this->identity($state,'runtime');
        return $runtime!==null && AsusSmartDnsCandidate::ownsPorts($runtime['pid'],6054) && $this->control('confirm',$job)['exit']===0 && $this->checkedJob($job)['phase']==='confirmed';
    }
    public function restore(array $job,array $snapshot): bool
    { return $this->control('rollback',$job)['exit']===0 && $this->checkedJob($job)['phase']==='rolled_back'; }
    public function stop(array $job): bool
    { $s=$this->checkedJob($job);return $s['phase']==='rolled_back' && $this->identity($s,'runtime')===null; }
    public function dependencies(): array
    {
        $out=[];foreach (['baseline','prepare','guard','forward','dns','confirm','restore','stop'] as $name) $out[$name]=[$this,$name];
        // A confirmed guardian remains alive; it drops only its two leases on
        // its next native tick. A rolled-back guardian exits itself.
        $out['release']=static function(array $job): void {};
        return $out;
    }
}
