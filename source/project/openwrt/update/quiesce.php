<?php
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(1);
$args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);
if(count($args)!==1||!in_array($args[0],['upgrade','remove'],true))exit(2);
require_once '/usr/share/nfqws2-web/openwrt-package-quiesce.php';
try{(new NfqwsOpenWrtPackageQuiesce(new AsusUpdateStore()))->run($args[0]);}
catch(Throwable $e){$code=in_array($e->getMessage(),['busy','invalid_request','invalid_state','launch_failed','core_stop_failed'],true)?$e->getMessage():'install_failed';file_put_contents('php://stderr',"Native package operation cannot proceed: ".$code."\n");exit(1);}
