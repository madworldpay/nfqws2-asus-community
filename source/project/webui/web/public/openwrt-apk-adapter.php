<?php
require_once __DIR__.'/openwrt-apk-command.php';
require_once __DIR__.'/openwrt-update-guard.php';
require_once __DIR__.'/platform.php';

/** Installed APK pre-commit gate: maintainer-script errors alone do not veto writes. */
final class NfqwsOpenWrtApkAdapter
{
    public function __construct(private AsusUpdateStore $store){}
    public function run():void
    {
        $manager=NfqwsOpenWrtApkCommand::manager();
        $plan=NfqwsPlatform::run(NfqwsOpenWrtApkCommand::simulation($manager['argv']),30);
        if($plan['status']!==0)throw new RuntimeException('package_preflight_failed');
        $mode=NfqwsOpenWrtApkCommand::affects(implode("\n",$plan['output']));if($mode===null)return;
        $guard=new NfqwsOpenWrtUpdateGuard($this->store);
        if($guard->authorize('hook-prerm')){
            $ticket=$guard->ticket();$raw=$this->store->readFile('operations/'.$ticket['id'].'/quiesced.json',1024);
            if($raw===null||json_decode($raw,true)!==['captured'=>true])throw new RuntimeException('busy');
            return; // The scoped staged gate already stopped and captured this transaction.
        }
        $entry='/usr/lib/nfqws2/update/quiesce.php';AsusUpdateStore::noLinks($entry);$s=@lstat($entry);
        if(!$s||!is_file($entry)||$s['uid']!==0||$s['nlink']!==1||!in_array($s['mode']&0777,[0600,0644],true)||$s['size']>131072)throw new RuntimeException('invalid_state');
        for($p=dirname($entry);$p!=='/';$p=dirname($p)){$d=@lstat($p);if(!$d||!is_dir($p)||$d['uid']!==0||($d['mode']&0022)!==0)throw new RuntimeException('invalid_state');}
        $p=@proc_open(['/usr/bin/php8-cgi','-d','register_argc_argv=1','-q','-f',$entry,'--',$mode],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','php://stderr','a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C','LC_ALL'=>'C']);
        if(!is_resource($p))throw new RuntimeException('launch_failed');
        // Quiescence may already be restoring DNS: never kill this mutation.
        if(proc_close($p)!==0)throw new RuntimeException('core_stop_failed');
    }
}
