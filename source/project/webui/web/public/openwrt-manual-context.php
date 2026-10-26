<?php
require_once __DIR__.'/update-lifecycle.php';

/** Only the fixed root quiesce controller inside a live native manager. */
final class NfqwsOpenWrtManualContext
{
    public static function manager():array
    {
        if(!NfqwsPlatform::native())throw new RuntimeException('invalid_state');$allowed=[];
        foreach(['ipk'=>'/bin/opkg','apk'=>'/usr/bin/apk']as $format=>$path){$real=realpath($path);if($real!==false)$allowed[$real]=$format;}
        $pid=getmypid();$seen=[];
        for($n=0;$n<32&&$pid>1;$n++){
            if(isset($seen[$pid]))break;$seen[$pid]=true;$i=AsusUpdateLifecycle::identity($pid);
            if($i!==null&&$i['uid']===0&&isset($allowed[$i['exe']])){
                $raw=@file_get_contents('/proc/'.$pid.'/cmdline',false,null,0,65537);
                if(!is_string($raw)||strlen($raw)>65536||!str_ends_with($raw,"\0")||AsusUpdateLifecycle::identity($pid)!==$i)throw new RuntimeException('invalid_state');
                return ['format'=>$allowed[$i['exe']],'identity'=>$i,'argv'=>explode("\0",substr($raw,0,-1))];
            }
            $raw=@file_get_contents('/proc/'.$pid.'/status');if(!is_string($raw)||!preg_match('/^PPid:\s+([0-9]+)/m',$raw,$m))break;$pid=(int)$m[1];
        }
        throw new RuntimeException('invalid_state');
    }
    public static function authorize():bool
    {
        if(!NfqwsPlatform::native())return false;$entry='/usr/lib/nfqws2/update/quiesce.php';
        try{AsusUpdateStore::noLinks($entry);}catch(Throwable $e){return false;}
        clearstatcache(true,$entry);$file=@lstat($entry);
        if(!$file||!is_file($entry)||$file['uid']!==0||$file['nlink']!==1||($file['mode']&0022)!==0)return false;
        for($parent=dirname($entry);$parent!=='/';$parent=dirname($parent)){$d=@lstat($parent);if(!$d||!is_dir($parent)||$d['uid']!==0||($d['mode']&0022)!==0)return false;}
        $php=realpath('/usr/bin/php-cgi');if($php!=='/usr/bin/php8-cgi')return false;
        $allowed=array_filter([realpath('/bin/opkg'),realpath('/usr/bin/apk')]);$controller=null;$manager=null;$pid=getmypid();$seen=[];
        for($n=0;$n<32&&$pid>1;$n++){
            if(isset($seen[$pid]))return false;$seen[$pid]=true;$i=AsusUpdateLifecycle::identity($pid);
            if($i!==null&&$i['uid']===0){
                if($controller===null&&$i['exe']===$php){
                    $raw=@file_get_contents('/proc/'.$pid.'/cmdline',false,null,0,8193);
                    if(is_string($raw)&&strlen($raw)<=8192&&str_ends_with($raw,"\0")){
                        $args=explode("\0",substr($raw,0,-1));$prefix=[$php,'-d','register_argc_argv=1','-q','-f',$entry,'--'];
                        if(count($args)===8&&array_slice($args,0,7)===$prefix&&in_array($args[7],['upgrade','remove'],true))$controller=$i;
                    }
                }elseif($controller!==null&&in_array($i['exe'],$allowed,true)){$manager=$i;break;}
            }
            $raw=@file_get_contents('/proc/'.$pid.'/status');if(!is_string($raw)||!preg_match('/^PPid:\s+([0-9]+)/m',$raw,$m))return false;$pid=(int)$m[1];
        }
        if($controller===null||$manager===null||!AsusUpdateLifecycle::alive($controller)||!AsusUpdateLifecycle::alive($manager))return false;
        $path='/tmp/nfqws2-native-package/state';try{AsusUpdateStore::noLinks($path);}catch(Throwable $e){return false;}
        $dir=@lstat(dirname($path));$s=@lstat($path);
        if(!$dir||!is_dir(dirname($path))||$dir['uid']!==0||($dir['mode']&0777)!==0700||!$s||!is_file($path)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>4096)return false;
        $raw=file_get_contents($path);if(!is_string($raw)||preg_match_all('/^manager=([^\r\n]*)$/m',$raw,$m)!==1)return false;
        return $m[1][0]===$manager['boot_id'].':'.$manager['pid'].':'.$manager['start_ticks']&&AsusUpdateLifecycle::alive($manager)&&AsusUpdateLifecycle::alive($controller);
    }
}
