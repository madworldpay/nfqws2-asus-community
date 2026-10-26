<?php
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(1);
$args=$argv;array_shift($args);if(($args[0]??null)==='--')array_shift($args);if($args!==[])exit(2);
require_once '/usr/share/nfqws2-web/openwrt-resource-upgrade.php';
try{
    if(!NfqwsPlatform::native())throw new RuntimeException('unsupported_abi');
    NfqwsOpenWrtResourceUpgrade::apply('/tmp/nfqws2-native-package/previous-resources.json','/usr/share/nfqws2/defaults','/etc/nfqws2');
}catch(Throwable $e){file_put_contents('php://stderr',"Native stock resources could not be updated: ".$e->getMessage()."\n");exit(1);}
