<?php
require_once __DIR__.'/update-store.php';

/** Per-operation union of native feed trust and the pinned application key. */
final class NfqwsOpenWrtApkTrust
{
    private static function directory(string $path,int $owner):void
    {
        AsusUpdateStore::noLinks($path);$s=@lstat($path);
        if(!$s||!is_dir($path)||!in_array($s['uid'],[0,$owner],true)||($s['mode']&0022)!==0)throw new RuntimeException('invalid_state');
    }
    public static function stage(string $destination,string $ownKey,array $roots=['/etc/apk/keys','/lib/apk/keys'],int $owner=0):array
    {
        if(!extension_loaded('openssl'))throw new RuntimeException('signature_unavailable');
        $own=@openssl_pkey_get_public($ownKey);$details=$own===false?false:openssl_pkey_get_details($own);
        if(strlen($ownKey)>16384||!$details||$details['type']!==OPENSSL_KEYTYPE_RSA||$details['bits']!==3072)throw new RuntimeException('invalid_signature');
        self::directory(dirname($destination),$owner);AsusUpdateStore::noLinks($destination);
        if(file_exists($destination)||is_link($destination)||count($roots)>2)throw new RuntimeException('invalid_state');
        $keys=[];$seen=[];$total=0;
        foreach($roots as $root){
            if(!is_string($root))throw new RuntimeException('invalid_state');
            if(!file_exists($root)&&!is_link($root))continue;self::directory($root,$owner);
            $names=scandir($root);if($names===false||count($names)>258)throw new RuntimeException('output_limit');
            foreach($names as $name){
                if(str_starts_with($name,'.')||isset($seen[$name]))continue;$seen[$name]=true;
                $path=$root.'/'.$name;$s=@lstat($path);
                if($s&&is_link($path)){
                    if(!in_array($s['uid'],[0,$owner],true))throw new RuntimeException('invalid_state');
                    $resolved=realpath($path);if($resolved===false)continue;
                    self::directory(dirname($resolved),$owner);$path=$resolved;$s=@lstat($path);
                }
                if(!$s||!is_file($path)||$s['size']>16384)continue;
                $raw=@file_get_contents($path,false,null,0,16385);
                if(!is_string($raw)||!preg_match('/\A\s*-----BEGIN (?:RSA )?PUBLIC KEY-----/',$raw)||@openssl_pkey_get_public($raw)===false)continue;
                if(!in_array($s['uid'],[0,$owner],true)||($s['mode']&0022)!==0||!preg_match('/^[A-Za-z0-9][A-Za-z0-9_.@+-]{0,191}$/D',$name))throw new RuntimeException('invalid_state');
                $keys[$name]=$raw;$total+=strlen($raw);if(count($keys)>128||$total>1048576)throw new RuntimeException('output_limit');
            }
        }
        $name='nfqws2-native-'.hash('sha256',$ownKey).'.pem';
        if(isset($keys[$name])&&$keys[$name]!==$ownKey)throw new RuntimeException('invalid_state');$keys[$name]=$ownKey;
        ksort($keys);$files=[];$mask=umask(0077);
        try{
            if(!mkdir($destination,0700))throw new RuntimeException('storage_unavailable');
            foreach($keys as $name=>$raw){
                if(file_put_contents($destination.'/'.$name,$raw)!==strlen($raw)||!chmod($destination.'/'.$name,0600))throw new RuntimeException('storage_unavailable');
                $files[$name]=hash('sha256',$raw);
            }
        }finally{umask($mask);}
        return ['files'=>$files,'digest'=>hash('sha256',json_encode($files,JSON_THROW_ON_ERROR))];
    }
}
