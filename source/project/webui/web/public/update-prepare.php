<?php
require_once __DIR__.'/update-store.php';
require_once __DIR__.'/update-manifest.php';
require_once __DIR__.'/update-transport.php';
require_once __DIR__.'/update-deadline.php';
require_once __DIR__.'/support-report-platform.php';

require_once __DIR__.'/update-package.php';

final class AsusUpdateSnapshot
{
    private static function ownerAllowed(string $relative,array $stat,int $owner): bool
    {
        return $stat['uid']===$owner||($stat['uid']===65534&&($stat['mode']&0170000)===0100000&&preg_match('~^etc/nfqws2/lists/[a-zA-Z0-9_.-]+$~D',$relative)===1);
    }
    private static function collect(string $opt,int $owner): array
    {
        AsusUpdateStore::noLinks($opt);$files=[];$total=0;
        $scan=function(string $relative)use(&$scan,&$files,&$total,$opt,$owner){$p=$opt.'/'.$relative;AsusUpdateStore::noLinks($p);$s=@lstat($p);if(!$s)return;
            if(!self::ownerAllowed($relative,$s,$owner))throw new RuntimeException('invalid_state');$type=$s['mode']&0170000;
            if($type===0040000){$names=@scandir($p);if(!is_array($names))throw new RuntimeException('invalid_state');foreach($names as $name)if($name!=='.'&&$name!=='..'){if(!preg_match('/^[a-zA-Z0-9_.-]{1,128}$/D',$name))throw new RuntimeException('invalid_state');$scan($relative.'/'.$name);}return;}
            if($type!==0100000||$s['nlink']!==1||($s['mode']&07000)!==0||$s['size']>8388608||count($files)>=512)throw new RuntimeException('invalid_state');$total+=$s['size'];if($total>33554432)throw new RuntimeException('output_limit');
            $hash=hash_file('sha256',$p);if($hash===false)throw new RuntimeException('invalid_state');$files[$relative]=['mode'=>$s['mode']&0777,'size'=>$s['size'],'sha256'=>$hash,'uid'=>$s['uid'],'gid'=>$s['gid']];
        };
        $scan('etc/nfqws2');foreach(['auth.json','support-relay.json','update-channel.json'] as $n)$scan('etc/nfqws-asus-web/'.$n);ksort($files);
        // Only proven stock resources may change with a package. Custom files
        // remain settings; a customized stock file refuses preparation.
        $resources=[];$baseline=$opt.'/share/nfqws2-asus/report-baseline.json';AsusUpdateStore::noLinks($baseline);$bs=@lstat($baseline);
        if($bs){if(($bs['mode']&0170000)!==0100000||$bs['uid']!==$owner||$bs['nlink']!==1||($bs['mode']&0022)!==0||$bs['size']>131072)throw new RuntimeException('invalid_state');
            try{$b=json_decode(file_get_contents($baseline),true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
            if(($b['schema_version']??null)!==1||!is_array($b['resources']??null)||count($b['resources'])>512)throw new RuntimeException('invalid_state');
            foreach($b['resources'] as $name=>$r){if(!preg_match('~^(lua|blob)/[a-zA-Z0-9_.-]+$~D',(string)$name)||!is_array($r)||!is_int($r['bytes']??null)||$r['bytes']<0||!preg_match('/^[a-f0-9]{64}$/D',$r['sha256']??''))throw new RuntimeException('invalid_state');
                $path='etc/nfqws2/'.(str_starts_with($name,'blob/')?'blobs/'.substr($name,5):$name);$f=$files[$path]??null;
                if(!$f||$f['size']!==$r['bytes']||$f['sha256']!==$r['sha256'])throw new RuntimeException('settings_changed');$resources[$path]=$r;
            }ksort($resources);
        }
        return ['files'=>$files,'total'=>$total,'package_resources'=>$resources];
    }
    public static function estimate(string $opt,int $owner=0): int {return self::collect($opt,$owner)['total'];}
    public static function capture(string $opt,string $destination,int $owner=0): array
    {
        $manifest=self::collect($opt,$owner);AsusUpdateStore::noLinks($destination);if(file_exists($destination)||is_link($destination))throw new RuntimeException('invalid_state');
        $free=@disk_free_space(dirname($destination));if($free===false||$free<$manifest['total']+16777216)throw new RuntimeException('insufficient_space');
        $mask=umask(0077);try{if(!mkdir($destination,0700))throw new RuntimeException('invalid_state');
            foreach($manifest['files'] as $name=>$item){$p=$destination.'/'.$name;if(!is_dir(dirname($p))&&!mkdir(dirname($p),0700,true))throw new RuntimeException('invalid_state');
                $in=@fopen($opt.'/'.$name,'rb');$out=@fopen($p,'xb');if(!$in||!$out)throw new RuntimeException('invalid_state');try{$s=fstat($in);if(($s['mode']&0170000)!==0100000||$s['uid']!==$item['uid']||$s['gid']!==$item['gid']||$s['nlink']!==1||stream_copy_to_stream($in,$out,$item['size']+1)!==$item['size']||!fflush($out))throw new RuntimeException('settings_changed');}finally{fclose($in);fclose($out);}if(!chmod($p,$item['mode'])||hash_file('sha256',$p)!==$item['sha256'])throw new RuntimeException('settings_changed');
            }
            $raw=json_encode($manifest,JSON_THROW_ON_ERROR);$f=fopen($destination.'/snapshot.json','xb');if(!$f)throw new RuntimeException('invalid_state');try{if(fwrite($f,$raw)!==strlen($raw)||!fflush($f))throw new RuntimeException('insufficient_space');}finally{fclose($f);}
        }finally{umask($mask);}if(self::collect($opt,$owner)!==$manifest)throw new RuntimeException('settings_changed');return $manifest;
    }
    public static function verify(string $opt,string $destination,int $owner=0,bool $allowPackageDefaults=false): bool
    {
        AsusUpdateStore::noLinks($destination);$p=$destination.'/snapshot.json';$s=@lstat($p);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>131072)throw new RuntimeException('invalid_state');
        try{$manifest=json_decode(file_get_contents($p),true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        $current=self::collect($opt,$owner);
        if($allowPackageDefaults){$active=fn($snapshot)=>array_filter($snapshot['files'],fn($name)=>!isset($snapshot['package_resources'][$name])&&!preg_match('~^etc/nfqws2/(?:nfqws2\.conf|lists/[a-zA-Z0-9_.-]+)\.notactive$~D',$name),ARRAY_FILTER_USE_KEY);if($active($current)!==$active($manifest))throw new RuntimeException('settings_changed');}
        elseif($current!==$manifest)throw new RuntimeException('settings_changed');
        foreach($manifest['files'] as $name=>$item){if(!preg_match('~^etc/(?:nfqws2|nfqws-asus-web)/[a-zA-Z0-9_./-]+$~D',$name)||in_array('..',explode('/',$name),true))throw new RuntimeException('invalid_state');$p=$destination.'/'.$name;AsusUpdateStore::noLinks($p);$s=@lstat($p);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0777)!==$item['mode']||$s['size']!==$item['size']||hash_file('sha256',$p)!==$item['sha256'])throw new RuntimeException('invalid_state');}return true;
    }
}

/** Shared local/worker contract, with independent platform implementations. */
interface NfqwsUpdatePreparation
{
    public function environment():array;
    public function check(bool $force=false):array;
    public function cached():?array;
    public function reserveCached(string $revision,string $requestId):array;
    public function completePrepare(string $id,?callable $stage=null):array;
}

/** Preparation has no service/opkg actions. A worker may call it after detaching. */
final class AsusUpdatePrepare implements NfqwsUpdatePreparation
{
    private AsusUpdateStore $store;
    public function __construct(?AsusUpdateStore $store=null,private ?AsusUpdateSource $source=null,private array $environment=[],private ?string $publicKey=null,private ?AsusUpdateDeadline $deadline=null)
    {$this->store=$store??new AsusUpdateStore();}
    public static function code(Throwable $error): string
    {
        $known=['channel_unconfigured','invalid_channel','invalid_manifest','invalid_signature','signature_unavailable','download_failed','download_size','download_hash','timed_out','channel_auth_failed','release_changed','unsupported_abi','unsupported_version','unsupported_package','invalid_package','package_reader_unavailable','missing_dependencies','dependency_change','pending_packages','insufficient_space','settings_changed','invalid_state','output_limit','stale_revision','busy','request_conflict','missing_operation','runtime_changed','core_stop_failed','core_start_failed','web_start_failed','web_health_failed','intent_mismatch','opkg_busy','install_failed','version_mismatch','launch_failed','interrupted'];
        $known=array_merge($known,['invalid_request','consent_required','check_required','auth_required','csrf_failed','dns_restore_required','dns_restore_failed']);
        return in_array($error->getMessage(),$known,true)?$error->getMessage():'update_failed';
    }
    public function environment(): array
    {
        $opt=$this->environment['opt']??dirname(AsusDpiStore::optPath('/var'));$opt=rtrim($opt,'/');
        AsusUpdateStore::noLinks($opt);$path=$opt.'/lib/opkg/status';$s=@lstat($path);$owner=$this->environment['owner']??0;
        if(!$s||($s['mode']&0170000)!==0100000||$s['nlink']!==1||$s['uid']!==$owner||$s['size']>2097152)throw new RuntimeException('invalid_state');$status=@file_get_contents($path);if(!is_string($status))throw new RuntimeException('invalid_state');
        $db=AsusUpdatePackage::database($status);$installed=$db['nfqws2-asus']['Version']??null;if(!is_string($installed)||!preg_match('/^[0-9]+\.[0-9]+\.[0-9]+-asus[0-9]+\+b[1-9][0-9]*$/D',$installed))throw new RuntimeException('unsupported_version');
        $abi=$this->environment['abi']??null;
        if($abi===null){$text='';$configs=array_merge([$opt.'/etc/opkg.conf'],glob($opt.'/etc/opkg/*.conf')?:[]);if(count($configs)>129)throw new RuntimeException('unsupported_abi');
            foreach($configs as $p){AsusUpdateStore::noLinks($p);$s=@lstat($p);if(!$s)continue;if(($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['size']>65536)throw new RuntimeException('unsupported_abi');$raw=@file_get_contents($p);if(!is_string($raw))throw new RuntimeException('unsupported_abi');$text.=$raw."\n";}$abi=AsusReportPlatform::abi($text);}
        $machine=$this->environment['machine']??php_uname('m');$family=match($abi){'aarch64-3.10'=>'aarch64-3.10','armv7-2.6','armv7-3.2'=>'armv7',default=>null};
        if($family===null||!($family==='aarch64-3.10'&&$machine==='aarch64'||$family==='armv7'&&in_array($machine,['armv7l','armv8l'],true)))throw new RuntimeException('unsupported_abi');
        return ['opt'=>$opt,'status'=>$status,'abi'=>$abi,'machine'=>$machine,'family'=>$family,'installed'=>$installed,'owner'=>$owner,'free'=>$this->environment['free']??disk_free_space($this->store->path()),'runtime_bytes'=>$this->environment['runtime_bytes']??33554432];
    }
    private function source(): AsusUpdateSource {return $this->source??new AsusUpdateTransport();}
    private function key(): string
    {
        if($this->publicKey!==null)return $this->publicKey;$p=($this->environment['resources']??'/opt/share/nfqws2-asus').'/update-release-key.pem';if(!is_file($p))$p=dirname(__DIR__,3).'/updates/trusted-release-key.pem';$v=@file_get_contents($p);if(!is_string($v))throw new RuntimeException('signature_unavailable');return $v;
    }
    public function check(bool $force=false): array
    {
        $lease=$this->store->lease('check.lock');try{$boot=AsusUpdateStore::boot();$up=AsusUpdateStore::uptime();$raw=null;$env=null;
            try{$env=$this->environment();$cached=$this->cached();if(!$force&&$cached!==null)return $cached;
                $this->deadline?->begin(15);try{$raw=$this->source()->manifest();}finally{$this->deadline?->end();}
                $manifest=AsusPackageManifest::verify($raw['json'],$raw['signature'],$this->key());$candidate=AsusPackageManifest::candidate($manifest,$env['family'],$env['installed']);
                $result=['state'=>$candidate===null?'current':'available','code'=>null,'candidate'=>$candidate,'installed_version'=>$env['installed']];
            }catch(Throwable $e){$code=self::code($e);$result=['state'=>$code==='channel_unconfigured'?'unconfigured':'failed','code'=>$code,'candidate'=>null,'installed_version'=>$env['installed']??null];}
            $this->store->withRetryLock(function()use($result,$raw,$boot,$up,$env){
                if(in_array($result['state'],['available','current'],true)){$this->store->writeFile('manifest.json',$raw['json']);$this->store->writeFile('manifest.sig',$raw['signature']);}
                $this->store->writeFile('check.json',json_encode(['boot_id'=>$boot,'uptime'=>$up,'installed'=>$env['installed']??null,'result'=>$result],JSON_THROW_ON_ERROR));
            });return $result;
        }finally{flock($lease,LOCK_UN);fclose($lease);}
    }
    /** Pure local read; missing or expired metadata never causes network I/O. */
    public function cached(): ?array
    {
        return $this->store->withLock(function(){
            $env=$this->environment();$raw=$this->store->readFile('check.json');if($raw===null)return null;$c=json_decode($raw,true,32,JSON_THROW_ON_ERROR);$up=AsusUpdateStore::uptime();
            if(($c['boot_id']??null)!==AsusUpdateStore::boot()||($c['installed']??null)!==$env['installed']||$up<($c['uptime']??INF)||$up-$c['uptime']>=300)return null;return $c['result'];
        });
    }
    public function reserveCached(string $revision,string $requestId): array
    {
        return $this->store->withLock(function()use($revision,$requestId){
            $state=$this->store->status();foreach(array_merge($state['active']?[$state['active']]:[],$state['history']) as $job)if($job['request_id']===$requestId){if($job['revision']!==$revision)throw new RuntimeException('request_conflict');return $job;}
            $checked=$this->cached();if(($checked['state']??null)!=='available'||$checked['candidate']['revision']!==$revision)throw new RuntimeException('stale_revision');
            if(($state['active']['state']??null)==='prepared'&&$state['active']['revision']!==$revision)$this->store->update($state['active']['id'],['state'=>'interrupted','code'=>'stale_revision']);
            $job=$this->store->reserve($revision,$requestId,$checked['candidate']);
            foreach(['manifest.json','manifest.sig'] as $file)$this->store->writeFile('operations/'.$job['id'].'/'.$file,$this->store->readFile($file)??'');return $job;
        });
    }
    public function reserve(string $revision,string $requestId): array
    {
        $state=$this->store->status();foreach(array_merge($state['active']?[$state['active']]:[],$state['history']) as $job)if($job['request_id']===$requestId){if($job['revision']!==$revision)throw new RuntimeException('request_conflict');return $job;}
        $this->check(true);return $this->reserveCached($revision,$requestId);
    }
    public function prepare(string $revision,string $requestId): array
    {$job=$this->reserve($revision,$requestId);return $job['state']==='preparing'?$this->completePrepare($job['id']):$job;}
    public function completePrepare(string $id,?callable $stage=null): array
    {
        return $this->store->withOperationLock($id,function()use($id,$stage){$job=$this->store->readOperation($id);if($job['state']!=='preparing')return $job;
            try{$base='operations/'.$id;$candidate=json_decode($this->store->readFile($base.'/candidate.json')??'',true,32,JSON_THROW_ON_ERROR);$env=$this->environment();$fresh=$this->check(true);
                if($fresh['state']!=='available'||$fresh['candidate']!==$candidate)throw new RuntimeException('stale_revision');
                $estimate=AsusUpdateSnapshot::estimate($env['opt'],$env['owner']);AsusUpdatePackage::space($env['free'],$candidate['package']['size'],$estimate,$env['runtime_bytes']);
                $path=$this->store->path($base.'/package.ipk');$this->deadline?->begin(180);try{$this->source()->download($candidate['package'],$path);}finally{$this->deadline?->end();}
                AsusUpdatePackage::inspect($path,$candidate,$env['status'],$env['abi'],$env['machine']);
                $free=$this->environment['free']??disk_free_space($this->store->path());AsusUpdatePackage::space($free,0,$estimate,$env['runtime_bytes']);
                AsusUpdateSnapshot::capture($env['opt'],$this->store->path($base.'/backup'),$env['owner']);
                $patch=['state'=>'prepared','prepared_uptime'=>AsusUpdateStore::uptime(),'code'=>null];if($stage!==null){$runtime=$stage($id,$env);if(!is_array($runtime)||!preg_match('/^[a-f0-9]{64}$/D',$runtime['digest']??''))throw new RuntimeException('invalid_state');$patch['runtime_digest']=$runtime['digest'];}
                return $this->store->update($id,$patch);
            }catch(Throwable $e){return $this->store->update($id,['state'=>'failed','code'=>self::code($e)]);}
        });
    }
}
