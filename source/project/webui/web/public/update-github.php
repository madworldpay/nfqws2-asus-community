<?php
/** Fixed public discovery and release locations. Signed metadata remains the trust gate. */
final class AsusGithubUpdateSource implements AsusUpdateSource
{
    private const METADATA='https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/updates/public.json';
    private const RELEASES='https://github.com/madworldpay/nfqws2-asus-community/releases/download/';
    private const ASSET_HOST='release-assets.githubusercontent.com';
    private const HTTPS_PORT=443;
    private const ENVELOPE_LIMIT=46080;
    private const CORE='(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-asus[1-9][0-9]{0,5}';

    public function __construct(private int $owner=0,private string $ca='/opt/etc/ssl/certs/ca-certificates.crt',private array $timeouts=['metadata'=>15,'download'=>180]){}

    private static function redirect(string $url): string
    {
        // GitHub asset URLs contain an expiring query, but their origin and path
        // are fixed. Never accept relative URLs, credentials or another service.
        $parts=parse_url($url);
        if(strlen($url)>8192||preg_match('/[^\x21-\x7e]|\\\\/',$url)||!is_array($parts)||($parts['scheme']??null)!=='https'||
            ($parts['host']??null)!==self::ASSET_HOST||($parts['port']??443)!==self::HTTPS_PORT||
            !preg_match('~^/github-production-release-asset/[A-Za-z0-9/_-]+$~D',$parts['path']??''))throw new RuntimeException('download_redirect');
        foreach(['user','pass','fragment'] as $key)if(array_key_exists($key,$parts))throw new RuntimeException('download_redirect');
        return $url;
    }

    private function request(string $url,int $cap,float $deadline,bool $redirects=false,?callable $consume=null): string
    {
        if(!extension_loaded('openssl')||!is_readable($this->ca))throw new RuntimeException('https_unavailable');
        for($hop=0;;$hop++){
            $remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException('timed_out');
            // A fresh context per hop carries no credentials, cookies or headers
            // supplied by a server. TLS peer and hostname checks are mandatory.
            $context=stream_context_create(['ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false,'cafile'=>$this->ca],
                'http'=>['timeout'=>min(15,$remaining),'follow_location'=>0,'max_redirects'=>0,'ignore_errors'=>true,'protocol_version'=>1.1,
                    'header'=>"Accept: application/octet-stream\r\nAccept-Encoding: identity\r\nConnection: close\r\nUser-Agent: NFQWS2-ASUS-Updater/1\r\n"]]);
            $f=@fopen($url,'rb',false,$context);if(!$f)throw new RuntimeException('download_failed');
            try{
                if(microtime(true)>=$deadline)throw new RuntimeException('timed_out');
                $status=0;$length=null;$encoding=null;$location=null;$headerBytes=0;
                foreach(stream_get_meta_data($f)['wrapper_data']??[] as $header){
                    $headerBytes+=strlen($header);if($headerBytes>16384)throw new RuntimeException('download_failed');
                    if(preg_match('~^HTTP/\S+ ([0-9]{3})\b~',$header,$match)){$status=(int)$match[1];$length=null;$encoding=null;$location=null;}
                    elseif(stripos($header,'Content-Length:')===0){$value=trim(substr($header,15));if($length!==null||!preg_match('/^[0-9]{1,10}$/D',$value)||(float)$value>$cap)throw new RuntimeException('download_size');$length=(int)$value;}
                    elseif(stripos($header,'Content-Encoding:')===0){if($encoding!==null)throw new RuntimeException('download_size');$encoding=strtolower(trim(substr($header,17)));}
                    elseif(stripos($header,'Location:')===0){if($location!==null)throw new RuntimeException('download_redirect');$location=trim(substr($header,9));}
                }
                if(in_array($status,[301,302,303,307,308],true)){
                    if(!$redirects||$hop>=3||$location===null)throw new RuntimeException('download_redirect');
                    $url=self::redirect($location);continue;
                }
                if($status!==200)throw new RuntimeException('download_failed');
                if($encoding!==null&&$encoding!=='identity')throw new RuntimeException('download_size');
                $count=0;$body='';
                while(!feof($f)){
                    $remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException('timed_out');
                    $timeout=min(5,$remaining);stream_set_timeout($f,(int)$timeout,(int)(($timeout-(int)$timeout)*1000000));
                    $chunk=@fread($f,min(16384,$cap+1-$count));
                    if(microtime(true)>=$deadline)throw new RuntimeException('timed_out');
                    if($chunk===false||stream_get_meta_data($f)['timed_out'])throw new RuntimeException('download_failed');
                    $count+=strlen($chunk);if($count>$cap)throw new RuntimeException('download_size');
                    if($consume!==null)$consume($chunk);else $body.=$chunk;
                    if($chunk==='')usleep(1000);
                }
                if($length!==null&&$count!==$length)throw new RuntimeException('download_size');
                return $body;
            }finally{fclose($f);}
        }
    }

