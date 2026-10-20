<?php
require_once __DIR__.'/dpi-store.php';
require_once __DIR__.'/support-report-platform.php';
/** Optional installation pseudonym, independent of hardware and network IDs. */
final class AsusShareSource
{
    public function __construct(private ?string $root=null,private int $owner=0,private ?AsusReportIO $io=null){}
    public function identity(bool $consent): ?string
    {
        if(!$consent)return null;
        $root=$this->root??AsusDpiStore::optPath('/etc/nfqws-asus-web/share-identity');
        if($root===''||$root[0]!=='/'||str_contains($root,"\0"))throw new RuntimeException('identity_unavailable');
        for($p=$root;$p!=='/';$p=dirname($p))if(is_link($p))throw new RuntimeException('identity_unavailable');
        $mask=umask(0077);
        try {if(!is_dir($root)&&!@mkdir($root,0700))throw new RuntimeException('identity_unavailable');}
        finally {umask($mask);}
        $st=@lstat($root);
        if(!$st||($st['mode']&0170000)!==0040000||($st['mode']&0777)!==0700||$st['uid']!==$this->owner)throw new RuntimeException('identity_unavailable');
        // A private lock serializes creation; unfinished IDs are never returned.
        $lock=$this->open($root.'/lock');
        try {
            if(!flock($lock,LOCK_EX))throw new RuntimeException('identity_unavailable');
            $path=$root.'/id';clearstatcache(true,$path);
            if(!file_exists($path)&&!is_link($path)) {
                $id=bin2hex(random_bytes(16));$tmp=$root.'/.new-'.bin2hex(random_bytes(8));$f=$this->open($tmp);
                try {if(fwrite($f,$id)!==32||!fflush($f))throw new RuntimeException('identity_unavailable');}
                finally {fclose($f);}
                try {if(!rename($tmp,$path))throw new RuntimeException('identity_unavailable');}
                finally {if(is_file($tmp))@unlink($tmp);}
            }
            $f=$this->open($path,false);
            try {$id=stream_get_contents($f,33);}finally {fclose($f);}
            if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('identity_unavailable');
            return $id;
        } finally {flock($lock,LOCK_UN);fclose($lock);}
    }
    private function open(string $path,bool $create=true): mixed
    {
        clearstatcache(true,$path);$st=@lstat($path);
        if($st&&(($st['mode']&0170000)!==0100000||($st['mode']&0777)!==0600||$st['uid']!==$this->owner||$st['nlink']!==1||$st['size']>32))throw new RuntimeException('identity_unavailable');
        $mask=umask(0077);
        try {$f=@fopen($path,$st?'r+b':($create?'x+b':'rb'));}finally {umask($mask);}
        if(!$f)throw new RuntimeException('identity_unavailable');
        $a=fstat($f);clearstatcache(true,$path);$b=@lstat($path);
        if(!$b||$a['ino']!==$b['ino']||$a['dev']!==$b['dev']||($a['mode']&0170000)!==0100000||($a['mode']&0777)!==0600||$a['uid']!==$this->owner||$a['nlink']!==1||$a['size']>32){fclose($f);throw new RuntimeException('identity_unavailable');}
        return $f;
    }
    public static function platform(array $nvram,string $kernel,array $versions): array
    {
        $fw=[];foreach(['firmver','buildno','extendno'] as $key)$fw[$key]=is_string($nvram[$key]??null)&&preg_match('/^[0-9]{1,8}(?:[._-][0-9]{1,8})*(?:[_-]gnuton[0-9._-]*)?$/Di',$nvram[$key])?$nvram[$key]:null;
        $v=[];foreach(['core','web'] as $key)$v[$key]=is_string($versions[$key]??null)&&preg_match('/^[A-Za-z0-9.+_-]{1,64}$/D',$versions[$key])?$versions[$key]:'unknown';
        return ['model'=>AsusReportPlatform::model(($nvram['odmpid']??'')?:($nvram['productid']??'')),'firmware'=>$fw,
            'kernel'=>preg_match('/^[0-9]{1,3}\.[0-9]{1,3}(?:\.[0-9]{1,4})?(?:[-_](?:merlin|asus|gnuton|[0-9_.]+))?$/Di',$kernel)?$kernel:null,'versions'=>$v];
    }
    public function capture(bool $consent,array $versions): array
    {
        $io=$this->io??new AsusReportIO();$platform=new AsusReportPlatform($io,new AsusReportValues());$nv=$platform->readNvram();
        $out=self::platform($nv['values'],trim($io->read('kernel',128)['value']),$versions);
        $id=$this->identity($consent);if($id!==null)$out['installation_id']=$id;return $out;
    }
}
