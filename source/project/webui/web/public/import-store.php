<?php
require_once __DIR__.'/share-read.php';
require_once __DIR__.'/dpi-store.php';
require_once __DIR__.'/resource-paths.php';
/** Lazy, bounded private journal and the common panel-writer mutex. */
final class AsusImportStore
{
    private string $root;
    private AsusShareRead $reader;
    private int $depth=0;
    public function __construct(?string $root=null,private int $owner=0)
    {
        $this->reader=$root===null?NfqwsPlatform::reader($owner):new AsusShareRead($owner);
        $this->root=$root??(NfqwsPlatform::current()==='keenetic-entware'
            ?self::keeneticRoot(dirname(AsusDpiStore::optPath('/etc')))
            :AsusDpiStore::optPath('/var/lib/nfqws2-asus/import'));
    }
    /** Keep the original journal and its writer mutex on upgrades. On vendor
     * layouts where /opt/var belongs to 1001, begin new history under the
     * panel's root-owned settings directory. Every reader uses this choice. */
    public static function keeneticRoot(string $opt): string
    {
        $legacy=$opt.'/var/lib/nfqws2-asus/import';
        $private=$opt.'/etc/nfqws-asus-web/import';
        clearstatcache();
        $old=@lstat($legacy);
        if(@lstat($private)!==false){
            if($old!==false)throw new RuntimeException('restore_required');
            return $private;
        }
        if($old!==false)return $legacy;
        $var=@lstat($opt.'/var');
        if($var!==false&&$var['uid']===1001&&$var['gid']===1001&&($var['mode']&0177777)===0040755)return $private;
        return $legacy;
    }
    private static function fullSignature(array $s):array
    {return array_intersect_key($s,array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));}
    private function syncDirectory(string $path):void
    {
        if(!$this->reader->directory($path))throw new RuntimeException('source_changed');
        clearstatcache(true,$path);$before=lstat($path);$f=@fopen($path,'r');
        if(!$f)throw new RuntimeException('storage_unavailable');
        try{
            if(self::fullSignature(fstat($f))!==self::fullSignature($before))throw new RuntimeException('source_changed');
            if(!fsync($f))throw new RuntimeException('storage_unavailable');
            clearstatcache(true,$path);$after=@lstat($path);
            if(!$after||self::fullSignature(fstat($f))!==self::fullSignature($before)||
                self::fullSignature($after)!==self::fullSignature($before)||!$this->reader->directory($path))throw new RuntimeException('source_changed');
        }finally{fclose($f);}
    }
    public function directory(bool $create=false): ?string
    {
        clearstatcache(true,$this->root);
        if(@lstat($this->root)===false){
            if(!$create)return null;$missing=[];$p=$this->root;
            while(@lstat($p)===false){$missing[]=$p;$p=dirname($p);}
            if(!$this->reader->directory($p))throw new RuntimeException('invalid_state');
            foreach(array_reverse($missing)as $dir){$mask=umask(0077);try{$ok=@mkdir($dir,0700);}finally{umask($mask);}if(!$ok)throw new RuntimeException('storage_unavailable');$this->syncDirectory(dirname($dir));}
        }
        if(!$this->reader->directory($this->root))throw new RuntimeException('invalid_state');$s=lstat($this->root);
        if($s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');return $this->root;
    }
    private function path(string $name): string
    {if(!preg_match('/^(?:state\.json|writer\.lock|[a-f0-9]{32}\.(?:conf|draft|file-[0-9]{1,3})|\.write-[a-f0-9]{32})$/D',$name))throw new RuntimeException('invalid_state');return $this->root.'/'.$name;}
    public function read(string $name,int $limit=262144,?array &$pin=null): ?string
    {
        $pin=null;if($this->directory()===null)return null;$p=$this->path($name);clearstatcache(true,$p);if(@lstat($p)===false)return null;
        $s=$this->reader->stat($p);if(!$s||$s['uid']!==$this->owner||($s['mode']&0777)!==0600)throw new RuntimeException('invalid_state');
        $raw=$this->reader->bytes($p,$limit);$after=$this->reader->stat($p);
        if(!$after||self::fullSignature($after)!==self::fullSignature($s)||!$this->reader->directory($this->root))throw new RuntimeException('source_changed');
        $pin=self::fullSignature($s);return $raw;
    }
    public function write(string $name,string $raw,int $limit=262144): void
    {
        if(strlen($raw)>$limit)throw new RuntimeException('output_limit');$this->directory(true);
        $before=$this->read($name,$limit);$destination=$this->path($name);clearstatcache(true,$destination);$expected=@lstat($destination);
        if(($before===null)!==($expected===false)||$this->read($name,$limit)!==$before)throw new RuntimeException('source_changed');
        $tmp=$this->path('.write-'.bin2hex(random_bytes(16)));$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('insufficient_space');
        $created=fstat($f);
        try{
            if(@fwrite($f,$raw)!==strlen($raw)||!@fflush($f)||!@fsync($f))throw new RuntimeException('insufficient_space');
            $stage=fstat($f);$named=$this->reader->stat($tmp);
            if(!$created||!$stage||!$named||self::fullSignature($stage)!==self::fullSignature($named)||
                $stage['dev']!==$created['dev']||$stage['ino']!==$created['ino']||$stage['uid']!==$this->owner||
                ($stage['mode']&0177777)!==0100600||$stage['nlink']!==1||$stage['size']!==strlen($raw))throw new RuntimeException('source_changed');
            fclose($f);$f=null;
            $observed=$this->read($name,$limit);clearstatcache(true,$destination);$actual=@lstat($destination);
            if($observed!==$before||($expected===false?$actual!==false:($actual===false||self::fullSignature($actual)!==self::fullSignature($expected)))||
                !$this->reader->directory($this->root)||self::fullSignature($this->reader->stat($tmp)??[])!==self::fullSignature($stage))throw new RuntimeException('source_changed');
            if(!@rename($tmp,$destination))throw new RuntimeException('storage_unavailable');
            // Publication is not a durable/read-back receipt until both the
            // directory barrier and the exact published inode bytes pass.
            $this->syncDirectory($this->root);
            $published=$this->reader->stat($destination);$expectedPublished=$stage;
            // Our verified rename may legitimately change ctime. Observe that
            // one publication field, then require the complete published pin
            // to remain stable across the exact byte readback.
            if(!$published)throw new RuntimeException('source_changed');$expectedPublished['ctime']=$published['ctime'];
            if(self::fullSignature($published)!==self::fullSignature($expectedPublished)||
                $this->read($name,$limit)!==$raw||self::fullSignature($this->reader->stat($destination)??[])!==self::fullSignature($published))throw new RuntimeException('source_changed');
        }finally{
            if(is_resource($f))fclose($f);
            // Preserve swapped/partial/unknown stages. Only our exact inode
            // containing the entire requested buffer may be removed here.
            $remaining=$this->reader->stat($tmp);
            if($created&&$remaining&&$remaining['dev']===$created['dev']&&$remaining['ino']===$created['ino']&&
                $remaining['uid']===$this->owner&&($remaining['mode']&0177777)===0100600&&$remaining['nlink']===1){
                try{if($this->reader->bytes($tmp,$limit)===$raw&&self::fullSignature($this->reader->stat($tmp)??[])===self::fullSignature($remaining))@unlink($tmp);}
                catch(Throwable $ignored){/* Unknown bytes remain for attention. */}
            }
        }
    }
    public function remove(string $name): void
    {if($this->read($name)!==null&&!@unlink($this->path($name)))throw new RuntimeException('storage_unavailable');}
    public function locked(callable $fn): mixed
    {
        if($this->depth)return $fn();$this->directory(true);$path=$this->path('writer.lock');$this->read('writer.lock',0);$mask=umask(0077);
        // Detached probes must not retain the writer lease after its owner dies.
        try{$f=@fopen($path,'c+be');}finally{umask($mask);}if(!$f)throw new RuntimeException('invalid_state');
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
            foreach($j['files']as $f)if(!is_array($f)||!is_string($f['path']??null)||NfqwsResourcePaths::canonical($f['path'])!==$f['path']||!preg_match('/^[a-f0-9]{64}$/D',$f['sha256']??''))throw new RuntimeException('invalid_state');
            if(isset($j['directories'])&&(!is_array($j['directories'])||array_diff(array_keys($j['directories']),['lua','blobs'])))throw new RuntimeException('invalid_state');
            foreach($j['directories']??[] as $identity)if($identity!==null)self::identity($identity);
            if(isset($j['parents'])&&(!is_array($j['parents'])||array_diff(array_keys($j['parents']),['lua','blobs'])))throw new RuntimeException('invalid_state');
            foreach($j['parents']??[] as $identity)self::identity($identity);
            foreach($j['files']as $f)if(isset($f['identity']))self::identity($f['identity']);
            // New journals bind exactly every declared original backup. Old
            // journals without both fields retain their content-only contract.
            if(array_key_exists('backup_binding_version',$j)||array_key_exists('backups',$j)){
                if(($j['backup_binding_version']??null)!==1||!is_array($j['backups']??null)||!array_is_list($j['files'])||!is_bool($j['dns_changed']??null)||!array_key_exists('draft_before',$j))throw new RuntimeException('invalid_state');
                $expected=[$j['id'].'.conf'];foreach($j['files']as $i=>$f)if(isset($f['before']))$expected[]=$j['id'].'.file-'.$i;
                if($j['dns_changed']&&$j['draft_before']!==null)$expected[]=$j['id'].'.draft';
                $names=array_keys($j['backups']);sort($names);sort($expected);if($names!==$expected)throw new RuntimeException('invalid_state');
                foreach($j['backups']as $name=>$pin){
                    if(!is_array($pin))throw new RuntimeException('invalid_state');$keys=array_keys($pin);sort($keys);
                    if($keys!==['ctime','dev','gid','ino','mode','mtime','nlink','size','uid'])throw new RuntimeException('invalid_state');
                    foreach($pin as $value)if(!is_int($value))throw new RuntimeException('invalid_state');
                    if($pin['uid']!==$this->owner||$pin['gid']<0||$pin['gid']>65535||$pin['mode']!==0100600||$pin['nlink']!==1||$pin['size']<0||$pin['size']>(str_ends_with($name,'.draft')?65536:262144))throw new RuntimeException('invalid_state');
                }
            }
            // Prepared-only full-original snapshots bind observed source
            // inodes as well as backup inodes. They cannot become commits.
            if(array_key_exists('source_binding_version',$j)||array_key_exists('sources',$j)){
                if(($j['source_binding_version']??null)!==1||!is_array($j['sources']??null)||
                    !in_array($j['state'],['prepared','rolled_back','restore_required'],true)||
                    !array_is_list($j['files'])||($j['dns_changed']??null)!==false||
                    array_key_exists('directories',$j)||array_key_exists('parents',$j))throw new RuntimeException('invalid_state');
                $keys=array_keys($j['sources']);sort($keys);if($keys!==['config','files']||!is_array($j['sources']['files']))throw new RuntimeException('invalid_state');
                $expected=[];foreach($j['files']as $f){if(($f['before']??null)!==$f['sha256']||isset($expected[$f['path']]))throw new RuntimeException('invalid_state');$expected[$f['path']]=true;}
                $paths=array_keys($j['sources']['files']);$names=array_keys($expected);sort($paths);sort($names);if($paths!==$names)throw new RuntimeException('invalid_state');
                foreach(array_merge([$j['sources']['config']],array_values($j['sources']['files']))as $pin){
                    if(!is_array($pin))throw new RuntimeException('invalid_state');$keys=array_keys($pin);sort($keys);
                    if($keys!==['ctime','dev','gid','ino','mode','mtime','nlink','size','uid'])throw new RuntimeException('invalid_state');
                    foreach($pin as $value)if(!is_int($value))throw new RuntimeException('invalid_state');
                    if(!in_array($pin['uid'],[$this->owner,65534],true)||$pin['gid']<0||$pin['gid']>65535||
                        ($pin['mode']&0170000)!==0100000||$pin['nlink']!==1||$pin['size']<0||$pin['size']>262144)throw new RuntimeException('invalid_state');
                }
                foreach($j['files']as $f){$p=$j['sources']['files'][$f['path']];$m=$f['metadata']??null;
                    if(!is_array($m)||$p['uid']!==($m['uid']??null)||$p['gid']!==($m['gid']??null)||($p['mode']&0777)!==($m['mode']??null))throw new RuntimeException('invalid_state');}
            }
            if(isset($j['inputs'])){if(!is_array($j['inputs'])||count($j['inputs'])>128)throw new RuntimeException('invalid_state');foreach($j['inputs'] as $path=>$sha)if(!is_string($path)||NfqwsResourcePaths::canonical($path)!==$path||!is_string($sha)||!preg_match('/^[a-f0-9]{64}$/D',$sha))throw new RuntimeException('invalid_state');}
            foreach($j['files']as $f){
                if(isset($f['before'])&&(!is_string($f['before'])||!preg_match('/^[a-f0-9]{64}$/D',$f['before'])))throw new RuntimeException('invalid_state');
                if(isset($f['before'])){$m=$f['metadata']??null;if(!is_array($m)||array_keys($m)!==['uid','gid','mode']||!in_array($m['uid'],[$this->owner,65534],true)||!is_int($m['gid'])||$m['gid']<0||$m['gid']>65535||!is_int($m['mode'])||$m['mode']<0||$m['mode']>0777)throw new RuntimeException('invalid_state');}
            }
        }return $v;
    }
    private static function identity(mixed $value):void
    {
        if(!is_array($value))throw new RuntimeException('invalid_state');$keys=array_keys($value);sort($keys);
        if($keys!==['dev','gid','ino','mode','uid'])throw new RuntimeException('invalid_state');
        foreach($value as $v)if(!is_int($v))throw new RuntimeException('invalid_state');
        // dev/ino can be signed on 32-bit PHP; compare the exact observed values.
        foreach(['uid','gid','mode'] as $key)if($value[$key]<0)throw new RuntimeException('invalid_state');
    }
    public function save(array $state): void
    {$this->write('state.json',json_encode($state,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR),262144);}
    public function prune(bool $remove=true): void
    {
        // Remove only closed, unreferenced backups. A pending transaction stays.
        $s=$this->state();$keep=[];foreach(array_merge([$s['current']],$s['history'])as $j)if($j!==null)$keep[]=$j['id'];$size=0;
        foreach(scandir($this->directory(true))as $name){if(in_array($name,['.','..'],true))continue;
            if(preg_match('/^([a-f0-9]{32})\.(conf|draft|file-[0-9]{1,3})$/D',$name,$m)&&$remove&&!in_array($m[1],$keep,true)){$this->remove($name);continue;}
            if(preg_match('/^\.write-[a-f0-9]{32}$/D',$name))throw new RuntimeException('restore_required');
            $raw=$this->read($name,262144);$size+=strlen($raw??'');if($size>8388608)throw new RuntimeException('output_limit');
        }
    }
}
