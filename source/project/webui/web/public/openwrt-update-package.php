<?php
require_once __DIR__.'/openwrt-update-environment.php';

/** Read-only preparation contract, before a package manager may run hooks. */
final class NfqwsOpenWrtUpdatePackage
{
    private static function identity(array $candidate,array $environment):array
    {
        $p=$candidate['package']??[];
        if(($environment['platform']??null)!=='openwrt'||!in_array($p['format']??null,['ipk','apk'],true))throw new RuntimeException('unsupported_abi');
        foreach(['series','format','arch']as $field)if(($p[$field]??null)!==($environment[$field]??null))throw new RuntimeException('unsupported_abi');
        return $p;
    }
    public static function metadata(array $record,array $candidate,array $environment):array
    {
        $p=self::identity($candidate,$environment);
        if(($record['name']??null)!=='nfqws2-native'||($record['version']??null)!==($candidate['package_version']??null)||
            ($record['version']??null)!==($p['version']??null)||($record['arch']??null)!==($p['arch']??null)||
            ($record['replaces']??[])!==[]||($record['conflicts']??[])!==[])throw new RuntimeException('invalid_package');
        $deps=$record['depends']??null;
        if(!is_array($deps)||!array_is_list($deps)||count($deps)>64)throw new RuntimeException('invalid_package');
        $seen=[];foreach($deps as $dep){if(!is_string($dep)||!preg_match('/^[a-z0-9][a-z0-9+._-]{0,80}$/D',$dep)||isset($seen[$dep]))throw new RuntimeException('invalid_package');$seen[$dep]=true;}
        $size=$record['installed_size']??null;$bound=$p['installed_size']??null;
        if(!is_int($bound)||$bound<1||$bound>134217728||($p['format']==='apk'&&(!is_int($size)||$size<1))||
            ($size!==null&&(!is_int($size)||$size<0||$size>$bound)))throw new RuntimeException('invalid_package');
        return $record;
    }
    public static function inspect(string $path,array $candidate,array $environment,?string $keys=null,int $owner=0):array
    {
        $p=self::identity($candidate,$environment);AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||!is_file($path)||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0777)!==0600)throw new RuntimeException('invalid_state');
        if($s['size']!==($p['size']??null)||$s['size']>33554432)throw new RuntimeException('download_size');
        $hash=hash_file('sha256',$path);if(!is_string($p['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$p['sha256'])||!is_string($hash)||!hash_equals($p['sha256'],$hash))throw new RuntimeException('download_hash');
        if($p['format']==='ipk'){
            $fields=AsusUpdatePackage::nativeControl($path);
            $list=static fn(string $s):array=>trim($s)===''?[]:array_map('trim',explode(',',$s));
            $record=['name'=>$fields['Package']??null,'version'=>$fields['Version']??null,'arch'=>$fields['Architecture']??null,
                'depends'=>$list($fields['Depends']??''),'installed_size'=>null,'replaces'=>$list($fields['Replaces']??''),'conflicts'=>$list($fields['Conflicts']??'')];
        }else{
            if($keys===null)throw new RuntimeException('invalid_signature');AsusUpdateStore::noLinks($keys);$k=@lstat($keys);
            if(!$k||!is_dir($keys)||$k['uid']!==$owner||($k['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
            $verified=NfqwsPlatform::run(['/usr/bin/apk','verify','--keys-dir',$keys,$path],30);
            if($verified['status']!==0)throw new RuntimeException('invalid_signature');
            $dump=NfqwsPlatform::run(['/usr/bin/apk','adbdump','--format','json',$path],30,[],1048576);
            if($dump['status']!==0)throw new RuntimeException('invalid_package');
            $data=AsusSupportSchema::toArray(AsusSupportSchema::decode(implode("\n",$dump['output']),1048576,'invalid_package'));
            $info=$data['info']??null;if(!is_array($info))throw new RuntimeException('invalid_package');
            $record=['name'=>$info['name']??null,'version'=>$info['version']??null,'arch'=>$info['arch']??null,
                'depends'=>$info['depends']??[],'installed_size'=>$info['installed-size']??null,'replaces'=>$info['replaces']??[],'conflicts'=>$info['conflicts']??[]];
        }
        return self::metadata($record,$candidate,$environment);
    }
    public static function space(int|float $overlay,int|float $ram,array $package,int $snapshot,int $runtime):bool
    {
        $stored=$package['installed_size']??null;$download=$package['size']??null;
        if(!is_int($stored)||$stored<1||$stored>134217728||!is_int($download)||$download<1||$download>33554432)throw new RuntimeException('invalid_package');
        if(!is_finite((float)$overlay)||!is_finite((float)$ram)||min($overlay,$ram,$snapshot,$runtime)<0||
            $overlay<$stored+4194304||$ram<$download+$snapshot+$runtime+4194304)throw new RuntimeException('insufficient_space');
        return true;
    }
}
