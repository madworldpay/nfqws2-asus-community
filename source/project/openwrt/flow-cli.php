<?php
require_once __DIR__.'/flow.php';
try {
    $input=fopen('php://stdin','rb');$raw=stream_get_contents($input,2097153);fclose($input);
    if(!is_string($raw)||strlen($raw)>2097152)throw new RuntimeException('firewall_snapshot_limit');
    $plan=NfqwsNativeFlow::inspect(json_decode($raw,true,512,JSON_THROW_ON_ERROR));
    echo 'NFQWS_FLOW_STATE='.escapeshellarg($plan['state'])."\n";
    echo 'NFQWS_FLOW_HANDLE='.escapeshellarg($plan['handle']===null?'':(string)$plan['handle'])."\n";
    echo 'NFQWS_FLOW_DEFINITION='.escapeshellarg($plan['definition'])."\n";
}catch(Throwable $e){file_put_contents('php://stderr','Acceleration check failed: '.$e->getMessage()."\n");exit(1);}
