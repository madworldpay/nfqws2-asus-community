<?php
/** Bootstrap-trusted key/discovery apply only to this transaction, never live files. */
final class NfqwsOpenWrtInstallTrust
{
    public static function stage(AsusUpdateStore $local,string $key,string $schema,string $discovery,string $installed='/usr/share/nfqws2-web',int $owner=0):array
    {
        $local->directory('coordinator');$app=$local->directory('coordinator/app');$resources=$local->directory('coordinator/resources');
        $files=glob($installed.'/*.php')?:[];
        if(!$files)throw new RuntimeException('runtime_limit');
        $files[]=$installed.'/platform-profile.json';$bytes=0;$indexBytes=0;
        foreach($files as $file){
            AsusUpdateStore::noLinks($file);clearstatcache(true,$file);$s=@lstat($file);
            if(!$s||!is_file($file)||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>131072||($bytes+=$s['size'])>16777216)throw new RuntimeException('invalid_state');
            $raw=file_get_contents($file);if(!is_string($raw)||strlen($raw)!==$s['size'])throw new RuntimeException('invalid_state');
            $name='app/'.basename($file);
            if($name==='app/update-github.php')$raw=$discovery;
            $entry=['mode'=>0600,'size'=>strlen($raw),'sha256'=>str_repeat('0',64)];
            $indexBytes+=strlen(json_encode([$name=>$entry],JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES))-1;
            if($indexBytes>131072)throw new RuntimeException('runtime_limit');
            $local->writeFile('coordinator/'.$name,$raw);
        }
        $local->writeFile('coordinator/resources/update-release-key.pem',$key);
        $local->writeFile('coordinator/resources/openwrt-package-manifest.schema.json',$schema);
        return ['application'=>$app,'resources'=>$resources];
    }

    /** Pair the corrected space check with its caller only for the known old code. */
    public static function refreshBuild107Apply(AsusUpdateStore $local,array $installed):void
    {
        if(($installed['build']??null)!==107||!in_array($installed['version']??null,['1.3.2-107','1.3.2-r107'],true))return;
        foreach(NFQWS_NATIVE_INSTALL_BUILD107_APPLY as $name=>[$sha,$replacement]){
            $source=$local->readFile('coordinator/app/'.$name);
            if($source===null||!hash_equals($sha,hash('sha256',$source)))return;
        }
        foreach(NFQWS_NATIVE_INSTALL_BUILD107_APPLY as $name=>[$sha,$replacement]){
            $local->writeFile('coordinator/app/'.$name,$replacement);
        }
    }
}
