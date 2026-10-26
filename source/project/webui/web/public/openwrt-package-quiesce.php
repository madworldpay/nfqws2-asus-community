<?php
require_once __DIR__.'/openwrt-update-guard.php';

/** One protected stop/snapshot boundary shared by native manager entry points. */
final class NfqwsOpenWrtPackageQuiesce
{
    public function __construct(private AsusUpdateStore $store){}
    public function run(string $mode):void
    {
        if(!in_array($mode,['upgrade','remove'],true))throw new RuntimeException('invalid_request');
        $manager=NfqwsOpenWrtManualContext::manager();$guard=new NfqwsOpenWrtUpdateGuard($this->store);$lease=null;
        if(!$guard->authorize('hook-prerm'))$lease=$this->store->lease('apply.lock');
        try{
            $script='/usr/lib/nfqws2/update/quiesce.sh';AsusUpdateStore::noLinks($script);clearstatcache(true,$script);$s=@lstat($script);
            if(!$s||!is_file($script)||!is_executable($script)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>131072)throw new RuntimeException('invalid_state');
            for($parent=dirname($script);$parent!=='/';$parent=dirname($parent)){$d=@lstat($parent);if(!$d||!is_dir($parent)||$d['uid']!==0||($d['mode']&0022)!==0)throw new RuntimeException('invalid_state');}
            $p=@proc_open([$script,$mode,$manager['format']],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C','LC_ALL'=>'C']);
            if(!is_resource($p))throw new RuntimeException('launch_failed');
            // Native scripts may be restoring DNS. No deadline may kill this
            // process halfway through a real manager mutation boundary.
            if(proc_close($p)!==0)throw new RuntimeException('core_stop_failed');
        }finally{if(is_resource($lease)){flock($lease,LOCK_UN);fclose($lease);}}
    }
}
