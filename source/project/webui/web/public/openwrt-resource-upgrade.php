<?php
require_once __DIR__.'/support-json-schema.php';

/** Update packaged Lua/blobs only while their active bytes still match old stock. */
final class NfqwsOpenWrtResourceUpgrade
{
    private static function parents(string $path,int $owner):void
    {
        for($p=dirname($path);$p!=='/';$p=dirname($p)){
            $s=@lstat($p);if(!$s||is_link($p)||!is_dir($p)||!in_array($s['uid'],[0,$owner],true)||(($s['mode']&0022)!==0&&!(($s['mode']&01000)!==0&&$s['uid']===0)))throw new RuntimeException('invalid_state');
        }
    }
    private static function read(string $path,int $owner,int $cap=16777216):array
    {
        self::parents($path,$owner);clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||is_link($path)||!is_file($path)||$s['uid']!==$owner||($s['mode']&0022)!==0||$s['nlink']!==1||$s['size']>$cap)throw new RuntimeException('invalid_state');
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$now=fstat($f);if($now['dev']!==$s['dev']||$now['ino']!==$s['ino'])throw new RuntimeException('invalid_state');$raw=stream_get_contents($f,$cap+1);if(!is_string($raw)||strlen($raw)!==$s['size'])throw new RuntimeException('invalid_state');return [$s,$raw];}finally{fclose($f);}
    }
    public static function apply(string $previous,string $defaults,string $active,int $owner=0):array
    {
        [, $raw]=self::read($previous,$owner,1048576);
        $old=AsusSupportSchema::toArray(AsusSupportSchema::decode($raw,1048576,'invalid_state'));
        if(!is_array($old)||!is_array($old['resources']??null)||count($old['resources'])>512)throw new RuntimeException('invalid_state');
        $plans=[];$bytes=0;
        foreach($old['resources']as $key=>$record){
            if(!is_string($key)||!preg_match('~^(lua|blob)/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})$~D',$key,$m)||
                !is_array($record)||!is_int($record['bytes']??null)||$record['bytes']<0||$record['bytes']>16777216||!is_string($record['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$record['sha256']))throw new RuntimeException('invalid_state');
            $relative=($m[1]==='blob'?'blobs':'lua').'/'.$m[2];$src=$defaults.'/'.$relative;$dst=$active.'/'.$relative;
            if(!file_exists($src)&&!is_link($src))continue;
            if(!file_exists($dst)&&!is_link($dst))continue;
            self::parents($dst,$owner);clearstatcache(true,$dst);$owned=@lstat($dst);
            // A custom link, owner or hard link is an operator resource, even
            // when its current bytes happen to equal an old packaged file.
            if(!$owned||is_link($dst)||!is_file($dst)||$owned['uid']!==$owner||$owned['nlink']!==1||($owned['mode']&0022)!==0)continue;
            [$s,$current]=self::read($dst,$owner);[, $new]=self::read($src,$owner);
            if(strlen($current)!==$record['bytes']||!hash_equals($record['sha256'],hash('sha256',$current))||$current===$new)continue;
            $bytes+=strlen($new);if($bytes>33554432)throw new RuntimeException('output_limit');
            $plans[]=[$key,$dst,$s,$current,$new];
        }
        $changed=[];
        foreach($plans as [$key,$dst,$s,$current,$new]){
            [$now,$raw]=self::read($dst,$owner);if($now['dev']!==$s['dev']||$now['ino']!==$s['ino']||$raw!==$current)throw new RuntimeException('settings_changed');
            $tmp=dirname($dst).'/.stock-'.bin2hex(random_bytes(8));$mask=umask(0077);
            try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('storage_unavailable');
            try{if(fwrite($f,$new)!==strlen($new)||!fflush($f)||!chmod($tmp,$s['mode']&0777))throw new RuntimeException('storage_unavailable');fclose($f);$f=null;
                if(!rename($tmp,$dst))throw new RuntimeException('storage_unavailable');$changed[]=$key;
            }finally{if(is_resource($f))fclose($f);if(is_file($tmp))unlink($tmp);}
        }
        return $changed;
    }
}
