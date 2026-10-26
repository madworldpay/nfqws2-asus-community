<?php
require_once __DIR__.'/support-json-schema.php';
require_once __DIR__.'/dpi-options.php';
require_once __DIR__.'/platform.php';
/** Root-private, lock-serialized state. No browser-supplied filesystem path. */
final class AsusDpiStore
{
    private const TERMINAL=['completed','partial','cancelled','timed_out','failed','interrupted'];
    private string $root;
    /** Entware's firmware-owned /opt mount alias is expected. Resolve that one
     * trusted boundary, then reject symlinks in all managed descendants. */
    public static function optPath(string $suffix,string $alias='/opt'): string
    {
        if($alias==='/opt'&&NfqwsPlatform::native())return NfqwsPlatform::translate('/opt'.$suffix);
        $base=realpath($alias);
        if($base===false||!is_dir($base)||!preg_match('~^/[a-z0-9/-]+$~D',$suffix))throw new RuntimeException('invalid_state');
        return rtrim($base,'/').$suffix;
    }
    public function __construct(?string $root=null,private int $owner=0)
    {
        $this->root=$root??self::optPath('/var/lib/nfqws2-asus/dpi-detector');
        for($p=$this->root;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');
        // Do not create shared Entware ancestors (e.g. var/lib) as 0700.
        // Existing directories retain their modes; only our state is private.
        $missing=[];
        for($p=dirname($this->root);!is_dir($p);$p=dirname($p))$missing[]=$p;
        foreach(array_reverse($missing) as $p){
            if(@mkdir($p,0755)){if(!chmod($p,0755))throw new RuntimeException('invalid_state');}
            elseif(!is_dir($p)||is_link($p))throw new RuntimeException('invalid_state');
        }
        if(!is_dir($this->root)&&!@mkdir($this->root,0700)&&!is_dir($this->root))throw new RuntimeException('invalid_state');
        clearstatcache(true,$this->root);
        $s=lstat($this->root);
        if(($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
    }
    private function regular(string $path,int $max): ?array
    {
        clearstatcache(true,$path);$s=@lstat($path);
        if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>$max)throw new RuntimeException('invalid_state');
        return $s;
    }
    private function read(string $name,int $max): ?string
    {
        $path=$this->root.'/'.$name;$s=$this->regular($path,$max);if(!$s)return null;
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try {$actual=fstat($f);if($s['ino']!==$actual['ino']||$s['dev']!==$actual['dev'])throw new RuntimeException('invalid_state');
            $raw=stream_get_contents($f,$max+1);if(!is_string($raw)||strlen($raw)>$max)throw new RuntimeException('invalid_state');return $raw;
        } finally {fclose($f);}
    }
    private function write(string $name,string $raw): void
    {
        $path=$this->root.'/'.$name;$this->regular($path,1048576);
        if(strlen($raw)>1048576)throw new RuntimeException('output_limit');
        $tmp=$this->root.'/.write-'.bin2hex(random_bytes(12));$mask=umask(0077);
        try{$f=@fopen($tmp,'xb');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('invalid_state');
        try {
            if(!chmod($tmp,0600)||fwrite($f,$raw)!==strlen($raw)||!fflush($f))throw new RuntimeException('invalid_state');
            fclose($f);$f=null;if(!@rename($tmp,$path))throw new RuntimeException('invalid_state');
        } finally {if(is_resource($f))fclose($f);@unlink($tmp);}
    }
    private function locked(callable $fn): mixed
    {
        $path=$this->root.'/control.lock';$before=$this->regular($path,0);
        $f=@fopen($path,$before?'r+b':'x+b');
        if(!$f) { $this->regular($path,0);$f=@fopen($path,'r+b'); }
        if(!$f)throw new RuntimeException('invalid_state');
        try {
            if(!$before&&!chmod($path,0600))throw new RuntimeException('invalid_state');
            $actual=fstat($f);$s=$this->regular($path,0);
            if(!$s||$s['ino']!==$actual['ino']||$s['dev']!==$actual['dev']||!flock($f,LOCK_EX))throw new RuntimeException('invalid_state');
            // No writer can be live while this lock is held; reclaim only our private atomic remnants.
            foreach(glob($this->root.'/.write-*')?:[] as $orphan)if(preg_match('/^\.write-[a-f0-9]{24}$/D',basename($orphan))){$this->regular($orphan,1048576);if(!@unlink($orphan))throw new RuntimeException('invalid_state');}
            $raw=$this->read('jobs.json',131072);$db=$raw===null?['jobs'=>[]]:json_decode($raw,true,32,JSON_THROW_ON_ERROR);
            if(!is_array($db)||array_keys($db)!==['jobs']||!is_array($db['jobs'])||count($db['jobs'])>3)throw new RuntimeException('invalid_state');
            foreach($db['jobs'] as $id=>$job)if(!preg_match('/^[a-f0-9]{32}$/D',(string)$id)||!is_array($job)||($job['id']??null)!==$id||!in_array($job['state']??null,array_merge(['queued','running'],self::TERMINAL),true))throw new RuntimeException('invalid_state');
            $result=$fn($db);$this->write('jobs.json',json_encode($db,JSON_THROW_ON_ERROR));return $result;
        } catch(JsonException $e) {throw new RuntimeException('invalid_state');}
        finally {flock($f,LOCK_UN);fclose($f);}
    }
    private static function boot(): string {return trim(file_get_contents('/proc/sys/kernel/random/boot_id'));}
    private static function uptime(): float {return (float)explode(' ',file_get_contents('/proc/uptime'))[0];}
    private function cleanupRun(string $id): void
    {
        $runs=$this->root.'/runs';$run=$runs.'/'.$id;
        if(is_link($runs)||is_link($run))throw new RuntimeException('invalid_state');
        if(!is_dir($run))return;$s=lstat($run);if($s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $known=['boot','guard.pid','ack','deadline','probe.deadline','probe.pid','spawn.pid','probe.exe','probe.cwd','probe.request','probe.request.new','probe.exit','probe.exit.new','closing','ending.reason','ended.uptime','args','g0.stdout','g0.stderr','outcome','outcome.new','cancel'];
        foreach($known as $name){$file=$run.'/'.$name;$s=@lstat($file);if($s&&$s['uid']===$this->owner&&($s['mode']&0170000)===0100000&&$s['nlink']===1)@unlink($file);}
        @rmdir($run);
    }
    private function prune(array &$db,float $uptime,int $wall,string $boot): void
    {
        foreach($db['jobs'] as $id=>&$job) {
            $sameBoot=($job['boot_id']??null)===$boot;
            if(!in_array($job['state'],self::TERMINAL,true)) {
                if(!$sameBoot||$uptime<($job['started_uptime']??INF)) {
                    $job['state']='interrupted';$job['finished_at']=$job['started_at'];$job['finished_uptime']=$job['started_uptime'];$job['code']='interrupted';$job['groups']=[];$this->eraseResult($id);$this->cleanupRun($id);
                }
            }
            $terminal=in_array($job['state'],self::TERMINAL,true);
            $expired=$wall<($job['last_wall']??$job['started_at'])||$wall-($terminal?($job['finished_at']??$job['started_at']):$job['started_at'])>=86400;
            if($sameBoot&&$uptime-($terminal?($job['finished_uptime']??$job['started_uptime']):$job['started_uptime'])>=86400)$expired=true;
            // A reboot discards previously retained payload rather than guessing
            // elapsed time from an unrelated monotonic clock.
            if($terminal&&!$sameBoot){$job['groups']=[];$this->eraseResult($id);}
            if($expired) {
                $this->eraseResult($id);$this->cleanupRun($id);unset($db['jobs'][$id]);
            }else $job['last_wall']=$wall;
        }
        unset($job);
    }
    private function eraseResult(string $id): void
    {foreach(['result','native','groups','options','messages'] as $suffix)if($this->regular($this->root.'/'.$id.'.'.$suffix.'.json',1048576)!==null&&!@unlink($this->root.'/'.$id.'.'.$suffix.'.json'))throw new RuntimeException('invalid_state');}
    public function reserve(string $requestId,string $kind,array $params): array
    {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D',$requestId)||!in_array($kind,['install','run'],true)||strlen(json_encode($params))>131072)throw new RuntimeException('invalid_request');
        $options=$params['options']??null;unset($params['options']);if($options!==null)$params['options_digest']=hash('sha256',json_encode($options,JSON_THROW_ON_ERROR));
        return $this->locked(function(array &$db)use($requestId,$kind,$params,$options){
            $up=self::uptime();$now=time();$boot=self::boot();$this->prune($db,$up,$now,$boot);
            foreach($db['jobs'] as $job)if($job['request_id']===$requestId) {
                if($job['kind']!==$kind||$job['params']!==$params)throw new RuntimeException('request_conflict');return $job;
            }
            foreach($db['jobs'] as $job)if(!in_array($job['state'],self::TERMINAL,true))throw new RuntimeException('busy');
            while(count($db['jobs'])>=3){$id=array_key_first($db['jobs']);$this->eraseResult($id);$this->cleanupRun($id);unset($db['jobs'][$id]);}
            $id=bin2hex(random_bytes(16));$job=['id'=>$id,'request_id'=>$requestId,'kind'=>$kind,'params'=>$params,'state'=>'queued','started_at'=>$now,'started_uptime'=>$up,'boot_id'=>$boot,'finished_at'=>null,'code'=>null,'groups'=>[]];
            if($options!==null)$this->write($id.'.options.json',json_encode($options,JSON_THROW_ON_ERROR));
            $db['jobs'][$id]=$job;return $job;
        });
    }
    public function claimLaunch(string $jobId): bool
    {
        return $this->locked(function(array &$db)use($jobId){
            if(!isset($db['jobs'][$jobId]))throw new RuntimeException('missing_job');
            if(!empty($db['jobs'][$jobId]['dispatched'])||$db['jobs'][$jobId]['state']!=='queued')return false;
            $db['jobs'][$jobId]['dispatched']=true;return true;
        });
    }
    public function attachIdentity(string $id,array $identity): void
    {
        $this->locked(function(array &$db)use($id,$identity){if(isset($db['jobs'][$id])&&!in_array($db['jobs'][$id]['state'],self::TERMINAL,true))$db['jobs'][$id]['identity']=$identity;});
    }
    public function update(string $jobId,array $patch): void
    {
        $this->locked(function(array &$db)use($jobId,$patch){
            if(!isset($db['jobs'][$jobId]))throw new RuntimeException('missing_job');
            $job=&$db['jobs'][$jobId];
            $allowed=['state','finished_at','finished_uptime','code','groups','context_before','context_after','identity','current_group','result','native','messages'];
            foreach($patch as $key=>$_)if(!in_array($key,$allowed,true))throw new RuntimeException('invalid_state');
            $next=$patch['state']??$job['state'];
            if(!in_array($next,array_merge(['queued','running'],self::TERMINAL),true)||
                (in_array($job['state'],self::TERMINAL,true)&&$patch!==[])||
                ($job['state']==='running'&&$next==='queued')||
                ($job['state']==='queued'&&in_array($next,['completed','partial'],true)))throw new RuntimeException('invalid_transition');
            foreach(['native','messages'] as $key)if(isset($patch[$key])){$raw=is_string($patch[$key])?$patch[$key]:json_encode($patch[$key],JSON_THROW_ON_ERROR);if($key==='messages'&&strlen($raw)>196608)throw new RuntimeException('output_limit');$this->write($jobId.'.'.$key.'.json',$raw);unset($patch[$key]);}
            if(isset($patch['groups'])){
                $raw=json_encode($patch['groups'],JSON_THROW_ON_ERROR);$this->write($jobId.'.groups.json',$raw);
                $patch['groups']=array_map(fn($g)=>['group'=>$g['group']],$patch['groups']);
            }
            if(isset($patch['result'])) {
                AsusSupportSchema::validate($patch['result'],'dpi');$this->write($jobId.'.result.json',$patch['result']);unset($patch['result']);
            }
            if(in_array($next,self::TERMINAL,true)&&!isset($patch['finished_uptime']))$patch['finished_uptime']=self::uptime();
            $job=array_replace($job,$patch);
        });
    }
    public function status(): array
    {
        return $this->locked(function(array &$db){
            $this->prune($db,self::uptime(),time(),self::boot());$active=null;$history=[];
            foreach($db['jobs'] as $job) {
                $job['native_available']=$this->regular($this->root.'/'.$job['id'].'.native.json',1048576)!==null;
                if(in_array($job['state'],self::TERMINAL,true))$history[]=$job;else {$raw=$this->read($job['id'].'.groups.json',1048576);if($raw!==null)$job['groups']=json_decode($raw,true,32,JSON_THROW_ON_ERROR);$raw=$this->read($job['id'].'.messages.json',196608);if($raw!==null)$job['messages']=json_decode($raw,true,32,JSON_THROW_ON_ERROR);$active=$job;}
            }
            return ['active'=>$active,'history'=>array_reverse($history)];
        });
    }
    public function cleanupArtifacts(callable $cleanup): void
    {
        $this->locked(function(array &$db)use($cleanup){
            $this->prune($db,self::uptime(),time(),self::boot());$active=null;
            foreach($db['jobs'] as $job)if($job['kind']==='install'&&!in_array($job['state'],self::TERMINAL,true))$active=$job['id'];
            $cleanup($active);
        });
    }
    public function readResult(string $jobId): string
    {
        return $this->locked(function(array &$db)use($jobId){
            $this->prune($db,self::uptime(),time(),self::boot());
            if(!isset($db['jobs'][$jobId])||!in_array($db['jobs'][$jobId]['state'],self::TERMINAL,true))throw new RuntimeException('result_unavailable');
            $raw=$this->read($jobId.'.result.json',262144);if($raw===null)throw new RuntimeException('result_unavailable');
            AsusSupportSchema::validate($raw,'dpi');return $raw;
        });
    }
    public function readOptions(string $id): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');
        return $this->locked(function(array &$db)use($id){$this->prune($db,self::uptime(),time(),self::boot());if(!isset($db['jobs'][$id]))throw new RuntimeException('missing_job');$raw=$this->read($id.'.options.json',131072);return $raw===null?AsusDpiOptions::defaults():json_decode($raw,true,32,JSON_THROW_ON_ERROR);});
    }
    public function readNative(string $id): string
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');
        return $this->locked(function(array &$db)use($id){$this->prune($db,self::uptime(),time(),self::boot());if(!isset($db['jobs'][$id])||!in_array($db['jobs'][$id]['state'],self::TERMINAL,true))throw new RuntimeException('result_unavailable');$raw=$this->read($id.'.native.json',1048576);if($raw===null)throw new RuntimeException('result_unavailable');return $raw;});
    }
    public function readPreferences(): array
    {return $this->locked(function(array &$db){$raw=$this->read('preferences.json',131072);return $raw===null?AsusDpiOptions::defaults():json_decode($raw,true,32,JSON_THROW_ON_ERROR);});}
    public function writePreferences(array $options): void
    {$options=AsusDpiOptions::normalize($options);$options['proxy']=null;$this->locked(function(array &$db)use($options){$this->write('preferences.json',json_encode($options,JSON_THROW_ON_ERROR));});}
    public function deleteResult(string $jobId): void
    {
        $this->locked(function(array &$db)use($jobId){
            if(!isset($db['jobs'][$jobId]))throw new RuntimeException('missing_job');
            if(!in_array($db['jobs'][$jobId]['state'],self::TERMINAL,true))throw new RuntimeException('busy');
            $this->eraseResult($jobId);
            $db['jobs'][$jobId]['groups']=[];
            unset($db['jobs'][$jobId]['context_before'],$db['jobs'][$jobId]['context_after']);
        });
    }
    public function reconcile(float $uptime,int $wallTime,string $bootId): void
    {$this->locked(function(array &$db)use($uptime,$wallTime,$bootId){$this->prune($db,$uptime,$wallTime,$bootId);});}
}
