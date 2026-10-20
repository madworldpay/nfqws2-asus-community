<?php
require_once __DIR__.'/support-json-schema.php';

/** Release metadata is trusted only after closed-schema and pinned-key verification. */
final class AsusPackageManifest
{
    private const CORE='(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-asus[1-9][0-9]{0,5}';

    private static function version(string $version,string $code): array
    {
        if(!preg_match('/^('.self::CORE.')\+b([1-9][0-9]{0,9})$/D',$version,$m)||(float)$m[2]>2147483647)throw new RuntimeException($code);
        preg_match('/^([0-9]+)\.([0-9]+)\.([0-9]+)-asus([0-9]+)$/D',$m[1],$c);
        return ['core'=>$m[1],'parts'=>array_map('intval',array_slice($c,1)),'build'=>(int)$m[2]];
    }

    public static function verify(string $json,string $signature,string $publicKey): array
    {
        $value=AsusSupportSchema::decode($json,32768,'invalid_manifest');
        $path=dirname(__DIR__).'/resources/package-manifest.schema.json';
        if(!is_file($path))$path='/opt/share/nfqws2-asus/package-manifest.schema.json';
        if(!is_file($path))$path=dirname(__DIR__,3).'/updates/package-manifest.schema.json';
        try {
            $raw=@file_get_contents($path);if(!is_string($raw))throw new RuntimeException();
            $schema=json_decode($raw,true,32,JSON_THROW_ON_ERROR);
            AsusSupportSchema::projection($value,$schema,$schema);
        }catch(Throwable $e){throw new RuntimeException('invalid_manifest');}
        $manifest=json_decode($json,true,32,JSON_THROW_ON_ERROR);
        $version=self::version($manifest['package_version'],'invalid_manifest');
        if(!is_int($manifest['build'])||$version['build']!==$manifest['build']||$version['core']!==$manifest['core_version'])throw new RuntimeException('invalid_manifest');
        $seen=[];
        foreach($manifest['packages'] as $package){
            if(isset($seen[$package['family']])||!is_int($package['size'])||$package['filename']!=='nfqws2-asus_'.$manifest['package_version'].'_'.$package['family'].'.ipk')throw new RuntimeException('invalid_manifest');
            $seen[$package['family']]=true;
        }
        if(!extension_loaded('openssl'))throw new RuntimeException('signature_unavailable');
        if(strlen($signature)>1024)throw new RuntimeException('invalid_signature');
        $signature=trim($signature);$bytes=base64_decode($signature,true);
        if($bytes===false||strlen($bytes)!==384||base64_encode($bytes)!==$signature)throw new RuntimeException('invalid_signature');
        $key=@openssl_pkey_get_public($publicKey);$details=$key===false?false:openssl_pkey_get_details($key);
        if(!$details||$details['type']!==OPENSSL_KEYTYPE_RSA||$details['bits']!==3072||@openssl_verify($json,$bytes,$key,OPENSSL_ALGO_SHA256)!==1)throw new RuntimeException('invalid_signature');
        $manifest['revision']=hash('sha256',$json);
        return $manifest;
    }

    public static function candidate(array $manifest,string $family,string $installedVersion): ?array
    {
        if(!in_array($family,['aarch64-3.10','armv7'],true))throw new RuntimeException('unsupported_abi');
        $installed=self::version($installedVersion,'unsupported_version');
        $target=self::version($manifest['package_version'],'invalid_manifest');
        // The global Build increases across core versions; a signed old core is never an upgrade.
        if($target['build']<=$installed['build']||$target['parts']<$installed['parts'])return null;
        foreach($manifest['packages'] as $package)if($package['family']===$family)return [
            'revision'=>$manifest['revision'],'package_version'=>$manifest['package_version'],
            'core_version'=>$manifest['core_version'],'web_version'=>$manifest['web_version'],
            'build'=>$manifest['build'],'notes'=>$manifest['notes'],'package'=>$package,
        ];
        throw new RuntimeException('unsupported_package');
    }
}
