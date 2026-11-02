<?php
// Installed outside the document root. Session arguments come from root-owned launchers.
if(isset($_SERVER['REQUEST_METHOD'])||!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(1);
// Run/guard live until the signed wall-clock and uptime deadlines or revocation,
// not until CGI's cumulative 30 CPU seconds. HTTP code keeps its normal limit.
set_time_limit(0);
require_once '/opt/share/nfqws-asus-web/technical-channel.php';
$mode=$argv[count($argv)-2]??'';$id=$argv[count($argv)-1]??'';
try{
    $c=new AsusTechnicalChannel();
    if($mode==='run'){$c->run($id);exit(0);}
    if($mode==='guard')exit($c->command($id));
    if($mode==='recover'){$c->status();exit(0);}
    if($mode==='stop'){$c->stop();exit(0);}
}catch(Throwable $e){exit(1);}
exit(1);
