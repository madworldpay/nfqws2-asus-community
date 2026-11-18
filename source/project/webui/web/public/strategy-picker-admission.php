<?php
/** Optional root-managed admission. No HTTP issuer or signal/restore operations. */
final class NfqwsStrategyPickerAdmission
{
    private string $root;
    public function __construct(?string $root=null)
    {
        if($root===null){
            if(!class_exists('NfqwsPlatform',false))require_once __DIR__.'/platform.php';
            $settings=NfqwsPlatform::settings();$root=$settings['web_config'].'/picker-admission';
            if($settings['root']==='/opt'){
                if(!class_exists('AsusShareRead',false))require_once __DIR__.'/share-read.php';
                if(!class_exists('NfqwsDeviceProfilesPaths',false)){
                    $paths=is_file(__DIR__.'/device-profiles-paths.php')?__DIR__.'/device-profiles-paths.php':dirname(__DIR__,3).'/experimental/device-profiles/device-profiles-paths.php';
                    require_once $paths;
                }
                $root=NfqwsDeviceProfilesPaths::readPath($root);
            }
        }
        if($root===''||$root[0]!=='/'||$root==='/'||str_ends_with($root,'/')||str_contains($root,"\0")||str_contains($root,'//')||preg_match('~(?:^|/)\.\.?(?:/|$)~',$root))throw new RuntimeException('invalid_admission');
        $this->root=$root;
    }
    private static function id(string $id):void{if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_admission');}
    private static function digest(string $v):void{if(!preg_match('/^[a-f0-9]{64}$/D',$v))throw new RuntimeException('invalid_admission');}
    public static function now():float{$v=explode(' ',trim((string)file_get_contents('/proc/uptime')))[0];if(!is_numeric($v)||!is_finite((float)$v))throw new RuntimeException('invalid_admission');return (float)$v;}
    private static function boot():string{$v=trim((string)file_get_contents('/proc/sys/kernel/random/boot_id'));if(!preg_match('/^[a-f0-9-]{36}$/D',$v))throw new RuntimeException('invalid_admission');return $v;}
    private static function processUid(int $pid):?int
    {
        $status=@file_get_contents('/proc/'.$pid.'/status',false,null,0,131073);
        if(!is_string($status)||strlen($status)>131072||!preg_match('/^Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$/m',$status,$m)||
           $m[1]!==$m[2]||$m[1]!==$m[3]||$m[1]!==$m[4]||(float)$m[1]>4294967295)return null;
        return (int)$m[1];
    }
    public static function identity(int $pid):?array
    {
        $p='/proc/'.$pid;clearstatcache(true,$p);$raw=@file_get_contents($p.'/stat',false,null,0,131073);
        if(!is_string($raw)||$raw===''||strlen($raw)>131072||($end=strrpos($raw,')'))===false)return null;$v=explode(' ',trim(substr($raw,$end+1)));
        if(($v[0]??'Z')==='Z'||!isset($v[19])||!preg_match('/^[0-9]+$/D',$v[19]))return null;
        $args=@file_get_contents($p.'/cmdline',false,null,0,131073);$cwd=@readlink($p.'/cwd');$uid=self::processUid($pid);
        if(!is_string($args)||$args===''||strlen($args)>131072||!is_string($cwd)||!is_int($uid))return null;
        $boot=self::boot();
        if(@file_get_contents($p.'/cmdline',false,null,0,131073)!==$args||@readlink($p.'/cwd')!==$cwd||self::processUid($pid)!==$uid)return null;
        $after=@file_get_contents($p.'/stat',false,null,0,131073);
        if(!is_string($after)||$after===''||strlen($after)>131072||($end=strrpos($after,')'))===false)return null;$last=explode(' ',trim(substr($after,$end+1)));
        if(($last[0]??'Z')==='Z'||($last[19]??null)!==$v[19])return null;
        return ['pid'=>$pid,'ticks'=>$v[19],'boot'=>$boot,'uid'=>$uid,'argv'=>explode("\0",rtrim($args,"\0")),'cwd'=>$cwd];
    }
    private static function keys(array $v,array $keys):void{$a=array_keys($v);sort($a);sort($keys);if($a!==$keys)throw new RuntimeException('invalid_admission');}
    private function dir(string $path):bool
    {
        for($p=$path;$p!=='/';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_admission');
        clearstatcache(true,$path);$s=@lstat($path);if(!$s)return false;
        if(($s['mode']&0170000)!==0040000||$s['uid']!==0||($s['mode']&0777)!==0700||realpath($path)!==$path)throw new RuntimeException('invalid_admission');return true;
    }
    private function location(string $id,bool $create=false):?string
    {
        self::id($id);if(!$this->dir($this->root)){if(!$create)return null;$mask=umask(0077);try{if(!mkdir($this->root,0700))throw new RuntimeException('invalid_admission');}finally{umask($mask);}if(!$this->dir($this->root))throw new RuntimeException('invalid_admission');}
        $dir=$this->root.'/'.$id;if(!$this->dir($dir)){if(!$create)return null;$mask=umask(0077);try{if(!mkdir($dir,0700))throw new RuntimeException('invalid_admission');}finally{umask($mask);}if(!$this->dir($dir))throw new RuntimeException('invalid_admission');}elseif($create)throw new RuntimeException('admission_exists');return $dir;
    }
    private static function statFile(string $path,int $cap=8192):?array
    {
        clearstatcache(true,$path);$s=@lstat($path);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==0||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>$cap)throw new RuntimeException('invalid_admission');return $s;
    }
    private static function read(string $path):array
    {
        $s=self::statFile($path);if(!$s)throw new RuntimeException('invalid_admission');$f=@fopen($path,'rb');if(!$f)throw new RuntimeException('invalid_admission');
        try{$a=fstat($f);if($a['dev']!==$s['dev']||$a['ino']!==$s['ino'])throw new RuntimeException('invalid_admission');$raw=stream_get_contents($f,8193);}finally{fclose($f);}
        if(!is_string($raw)||strlen($raw)>8192)throw new RuntimeException('invalid_admission');$v=json_decode($raw,true,16,JSON_THROW_ON_ERROR);if(!is_array($v))throw new RuntimeException('invalid_admission');return $v;
    }
    private static function atomic(string $path,array $v):void
    {
        $tmp=dirname($path).'/.tmp-'.bin2hex(random_bytes(12));$raw=json_encode($v,JSON_THROW_ON_ERROR);if(strlen($raw)>8192)throw new RuntimeException('invalid_admission');$mask=umask(0077);
        try{$f=fopen($tmp,'xb');if(!$f)throw new RuntimeException('invalid_admission');try{if(!chmod($tmp,0600)||fwrite($f,$raw)!==strlen($raw)||!fflush($f)||(function_exists('fsync')&&!fsync($f)))throw new RuntimeException('invalid_admission');}finally{fclose($f);}if(!rename($tmp,$path))throw new RuntimeException('invalid_admission');}finally{umask($mask);if(is_file($tmp))unlink($tmp);}
    }
    private function record(string $dir,string $id):array
    {
        $v=self::read($dir.'/record.json');self::keys($v,['schema','request_id','scope','selection_sha256','plan_sha256','boot','created','expires','state','job_id','handler']);
        self::id($v['request_id']??'');self::id($v['scope']??'');self::digest($v['selection_sha256']??'');self::digest($v['plan_sha256']??'');
        if($v['schema']!==1||$v['request_id']!==$id||!is_string($v['boot'])||!preg_match('/^[a-f0-9-]{36}$/D',$v['boot'])||
           (!is_int($v['created'])&&!is_float($v['created']))||(!is_int($v['expires'])&&!is_float($v['expires']))||
           !is_finite((float)$v['created'])||!is_finite((float)$v['expires'])||$v['created']<0||$v['expires']<=$v['created']||$v['expires']-$v['created']>60||
           !in_array($v['state'],['open','admitting','accepted','closed'],true)||($v['job_id']!==null&&(!is_string($v['job_id'])||!preg_match('/^[a-f0-9]{32}$/D',$v['job_id']))))throw new RuntimeException('invalid_admission');
        if($v['handler']!==null)self::actorShape($v['handler'],$v['boot']);
        if($v['state']==='open'&&($v['handler']!==null||$v['job_id']!==null)||$v['state']==='admitting'&&($v['handler']===null||$v['job_id']!==null)||$v['state']==='accepted'&&($v['handler']===null||$v['job_id']===null))throw new RuntimeException('invalid_admission');
        return $v;
    }
    private static function actorShape(mixed $a,string $boot):void
    {
        if(!is_array($a))throw new RuntimeException('invalid_admission');self::keys($a,['pid','ticks','boot','uid','argv','cwd']);
        if(!is_int($a['pid'])||$a['pid']<2||!is_string($a['ticks'])||!preg_match('/^[0-9]+$/D',$a['ticks'])||$a['boot']!==$boot||$a['uid']!==0||!is_array($a['argv'])||!array_is_list($a['argv'])||!$a['argv']||!is_string($a['cwd'])||!str_starts_with($a['cwd'],'/'))throw new RuntimeException('invalid_admission');
        foreach($a['argv']as $arg)if(!is_string($arg)||str_contains($arg,"\0"))throw new RuntimeException('invalid_admission');
    }
    private static function lock(string $dir)
    {
        $s=self::statFile($dir.'/lock',0);if(!$s||$s['size']!==0)throw new RuntimeException('invalid_admission');$f=fopen($dir.'/lock','r+be');if(!$f)throw new RuntimeException('invalid_admission');$a=fstat($f);
        if($s['dev']!==$a['dev']||$s['ino']!==$a['ino']){fclose($f);throw new RuntimeException('invalid_admission');}return $f;
    }
    public function prepare(string $id,string $scope,string $selection,string $plan,mixed $ttl=30):array
    {
        self::id($id);self::id($scope);self::digest($selection);self::digest($plan);if(!is_int($ttl)||$ttl<1||$ttl>60||(self::processUid(getmypid())!==0))throw new RuntimeException('invalid_admission');
        $dir=$this->location($id,true);$mask=umask(0077);try{$f=fopen($dir.'/lock','xb');if(!$f)throw new RuntimeException('invalid_admission');fclose($f);chmod($dir.'/lock',0600);}finally{umask($mask);}
        $now=self::now();$v=['schema'=>1,'request_id'=>$id,'scope'=>$scope,'selection_sha256'=>$selection,'plan_sha256'=>$plan,'boot'=>self::boot(),'created'=>$now,'expires'=>$now+$ttl,'state'=>'open','job_id'=>null,'handler'=>null];self::atomic($dir.'/record.json',$v);return $v;
    }
    private function revoked(string $dir,array $record):bool
    {
        if(self::statFile($dir.'/revoked.json')===null)return false;$v=self::read($dir.'/revoked.json');
        if($v!==['schema'=>1,'request_id'=>$record['request_id'],'scope'=>$record['scope']])throw new RuntimeException('invalid_admission');return true;
    }
    private static function candidateBinding(string $path):array
    {
        $s=self::statFile($path);if(!$s)throw new RuntimeException('invalid_admission');$v=[];foreach(['dev','ino','mode','uid','gid','nlink','size']as $k)$v[$k]=$s[$k];$v['sha256']=hash_file('sha256',$path);return $v;
    }
    private static function removeCandidate(string $path,array $expected):void
    {
        if(self::statFile($path)===null)return;if(self::candidateBinding($path)!==$expected)throw new RuntimeException('invalid_admission');if(!unlink($path))throw new RuntimeException('invalid_admission');
    }
    public function enter(string $id,string $selection,?string $plan):?NfqwsStrategyPickerAdmissionLease
    {
        $dir=$this->location($id);if($dir===null)return null;$v=$this->record($dir,$id);self::digest($selection);
        if($plan===null||!hash_equals($v['selection_sha256'],$selection)||!hash_equals($v['plan_sha256'],$plan))throw new RuntimeException('admission_mismatch');
        if($v['boot']!==self::boot()||$v['expires']<=self::now()||$v['created']>self::now()||$v['state']!=='open'||$this->revoked($dir,$v))throw new RuntimeException('admission_closed');
        $actor=self::identity(getmypid());if(!$actor||$actor['uid']!==0)throw new RuntimeException('invalid_admission');self::actorShape($actor,$v['boot']);
        $candidate=$dir.'/handler-'.$actor['pid'].'-'.$actor['ticks'].'.json';
        if(file_exists($candidate)||is_link($candidate))throw new RuntimeException('invalid_admission');
        self::atomic($candidate,['schema'=>1,'request_id'=>$id,'scope'=>$v['scope'],'selection_sha256'=>$selection,'plan_sha256'=>$plan,'actor'=>$actor]);
        $binding=self::candidateBinding($candidate);$f=null;try{$f=self::lock($dir);if(!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('admission_busy');$v=$this->record($dir,$id);
            if($v['state']!=='open'||$v['boot']!==self::boot()||$v['expires']<=self::now()||$this->revoked($dir,$v))throw new RuntimeException('admission_closed');
            if(!hash_equals($v['selection_sha256'],$selection)||!hash_equals($v['plan_sha256'],$plan))throw new RuntimeException('admission_mismatch');
            $v['state']='admitting';$v['handler']=$actor;self::atomic($dir.'/record.json',$v);
            return new NfqwsStrategyPickerAdmissionLease($f,fn()=>self::removeCandidate($candidate,$binding),fn($job)=>$this->accept($dir,$id,$actor,$job));
        }catch(Throwable $e){if(is_resource($f)){flock($f,LOCK_UN);fclose($f);}self::removeCandidate($candidate,$binding);throw $e;}
    }
    private function accept(string $dir,string $id,array $actor,string $job):void
    {
        self::id($job);$v=$this->record($dir,$id);if($v['state']!=='admitting'||$v['handler']!==$actor||$v['job_id']!==null)throw new RuntimeException('invalid_admission');$v['state']='accepted';$v['job_id']=$job;self::atomic($dir.'/record.json',$v);
    }
    public function revoke(string $id,string $scope):array
    {
        self::id($scope);$dir=$this->location($id);if($dir===null)throw new RuntimeException('invalid_admission');$v=$this->record($dir,$id);if(!hash_equals($v['scope'],$scope))throw new RuntimeException('admission_mismatch');
        $path=$dir.'/revoked.json';if(self::statFile($path)===null)self::atomic($path,['schema'=>1,'request_id'=>$id,'scope'=>$scope]);$this->revoked($dir,$v);
        $f=self::lock($dir);try{$closed=flock($f,LOCK_EX|LOCK_NB);if($closed){$v=$this->record($dir,$id);$v['state']='closed';self::atomic($dir.'/record.json',$v);}return ['closed'=>$closed,'record'=>$v,'actors'=>$this->candidates($id,$scope)];}finally{flock($f,LOCK_UN);fclose($f);}
    }
    public function candidates(string $id,string $scope):array
    {
        $dir=$this->location($id);if(!$dir)throw new RuntimeException('invalid_admission');$r=$this->record($dir,$id);if(!hash_equals($r['scope'],$scope))throw new RuntimeException('admission_mismatch');$out=[];
        foreach(glob($dir.'/handler-*.json')as $p){$v=self::read($p);self::keys($v,['schema','request_id','scope','selection_sha256','plan_sha256','actor']);$a=$v['actor']??null;
            if(!is_array($a))throw new RuntimeException('invalid_admission');self::keys($a,['pid','ticks','boot','uid','argv','cwd']);
            if($v['schema']!==1||$v['request_id']!==$id||$v['scope']!==$scope||$v['selection_sha256']!==$r['selection_sha256']||$v['plan_sha256']!==$r['plan_sha256']||
               !is_int($a['pid'])||$a['pid']<2||!is_string($a['ticks'])||!preg_match('/^[0-9]+$/D',$a['ticks'])||$a['boot']!==$r['boot']||$a['uid']!==0||
               !is_array($a['argv'])||!array_is_list($a['argv'])||!$a['argv']||!is_string($a['cwd'])||$p!==$dir.'/handler-'.$a['pid'].'-'.$a['ticks'].'.json')throw new RuntimeException('invalid_admission');
            foreach($a['argv']as $arg)if(!is_string($arg)||str_contains($arg,"\0"))throw new RuntimeException('invalid_admission');$out[]=$a;
        }return $out;
    }
}
final class NfqwsStrategyPickerAdmissionLease
{
    public function __construct(private $lock,private mixed $removeCandidate,private mixed $accept){}
    public function accepted(string $job):void{($this->accept)($job);}
    public function release():void{if(is_resource($this->lock)){flock($this->lock,LOCK_UN);fclose($this->lock);$this->lock=null;}if($this->removeCandidate!==null){$remove=$this->removeCandidate;$this->removeCandidate=null;$remove();}}
}
