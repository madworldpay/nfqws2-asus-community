<?php
/** Bootstrap-trusted key/discovery apply only to this transaction, never live files. */
final class NfqwsOpenWrtInstallTrust
{
    public static function stage(AsusUpdateStore $local,string $key,string $schema,string $discovery,string $installed='/usr/share/nfqws2-web',int $owner=0):array
    {
        $local->directory('coordinator');$app=$local->directory('coordinator/app');$resources=$local->directory('coordinator/resources');
        $files=glob($installed.'/*.php')?:[];
        if(count($files)<1||count($files)>128)throw new RuntimeException('runtime_limit');
        $files[]=$installed.'/platform-profile.json';$bytes=0;
        foreach($files as $file){
            AsusUpdateStore::noLinks($file);clearstatcache(true,$file);$s=@lstat($file);
            if(!$s||!is_file($file)||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>131072||($bytes+=$s['size'])>16777216)throw new RuntimeException('invalid_state');
            $raw=file_get_contents($file);if(!is_string($raw)||strlen($raw)!==$s['size'])throw new RuntimeException('invalid_state');
            $local->writeFile('coordinator/app/'.basename($file),basename($file)==='update-github.php'?$discovery:$raw);
        }
        $local->writeFile('coordinator/resources/update-release-key.pem',$key);
        $local->writeFile('coordinator/resources/openwrt-package-manifest.schema.json',$schema);
        return ['application'=>$app,'resources'=>$resources];
    }
}
