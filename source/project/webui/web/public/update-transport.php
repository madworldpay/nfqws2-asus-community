<?php
require_once __DIR__.'/dpi-store.php';

/** The origin/token are operator-private configuration, never browser arguments. */
interface AsusUpdateSource
{
    public function manifest(): array;
    public function download(array $package,string $destination): void;
}
require_once __DIR__.'/update-github.php';
final class AsusUpdateTransport implements AsusUpdateSource
{
    private string $origin;
    private string $token;
    private ?AsusUpdateSource $publicSource=null;
    public function __construct(?string $config=null,private int $owner=0,private string $ca='/opt/etc/ssl/certs/ca-certificates.crt',private array $timeouts=['metadata'=>15,'download'=>180])
    {
        $default=$config===null;
        $config=$config??AsusDpiStore::optPath('/etc/nfqws-asus-web').'/update-channel.json';
        if(!file_exists($config)&&!is_link($config)){
            if(!$default)throw new RuntimeException('channel_unconfigured');
            $this->publicSource=new AsusGithubUpdateSource($owner,$ca,$timeouts);return;
        }
        try{
            for($p=$config;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException();
            $s=lstat($config);
            if(!$s||($s['mode']&0170000)!==0100000||($s['mode']&0777)!==0600||$s['uid']!==$owner||$s['nlink']!==1||$s['size']>4096)throw new RuntimeException();
            $f=@fopen($config,'rb');if(!$f)throw new RuntimeException();
            try{$actual=fstat($f);if($s['ino']!==$actual['ino']||$s['dev']!==$actual['dev'])throw new RuntimeException();$raw=stream_get_contents($f,4097);}finally{fclose($f);}
            $v=AsusSupportSchema::decode($raw,4096,'invalid_channel');
            if(!is_object($v))throw new RuntimeException();$keys=array_keys(get_object_vars($v));sort($keys);
            if($keys!==['origin','token']||!is_string($v->origin)||!is_string($v->token)||!preg_match('/^[A-Za-z0-9_-]{43,128}$/D',$v->token))throw new RuntimeException();
            $url=parse_url($v->origin);
            if(strlen($v->origin)>2048||preg_match('/[^\x21-\x7e]/',$v->origin)||!is_array($url)||($url['scheme']??'')!=='https'||empty($url['host'])||!in_array($url['path']??'',['','/'],true))throw new RuntimeException();
            foreach(['user','pass','query','fragment'] as $key)if(isset($url[$key]))throw new RuntimeException();
            $this->origin=rtrim($v->origin,'/');$this->token=$v->token;
        }catch(Throwable $e){throw new RuntimeException('invalid_channel');}
    }

    private function request(string $path,int $cap,float $deadline,?callable $consume=null,array $extra=[]): string
    {
        if(!extension_loaded('openssl')||!is_readable($this->ca))throw new RuntimeException('https_unavailable');
        $remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException('timed_out');
        $headers="Authorization: Bearer ".$this->token."\r\nAccept: application/octet-stream\r\nAccept-Encoding: identity\r\nConnection: close\r\nUser-Agent: NFQWS2-ASUS-Updater/1\r\n";
        foreach($extra as $key=>$value)$headers.=$key.': '.$value."\r\n";
        $context=stream_context_create(['ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false,'cafile'=>$this->ca],
            'http'=>['timeout'=>min(15,$remaining),'follow_location'=>0,'max_redirects'=>0,'ignore_errors'=>true,'protocol_version'=>1.1,'header'=>$headers]]);
        $f=@fopen($this->origin.'/nfqws-updates/v1/'.$path,'rb',false,$context);if(!$f)throw new RuntimeException('download_failed');
        try{
            $status=0;$length=null;$encoding=null;
            foreach(stream_get_meta_data($f)['wrapper_data']??[] as $h){
                if(preg_match('~^HTTP/\S+ ([0-9]{3})\b~',$h,$m)){$status=(int)$m[1];$length=null;$encoding=null;}
                elseif(stripos($h,'Content-Length:')===0){$v=trim(substr($h,15));if($length!==null||!preg_match('/^[0-9]{1,10}$/D',$v)||(float)$v>$cap)throw new RuntimeException('download_size');$length=(int)$v;}
                elseif(stripos($h,'Content-Encoding:')===0){if($encoding!==null)throw new RuntimeException('download_size');$encoding=strtolower(trim(substr($h,17)));}
            }
            if(in_array($status,[301,302,303,307,308],true))throw new RuntimeException('download_redirect');
            if($status===403)throw new RuntimeException('channel_auth_failed');
            if($status===412)throw new RuntimeException('release_changed');
            if($status!==200)throw new RuntimeException('download_failed');
            if($encoding!==null&&$encoding!=='identity')throw new RuntimeException('download_size');
            $count=0;$body='';
            while(!feof($f)){
                $remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException('timed_out');
                $timeout=min(5,$remaining);stream_set_timeout($f,(int)$timeout,(int)(($timeout-(int)$timeout)*1000000));
                $chunk=@fread($f,min(16384,$cap+1-$count));
                if($chunk===false||stream_get_meta_data($f)['timed_out'])throw new RuntimeException('download_failed');
                $count+=strlen($chunk);if($count>$cap)throw new RuntimeException('download_size');
                if($consume!==null)$consume($chunk);else $body.=$chunk;
                if($chunk==='')usleep(1000);
            }
            if($length!==null&&$count!==$length)throw new RuntimeException('download_size');
            return $body;
        }finally{fclose($f);}
    }

    public function manifest(): array
    {
        if($this->publicSource!==null)return $this->publicSource->manifest();
        $deadline=microtime(true)+$this->timeouts['metadata'];
        $json=$this->request('manifest.json',32768,$deadline);
        $signature=$this->request('manifest.sig',1024,$deadline,null,['If-Match'=>'"'.hash('sha256',$json).'"']);
        return ['json'=>$json,'signature'=>$signature];
    }

    public function download(array $package,string $destination): void
    {
        if($this->publicSource!==null){$this->publicSource->download($package,$destination);return;}
        if(!is_string($package['filename']??null)||!preg_match('/^nfqws2-asus_[A-Za-z0-9.+-]{1,80}_(?:aarch64-3\.10|armv7)\.ipk$/D',$package['filename'])||
            !is_int($package['size']??null)||$package['size']<1||$package['size']>33554432||!is_string($package['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$package['sha256']))throw new RuntimeException('invalid_manifest');
        for($p=$destination;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');
        $parent=@lstat(dirname($destination));
        if(!$parent||($parent['mode']&0170000)!==0040000||($parent['mode']&0777)!==0700||$parent['uid']!==$this->owner)throw new RuntimeException('invalid_state');
        $mask=umask(0077);try{$out=@fopen($destination,'xb');}finally{umask($mask);}
        if(!$out)throw new RuntimeException('invalid_state');$created=fstat($out);$success=false;
        try{
            if(!chmod($destination,0600))throw new RuntimeException('invalid_state');
            $hash=hash_init('sha256');$count=0;
            $this->request('packages/'.$package['filename'],$package['size'],microtime(true)+$this->timeouts['download'],function($chunk)use($out,$hash,&$count){
                $count+=strlen($chunk);hash_update($hash,$chunk);if(fwrite($out,$chunk)!==strlen($chunk))throw new RuntimeException('insufficient_space');
            });
            if($count!==$package['size'])throw new RuntimeException('download_size');
            if(!hash_equals($package['sha256'],hash_final($hash)))throw new RuntimeException('download_hash');
            if(!fflush($out))throw new RuntimeException('insufficient_space');$success=true;
        }finally{
            fclose($out);
            if(!$success){clearstatcache(true,$destination);$s=@lstat($destination);if($s&&$s['ino']===$created['ino']&&$s['dev']===$created['dev']&&($s['mode']&0170000)===0100000)@unlink($destination);}
        }
    }
}
