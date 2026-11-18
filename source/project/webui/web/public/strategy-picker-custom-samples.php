<?php
require_once __DIR__.'/strategy-picker-custom-score.php';

/** Internal caller holds engine.lock + shared writer. Only capture() issues
 * sample ids, around an actual trusted probe callback. A private exclusive
 * artifact is published logically ONLY by the atomic journal reference; an
 * uncommitted file is never a readable report. No HTTP caller is enabled. */
final class NfqwsStrategyPickerCustomSamples
{
    private const FILE_LIMIT=69632;
    private const MAX_FILES=96;
    private const TOTAL_LIMIT=8388608;
    private Closure $checkpoint;
    private Closure $context;
    public function __construct(private NfqwsStrategyPickerState $store,callable $checkpoint,?callable $context=null,private int $owner=0)
    {$this->checkpoint=Closure::fromCallable($checkpoint);$this->context=Closure::fromCallable($context??[AsusDpiWorker::class,'context']);}
    private static function keys(array $v,array $expected):bool
    {$k=array_keys($v);sort($k);sort($expected);return $k===$expected;}
    private static function encode(array $v):string
    {return json_encode($v,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);}
    private static function wire(array $v):array
    {return json_decode(self::encode($v),true,32,JSON_THROW_ON_ERROR);}
    private static function hex(mixed $v,int $n=64):bool
    {return is_string($v)&&preg_match('/^[a-f0-9]{'.$n.'}$/D',$v)===1;}
    private static function role(mixed $v):bool
    {return is_string($v)&&preg_match('/^[a-z0-9][a-z0-9_-]{0,63}$/D',$v)===1;}
    private static function identity(array $s):array
    {return ['dev'=>(string)$s['dev'],'ino'=>(string)$s['ino'],'uid'=>$s['uid'],'gid'=>$s['gid'],
        'mode'=>$s['mode']&07777,'nlink'=>$s['nlink']];}
    private function root():string
    {
        $root=dirname($this->store->path('state.json'));$j=$this->store->read();
        if(!isset($j['series']))return $root;
        $total=NfqwsStrategyPickerRequest::rounds((string)($j['rounds']??1));
        $round=$j['series']['selected']??$j['series']['current']??null;
        if(!is_int($round)||$round<1||$round>$total||($j['series']['total']??null)!==$total)
            throw new RuntimeException('storage_unavailable');
        // Each explicit round retains the original artifact/attempt limits.
        // Previous round files remain intact in their owned directory.
        $part=$this->store->round($round);
        return dirname($part->path('state.json'));
    }
    private function path(string $job,string $id):string
    {
        if(!self::hex($job,32)||!self::hex($id,32))throw new RuntimeException('invalid_request');
        $root=$this->root();$name='custom-'.$job.'-'.$id.'.json';
        try{return class_exists('NfqwsDeviceProfilesPaths',false)?NfqwsDeviceProfilesPaths::guard($root,$name,$this->owner):NfqwsPlatform::guardFile($root,$name,$this->owner);}
        catch(Throwable $e){throw new RuntimeException('storage_unavailable',0,$e);}
    }
    private function stat(string $path):?array
    {
        clearstatcache(true,$path);$s=@lstat($path);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||($s['mode']&07777)!==0600||$s['uid']!==$this->owner||
            $s['nlink']!==1||$s['size']>self::FILE_LIMIT)throw new RuntimeException('storage_unavailable');
        return $s;
    }
    private function journal(?string $id=null):array
    {
        $path=$this->store->path('state.json');$stat=@lstat($path);
        if(!$stat||$stat['uid']!==$this->owner||$stat['nlink']!==1||($stat['mode']&07777)!==0600)
            throw new RuntimeException('storage_unavailable');
        $j=$this->store->read();
        if(!is_array($j)||!self::hex($j['id']??null,32)||$id!==null&&$j['id']!==$id)throw new RuntimeException('stale_state');
        return $j;
    }
    private function working(?string $id,string $config,?array $pending=null):array
    {
        ($this->checkpoint)();$j=$this->journal($id);
        if(($j['state']??null)!=='running'||($j['boot']??null)!==AsusUpdateStore::boot()||
            ($j['current']??null)!==$config)throw new RuntimeException('stale_state');
        $deadline=NfqwsStrategyPickerBudget::overallDeadline($j);if($deadline!==null&&AsusUpdateStore::uptime()>=$deadline)throw new RuntimeException('timed_out');
        if($pending!==null&&($j['custom_sample_pending']??null)!==$pending)throw new RuntimeException('stale_state');
        return $j;
    }
    private function manifest(array $j):array
    {
        $v=$j['custom_manifest']??null;$sha=$j['custom_manifest_sha256']??null;
        if(!is_array($v)||!self::hex($sha)||hash('sha256',self::encode($v))!==$sha)throw new RuntimeException('stale_state');
        try{$v=NfqwsStrategyPickerCustomWorker::document(self::encode($v),'probe');}
        catch(Throwable $e){throw new RuntimeException('stale_state',0,$e);}
        if(($j['custom_hosts']??null)!==$v['hosts'])throw new RuntimeException('stale_state');return $v;
    }
    private function context(string $expected,string $dns):void
    {
        $c=($this->context)();
        if(!is_array($c)||!self::keys($c,['nfqws','ark','tun_observed','dns'])||
            !in_array($c['nfqws'],['running','stopped'],true)||!in_array($c['ark'],['loaded','absent'],true)||
            !is_bool($c['tun_observed'])||!is_array($c['dns'])||!self::keys($c['dns'],['schema_version','state','sha256'])||
            $c['dns']['schema_version']!==1||$c['dns']['state']!=='known'||$c['dns']['sha256']!==$dns)
            throw new RuntimeException('incomparable_result');
        ksort($c);if(hash('sha256',json_encode($c,JSON_THROW_ON_ERROR))!==$expected)throw new RuntimeException('incomparable_result');
    }
    private function refs(array $j):array
    {
        $refs=$j['custom_sample_refs']??[];
        if(!is_array($refs)||!array_is_list($refs)||count($refs)>32)throw new RuntimeException('storage_unavailable');
        $ids=[];$roles=[];
        foreach($refs as $r){
            if(!is_array($r)||!self::keys($r,['id','role','repeat','config_sha256','context_sha256','manifest_sha256','bytes','sha256','identity'])||
                !self::hex($r['id'],32)||!self::role($r['role'])||!in_array($r['repeat'],[1,2],true)||
                !self::hex($r['config_sha256'])||!self::hex($r['context_sha256'])||!self::hex($r['manifest_sha256'])||
                $r['manifest_sha256']!==($j['custom_manifest_sha256']??null)||!self::hex($r['sha256'])||
                !is_int($r['bytes'])||$r['bytes']<1||$r['bytes']>self::FILE_LIMIT||!is_array($r['identity'])||
                !self::keys($r['identity'],['dev','ino','uid','gid','mode','nlink'])||
                in_array($r['id'],$ids,true)||in_array([$r['role'],$r['repeat']],$roles,true))throw new RuntimeException('storage_unavailable');
            $ids[]=$r['id'];$roles[]=[$r['role'],$r['repeat']];
        }
        return $refs;
    }
    private function admission():void
    {
        $root=$this->root();$d=@opendir($root);if(!$d)throw new RuntimeException('storage_unavailable');
        $count=0;$bytes=0;$entries=0;
        try{while(false!==($name=readdir($d))){
            if(++$entries>512)throw new RuntimeException('output_limit');
            if(!preg_match('/^custom-([a-f0-9]{32})-([a-f0-9]{32})\.json$/D',$name,$m))continue;
            $p=$this->path($m[1],$m[2]);$s=$this->stat($p);if(!$s)throw new RuntimeException('storage_unavailable');
            $count++;$bytes+=$s['size'];
        }}finally{closedir($d);}
        if($count>=self::MAX_FILES||$bytes+self::FILE_LIMIT>self::TOTAL_LIMIT)throw new RuntimeException('output_limit');
        $free=@disk_free_space($root);if($free===false||$free<1048576+self::FILE_LIMIT)throw new RuntimeException('insufficient_space');
    }
    private function readArtifact(array $j,array $ref):array
    {
        $path=$this->path($j['id'],$ref['id']);$s=$this->stat($path);
        if(!$s||self::identity($s)!==$ref['identity']||$s['size']!==$ref['bytes'])throw new RuntimeException('storage_unavailable');
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('storage_unavailable');
        try{
            if(self::identity(fstat($f))!==$ref['identity'])throw new RuntimeException('storage_unavailable');
            $raw=stream_get_contents($f,self::FILE_LIMIT+1);
            $now=$this->stat($path);
            if(!is_string($raw)||strlen($raw)!==$ref['bytes']||hash('sha256',$raw)!==$ref['sha256']||
                !$now||self::identity($now)!==$ref['identity']||self::identity(fstat($f))!==$ref['identity'])
                throw new RuntimeException('storage_unavailable');
        }finally{fclose($f);}
        try{
            $v=AsusSupportSchema::decode($raw,self::FILE_LIMIT,'storage_unavailable');
            if(!$v instanceof stdClass)throw new RuntimeException('storage_unavailable');
            $v=json_decode($raw,true,32,JSON_THROW_ON_ERROR);
            if(!self::keys($v,['schema_version','job_id','sample_id','role','repeat','config_sha256','context_sha256',
                'manifest_sha256','started_uptime','finished_uptime','elapsed_ms','envelope'])||!in_array($v['schema_version'],[1,2],true)||
                $v['job_id']!==$j['id']||$v['sample_id']!==$ref['id'])throw new RuntimeException('storage_unavailable');
            foreach(['role','repeat','config_sha256','context_sha256','manifest_sha256']as $key)
                if($v[$key]!==$ref[$key])throw new RuntimeException('storage_unavailable');
            foreach(['started_uptime','finished_uptime']as $key)
                if(!is_int($v[$key])&&!is_float($v[$key])||!is_finite((float)$v[$key])||$v[$key]<0)throw new RuntimeException('storage_unavailable');
            if(!is_int($v['elapsed_ms'])||$v['elapsed_ms']<0||$v['elapsed_ms']>90000||$v['finished_uptime']<$v['started_uptime']||
                abs(($v['finished_uptime']-$v['started_uptime'])*1000-$v['elapsed_ms'])>1.01||!is_array($v['envelope']))
                throw new RuntimeException('storage_unavailable');
            $manifest=$this->manifest($j);
            if($v['schema_version']!==$manifest['schema_version']||($v['envelope']['manifest_sha256']??null)!==$ref['manifest_sha256']||
                NfqwsStrategyPickerCustomWorker::scope($v['envelope'])!==NfqwsStrategyPickerCustomWorker::scope($manifest))
                throw new RuntimeException('storage_unavailable');
            $score=NfqwsStrategyPickerCustomScore::measure($v['envelope'],$ref['context_sha256'],$ref['id']);
            return ['document'=>$v,'score'=>$score];
        }catch(Throwable $e){throw new RuntimeException('storage_unavailable',0,$e);}
    }
    public function capture(string $role,string $config,int $repeat,string $nativeContext,callable $probe):array
    {
        if(!self::role($role)||!self::hex($config)||!self::hex($nativeContext)||!in_array($repeat,[1,2],true))throw new RuntimeException('invalid_request');
        $j=$this->working(null,$config);$id=$j['id'];
        if(($j['custom_sample_pending']??null)!==null||($j['custom_sample_cleanup']??null)!==null)throw new RuntimeException('busy');
        $manifest=$this->manifest($j);$refs=$this->refs($j);$attempts=$j['custom_sample_attempts']??0;
        if(!is_int($attempts)||$attempts<0)throw new RuntimeException('storage_unavailable');
        if(count($refs)>=32||$attempts>=64)throw new RuntimeException('output_limit');
        foreach($refs as $r)if($r['role']===$role&&
            ($r['repeat']===$repeat||$r['config_sha256']!==$config))throw new RuntimeException('stale_state');
        $this->context($nativeContext,$manifest['dns_context']);$this->admission();
        $sample=bin2hex(random_bytes(16));$path=$this->path($id,$sample);
        if(@lstat($path)!==false)throw new RuntimeException('storage_unavailable');
        $pending=self::wire(['id'=>$sample,'role'=>$role,'repeat'=>$repeat,'config_sha256'=>$config,
            'context_sha256'=>$nativeContext,'manifest_sha256'=>$j['custom_manifest_sha256'],
            'started_uptime'=>AsusUpdateStore::uptime(),'identity'=>null,'expected'=>null]);
        $current=$this->working($id,$config);
        if(($current['custom_sample_pending']??null)!==null||($current['custom_sample_cleanup']??null)!==null||
            $this->refs($current)!==$refs||($current['custom_sample_attempts']??0)!==$attempts||
            ($current['custom_manifest_sha256']??null)!==$pending['manifest_sha256'])throw new RuntimeException('stale_state');
        $this->manifest($current);
        $current['custom_sample_pending']=$pending;$current['custom_sample_attempts']=$attempts+1;$this->store->write($current);
        $f=null;$identity=null;$raw='';$written=0;$committed=false;$primary=null;
        try{
            $this->working($id,$config,$pending);$envelope=$probe();$finished=AsusUpdateStore::uptime();
            $current=$this->working($id,$config,$pending);$this->context($nativeContext,$manifest['dns_context']);
            try{$scope=is_array($envelope)?NfqwsStrategyPickerCustomWorker::scope($envelope):null;}
            catch(Throwable $e){throw new RuntimeException('incomparable_result',0,$e);}
            if(($current['custom_manifest_sha256']??null)!==$pending['manifest_sha256']||
                !is_array($envelope)||($envelope['manifest_sha256']??null)!==$pending['manifest_sha256']||
                $scope!==NfqwsStrategyPickerCustomWorker::scope($manifest))
                throw new RuntimeException('incomparable_result');
            $score=NfqwsStrategyPickerCustomScore::measure($envelope,$nativeContext,$sample);
            $elapsed=(int)floor(($finished-$pending['started_uptime'])*1000);
            if($elapsed<0||$elapsed>90000)throw new RuntimeException('timed_out');
            $raw=self::encode(['schema_version'=>$manifest['schema_version'],'job_id'=>$id,'sample_id'=>$sample,'role'=>$role,'repeat'=>$repeat,
                'config_sha256'=>$config,'context_sha256'=>$nativeContext,'manifest_sha256'=>$pending['manifest_sha256'],
                'started_uptime'=>$pending['started_uptime'],'finished_uptime'=>$finished,'elapsed_ms'=>$elapsed,'envelope'=>$envelope]);
            if(strlen($raw)>self::FILE_LIMIT)throw new RuntimeException('output_limit');
            $current=$this->working($id,$config,$pending);
            $pending['expected']=['bytes'=>strlen($raw),'sha256'=>hash('sha256',$raw)];
            $current['custom_sample_pending']=$pending;$this->store->write($current);
            $this->working($id,$config,$pending);
            $mask=umask(0077);try{$f=@fopen($path,'xb');}finally{umask($mask);}
            if(!$f)throw new RuntimeException('storage_unavailable');$identity=self::identity(fstat($f));
            $current=$this->working($id,$config,$pending);$pending['identity']=$identity;
            $current['custom_sample_pending']=$pending;$this->store->write($current);
            $this->working($id,$config,$pending);
            while($written<strlen($raw)){$n=fwrite($f,substr($raw,$written));if(!$n)throw new RuntimeException('insufficient_space');$written+=$n;}
            if(!fflush($f)||(function_exists('fsync')&&!fsync($f)))throw new RuntimeException('insufficient_space');
            $ref=['id'=>$sample,'role'=>$role,'repeat'=>$repeat,'config_sha256'=>$config,'context_sha256'=>$nativeContext,
                'manifest_sha256'=>$pending['manifest_sha256'],'bytes'=>strlen($raw),'sha256'=>hash('sha256',$raw),'identity'=>$identity];
            $current=$this->working($id,$config,$pending);$this->context($nativeContext,$manifest['dns_context']);
            $current=$this->working($id,$config,$pending);
            if($this->refs($current)!==$refs||($current['custom_manifest_sha256']??null)!==$pending['manifest_sha256'])throw new RuntimeException('stale_state');
            $loaded=$this->readArtifact($current,$ref);
            if($loaded['score']!==$score)throw new RuntimeException('incomparable_result');
            $current['custom_sample_refs']=[...$refs,$ref];unset($current['custom_sample_pending']);$this->store->write($current);
            $committed=true;return $score;
        }catch(Throwable $error){$primary=$error;throw $error;}finally{
            if(is_resource($f))fclose($f);
            try{if(!$committed){
                $current=$this->journal();
                if($current['id']===$id&&($current['custom_sample_pending']??null)===$pending){
                    $cleaned=false;
                    try{$stat=$this->stat($path);
                        $cleaned=$stat===null;
                        if($stat&&$identity!==null&&self::identity($stat)===$identity&&$stat['size']===$written&&
                            hash_file('sha256',$path)===hash('sha256',substr($raw,0,$written)))$cleaned=unlink($path);
                    }catch(Throwable $ignored){} // Preserve both an unknown file and its intent.
                    if($cleaned){unset($current['custom_sample_pending']);$this->store->write($current);}
                }
            }}catch(Throwable $cleanup){if($primary===null)throw $cleanup;}
        }
    }
    public function load(string $id,string $sample):array
    {
        $j=$this->journal($id);foreach($this->refs($j)as $r)if($r['id']===$sample)return $this->readArtifact($j,$r);
        throw new RuntimeException('incomparable_result');
    }
    /** Read-only immutable manifest projection for the trusted joint adapter. */
    public function manifestFor(string $id):array
    {return $this->manifest($this->journal($id));}
    public function pair(string $id,string $role):array
    {
        $j=$this->journal($id);$runs=[];$config=null;
        foreach($this->refs($j)as $r)if($r['role']===$role){
            if($config!==null&&$r['config_sha256']!==$config)throw new RuntimeException('incomparable_result');
            $config=$r['config_sha256'];$runs[$r['repeat']]=$this->readArtifact($j,$r)['score'];
        }
        if(count($runs)!==2||!isset($runs[1],$runs[2]))throw new RuntimeException('incomparable_result');
        return [$runs[1],$runs[2]];
    }
    public function compare(string $id,string $baseline,string $candidate):array
    {return NfqwsStrategyPickerCustomScore::compare($this->pair($id,$baseline),$this->pair($id,$candidate));}
    private function terminal(string $id,?callable $applied=null):array
    {
        $j=$this->journal($id);
        if(($j['actuator']??null)!==null||($j['custom_worker']??null)!==null)throw new RuntimeException('busy');
        if(($j['state']??null)==='applied'&&$applied!==null)$applied($j);
        elseif(!in_array($j['state']??null,['completed','failed','cancelled','interrupted'],true)||($j['restored']??false)!==true)throw new RuntimeException('busy');
        return $j;
    }
    private function pending(array $j):?array
    {
        $p=$j['custom_sample_pending']??null;if($p===null)return null;
        if(!is_array($p)||!self::keys($p,['id','role','repeat','config_sha256','context_sha256','manifest_sha256','started_uptime','identity','expected'])||
            !self::hex($p['id'],32)||!self::role($p['role'])||!in_array($p['repeat'],[1,2],true)||
            !self::hex($p['config_sha256'])||!self::hex($p['context_sha256'])||!self::hex($p['manifest_sha256'])||
            $p['manifest_sha256']!==($j['custom_manifest_sha256']??null)||
            (!is_int($p['started_uptime'])&&!is_float($p['started_uptime']))||!is_finite((float)$p['started_uptime'])||$p['started_uptime']<0)
            throw new RuntimeException('storage_unavailable');
        $a=$p['identity'];
        if($a!==null&&(!is_array($a)||!self::keys($a,['dev','ino','uid','gid','mode','nlink'])||
            !is_string($a['dev'])||!is_string($a['ino'])||!preg_match('/^-?[0-9]{1,32}$/D',$a['dev'])||!preg_match('/^-?[0-9]{1,32}$/D',$a['ino'])||
            $a['uid']!==$this->owner||!is_int($a['gid'])||$a['gid']<0||$a['mode']!==0600||$a['nlink']!==1))throw new RuntimeException('storage_unavailable');
        $e=$p['expected'];
        if($e!==null&&(!is_array($e)||!self::keys($e,['bytes','sha256'])||!is_int($e['bytes'])||$e['bytes']<1||$e['bytes']>self::FILE_LIMIT||!self::hex($e['sha256'])))
            throw new RuntimeException('storage_unavailable');
        $this->manifest($j);return $p;
    }
    public function recoverPending(string $id,?callable $applied=null):void
    {
        $j=$this->terminal($id,$applied);$pending=$this->pending($j);if($pending===null)return;
        if(($j['custom_sample_cleanup']??null)!==null)throw new RuntimeException('busy');
        $refs=$this->refs($j);
        foreach($refs as $ref)if($ref['id']===$pending['id']||[$ref['role'],$ref['repeat']]===[$pending['role'],$pending['repeat']])
            throw new RuntimeException('recovery_required');
        $current=function()use($id,$pending,$refs,$applied):array{
            $v=$this->terminal($id,$applied);
            if($this->pending($v)!==$pending||$this->refs($v)!==$refs||($v['custom_sample_cleanup']??null)!==null)throw new RuntimeException('stale_state');
            return $v;
        };
        try{
            $path=$this->path($id,$pending['id']);
            $s=$this->stat($path);
            if($s){
                if($pending['identity']===null||self::identity($s)!==$pending['identity'])throw new RuntimeException('recovery_required');
                $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('recovery_required');
                try{
                    if(self::identity(fstat($f))!==$pending['identity'])throw new RuntimeException('recovery_required');
                    $raw=stream_get_contents($f,self::FILE_LIMIT+1);$now=$this->stat($path);
                    if(!is_string($raw)||strlen($raw)!==$s['size']||!$now||self::identity($now)!==$pending['identity']||
                        self::identity(fstat($f))!==$pending['identity'])throw new RuntimeException('recovery_required');
                    $expected=$pending['expected'];
                    if($raw!==''&&($expected===null||strlen($raw)!==$expected['bytes']||hash('sha256',$raw)!==$expected['sha256']))
                        throw new RuntimeException('recovery_required');
                }finally{fclose($f);}
                $current();$now=$this->stat($path);
                if(!$now||self::identity($now)!==$pending['identity']||!unlink($path))throw new RuntimeException('recovery_required');
            }
        }catch(Throwable $e){throw new RuntimeException('recovery_required',0,$e);}
        $v=$current();unset($v['custom_sample_pending']);$this->store->write($v);
    }
    public function retire(string $id,?callable $applied=null):void
    {
        $this->terminal($id,$applied);$this->recoverPending($id,$applied);$this->clear($id,$applied);$j=$this->terminal($id,$applied);
        if($this->refs($j)||($j['custom_sample_pending']??null)!==null||($j['custom_sample_cleanup']??null)!==null)throw new RuntimeException('busy');
        if(($j['custom_samples_retired']??false)!==true){$j['custom_samples_retired']=true;$this->store->write($j);}
    }
    public function clear(string $id,?callable $applied=null):void
    {
        $j=$this->terminal($id,$applied);
        if(($j['custom_sample_pending']??null)!==null)throw new RuntimeException('busy');
        $refs=$this->refs($j);$intent=$j['custom_sample_cleanup']??null;$resuming=$intent!==null;
        if($resuming&&$intent!==['refs'=>$refs])throw new RuntimeException('stale_state');
        foreach($refs as $r){$p=$this->path($id,$r['id']);if(!$this->stat($p)&&$resuming)continue;$this->readArtifact($j,$r);}
        if(!$refs){if($resuming){unset($j['custom_sample_cleanup']);$this->store->write($j);}return;}
        if(!$resuming){$intent=['refs'=>$refs];$j['custom_sample_cleanup']=$intent;$this->store->write($j);}
        foreach($refs as $r){
            $current=$this->terminal($id,$applied);
            if(($current['custom_sample_cleanup']??null)!==$intent||$this->refs($current)!==$refs)throw new RuntimeException('stale_state');
            $p=$this->path($id,$r['id']);if(!$this->stat($p))continue;$this->readArtifact($current,$r);
            if(!unlink($p))throw new RuntimeException('storage_unavailable');
        }
        $current=$this->terminal($id,$applied);
        if(($current['custom_sample_cleanup']??null)!==$intent||$this->refs($current)!==$refs)throw new RuntimeException('stale_state');
        $current['custom_sample_refs']=[];unset($current['custom_sample_cleanup']);$this->store->write($current);
    }
}
