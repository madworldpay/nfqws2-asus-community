<?php
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(1);
require_once '/usr/share/nfqws2-web/openwrt-apk-adapter.php';
try{(new NfqwsOpenWrtApkAdapter(new AsusUpdateStore()))->run();}
catch(Throwable $e){$code=in_array($e->getMessage(),['busy','invalid_state','launch_failed','core_stop_failed','unsupported_manager_command','package_preflight_failed'],true)?$e->getMessage():'install_failed';file_put_contents('php://stderr',"NFQWS2 native package operation stopped before file replacement: ".$code.". Use a normal native package command after resolving the service conflict.\n");exit(1);}
