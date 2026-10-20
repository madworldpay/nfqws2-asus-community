<?php
// CLI only; no HTTP endpoint, persistent worker, credentials or report payload.
if(isset($_SERVER['REQUEST_METHOD'])||($argv[1]??'')!=='location'){http_response_code(403);exit;}
require_once __DIR__.'/support-mail.php';
try {
    $raw=file_get_contents('php://stdin',false,null,0,8193);$v=is_string($raw)&&strlen($raw)<=8192?json_decode($raw,true,8):null;
    if(!is_array($v)||array_keys($v)!==['config','ca','owner']||!is_string($v['config'])||!is_string($v['ca'])||!is_int($v['owner']))throw new RuntimeException();
    echo json_encode((new AsusSupportMail($v['config'],$v['ca'],$v['owner']))->locationDirect(),JSON_THROW_ON_ERROR);
}catch(Throwable $e){echo '{"available":false,"code":"unavailable"}';}
