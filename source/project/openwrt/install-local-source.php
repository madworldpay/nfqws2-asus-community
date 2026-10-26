<?php
/** Local verified bootstrap archive, consumed once by the installed coordinator. */
final class NfqwsOpenWrtInstallLocalSource implements AsusUpdateSource
{
    public function __construct(private array $plan){}
    public function manifest():array{return ['json'=>$this->plan['manifest'],'signature'=>$this->plan['signature']];}
    public function download(array $package,string $destination):void
    {
        if($package!==$this->plan['candidate']['package'])throw new RuntimeException('stale_revision');$source=$this->plan['archive'];
        AsusUpdateStore::noLinks($source);AsusUpdateStore::noLinks($destination);clearstatcache(true,$source);$s=@lstat($source);$parent=@lstat(dirname($destination));
        if(!$s||!is_file($source)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==0600||file_exists($destination)||!$parent||!is_dir(dirname($destination))||$parent['uid']!==0||($parent['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        if($s['size']!==$package['size']||!hash_equals($package['sha256'],hash_file('sha256',$source)))throw new RuntimeException('download_hash');
        // Both directories belong to the root-private /tmp bootstrap/update
        // stores. Rename retains ownership/mode and does not duplicate RAM.
        if(!rename($source,$destination))throw new RuntimeException('download_failed');
    }
}
