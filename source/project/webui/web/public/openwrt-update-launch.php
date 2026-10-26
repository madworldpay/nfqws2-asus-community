<?php
require_once __DIR__.'/openwrt-update-runtime.php';

/** Fixed native detach command, independent of the web server process lifetime. */
final class NfqwsOpenWrtUpdateLaunch
{
    private static function executable(string $path):void
    {
        AsusUpdateStore::noLinks($path);$s=@lstat($path);
        if(!$s||!is_file($path)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0022)!==0||!is_executable($path))throw new RuntimeException('invalid_state');
        for($p=dirname($path);$p!=='/';$p=dirname($p)){$d=@lstat($p);if(!$d||!is_dir($p)||$d['uid']!==0||($d['mode']&0022)!==0&&!(($d['mode']&01000)!==0&&$d['uid']===0))throw new RuntimeException('invalid_state');}
    }
    public static function launch(AsusUpdateStore $store,string $kind,string $id):void
    {
        if(!in_array($kind,['check','prepare','apply'],true)||!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');
        $entry='/usr/lib/nfqws2/update/worker.sh';
        if($kind==='apply'){
            $root=$store->path('operations/'.$id.'/runtime');$r=NfqwsOpenWrtUpdateRuntime::load($root);
            if(($store->readOperation($id)['runtime_digest']??null)!==$r['digest'])throw new RuntimeException('runtime_changed');$entry=$root.'/run.sh';
        }
        self::executable('/bin/busybox');self::executable($entry);
        $p=@proc_open(['/bin/busybox','start-stop-daemon','-S','-b','-p',$store->path('unused-native-'.$kind.'-'.$id.'.pid'),'-x','/bin/sh','--',$entry,'guard-'.$kind,$id],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C','LC_ALL'=>'C','HOME'=>'/']);
        if(!is_resource($p)||proc_close($p)!==0)throw new RuntimeException('launch_failed');
    }
}
