<?php
/** INTERNAL raw depot for paired pre-input/source callbacks. The caller keeps
 * the existing engine/shared-writer locks and supplies its original checkpoint.
 * Files are captures, never accepted results. No HTTP, Start, cleanup, native
 * semantic validation, new clock or mutation/Apply/export authority lives here.
 */
final class NfqwsStrategyPickerNativeCapture
{
    private const CAPS=['index'=>131072,'options'=>131072,'native'=>1048576];
    private const SLOT=1310720;
    private const META=32768;
    private const ATTEMPTS=6; // Two existing warm+two-measured trials, no retries.
    private const TOTAL=8388608;
    private Closure $checkpoint;
    public function __construct(private NfqwsStrategyPickerState $store,callable $checkpoint,private int $owner=0)
    {if($store->owner()!==$owner)throw new RuntimeException('storage_unavailable');$this->checkpoint=Closure::fromCallable($checkpoint);}
    private static function encode(array $v):string
    {return json_encode($v,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);}
    private static function fields(array $s):array
    {return array_intersect_key($s,array_flip(['dev','ino','mode','nlink','uid','gid','size','mtime','ctime']));}
    private static function hex(mixed $s,int $n=64):bool
    {return is_string($s)&&preg_match('/^[a-f0-9]{'.$n.'}$/D',$s)===1;}
    private static function uuid(mixed $s):bool
    {return is_string($s)&&preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/D',$s)===1;}
    private function path(string $name):string
    {
        if($name!=='native-capture.lock'&&!preg_match('/^native-[a-f0-9]{32}-[a-f0-9-]{36}\.(?:slot|intent\.json|capture\.json)$/D',$name))throw new RuntimeException('invalid_request');
        $root=dirname($this->store->path('state.json'));clearstatcache(true,$root);$s=@lstat($root);
        if(!$s||($s['mode']&0177777)!==0040700||$s['uid']!==$this->owner)throw new RuntimeException('storage_unavailable');
        return class_exists('NfqwsDeviceProfilesPaths',false)?NfqwsDeviceProfilesPaths::guard($root,$name,$this->owner):NfqwsPlatform::guardFile($root,$name,$this->owner);
    }
    private function file(string $path,int $cap):array
    {
        clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||($s['mode']&0177777)!==0100600||$s['uid']!==$this->owner||$s['nlink']!==1||$s['size']>$cap)throw new RuntimeException('storage_unavailable');
        $f=@fopen($path,'rbe');if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(self::fields(fstat($f))!==self::fields($s))throw new RuntimeException('source_changed');
            $raw=stream_get_contents($f,$cap+1);clearstatcache(true,$path);$after=@lstat($path);
            if(!is_string($raw)||strlen($raw)!==$s['size']||self::fields(fstat($f))!==self::fields($s)||!$after||self::fields($after)!==self::fields($s))throw new RuntimeException('source_changed');
        }finally{fclose($f);}
        return ['raw'=>$raw,'bytes'=>strlen($raw),'sha256'=>hash('sha256',$raw),'metadata'=>self::fields($s)];
    }
    private function syncDirectory():void
    {$f=fopen(dirname($this->store->path('state.json')),'r');try{if(!$f||!fsync($f))throw new RuntimeException('insufficient_space');}finally{if(is_resource($f))fclose($f);}}
    private static function write($f,string $raw):void
    {for($offset=0;$offset<strlen($raw);$offset+=$n){$n=fwrite($f,substr($raw,$offset,65536));if(!is_int($n)||$n<=0)throw new RuntimeException('insufficient_space');}}
    private function create(string $name,string $raw,int $cap):array
    {
        if(strlen($raw)>$cap)throw new RuntimeException('output_limit');$path=$this->path($name);
        clearstatcache(true,$path);if(@lstat($path)!==false)throw new RuntimeException('request_conflict');
        $mask=umask(0077);try{$f=@fopen($path,'xbe');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('storage_unavailable');
        try{self::write($f,$raw);if(!fflush($f)||!fsync($f))throw new RuntimeException('insufficient_space');}finally{fclose($f);}
        $this->syncDirectory();$v=$this->file($this->path($name),$cap);
        if($v['raw']!==$raw)throw new RuntimeException('source_changed');return $v;
    }
    private function locked(callable $fn):mixed
    {
        $path=$this->path('native-capture.lock');clearstatcache(true,$path);
        if(@lstat($path)===false)$this->create('native-capture.lock','',0);
        $pin=$this->file($path,0);$f=@fopen($path,'r+be');if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(self::fields(fstat($f))!==$pin['metadata']||!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');
            if($this->file($this->path('native-capture.lock'),0)!==$pin)throw new RuntimeException('source_changed');return $fn();
        }finally{flock($f,LOCK_UN);fclose($f);}
    }
    private function overwrite(string $name,array $expected,string $raw,int $cap):array
    {
        $path=$this->path($name);$before=$this->file($path,$cap);$pin=$before;unset($pin['raw']);
        if($pin!==$expected||strlen($raw)!==$before['bytes'])throw new RuntimeException('source_changed');
        $f=fopen($path,'r+be');if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(self::fields(fstat($f))!==$pin['metadata'])throw new RuntimeException('source_changed');
            self::write($f,$raw);if(!fflush($f)||!fsync($f))throw new RuntimeException('insufficient_space');
        }finally{fclose($f);}
        $after=$this->file($this->path($name),$cap);
        foreach(['dev','ino','mode','nlink','uid','gid','size']as $key)if($after['metadata'][$key]!==$pin['metadata'][$key])throw new RuntimeException('source_changed');
        if($after['raw']!==$raw)throw new RuntimeException('source_changed');return $after;
    }
    private function working(string $request,array $input,?string $nativeJob=null):array
    {
        if(!self::uuid($request))throw new RuntimeException('invalid_request');
        $keys=array_keys($input);sort($keys);$expected=['mode','parent_id','parent_request_id','parent_boot','profile_id','source','recipe','config_sha256','resource_fingerprint_sha256','resource_binding_scope','warmup','repeat'];sort($expected);
        if($keys!==$expected||$input['mode']!=='picker-trial-native-input-v1'||!self::hex($input['parent_id'],32)||!self::hex($input['parent_request_id'],32)||
            !is_string($input['parent_boot'])||
            !(self::hex($input['profile_id'],32)||(class_exists('NfqwsDeviceProfilesLibrary',false)&&NfqwsDeviceProfilesLibrary::validId($input['profile_id'])))||
            !in_array($input['source'],['current','synthesis'],true)||
            !self::hex($input['config_sha256'])||!self::hex($input['resource_fingerprint_sha256'])||
            $input['resource_binding_scope']!=='existing_fingerprint_excludes_mutable_AUTO'||!is_bool($input['warmup'])||
            ($input['warmup']?$input['repeat']!==null:!in_array($input['repeat'],[1,2],true))||
            ($input['recipe']!==null&&!is_array($input['recipe'])&&!(is_string($input['recipe'])&&preg_match('/^s-[a-f0-9]{16}$/D',$input['recipe'])===1))||strlen(self::encode($input))>8192)throw new RuntimeException('invalid_request');
        // Void completion of the original guard/checkpoint is required. Its
        // return value, input digests and this journal are not physical proof.
        if(($this->checkpoint)()!==null)throw new RuntimeException('invalid_request');
        $path=$this->store->path('state.json');$j=json_decode($this->file($path,1048576)['raw'],true,32,JSON_THROW_ON_ERROR);
        if(!is_array($j)||($j['state']??null)!=='running'||($j['id']??null)!==$input['parent_id']||($j['request_id']??null)!==$input['parent_request_id']||
            ($j['boot']??null)!==$input['parent_boot']||$j['boot']!==AsusUpdateStore::boot()||($j['current']??null)!==$input['config_sha256']||
            ($j['resources_sha256']??null)!==$input['resource_fingerprint_sha256']||($j['dpi_request']??null)!==$request||
            $nativeJob!==null&&($j['dpi_job']??null)!==$nativeJob)throw new RuntimeException('source_changed');
        foreach([$j['trial_profile']??null,$j['engine_trial']['profile']??null]as $activeProfile)
            if($activeProfile!==null&&$activeProfile!==$input['profile_id'])throw new RuntimeException('source_changed');
        // Older raw captures used an opaque 32-hex ID. Current trials carry
        // the saved or stock ID and must resolve it in this job's library.
        if(!self::hex($input['profile_id'],32))$this->store->profileLibrary($j)->entry($input['profile_id']);
        try{$deadline=NfqwsStrategyPickerBudget::overallDeadline($j);}catch(Throwable $e){throw new RuntimeException('source_changed',0,$e);}
        if($deadline!==null&&AsusUpdateStore::uptime()>=$deadline)throw new RuntimeException('timed_out');return $j;
    }
    private function prefix(string $request,array $input):string
    {return 'native-'.$input['parent_id'].'-'.$request;}
    private function admission():void
    {
        $root=dirname($this->store->path('state.json'));$d=opendir($root);if(!$d)throw new RuntimeException('storage_unavailable');
        $entries=0;$attempts=[];$accounted=0;
        try{while(false!==($name=readdir($d))){if(++$entries>512)throw new RuntimeException('output_limit');
            if(!str_starts_with($name,'native-')||$name==='native-capture.lock')continue;
            if(!preg_match('/^(native-[a-f0-9]{32}-[a-f0-9-]{36})\.(slot|intent\.json|capture\.json)$/D',$name,$m))throw new RuntimeException('storage_unavailable');
            $v=$this->file($this->path($name),$m[2]==='slot'?self::SLOT:self::META);
            $attempts[$m[1]]=true;$accounted+=$v['bytes'];
        }}finally{closedir($d);}
        // Include both immutable metadata records for every partial reservation,
        // even when its capture record has not been written. No orphan cleanup.
        $reserved=count($attempts)*(self::SLOT+2*self::META);
        if(count($attempts)>=self::ATTEMPTS||max($accounted,$reserved)+self::SLOT+2*self::META>self::TOTAL)throw new RuntimeException('output_limit');
        $free=@disk_free_space($root);if($free===false||$free<1048576+self::SLOT+2*self::META)throw new RuntimeException('insufficient_space');
    }
    public function reserve(string $request,array $input):void
    {
        $j=$this->working($request,$input);$prefix=$this->prefix($request,$input);
        $this->locked(function()use($j,$prefix,$request,$input):void{
            foreach(['slot','intent.json','capture.json']as $suffix){$p=$this->path($prefix.'.'.$suffix);clearstatcache(true,$p);if(@lstat($p)!==false)throw new RuntimeException('request_conflict');}
            $this->admission();
            // Actual non-sparse bytes, fsync and published-inode readback BEFORE
            // possible input. ftruncate/free-space guesses are not reservation.
            $slot=$this->create($prefix.'.slot',str_repeat("\0",self::SLOT),self::SLOT);
            $st=lstat($this->path($prefix.'.slot'));if(!isset($st['blocks'])||$st['blocks']*512<self::SLOT)throw new RuntimeException('insufficient_space');
            $slotRef=$slot;unset($slotRef['raw']);$slotRef['name']=$prefix.'.slot';
            $pending=self::encode(['schema'=>1,'state'=>'capture_pending','accepted'=>false,'native_request'=>$request,'input_sha256'=>hash('sha256',self::encode($input))]);
            $capture=$this->create($prefix.'.capture.json',str_pad($pending,self::META,' '),self::META);
            $st=lstat($this->path($prefix.'.capture.json'));if(!isset($st['blocks'])||$st['blocks']*512<self::META)throw new RuntimeException('insufficient_space');
            unset($capture['raw']);$capture['name']=$prefix.'.capture.json';
            $intent=['schema'=>1,'state'=>'reserved_unaccepted','native_request'=>$request,'input'=>$input,
                'input_sha256'=>hash('sha256',self::encode($input)),'phase'=>$j['phase']??null,'slot'=>$slotRef,'capture'=>$capture];
            $this->create($prefix.'.intent.json',self::encode($intent),self::META);
            $after=$this->working($request,$input);
            if(($after['phase']??null)!==($j['phase']??null)||($after['dpi_job']??null)!==($j['dpi_job']??null))throw new RuntimeException('source_changed');
        });
    }
    public function capture(array $snapshot,array $input):array
    {
        $job=$snapshot['job']??null;$request=$job['request_id']??null;$id=$job['id']??null;
        if(!self::uuid($request)||!self::hex($id,32))throw new RuntimeException('source_changed');
        $j=$this->working($request,$input,$id);$prefix=$this->prefix($request,$input);
        return $this->locked(function()use($snapshot,$input,$job,$request,$id,$j,$prefix):array{
            $captureFile=$this->file($this->path($prefix.'.capture.json'),self::META);
            $pending=json_decode($captureFile['raw'],true,32,JSON_THROW_ON_ERROR);
            if(($pending['state']??null)==='captured_unaccepted')throw new RuntimeException('request_conflict');
            if(($pending['state']??null)!=='capture_pending')throw new RuntimeException('source_changed');
            $intentFile=$this->file($this->path($prefix.'.intent.json'),self::META);$intent=json_decode($intentFile['raw'],true,32,JSON_THROW_ON_ERROR);
            if(($intent['schema']??null)!==1||($intent['state']??null)!=='reserved_unaccepted'||($intent['native_request']??null)!==$request||
                ($intent['input']??null)!==$input||($intent['input_sha256']??null)!==hash('sha256',self::encode($input))||
                ($intent['phase']??null)!==($j['phase']??null)||($intent['slot']['name']??null)!==$prefix.'.slot'||
                ($intent['capture']['name']??null)!==$prefix.'.capture.json')throw new RuntimeException('source_changed');
            $capturePin=$captureFile;unset($capturePin['raw']);$expectedCapture=$intent['capture'];unset($expectedCapture['name']);
            if($capturePin!==$expectedCapture)throw new RuntimeException('source_changed');
            if(($snapshot['mode']??null)!=='dpi-native-source-snapshot-v1'||($job['state']??null)!=='completed'||($job['kind']??null)!=='run'||
                ($job['boot_id']??null)!==$input['parent_boot']||!empty($job['result_deleted']))throw new RuntimeException('source_changed');
            $artifacts=[];$offset=0;
            foreach(self::CAPS as $kind=>$cap){$a=$snapshot[$kind]??null;
                if(!is_array($a)||!is_string($a['raw']??null)||!is_int($a['bytes']??null)||$a['bytes']<1||$a['bytes']>$cap||strlen($a['raw'])!==$a['bytes']||
                    ($a['sha256']??null)!==hash('sha256',$a['raw'])||!is_array($a['metadata']??null)||count($a['metadata'])!==9||
                    ($a['metadata']['uid']??null)!==$this->owner||($a['metadata']['mode']??0)!==0100600||($a['metadata']['nlink']??null)!==1||($a['metadata']['size']??null)!==$a['bytes'])throw new RuntimeException('source_changed');
                $artifacts[$kind]=['offset'=>$offset,'bytes'=>$a['bytes'],'sha256'=>$a['sha256'],'source_metadata'=>$a['metadata']];$offset+=$a['bytes'];
            }
            $index=json_decode($snapshot['index']['raw'],true,32,JSON_THROW_ON_ERROR);
            if(($index['jobs'][$id]??null)!==$job||($job['params']['options_digest']??null)!==$snapshot['options']['sha256'])throw new RuntimeException('source_changed');
            $slotPath=$this->path($prefix.'.slot');$slot=$this->file($slotPath,self::SLOT);$expected=$intent['slot'];unset($expected['name']);
            $pin=$slot;unset($pin['raw']);if($pin!==$expected||$slot['bytes']!==self::SLOT||$slot['raw']!==str_repeat("\0",self::SLOT))throw new RuntimeException('source_changed');
            unset($slot['raw']);$f=fopen($slotPath,'r+be');if(!$f)throw new RuntimeException('storage_unavailable');
            try{if(self::fields(fstat($f))!==$pin['metadata'])throw new RuntimeException('source_changed');
                foreach(self::CAPS as $kind=>$_)self::write($f,$snapshot[$kind]['raw']);
                if(!fflush($f)||!fsync($f))throw new RuntimeException('insufficient_space');
            }finally{fclose($f);}
            $retained=$this->file($this->path($prefix.'.slot'),self::SLOT);
            foreach(['dev','ino','mode','nlink','uid','gid','size']as $key)if($retained['metadata'][$key]!==$pin['metadata'][$key])throw new RuntimeException('source_changed');
            foreach($artifacts as $kind=>$a)if(substr($retained['raw'],$a['offset'],$a['bytes'])!==$snapshot[$kind]['raw'])throw new RuntimeException('source_changed');
            if(substr($retained['raw'],$offset)!==str_repeat("\0",self::SLOT-$offset))throw new RuntimeException('source_changed');
            unset($retained['raw']);$retained['name']=$prefix.'.slot';
            $value=['schema'=>1,'state'=>'captured_unaccepted','accepted'=>false,'native_job_id'=>$id,'native_request'=>$request,
                'input'=>$input,'intent_sha256'=>$intentFile['sha256'],'slot'=>$retained,'artifacts'=>$artifacts];
            $recordRaw=self::encode($value);if(strlen($recordRaw)>self::META)throw new RuntimeException('output_limit');
            $record=$this->overwrite($prefix.'.capture.json',$expectedCapture,str_pad($recordRaw,self::META,' '),self::META);
            // Captured bytes survive guard/source/post-result errors. Returning
            // this reference is NOT acceptance or a successful native result.
            $after=$this->working($request,$input,$id);
            if(($after['phase']??null)!==($j['phase']??null))throw new RuntimeException('source_changed');
            return ['name'=>$prefix.'.capture.json','sha256'=>$record['sha256'],'metadata'=>$record['metadata'],'state'=>'captured_unaccepted','accepted'=>false];
        });
    }
}
