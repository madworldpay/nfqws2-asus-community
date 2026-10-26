<?php
require_once __DIR__.'/openwrt-update-package.php';

/** Application-only native transaction. No general system upgrade is requested. */
final class NfqwsOpenWrtUpdateManager
{
    private static function package(string $name,string $version):void
    {
        if(!preg_match('/^[a-z0-9][a-z0-9+._-]{0,127}$/D',$name)||!preg_match('/^[A-Za-z0-9][A-Za-z0-9.+_:~\-]{0,199}$/D',$version))throw new RuntimeException('pending_packages');
    }
    public static function database(string $raw,string $format,bool $ownTransition=false,bool $ownOnly=false):array
    {
        if(strlen($raw)>2097152||str_contains($raw,"\0")||!in_array($format,['ipk','apk'],true)||trim($raw)==='')throw new RuntimeException('pending_packages');
        $out=[];
        foreach(preg_split('/\n[ \t]*\n/',trim($raw))as $section){
            if($ownOnly&&!preg_match($format==='ipk'?'/^Package:[ \t]+nfqws2-native[ \t]*$/m':'/^P:nfqws2-native$/m',$section))continue;
            if($format==='ipk'){
                $p=AsusUpdatePackage::fields($section);if($ownTransition&&($p['Package']??null)==='nfqws2-native')continue;$status=preg_split('/\s+/',trim($p['Status']??''));$flags=explode(',',$status[1]??'');
                if(count($status)!==3||!in_array($status[0],['install','hold','deinstall','purge','unknown'],true)||array_diff($flags,['ok','user','prefer','hold'])||count($flags)!==count(array_unique($flags)))throw new RuntimeException('pending_packages');
                if(in_array($status[2],['not-installed','config-files'],true))continue;
                if($status[2]!=='installed'||!in_array($status[0],['install','hold'],true))throw new RuntimeException('pending_packages');
                $name=$p['Package']??'';$version=$p['Version']??'';
            }else{
                $p=[];foreach(explode("\n",$section)as $line){if(!preg_match('/^([A-Za-z]):(.*)$/D',$line,$m))throw new RuntimeException('pending_packages');
                    if(in_array($m[1],['P','V','f'],true)){if(isset($p[$m[1]]))throw new RuntimeException('pending_packages');$p[$m[1]]=$m[2];}}
                $name=$p['P']??'';$version=$p['V']??'';if($ownTransition&&$name==='nfqws2-native')continue;
                if(!preg_match('/^[Sx]*$/D',$p['f']??''))throw new RuntimeException('pending_packages');
            }
            self::package($name,$version);if(isset($out[$name]))throw new RuntimeException('pending_packages');$out[$name]=$version;
        }
        if(count($out)>4096||count($out)<1)throw new RuntimeException('pending_packages');ksort($out);return $out;
    }
    public static function raw(array $environment):string
    {
        $file=match($environment['format']??null){'ipk'=>'/usr/lib/opkg/status','apk'=>'/lib/apk/db/installed',default=>throw new RuntimeException('unsupported_abi')};
        $path=realpath($file);if($path===false)throw new RuntimeException('pending_packages');$s=@lstat($path);
        if(!$s||!is_file($path)||$s['uid']!==0||($s['mode']&0022)!==0||$s['size']>2097152)throw new RuntimeException('pending_packages');
        $raw=file_get_contents($path);if(!is_string($raw))throw new RuntimeException('pending_packages');return $raw;
    }
    public static function installed(array $environment,bool $ownTransition=false,bool $ownOnly=false):array
    {return self::database(self::raw($environment),$environment['format'],$ownTransition,$ownOnly);}
    /** Dependencies may name a native installed provider, such as libgcc1 -> libgcc. */
    private static function provided(array $environment,array $installed,bool $ownTransition=false):array
    {
        $raw=self::raw($environment);if(self::database($raw,$environment['format'],$ownTransition)!==$installed)throw new RuntimeException('dependency_change');$out=[];
        foreach(preg_split('/\n[ \t]*\n/',trim($raw))as $section){
            if($environment['format']==='ipk'){$p=AsusUpdatePackage::fields($section);$name=$p['Package']??'';$offers=explode(',',$p['Provides']??'');}
            else{preg_match('/^P:(.*)$/m',$section,$nameRow);$name=$nameRow[1]??'';if(preg_match_all('/^p:(.*)$/m',$section,$rows)>1)throw new RuntimeException('pending_packages');$offers=preg_split('/[ \t]+/',$rows[1][0]??'');}
            if(!isset($installed[$name]))continue;
            foreach($offers as $offer){$offer=trim($offer);
                $pattern=$environment['format']==='ipk'?'/^([a-z0-9][a-z0-9+._-]{0,127})(?:[ \t]+\([<>=]+[ \t]*[A-Za-z0-9.+_:~\-]+\))?$/D':'/^([a-z0-9][a-z0-9+._-]{0,127})(?:=[A-Za-z0-9.+_:~\-]+)?$/D';
                if(preg_match($pattern,$offer,$m))$out[$m[1]]=true;
            }
        }return $out;
    }
    private static function unresolved(array $environment,array $installed,array $depends,bool $ownTransition):array
    {
        if(!array_is_list($depends)||count($depends)>64)throw new RuntimeException('invalid_package');
        foreach($depends as $name)if(!is_string($name)||!preg_match('/^[a-z0-9][a-z0-9+._-]{0,80}$/D',$name))throw new RuntimeException('invalid_package');
        $missing=array_values(array_diff($depends,array_keys($installed)));
        if($missing){$provided=self::provided($environment,$installed,$ownTransition);$missing=array_values(array_filter($missing,fn($name)=>!isset($provided[$name])));}
        return $missing;
    }
    public static function missing(array $environment,array $depends,bool $ownTransition=false):array
    {return self::unresolved($environment,self::installed($environment,$ownTransition),$depends,$ownTransition);}
    public static function argv(string $path,array $environment,array $installed,array $record,?string $keys=null,bool $simulate=false,bool $ownTransition=false):array
    {
        if(($record['name']??null)!=='nfqws2-native'||!is_array($record['depends']??null))throw new RuntimeException('invalid_package');
        if(!str_starts_with($path,'/')||strpbrk($path,"\0\r\n")!==false)throw new RuntimeException('invalid_state');
        if(self::unresolved($environment,$installed,$record['depends'],$ownTransition))throw new RuntimeException('missing_dependencies');
        if(($environment['format']??null)==='ipk')return array_merge(['/bin/opkg','--nodeps'],$simulate?['--noaction']:[],['install',$path]);
        if(($environment['format']??null)!=='apk')throw new RuntimeException('unsupported_abi');
        if($keys===null)throw new RuntimeException('invalid_signature');$argv=['/usr/bin/apk','add','--network=no','--cache=no','--repositories-file','/dev/null','--keys-dir',$keys];
        if($simulate)$argv[]='--simulate';
        $argv[]=$path;return $argv;
    }
    public static function plan(string $raw,string $format,array $record):bool
    {
        if(strlen($raw)>65536||str_contains($raw,"\0"))throw new RuntimeException('dependency_change');$seen=0;$version=preg_quote($record['version']??'','#');
        foreach(explode("\n",trim($raw))as $line){
            if($line==='')continue;
            if($format==='ipk'&&$line==='Multiple packages (nfqws2-native and nfqws2-native) providing same name marked HOLD or PREFER. Using latest.')continue;
            if($format==='ipk'&&preg_match('#^(?:Installing nfqws2-native \('.$version.'\) to root|Upgrading nfqws2-native on root from [A-Za-z0-9.+_:~\-]+ to '.$version.')\.\.\.$#D',$line)){$seen++;continue;}
            if($format==='apk'&&preg_match('#^\(1/1\) (?:Installing nfqws2-native \('.$version.'\)|Upgrading nfqws2-native \([A-Za-z0-9.+_:~\-]+ -> '.$version.'\))$#D',$line)){$seen++;continue;}
            if($format==='apk'&&preg_match('/^OK: [0-9]+(?:\.[0-9]+)? (?:B|KiB|MiB|GiB) in [0-9]+ packages$/D',$line))continue;
            throw new RuntimeException('dependency_change');
        }
        if($seen!==1)throw new RuntimeException('dependency_change');return true;
    }
}
