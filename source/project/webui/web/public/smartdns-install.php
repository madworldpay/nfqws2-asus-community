<?php
require_once __DIR__.'/dpi-install.php';

/** Extract only fixed regular engine files. Package scripts and archive links never run. */
final class AsusSmartDnsArchive
{
    private static function read($stream,int $size): string
    {
        $out='';while(strlen($out)<$size){$s=@gzread($stream,min(16384,$size-strlen($out)));if(!is_string($s)||$s==='')throw new RuntimeException('invalid_package');$out.=$s;}return $out;
    }
    private static function walk(string $path,callable $consume): void
    {
        $f=@gzopen($path,'rb');if(!$f)throw new RuntimeException('invalid_package');$total=0;
        try{for($n=0;$n<2048;$n++){
            $h=self::read($f,512);if($h===str_repeat("\0",512))return;
            $size=trim(substr($h,124,12)," \0");$sum=trim(substr($h,148,8)," \0");
            if(!preg_match('/^[0-7]{1,11}$/D',$size)||!preg_match('/^[0-7]{1,7}$/D',$sum)||array_sum(unpack('C*',substr_replace($h,str_repeat(' ',8),148,8)))!==octdec($sum))throw new RuntimeException('invalid_package');
            $size=(int)octdec($size);$total+=$size;if($total>33554432)throw new RuntimeException('invalid_package');
            $name=rtrim(substr($h,0,100),"\0");$prefix=rtrim(substr($h,345,155),"\0");if($prefix!=='')$name=$prefix.'/'.$name;
            if(str_starts_with($name,'./'))$name=substr($name,2);
            $out=$consume($name,$size,$h[156]);
            try{for($left=$size;$left>0;){$chunk=self::read($f,min(16384,$left));if(is_resource($out)&&fwrite($out,$chunk)!==strlen($chunk))throw new RuntimeException('insufficient_space');$left-=strlen($chunk);}}
            finally{if(is_resource($out))fclose($out);}
            if($size%512)self::read($f,512-$size%512);
        }throw new RuntimeException('invalid_package');}finally{gzclose($f);}
    }
    public static function extract(string $ipk,string $stage,array $artifact): void
    {
        $data=$stage.'/data.tar.gz';$found=false;
        self::walk($ipk,function($name,$size,$type)use($data,&$found){
            if($name!=='data.tar.gz')return null;
            if($found||!in_array($type,["\0",'0'],true)||$size>16777216)throw new RuntimeException('invalid_package');$found=true;
            $f=@fopen($data,'xb');if(!$f)throw new RuntimeException('invalid_state');chmod($data,0600);return $f;
        });
        if(!$found)throw new RuntimeException('invalid_package');$seen=[];$prefix='opt/usr/local/lib/smartdns/';
        self::walk($data,function($name,$size,$type)use($stage,$artifact,$prefix,&$seen){
            if(!str_starts_with($name,$prefix))return null;$name=substr($name,strlen($prefix));
            if(!isset($artifact['files'][$name]))return null;$want=$artifact['files'][$name];
            if(isset($seen[$name])||!in_array($type,["\0",'0'],true)||$size!==$want['size'])throw new RuntimeException('invalid_package');
            $seen[$name]=true;$f=@fopen($stage.'/'.$name,'xb');if(!$f)throw new RuntimeException('invalid_state');chmod($stage.'/'.$name,0700);return $f;
        });
        if(count($seen)!==count($artifact['files']))throw new RuntimeException('invalid_package');unlink($data);
        foreach($artifact['files'] as $name=>$want)if(!hash_equals($want['sha256'],hash_file('sha256',$stage.'/'.$name)))throw new RuntimeException('download_hash');
        foreach($artifact['links'] as $name=>$target)if(!symlink($target,$stage.'/'.$name))throw new RuntimeException('invalid_state');
    }
}

