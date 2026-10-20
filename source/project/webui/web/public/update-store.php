<?php
require_once __DIR__.'/dpi-store.php';

/** Private transaction journal. Paths come from trusted code, never HTTP fields. */
final class AsusUpdateStore
{
    public const TERMINAL=['succeeded','failed','interrupted'];
    private string $root;
    private bool $locked=false;
    public function __construct(?string $root=null,private int $owner=0)
    {
        $this->root=$root??AsusDpiStore::optPath('/var/lib/nfqws2-asus/updates');
        self::noLinks($this->root);
        $missing=[];for($p=dirname($this->root);!is_dir($p);$p=dirname($p))$missing[]=$p;
        foreach(array_reverse($missing) as $p)if(!@mkdir($p,0755)&&!is_dir($p))throw new RuntimeException('invalid_state');
        $this->directory('');$this->directory('operations');
    }
    /** Canonicalize only the supported Entware /opt alias, not child symlinks. */
    public static function installed(string $relative): string
    {
        if(!preg_match('~^[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*$~D',$relative)||in_array('..',explode('/',$relative),true)||in_array('.',explode('/',$relative),true))throw new RuntimeException('invalid_state');
        return dirname(AsusDpiStore::optPath('/var')).'/'.$relative;
    }
    public static function noLinks(string $path): void
    {for($p=$path;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');}
    public function path(string $name=''): string
    {
        if($name!==''&&(!preg_match('~^[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*$~D',$name)||in_array('..',explode('/',$name),true)||in_array('.',explode('/',$name),true)))throw new RuntimeException('invalid_request');
        $p=$this->root.($name===''?'':'/'.$name);self::noLinks($p);return $p;
    }
    public function directory(string $name): string
    {
        $p=$this->path($name);$mask=umask(0077);try{if(!is_dir($p)&&!@mkdir($p,0700)&&!is_dir($p))throw new RuntimeException('invalid_state');}finally{umask($mask);}
        clearstatcache(true,$p);$s=@lstat($p);
        if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');return $p;
    }
    private function regular(string $path,int $max): ?array
    {
        clearstatcache(true,$path);$s=@lstat($path);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>$max)throw new RuntimeException('invalid_state');return $s;
    }
    public function readFile(string $name,int $max=131072): ?string
    {
        $p=$this->path($name);$s=$this->regular($p,$max);if(!$s)return null;$f=@fopen($p,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$a=fstat($f);if($s['ino']!==$a['ino']||$s['dev']!==$a['dev'])throw new RuntimeException('invalid_state');$v=stream_get_contents($f,$max+1);if(!is_string($v)||strlen($v)>$max)throw new RuntimeException('invalid_state');return $v;}finally{fclose($f);}
    }
    public function writeFile(string $name,string $raw): void
    {
        if(strlen($raw)>131072)throw new RuntimeException('output_limit');$p=$this->path($name);$this->regular($p,131072);
        $dir=dirname($p);$s=@lstat($dir);if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $tmp=$dir.'/.write-'.bin2hex(random_bytes(12));$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('invalid_state');
        try{if(!chmod($tmp,0600)||fwrite($f,$raw)!==strlen($raw)||!fflush($f))throw new RuntimeException('invalid_state');fclose($f);$f=null;if(!rename($tmp,$p))throw new RuntimeException('invalid_state');}finally{if(is_resource($f))fclose($f);@unlink($tmp);}
    }
    public function withLock(callable $fn): mixed
    {
        if($this->locked)return $fn();$p=$this->path('control.lock');$s=$this->regular($p,0);$mask=umask(0077);
        try{$f=@fopen($p,$s?'r+be':'x+be');}finally{umask($mask);}if(!$f){$this->regular($p,0);$f=@fopen($p,'r+be');}if(!$f)throw new RuntimeException('invalid_state');
        try{$a=fstat($f);$s=$this->regular($p,0);if(!$s||$a['ino']!==$s['ino']||$a['dev']!==$s['dev'])throw new RuntimeException('invalid_state');if(!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');$this->locked=true;return $fn();}finally{$this->locked=false;flock($f,LOCK_UN);fclose($f);}
    }
    /** Trusted workers tolerate brief HTTP polling without replaying callbacks. */
    public function withRetryLock(callable $fn): mixed
    {
        $deadline=self::uptime()+1;
        do{$entered=false;try{return $this->withLock(function()use($fn,&$entered){$entered=true;return $fn();});}
            catch(RuntimeException $e){if($entered||$e->getMessage()!=='busy'||self::uptime()>=$deadline)throw $e;usleep(10000);}
        }while(true);
    }
    /** Independent leases keep long work out of the short journal lock. */
    public function lease(string $name,bool $shared=false)
    {
        if(!in_array($name,['apply.lock','check.lock'],true)&&!preg_match('~^operations/[a-f0-9]{32}/(?:work|critical)\.lock$~D',$name))throw new RuntimeException('invalid_request');
        $p=$this->path($name);$s=$this->regular($p,0);$mask=umask(0077);try{$f=@fopen($p,$s?'r+be':'x+be');}finally{umask($mask);}if(!$f){$this->regular($p,0);$f=@fopen($p,'r+be');}if(!$f)throw new RuntimeException('invalid_state');
        $a=fstat($f);$s=$this->regular($p,0);if(!$s||$s['ino']!==$a['ino']||$s['dev']!==$a['dev']){fclose($f);throw new RuntimeException('invalid_state');}
        if(!flock($f,($shared?LOCK_SH:LOCK_EX)|LOCK_NB)){fclose($f);throw new RuntimeException('busy');}return $f;
    }
    public function withOperationLock(string $id,callable $fn): mixed
    {self::id($id);$f=$this->lease('operations/'.$id.'/work.lock');try{return $fn();}finally{flock($f,LOCK_UN);fclose($f);}}
    public static function boot(): string {return trim(file_get_contents('/proc/sys/kernel/random/boot_id'));}
    public static function uptime(): float {return (float)explode(' ',file_get_contents('/proc/uptime'))[0];}
    private static function id(string $id): void {if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');}
    private function db(): array
    {
        $raw=$this->readFile('operations.json');if($raw===null)return ['operations'=>[]];
        try{$db=json_decode($raw,true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(!is_array($db)||array_keys($db)!==['operations']||!is_array($db['operations'])||count($db['operations'])>3)throw new RuntimeException('invalid_state');
        foreach($db['operations'] as $id=>$job)if(!preg_match('/^[a-f0-9]{32}$/D',(string)$id)||!is_array($job)||($job['id']??null)!==$id||!in_array($job['state']??null,array_merge(['preparing','prepared','applying'],self::TERMINAL),true))throw new RuntimeException('invalid_state');return $db;
    }
    private function save(array $db): void {$this->writeFile('operations.json',json_encode($db,JSON_THROW_ON_ERROR));}
    private function rotate(array &$db): void
    {
        $terminal=array_filter($db['operations'],fn($j)=>in_array($j['state'],self::TERMINAL,true));
        while(count($terminal)>2){$id=array_key_first($terminal);$this->clean($id);unset($terminal[$id],$db['operations'][$id]);}
    }
    private function clean(string $id): void
    {
        $dir=$this->path('operations/'.$id);if(!is_dir($dir))return;$this->directory('operations/'.$id);
        // Unknown operator files and links are deliberately left alone.
        $this->pruneTree('operations/'.$id.'/backup','snapshot.json');
        $partial=$this->readFile('operations/'.$id.'/runtime/staging.json')!==null;
        $this->pruneTree('operations/'.$id.'/runtime',$partial?'staging.json':'closure.json',$partial);
        foreach(['package.ipk','snapshot.json','candidate.json','manifest.json','manifest.sig','apply.json','work.lock','critical.lock','guard.json','cancel.json','boundary.json','preflight-error.json','network.json'] as $name){$p=$dir.'/'.$name;$s=@lstat($p);if($s&&($s['mode']&0170000)===0100000&&$s['uid']===$this->owner&&$s['nlink']===1)@unlink($p);}
        @rmdir($dir);
    }
    private function pruneTree(string $name,string $index,bool $incomplete=false): void
    {
        $dir=$this->path($name);if(!is_dir($dir))return;$this->directory($name);$raw=$this->readFile($name.'/'.$index);if($raw===null)return;
        try{$v=json_decode($raw,true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(!is_array($v['files']??null)||count($v['files'])>512)throw new RuntimeException('invalid_state');$dirs=[$dir];
        foreach($v['files'] as $file=>$meta){if(!is_string($file)||!preg_match('~^[a-zA-Z0-9_+.-]+(?:/[a-zA-Z0-9_+.-]+)*$~D',$file)||in_array('..',explode('/',$file),true)||in_array('.',explode('/',$file),true)||!is_array($meta)||!is_int($meta['mode']??null)||!is_int($meta['size']??null)||$meta['size']<0||!preg_match('/^[a-f0-9]{64}$/D',$meta['sha256']??''))throw new RuntimeException('invalid_state');
            $p=$dir.'/'.$file;$safe=true;for($parent=$p;$parent!==$dir;$parent=dirname($parent))if(is_link($parent)){$safe=false;break;}if(!$safe)continue;
            $s=@lstat($p);if($s&&($s['mode']&0170000)===0100000&&$s['uid']===$this->owner&&$s['nlink']===1){
                $complete=($s['mode']&0777)===$meta['mode']&&$s['size']===$meta['size']&&hash_file('sha256',$p)===$meta['sha256'];
                $partial=$incomplete&&in_array($s['mode']&0777,[0600,$meta['mode']],true)&&$s['size']<=$meta['size'];
                if($complete||$partial)@unlink($p);
            }
            for($parent=dirname($p);$parent!==$dir;$parent=dirname($parent))$dirs[]=$parent;
        }
        @unlink($dir.'/'.$index);if($incomplete){$s=@lstat($dir.'/closure.json');if($s&&($s['mode']&0170000)===0100000&&$s['uid']===$this->owner&&$s['nlink']===1&&($s['mode']&0777)===0600&&$s['size']<=131072)@unlink($dir.'/closure.json');}
        $dirs=array_values(array_unique($dirs));usort($dirs,fn($a,$b)=>strlen($b)<=>strlen($a));foreach($dirs as $p){$s=@lstat($p);if($s&&($s['mode']&0170000)===0040000&&$s['uid']===$this->owner)@rmdir($p);}
    }
    public function reserve(string $revision,string $requestId,array $candidate): array
    {
        self::id($requestId);if(!preg_match('/^[a-f0-9]{64}$/D',$revision)||($candidate['revision']??null)!==$revision)throw new RuntimeException('invalid_request');
        return $this->withLock(function()use($revision,$requestId,$candidate){$db=$this->db();
            foreach($db['operations'] as $job)if($job['request_id']===$requestId){if($job['revision']!==$revision)throw new RuntimeException('request_conflict');return $job;}
            foreach($db['operations'] as $job)if(!in_array($job['state'],self::TERMINAL,true))throw new RuntimeException('busy');
            $id=bin2hex(random_bytes(16));$this->directory('operations/'.$id);$this->writeFile('operations/'.$id.'/candidate.json',json_encode($candidate,JSON_THROW_ON_ERROR));
            $job=['id'=>$id,'request_id'=>$requestId,'revision'=>$revision,'state'=>'preparing','code'=>null,'boot_id'=>self::boot(),'created_at'=>time(),'created_uptime'=>self::uptime(),'package_version'=>$candidate['package_version']];
            $db['operations'][$id]=$job;$this->rotate($db);$this->save($db);return $job;
        });
    }
    public function update(string $id,array $patch): array
    {
        self::id($id);return $this->withRetryLock(function()use($id,$patch){$db=$this->db();if(!isset($db['operations'][$id]))throw new RuntimeException('missing_operation');$job=$db['operations'][$id];
            $allowed=['state','code','identity','prepared_uptime','apply_request_id','intent','installed_version','core_state','settings_verified','finished_at','phase','runtime_digest'];
            foreach($patch as $k=>$_)if(!in_array($k,$allowed,true))throw new RuntimeException('invalid_state');
            $next=$patch['state']??$job['state'];$transitions=['preparing'=>['preparing','prepared','failed','interrupted'],'prepared'=>['prepared','applying','failed','interrupted'],'applying'=>['applying','succeeded','failed','interrupted']];
            if(!in_array($next,$transitions[$job['state']]??[],true))throw new RuntimeException('invalid_transition');
            if(in_array($next,self::TERMINAL,true))$patch['finished_at']=time();$db['operations'][$id]=array_replace($job,$patch);$result=$db['operations'][$id];$this->rotate($db);$this->save($db);return $result;
        });
    }
    public function readOperation(string $id): array
    {self::id($id);return $this->withRetryLock(function()use($id){$db=$this->db();if(!isset($db['operations'][$id]))throw new RuntimeException('missing_operation');return $db['operations'][$id];});}
    public function claimApply(string $id,string $revision,string $requestId): array
    {
        self::id($id);self::id($requestId);if(!preg_match('/^[a-f0-9]{64}$/D',$revision))throw new RuntimeException('invalid_request');
        return $this->withLock(function()use($id,$revision,$requestId){$db=$this->db();if(!isset($db['operations'][$id]))throw new RuntimeException('missing_operation');$job=$db['operations'][$id];
            foreach($db['operations'] as $other)if(($other['apply_request_id']??null)===$requestId){
                if($other['id']!==$id||$other['revision']!==$revision)throw new RuntimeException('request_conflict');return ['operation'=>$other,'launch'=>false];
            }
            if($job['revision']!==$revision)throw new RuntimeException('stale_revision');
            if($job['state']!=='prepared'||$job['boot_id']!==self::boot()||!preg_match('/^[a-f0-9]{64}$/D',$job['runtime_digest']??''))throw new RuntimeException('invalid_state');
            if($this->readFile('operations/'.$id.'/cancel.json',1024)!==null)throw new RuntimeException('interrupted');
            $job=array_replace($job,['state'=>'applying','phase'=>'queued','apply_request_id'=>$requestId,'apply_uptime'=>self::uptime(),'identity'=>null]);
            $db['operations'][$id]=$job;$this->save($db);return ['operation'=>$job,'launch'=>true];
        });
    }
    public function claimPrepare(string $id): bool
    {
        self::id($id);return $this->withLock(function()use($id){$db=$this->db();if(!isset($db['operations'][$id]))throw new RuntimeException('missing_operation');$job=$db['operations'][$id];
            if($job['state']!=='preparing'||isset($job['prepare_launch_uptime']))return false;
            if($job['boot_id']!==self::boot())throw new RuntimeException('interrupted');$db['operations'][$id]['prepare_launch_uptime']=self::uptime();$this->save($db);return true;
        });
    }
    public function status(): array
    {return $this->withLock(function(){$db=$this->db();$active=null;$history=[];foreach($db['operations'] as $job)if(in_array($job['state'],self::TERMINAL,true))$history[]=$job;else $active=$job;if($this->readFile('operations.json')===null)$this->save($db);return ['active'=>$active,'history'=>array_reverse($history)];});}
    public function reconcile(string $boot,float $uptime): void
    {$this->withLock(function()use($boot,$uptime){$db=$this->db();$before=$db;foreach($db['operations'] as &$job)if(!in_array($job['state'],self::TERMINAL,true)&&($job['boot_id']!==$boot||$uptime<$job['created_uptime'])){$job['state']='interrupted';$job['code']='interrupted';$job['finished_at']=time();}unset($job);$this->rotate($db);if($db!==$before)$this->save($db);});}
}
