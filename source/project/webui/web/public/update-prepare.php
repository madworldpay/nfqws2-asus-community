<?php
require_once __DIR__.'/update-store.php';
require_once __DIR__.'/update-manifest.php';
require_once __DIR__.'/update-transport.php';
require_once __DIR__.'/update-deadline.php';
require_once __DIR__.'/support-report-platform.php';

/** Read only bounded control metadata; never extract or execute archive paths. */
final class AsusUpdatePackage
{
    private const REPLACEES=['nfqws2-keenetic','nfqws-keenetic','tpws-keenetic','nfqws-keenetic-web','nfqws-asus-web'];
    public static function fields(string $raw): array
    {
        if(strlen($raw)>2097152||str_contains($raw,"\0"))throw new RuntimeException('invalid_package');$out=[];$key=null;
        foreach(explode("\n",rtrim($raw,"\n")) as $line){if(preg_match('/^[ \t]/',$line)&&$key!==null){$out[$key].=' '.trim($line);continue;}if(!preg_match('/^([A-Za-z][A-Za-z0-9-]*):[ \t]*(.*)$/D',$line,$m)||isset($out[$m[1]]))throw new RuntimeException('invalid_package');$key=$m[1];$out[$key]=$m[2];}return $out;
    }
    private static function dependencies(string $text): array
    {
        if($text==='')return [];$out=array_map('trim',explode(',',$text));foreach($out as $p)if(!preg_match('/^[a-z0-9][a-z0-9+.-]{0,80}$/D',$p))throw new RuntimeException('dependency_change');$out=array_values(array_unique($out));sort($out);return $out;
    }
    public static function database(string $raw): array
    {
        if(strlen($raw)>2097152)throw new RuntimeException('pending_packages');$db=[];
        foreach(preg_split('/\n[ \t]*\n/',trim($raw)) as $section){$p=self::fields($section);$name=$p['Package']??'';if(!preg_match('/^[a-z0-9][a-z0-9+.-]{0,80}$/D',$name))throw new RuntimeException('pending_packages');
            $status=preg_split('/\s+/',trim($p['Status']??''));if(count($status)!==3||!in_array($status[2],['installed','not-installed','config-files'],true))throw new RuntimeException('pending_packages');
            // Opkg retains superseded versions with preference/user flags. They
            // are absent packages, not an interrupted installation or the active version.
            if($status[2]==='not-installed'){
                $flags=explode(',',$status[1]);if(count($flags)!==count(array_unique($flags))||array_diff($flags,['ok','user','prefer']))throw new RuntimeException('pending_packages');continue;
            }
            if(isset($db[$name])||!in_array($status[1],['ok','user'],true))throw new RuntimeException('pending_packages');$db[$name]=$p;
        }return $db;
    }
    private static function header(string $h): ?array
    {
        if(strlen($h)!==512)throw new RuntimeException('invalid_package');if($h===str_repeat("\0",512))return null;
        $size=trim(substr($h,124,12)," \0");$sum=trim(substr($h,148,8)," \0");
        if(!preg_match('/^[0-7]{1,11}$/D',$size)||!preg_match('/^[0-7]{1,7}$/D',$sum))throw new RuntimeException('invalid_package');
        $actual=array_sum(unpack('C*',substr_replace($h,str_repeat(' ',8),148,8)));if($actual!==octdec($sum))throw new RuntimeException('invalid_package');
        $name=rtrim(substr($h,0,100),"\0");if(str_starts_with($name,'./'))$name=substr($name,2);
        if(trim(substr($h,345,155),"\0")!==''||!in_array($h[156],["\0",'0'],true)||!preg_match('/^[a-zA-Z0-9.-]+$/D',$name))throw new RuntimeException('invalid_package');
        return ['name'=>$name,'size'=>(int)octdec($size)];
    }
    private static function gzRead($f,int $n): string
    {$out='';while(strlen($out)<$n){$chunk=@gzread($f,min(16384,$n-strlen($out)));if(!is_string($chunk)||$chunk==='')throw new RuntimeException('invalid_package');$out.=$chunk;}return $out;}
    private static function control(string $path,string $family): array
    {
        if(!function_exists('gzopen'))throw new RuntimeException('package_reader_unavailable');$f=@gzopen($path,'rb');if(!$f)throw new RuntimeException('invalid_package');$found=[];$control=null;$total=0;
        try{for($i=0;$i<8;$i++){$h=self::header(self::gzRead($f,512));if($h===null)break;$name=$h['name'];$size=$h['size'];
            if(isset($found[$name])||!in_array($name,['control.tar.gz','data.tar.gz','debian-binary'],true)||$size>134217728||($name==='control.tar.gz'&&$size>2097152)||($name==='debian-binary'&&$size!==4))throw new RuntimeException('invalid_package');$found[$name]=true;$total+=$size;if($total>134217728)throw new RuntimeException('invalid_package');
            $raw='';for($left=$size;$left>0;){$chunk=self::gzRead($f,min(16384,$left));if($name!=='data.tar.gz')$raw.=$chunk;$left-=strlen($chunk);}if($size%512)self::gzRead($f,512-$size%512);
            if($name==='control.tar.gz')$control=$raw;elseif($name==='debian-binary'&&$raw!=="2.0\n")throw new RuntimeException('invalid_package');
        }}finally{gzclose($f);}
        if(count($found)!==3||$control===null)throw new RuntimeException('invalid_package');$tar=@gzdecode($control,4194304);if(!is_string($tar)||strlen($tar)>4194304)throw new RuntimeException('invalid_package');$fields=null;$seen=[];$bootstrap=[];
        $helpers=$family==='armv7'?['busybox-migration-armv7-2.6','busybox-migration-armv7-3.2']:['busybox-migration-aarch64-3.10'];
        for($p=0,$n=0;$p+512<=strlen($tar)&&$n<16;$n++){$block=substr($tar,$p,512);$h=self::header($block);$p+=512;if($h===null)break;
            $helper=in_array($h['name'],$helpers,true);
            if((!$helper&&!in_array($h['name'],['control','preinst','postinst','prerm','postrm','conffiles'],true))||isset($seen[$h['name']])||$h['size']>($helper?1048576:131072)||$p+$h['size']>strlen($tar))throw new RuntimeException('invalid_package');$seen[$h['name']]=true;
            if($helper){
                // Signed, fixed-name bootstrap binaries are read as bytes only.
                // They let preinst preserve data after the old payload was removed.
                $elf=substr($tar,$p,20);$mode=trim(substr($block,100,8),"\0 ");
                if($h['size']<20||substr($elf,0,4)!=="\x7fELF"||ord($elf[4])!==($family==='armv7'?1:2)||ord($elf[5])!==1||unpack('v',substr($elf,18,2))[1]!==($family==='armv7'?40:183)||!preg_match('/^[0-7]{1,7}$/D',$mode)||octdec($mode)!==0755)throw new RuntimeException('invalid_package');
                $bootstrap[]=$h['name'];
            }
            if($h['name']==='control'){if($h['size']>16384)throw new RuntimeException('invalid_package');$fields=self::fields(substr($tar,$p,$h['size']));}$p+=(int)(ceil($h['size']/512)*512);
        }if($fields===null)throw new RuntimeException('invalid_package');sort($bootstrap);sort($helpers);if($bootstrap!==[]&&$bootstrap!==$helpers)throw new RuntimeException('invalid_package');return $fields;
    }
    public static function inspect(string $path,array $candidate,string $status,string $abi,string $machine): array
    {
        $family=$candidate['package']['family']??null;
        if(!(($family==='aarch64-3.10'&&$abi==='aarch64-3.10'&&$machine==='aarch64')||($family==='armv7'&&in_array($abi,['armv7-2.6','armv7-3.2'],true)&&in_array($machine,['armv7l','armv8l'],true))))throw new RuntimeException('unsupported_abi');
        AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['nlink']!==1)throw new RuntimeException('invalid_state');
        if($s['size']!==($candidate['package']['size']??null))throw new RuntimeException('download_size');if(!hash_equals($candidate['package']['sha256'],hash_file('sha256',$path)))throw new RuntimeException('download_hash');
        $control=self::control($path,$family);
        if(($control['Package']??null)!=='nfqws2-asus'||($control['Version']??null)!==$candidate['package_version']||($control['Architecture']??null)!==($family==='armv7'?'all':$family)||($control['Replaces']??'')!=='nfqws-asus-web')throw new RuntimeException('invalid_package');
        $db=self::database($status);if(!isset($db['nfqws2-asus'])||!preg_match('/^install (?:ok|user) installed$/D',$db['nfqws2-asus']['Status']??''))throw new RuntimeException('unsupported_version');
        $deps=self::dependencies($control['Depends']??'');if($deps!==self::dependencies($db['nfqws2-asus']['Depends']??''))throw new RuntimeException('dependency_change');
        foreach($deps as $p)if(!isset($db[$p])||!preg_match('/^install (?:ok|user) installed$/D',$db[$p]['Status']))throw new RuntimeException('missing_dependencies');
        foreach(array_filter(array_map('trim',explode(',',$control['Conflicts']??''))) as $p)if(!in_array($p,self::REPLACEES,true))throw new RuntimeException('invalid_package');
        foreach(self::REPLACEES as $p)if(isset($db[$p])&&str_ends_with($db[$p]['Status'],' installed'))throw new RuntimeException('pending_packages');return $control;
    }
    public static function space(int|float $free,int $ipk,int $snapshot,int $runtime): bool
    {if(min($free,$ipk,$snapshot,$runtime)<0||$free<$ipk+$snapshot+$runtime+16777216)throw new RuntimeException('insufficient_space');return true;}
}

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

/** Preparation has no service/opkg actions. A worker may call it after detaching. */
final class AsusUpdatePrepare
{
    private AsusUpdateStore $store;
    public function __construct(?AsusUpdateStore $store=null,private ?AsusUpdateSource $source=null,private array $environment=[],private ?string $publicKey=null,private ?AsusUpdateDeadline $deadline=null)
    {$this->store=$store??new AsusUpdateStore();}
    public static function code(Throwable $error): string
    {
        $known=['channel_unconfigured','invalid_channel','invalid_manifest','invalid_signature','signature_unavailable','download_failed','download_size','download_hash','timed_out','channel_auth_failed','release_changed','unsupported_abi','unsupported_version','unsupported_package','invalid_package','package_reader_unavailable','missing_dependencies','dependency_change','pending_packages','insufficient_space','settings_changed','invalid_state','output_limit','stale_revision','busy','request_conflict','missing_operation','runtime_changed','core_stop_failed','core_start_failed','web_start_failed','web_health_failed','intent_mismatch','opkg_busy','install_failed','version_mismatch','launch_failed','interrupted'];
        $known=array_merge($known,['invalid_request','consent_required','check_required','auth_required','csrf_failed']);
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
