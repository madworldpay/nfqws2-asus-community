<?php
require_once __DIR__.'/dpi-store.php';
/** Private copies of original CLI reports; no executable or browser paths. */
final class AsusDpiSavedStore
{
    private const MAX_FILE=1048576;
    private const MAX_TOTAL=20971520;
    private string $root;
    public function __construct(?string $root=null,private ?string $sourceDir=null,private int $owner=0)
    {
        $this->root=$root??AsusDpiStore::optPath('/var/lib/nfqws2-asus/dpi-saved');
        self::noLinks($this->root);
        $parents=[];
        for($p=dirname($this->root);!is_dir($p);$p=dirname($p))$parents[]=$p;
        foreach(array_reverse($parents) as $p)if(!@mkdir($p,0755)&&!is_dir($p))throw new RuntimeException('invalid_state');
        if(!is_dir($this->root)) {
            $mask=umask(0077);
            try {if(!@mkdir($this->root,0700)&&!is_dir($this->root))throw new RuntimeException('invalid_state');}
            finally {umask($mask);}
        }
        clearstatcache(true,$this->root);$s=lstat($this->root);
        if(($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
    }
    private static function noLinks(string $path): void
    {
        if($path===''||$path[0]!=='/'||str_contains($path,"\0"))throw new RuntimeException('invalid_state');
        for($p=$path;$p!=='/';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');
    }
    private static function name(string $name): bool
    {return preg_match('/^dpi_detector_results-[0-9]{8}-[0-9]{6}\.txt$/D',$name)===1;}
    private function stat(string $path,int $max,bool $private=true): ?array
    {
        clearstatcache(true,$path);$s=@lstat($path);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||$s['size']<0||$s['size']>$max||
            ($private?($s['mode']&0777)!==0600:($s['mode']&0022)!==0))throw new RuntimeException('invalid_state');
        return $s;
    }
    private function readFile(string $path,int $max,bool $private=true): ?array
    {
        $before=$this->stat($path,$max,$private);if(!$before)return null;
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try {
            $opened=fstat($f);
            if($opened['ino']!==$before['ino']||$opened['dev']!==$before['dev'])throw new RuntimeException('source_changed');
            $raw=stream_get_contents($f,$max+1);$after=fstat($f);
            if(!is_string($raw)||strlen($raw)>$max||strlen($raw)!==$opened['size']||$opened['size']!==$after['size']||$opened['mtime']!==$after['mtime']||$opened['ctime']!==$after['ctime'])throw new RuntimeException('source_changed');
        } finally {fclose($f);}
        $end=$this->stat($path,$max,$private);
        if(!$end||$end['ino']!==$before['ino']||$end['dev']!==$before['dev']||$end['size']!==$after['size']||$end['mtime']!==$after['mtime']||$end['ctime']!==$after['ctime'])throw new RuntimeException('source_changed');
        return ['raw'=>$raw,'stat'=>$end];
    }
    private function write(string $name,string $raw): void
    {
        $dest=$this->root.'/'.$name;$this->stat($dest,max(self::MAX_FILE,131072));
        $tmp=$this->root.'/.write-'.bin2hex(random_bytes(12));$mask=umask(0077);
        try {$f=@fopen($tmp,'xb');}finally {umask($mask);}
        if(!$f)throw new RuntimeException('insufficient_space');
        try {
            if(!chmod($tmp,0600)||@fwrite($f,$raw)!==strlen($raw)||!@fflush($f))throw new RuntimeException('insufficient_space');
            fclose($f);$f=null;
            if(!@rename($tmp,$dest))throw new RuntimeException('invalid_state');
        }finally {if(is_resource($f))fclose($f);@unlink($tmp);}
    }
    private function cleanupOrphans(array $db): void
    {
        $dir=opendir($this->root);$count=0;
        try {while(($name=readdir($dir))!==false) {
            if($name==='.'||$name==='..')continue;
            if(++$count>128)throw new RuntimeException('invalid_state');
            $orphan=preg_match('/^([a-f0-9]{32})\.txt$/D',$name,$m)&&!isset($db['reports'][$m[1]]);
            if($orphan||preg_match('/^\.write-[a-f0-9]{24}$/D',$name)) {
                $path=$this->root.'/'.$name;$this->stat($path,self::MAX_FILE);
                if(!@unlink($path))throw new RuntimeException('invalid_state');
            }
        }}finally {closedir($dir);}
    }
    /** The index commit decides whether an interrupted deletion rolls back. */
    private function recoverDelete(array $db): void
    {
        $journal=$this->readFile($this->root.'/delete.json',8192);if($journal===null)return;
        $j=json_decode($journal['raw'],true,16,JSON_THROW_ON_ERROR);
        if(!is_array($j)||array_keys($j)!==['version','id','report','source_present']||$j['version']!==1||!is_bool($j['source_present']))throw new RuntimeException('invalid_state');
        $id=$j['id'];self::id($id);$r=$j['report'];
        if(!is_array($r)||($r['id']??null)!==$id||!self::name($r['filename']??'')||!is_string($r['source']??null)||basename($r['source'])!==$r['filename']||!str_starts_with($r['source'],'/')||!preg_match('/^[a-f0-9]{64}$/D',$r['sha256']??'')||!is_int($r['source_ino']??null)||!is_int($r['source_dev']??null))throw new RuntimeException('invalid_state');
        $rollback=isset($db['reports'][$id]);if($rollback&&$db['reports'][$id]!==$r)throw new RuntimeException('invalid_state');
        foreach([[$r['source'],dirname($r['source']).'/.nfqws2-deleted-'.$id,false],[$this->root.'/'.$id.'.txt',$this->root.'/.deleted-'.$id.'.txt',true]] as [$from,$to,$private]) {
            self::noLinks($from);self::noLinks($to);$moved=$this->readFile($to,self::MAX_FILE,$private);
            if($moved===null)continue;
            if(!$rollback&&(!hash_equals($r['sha256'],hash('sha256',$moved['raw']))||(!$private&&($moved['stat']['ino']!==$r['source_ino']||$moved['stat']['dev']!==$r['source_dev']))))throw new RuntimeException('source_changed');
            // link() cannot overwrite a newly saved original during rollback.
            if($rollback&&!@link($to,$from))throw new RuntimeException('source_changed');
            if(!@unlink($to))throw new RuntimeException('invalid_state');
        }
        if(!@unlink($this->root.'/delete.json'))throw new RuntimeException('invalid_state');
    }
    private function locked(callable $fn): mixed
    {
        $path=$this->root.'/control.lock';$before=$this->stat($path,0);$mask=umask(0077);
        try {$f=@fopen($path,$before?'r+b':'x+b');}finally {umask($mask);}
        if(!$f)$f=@fopen($path,'r+b');if(!$f)throw new RuntimeException('invalid_state');
        try {
            $s=$this->stat($path,0);$a=fstat($f);
            if(!$s||$s['ino']!==$a['ino']||$s['dev']!==$a['dev']||!flock($f,LOCK_EX))throw new RuntimeException('invalid_state');
            $saved=$this->readFile($this->root.'/index.json',131072);
            $db=$saved===null?['version'=>1,'reports'=>[]]:json_decode($saved['raw'],true,32,JSON_THROW_ON_ERROR);
            if(!is_array($db)||array_keys($db)!==['version','reports']||$db['version']!==1||!is_array($db['reports'])||count($db['reports'])>20)throw new RuntimeException('invalid_state');
            foreach($db['reports'] as $id=>$r) {
                if(!preg_match('/^[a-f0-9]{32}$/D',(string)$id)||!is_array($r)||($r['id']??null)!==$id||!self::name($r['filename']??'')||
                    !is_string($r['source']??null)||basename($r['source'])!==$r['filename']||!preg_match('/^[a-f0-9]{64}$/D',$r['sha256']??'')||
                    !is_int($r['bytes']??null)||$r['bytes']<1||$r['bytes']>self::MAX_FILE||!is_int($r['source_ino']??null)||!is_int($r['source_dev']??null))throw new RuntimeException('invalid_state');
            }
            $this->recoverDelete($db);$this->cleanupOrphans($db);$before=$db;$committed=false;
            try {
                $result=$fn($db);$this->write('index.json',json_encode($db,JSON_THROW_ON_ERROR));$committed=true;
                $this->recoverDelete($db);return $result;
            }catch(Throwable $e) {
                if(!$committed){$this->recoverDelete($before);$this->cleanupOrphans($before);}
                throw $e;
            }
        }catch(JsonException $e){throw new RuntimeException('invalid_state');}
        finally {flock($f,LOCK_UN);fclose($f);}
    }
    private static function listing(array $db,string $code='ready',int $skipped=0,bool $truncated=false): array
    {
        $reports=[];
        foreach($db['reports'] as $r)$reports[]=['id'=>$r['id'],'filename'=>$r['filename'],'bytes'=>$r['bytes'],'sha256'=>$r['sha256']];
        return ['reports'=>$reports,'code'=>$code,'skipped'=>$skipped,'scan_truncated'=>$truncated];
    }
    public function list(): array
    {return $this->locked(fn(&$db)=>self::listing($db));}
    public function refresh(): array
    {
        return $this->locked(function(&$db){
            try {
                if($this->sourceDir===null){require_once __DIR__.'/dpi-install.php';$this->sourceDir=dirname((new AsusDpiInstaller())->binary());}
                self::noLinks($this->sourceDir);
                $dir=@opendir($this->sourceDir);if(!$dir)return self::listing($db,'source_unavailable');
            }catch(Throwable $e){return self::listing($db,'source_unavailable');}
            $names=[];$entries=0;$truncated=false;
            try {while(($name=readdir($dir))!==false){if($name==='.'||$name==='..')continue;if(++$entries>256){$truncated=true;break;}if(self::name($name))$names[]=$name;}}
            finally {closedir($dir);}
            sort($names,SORT_STRING);$skipped=0;$code=$truncated?'scan_truncated':'ready';
            $total=array_sum(array_column($db['reports'],'bytes'));
            foreach($names as $name) {
                $path=$this->sourceDir.'/'.$name;
                try {
                    $src=$this->readFile($path,self::MAX_FILE,false);
                    if(!$src||$src['raw']===''||preg_match('//u',$src['raw'])!==1)throw new RuntimeException('invalid_state');
                    $again=$this->readFile($path,self::MAX_FILE,false);
                    if(!$again||$again['raw']!==$src['raw']||$again['stat']['ino']!==$src['stat']['ino']||$again['stat']['dev']!==$src['stat']['dev'])throw new RuntimeException('source_changed');
                    $hash=hash('sha256',$src['raw']);$same=null;
                    foreach($db['reports'] as $id=>$r)if($r['source']===$path&&$r['sha256']===$hash){$same=$id;break;}
                    if($same!==null){$db['reports'][$same]['source_ino']=$src['stat']['ino'];$db['reports'][$same]['source_dev']=$src['stat']['dev'];continue;}
                    $bytes=strlen($src['raw']);
                    if(count($db['reports'])>=20||$total+$bytes>self::MAX_TOTAL){$code='limit_reached';continue;}
                    $free=@disk_free_space($this->root);
                    if($free===false||$free<$bytes+262144){$code='insufficient_space';continue;}
                    $id=bin2hex(random_bytes(16));$this->write($id.'.txt',$src['raw']);
                    $db['reports'][$id]=['id'=>$id,'filename'=>$name,'sha256'=>$hash,'bytes'=>$bytes,'source'=>$path,'source_ino'=>$src['stat']['ino'],'source_dev'=>$src['stat']['dev']];$total+=$bytes;
                }catch(Throwable $e){$skipped++;}
            }
            return self::listing($db,$code,$skipped,$truncated);
        });
    }
    private static function id(string $id): void
    {if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');}
    public function read(string $id): array
    {
        self::id($id);
        return $this->locked(function(&$db)use($id){
            $r=$db['reports'][$id]??null;if(!$r)throw new RuntimeException('result_unavailable');
            $v=$this->readFile($this->root.'/'.$id.'.txt',self::MAX_FILE);
            if(!$v||strlen($v['raw'])!==$r['bytes']||!hash_equals($r['sha256'],hash('sha256',$v['raw'])))throw new RuntimeException('invalid_state');
            return ['raw'=>$v['raw'],'sha256'=>$r['sha256'],'filename'=>$r['filename']];
        });
    }
    public function delete(string $id): void
    {
        self::id($id);
        $this->locked(function(&$db)use($id){
            $r=$db['reports'][$id]??null;if(!$r)throw new RuntimeException('result_unavailable');
            try {
                self::noLinks($r['source']);$s=$this->readFile($r['source'],self::MAX_FILE,false);
                if($s&&($s['stat']['ino']!==$r['source_ino']||$s['stat']['dev']!==$r['source_dev']||!hash_equals($r['sha256'],hash('sha256',$s['raw']))))throw new RuntimeException('source_changed');
            }catch(Throwable $e){throw new RuntimeException('source_changed');}
            $sourceTo=dirname($r['source']).'/.nfqws2-deleted-'.$id;$snapshotTo=$this->root.'/.deleted-'.$id.'.txt';
            if(file_exists($sourceTo)||is_link($sourceTo)||file_exists($snapshotTo)||is_link($snapshotTo))throw new RuntimeException('invalid_state');
            $this->write('delete.json',json_encode(['version'=>1,'id'=>$id,'report'=>$r,'source_present'=>$s!==null],JSON_THROW_ON_ERROR));
            if($s) {
                if(!@rename($r['source'],$sourceTo))throw new RuntimeException('invalid_state');
                $moved=$this->readFile($sourceTo,self::MAX_FILE,false);
                if(!$moved||$moved['stat']['ino']!==$r['source_ino']||$moved['stat']['dev']!==$r['source_dev']||!hash_equals($r['sha256'],hash('sha256',$moved['raw'])))throw new RuntimeException('source_changed');
            }
            $p=$this->root.'/'.$id.'.txt';
            if($this->stat($p,self::MAX_FILE)===null||!@rename($p,$snapshotTo))throw new RuntimeException('invalid_state');
            unset($db['reports'][$id]);
        });
    }
}
