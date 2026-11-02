<?php
/** Optional Entware capability. No feeds, dependency resolution, core actions or DB writes. */
declare(strict_types=1);
require_once __DIR__.'/update-store.php';
require_once __DIR__.'/update-package.php';
require_once __DIR__.'/support-report-platform.php';
final class NfqwsIpHealthSockets
{
    private string $opt;
    private string $root;
    private int $owner;
    private ?AsusUpdateStore $store=null;
    private const TARGET='php8-mod-sockets';
    private const FILES=['opt/etc/php8/20_sockets.ini'=>0644,'opt/lib/php8/sockets.so'=>0755];
    public function __construct(private array $options=[])
    {$this->opt=rtrim($options['opt']??dirname(AsusDpiStore::optPath('/var')),'/');$this->owner=$options['owner']??0;$this->root=$options['state']??$this->opt.'/var/lib/nfqws2-asus/ip-health-sockets';}
    private function store():AsusUpdateStore{return $this->store??=new AsusUpdateStore($this->root,$this->owner);}
    private static function keys(array $a,array $b):bool{$k=array_keys($a);sort($k);sort($b);return $k===$b;}
    private function file(string $p,int $cap,?int $mode=null):string
    {
        AsusUpdateStore::noLinks($p);if(str_starts_with($p,$this->opt.'/'))for($d=dirname($p);; $d=dirname($d)){$parent=@lstat($d);if($parent&&(($parent['mode']&0170000)!==0040000||$parent['uid']!==$this->owner||($parent['mode']&0022)!==0))throw new RuntimeException('invalid_state');if($d===$this->opt)break;}clearstatcache(true,$p);$s=@lstat($p);
        if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>$cap||$mode!==null&&($s['mode']&07777)!==$mode)throw new RuntimeException('invalid_state');
        $raw=@file_get_contents($p);if(!is_string($raw)||strlen($raw)!==$s['size'])throw new RuntimeException('invalid_state');return $raw;
    }
    private function json(string $name):?array
    {$raw=$this->store()->readFile($name);if($raw===null)return null;try{$v=json_decode($raw,true,20,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}if(!is_array($v))throw new RuntimeException('invalid_state');return $v;}
    private function save(string $name,array $v):void{$this->store()->writeFile($name,json_encode($v,JSON_THROW_ON_ERROR));}
    private function catalog():array
    {
        $raw=$this->file($this->opt.'/share/nfqws2-asus/ip-health-sockets/catalog.json',16384);
        try{$v=json_decode($raw,true,12,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('sockets_artifact_invalid');}
        if(!is_array($v)||!self::keys($v,['schema_version','entries'])||$v['schema_version']!==1||!is_array($v['entries'])||!array_is_list($v['entries'])||count($v['entries'])<1||count($v['entries'])>4)throw new RuntimeException('sockets_artifact_invalid');$seen=[];
        foreach($v['entries'] as $e){
            if(!is_array($e)||!self::keys($e,['abi','php_version','php_package_version','version','architecture','filename','size','sha256','files'])||!in_array($e['abi'],['armv7-2.6','armv7-3.2','aarch64-3.10'],true)||$e['architecture']!==$e['abi']||!is_string($e['php_version'])||!preg_match('/^8\.[2-9]\.[0-9]{1,3}$/D',$e['php_version'])||!is_string($e['version'])||!preg_match('/^'.preg_quote($e['php_version'],'/').'[-][1-9][0-9]{0,3}$/D',$e['version'])||$e['php_package_version']!==$e['version']||isset($seen[$e['abi']."\0".$e['php_package_version']])||$e['filename']!==self::TARGET.'_'.$e['version'].'_'.$e['abi'].'.ipk'||!is_int($e['size'])||$e['size']<1024||$e['size']>65536||!is_string($e['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$e['sha256'])||!is_array($e['files'])||!self::keys($e['files'],array_keys(self::FILES)))throw new RuntimeException('sockets_artifact_invalid');
            foreach(self::FILES as $p=>$mode){$f=$e['files'][$p];if(!is_array($f)||!self::keys($f,['size','sha256','mode'])||$f['mode']!==$mode||!is_int($f['size'])||$f['size']<1||$f['size']>131072||!is_string($f['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$f['sha256']))throw new RuntimeException('sockets_artifact_invalid');}$seen[$e['abi']."\0".$e['php_package_version']]=true;
        }return $v['entries'];
    }
    /** Fixed manager data uses its own stable, bounded read policy. */
    private function managerStatus():string
    {
        require_once __DIR__.'/update-rollback.php';
        try{return AsusUpdateRollback::managerStatus($this->opt,$this->owner);}
        catch(Throwable $e){throw new RuntimeException('invalid_state');}
    }
    private function managerConfig():string
    {
        require_once __DIR__.'/update-rollback.php';
        try{return AsusUpdateRollback::managerConfig($this->opt,$this->owner);}
        catch(Throwable $e){throw new RuntimeException('invalid_state');}
    }
    /** Strict normal policy for every other package; only target unpacked is classified separately. */
    private function environment():array
    {
        $raw=$this->managerStatus();$other=[];$module=null;
        foreach(preg_split('/\n[ \t]*\n/',trim($raw)) as $part){$f=AsusUpdatePackage::fields($part);if(($f['Package']??null)!==self::TARGET){$other[]=$part;continue;}
            $state=$f['Status']??'';if(preg_match('/^(?:unknown|install|deinstall|purge) (?:ok|prefer|user|prefer,user) not-installed$/D',$state))continue;
            if($module!==null)throw new RuntimeException('sockets_recovery_required');if(str_ends_with($state,' installed')){$check=AsusUpdatePackage::database($part);if(!isset($check[self::TARGET])||!str_starts_with($state,'install '))throw new RuntimeException('sockets_recovery_required');}elseif(!preg_match('/^install (?:ok|user) unpacked$/D',$state))throw new RuntimeException('sockets_recovery_required');$module=$f;
        }
        $db=AsusUpdatePackage::database(implode("\n\n",$other));$own=$db['nfqws2-asus']??[];
        if(!preg_match('/^install (?:ok|user) installed$/D',$own['Status']??'')||!preg_match('/^[0-9]+\.[0-9]+\.[0-9]+-asus[0-9]+\+b([1-9][0-9]{0,5})$/D',$own['Version']??'',$m)||(int)$m[1]<82)throw new RuntimeException('unsupported_version');
        $abi=$this->options['abi']??null;if($abi===null)$abi=AsusReportPlatform::abi($this->managerConfig());
        $machine=$this->options['machine']??php_uname('m');if(!($abi==='aarch64-3.10'&&$machine==='aarch64'||in_array($abi,['armv7-2.6','armv7-3.2'],true)&&in_array($machine,['armv7l','armv8l'],true)))throw new RuntimeException('unsupported_abi');
        foreach(['php8','libc','libssp','librt','libpthread'] as $name)if(!preg_match('/^install [^ ]+ installed$/D',$db[$name]['Status']??''))throw new RuntimeException('missing_dependencies');
        ksort($db);foreach($db as &$row)ksort($row);unset($row);
        return ['abi'=>$abi,'own'=>$own['Version'],'php'=>$db['php8']['Version'],'foreign'=>hash('sha256',json_encode($db,JSON_THROW_ON_ERROR)),'module'=>$module];
    }
    /** Fully bounded tar reader: regular files/root directory only, no extraction. */
    private static function tar(string $compressed,int $cap):array
    {
        $tar=@gzdecode($compressed,$cap+1);if(!is_string($tar)||strlen($tar)>$cap)throw new RuntimeException('sockets_artifact_invalid');$out=[];$dirs=[];$ended=false;
        for($p=0,$count=0;$p+512<=strlen($tar)&&$count<32;$count++){
            $h=substr($tar,$p,512);$p+=512;if($h===str_repeat("\0",512)){$ended=true;break;}
            foreach([[100,8],[108,8],[116,8],[124,12],[148,8]] as [$at,$len])if(!preg_match('/^[0-7]+$/D',trim(substr($h,$at,$len)," \0")))throw new RuntimeException('sockets_artifact_invalid');
            if(array_sum(unpack('C*',substr_replace($h,str_repeat(' ',8),148,8)))!==octdec(trim(substr($h,148,8)," \0"))||octdec(trim(substr($h,108,8)," \0"))!==0||octdec(trim(substr($h,116,8)," \0"))!==0||trim(substr($h,157,100),"\0")!==''||trim(substr($h,345,155),"\0")!=='')throw new RuntimeException('sockets_artifact_invalid');
            $name=rtrim(substr($h,0,100),"\0");if(str_starts_with($name,'./'))$name=substr($name,2);$size=(int)octdec(trim(substr($h,124,12)," \0"));$mode=(int)octdec(trim(substr($h,100,8)," \0"));
            if($h[156]==='5'){if(str_ends_with($name,'/'))$name=substr($name,0,-1);if(!in_array($name,['','.','opt','opt/etc','opt/etc/php8','opt/lib','opt/lib/php8'],true)||isset($dirs[$name])||$size!==0||$mode!==0755)throw new RuntimeException('sockets_artifact_invalid');$dirs[$name]=true;continue;}
            if(!in_array($h[156],["\0",'0'],true)||!preg_match('~^[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*$~D',$name)||array_intersect(explode('/',$name),['.','..'])||isset($out[$name])||$size>$cap||$p+$size>strlen($tar))throw new RuntimeException('sockets_artifact_invalid');
            $out[$name]=['bytes'=>substr($tar,$p,$size),'mode'=>$mode];$p+=(int)(ceil($size/512)*512);
        }if(!$ended)throw new RuntimeException('sockets_artifact_invalid');return $out;
    }
    private function artifact(string $path,array $e):array
    {
        try{$raw=$this->file($path,65536);if(strlen($raw)!==$e['size']||!hash_equals($e['sha256'],hash('sha256',$raw)))throw new RuntimeException('invalid_state');$outer=self::tar($raw,196608);
            if(!self::keys($outer,['debian-binary','control.tar.gz','data.tar.gz'])||$outer['debian-binary']['bytes']!=="2.0\n")throw new RuntimeException('invalid_state');$ctl=self::tar($outer['control.tar.gz']['bytes'],16384);if(!self::keys($ctl,['control']))throw new RuntimeException('invalid_state');$f=AsusUpdatePackage::fields($ctl['control']['bytes']);
            if(($f['Package']??null)!==self::TARGET||($f['Version']??null)!==$e['version']||($f['Architecture']??null)!==$e['architecture']||($f['Depends']??null)!=='libc, libssp, librt, libpthread, php8'||array_intersect(array_keys($f),['Conflicts','Replaces'])||($f['Provides']??null)!==($e['abi']==='armv7-2.6'?null:'php8-mod-sockets-any'))throw new RuntimeException('invalid_state');
            $data=self::tar($outer['data.tar.gz']['bytes'],262144);if(!self::keys($data,array_keys(self::FILES)))throw new RuntimeException('invalid_state');
            foreach($data as $p=>$v){$wanted=$e['files'][$p];if($v['mode']!==$wanted['mode']||strlen($v['bytes'])!==$wanted['size']||!hash_equals($wanted['sha256'],hash('sha256',$v['bytes'])))throw new RuntimeException('invalid_state');}
            if($data['opt/etc/php8/20_sockets.ini']['bytes']!=="extension=sockets.so\n")throw new RuntimeException('invalid_state');$elf=$data['opt/lib/php8/sockets.so']['bytes'];if(strlen($elf)<64||substr($elf,0,4)!=="\x7fELF"||ord($elf[4])!==($e['abi']==='aarch64-3.10'?2:1)||ord($elf[5])!==1||unpack('v',substr($elf,18,2))[1]!==($e['abi']==='aarch64-3.10'?183:40))throw new RuntimeException('invalid_state');return $data;
        }catch(Throwable $x){throw new RuntimeException('sockets_artifact_invalid');}
    }
    private static function now():float{$t=hrtime();return (float)$t[0]+$t[1]/1000000000;}
    private function command(array $argv,float $seconds,int $cap=16384,?string $log=null):array
    {
        $mask=umask(0022);try{$p=@proc_open($argv,[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes,'/',['PATH'=>'/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C','LC_ALL'=>'C']);}finally{umask($mask);}if(!is_resource($p))throw new RuntimeException('sockets_launch_failed');
        foreach($pipes as $pipe)stream_set_blocking($pipe,false);$out='';$err='';$deadline=self::now()+$seconds;$exit=-1;
        try{while(true){$out.=stream_get_contents($pipes[1]);$err.=stream_get_contents($pipes[2]);if(strlen($out)+strlen($err)>$cap)throw new RuntimeException('output_limit');$status=proc_get_status($p);if(!$status['running']){$exit=$status['exitcode'];break;}if(self::now()>=$deadline)throw new RuntimeException('timed_out');usleep(10000);}
            $out.=stream_get_contents($pipes[1]);$err.=stream_get_contents($pipes[2]);if(strlen($out)+strlen($err)>$cap)throw new RuntimeException('output_limit');
        }finally{if(proc_get_status($p)['running']){proc_terminate($p,15);$end=self::now()+0.5;do{usleep(10000);$running=proc_get_status($p)['running'];}while($running&&self::now()<$end);if($running)proc_terminate($p,9);}foreach($pipes as $pipe)fclose($pipe);$closed=proc_close($p);if($exit<0)$exit=$closed;if($log!==null)$this->store()->writeFile($log,substr($out.$err,0,$cap));}
        return [$exit,$out,$err];
    }
    private function probe(string $module,string $version,string $directory):void
    {
        $script='<?php $p=[];if(PHP_VERSION!=='.var_export($version,true).'||!extension_loaded("sockets")||!function_exists("socket_create_pair")||!socket_create_pair(AF_UNIX,SOCK_STREAM,0,$p))exit(1);if(socket_write($p[0],"ok")!==2||socket_read($p[1],2)!=="ok")exit(1);foreach($p as $s)socket_close($s);echo "NFQWS_SOCKETS_OK:'. $version.'\\n";';
        $path=$directory.'/probe-'.hash('sha256',$version).'.php';if(is_file($path)){if($this->file($path,4096,0600)!==$script)throw new RuntimeException('invalid_state');}else{$f=fopen($path,'xb');if(!$f)throw new RuntimeException('invalid_state');try{chmod($path,0600);if(fwrite($f,$script)!==strlen($script))throw new RuntimeException('insufficient_space');}finally{fclose($f);}}
        $php=$this->options['php']??[$this->opt.'/bin/php-cgi'];if(!isset($this->options['php'])){$real=realpath($php[0]);if($real===false||!str_starts_with($real,$this->opt.'/bin/'))throw new RuntimeException('sockets_probe_failed');$this->file($real,16777216);}
        [$exit,$out,$err]=$this->command(array_merge($php,['-n','-d','extension='.$module,'-q','-f',$path]),5);
        if($exit!==0||$out!=="NFQWS_SOCKETS_OK:".$version."\n"||$err!=='')throw new RuntimeException('sockets_probe_failed');
    }
    private function targetPath(string $p):string
    {
        $path=$this->opt.substr($p,3);AsusUpdateStore::noLinks($path);
        for($d=dirname($path);; $d=dirname($d)){clearstatcache(true,$d);$s=@lstat($d);if($s&&(($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0022)!==0))throw new RuntimeException('sockets_path_conflict');if($d===$this->opt)break;if(!str_starts_with($d,$this->opt.'/'))throw new RuntimeException('invalid_state');}return $path;
    }
    private function inventory():iterable
    {
        require_once __DIR__.'/update-rollback.php';
        try{yield from AsusUpdateRollback::inventory($this->opt,$this->owner);}
        catch(Throwable $e){throw new RuntimeException('invalid_state');}
    }
    private function absent():void
    {foreach(self::FILES as $p=>$_){$path=$this->targetPath($p);if(file_exists($path)||is_link($path))throw new RuntimeException('sockets_path_conflict');}if((glob($this->opt.'/lib/opkg/info/'.self::TARGET.'.*')?:[])!==[])throw new RuntimeException('sockets_recovery_required');
        foreach($this->inventory() as $record)foreach($record['lines'] as $line){if(isset(self::FILES[ltrim($line,'/')]))throw new RuntimeException('sockets_path_conflict');if(in_array(basename($line),['sockets.so','20_sockets.ini'],true)){$parent=@realpath(dirname($line));foreach(self::FILES as $target=>$_)if($line===$this->opt.substr($target,3)||$parent!==false&&$parent.'/'.basename($line)===$this->opt.substr($target,3))throw new RuntimeException('sockets_path_conflict');}}}
    private function exactInstalled(array $e):void
    {
        try{foreach($e['files'] as $p=>$v){$path=$this->targetPath($p);$raw=$this->file($path,131072,$v['mode']);if(strlen($raw)!==$v['size']||!hash_equals($v['sha256'],hash('sha256',$raw)))throw new RuntimeException('invalid_state');}
            $prefix=$this->opt.'/lib/opkg/info/'.self::TARGET.'.';$paths=glob($prefix.'*')?:[];$seen=[];foreach($paths as $p){$suffix=substr($p,strlen($prefix));if(!in_array($suffix,['control','list'],true))throw new RuntimeException('invalid_state');if($suffix==='control')$seen[$suffix]=$this->file($p,16384);}
            foreach($this->inventory() as $index=>$record)if($index===self::TARGET.'.list')$seen['list']=$record['lines'];
            if(!self::keys($seen,['control','list']))throw new RuntimeException('invalid_state');$f=AsusUpdatePackage::fields($seen['control']);if(($f['Package']??null)!==self::TARGET||($f['Version']??null)!==$e['version']||($f['Architecture']??null)!==$e['architecture']||($f['Depends']??null)!=='libc, libssp, librt, libpthread, php8'||array_intersect(array_keys($f),['Conflicts','Replaces'])||($f['Provides']??null)!==($e['abi']==='armv7-2.6'?null:'php8-mod-sockets-any'))throw new RuntimeException('invalid_state');
            $list=$seen['list'];sort($list);$wanted=array_map(fn($p)=>'/'.$p,array_keys(self::FILES));sort($wanted);if($list!==$wanted)throw new RuntimeException('invalid_state');
        }catch(Throwable $x){throw new RuntimeException('sockets_recovery_required');}
    }
    private function selected(array $env):array
    {foreach($this->catalog() as $e)if($e['abi']===$env['abi']&&$e['php_package_version']===$env['php'])return $e;throw new RuntimeException('sockets_php_unsupported');}
    private function plan(string $id):array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');$p=$this->json('operations/'.$id.'/plan.json');
        if($p===null||!self::keys($p,['schema_version','id','own','foreign','entry'])||$p['schema_version']!==1||$p['id']!==$id||!is_string($p['own'])||!is_string($p['foreign'])||!preg_match('/^[a-f0-9]{64}$/D',$p['foreign'])||!is_array($p['entry']))throw new RuntimeException('sockets_recovery_required');return $p;
    }
    private function proof(string $id,array $plan):void
    {$v=$this->json('operations/'.$id.'/boundary.json');if($v!==['schema_version'=>1,'id'=>$id,'own'=>$plan['own'],'foreign'=>$plan['foreign'],'sha256'=>$plan['entry']['sha256']])throw new RuntimeException('sockets_recovery_required');}
    private function result(string $state,?string $code=null):array{$v=['state'=>$state,'code'=>$code];$this->save('status.json',$v);return $v;}
    /** Passive even after interruption: never construct the mutating store. */
    public function status():array
    {
        $empty=['state'=>'unavailable','code'=>'sockets_unprepared'];clearstatcache();AsusUpdateStore::noLinks($this->root);$root=@lstat($this->root);
        if(!$root)return $empty;if(($root['mode']&0170000)!==0040000||$root['uid']!==$this->owner||($root['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $path=$this->root.'/status.json';AsusUpdateStore::noLinks($path);$before=@lstat($path);if(!$before)return $empty;
        if(($before['mode']&0170000)!==0100000||$before['uid']!==$this->owner||($before['mode']&0777)!==0600||$before['nlink']!==1||$before['size']>131072)throw new RuntimeException('invalid_state');
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$actual=fstat($f);foreach(['ino','dev','mode','uid','nlink','size'] as $key)if($actual[$key]!==$before[$key])throw new RuntimeException('invalid_state');$raw=stream_get_contents($f,131073);if(!is_string($raw)||strlen($raw)>131072)throw new RuntimeException('invalid_state');}
        finally{fclose($f);}
        try{$v=json_decode($raw,true,20,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        $codes=['busy','invalid_state','unsupported_version','unsupported_abi','missing_dependencies','pending_packages','opkg_busy','sockets_unprepared','sockets_not_requested','sockets_preparing','sockets_configuring','sockets_php_unsupported','sockets_path_conflict','sockets_artifact_invalid','sockets_probe_failed','sockets_recovery_required','sockets_baseline_changed','sockets_install_failed','sockets_launch_failed','sockets_storage_full','timed_out','output_limit','insufficient_space'];
        if(!is_array($v)||!self::keys($v,['state','code'])||!in_array($v['state'],['ready','pending','failed','unavailable'],true)||$v['code']!==null&&!in_array($v['code'],$codes,true))throw new RuntimeException('invalid_state');return $v;
    }
    /** No absent-journal install while the main core is stopped. */
    public function admitted():bool
    {
        require_once __DIR__.'/ip-health-store.php';$directory=$this->opt.'/etc/nfqws2/ip-health';$path=$directory.'/bans.json';
        if(file_exists($path)||is_link($path)){$this->file($path,524288,0600);return (new NfqwsIpHealthStore($directory))->status()['enabled'];}
        require_once __DIR__.'/update-lifecycle.php';$intent=(new AsusUpdateLifecycle(['owner'=>$this->owner,'run'=>$this->options['run']??'/tmp/nfqws2-asus','engine'=>$this->opt.'/usr/bin/nfqws2']))->intent();
        if($intent['mode']!=='running'||!$intent['enabled'])return false;$init=$this->opt.'/etc/init.d/S51nfqws2';$this->file($init,262144);if(!is_executable($init))return false;[$exit]=$this->command([$init,'check'],8);return $exit===0;
    }
    public function lease(){return $this->store()->lease('apply.lock');}
    public function failure(Throwable $error):array
    {
        $known=['busy','invalid_state','unsupported_version','unsupported_abi','missing_dependencies','pending_packages','opkg_busy','sockets_php_unsupported','sockets_path_conflict','sockets_artifact_invalid','sockets_probe_failed','sockets_recovery_required','sockets_baseline_changed','sockets_install_failed','sockets_launch_failed','sockets_storage_full','timed_out','output_limit','insufficient_space'];
        return $this->result('failed',in_array($error->getMessage(),$known,true)?$error->getMessage():'sockets_install_failed');
    }
    /** Caller serializes this operation and holds the shared updater lease. */
    public function prepare():array
    {
        $env=$this->environment();$store=$this->store();
        if($env['module']!==null&&str_ends_with($env['module']['Status'],' installed')){
            if(!preg_match('/^([0-9]+\.[0-9]+\.[0-9]+)(?:[-+].*)?$/D',$env['php'],$v))throw new RuntimeException('sockets_php_unsupported');$store->directory('probe');$path=$this->targetPath('opt/lib/php8/sockets.so');$this->file($path,1048576);$this->probe($path,$v[1],$store->path('probe'));return $this->result('ready');
        }
        $entry=$this->selected($env);$current=$this->json('current.json');
        if($env['module']!==null){
            if($current===null||!self::keys($current,['id'])||!is_string($current['id']))throw new RuntimeException('sockets_recovery_required');$id=$current['id'];$plan=$this->plan($id);
            if($plan['entry']!==$entry||$plan['own']!==$env['own']||$plan['foreign']!==$env['foreign']||($env['module']['Version']??null)!==$entry['version']||($env['module']['Architecture']??null)!==$entry['architecture'])throw new RuntimeException('sockets_recovery_required');$this->proof($id,$plan);$this->exactInstalled($entry);$this->artifact($store->path('operations/'.$id.'/package.ipk'),$entry);$this->probe($this->opt.'/lib/php8/sockets.so',$entry['php_version'],$store->path('operations/'.$id.'/runtime'));
            $this->result('pending','sockets_configuring');return ['id'=>$id,'action'=>'configure','state'=>'pending'];
        }
        $this->absent();$source=$this->opt.'/share/nfqws2-asus/ip-health-sockets/ipks/'.$entry['filename'];$data=$this->artifact($source,$entry);
        if($current!==null&&is_string($current['id']??null)){$old=$this->plan($current['id']);if($old['entry']===$entry&&$old['own']===$env['own']&&$old['foreign']===$env['foreign'])return ['id'=>$current['id'],'action'=>'install','state'=>'pending'];}
        if(count(glob($store->path('operations').'/*')?:[])>=8)throw new RuntimeException('sockets_storage_full');$id=bin2hex(random_bytes(16));$base='operations/'.$id;$store->directory($base);$store->directory($base.'/runtime');
        $store->writeFile($base.'/package.ipk',$this->file($source,65536));$store->writeFile($base.'/runtime/sockets.so',$data['opt/lib/php8/sockets.so']['bytes']);
        $plan=['schema_version'=>1,'id'=>$id,'own'=>$env['own'],'foreign'=>$env['foreign'],'entry'=>$entry];$this->save($base.'/plan.json',$plan);
        $command=$this->options['entry']??[$this->opt.'/bin/php-cgi','-n','-d','register_argc_argv=1','-q','-f',$this->opt.'/lib/nfqws2-asus/ip-health-sockets/worker.php','--'];if(isset($this->options['entry_config']))$command[]=$this->options['entry_config'];
        $script="#!/bin/sh\n[ \"\$#\" = 2 ] || exit 1\nexec ".implode(' ',array_map('escapeshellarg',array_merge($command,['preflight']))).' "$1" "$2"'."\n";$store->writeFile($base.'/runtime/check.sh',$script);chmod($store->path($base.'/runtime/check.sh'),0700);
        $this->save('current.json',['id'=>$id]);$this->result('pending','sockets_preparing');$this->probe($store->path($base.'/runtime/sockets.so'),$entry['php_version'],$store->path($base.'/runtime'));return ['id'=>$id,'action'=>'install','state'=>'pending'];
    }
    /** Runs only in the child of sockets-launch while that parent holds opkg's POSIX lock. */
    public function preflight(string $id,string $action):void
    {try{$this->validate($id,$action,true);}catch(Throwable $e){$this->save('operations/'.$id.'/preflight-error.json',['code'=>$e->getMessage()]);throw $e;}}
    private function validate(string $id,string $action,bool $boundary):void
    {
        if(!in_array($action,['install','configure'],true))throw new RuntimeException('invalid_request');$plan=$this->plan($id);$env=$this->environment();$entry=$this->selected($env);
        if($entry!==$plan['entry']||$env['foreign']!==$plan['foreign']||$env['own']!==$plan['own'])throw new RuntimeException('sockets_baseline_changed');$dir=$this->store()->path('operations/'.$id);$this->artifact($dir.'/package.ipk',$entry);
        if($action==='install'){if($env['module']!==null)throw new RuntimeException('sockets_baseline_changed');$this->absent();$bytes=$this->file($dir.'/runtime/sockets.so',131072,0600);$expected=$entry['files']['opt/lib/php8/sockets.so'];if(strlen($bytes)!==$expected['size']||hash('sha256',$bytes)!==$expected['sha256'])throw new RuntimeException('sockets_artifact_invalid');$this->probe($dir.'/runtime/sockets.so',$entry['php_version'],$dir.'/runtime');if($boundary)$this->save('operations/'.$id.'/boundary.json',['schema_version'=>1,'id'=>$id,'own'=>$plan['own'],'foreign'=>$plan['foreign'],'sha256'=>$entry['sha256']]);}
        else{if(($env['module']['Version']??null)!==$entry['version']||($env['module']['Architecture']??null)!==$entry['architecture']||!preg_match('/^install (?:ok|user) unpacked$/D',$env['module']['Status']??''))throw new RuntimeException('sockets_recovery_required');$this->proof($id,$plan);$this->exactInstalled($entry);$this->probe($this->opt.'/lib/php8/sockets.so',$entry['php_version'],$dir.'/runtime');}
    }
    public function apply(string $id):array
    {
        try{$plan=$this->plan($id);$env=$this->environment();$action=$env['module']===null?'install':'configure';$this->validate($id,$action,false);
            $launcher=$this->options['launcher']??$this->opt.'/libexec/nfqws2-asus/sockets-launch';$this->file($launcher,131072);$args=[$launcher,$id];if($action==='configure')$args[]='configure';$this->save('operations/'.$id.'/preflight-error.json',['code'=>null]);$timeout=$this->options['install_timeout']??60;if(!is_numeric($timeout)||$timeout<=0||$timeout>60)throw new RuntimeException('invalid_state');[$exit,$out,$err]=$this->command($args,(float)$timeout,32768,'operations/'.$id.'/opkg.log');
            if($exit===73)return $this->result('failed','opkg_busy');if($exit!==0){$failure=$this->json('operations/'.$id.'/preflight-error.json');throw new RuntimeException($exit===74&&is_string($failure['code']??null)?$failure['code']:'sockets_install_failed');}$env=$this->environment();if($env['foreign']!==$plan['foreign']||($env['module']['Version']??null)!==$plan['entry']['version']||($env['module']['Architecture']??null)!==$plan['entry']['architecture']||!preg_match('/^install (?:ok|user) installed$/D',$env['module']['Status']??''))throw new RuntimeException('sockets_install_failed');$this->exactInstalled($plan['entry']);$this->probe($this->opt.'/lib/php8/sockets.so',$plan['entry']['php_version'],$this->store()->path('operations/'.$id.'/runtime'));return $this->result('ready');
        }catch(Throwable $e){$code=$e->getMessage();$allowed=['opkg_busy','pending_packages','sockets_baseline_changed','sockets_recovery_required','sockets_probe_failed','sockets_install_failed','sockets_artifact_invalid','timed_out','output_limit','invalid_state'];return $this->result('failed',in_array($code,$allowed,true)?$code:'sockets_install_failed');}
    }
}
