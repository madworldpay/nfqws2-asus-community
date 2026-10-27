<?php
require_once __DIR__.'/profile-catalog.php';
require_once __DIR__.'/import-document.php';
/** No origin, URL, redirect target, or local path comes from an HTTP request. */
final class AsusProfileCatalogTransport
{
    private const ORIGIN='https://mad13mansprofy13.asuscomm.com:5443/nfqws-profiles/v1/';
    private const TTL=600;
    private string $key;
    private string $cache;
    private mixed $read;
    private mixed $clock;
    private int $build;
    public function __construct(?string $publicKey=null,?callable $read=null,?string $cache=null,private int $owner=0,?callable $clock=null,?int $build=null,private string $ca='/opt/etc/ssl/certs/ca-certificates.crt')
    {
        $this->ca=NfqwsPlatform::translate($this->ca);
        $keyFile=NfqwsPlatform::sharedFile('profile-catalog-public.pem',dirname(__DIR__,3).'/asus/profile-catalog-public.pem');
        $this->key=$publicKey??(string)@file_get_contents($keyFile,false,null,0,2049);
        $this->cache=$cache??'/tmp/nfqws2-asus-profile-catalog';$this->read=$read??fn($url,$cap,$deadline)=>self::https($url,$cap,$deadline,$this->ca);$this->clock=$clock??time(...);
        $this->build=$build??self::installedBuild();
    }
    private static function installedBuild(): int
    {
        $path=NfqwsPlatform::sharedFile('report-baseline.json',dirname(__DIR__,3).'/report-baseline.json');
        if(is_file($path)) {
            $v=json_decode((string)@file_get_contents($path,false,null,0,131073),true);
            if(NfqwsPlatform::native()&&is_int($v['build_number']??null)&&$v['build_number']>0&&$v['build_number']<1000000000)return $v['build_number'];
            if(preg_match('/\+b([1-9][0-9]{0,8})$/D',$v['package_version']??'',$m))return (int)$m[1];
        }
        $raw=trim((string)@file_get_contents(dirname(__DIR__,3).'/BUILD_NUMBER'));
        return preg_match('/^[1-9][0-9]{0,8}$/D',$raw)?(int)$raw:0;
    }
    public function build(): int {return $this->build;}
    private static function https(string $url,int $cap,float $deadline,string $ca): string
    {
        $remaining=$deadline-microtime(true);
        if($remaining<=0)throw new RuntimeException('catalog_timeout');
        if(!extension_loaded('openssl')||!is_readable($ca))throw new RuntimeException('catalog_unavailable');
        $context=stream_context_create(['ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false,'cafile'=>$ca],
            'http'=>['timeout'=>$remaining,'follow_location'=>0,'max_redirects'=>0,'ignore_errors'=>true,'protocol_version'=>1.1,
            'header'=>"Accept: application/json\r\nAccept-Encoding: identity\r\nConnection: close\r\nUser-Agent: NFQWS2-ASUS-Catalog/1\r\n"]]);
        // The resolver is system-owned. This timeout bounds connect/TLS/reads;
        // never accept a response after the total deadline, including DNS time.
        $f=@fopen($url,'rb',false,$context);
        if(!$f)throw new RuntimeException(microtime(true)>=$deadline?'catalog_timeout':'catalog_unavailable');
        try {
            $status=0;$length=null;$encoding=null;
            foreach(stream_get_meta_data($f)['wrapper_data']??[] as $h) {
                if(preg_match('~^HTTP/\S+ ([0-9]{3})\b~',$h,$m)){$status=(int)$m[1];$length=null;$encoding=null;}
                elseif(stripos($h,'Content-Length:')===0){$v=trim(substr($h,15));if($length!==null||!preg_match('/^[0-9]{1,10}$/D',$v)||(float)$v>$cap)throw new RuntimeException('catalog_limit');$length=(int)$v;}
                elseif(stripos($h,'Content-Encoding:')===0){if($encoding!==null)throw new RuntimeException('catalog_limit');$encoding=strtolower(trim(substr($h,17)));}
            }
            if($status!==200)throw new RuntimeException('catalog_unavailable');
            if($encoding!==null&&$encoding!=='identity')throw new RuntimeException('catalog_limit');
            $raw='';
            while(!feof($f)) {
                $remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException('catalog_timeout');
                stream_set_timeout($f,(int)$remaining,(int)(($remaining-(int)$remaining)*1000000));
                $chunk=@fread($f,min(16384,$cap+1-strlen($raw)));
                if($chunk===false||stream_get_meta_data($f)['timed_out'])throw new RuntimeException('catalog_timeout');
                $raw.=$chunk;if(strlen($raw)>$cap)throw new RuntimeException('catalog_limit');
                if($chunk==='')usleep(1000);
            }
            if(microtime(true)>$deadline)throw new RuntimeException('catalog_timeout');
            if($length!==null&&strlen($raw)!==$length)throw new RuntimeException('catalog_invalid');
            return $raw;
        }finally{fclose($f);}
    }
    private function fetch(string $path,int $cap,float $deadline): string
    {
        if(microtime(true)>=$deadline)throw new RuntimeException('catalog_timeout');
        $raw=($this->read)(self::ORIGIN.$path,$cap,$deadline);
        if(microtime(true)>$deadline)throw new RuntimeException('catalog_timeout');
        if(!is_string($raw)||strlen($raw)>$cap)throw new RuntimeException('catalog_limit');return $raw;
    }
    private function directory(): void
    {
        for($p=$this->cache;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException('catalog_unavailable');
        if(!is_dir($this->cache)&&!@mkdir($this->cache,0700)&&!is_dir($this->cache))throw new RuntimeException('catalog_unavailable');
        clearstatcache(true,$this->cache);$s=@lstat($this->cache);
        if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('catalog_unavailable');
    }
    private function cached(): ?array
    {
        $this->directory();$path=$this->cache.'/catalog.json';clearstatcache(true,$path);$s=@lstat($path);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>131072)throw new RuntimeException('catalog_unavailable');
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('catalog_unavailable');
        try{$actual=fstat($f);if($actual['ino']!==$s['ino']||$actual['dev']!==$s['dev'])throw new RuntimeException('catalog_unavailable');$raw=stream_get_contents($f,131073);}finally{fclose($f);}
        if(!is_string($raw)||strlen($raw)>131072)throw new RuntimeException('catalog_invalid');
        try{$index=AsusProfileCatalog::verify($raw,$this->key);}
        catch(RuntimeException $e){if(in_array($e->getMessage(),['catalog_invalid','catalog_signature'],true))return null;throw $e;}
        return ['index'=>$index,'mtime'=>$s['mtime']];
    }
    private function save(string $raw,int $now): void
    {
        $this->directory();$tmp=$this->cache.'/.write-'.bin2hex(random_bytes(12));$mask=umask(0077);
        try{$f=@fopen($tmp,'xb');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('catalog_unavailable');
        try {
            if(!chmod($tmp,0600)||fwrite($f,$raw)!==strlen($raw)||!fflush($f)||!touch($tmp,$now))throw new RuntimeException('catalog_unavailable');
            fclose($f);$f=null;if(!@rename($tmp,$this->cache.'/catalog.json'))throw new RuntimeException('catalog_unavailable');
        }finally{if(is_resource($f))fclose($f);@unlink($tmp);}
    }
    private function index(float $deadline): array
    {
        $now=($this->clock)();$old=$this->cached();
        if($old!==null&&$old['mtime']<=$now&&$now-$old['mtime']<self::TTL)return $old['index'];
        $raw=$this->fetch('catalog.json',AsusProfileCatalog::ENVELOPE_LIMIT,$deadline);$index=AsusProfileCatalog::verify($raw,$this->key);
        if($old!==null&&$index['revision']<$old['index']['revision'])throw new RuntimeException('catalog_changed');
        $this->save($raw,$now);return $index;
    }
    public function catalog(): array {return $this->index(microtime(true)+20);}
    public function document(string $id,string $sha256): string
    {
        if(!preg_match('/^[a-z0-9][a-z0-9-]{0,63}$/D',$id)||!preg_match('/^[a-f0-9]{64}$/D',$sha256))throw new RuntimeException('invalid_request');
        $deadline=microtime(true)+20;$index=$this->index($deadline);$selected=null;
        foreach($index['profiles'] as $entry)if($entry['id']===$id&&hash_equals($entry['sha256'],$sha256))$selected=$entry;
        if($selected===null)throw new RuntimeException('catalog_changed');
        if($selected['min_build']>$this->build)throw new RuntimeException('catalog_version');
        $raw=$this->fetch('files/'.$sha256.'.json',$selected['size'],$deadline);
        if(strlen($raw)!==$selected['size']||!hash_equals($sha256,hash('sha256',$raw)))throw new RuntimeException('catalog_invalid');
        AsusImportDocument::read([$raw]);return $raw;
    }
}
