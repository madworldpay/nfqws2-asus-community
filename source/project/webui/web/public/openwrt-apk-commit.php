<?php
require_once __DIR__.'/openwrt-update-guard.php';

/** APK maintainer-script errors are not a pre-write veto; use its pre-commit gate. */
final class NfqwsOpenWrtApkCommit
{
    public static function install(AsusUpdateStore $store,string $id):array
    {
        $ticket=(new NfqwsOpenWrtUpdateGuard($store))->context($id);
        if($ticket['format']!=='apk'||$ticket['phase']!=='installing'||$ticket['worker']['pid']!==getmypid())throw new RuntimeException('invalid_state');
        $dir='/etc/apk/commit_hooks.d';AsusUpdateStore::noLinks($dir);$made=false;$mask=umask(0077);
        try{
            if(!is_dir($dir)){if(!mkdir($dir,0755))throw new RuntimeException('invalid_state');$made=true;}
            $s=lstat($dir);if(!is_dir($dir)||$s['uid']!==0||($s['mode']&0022)!==0)throw new RuntimeException('invalid_state');
            $name='00-nfqws2-native-'.$id;$path=$dir.'/'.$name;
            if(file_exists($path)||is_link($path)||file_exists('/lib/apk/commit_hooks.d/'.$name)||is_link('/lib/apk/commit_hooks.d/'.$name))throw new RuntimeException('busy');
            $w=$ticket['worker'];$entry=$store->path('operations/'.$id.'/runtime/worker.php');
            $script="#!/bin/sh\n# NFQWS2 native scoped pre-commit gate v1\n[ \"\$1\" = pre-commit ] || exit 0\n";
            // An abandoned gate is inert after its exact worker exits or a reboot.
            // PID reuse cannot turn it into a permanent system update blocker.
            $script.='[ "$(cat /proc/sys/kernel/random/boot_id)" = '.escapeshellarg($w['boot_id']).' ] || exit 0'."\n";
            $script.='[ "$(sed \'s/.*) //\' /proc/'.$w['pid'].'/stat 2>/dev/null | awk \'{print $20}\')" = '.escapeshellarg($w['start_ticks']).' ] || exit 0'."\n";
            $script.='exec /usr/bin/php8-cgi -d register_argc_argv=1 -q -f '.escapeshellarg($entry).' -- hook-apk-precommit '.escapeshellarg($id)."\n";
            $f=@fopen($path,'xb');if(!$f)throw new RuntimeException('invalid_state');
            try{if(fwrite($f,$script)!==strlen($script)||!fflush($f)||!chmod($path,0700))throw new RuntimeException('insufficient_space');}finally{fclose($f);}
            $token=['id'=>$id,'sha256'=>hash('sha256',$script),'directory_created'=>$made];
            $store->writeFile('operations/'.$id.'/apk-commit.json',json_encode($token,JSON_THROW_ON_ERROR));return $token;
        }finally{umask($mask);}
    }
    public static function remove(array $token):bool
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$token['id']??'')||!preg_match('/^[a-f0-9]{64}$/D',$token['sha256']??'')||!is_bool($token['directory_created']??null))throw new RuntimeException('invalid_state');
        $dir='/etc/apk/commit_hooks.d';$path=$dir.'/00-nfqws2-native-'.$token['id'];AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$s=@lstat($path);
        if($s===false)return true;
        if(!is_file($path)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==0700||$s['size']>4096||hash_file('sha256',$path)!==$token['sha256'])return false;
        if(!unlink($path))return false;if($token['directory_created'])@rmdir($dir);return true;
    }
}
