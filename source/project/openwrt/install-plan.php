<?php
require_once __DIR__.'/../webui/web/public/openwrt-update-environment.php';
require_once __DIR__.'/../webui/web/public/openwrt-update-manifest.php';

/** Pure bootstrap policy. Only verified metadata may select a native action. */
final class NfqwsOpenWrtInstallPlan
{
    public static function select(string $json,string $signature,string $key,string $release,?array $own=null,?string $schema=null):array
    {
        $manifest=NfqwsOpenWrtPackageManifest::verify($json,$signature,$key,$schema);
        $firmware=NfqwsOpenWrtUpdateEnvironment::firmware($release);
        $candidate=NfqwsOpenWrtPackageManifest::select($manifest,$firmware);$action='install';
        if($own!==null){
            $keys=array_keys($own);sort($keys);
            if($keys!==['arch','build','format','name','state','version']||$own['name']!=='nfqws2-native'||$own['format']!==$firmware['format']||$own['arch']!==$firmware['arch']||
                !in_array($own['state'],['installed','unpacked','recovery_pending','broken'],true)||!is_int($own['build'])||$own['build']<1||$own['build']>2147483647||
                !is_string($own['version'])||!preg_match('/^(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-'.($firmware['format']==='apk'?'r':'').'[1-9][0-9]{0,9}$/D',$own['version']))throw new RuntimeException('unsupported_version');
            if($own['version']===$candidate['package_version']){
                if($own['build']>$manifest['build'])throw new RuntimeException('unsupported_version');
                $action=$own['state']==='installed'&&$own['build']===$manifest['build']?'current':
                    ($firmware['format']==='ipk'&&$own['state']==='unpacked'?'configure':'repair_required');
            }else{
                if(NfqwsOpenWrtPackageManifest::candidate($manifest,$firmware,$own['version'],$own['build'])===null)throw new RuntimeException('unsupported_version');$action='upgrade';
            }
        }
        return ['action'=>$action,'firmware'=>$firmware,'candidate'=>$candidate,'installed'=>$own];
    }
}
