<?php
require_once __DIR__.'/dpi-catalog.php';
require_once __DIR__.'/dpi-runtime.php';
/** Fixed HTTPS transport. Constructor overrides are trusted test dependencies, never HTTP input. */
final class AsusDpiDownload
{
    public function __construct(private string $ca='/opt/etc/ssl/certs/ca-certificates.crt',private array $hosts=['github.com','release-assets.githubusercontent.com'],private int $port=443,private int $maxBytes=8388608) {}
    private function trusted(string $url): void
    {
        $p=parse_url($url);
        if(strlen($url)>4096||preg_match('/[^\x21-\x7e]/',$url)||!is_array($p)||($p['scheme']??'')!=='https'||
            !in_array($p['host']??'',$this->hosts,true)||($p['port']??443)!==$this->port)throw new RuntimeException('untrusted_download');
        foreach(['user','pass','fragment'] as $k)if(isset($p[$k]))throw new RuntimeException('untrusted_download');
    }
    public function fetch(array $artifact,string $dest,float $deadline): void
    {
        if(!extension_loaded('openssl')||!is_readable($this->ca))throw new RuntimeException('https_unavailable');
        $expected=$artifact['size'];if(!is_int($expected)||$expected<1||$expected>$this->maxBytes)throw new RuntimeException('download_size');
        $url=$artifact['url'];$f=null;$out=null;
        try {
            for($redirects=0;;$redirects++) {
                $this->trusted($url);$remaining=$deadline-microtime(true);
                if($remaining<=0)throw new RuntimeException('timed_out');
                $context=stream_context_create(['ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false,'cafile'=>$this->ca],
                    'http'=>['timeout'=>min(15,$remaining),'follow_location'=>0,'max_redirects'=>0,'ignore_errors'=>true,'protocol_version'=>1.1,
                        'header'=>"Accept: application/octet-stream\r\nAccept-Encoding: identity\r\nConnection: close\r\nUser-Agent: NFQWS2-ASUS-DPI/1\r\n"]]);
                $f=@fopen($url,'rb',false,$context);if(!$f)throw new RuntimeException('download_failed');
                $headers=stream_get_meta_data($f)['wrapper_data']??[];$status=0;$location=null;$length=null;$encoding=null;
                foreach($headers as $h) {
                    if(preg_match('~^HTTP/\S+ ([0-9]{3})\b~',$h,$m)){$status=(int)$m[1];$location=null;$length=null;$encoding=null;}
                    elseif(stripos($h,'Location:')===0){if($location!==null)throw new RuntimeException('download_redirect');$location=trim(substr($h,9));}
                    elseif(stripos($h,'Content-Length:')===0){$v=trim(substr($h,15));if($length!==null||!preg_match('/^[0-9]+$/D',$v)||strlen($v)>8)throw new RuntimeException('download_size');$length=(int)$v;}
                    elseif(stripos($h,'Content-Encoding:')===0)$encoding=trim(substr($h,17));
                }
                if(in_array($status,[301,302,303,307,308],true)) {
                    fclose($f);$f=null;if($redirects>=3||!is_string($location))throw new RuntimeException('download_redirect');
                    $this->trusted($location);$url=$location;continue;
                }
                if($status!==200)throw new RuntimeException('download_failed');
                if(($length!==null&&$length!==$expected)||($encoding!==null&&strtolower($encoding)!=='identity'))throw new RuntimeException('download_size');
                break;
            }
            $out=@fopen($dest,'xb');if(!$out)throw new RuntimeException('invalid_state');chmod($dest,0600);
            $hash=hash_init('sha256');$count=0;
            while(!feof($f)) {
                $remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException('timed_out');
                $timeout=min(5,$remaining);stream_set_timeout($f,(int)$timeout,(int)(($timeout-(int)$timeout)*1000000));
                $data=@fread($f,min(16384,$expected+1-$count));
                if($data===false||stream_get_meta_data($f)['timed_out'])throw new RuntimeException('download_failed');
                $count+=strlen($data);if($count>$expected)throw new RuntimeException('download_size');
                hash_update($hash,$data);if(fwrite($out,$data)!==strlen($data))throw new RuntimeException('insufficient_space');
            }
            if($count!==$expected)throw new RuntimeException('download_size');
            if(!hash_equals($artifact['sha256'],hash_final($hash)))throw new RuntimeException('download_hash');
            if(!fflush($out))throw new RuntimeException('insufficient_space');
        } catch(Throwable $e) {if(is_resource($out))fclose($out);$out=null;if(is_file($dest)&&!is_link($dest))@unlink($dest);throw $e;}
        finally {if(is_resource($f))fclose($f);if(is_resource($out))fclose($out);}
    }
}
final class AsusDpiInstaller
{
    private string $root;
    public function __construct(?string $root=null,private int $owner=0,private ?array $artifact=null,private mixed $fetcher=null,private mixed $prober=null,private ?string $legacyBundle=null)
    {$this->root=$root??AsusDpiStore::optPath('/lib/nfqws2-asus/dpi-detector');}
    private function primaryArtifact(): array
    {
        if($this->artifact!==null)return $this->artifact;
        $p=@proc_open([AsusDpiRuntime::BUSYBOX,'sh','-c','. /opt/lib/nfqws2-asus/abi.sh; asus_entware_primary_abi'],[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/usr/bin:/bin:/opt/bin','LANG'=>'C']);
        if(!is_resource($p))throw new RuntimeException('unsupported_abi');$abi=stream_get_contents($pipes[1],64);fclose($pipes[1]);$exit=proc_close($p);
        if($exit!==0)throw new RuntimeException('unsupported_abi');return AsusDpiCatalog::artifact(trim($abi));
    }
    private function directory(bool $create): bool
    {
        for($p=$this->root;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');
        if(!is_dir($this->root)){if(!$create)return false;if(!mkdir($this->root,0711)||!chmod($this->root,0711))throw new RuntimeException('invalid_state');}
        clearstatcache();$s=lstat($this->root);
        if(($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0711)throw new RuntimeException('invalid_state');return true;
    }
    public static function availableMemoryKiB(string $raw): int
    {
        // MemFree alone deliberately underestimates availability on old kernels;
        // reclaimable cache is not counted without trustworthy kernel estimates.
        foreach(['MemAvailable','MemFree'] as $key){
            $count=preg_match_all('/^'.$key.':/m',$raw);if($count===0)continue;if($count!==1)return 0;
            if(preg_match_all('/^'.$key.':\s+([0-9]{1,10}) kB\s*$/m',$raw,$m)!==1)return 0;
            $value=(float)$m[1][0];return $value<=2147483647?(int)$value:0;
        }
        return 0;
    }
    public function cleanupStages(?string $activeJob=null): void
    {
        if(!$this->directory(false))return;
        foreach(scandir($this->root) as $name){
            if(!preg_match('/^\.(?:stage|active)-([a-f0-9]{24}|[a-f0-9]{32})$/D',$name,$m)||$m[1]===$activeJob)continue;
            $path=$this->root.'/'.$name;$s=lstat($path);
            if($s&&($s['mode']&0170000)===0100000&&$s['uid']===$this->owner&&$s['nlink']===1&&$s['size']<=8388608)@unlink($path);
        }
    }
    public function availability(): array
    {
        try {
            $this->primaryArtifact();$cap=(new AsusDpiRuntime())->capabilities();if(!$cap['available'])return $cap;
            if(time()<1704067200)return ['available'=>false,'code'=>'invalid_clock'];
            if(!extension_loaded('openssl')||!is_readable('/opt/etc/ssl/certs/ca-certificates.crt'))return ['available'=>false,'code'=>'https_unavailable'];
            if(self::availableMemoryKiB(file_get_contents('/proc/meminfo'))<65536)return ['available'=>false,'code'=>'insufficient_memory'];
            if((float)@disk_free_space('/opt')<12582912)return ['available'=>false,'code'=>'insufficient_space'];
            return ['available'=>true,'code'=>'ready'];
        }catch(Throwable $e){return ['available'=>false,'code'=>in_array($e->getMessage(),['unsupported_abi','invalid_state'],true)?$e->getMessage():'unsupported_runtime'];}
    }
    private function installedArtifact(): ?array
    {
        if(!$this->directory(false))return null;
        $path=$this->root.'/active.json';if(is_link($path))throw new RuntimeException('invalid_state');$s=@lstat($path);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>2048)throw new RuntimeException('invalid_state');
        $meta=json_decode(file_get_contents($path),true,8,JSON_THROW_ON_ERROR);$a=$this->primaryArtifact();
        // A new preferred binary does not revoke a previously accepted release.
        // Only hashes pinned for this ABI are eligible; state cannot add trust.
        $selected=null;
        foreach(array_merge([$a],$a['accepted_installed']??[]) as $candidate)
            if($meta===['version'=>AsusDpiCatalog::load()['version'],'sha256'=>$candidate['sha256']]){$selected=$candidate;break;}
        if($selected===null)return null;$a=$selected;
        $binary=$this->root.'/'.$a['sha256'];$b=@lstat($binary);
        if(!$b||($b['mode']&0170000)!==0100000||$b['uid']!==$this->owner||($b['mode']&0777)!==0755||$b['nlink']!==1||$b['size']!==$a['size']||!hash_equals($a['sha256'],hash_file('sha256',$binary)))return null;
        return $a;
    }
    public function installed(): array
    {return $this->installedArtifact()===null?['installed'=>false,'version'=>null]:['installed'=>true,'version'=>AsusDpiCatalog::load()['version']];}
    public function binary(): string
    {$a=$this->installedArtifact();if($a===null)throw new RuntimeException('not_installed');return $this->root.'/'.$a['sha256'];}
    private function copyLegacyBundle(array $artifact,string $dest): void
    {
        if(($artifact['name']??null)!=='dpi-detector-armv5te')throw new RuntimeException('invalid_state');
        $source=$this->legacyBundle??AsusDpiStore::optPath('/libexec/nfqws2-asus/optional/dpi-detector-armv5te');
        for($p=$source;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');
        $s=@lstat($source);
        if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||($s['mode']&0022)!==0)throw new RuntimeException('invalid_state');
        if($s['size']!==$artifact['size']||$s['size']>8388608)throw new RuntimeException('download_size');
        $in=@fopen($source,'rb');if(!$in)throw new RuntimeException('invalid_state');$out=null;
        try{$opened=fstat($in);if($opened['ino']!==$s['ino']||$opened['dev']!==$s['dev'])throw new RuntimeException('invalid_state');
            $out=@fopen($dest,'xb');if(!$out)throw new RuntimeException('invalid_state');chmod($dest,0600);
            if(stream_copy_to_stream($in,$out,$artifact['size']+1)!==$artifact['size']||!fflush($out))throw new RuntimeException('download_size');
        }finally{fclose($in);if(is_resource($out))fclose($out);}
    }
    public function install(string $jobId): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$jobId))throw new RuntimeException('invalid_request');
        $this->directory(true);$this->cleanupStages($jobId);if($this->installed()['installed'])return $this->installed();
        if($this->artifact===null){$a=$this->availability();if(!$a['available'])throw new RuntimeException($a['code']);}
        $artifact=$this->primaryArtifact();$stage=$this->root.'/.stage-'.$jobId;$metadata=$this->root.'/.active-'.$jobId;
        try {
            if(($artifact['source']??null)==='bundled-legacy')$this->copyLegacyBundle($artifact,$stage);
            elseif($this->fetcher!==null)($this->fetcher)($artifact,$stage,microtime(true)+115);else (new AsusDpiDownload())->fetch($artifact,$stage,microtime(true)+115);
            $s=@lstat($stage);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||$s['size']!==$artifact['size'])throw new RuntimeException('download_size');
            if(!hash_equals($artifact['sha256'],hash_file('sha256',$stage)))throw new RuntimeException('download_hash');
            $f=fopen($stage,'rb');$elf=fread($f,64);fclose($f);
            if(strlen($elf)<20||substr($elf,0,4)!=="\x7fELF"||ord($elf[4])!==$artifact['elf_class']||ord($elf[5])!==1||unpack('v',substr($elf,18,2))[1]!==$artifact['elf_machine'])throw new RuntimeException('unsupported_binary');
            chmod($stage,0755);
            $r=$this->prober!==null?($this->prober)($jobId,[$stage,'--version'],'/',5):(new AsusDpiRuntime())->probe($jobId,[$stage,'--version'],'/',5);
            if(($r['exit']??-1)!==0||trim($r['stdout']??'')!=='dpi-detector 5.0.0-alpha.21')throw new RuntimeException('unsupported_binary');
            $target=$this->root.'/'.$artifact['sha256'];if(is_link($target))throw new RuntimeException('invalid_state');
            if(file_exists($target)) {if(!is_file($target)||hash_file('sha256',$target)!==$artifact['sha256'])throw new RuntimeException('invalid_state');unlink($stage);}
            elseif(!rename($stage,$target))throw new RuntimeException('invalid_state');
            $f=fopen($metadata,'xb');if(!$f)throw new RuntimeException('invalid_state');chmod($metadata,0600);
            $raw=json_encode(['version'=>AsusDpiCatalog::load()['version'],'sha256'=>$artifact['sha256']]);
            try{if(fwrite($f,$raw)!==strlen($raw)||!fflush($f))throw new RuntimeException('insufficient_space');}finally{fclose($f);}
            if(is_link($this->root.'/active.json')||!rename($metadata,$this->root.'/active.json'))throw new RuntimeException('invalid_state');
            return $this->installed();
        } finally {if(is_file($stage)&&!is_link($stage))@unlink($stage);if(is_file($metadata)&&!is_link($metadata))@unlink($metadata);}
    }
}
