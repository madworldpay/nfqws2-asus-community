<?php
require_once __DIR__.'/share-read.php';
require_once __DIR__.'/dpi-store.php';
/** Lazy, bounded private journal and the common panel-writer mutex. */
final class AsusImportStore
{
    private string $root;
    private AsusShareRead $reader;
    private int $depth=0;
    public function __construct(?string $root=null,private int $owner=0)
    {
        $this->root=$root??AsusDpiStore::optPath('/var/lib/nfqws2-asus/import');
        $this->reader=$root===null?new AsusShareRead($owner,realpath('/opt'),'/opt'):new AsusShareRead($owner);
    }
    public function directory(bool $create=false): ?string
    {
        clearstatcache(true,$this->root);
        if(@lstat($this->root)===false){
            if(!$create)return null;$missing=[];$p=$this->root;
            while(@lstat($p)===false){$missing[]=$p;$p=dirname($p);}
            if(!$this->reader->directory($p))throw new RuntimeException('invalid_state');
            foreach(array_reverse($missing)as $dir){$mask=umask(0077);try{$ok=@mkdir($dir,0700);}finally{umask($mask);}if(!$ok)throw new RuntimeException('storage_unavailable');}
        }
        if(!$this->reader->directory($this->root))throw new RuntimeException('invalid_state');$s=lstat($this->root);
        if($s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');return $this->root;
    }
    private function path(string $name): string
    {if(!preg_match('/^(?:state\.json|writer\.lock|[a-f0-9]{32}\.(?:conf|draft|file-[0-9]{1,3})|\.write-[a-f0-9]{32})$/D',$name))throw new RuntimeException('invalid_state');return $this->root.'/'.$name;}
    public function read(string $name,int $limit=262144): ?string
    {
        if($this->directory()===null)return null;$p=$this->path($name);clearstatcache(true,$p);if(@lstat($p)===false)return null;
        $s=$this->reader->stat($p);if(!$s||$s['uid']!==$this->owner||($s['mode']&0777)!==0600)throw new RuntimeException('invalid_state');
        return $this->reader->bytes($p,$limit);
    }
    public function write(string $name,string $raw,int $limit=262144): void
    {
        if(strlen($raw)>$limit)throw new RuntimeException('output_limit');$this->directory(true);$this->read($name,$limit);
        $tmp=$this->path('.write-'.bin2hex(random_bytes(16)));$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('insufficient_space');
        try{if(@fwrite($f,$raw)!==strlen($raw)||!@fflush($f)||(function_exists('fsync')&&!@fsync($f)))throw new RuntimeException('insufficient_space');fclose($f);$f=null;
            if(!$this->reader->directory($this->root)||!@rename($tmp,$this->path($name)))throw new RuntimeException('storage_unavailable');
        }finally{if(is_resource($f))fclose($f);if(is_file($tmp))@unlink($tmp);}
    }
    public function remove(string $name): void
    {if($this->read($name)!==null&&!@unlink($this->path($name)))throw new RuntimeException('storage_unavailable');}
    public function locked(callable $fn): mixed
    {
        if($this->depth)return $fn();$this->directory(true);$path=$this->path('writer.lock');$this->read('writer.lock',0);$mask=umask(0077);
        try{$f=@fopen($path,'c+b');}finally{umask($mask);}if(!$f)throw new RuntimeException('invalid_state');
        try{$opened=fstat($f);clearstatcache(true,$path);$named=lstat($path);if(!$opened||!$named||$opened['ino']!==$named['ino']||$opened['dev']!==$named['dev']||!$this->reader->directory($this->root)||($opened['mode']&0777)!==0600||$opened['uid']!==$this->owner||$opened['nlink']!==1)throw new RuntimeException('invalid_state');
            if(!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');$this->depth++;try{return $fn();}finally{$this->depth--;}
        }finally{flock($f,LOCK_UN);fclose($f);}
    }
    public function state(): array
    {
        $raw=$this->read('state.json',262144);if($raw===null)return ['schema_version'=>1,'current'=>null,'history'=>[]];
        try{$v=json_decode($raw,true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(!is_array($v)||count($v)!==3||($v['schema_version']??null)!==1||!array_key_exists('current',$v)||!is_array($v['history']??null)||!array_is_list($v['history'])||count($v['history'])>3)throw new RuntimeException('invalid_state');
        foreach(array_merge([$v['current']],$v['history'])as $j)if($j!==null){
            if(!is_array($j)||!preg_match('/^[a-f0-9]{32}$/D',$j['id']??'')||!in_array($j['state']??'', ['prepared','committing','committed','undoing','undone','rolled_back','restore_required'],true)||!is_array($j['files']??null)||count($j['files'])>128)throw new RuntimeException('invalid_state');
            foreach(['request_digest','before','after']as $k)if(!is_string($j[$k]??null)||!preg_match('/^[a-f0-9]{64}$/D',$j[$k]))throw new RuntimeException('invalid_state');
            foreach($j['files']as $f)if(!is_array($f)||!preg_match('~^/opt/etc/nfqws2/(lists|lua|blobs)/[A-Za-z0-9_.-]{1,128}$~D',$f['path']??'')||!preg_match('/^[a-f0-9]{64}$/D',$f['sha256']??''))throw new RuntimeException('invalid_state');
            foreach($j['files']as $f){
                if(isset($f['before'])&&(!is_string($f['before'])||!preg_match('/^[a-f0-9]{64}$/D',$f['before'])))throw new RuntimeException('invalid_state');
                if(isset($f['before'])){$m=$f['metadata']??null;if(!is_array($m)||array_keys($m)!==['uid','gid','mode']||!in_array($m['uid'],[$this->owner,65534],true)||!is_int($m['gid'])||$m['gid']<0||$m['gid']>65535||!is_int($m['mode'])||$m['mode']<0||$m['mode']>0777)throw new RuntimeException('invalid_state');}
            }
        }return $v;
    }
    public function save(array $state): void
    {$this->write('state.json',json_encode($state,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR),262144);}
    public function prune(): void
    {
        // Remove only closed, unreferenced backups. A pending transaction stays.
        $s=$this->state();$keep=[];foreach(array_merge([$s['current']],$s['history'])as $j)if($j!==null)$keep[]=$j['id'];$size=0;
        foreach(scandir($this->directory(true))as $name){if(in_array($name,['.','..'],true))continue;
            if(preg_match('/^([a-f0-9]{32})\.(conf|draft|file-[0-9]{1,3})$/D',$name,$m)&&!in_array($m[1],$keep,true)){$this->remove($name);continue;}
            if(preg_match('/^\.write-[a-f0-9]{32}$/D',$name)){$this->remove($name);continue;}
            $raw=$this->read($name,262144);$size+=strlen($raw??'');if($size>8388608)throw new RuntimeException('output_limit');
        }
    }
}
