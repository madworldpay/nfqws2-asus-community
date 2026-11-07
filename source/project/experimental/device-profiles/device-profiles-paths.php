<?php
if(!class_exists('NfqwsPlatform',false))require_once __DIR__.'/platform.php';

/** Pin the firmware /opt alias and the service-owned private RAM boundary. */
final class NfqwsDeviceProfilesPaths
{
    private AsusShareRead $reader;
    private string $base;
    public function __construct(private string $alias='/opt',private int $owner=0)
    {
        if(!class_exists('AsusShareRead',false))require_once __DIR__.'/share-read.php';
        $base=realpath($alias);if($base===false)throw new RuntimeException('storage_unavailable');
        $this->base=rtrim($base,'/');$this->reader=new AsusShareRead($owner,$this->base,$alias,true);
        if(!$this->reader->directory($this->base))throw new RuntimeException('storage_unavailable');
    }
    public function canonical(string $path):string
    {
        if($path!==$this->alias&&!str_starts_with($path,$this->alias.'/'))throw new RuntimeException('unsafe_panel_file');
        if(preg_match('~(?:^|/)\.\.?(?:/|$)~',$path)||str_contains($path,"\0"))throw new RuntimeException('unsafe_panel_file');
        return $this->base.substr($path,strlen($this->alias));
    }
    public function file(string $directory,string $name):string
    {
        if(!preg_match('/^[A-Za-z0-9_.-]{1,128}$/D',$name)||in_array($name,['.','..'],true))throw new RuntimeException('unsafe_panel_file');
        $base=$this->canonical($directory);
        if(!$this->reader->directory($base))throw new RuntimeException('unsafe_panel_file');
        $path=$base.'/'.$name;clearstatcache(true,$path);$s=@lstat($path);
        if($s!==false&&(!$this->reader->stat($path)||($s['mode']&0002)!==0))throw new RuntimeException('unsafe_panel_file');
        return $path;
    }
    public static function guard(string $directory,string $name,int $owner=0):string
    {
        if($directory==='/opt'||str_starts_with($directory,'/opt/'))return (new self('/opt',$owner))->file($directory,$name);
        $ram='/tmp/nfqws2-asus';
        if($directory===$ram||str_starts_with($directory,$ram.'/')){
            $stat=@lstat($ram);
            if(!$stat||is_link($ram)||!is_dir($ram)||$stat['uid']!==$owner||($stat['mode']&0777)!==0700)throw new RuntimeException('unsafe_panel_file');
            // Merlin's firmware /tmp is 0777 without sticky. The ordinary
            // service owns this 0700 boundary; no other RAM tree is admitted.
            return (new self($ram,$owner))->file($directory,$name);
        }
        $base=realpath('/opt');
        if($base!==false&&($directory===$base||str_starts_with($directory,$base.'/')))return (new self('/opt',$owner))->file('/opt'.substr($directory,strlen($base)),$name);
        return NfqwsPlatform::guardFile($directory,$name,$owner);
    }
    public static function reader(string $path,int $owner=0):AsusShareRead
    {
        if($path==='/opt'||str_starts_with($path,'/opt/'))return NfqwsPlatform::reader($owner,true);
        $opt=realpath('/opt');if($opt!==false&&($path===$opt||str_starts_with($path,$opt.'/')))return NfqwsPlatform::reader($owner,true);
        return new AsusShareRead($owner,null,null,true);
    }
    public static function readPath(string $path):string
    {
        return $path==='/opt'||str_starts_with($path,'/opt/')?(new self())->canonical($path):$path;
    }
    public static function cliEntry(string $entry,array $server,array $argv):bool
    {
        $supplied=$server['SCRIPT_FILENAME']??($argv[0]??'');
        return !isset($server['REQUEST_METHOD'])&&is_string($supplied)&&($supplied===$entry||realpath($supplied)===$entry);
    }
}
