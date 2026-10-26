<?php
require_once __DIR__.'/update-manifest.php';

/** Native and Entware releases use the same trust key, separate closed identities. */
final class NfqwsOpenWrtPackageManifest
{
    public static function verify(string $json,string $signature,string $key,?string $schemaPath=null):array
    {
        $value=AsusSupportSchema::decode($json,32768,'invalid_manifest');
        $path=$schemaPath??NfqwsPlatform::sharedFile('openwrt-package-manifest.schema.json',dirname(__DIR__,3).'/updates/openwrt-package-manifest.schema.json');
        try{$schema=json_decode((string)file_get_contents($path),true,32,JSON_THROW_ON_ERROR);AsusSupportSchema::projection($value,$schema,$schema);}
        catch(Throwable $e){throw new RuntimeException('invalid_manifest');}
        $v=AsusSupportSchema::toArray($value);$seen=[];
        foreach($v['packages']as $p){
            $format=$p['series']==='24.10'?'ipk':'apk';
            $version=$v['core_version'].'-'.($format==='apk'?'r':'').$v['build'];
            $name='nfqws2-native_'.$version.'_'.$p['arch'].'.'.$format;
            $id=$p['series'].':'.$p['arch'];
            if(isset($seen[$id])||$p['format']!==$format||$p['version']!==$version||$p['filename']!==$name)throw new RuntimeException('invalid_manifest');
            $seen[$id]=true;
        }
        AsusPackageManifest::verifySignature($json,$signature,$key);
        $v['revision']=hash('sha256',$json);return $v;
    }

    public static function candidate(array $manifest,array $identity,string $installed,int $build):?array
    {
        $series=$identity['series']??null;$format=$series==='24.10'?'ipk':($series==='25.12'?'apk':null);
        $arch=$identity['arch']??null;
        if(($identity['platform']??null)!=='openwrt'||$format===null||($identity['format']??null)!==$format||!is_string($arch)||!preg_match('/^[a-z0-9][a-z0-9_+-]{0,99}$/D',$arch))throw new RuntimeException('unsupported_abi');
        $suffix=$format==='apk'?'r':'';
        if(!preg_match('/^((?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5}))-'.$suffix.'([1-9][0-9]{0,9})$/D',$installed,$m)||(float)$m[2]>2147483647||$build<1)throw new RuntimeException('unsupported_version');
        if($manifest['build']<=$build||$manifest['build']<=(int)$m[2]||version_compare($manifest['core_version'],$m[1],'<'))return null;
        foreach($manifest['packages']as $p)if($p['series']===$series&&$p['arch']===$arch&&$p['format']===$format)return [
            'revision'=>$manifest['revision'],'package_version'=>$p['version'],'core_version'=>$manifest['core_version'],
            'web_version'=>$manifest['web_version'],'build'=>$manifest['build'],'notes'=>$manifest['notes'],
            'package'=>$p+['family'=>$arch],
        ];
        throw new RuntimeException('unsupported_package');
    }
}