/** Private, optional runtime only. Does not stop, configure or replace any resolver. */
final class AsusSmartDnsInstaller
{
    private string $root;
    public function __construct(?string $root=null,private int $owner=0,private ?array $artifact=null,private mixed $fetcher=null,private mixed $prober=null)
    {$this->root=$root??AsusDpiStore::optPath('/lib/nfqws2-asus/smartdns-engine');}
    public static function code(string $code): string
    {return in_array($code,['ready','busy','invalid_request','consent_required','invalid_state','invalid_package','unsupported_runtime','unsupported_abi','unsupported_binary','not_installed','invalid_clock','insufficient_memory','insufficient_space','https_unavailable','download_failed','download_hash','download_size','download_redirect','untrusted_download','timed_out','launch_failed','interrupted'],true)?$code:'failed';}
    public static function catalog(): array
    {
        $path='/opt/share/nfqws2-asus/smartdns-catalog.json';if(!is_file($path))$path=dirname(__DIR__,3).'/support/smartdns-catalog.json';
        return json_decode(file_get_contents($path),true,32,JSON_THROW_ON_ERROR);
    }
    public function artifact(): array
    {
        if($this->artifact!==null)return $this->artifact;
        $p=@proc_open([AsusDpiRuntime::BUSYBOX,'sh','-c','. /opt/lib/nfqws2-asus/abi.sh; asus_entware_primary_abi'],[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C']);
        if(!is_resource($p))throw new RuntimeException('unsupported_abi');$abi=trim(stream_get_contents($pipes[1],64));fclose($pipes[1]);$exit=proc_close($p);
        if($exit!==0||!in_array($abi,['armv7-2.6','armv7-3.2','aarch64-3.10'],true))throw new RuntimeException('unsupported_abi');
        // The vendor's ARM-on-AArch64 wrapper changes a kernel setting. Never do that here.
        if(str_starts_with($abi,'armv7')&&php_uname('m')==='aarch64')throw new RuntimeException('unsupported_runtime');
        return self::catalog()['artifacts'][$abi==='aarch64-3.10'?'aarch64':'arm'];
    }
    public function directory(): string
    {
        for($p=$this->root;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');
        if(!file_exists($this->root)&&!mkdir($this->root,0700))throw new RuntimeException('invalid_state');
        $s=lstat($this->root);if(($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');return $this->root;
    }
    private static function regular(string $path,int $owner): array
    {
        $s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0022)!==0)throw new RuntimeException('invalid_state');return $s;
    }
    private function verifiedBundle(string $dir,array $a): bool
    {
        $s=@lstat($dir);if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $lib=@lstat($dir.'/lib');if(!$lib||($lib['mode']&0170000)!==0040000||$lib['uid']!==$this->owner||($lib['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        foreach($a['files'] as $name=>$want){$s=self::regular($dir.'/'.$name,$this->owner);if($s['size']!==$want['size']||!hash_equals($want['sha256'],hash_file('sha256',$dir.'/'.$name)))return false;}
        foreach($a['links'] as $name=>$target)if(!is_link($dir.'/'.$name)||readlink($dir.'/'.$name)!==$target)return false;return true;
    }
    private function activate(string $id,array $a): void
    {
        $next=$this->root.'/.current-'.$id;if(file_exists($next)||is_link($next))throw new RuntimeException('invalid_state');
        try{if(!symlink($a['sha256'],$next)||!rename($next,$this->root.'/current'))throw new RuntimeException('invalid_state');}
        finally{if(is_link($next))unlink($next);}
    }
    public function installed(): array
    {
        $no=['installed'=>false,'version'=>null];if(!file_exists($this->root)&&!is_link($this->root))return $no;
        $this->directory();$a=$this->artifact();$current=$this->root.'/current';
        if(!is_link($current)){if(file_exists($current))throw new RuntimeException('invalid_state');return $no;}
        if(readlink($current)!==$a['sha256'])return $no;$dir=$this->root.'/'.$a['sha256'];
        if(!$this->verifiedBundle($dir,$a))return $no;
        return ['installed'=>true,'version'=>$a['version']];
    }
    public function binaryDirectory(): string
    {if(!$this->installed()['installed'])throw new RuntimeException('not_installed');return $this->root.'/'.$this->artifact()['sha256'];}
    public function availability(): array
    {
        try{$this->artifact();if(!function_exists('gzopen')||!function_exists('proc_open'))throw new RuntimeException('unsupported_runtime');
            if(time()<1704067200)throw new RuntimeException('invalid_clock');
            if(!extension_loaded('openssl')||!is_readable('/opt/etc/ssl/certs/ca-certificates.crt'))throw new RuntimeException('https_unavailable');
            if(AsusDpiInstaller::availableMemoryKiB(file_get_contents('/proc/meminfo'))<65536)throw new RuntimeException('insufficient_memory');
            if((float)@disk_free_space('/opt')<50331648)throw new RuntimeException('insufficient_space');return ['available'=>true,'code'=>'ready'];
        }catch(Throwable $e){return ['available'=>false,'code'=>self::code($e->getMessage())];}
    }
    private static function removeStage(string $path): void
    {
        if(!is_dir($path)||is_link($path))return;
        foreach(scandir($path) as $name)if($name!=='.'&&$name!=='..'){$p=$path.'/'.$name;if(is_dir($p)&&!is_link($p))self::removeStage($p);else @unlink($p);}@rmdir($path);
    }
    public function cleanupStages(?string $active=null): void
    {
        $root=$this->directory();foreach(scandir($root) as $name){
            if(!preg_match('/^\.stage-([a-f0-9]{32})$/D',$name,$m)||$m[1]===$active)continue;
            $path=$root.'/'.$name;$s=lstat($path);if(($s['mode']&0170000)===0040000&&$s['uid']===$this->owner&&($s['mode']&0777)===0700)self::removeStage($path);
        }
    }
    private function probe(string $stage): array
    {
        if($this->prober!==null)return ($this->prober)(['./smartdns','-v'],$stage,5);
        $p=@proc_open(['./smartdns','-v'],[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['file','/dev/null','a']],$pipes,$stage,['PATH'=>'/usr/bin:/bin','LANG'=>'C']);
        if(!is_resource($p))throw new RuntimeException('unsupported_binary');stream_set_blocking($pipes[1],false);$text='';$end=microtime(true)+5;$exit=-1;
        try{do{$text.=stream_get_contents($pipes[1],1025-strlen($text));$s=proc_get_status($p);if(!$s['running']){$exit=$s['exitcode'];break;}
            if(strlen($text)>1024||microtime(true)>=$end){proc_terminate($p,9);throw new RuntimeException('unsupported_binary');}usleep(20000);
        }while(true);$text.=stream_get_contents($pipes[1],1025-strlen($text));}finally{fclose($pipes[1]);proc_close($p);}return ['exit'=>$exit,'stdout'=>$text];
    }
    public function install(string $id): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');$this->directory();$this->cleanupStages($id);
        if($this->installed()['installed'])return $this->installed();
        $a=$this->artifact();$target=$this->root.'/'.$a['sha256'];
        if(file_exists($target)||is_link($target)){
            if(!$this->verifiedBundle($target,$a))throw new RuntimeException('invalid_state');$r=$this->probe($target);
            if(($r['exit']??-1)!==0||trim($r['stdout']??'')!==$a['version_output'])throw new RuntimeException('unsupported_binary');
            $this->activate($id,$a);return $this->installed();
        }
        if($this->artifact===null){$cap=$this->availability();if(!$cap['available'])throw new RuntimeException($cap['code']);}
        $stage=$this->root.'/.stage-'.$id;$next=$this->root.'/.current-'.$id;
        if(file_exists($stage)||is_link($stage)||file_exists($next)||is_link($next))throw new RuntimeException('invalid_state');
        if(!mkdir($stage,0700)||!mkdir($stage.'/lib',0700))throw new RuntimeException('invalid_state');
        try{$ipk=$stage.'/download.ipk';$deadline=microtime(true)+115;
            if($this->fetcher!==null)($this->fetcher)($a,$ipk,$deadline);else (new AsusDpiDownload(maxBytes:16777216))->fetch($a,$ipk,$deadline);
            $s=self::regular($ipk,$this->owner);if($s['size']!==$a['size'])throw new RuntimeException('download_size');if(!hash_equals($a['sha256'],hash_file('sha256',$ipk)))throw new RuntimeException('download_hash');
            AsusSmartDnsArchive::extract($ipk,$stage,$a);unlink($ipk);
            $h=file_get_contents($stage.'/smartdns',false,null,0,64);
            if(strlen($h)<20||substr($h,0,4)!=="\x7fELF"||ord($h[4])!==$a['elf_class']||ord($h[5])!==1||unpack('v',substr($h,18,2))[1]!==$a['elf_machine'])throw new RuntimeException('unsupported_binary');
            $r=$this->probe($stage);if(($r['exit']??-1)!==0||trim($r['stdout']??'')!==$a['version_output'])throw new RuntimeException('unsupported_binary');
            if(file_exists($target)||is_link($target))throw new RuntimeException('invalid_state');
            if(!rename($stage,$target))throw new RuntimeException('invalid_state');$this->activate($id,$a);
            return $this->installed();
        }finally{self::removeStage($stage);if(is_link($next))unlink($next);}
    }
}
