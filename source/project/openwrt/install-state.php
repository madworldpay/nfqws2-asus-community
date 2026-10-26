<?php
require_once __DIR__.'/../webui/web/public/openwrt-update-manager.php';

/** Native manager state is observed, never repaired by editing its database. */
final class NfqwsOpenWrtInstallState
{
    public static function parse(string $raw,array $environment,?string $profile):?array
    {
        $format=$environment['format']??null;NfqwsOpenWrtUpdateManager::database($raw,$format,true);$own=null;
        foreach(preg_split('/\n[ \t]*\n/',trim($raw))as $section){
            if($format==='ipk'){
                $v=AsusUpdatePackage::fields($section);if(($v['Package']??null)!=='nfqws2-native')continue;
                $status=preg_split('/\s+/',trim($v['Status']??''));$flags=explode(',',$status[1]??'');
                if(count($status)!==3||!in_array($status[0],['install','hold','deinstall','purge','unknown'],true)||array_diff($flags,['ok','user','prefer','hold'])||count($flags)!==count(array_unique($flags)))throw new RuntimeException('pending_packages');
                if(in_array($status[2],['not-installed','config-files'],true))continue;
                if(!in_array($status[2],['installed','unpacked'],true)||!in_array($status[0],['install','hold','deinstall'],true))throw new RuntimeException('pending_packages');
                $state=$status[2]==='unpacked'?'unpacked':($status[0]==='deinstall'?'recovery_pending':'installed');$version=$v['Version']??null;$arch=$v['Architecture']??null;
            }else{
                $v=[];foreach(explode("\n",$section)as $line){if(preg_match('/^([PVAf]):(.*)$/D',$line,$m)){if(isset($v[$m[1]]))throw new RuntimeException('pending_packages');$v[$m[1]]=$m[2];}}
                if(($v['P']??null)!=='nfqws2-native')continue;$version=$v['V']??null;$arch=$v['A']??null;$state=preg_match('/^[Sx]*$/D',$v['f']??'')?'installed':'broken';
            }
            if($own!==null)throw new RuntimeException('pending_packages');
            if(!is_string($version)||!preg_match('/^(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-'.($format==='apk'?'r':'').'([1-9][0-9]{0,9})$/D',$version,$parts)||(float)$parts[1]>2147483647||$arch!==($environment['arch']??null))throw new RuntimeException('unsupported_version');
            $build=(int)$parts[1];$valid=false;
            if($profile!==null){try{$p=AsusSupportSchema::toArray(AsusSupportSchema::decode($profile,4096,'invalid_state'));
                $valid=is_array($p)&&($p['platform']??null)==='openwrt'&&($p['series']??null)===($environment['series']??null)&&($p['arch']??null)===$arch&&($p['format']??null)===$format&&($p['version']??null)===$version&&is_int($p['application_build']??null)&&$p['application_build']>=1&&$p['application_build']<=2147483647;
                if($valid)$build=$p['application_build'];
            }catch(Throwable $ignored){}}
            if(!$valid)$state='broken';
            $own=['name'=>'nfqws2-native','version'=>$version,'arch'=>$arch,'format'=>$format,'state'=>$state,'build'=>$build];
        }
        return $own;
    }
    public static function read(array $environment):?array
    {
        $raw=NfqwsOpenWrtUpdateManager::raw($environment);$profile=null;$path='/usr/share/nfqws2/platform.json';
        try{AsusUpdateStore::noLinks($path);$s=@lstat($path);$safe=$s&&is_file($path)&&$s['uid']===0&&$s['nlink']===1&&($s['mode']&0022)===0&&$s['size']<=4096;
            for($parent=dirname($path);$safe&&$parent!=='/';$parent=dirname($parent)){$d=@lstat($parent);$safe=$d&&is_dir($parent)&&$d['uid']===0&&($d['mode']&0022)===0;}
            if($safe){$p=file_get_contents($path);if(is_string($p))$profile=$p;}
        }catch(Throwable $ignored){}
        return self::parse($raw,$environment,$profile);
    }
}
