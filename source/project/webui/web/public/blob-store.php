<?php
require_once __DIR__.'/dpi-store.php';
require_once __DIR__.'/share-read.php';
/** Fixed blob resources are inert bytes. Mounted storage paths stay private. */
final class AsusBlobStore
{
    public const FILE_LIMIT=262144;
    public const COUNT_LIMIT=128;
    private const SCAN_LIMIT=512;
    private const TOTAL_LIMIT=2097152;
    private string $root;
    private string $directory;
    private AsusShareRead $reader;
    private ?string $catalog;
    public function __construct(?string $root=null,private int $owner=0,?string $catalog=null,?AsusShareRead $reader=null)
    {
        $this->root=$root??AsusDpiStore::optPath('/etc/nfqws2');$this->directory=$this->root.'/blobs';
        $this->reader=$reader??($root===null?NfqwsPlatform::reader($owner):new AsusShareRead($owner));
        try{$this->catalog=$catalog??NfqwsPlatform::sharedFile('blob-catalog.json',__DIR__.'/blob-catalog.json');
            // sharedFile uses logical package paths; the reader pins /opt's resolved mount.
            $alias=NfqwsPlatform::settings()['root'];if($alias!==''&&str_starts_with($this->catalog,$alias.'/')){$base=realpath($alias);$this->catalog=$base===false?null:rtrim($base,'/').substr($this->catalog,strlen($alias));}
        }catch(Throwable $e){$this->catalog=null;}
    }
    private static function name(string $name): bool
    {return strlen($name)<=128&&preg_match('/^[A-Za-z0-9][A-Za-z0-9_.-]*\.bin$/Di',$name)===1;}
    private static function canonicalName(string $name): string
    {
        if($name===''||strlen($name)>512||preg_match('//u',$name)!==1||preg_match('~[/\\\\\x00-\x1f\x7f]~',$name)||$name[0]==='.'||!preg_match('/\.bin$/Di',$name))throw new RuntimeException('invalid_blob');
        if(self::name($name))return $name;
        $stem=trim((string)preg_replace('/[^A-Za-z0-9_.-]+/u','-',substr($name,0,-4)),'-._');
        if($stem==='')$stem='blob';$canonical=substr($stem,0,124).'.bin';
        if(strlen($name)>128&&preg_match('/^[A-Za-z0-9_.-]+$/D',$name))throw new RuntimeException('invalid_blob');
        return $canonical;
    }
    public static function uploadBytes(string $name,string $encoded,string $sha256): string
    {
        self::canonicalName($name);if(!preg_match('/^[a-f0-9]{64}$/D',$sha256))throw new RuntimeException('invalid_blob');
        if(strlen($encoded)>349528)throw new RuntimeException('file_too_large');
        $raw=base64_decode($encoded,true);
        if($raw===false||base64_encode($raw)!==$encoded||$raw==='')throw new RuntimeException('invalid_blob');
        if(strlen($raw)>self::FILE_LIMIT)throw new RuntimeException('file_too_large');
        if(!hash_equals($sha256,hash('sha256',$raw)))throw new RuntimeException('hash_mismatch');return $raw;
    }
    private function metadata(): array
    {
        if($this->catalog===null)return [];
        try{$reader=new AsusShareRead($this->owner);if(!$reader->directory(dirname($this->catalog)))$reader=$this->reader;
            $s=$reader->stat($this->catalog);if(!$s||$s['uid']!==$this->owner||($s['mode']&0022)!==0)return [];
            $v=json_decode($reader->bytes($this->catalog,131072),true,16,JSON_THROW_ON_ERROR);
            if(!is_array($v)||!self::keys($v,['schema_version','files'])||$v['schema_version']!==1||!is_array($v['files'])||!array_is_list($v['files'])||count($v['files'])>self::COUNT_LIMIT)return [];
            foreach($v['files']as $row){if(!is_array($row)||!self::keys($row,['name','sha256','byte_length','format','label'])||!is_string($row['name'])||!self::name($row['name'])||!is_string($row['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$row['sha256'])||!is_int($row['byte_length'])||$row['byte_length']<1||$row['byte_length']>self::FILE_LIMIT||!in_array($row['format'],['tls','quic','stun','other'],true)||!is_array($row['label'])||!self::keys($row['label'],['ru','en']))return [];
                foreach($row['label']as $label)if(!is_string($label)||$label===''||strlen($label)>256||preg_match('//u',$label)!==1||preg_match('/[\x00-\x1f\x7f]/',$label))return [];
            }return $v['files'];
        }catch(Throwable $e){return [];}
    }
    private static function keys(array $v,array $want): bool {$keys=array_keys($v);sort($keys);sort($want);return $keys===$want;}
    private function row(string $name,int $size,?string $hash,string $state,array $catalog): array
    {
        $row=['name'=>$name,'path'=>NfqwsPlatform::translate('/opt/etc/nfqws2/blobs/').$name,'byte_length'=>$size,'sha256'=>$hash,'state'=>$state,'format'=>'other','label'=>null,'bundled'=>false];
        if($state==='available')foreach($catalog as $known)if($known['byte_length']===$size&&$known['sha256']===$hash){$row['format']=$known['format'];$row['label']=$known['label'];$row['bundled']=true;break;}
        return $row;
    }
    private function directory(bool $create=false): bool
    {
        if(!$this->reader->directory($this->root))throw new RuntimeException('resource_unavailable');
        clearstatcache(true,$this->directory);if(@lstat($this->directory)===false){
            if(!$create)return false;$mask=umask(0022);try{$ok=@mkdir($this->directory,0755);}finally{umask($mask);}if(!$ok)throw new RuntimeException('storage_unavailable');
        }
        if(!$this->reader->directory($this->directory))throw new RuntimeException('resource_unavailable');return true;
    }
    public function inventory(): array
    {
        $out=['files'=>[],'skipped'=>0,'scan_truncated'=>false];if(!$this->directory())return $out;
        $handle=@opendir($this->directory);if(!$handle)throw new RuntimeException('resource_unavailable');$count=0;$remaining=self::TOTAL_LIMIT;$catalog=$this->metadata();
        try{while(($name=readdir($handle))!==false){if($name==='.'||$name==='..')continue;
            if(++$count>self::SCAN_LIMIT){$out['scan_truncated']=true;break;}
            if(!self::name($name)){$out['skipped']++;continue;}$path=$this->directory.'/'.$name;$stat=$this->reader->stat($path);
            if(!$stat){$out['skipped']++;continue;}if(count($out['files'])>=self::COUNT_LIMIT){$out['scan_truncated']=true;break;}
            $hash=null;$state='unavailable';$size=$stat['size'];
            if($size===0)$state='unavailable';
            elseif($size>self::FILE_LIMIT)$state='too_large';
            elseif($size>$remaining)$out['scan_truncated']=true;
            else {$limit=min(self::FILE_LIMIT,$remaining);$charged=$limit;
                try{$raw=$this->reader->bytes($path,$limit);$charged=strlen($raw);$size=$charged;if($size>0){$hash=hash('sha256',$raw);$state='available';}}
                catch(RuntimeException $e){}finally{$remaining-=$charged;}}
            $out['files'][]=$this->row($name,$size,$hash,$state,$catalog);
        }}finally{closedir($handle);}
        usort($out['files'],fn($a,$b)=>strcmp($a['name'],$b['name']));return $out;
    }
    private static function same(array $a,array $b,array $fields=['dev','ino','mode','uid','gid','nlink']): bool
    {foreach($fields as $field)if($a[$field]!==$b[$field])return false;return true;}
    /** Pin the resource parent and blob directory across staging and publication. */
    private function pin(): array
    {
        $this->directory(true);$out=[];foreach([$this->root,$this->directory]as $path){clearstatcache(true,$path);$s=@lstat($path);if(!$s||$s['uid']!==$this->owner)throw new RuntimeException('resource_unavailable');$out[$path]=$s;}return $out;
    }
    private function pinned(array $pin): bool
    {
        foreach($pin as $path=>$before){clearstatcache(true,$path);$s=@lstat($path);if(!$s||!self::same($before,$s)||!$this->reader->directory($path))return false;}return true;
    }
    private function existing(string $name,string $sha256,int $size): ?bool
    {
        $path=$this->directory.'/'.$name;clearstatcache(true,$path);if(@lstat($path)===false)return null;
        $stat=$this->reader->stat($path);if(!$stat)throw new RuntimeException('source_changed');
        if($stat['size']!==$size)return false;return hash_equals($sha256,hash('sha256',$this->reader->bytes($path,self::FILE_LIMIT)));
    }
    private function cleanStages(array $pin): void
    {
        $h=@opendir($this->directory);if(!$h)throw new RuntimeException('resource_unavailable');$count=0;
        try{while(($name=readdir($h))!==false){if($name==='.'||$name==='..')continue;if(++$count>self::SCAN_LIMIT)throw new RuntimeException('output_limit');
            if(!preg_match('/^\.blob-upload-([A-Za-z0-9][A-Za-z0-9_.-]*\.bin)\.([a-f0-9]{32})$/Di',$name,$m)||!self::name($m[1]))continue;
            $path=$this->directory.'/'.$name;clearstatcache(true,$path);$s=@lstat($path);$target=$this->directory.'/'.$m[1];clearstatcache(true,$target);$t=@lstat($target);
            if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||!in_array($s['mode']&0777,[0600,0644],true)||!in_array($s['nlink'],[1,2],true)||$s['size']>self::FILE_LIMIT||($s['nlink']===2&&(!$t||!self::same($s,$t)))||!$this->pinned($pin))throw new RuntimeException('source_changed');
            if(!@unlink($path))throw new RuntimeException('storage_unavailable');
        }}finally{closedir($h);}
    }
    public function upload(string $name,string $encoded,string $sha256): array
    {
        $raw=self::uploadBytes($name,$encoded,$sha256);$name=self::canonicalName($name);$size=strlen($raw);$pin=$this->pin();$this->cleanStages($pin);$chosen=null;
        foreach([null,12,64]as $length){$candidate=$length===null?$name:substr(substr($name,0,-4),0,123-$length).'-'.substr($sha256,0,$length).'.bin';
            $exists=$this->existing($candidate,$sha256,$size);if($exists===true){if(!$this->pinned($pin))throw new RuntimeException('source_changed');return $this->row($candidate,$size,$sha256,'available',$this->metadata());}
            if($exists===null){$chosen=$candidate;break;}
        }
        if($chosen===null)throw new RuntimeException('source_changed');if(!$this->pinned($pin))throw new RuntimeException('source_changed');
        $path=$this->directory.'/'.$chosen;$tmp=$this->directory.'/.blob-upload-'.$chosen.'.'.bin2hex(random_bytes(16));$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('insufficient_space');$opened=fstat($f);
        try{clearstatcache(true,$tmp);$named=@lstat($tmp);if(!$opened||!$named||!self::same($opened,$named)||$opened['uid']!==$this->owner||$opened['nlink']!==1||!$this->pinned($pin))throw new RuntimeException('source_changed');
            $offset=0;while($offset<$size){$written=@fwrite($f,substr($raw,$offset));if(!$written)throw new RuntimeException('insufficient_space');$offset+=$written;}
            if(!@fflush($f)||(function_exists('fsync')&&!@fsync($f)))throw new RuntimeException('insufficient_space');
            if(!$this->pinned($pin)||!@chmod($tmp,0644))throw new RuntimeException('storage_unavailable');$done=fstat($f);clearstatcache(true,$tmp);$named=@lstat($tmp);
            if(!$done||!$named||!self::same($done,$named)||$done['ino']!==$opened['ino']||$done['dev']!==$opened['dev']||$done['size']!==$size||($done['mode']&0777)!==0644||$done['nlink']!==1||!$this->pinned($pin))throw new RuntimeException('source_changed');
            // Only our fresh stage is linked, and link() cannot replace any name.
            if(!@link($tmp,$path))throw new RuntimeException('source_changed');
            clearstatcache(true,$path);$published=@lstat($path);if(!$published||!self::same($done,$published,['dev','ino','mode','uid','gid'])||$published['nlink']!==2||!$this->pinned($pin))throw new RuntimeException('source_changed');
            if(!@unlink($tmp))throw new RuntimeException('storage_unavailable');clearstatcache(true,$path);$published=$this->reader->stat($path);
            if(!$published||$published['ino']!==$done['ino']||$published['dev']!==$done['dev']||!$this->pinned($pin))throw new RuntimeException('source_changed');
            return $this->row($chosen,$size,$sha256,'available',$this->metadata());
        }finally{fclose($f);clearstatcache(true,$tmp);$left=@lstat($tmp);if($left&&$opened&&$left['dev']===$opened['dev']&&$left['ino']===$opened['ino']&&$this->pinned($pin))@unlink($tmp);}
    }
}
