<?php
require_once __DIR__.'/config.php';
try {
    if(count($argv)!==2)throw new RuntimeException('invalid_request');
    $path=$argv[1];
    if($path!=='/etc/nfqws2/nfqws2.conf')throw new RuntimeException('invalid_config_path');
    for($p=$path;$p!=='/';$p=dirname($p)) {
        clearstatcache(true,$p);$s=@lstat($p);
        if(!$s||$s['uid']!==0||is_link($p)||($s['mode']&0022)!==0)throw new RuntimeException('unsafe_config_file');
    }
    if(!is_file($path)||filesize($path)>262144)throw new RuntimeException('invalid_native_config');
    $raw=file_get_contents($path);if(!is_string($raw))throw new RuntimeException('invalid_native_config');
    echo NfqwsNativeConfig::shell(NfqwsNativeConfig::parse($raw));
}catch(Throwable $e){file_put_contents('php://stderr',"Native configuration could not be read: ".$e->getMessage()."\n");exit(1);}
