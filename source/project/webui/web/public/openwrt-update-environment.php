<?php
require_once __DIR__.'/update-prepare.php';

/** Actual firmware metadata and the native manager must agree with our package. */
final class NfqwsOpenWrtUpdateEnvironment
{
    public static function resolve(string $release,array $profile,array $record):array
    {
        if(strlen($release)>16384||str_contains($release,"\0"))throw new RuntimeException('unsupported_abi');
        $fields=[];preg_match_all("/^DISTRIB_(RELEASE|ARCH|TARGET)='([^'\r\n]*)'$/m",$release,$matches,PREG_SET_ORDER);
        foreach($matches as $m){if(isset($fields[$m[1]]))throw new RuntimeException('unsupported_abi');$fields[$m[1]]=$m[2];}
        $arch=$fields['ARCH']??'';
        if(count($fields)!==3||!preg_match('/^(24\.10|25\.12)(?:\.[0-9]+)?(?:[-+][A-Za-z0-9_.-]+)?$/D',$fields['RELEASE'],$m)||
            !preg_match('/^[a-z0-9][a-z0-9_+-]{0,99}$/D',$arch)||!preg_match('~^[a-z0-9_-]+/[a-z0-9_-]+$~D',$fields['TARGET']))throw new RuntimeException('unsupported_abi');
        $series=$m[1];$format=$series==='24.10'?'ipk':'apk';
        if(($profile['platform']??null)!=='openwrt'||($profile['arch']??null)!==$arch||($profile['series']??null)!==$series||($profile['format']??null)!==$format)throw new RuntimeException('unsupported_abi');
        $version=$profile['version']??null;$build=$profile['application_build']??null;
        if(!is_string($version)||!preg_match('/^(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-'.($format==='apk'?'r':'').'[1-9][0-9]{0,9}$/D',$version)||!is_int($build)||$build<1||$build>2147483647)throw new RuntimeException('unsupported_version');
        if(($record['name']??null)!=='nfqws2-native'||($record['version']??null)!==$version||($record['arch']??null)!==$arch)throw new RuntimeException('version_mismatch');
        return ['platform'=>'openwrt','series'=>$series,'arch'=>$arch,'format'=>$format,'target'=>$fields['TARGET'],
            'installed'=>$version,'build'=>$build,'manager'=>$format==='ipk'?'/bin/opkg':'/usr/bin/apk'];
    }

    public static function opkgRecord(string $raw):array
    {
        $v=AsusUpdatePackage::fields($raw);$status=preg_split('/\s+/',trim($v['Status']??''));
        $flags=explode(',',$status[1]??'');
        if(count($status)!==3||!in_array($status[0],['install','hold'],true)||$status[2]!=='installed'||count($flags)!==count(array_unique($flags))||array_diff($flags,['ok','user','prefer']))throw new RuntimeException('pending_packages');
        return ['name'=>$v['Package']??null,'version'=>$v['Version']??null,'arch'=>$v['Architecture']??null];
    }

    public static function collect():array
    {
        if(!NfqwsPlatform::native())throw new RuntimeException('unsupported_abi');
        $path=NfqwsPlatform::sharedFile('platform.json','/usr/share/nfqws2/platform.json');
        $raw=@file_get_contents($path,false,null,0,4097);if(!is_string($raw)||strlen($raw)>4096)throw new RuntimeException('unsupported_abi');
        $profile=AsusSupportSchema::toArray(AsusSupportSchema::decode($raw,4096,'unsupported_abi'));
        if(!is_array($profile))throw new RuntimeException('unsupported_abi');
        $release=(string)@file_get_contents('/etc/openwrt_release',false,null,0,16385);
        $format=$profile['format']??null;
        if($format==='ipk'){
            $r=NfqwsPlatform::run(['/bin/opkg','status','nfqws2-native'],5);
            if($r['status']!==0)throw new RuntimeException('unsupported_version');
            $record=self::opkgRecord(implode("\n",$r['output']));
        }elseif($format==='apk'){
            $r=NfqwsPlatform::run(['/usr/bin/apk','query','--installed','--format','json','--fields','name,version,arch','nfqws2-native'],5);
            if($r['status']!==0)throw new RuntimeException('unsupported_version');
            $rows=AsusSupportSchema::toArray(AsusSupportSchema::decode(implode("\n",$r['output']),65536,'unsupported_version'));
            if(!is_array($rows)||array_keys($rows)!==[0]||!is_array($rows[0]))throw new RuntimeException('unsupported_version');$record=$rows[0];
        }else throw new RuntimeException('unsupported_abi');
        return self::resolve($release,$profile,$record);
    }
}
