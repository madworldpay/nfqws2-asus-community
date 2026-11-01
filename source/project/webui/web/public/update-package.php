<?php
/** Read only bounded control metadata; never extract or execute archive paths. */
final class AsusUpdatePackage
{
    private const REPLACEES=['nfqws2-keenetic','nfqws-keenetic','tpws-keenetic','nfqws-keenetic-web','nfqws-asus-web'];
    // Opkg serializes persistent policy bits in this order; "ok" stands alone.
    private const POLICY_FLAGS=['hold','noprune','prefer','user'];
    public static function fields(string $raw): array
    {
        if(strlen($raw)>2097152||str_contains($raw,"\0"))throw new RuntimeException('invalid_package');$out=[];$key=null;
        foreach(explode("\n",rtrim($raw,"\n")) as $line){if(preg_match('/^[ \t]/',$line)&&$key!==null){$out[$key].=' '.trim($line);continue;}if(!preg_match('/^([A-Za-z][A-Za-z0-9-]*):[ \t]*(.*)$/D',$line,$m)||isset($out[$m[1]]))throw new RuntimeException('invalid_package');$key=$m[1];$out[$key]=$m[2];}return $out;
    }
    private static function dependencies(string $text): array
    {
        if($text==='')return [];$out=array_map('trim',explode(',',$text));foreach($out as $p)if(!preg_match('/^[a-z0-9][a-z0-9+.-]{0,80}$/D',$p))throw new RuntimeException('dependency_change');$out=array_values(array_unique($out));sort($out);return $out;
    }
    public static function database(string $raw,bool $allowOwnUnpacked=false): array
    {
        if(strlen($raw)>2097152)throw new RuntimeException('pending_packages');$db=[];
        foreach(preg_split('/\n[ \t]*\n/',trim($raw)) as $section){$p=self::fields($section);$name=$p['Package']??'';if(!preg_match('/^[a-z0-9][a-z0-9+.-]{0,80}$/D',$name))throw new RuntimeException('pending_packages');
            $own=$name==='nfqws2-asus';$status=preg_split('/\s+/',trim($p['Status']??''));$ownPending=$allowOwnUnpacked&&$own&&preg_match('/^install (?:ok|user) unpacked$/D',$p['Status']??'');
            if(count($status)!==3||!in_array($status[0],['unknown','install','deinstall','purge'],true)||!in_array($status[2],['installed','not-installed','config-files'],true)&&!$ownPending)throw new RuntimeException('pending_packages');
            $flags=explode(',',$status[1]);$allowed=$own?['prefer','user']:self::POLICY_FLAGS;
            if($status[1]!=='ok'&&$flags!==array_values(array_intersect($allowed,$flags)))throw new RuntimeException('pending_packages');
            // Opkg retains superseded versions with preference/user flags. They
            // are absent packages, not an interrupted installation or the active version.
            if($status[2]==='not-installed')continue;
            // Foreign holds affect their upgrades, not whether they are installed.
            // Never override a policy flag on the package this operation changes.
            if(isset($db[$name])||$own&&!in_array($status[1],['ok','user'],true))throw new RuntimeException('pending_packages');$db[$name]=$p;
        }return $db;
    }
    private static function header(string $h,bool $nativeRoot=false): ?array
    {
        if(strlen($h)!==512)throw new RuntimeException('invalid_package');if($h===str_repeat("\0",512))return null;
        $size=trim(substr($h,124,12)," \0");$sum=trim(substr($h,148,8)," \0");
        if(!preg_match('/^[0-7]{1,11}$/D',$size)||!preg_match('/^[0-7]{1,7}$/D',$sum))throw new RuntimeException('invalid_package');
        $actual=array_sum(unpack('C*',substr_replace($h,str_repeat(' ',8),148,8)));if($actual!==octdec($sum))throw new RuntimeException('invalid_package');
        $name=rtrim(substr($h,0,100),"\0");
        if($nativeRoot&&in_array($name,['.','./'],true)&&$h[156]==='5'&&octdec($size)===0&&trim(substr($h,345,155),"\0")==='')return ['name'=>'.','size'=>0,'directory'=>true];
        if(str_starts_with($name,'./'))$name=substr($name,2);
        if(trim(substr($h,345,155),"\0")!==''||!in_array($h[156],["\0",'0'],true)||!preg_match('/^[a-zA-Z0-9.-]+$/D',$name))throw new RuntimeException('invalid_package');
        return ['name'=>$name,'size'=>(int)octdec($size)];
    }
    private static function gzRead($f,int $n): string
    {$out='';while(strlen($out)<$n){$chunk=@gzread($f,min(16384,$n-strlen($out)));if(!is_string($chunk)||$chunk==='')throw new RuntimeException('invalid_package');$out.=$chunk;}return $out;}
    private static function control(string $path,string $family,?array &$scripts=null): array
    {
        $scripts=[];if(!function_exists('gzopen'))throw new RuntimeException('package_reader_unavailable');$f=@gzopen($path,'rb');if(!$f)throw new RuntimeException('invalid_package');$found=[];$control=null;$total=0;
        try{for($i=0;$i<8;$i++){$h=self::header(self::gzRead($f,512));if($h===null)break;$name=$h['name'];$size=$h['size'];
            if(isset($found[$name])||!in_array($name,['control.tar.gz','data.tar.gz','debian-binary'],true)||$size>134217728||($name==='control.tar.gz'&&$size>2097152)||($name==='debian-binary'&&$size!==4))throw new RuntimeException('invalid_package');$found[$name]=true;$total+=$size;if($total>134217728)throw new RuntimeException('invalid_package');
            $raw='';for($left=$size;$left>0;){$chunk=self::gzRead($f,min(16384,$left));if($name!=='data.tar.gz')$raw.=$chunk;$left-=strlen($chunk);}if($size%512)self::gzRead($f,512-$size%512);
            if($name==='control.tar.gz')$control=$raw;elseif($name==='debian-binary'&&$raw!=="2.0\n")throw new RuntimeException('invalid_package');
        }}finally{gzclose($f);}
        if(count($found)!==3||$control===null)throw new RuntimeException('invalid_package');$tar=@gzdecode($control,4194304);if(!is_string($tar)||strlen($tar)>4194304)throw new RuntimeException('invalid_package');$fields=null;$seen=[];$bootstrap=[];
        $helpers=$family==='native'?[]:($family==='armv7'?['busybox-migration-armv7-2.6','busybox-migration-armv7-3.2']:['busybox-migration-aarch64-3.10']);
        for($p=0,$n=0;$p+512<=strlen($tar)&&$n<16;$n++){$block=substr($tar,$p,512);$h=self::header($block,$family==='native');$p+=512;if($h===null)break;
            if(isset($h['directory'])){if(isset($seen['.']))throw new RuntimeException('invalid_package');$seen['.']=true;continue;}
            $helper=in_array($h['name'],$helpers,true);
            if((!$helper&&!in_array($h['name'],['control','preinst','postinst','prerm','postrm','conffiles'],true))||isset($seen[$h['name']])||$h['size']>($helper?1048576:131072)||$p+$h['size']>strlen($tar))throw new RuntimeException('invalid_package');$seen[$h['name']]=true;
            if($helper){
                // Signed, fixed-name bootstrap binaries are read as bytes only.
                // They let preinst preserve data after the old payload was removed.
                $elf=substr($tar,$p,20);$mode=trim(substr($block,100,8),"\0 ");
                if($h['size']<20||substr($elf,0,4)!=="\x7fELF"||ord($elf[4])!==($family==='armv7'?1:2)||ord($elf[5])!==1||unpack('v',substr($elf,18,2))[1]!==($family==='armv7'?40:183)||!preg_match('/^[0-7]{1,7}$/D',$mode)||octdec($mode)!==0755)throw new RuntimeException('invalid_package');
                $bootstrap[]=$h['name'];
            }
            if($h['name']==='control'){if($h['size']>16384)throw new RuntimeException('invalid_package');$fields=self::fields(substr($tar,$p,$h['size']));}
            elseif(in_array($h['name'],['preinst','postinst','prerm','postrm'],true)){$mode=trim(substr($block,100,8),"\0 ");if(!preg_match('/^[0-7]{1,7}$/D',$mode))throw new RuntimeException('invalid_package');$scripts[$h['name']]=['bytes'=>substr($tar,$p,$h['size']),'mode'=>(int)octdec($mode)];}
            $p+=(int)(ceil($h['size']/512)*512);
        }if($fields===null)throw new RuntimeException('invalid_package');sort($bootstrap);sort($helpers);if($bootstrap!==[]&&$bootstrap!==$helpers)throw new RuntimeException('invalid_package');return $fields;
    }
    public static function nativeControl(string $path):array{return self::control($path,'native');}
    public static function inspect(string $path,array $candidate,string $status,string $abi,string $machine,?string $opt=null,int $owner=0): array
    {
        $family=$candidate['package']['family']??null;
        if(!(($family==='aarch64-3.10'&&$abi==='aarch64-3.10'&&$machine==='aarch64')||($family==='armv7'&&in_array($abi,['armv7-2.6','armv7-3.2'],true)&&in_array($machine,['armv7l','armv8l'],true))))throw new RuntimeException('unsupported_abi');
        AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['nlink']!==1)throw new RuntimeException('invalid_state');
        if($s['size']!==($candidate['package']['size']??null))throw new RuntimeException('download_size');if(!hash_equals($candidate['package']['sha256'],hash_file('sha256',$path)))throw new RuntimeException('download_hash');
        $scripts=null;$control=self::control($path,$family,$scripts);$resume=($candidate['action']??null)==='configure';
        if(($control['Package']??null)!=='nfqws2-asus'||($control['Version']??null)!==$candidate['package_version']||($control['Architecture']??null)!==($family==='armv7'?'all':$family)||($control['Replaces']??'')!=='nfqws-asus-web')throw new RuntimeException('invalid_package');
        // Opkg marks the old version deinstall before running the new preinst.
        // A failed preinst leaves that old, fully configured version installed.
        // The explicit newer update can retry it through opkg without changing
        // the database by hand. Pending payload states and held flags stay blocked.
        $db=self::database($status,$resume);$own=$db['nfqws2-asus']??[];
        if($resume){if(!preg_match('/^install (?:ok|user) unpacked$/D',$own['Status']??'')||($own['Version']??null)!==$candidate['package_version']||($own['Architecture']??null)!==$control['Architecture'])throw new RuntimeException('recovery_required');}
        elseif(!preg_match('/^(?:install|deinstall) (?:ok|user) installed$/D',$own['Status']??''))throw new RuntimeException('unsupported_version');
        $deps=self::dependencies($control['Depends']??'');if($deps!==self::dependencies($db['nfqws2-asus']['Depends']??''))throw new RuntimeException('dependency_change');
        foreach($deps as $p){$state=preg_split('/\s+/',trim($db[$p]['Status']??''));
            // Database validation already checked the flags; --nodeps does not
            // upgrade held dependencies, which still satisfy installed state.
            if(count($state)!==3||$state[0]!=='install'||$state[2]!=='installed')throw new RuntimeException('missing_dependencies');}
        foreach(array_filter(array_map('trim',explode(',',$control['Conflicts']??''))) as $p)if(!in_array($p,self::REPLACEES,true))throw new RuntimeException('invalid_package');
        foreach(self::REPLACEES as $p)if(isset($db[$p])&&str_ends_with($db[$p]['Status'],' installed'))throw new RuntimeException('pending_packages');
        if($resume){if($opt===null||!isset($scripts['postinst']))throw new RuntimeException('recovery_required');self::recoveryScripts($opt,$owner,$scripts);self::recoveryPayload($path,$opt,$owner);}
        return $control;
    }
    private static function recoveryScripts(string $opt,int $owner,array $scripts): void
    {
        foreach($scripts as $name=>$script){$path=$opt.'/lib/opkg/info/nfqws2-asus.'.$name;self::recoveryParents($path,$opt,$owner);$s=@lstat($path);$bytes=$script['bytes'];
            if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&07777)!==$script['mode']||$script['mode']!==0755||$s['size']!==strlen($bytes)||!hash_equals(hash('sha256',$bytes),hash_file('sha256',$path)))throw new RuntimeException('recovery_required');}
        $migration=$opt.'/etc/nfqws2-asus-migration';AsusUpdateStore::noLinks($migration.'/snapshot');
        if(file_exists($migration.'/snapshot')){
            $consumed=false;foreach(['data-restored','complete'] as $name){$path=$migration.'/'.$name;AsusUpdateStore::noLinks($path);$s=@lstat($path);
                if($s&&($s['mode']&0170000)===0100000&&$s['uid']===$owner&&$s['nlink']===1&&($s['mode']&0022)===0&&$s['size']<=4096)$consumed=true;}
            if(!$consumed)throw new RuntimeException('recovery_required');
        }
    }
    private static function recoveryParents(string $path,string $opt,int $owner): void
    {
        AsusUpdateStore::noLinks($path);
        for($parent=dirname($path);;$parent=dirname($parent)){$s=@lstat($parent);
            if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$owner||($s['mode']&0022)!==0)throw new RuntimeException('recovery_required');
            if($parent===$opt)break;if(!str_starts_with($parent,$opt.'/'))throw new RuntimeException('invalid_state');
        }
    }
    /** The caller has already verified this private candidate's signature/hash. */
    public static function stockDefaults(string $package,string $opt,int $owner):array
    {return self::recoveryPayload($package,$opt,$owner,true);}
    /** Compare archive members as bytes, without extracting any archive paths. */
    private static function recoveryPayload(string $package,string $opt,int $owner,bool $defaultsOnly=false): array
    {
        $parent=dirname($package);AsusUpdateStore::noLinks($parent);$s=@lstat($parent);$free=@disk_free_space($parent);
        if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        if($free===false||$free<filesize($package)+16777216)throw new RuntimeException('insufficient_space');
        // The unique operation directory and work lease own this fixed scratch
        // name, so journal rotation can reclaim it after a killed verifier.
        $temporary=$parent.'/recovery-data.gz';$out=@fopen($temporary,'xb');if(!$out)throw new RuntimeException('invalid_state');chmod($temporary,0600);$outer=null;$data=null;
        try{
            $outer=@gzopen($package,'rb');if(!$outer)throw new RuntimeException('invalid_package');$found=false;
            for($i=0;$i<8;$i++){$h=self::header(self::gzRead($outer,512));if($h===null)break;$size=$h['size'];if($size>33554432)throw new RuntimeException('invalid_package');
                for($left=$size;$left>0;){$chunk=self::gzRead($outer,min(16384,$left));if($h['name']==='data.tar.gz'&&fwrite($out,$chunk)!==strlen($chunk))throw new RuntimeException('insufficient_space');$left-=strlen($chunk);}
                if($h['name']==='data.tar.gz'){$found=true;break;}if($size%512)self::gzRead($outer,512-$size%512);
            }
            if(!$found||!fflush($out))throw new RuntimeException('invalid_package');fclose($out);$out=null;gzclose($outer);$outer=null;
            $data=@gzopen($temporary,'rb');if(!$data)throw new RuntimeException('invalid_package');$seen=[];$total=0;$files=0;$defaults=[];
            for($count=0;$count<8192;$count++){
                $h=self::gzRead($data,512);if($h===str_repeat("\0",512)){if($files===0&&!$defaultsOnly)throw new RuntimeException('invalid_package');ksort($defaults);return $defaults;}
                $size=trim(substr($h,124,12)," \0");$sum=trim(substr($h,148,8)," \0");$mode=trim(substr($h,100,8)," \0");$uid=trim(substr($h,108,8)," \0");
                if(!preg_match('/^[0-7]{1,11}$/D',$size)||!preg_match('/^[0-7]{1,7}$/D',$sum)||!preg_match('/^[0-7]{1,7}$/D',$mode)||!preg_match('/^0+$/D',$uid)||octdec($size)>16777216||octdec($mode)>0777||array_sum(unpack('C*',substr_replace($h,str_repeat(' ',8),148,8)))!==octdec($sum))throw new RuntimeException('invalid_package');
                $name=rtrim(substr($h,0,100),"\0");$prefix=rtrim(substr($h,345,155),"\0");if($prefix!=='')$name=$prefix.'/'.$name;if(str_starts_with($name,'./'))$name=substr($name,2);
                // USTAR serializes directory names with a trailing slash.
                // Strip exactly that suffix; doubled separators stay invalid.
                if($h[156]==='5'&&str_ends_with($name,'/'))$name=substr($name,0,-1);
                if(strlen($name)>512||preg_match('/[\x00-\x20\x7f\\\\]/',$name)||!($name==='opt'||str_starts_with($name,'opt/'))||array_intersect(explode('/',$name),['','.', '..'])||isset($seen[$name])||!in_array($h[156],["\0",'0','5'],true))throw new RuntimeException('invalid_package');$seen[$name]=true;
                $size=(int)octdec($size);$total+=$size;if($total>134217728)throw new RuntimeException('invalid_package');
                if($h[156]==='5'){if($size!==0)throw new RuntimeException('invalid_package');continue;}
                $files++;$hash=hash_init('sha256');for($left=$size;$left>0;){$chunk=self::gzRead($data,min(16384,$left));hash_update($hash,$chunk);$left-=strlen($chunk);}if($size%512)self::gzRead($data,512-$size%512);$digest=hash_final($hash);
                if($defaultsOnly){
                    $target=null;
                    if($name==='opt/etc/nfqws2/nfqws2.conf.notactive')$target='etc/nfqws2/nfqws2.conf';
                    elseif(preg_match('~^opt/etc/nfqws2/lists/([a-zA-Z0-9_.-]+)\.notactive$~D',$name,$match))$target='etc/nfqws2/lists/'.$match[1];
                    elseif(preg_match('~^opt/share/nfqws2-asus/defaults/blobs/([a-zA-Z0-9_.-]+\.bin)$~D',$name,$match))$target='etc/nfqws2/blobs/'.$match[1];
                    if($target!==null){if(count($defaults)>=512||((int)octdec($mode)&0022)!==0)throw new RuntimeException('invalid_package');$defaults[$target]=['mode'=>(int)octdec($mode),'size'=>$size,'sha256'=>$digest];}
                    continue;
                }
                // The package owns these two conffiles, whose active contents
                // are deliberately administrator-specific after installation.
                if(in_array($name,['opt/etc/nfqws-asus-web/auth.json','opt/etc/nfqws-asus-web/support-relay.json'],true))continue;
                $path=$opt.substr($name,3);self::recoveryParents($path,$opt,$owner);$installed=@lstat($path);
                if(!$installed||($installed['mode']&0170000)!==0100000||$installed['uid']!==$owner||$installed['nlink']!==1||($installed['mode']&07777)!==octdec($mode)||$installed['size']!==$size||!hash_equals($digest,hash_file('sha256',$path)))throw new RuntimeException('recovery_required');
            }
            throw new RuntimeException('invalid_package');
        }finally{if(is_resource($out))fclose($out);if(is_resource($outer))gzclose($outer);if(is_resource($data))gzclose($data);@unlink($temporary);}
    }
    public static function space(int|float $free,int $ipk,int $snapshot,int $runtime): bool
    {if(min($free,$ipk,$snapshot,$runtime)<0||$free<$ipk+$snapshot+$runtime+16777216)throw new RuntimeException('insufficient_space');return true;}
}

