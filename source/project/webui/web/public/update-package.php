<?php
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
    private static function control(string $path,string $family): array
    {
        if(!function_exists('gzopen'))throw new RuntimeException('package_reader_unavailable');$f=@gzopen($path,'rb');if(!$f)throw new RuntimeException('invalid_package');$found=[];$control=null;$total=0;
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
            if($h['name']==='control'){if($h['size']>16384)throw new RuntimeException('invalid_package');$fields=self::fields(substr($tar,$p,$h['size']));}$p+=(int)(ceil($h['size']/512)*512);
        }if($fields===null)throw new RuntimeException('invalid_package');sort($bootstrap);sort($helpers);if($bootstrap!==[]&&$bootstrap!==$helpers)throw new RuntimeException('invalid_package');return $fields;
    }
    public static function nativeControl(string $path):array{return self::control($path,'native');}
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

