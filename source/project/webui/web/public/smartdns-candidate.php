<?php
require_once __DIR__.'/smartdns-install.php';
require_once __DIR__.'/smartdns-store.php';
require_once __DIR__.'/dpi-runtime.php';

/** Foreground engines and DNS helpers, only inside an authenticated guardian. */
final class AsusSmartDnsCandidate
{
    private string $root;
    private int $owner;
    private int $attempt=0;
    public function __construct(private AsusSmartDnsInstaller $installer,private string $id,private array $deps=[])
    {
        if (!preg_match('/^[a-f0-9]{32}$/D',$id)) throw new RuntimeException('invalid_request');
        $this->root=$deps['root']??AsusDpiStore::optPath('/etc/nfqws-asus-web/smartdns');
        $this->owner=$deps['owner']??0;
    }
    private function now(): float { return (float)explode(' ',file_get_contents('/proc/uptime'))[0]; }
    /** Authenticate the fixed native ancestry before a worker edits its journal. */
    public function authenticate(): float { return $this->guarded(); }
    private function proof(string $name,int $fields): array
    {
        $path=$this->root.'/jobs/'.$this->id.'/'.$name;$s=@lstat($path);
        if (!$s || ($s['mode']&0170000)!==0100000 || ($s['mode']&0777)!==0600 || $s['uid']!==$this->owner || $s['nlink']!==1 || $s['size']>512) throw new RuntimeException('guard_unavailable');
        $raw=@file_get_contents($path);
        if (!is_string($raw) || !preg_match('/^[0-9a-f. -]+\n$/D',$raw)) throw new RuntimeException('guard_unavailable');
        $v=explode(' ',trim($raw));
        if (count($v)!==$fields || !preg_match('/^[1-9][0-9]{0,9}$/D',$v[0]) || !preg_match('/^[1-9][0-9]{0,19}$/D',$v[1])) throw new RuntimeException('guard_unavailable');
        $identity=AsusDpiRuntime::identity((int)$v[0]);
        $status=@file_get_contents('/proc/'.$v[0].'/status');
        if ($identity===null || $identity['starttime']!==$v[1] || $identity['boot_id']!==$v[2] || !is_string($status) || !preg_match('/^Uid:\s+'.$this->owner.'\s+'.$this->owner.'\s+'.$this->owner.'\s+'.$this->owner.'\s*$/m',$status)) throw new RuntimeException('guard_unavailable');
        return $v;
    }
    private function guarded(): float
    {
        if (isset($this->deps['guard'])) {
            if (($this->deps['guard'])()!==true) throw new RuntimeException('guard_unavailable');
            return $this->now()+150;
        }
        (new AsusSmartDnsStore($this->root,$this->owner))->directory(false);
        for ($p=$this->root.'/jobs/'.$this->id;$p!==$this->root;$p=dirname($p)) {
            $s=@lstat($p);
            if (!$s || ($s['mode']&0170000)!==0040000 || ($s['mode']&0777)!==0700 || $s['uid']!==$this->owner) throw new RuntimeException('guard_unavailable');
        }
        $guard=$this->proof('guard',4);$anchor=$this->proof('anchor',3);
        // The shell records its direct PHP child immediately after fork.
        $until=$this->now()+1;
        do {
            try { $worker=$this->proof('worker',3);break; }
            catch (Throwable $e) {if ($this->now()>=$until) throw new RuntimeException('guard_unavailable');usleep(10000);}
        } while (true);
        if ((int)$worker[0]!==getmypid() || !is_numeric($guard[3]) || !is_finite((float)$guard[3]) || (float)$guard[3]<=$this->now() || (float)$guard[3]>$this->now()+151) throw new RuntimeException('guard_unavailable');
        $status=file_get_contents('/proc/self/status');
        if (!preg_match('/^PPid:\s+'.$anchor[0].'\s*$/m',$status)) throw new RuntimeException('guard_unavailable');
        $expected=['/bin/sh','/opt/lib/nfqws2-asus/smartdns/config-worker.sh'];
        $a=explode("\0",rtrim((string)@file_get_contents('/proc/'.$anchor[0].'/cmdline'),"\0"));
        $g=explode("\0",rtrim((string)@file_get_contents('/proc/'.$guard[0].'/cmdline'),"\0"));
        if ($a!==array_merge($expected,['session',$this->id,$guard[0],$guard[1]]) || $g!==array_merge($expected,[$this->id])) throw new RuntimeException('guard_unavailable');
        return (float)$guard[3];
    }
    private function probe(): string
    {
        if (isset($this->deps['probe'])) return ($this->deps['probe'])();
        $base='/opt/lib/nfqws2-asus/smartdns';$path=$base.'/tools.json';$s=@lstat($path);
        if (!$s || ($s['mode']&0170000)!==0100000 || $s['uid']!==0 || ($s['mode']&0022)!==0 || $s['nlink']!==1 || $s['size']>4096) throw new RuntimeException('unsupported_binary');
        try { $m=json_decode(file_get_contents($path),true,8,JSON_THROW_ON_ERROR); }
        catch (Throwable $e) {throw new RuntimeException('unsupported_binary');}
        $file=$base.'/dns-probe';$f=@lstat($file);
        if (($m['schema_version']??null)!==1 || !preg_match('/^[a-f0-9]{64}$/D',$m['dns_probe_sha256']??'') || !$f || ($f['mode']&0170000)!==0100000 || $f['uid']!==0 || ($f['mode']&0022)!==0 || $f['nlink']!==1 || !hash_equals($m['dns_probe_sha256'],hash_file('sha256',$file))) throw new RuntimeException('unsupported_binary');
        return $file;
    }
    private function start(array $arguments,string $cwd,int $limit): object
    {
        error_clear_last();
        $p=@proc_open($arguments,[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes,$cwd,['PATH'=>'/usr/bin:/bin','LANG'=>'C']);
        if (!is_resource($p)) {
            $message=error_get_last()['message']??'';
            throw new RuntimeException(str_contains($message,'Cannot allocate memory')?'insufficient_memory':'unsupported_binary');
        }
        foreach ($pipes as $pipe) stream_set_blocking($pipe,false);
        // PHP 8.2 returns a finished child's exit code only on the first
        // status read. A cached local DNS answer can finish before this call.
        $status=proc_get_status($p);
        return (object)['process'=>$p,'pipes'=>$pipes,'out'=>'','err'=>'','limit'=>$limit,'done'=>!$status['running'],'exit'=>$status['running']?null:$status['exitcode'],'pid'=>$status['pid']];
    }
    private function poll(object $p): void
    {
        foreach ([1=>'out',2=>'err'] as $fd=>$field) {
            if (!is_resource($p->pipes[$fd]??null)) continue;
            $raw=stream_get_contents($p->pipes[$fd],min(8192,$p->limit-strlen($p->out)-strlen($p->err)+1));
            if (!is_string($raw)) throw new RuntimeException('invalid_state');
            $p->{$field}.=$raw;
            if (strlen($p->out)+strlen($p->err)>$p->limit) throw new RuntimeException('output_limit');
        }
        if (!$p->done) {
            $s=proc_get_status($p->process);
            if (!$s['running']) {$p->done=true;$p->exit=$s['exitcode'];}
        }
    }
    private function close(object $p): void
    {
        if (!is_resource($p->process)) return;
        if (!$p->done) {
            $s=proc_get_status($p->process);
            if ($s['running']) {
                proc_terminate($p->process,15);$until=$this->now()+0.5;
                do {$s=proc_get_status($p->process);if (!$s['running']) break;usleep(10000);} while ($this->now()<$until);
                if ($s['running']) proc_terminate($p->process,9);
            }
        }
        foreach ($p->pipes as $pipe) if (is_resource($pipe)) fclose($pipe);
        proc_close($p->process);$p->process=null;
    }
    private function checkpoint(object $engine,float $deadline): void
    {
        if ($this->now()>=$deadline) throw new RuntimeException('timed_out');
        $this->poll($engine);
        if ($engine->done) throw new RuntimeException('invalid_configuration');
    }
    private static function inodes(int $pid): array
    {
        $out=[];
        foreach (@scandir('/proc/'.$pid.'/fd')?:[] as $fd) {
            if (!preg_match('/^[0-9]+$/D',$fd)) continue;
            $link=@readlink('/proc/'.$pid.'/fd/'.$fd);
            if (is_string($link) && preg_match('/^socket:\[([0-9]+)\]$/D',$link,$m)) $out[]=$m[1];
        }
        return $out;
    }
    public static function ownsPorts(int $pid,int $port): bool
    {
        $owned=self::inodes($pid);$address='0100007F:'.sprintf('%04X',$port);
        foreach (['udp','tcp'] as $protocol) {
            $found=false;$raw=@file_get_contents('/proc/net/'.$protocol);
            foreach (explode("\n",is_string($raw)?$raw:'') as $line) {
                $v=preg_split('/\s+/',trim($line));
                if (($v[1]??'')===$address && ($protocol!=='tcp' || ($v[3]??'')==='0A') && in_array($v[9]??null,$owned,true)) {$found=true;break;}
            }
            if (!$found) return false;
        }
        return true;
    }
    private function query(object $engine,string $probe,int $port,string $name,string $transport,array $types,float $deadline): array
    {
        $out=[];
        // Old kernels account the PHP address space again at fork, before
        // exec replaces it with the tiny helper. Reap each family first to
        // avoid overlapping these reservations; keep the same total deadline.
        foreach ($types as $type) {
            $this->checkpoint($engine,$deadline);
            $child=$this->start([$probe,'127.0.0.1',(string)$port,$name,$type,$transport,'2500'],'/',8192);
            try {
                do {
                    $this->checkpoint($engine,$deadline);$this->poll($child);
                    if (!$child->done) usleep(10000);
                } while (!$child->done);
                $this->poll($child);
                try {$reply=json_decode($child->out,true,12,JSON_THROW_ON_ERROR);}
                catch (Throwable $e) {throw new RuntimeException('dns_validation_failed');}
                if (!is_array($reply) || ($reply['ok']??null)!==($child->exit===0)) throw new RuntimeException('dns_validation_failed');
                $out[$type]=$reply;
            } finally {$this->close($child);}
        }
        return $out;
    }
    private function freePort(int $port): void
    {
        $sockets=[];
        try {
            foreach (['udp','tcp'] as $protocol) {
                $s=@stream_socket_server($protocol.'://127.0.0.1:'.$port,$errno,$error,STREAM_SERVER_BIND|($protocol==='tcp'?STREAM_SERVER_LISTEN:0));
                if (!is_resource($s)) throw new RuntimeException('port_busy');
                $sockets[]=$s;
            }
        } finally {foreach ($sockets as $s) fclose($s);}
    }
    public function run(array $request): array
    {
        $guardEnd=$this->guarded();
        $keys=array_keys($request);sort($keys);$want=['request_id','profile_hash','stage','server_id','bundle','port','config','names','query_timeout_ms','max_parallel_queries','deadline_uptime'];sort($want);
        if ($keys!==$want || $request['request_id']!==$this->id || !is_string($request['profile_hash']) || !preg_match('/^[a-f0-9]{64}$/D',$request['profile_hash']) || !in_array($request['stage'],['upstream','profile'],true) || !is_int($request['port']) || $request['port']<16053 || $request['port']>16062 || !is_string($request['config']) || strlen($request['config'])>131072 || str_contains($request['config'],"\0") || !is_string($request['bundle']) || strlen($request['bundle'])>4096 || str_contains($request['bundle'],"\0") || !is_array($request['names']) || !array_is_list($request['names']) || !$request['names'] || count($request['names'])>321 || $request['query_timeout_ms']!==2500 || $request['max_parallel_queries']!==2 || !is_numeric($request['deadline_uptime']) || !is_finite((float)$request['deadline_uptime'])) throw new RuntimeException('invalid_request');
        if (($request['stage']==='profile' && $request['server_id']!==null) || ($request['stage']==='upstream' && (!is_string($request['server_id']) || !preg_match('/^[a-z][a-z0-9_-]{0,31}$/D',$request['server_id'])))) throw new RuntimeException('invalid_request');
        try {foreach ($request['names'] as $name) AsusSmartDnsProfile::domain($name,'query');}
        catch (AsusSmartDnsProfileError $e) {throw new RuntimeException('invalid_request');}
        $deadline=min((float)$request['deadline_uptime'],$guardEnd,$this->now()+90);
        if ($deadline<=$this->now()) throw new RuntimeException('timed_out');
        $bundle=isset($this->deps['bundle'])?($this->deps['bundle'])():$this->installer->binaryDirectory();
        if (realpath($request['bundle'])===false || realpath($bundle)!==realpath($request['bundle'])) throw new RuntimeException('invalid_state');
        $probe=$this->probe();$this->freePort($request['port']);
        (new AsusSmartDnsStore($this->root,$this->owner))->directory(true);
        $dir=$this->root;
        foreach (['jobs',$this->id,'attempt-'.(++$this->attempt)] as $part) {
            $dir.='/'.$part;$mask=umask(0077);
            try {if (!is_dir($dir) && !@mkdir($dir,0700)) throw new RuntimeException('insufficient_space');}
            finally {umask($mask);}
            $s=lstat($dir);
            if (($s['mode']&0170000)!==0040000 || ($s['mode']&0777)!==0700 || $s['uid']!==$this->owner) throw new RuntimeException('invalid_state');
        }
        $config=$dir.'/candidate.conf';$pid=$dir.'/candidate.pid';$engine=null;
        try {
            $mask=umask(0077);try {$f=@fopen($config,'xb');} finally {umask($mask);}
            if (!$f) throw new RuntimeException('invalid_state');
            try {if (fwrite($f,$request['config'])!==strlen($request['config']) || !fflush($f)) throw new RuntimeException('insufficient_space');}
            finally {fclose($f);}
            $engine=$this->start(['./smartdns','-f','-c',$config,'-p',$pid],$bundle,65536);
            $startup=min($deadline,$this->now()+5);
            while (!self::ownsPorts($engine->pid,$request['port'])) {
                $this->checkpoint($engine,$deadline);
                if ($this->now()>=$startup) throw new RuntimeException('invalid_configuration');
                usleep(10000);
            }
            $results=[];
            foreach ($request['names'] as $name) {
                $udp=$this->query($engine,$probe,$request['port'],$name,'udp',['A','AAAA'],$deadline);
                $types=array_values(array_filter(['A','AAAA'],fn($type)=>($udp[$type]['truncated']??false)===true));
                $tcp=$types?$this->query($engine,$probe,$request['port'],$name,'tcp',$types,$deadline):[];
                foreach (['A','AAAA'] as $type) $results[]=['name'=>$name,'type'=>$type,'udp'=>$udp[$type],'tcp'=>$tcp[$type]??null];
            }
            return ['started'=>true,'syntax_ok'=>true,'results'=>$results];
        } finally {
            if ($engine!==null) $this->close($engine);
            foreach ([$config,$pid] as $file) if (is_file($file) || is_link($file)) @unlink($file);
            @rmdir($dir);
        }
    }
}
