<?php
require_once __DIR__.'/update-store.php';

/** Immutable application closure; OpenWrt's PHP remains a native system dependency. */
final class NfqwsOpenWrtUpdateRuntime
{
    private static function regular(string $path,int $owner,int $cap):array
    {
        AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||!is_file($path)||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>$cap)throw new RuntimeException('invalid_state');
        return ['mode'=>$s['mode']&0777,'size'=>$s['size'],'sha256'=>hash_file('sha256',$path)];
    }
    private static function php():array
    {
        $path=realpath('/usr/bin/php-cgi');
        if($path!=='/usr/bin/php8-cgi'||!is_executable($path))throw new RuntimeException('unsupported_runtime');
        return ['path'=>$path]+self::regular($path,0,16777216);
    }
    public static function stage(string $destination,array $options=[],int $owner=0):array
    {
        AsusUpdateStore::noLinks($destination);if(file_exists($destination)||is_link($destination))throw new RuntimeException('invalid_state');
        $parent=@lstat(dirname($destination));if(!$parent||!is_dir(dirname($destination))||$parent['uid']!==$owner||($parent['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $php=self::php();$app=$options['application']??'/usr/share/nfqws2-web';$resources=$options['resources']??'/usr/share/nfqws2';
        $sources=[];$total=0;
        $add=function(string $name,string $path,int $mode=0600)use(&$sources,&$total,$owner){
            $s=self::regular($path,$owner,4194304);$s['mode']=$mode;$s['source']=$path;$total+=$s['size'];
            if($total>16777216||count($sources)>=192)throw new RuntimeException('runtime_limit');$sources[$name]=$s;
        };
        $files=glob($app.'/*.php')?:[];if(count($files)<1||count($files)>128)throw new RuntimeException('runtime_limit');
        foreach($files as $file)$add('app/'.basename($file),$file);
        $add('app/platform-profile.json',$app.'/platform-profile.json');
        $add('worker.php',$options['entry']??'/usr/lib/nfqws2/update/worker.php');
        foreach(['openwrt-package-manifest.schema.json','update-release-key.pem']as $name)$add('resources/'.$name,$resources.'/'.$name);
        $runner="#!/bin/sh\nset -f\numask 077\nPATH=/usr/sbin:/usr/bin:/sbin:/bin\nexport PATH\nunset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME\n[ \"\$#\" = 2 ] || exit 2\ncase \"\$1\" in check|prepare|apply|guard-check|guard-prepare) ;; *) exit 2;; esac\ncase \"\$2\" in ''|*[!a-f0-9]*) exit 2;; esac\n[ \"\${#2}\" = 32 ] || exit 2\nexec ".escapeshellarg($php['path']).' -d register_argc_argv=1 -q -f '.escapeshellarg($destination.'/worker.php').' -- "$1" "$2"'."\n";
        $total+=strlen($runner);$free=$options['free']??disk_free_space(dirname($destination));
        if(!is_numeric($free)||!is_finite((float)$free)||$free<$total+4194304)throw new RuntimeException('insufficient_space');
        $index=[];foreach($sources as $name=>$s)$index[$name]=array_intersect_key($s,array_flip(['mode','size','sha256']));
        $index['run.sh']=['mode'=>0700,'size'=>strlen($runner),'sha256'=>hash('sha256',$runner)];ksort($index);
        $mask=umask(0077);
        try{
            if(!mkdir($destination,0700))throw new RuntimeException('invalid_state');
            if(file_put_contents($destination.'/staging.json',json_encode(['files'=>$index],JSON_THROW_ON_ERROR))===false)throw new RuntimeException('insufficient_space');
            foreach($sources as $name=>$s){
                $path=$destination.'/'.$name;if(!is_dir(dirname($path))&&!mkdir(dirname($path),0700,true))throw new RuntimeException('invalid_state');
                if(!copy($s['source'],$path)||!chmod($path,$s['mode']))throw new RuntimeException('insufficient_space');
                $actual=self::regular($path,$owner,4194304);if($actual!==$index[$name])throw new RuntimeException('runtime_changed');
            }
            if(file_put_contents($destination.'/run.sh',$runner)!==strlen($runner)||!chmod($destination.'/run.sh',0700))throw new RuntimeException('insufficient_space');
            $raw=json_encode(['schema'=>1,'php'=>$php,'files'=>$index,'bytes'=>$total],JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES);
            if(strlen($raw)>131072||file_put_contents($destination.'/closure.json',$raw)!==strlen($raw))throw new RuntimeException('insufficient_space');
            unlink($destination.'/staging.json');
        }finally{umask($mask);}
        return self::load($destination,$owner);
    }
    public static function load(string $directory,int $owner=0):array
    {
        AsusUpdateStore::noLinks($directory);$s=@lstat($directory);
        if(!$s||!is_dir($directory)||$s['uid']!==$owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $meta=self::regular($directory.'/closure.json',$owner,131072);if($meta['mode']!==0600)throw new RuntimeException('invalid_state');
        $raw=file_get_contents($directory.'/closure.json');$v=json_decode($raw,true,32,JSON_THROW_ON_ERROR);
        if(!is_array($v)||array_keys($v)!==['schema','php','files','bytes']||$v['schema']!==1||!is_array($v['files'])||count($v['files'])>192||$v['php']!==self::php())throw new RuntimeException('runtime_changed');
        foreach(['worker.php','run.sh','app/platform.php','app/platform-profile.json','app/update-store.php','app/openwrt-update-runtime.php','resources/openwrt-package-manifest.schema.json','resources/update-release-key.pem']as $required)if(!isset($v['files'][$required]))throw new RuntimeException('runtime_changed');
        $total=0;
        foreach($v['files']as $name=>$item){
            if(!is_string($name)||!preg_match('~^(?:app/[A-Za-z0-9_.-]+|resources/(?:openwrt-package-manifest\.schema\.json|update-release-key\.pem)|worker\.php|run\.sh)$~D',$name)||in_array(basename($name),['.','..'],true))throw new RuntimeException('invalid_state');
            if(($item['mode']??null)!==($name==='run.sh'?0700:0600))throw new RuntimeException('runtime_changed');
            $actual=self::regular($directory.'/'.$name,$owner,4194304);if($actual!==$item)throw new RuntimeException('runtime_changed');$total+=$actual['size'];
        }
        if($total!==$v['bytes']||$total>16777216)throw new RuntimeException('runtime_changed');
        return $v+['digest'=>hash('sha256',$raw)];
    }
}