    public function manifest(): array
    {
        $raw=$this->request(self::METADATA,self::ENVELOPE_LIMIT,microtime(true)+min(15,$this->timeouts['metadata']));
        $envelope=AsusSupportSchema::decode($raw,self::ENVELOPE_LIMIT,'invalid_manifest');
        if(!is_object($envelope))throw new RuntimeException('invalid_manifest');
        $keys=array_keys(get_object_vars($envelope));sort($keys);
        if($keys!==['manifest','signature']||!is_string($envelope->manifest)||!is_string($envelope->signature))throw new RuntimeException('invalid_manifest');
        $json=base64_decode($envelope->manifest,true);
        if($json===false||$json===''||strlen($json)>32768||base64_encode($json)!==$envelope->manifest)throw new RuntimeException('invalid_manifest');
        $signature=base64_decode($envelope->signature,true);
        if(strlen($envelope->signature)>1024||$signature===false||strlen($signature)!==384||base64_encode($signature)!==$envelope->signature)throw new RuntimeException('invalid_signature');
        return ['json'=>$json,'signature'=>$envelope->signature];
    }

    public function download(array $package,string $destination): void
    {
        if(!is_string($package['filename']??null)||!preg_match('/^nfqws2-asus_'.self::CORE.'\+b([1-9][0-9]{0,9})_(?:aarch64-3\.10|armv7)\.ipk$/D',$package['filename'],$match)||(float)$match[1]>2147483647||
            !is_int($package['size']??null)||$package['size']<1||$package['size']>33554432||!is_string($package['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$package['sha256']))throw new RuntimeException('invalid_manifest');
        $url=self::RELEASES.'build'.$match[1].'/'.$package['filename'];
        for($path=$destination;$path!=='/'&&$path!=='.';$path=dirname($path))if(is_link($path))throw new RuntimeException('invalid_state');
        $parent=@lstat(dirname($destination));
        if(!$parent||($parent['mode']&0170000)!==0040000||($parent['mode']&0777)!==0700||$parent['uid']!==$this->owner)throw new RuntimeException('invalid_state');
        $mask=umask(0077);try{$out=@fopen($destination,'xb');}finally{umask($mask);}
        if(!$out)throw new RuntimeException('invalid_state');$created=fstat($out);$success=false;
        try{
            if(!chmod($destination,0600))throw new RuntimeException('invalid_state');
            $hash=hash_init('sha256');$count=0;
            $this->request($url,$package['size'],microtime(true)+min(180,$this->timeouts['download']),true,function($chunk)use($out,$hash,&$count){
                $count+=strlen($chunk);hash_update($hash,$chunk);if(fwrite($out,$chunk)!==strlen($chunk))throw new RuntimeException('insufficient_space');
            });
            if($count!==$package['size'])throw new RuntimeException('download_size');
            if(!hash_equals($package['sha256'],hash_final($hash)))throw new RuntimeException('download_hash');
            if(!fflush($out))throw new RuntimeException('insufficient_space');$success=true;
        }finally{
            fclose($out);
            if(!$success){clearstatcache(true,$destination);$stat=@lstat($destination);if($stat&&$stat['ino']===$created['ino']&&$stat['dev']===$created['dev']&&($stat['mode']&0170000)===0100000)@unlink($destination);}
        }
    }
}
