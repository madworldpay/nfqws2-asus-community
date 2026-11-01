<?php
declare(strict_types=1);
require_once __DIR__.'/platform.php';

/** Root-owned incident journal. Packet observations belong in RAM, never here. */
final class NfqwsIpHealthStore
{
    private string $directory;
    private string $runtimeDir;
    private int $owner;
    public function __construct(?string $directory=null,?string $runtimeDir=null)
    {
        $custom=$directory!==null;
        if($directory===null){
            if(NfqwsPlatform::native())$directory='/etc/nfqws2/ip-health';
            else{$opt=realpath('/opt');if($opt===false)throw new RuntimeException('storage_unavailable');$directory=$opt.'/etc/nfqws2/ip-health';}
        }
        $this->directory=rtrim($directory,'/');
        $this->runtimeDir=rtrim($runtimeDir??(NfqwsPlatform::native()?'/var/run/nfqws2-native/ip-health':'/tmp/nfqws2-asus-ip-health'),'/');
        // Explicit fixture directories use the caller's effective uid. The HTTP
        // entrypoint supplies neither path, so production always requires root.
        $this->owner=0;
        if($custom){$status=(string)@file_get_contents('/proc/self/status');if(!preg_match('/^Uid:\s+\d+\s+(\d+)/m',$status,$m))throw new RuntimeException('unsupported_runtime');$this->owner=(int)$m[1];}
    }
    public static function saneTime(int $now):bool{return $now>=1704067200&&$now<=4102444800;}
    public static function generation(string $generation):bool{return (bool)preg_match('/^[A-Za-z0-9_.:-]{1,128}$/D',$generation);}
    public static function host(string $host):bool{return strlen($host)<=253&&(bool)preg_match('/^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/D',$host);}
    public static function publicIp(string $ip):?string
    {
        $bin=@inet_pton($ip);if($bin===false)return null;$canonical=inet_ntop($bin);
        if(strlen($bin)===4){
            $n=unpack('N',$bin)[1];
            foreach([['0.0.0.0',8],['10.0.0.0',8],['100.64.0.0',10],['127.0.0.0',8],['169.254.0.0',16],['172.16.0.0',12],['192.0.0.0',24],['192.0.2.0',24],['192.168.0.0',16],['198.18.0.0',15],['198.51.100.0',24],['203.0.113.0',24],['224.0.0.0',4],['240.0.0.0',4]] as [$base,$bits]){if(($n>>(32-$bits))===(unpack('N',inet_pton($base))[1]>>(32-$bits)))return null;}
        }else{
            // Only native global unicast; exclude mapped/local, documentation,
            // transition and benchmarking ranges even where PHP accepts them.
            $first=ord($bin[0]);if(($first&0xe0)!==0x20)return null;
            $hex=bin2hex($bin);if(str_starts_with($hex,'20010db8')||str_starts_with($hex,'20010000')||str_starts_with($hex,'20010002')||str_starts_with($hex,'2002')||str_starts_with($hex,'3fff'))return null;
        }
        return $canonical;
    }
    /** Firmware owns these boundaries, whose stock modes differ from our dirs. */
    public static function systemDirectory(string $path,array $s):bool
    {
        if($s['uid']!==0)return false;
        if($path==='/tmp')return ($s['mode']&0170000)===0040000;
        if(($s['mode']&0170000)!==0120000)return false;
        $target=match($path){'/var'=>'/tmp','/var/run'=>'/tmp/run',default=>null};
        if($target===null||realpath($path)!==$target)return false;
        clearstatcache(true,'/tmp');$tmp=@lstat('/tmp');
        if($tmp===false||$tmp['uid']!==0||($tmp['mode']&0170000)!==0040000)return false;
        clearstatcache(true,$target);$t=@lstat($target);
        return $t!==false&&$t['uid']===0&&($t['mode']&0170000)===0040000&&($target==='/tmp'||($t['mode']&0022)===0);
    }
    /** /opt is the platform anchor; writable firmware mount parents are outside it. */
    private function optBoundary(string $path):?string
    {
        clearstatcache(true,'/opt');$root=realpath('/opt');
        if($root===false||$root==='/'||($path!==$root&&!str_starts_with($path,$root.'/')))return null;
        $alias=@lstat('/opt');clearstatcache(true,$root);$s=@lstat($root);
        if($alias===false||$alias['uid']!==0||!in_array($alias['mode']&0170000,[0040000,0120000],true)||$s===false||$s['uid']!==0||($s['mode']&0170000)!==0040000||($s['mode']&0022)!==0)throw new RuntimeException('invalid_state');
        return $root;
    }
    private function directory(string $path,bool $create,bool $ram=false):bool
    {
        if($path===''||$path[0]!=='/'||str_contains($path,"\0")||preg_match('~(?:^|/)\.\.?(?:/|$)~',$path))throw new RuntimeException('invalid_state');
        $boundary=$ram?null:$this->optBoundary($path);
        for($p=$path;$p!=='/';$p=dirname($p)){
            clearstatcache(true,$p);$s=@lstat($p);if($s===false)continue;
            if(self::systemDirectory($p,$s)){if($p==='/tmp')break;continue;}
            if(($s['mode']&0170000)!==0040000||!in_array($s['uid'],[0,$this->owner],true)||($s['mode']&0022)!==0)throw new RuntimeException('invalid_state');
            if($p===$boundary)break;
        }
        if(!is_dir($path)){if(!$create)return false;$mask=umask(0077);try{if(!@mkdir($path,0700,true)&&!is_dir($path))throw new RuntimeException('storage_unavailable');}finally{umask($mask);}}
        $s=lstat($path);if($s['uid']!==$this->owner||!in_array($s['mode']&0777,$ram?[0700,0755]:[0700],true))throw new RuntimeException('invalid_state');return true;
    }
    private function regular(string $path,int $limit):?array
    {
        clearstatcache(true,$path);$s=@lstat($path);if($s===false)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>$limit)throw new RuntimeException('invalid_state');return $s;
    }
    private function read(string $path,int $limit):?array
    {
        $before=$this->regular($path,$limit);if($before===null)return null;$f=@fopen($path,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$after=fstat($f);if($before['dev']!==$after['dev']||$before['ino']!==$after['ino'])throw new RuntimeException('invalid_state');$raw=stream_get_contents($f,$limit+1);if(!is_string($raw)||strlen($raw)>$limit)throw new RuntimeException('invalid_state');}
        finally{fclose($f);}
        try{$v=json_decode($raw,true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}if(!is_array($v))throw new RuntimeException('invalid_state');return $v;
    }
    private function write(string $path,array $value,int $limit):void
    {
        $this->regular($path,$limit);$raw=json_encode($value,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);if(strlen($raw)>$limit)throw new RuntimeException('output_limit');
        $tmp=dirname($path).'/.write-'.bin2hex(random_bytes(12));$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(@fwrite($f,$raw)!==strlen($raw)||!@fflush($f)||(function_exists('fsync')&&!@fsync($f)))throw new RuntimeException('insufficient_space');fclose($f);$f=null;$this->regular($path,$limit);if(!@rename($tmp,$path))throw new RuntimeException('storage_unavailable');}
        finally{if(is_resource($f))fclose($f);if(is_file($tmp))@unlink($tmp);}
    }
    private function locked(string $dir,bool $write,callable $fn,bool $ram=false):mixed
    {
        if(!$this->directory($dir,$write,$ram))return $fn();$path=$dir.'/state.lock';$before=$this->regular($path,0);
        if($before===null&&!$write)return $fn();$mask=umask(0077);try{$f=@fopen($path,$before===null?'x+b':'r+b');}finally{umask($mask);}
        if(!$f){$before=$this->regular($path,0);$f=@fopen($path,'r+b');}if(!$f)throw new RuntimeException('invalid_state');
        try{$actual=fstat($f);$current=$this->regular($path,0);if($current===null||$actual['ino']!==$current['ino']||$actual['dev']!==$current['dev'])throw new RuntimeException('invalid_state');$deadline=hrtime(true)+500000000;
            do{if(flock($f,($write?LOCK_EX:LOCK_SH)|LOCK_NB))return $fn();if(hrtime(true)>=$deadline)throw new RuntimeException('busy');usleep(10000);}while(true);
        }finally{flock($f,LOCK_UN);fclose($f);}
    }
    private static function keys(array $value,array $expected):bool{$keys=array_keys($value);sort($keys);sort($expected);return $keys===$expected;}
    private static function emptyState():array{return ['schema_version'=>1,'enabled'=>true,'generation'=>'none','entries'=>[],'history'=>[],'recheck'=>[]];}
    private function state():array
    {
        $v=$this->read($this->directory.'/bans.json',524288)??self::emptyState();
        if(!self::keys($v,['schema_version','enabled','generation','entries','history','recheck'])||$v['schema_version']!==1||!is_bool($v['enabled'])||!is_string($v['generation'])||!self::generation($v['generation'])||!is_array($v['entries'])||count($v['entries'])>512||!is_array($v['history'])||count($v['history'])>512||!is_array($v['recheck'])||!array_is_list($v['recheck'])||count($v['recheck'])>512)throw new RuntimeException('invalid_state');
        foreach($v['entries'] as $id=>$e){if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id)||!is_array($e)||!self::keys($e,['id','ip','port','host','until','first_seen','incident','last_check','check_state','generation','successes'])||$e['id']!==$id||!is_string($e['ip'])||self::publicIp($e['ip'])!==$e['ip']||$e['port']!==443||!is_string($e['host'])||!self::host($e['host'])||!is_int($e['until'])||!is_int($e['first_seen'])||!self::saneTime($e['first_seen'])||$e['until']<$e['first_seen']||$e['until']>$e['first_seen']+604800||!in_array($e['incident'],[1,2],true)||($e['last_check']!==null&&(!is_int($e['last_check'])||!self::saneTime($e['last_check'])))||!in_array($e['check_state'],['due','checking','silent','replied','unknown'],true)||!is_string($e['generation'])||!self::generation($e['generation'])||!is_int($e['successes'])||$e['successes']<0||$e['successes']>2)throw new RuntimeException('invalid_state');}
        foreach($v['history'] as $ip=>$at)if(!is_string($ip)||self::publicIp($ip)!==$ip||!is_int($at)||!self::saneTime($at))throw new RuntimeException('invalid_state');
        foreach($v['recheck'] as $id)if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id)||!isset($v['entries'][$id]))throw new RuntimeException('invalid_state');return $v;
    }
    private static function prune(array &$v,int $now):void
    {
        if(self::saneTime($now)){foreach($v['entries'] as $id=>$entry)if($entry['until']<=$now)unset($v['entries'][$id]);foreach($v['history'] as $ip=>$at)if($at<$now-2592000)unset($v['history'][$ip]);}
        if(count($v['entries'])>512){uasort($v['entries'],fn($a,$b)=>$b['first_seen']<=>$a['first_seen']);$v['entries']=array_slice($v['entries'],0,512,true);}
        if(count($v['history'])>512){arsort($v['history']);$v['history']=array_slice($v['history'],0,512,true);}
        $v['recheck']=array_values(array_unique(array_filter($v['recheck'],fn($id)=>isset($v['entries'][$id]))));
    }
    /** Internal controller transaction; serializes changes, never network I/O. */
    public function transaction(callable $fn,?int $now=null):mixed
    {
        $now??=time();return $this->locked($this->directory,true,function()use($fn,$now){$old=$this->state();$v=$old;self::prune($v,$now);$result=$fn($v);self::prune($v,$now);if($v!==$old)$this->write($this->directory.'/bans.json',$v,524288);return $result;});
    }
    public function view(?int $now=null):array{$now??=time();return $this->locked($this->directory,false,function()use($now){$v=$this->state();self::prune($v,$now);return $v;});}
    /** A separate RAM journal prevents flash writes for each flow observation. */
    public function evidence(callable $fn):mixed
    {return $this->locked($this->runtimeDir,true,function()use($fn){$v=$this->read($this->runtimeDir.'/evidence.json',262144)??[];$result=$fn($v);$this->write($this->runtimeDir.'/evidence.json',$v,262144);return $result;},true);}
    private static function publicEntries(array $v,int $now):array
    {
        if(!self::saneTime($now))return [];$out=[];foreach($v['entries'] as $e){if($e['until']<=$now||$e['first_seen']>$now+5)continue;if($e['generation']!==$v['generation']&&!in_array($e['id'],$v['recheck'],true))$e['check_state']='unknown';unset($e['generation'],$e['successes']);$out[]=$e;}usort($out,fn($a,$b)=>strcmp($a['ip'],$b['ip']));return $out;
    }
    private static function revision(array $v,int $now):string
    {
        // Visible check metadata binds a queued action and its completed result,
        // so replaying a lost recheck reply cannot enqueue another probe.
        return hash('sha256',json_encode([$v['enabled'],$v['generation'],self::publicEntries($v,$now)],JSON_THROW_ON_ERROR));
    }
    private function runtime(int $now):array
    {
        $fallback=['state'=>'stopped','code'=>null,'updated_at'=>null,'dns'=>'unavailable'];
        try{if(!$this->directory($this->runtimeDir,false,true))return $fallback;$v=$this->read($this->runtimeDir.'/runtime-status.json',4096);if($v===null)return $fallback;
            if(!self::keys($v,['state','code','updated_at','dns'])||!in_array($v['state'],['active','starting','stopped','unavailable'],true)||($v['code']!==null&&(!is_string($v['code'])||!preg_match('/^[a-z0-9_]{1,64}$/D',$v['code'])))||($v['updated_at']!==null&&(!is_int($v['updated_at'])||!self::saneTime($v['updated_at'])))||!in_array($v['dns'],['router_udp','unavailable'],true))throw new RuntimeException('invalid_state');
            if(in_array($v['state'],['active','starting'],true)&&(!self::saneTime($now)||$v['updated_at']===null||$v['updated_at']>$now+5||$now-$v['updated_at']>20))return ['state'=>'unavailable','code'=>'controller_stale','updated_at'=>$v['updated_at'],'dns'=>'unavailable'];return $v;
        }catch(Throwable $e){return ['state'=>'unavailable','code'=>'invalid_state','updated_at'=>null,'dns'=>'unavailable'];}
    }
    public function status(?int $now=null):array{$now??=time();$v=$this->view($now);return ['schema_version'=>1,'revision'=>self::revision($v,$now),'enabled'=>$v['enabled'],'runtime'=>$this->runtime($now),'entries'=>self::publicEntries($v,$now)];}
    private function mutation(string $revision,int $now,callable $fn,bool $publish=true,bool $resetEvidence=false,bool $persistSelection=false):array
    {
        if(!preg_match('/^[a-f0-9]{64}$/D',$revision))throw new RuntimeException('invalid_request');
        $this->locked($this->directory,true,function()use($revision,$now,$fn,$publish,$resetEvidence,$persistSelection){$old=$this->state();$v=$old;self::prune($v,$now);if(!hash_equals(self::revision($v,$now),$revision))throw new RuntimeException('stale_revision');$fn($v);self::prune($v,$now);if($v!==$old||($persistSelection&&!file_exists($this->directory.'/bans.json')))$this->write($this->directory.'/bans.json',$v,524288);if($publish){$effective=$v;if($this->runtime($now)['state']!=='active')$effective['enabled']=false;$this->publishRaw(self::formatManifest($effective,$now,$v['generation']));}if($resetEvidence&&$this->directory($this->runtimeDir,false,true))$this->evidence(function(array &$ram){$ram=[];});});return $this->status($now);
    }
    public function configure(bool $enabled,string $revision,?int $now=null):array{return $this->mutation($revision,$now??time(),function(array &$v)use($enabled){$v['enabled']=$enabled;},true,!$enabled,true);}
    public function remove(string $id,string $revision,?int $now=null):array
    {if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');return $this->mutation($revision,$now??time(),function(array &$v)use($id){if(!isset($v['entries'][$id]))throw new RuntimeException('not_found');unset($v['entries'][$id]);});}
    public function clear(string $revision,?int $now=null):array{return $this->mutation($revision,$now??time(),function(array &$v){$v['entries']=[];$v['recheck']=[];});}
    public function recheck(string $id,string $revision,?int $now=null):array
    {if($id!=='all'&&!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');return $this->mutation($revision,$now??time(),function(array &$v)use($id){$ids=$id==='all'?array_keys($v['entries']):[$id];foreach($ids as $entry){if(!isset($v['entries'][$entry]))throw new RuntimeException('not_found');$v['entries'][$entry]['check_state']='due';}$v['recheck']=array_values(array_unique(array_merge($v['recheck'],$ids)));},false);}
    private static function formatManifest(array $v,int $now,string $generation):string
    {
        if(!self::saneTime($now))return "IPHEALTH1\nexpires $now\nenabled 0\n";
        $enabled=$v['enabled']&&self::generation($generation);$out="IPHEALTH1\nexpires ".($now+15)."\nenabled ".($enabled?'1':'0')."\n";if($enabled&&$v['generation']===$generation)foreach($v['entries'] as $entry)if($entry['generation']===$generation&&$entry['until']>$now&&$entry['first_seen']<=$now+5)$out.='ban '.$entry['ip'].' '.$entry['until']."\n";return $out;
    }
    public function manifest(int $now,string $generation):string
    {
        try{return self::formatManifest($this->view($now),$now,$generation);}
        catch(Throwable $e){return "IPHEALTH1\nexpires $now\nenabled 0\n";}
    }
    private function manifestFile():string
    {
        $path=$this->runtimeDir.'/active.txt';clearstatcache(true,$path);$s=@lstat($path);
        if($s!==false&&(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||($s['mode']&0777)!==0644||$s['size']>65536))throw new RuntimeException('invalid_state');return $path;
    }
    private function publishRaw(string $raw):void
    {
        if(!$this->directory($this->runtimeDir,false,true))return;if(strlen($raw)>65536)throw new RuntimeException('output_limit');$path=$this->manifestFile();$tmp=$this->runtimeDir.'/.active-'.bin2hex(random_bytes(12));$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(@fwrite($f,$raw)!==strlen($raw)||!@fflush($f)||!@chmod($tmp,0644))throw new RuntimeException('insufficient_space');fclose($f);$f=null;$this->manifestFile();if(!@rename($tmp,$path))throw new RuntimeException('storage_unavailable');}
        finally{if(is_resource($f))fclose($f);if(is_file($tmp))@unlink($tmp);}
    }
    /** Publish under the same lock as web mutations; never republish a cached
     * manifest after a concurrent disable/remove/clear has completed. */
    public function publishManifest(int $now,string $generation):void
    {
        $this->locked($this->directory,true,function()use($now,$generation){try{$v=$this->state();$raw=self::formatManifest($v,$now,$generation);}catch(Throwable $e){$this->publishRaw("IPHEALTH1\nexpires $now\nenabled 0\n");throw $e;}$this->publishRaw($raw);});
    }
    /** RAM-only readiness, written by the root worker, never by a packet hook. */
    public function runtimeStatus(string $state,?string $code,int $now,string $dns='unavailable'):void
    {
        if(!in_array($state,['active','starting','stopped','unavailable'],true)||($code!==null&&!preg_match('/^[a-z0-9_]{1,64}$/D',$code))||!in_array($dns,['router_udp','unavailable'],true))throw new RuntimeException('invalid_state');
        if(!$this->directory($this->runtimeDir,false,true))return;
        $this->write($this->runtimeDir.'/runtime-status.json',['state'=>$state,'code'=>$code,'updated_at'=>self::saneTime($now)?$now:null,'dns'=>$dns],4096);
    }
    public function publishInactive(int $now):void
    {$this->publishRaw("IPHEALTH1\nexpires $now\nenabled 0\n");}
}
