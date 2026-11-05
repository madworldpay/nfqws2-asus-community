<?php
require_once __DIR__.'/support-json-schema.php';

/** Update packaged Lua/blobs only while their active bytes still match old stock. */
final class NfqwsOpenWrtResourceUpgrade
{
    private static function parents(string $path,int $owner,?string $boundary=null):void
    {
        // ASUS owns the /opt alias; its descendants must still be ordinary,
        // protected directories. Native callers retain the complete root walk.
        if($boundary!==null&&(!str_starts_with($boundary,'/')||str_ends_with($boundary,'/')||!str_starts_with($path,$boundary.'/')))throw new RuntimeException('invalid_state');
        for($p=dirname($path);$p!=='/'&&$p!==$boundary;$p=dirname($p)){
            $s=@lstat($p);if(!$s||is_link($p)||!is_dir($p)||!in_array($s['uid'],[0,$owner],true)||(($s['mode']&0022)!==0&&!(($s['mode']&01000)!==0&&$s['uid']===0)))throw new RuntimeException('invalid_state');
        }
    }
    private static function read(string $path,int $owner,int $cap=16777216,?string $boundary=null):array
    {
        self::parents($path,$owner,$boundary);clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||is_link($path)||!is_file($path)||$s['uid']!==$owner||($s['mode']&0022)!==0||$s['nlink']!==1||$s['size']>$cap)throw new RuntimeException('invalid_state');
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$now=fstat($f);if($now['dev']!==$s['dev']||$now['ino']!==$s['ino'])throw new RuntimeException('invalid_state');$raw=stream_get_contents($f,$cap+1);if(!is_string($raw)||strlen($raw)!==$s['size'])throw new RuntimeException('invalid_state');return [$s,$raw];}finally{fclose($f);}
    }
    private static function syncParent(string $path):void
    {
        $directory=@fopen(dirname($path),'r');if(!$directory)throw new RuntimeException('storage_unavailable');
        try{if(!fsync($directory))throw new RuntimeException('storage_unavailable');}finally{fclose($directory);}
    }
    public static function apply(string $previous,string $defaults,string $active,int $owner=0,?string $boundary=null):array
    {
        [, $raw]=self::read($previous,$owner,1048576,$boundary);
        $old=AsusSupportSchema::toArray(AsusSupportSchema::decode($raw,1048576,'invalid_state'));
        if(!is_array($old)||!is_array($old['resources']??null)||count($old['resources'])>512)throw new RuntimeException('invalid_state');
        $plans=[];$bytes=0;
        foreach($old['resources']as $key=>$record){
            if(!is_string($key)||!preg_match('~^(lua|blob)/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})$~D',$key,$m)||
                !is_array($record)||!is_int($record['bytes']??null)||$record['bytes']<0||$record['bytes']>16777216||!is_string($record['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$record['sha256']))throw new RuntimeException('invalid_state');
            $relative=($m[1]==='blob'?'blobs':'lua').'/'.$m[2];$src=$defaults.'/'.$relative;$dst=$active.'/'.$relative;
            if(!file_exists($src)&&!is_link($src))continue;
            if(!file_exists($dst)&&!is_link($dst))continue;
            self::parents($dst,$owner,$boundary);clearstatcache(true,$dst);$owned=@lstat($dst);
            // A custom link, owner or hard link is an operator resource, even
            // when its current bytes happen to equal an old packaged file.
            if(!$owned||is_link($dst)||!is_file($dst)||$owned['uid']!==$owner||$owned['nlink']!==1||($owned['mode']&0022)!==0)continue;
            [$s,$current]=self::read($dst,$owner,16777216,$boundary);[, $new]=self::read($src,$owner,16777216,$boundary);
            if(strlen($current)!==$record['bytes']||!hash_equals($record['sha256'],hash('sha256',$current))||$current===$new)continue;
            $bytes+=strlen($new);if($bytes>33554432)throw new RuntimeException('output_limit');
            $plans[]=[$key,$dst,$s,$current,$new];
        }
        $changed=[];
        foreach($plans as [$key,$dst,$s,$current,$new]){
            [$now,$raw]=self::read($dst,$owner,16777216,$boundary);if($now['dev']!==$s['dev']||$now['ino']!==$s['ino']||$raw!==$current)throw new RuntimeException('settings_changed');
            $tmp=dirname($dst).'/.stock-'.bin2hex(random_bytes(8));$mask=umask(0077);
            try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('storage_unavailable');
            try{if(fwrite($f,$new)!==strlen($new)||!fflush($f)||!chmod($tmp,$s['mode']&0777))throw new RuntimeException('storage_unavailable');fclose($f);$f=null;
                if(!rename($tmp,$dst))throw new RuntimeException('storage_unavailable');$changed[]=$key;
            }finally{if(is_resource($f))fclose($f);if(is_file($tmp))unlink($tmp);}
        }
        return $changed;
    }
    /** ASUS only: discard new manager alternatives that exactly duplicate stock. */
    public static function cleanupOpkgSidecars(string $journal,string $defaults,string $active,int $owner=0,?string $boundary=null):array
    {
        if(!file_exists($journal)&&!is_link($journal))return [];
        [$meta,$raw]=self::read($journal,$owner,131072,$boundary);
        if(($meta['mode']&0777)!==0600||!str_ends_with($raw,"\n"))throw new RuntimeException('invalid_state');
        $lines=explode("\n",substr($raw,0,-1));if(array_shift($lines)!=='NFQWS LUA SIDECARS 1'||count($lines)>512)throw new RuntimeException('invalid_state');
        $before=[];foreach($lines as $name){if(!preg_match('/^[a-zA-Z0-9_.-]{1,124}\.lua-opkg$/D',$name)||isset($before[$name]))throw new RuntimeException('invalid_state');$before[$name]=true;}
        self::parents($defaults.'/lua/placeholder.lua',$owner,$boundary);$names=@scandir($defaults.'/lua');if(!is_array($names)||count($names)>514)throw new RuntimeException('invalid_state');
        $plans=[];$restores=[];$bytes=0;
        foreach($before as $name=>$_){
            [$saved,$original]=self::read(dirname($journal).'/'.$name,$owner,8388608,$boundary);
            if(($saved['mode']&07000)!==0)throw new RuntimeException('invalid_state');
            $bytes+=strlen($original);if($bytes>33554432)throw new RuntimeException('output_limit');
            $path=$active.'/lua/'.$name;$now=null;$copy=null;
            if(file_exists($path)||is_link($path)){
                [$now,$copy]=self::read($path,$owner,8388608,$boundary);
                if($copy===$original&&($now['mode']&0777)===($saved['mode']&0777)&&$now['gid']===$saved['gid'])continue;
                [$factory,$stock]=self::read($defaults.'/lua/'.substr($name,0,-5),$owner,8388608,$boundary);
                if($copy!==$stock||($now['mode']&0777)!==($factory['mode']&0777))throw new RuntimeException('settings_changed');
            }else self::parents($path,$owner,$boundary);
            $restores[]=[$path,$now,$copy,$saved,$original];
        }
        foreach($names as $name){
            if(!preg_match('/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,123}\.lua$/D',$name)||isset($before[$name.'-opkg']))continue;
            $path=$active.'/lua/'.$name.'-opkg';if(!file_exists($path)&&!is_link($path))continue;
            try{[$s,$copy]=self::read($path,$owner,8388608,$boundary);}catch(RuntimeException $e){continue;}
            [$factory,$stock]=self::read($defaults.'/lua/'.$name,$owner,8388608,$boundary);
            if($copy!==$stock||($s['mode']&0777)!==($factory['mode']&0777))continue;
            $bytes+=strlen($copy);if($bytes>33554432)throw new RuntimeException('output_limit');
            $plans[]=[$path,$s,$copy];
        }
        // All retained copies and all cleanup proofs are checked before writes.
        foreach($restores as [$path,$prior,$copy,$saved,$original]){
            if($prior===null){if(file_exists($path)||is_link($path))throw new RuntimeException('settings_changed');}
            else{[$now,$raw]=self::read($path,$owner,8388608,$boundary);if($now['dev']!==$prior['dev']||$now['ino']!==$prior['ino']||$raw!==$copy)throw new RuntimeException('settings_changed');}
            // A killed restore leaves staging in the private journal, never
            // in the active settings scanned by an older updater.
            $tmp=dirname($journal).'/.restore-'.bin2hex(random_bytes(8));$mask=umask(0077);
            try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('storage_unavailable');
            try{
                if(fwrite($f,$original)!==strlen($original)||!fflush($f)||!chgrp($tmp,$saved['gid'])||!chmod($tmp,$saved['mode']&0777)||!fsync($f))throw new RuntimeException('storage_unavailable');
                fclose($f);$f=null;if(!rename($tmp,$path))throw new RuntimeException('storage_unavailable');self::syncParent($path);
            }finally{if(is_resource($f))fclose($f);if(is_file($tmp))unlink($tmp);}
        }
        $removed=[];
        foreach($plans as [$path,$s,$copy]){
            try{[$now,$raw]=self::read($path,$owner,8388608,$boundary);}catch(RuntimeException $e){continue;}
            if($now['dev']!==$s['dev']||$now['ino']!==$s['ino']||($now['mode']&0777)!==($s['mode']&0777)||$raw!==$copy)continue;
            if(!unlink($path))throw new RuntimeException('storage_unavailable');$removed[]=basename($path);
        }
        return $removed;
    }
    /** Seal completion before the baseline is consumed; preinst reclaims it later. */
    public static function finishOpkgSidecars(string $journal,int $owner=0,?string $boundary=null):void
    {
        if(!file_exists($journal)&&!is_link($journal))return;
        [, $raw]=self::read($journal,$owner,131072,$boundary);
        $path=dirname($journal).'/complete';
        if(file_exists($path)||is_link($path)){
            [, $done]=self::read($path,$owner,32,$boundary);if($done!=="restored\n")throw new RuntimeException('invalid_state');return;
        }
        $stage=dirname($journal).'/.complete-'.bin2hex(random_bytes(8));
        $mask=umask(0077);try{$f=@fopen($stage,'xb');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('storage_unavailable');
        try{
            if(fwrite($f,"restored\n")!==9||!fflush($f)||!fsync($f))throw new RuntimeException('storage_unavailable');
            fclose($f);$f=null;if(!rename($stage,$path))throw new RuntimeException('storage_unavailable');self::syncParent($path);
        }finally{if(is_resource($f))fclose($f);if(is_file($stage))unlink($stage);}
    }
}
