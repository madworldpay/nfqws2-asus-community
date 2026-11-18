<?php
umask(0077);[$web,$root]=array_slice($argv,1,2);[$stage,$id,$nonce]=array_slice($argv,-3);
require $web.'/strategy-picker-custom-worker.php';$s=new NfqwsStrategyPickerState($root);
$deps=['resolve'=>static function($host){if(NfqwsPublicIpv4::test($host))throw new RuntimeException('fixture_literal_resolved');return ['8.8.8.8'];},'probe'=>static function($host)use($s){
    $recipe=$s->read()['active_recipe']??null;$component=$recipe['tls']??['method'=>'pass'];
    $literal=NfqwsPublicIpv4::test($host);
    foreach($recipe['overrides']??[]as $rule)if($rule['protocol']==='tls'){
        if(isset($rule['addresses'])){if($literal&&in_array($host,$rule['addresses'],true)){$component=$rule['component'];break;}}
        else foreach($rule['domains']as $domain)if(!$literal&&($host===$domain||str_ends_with($host,'.'.$domain))){$component=$rule['component'];break 2;}
    }
    if($literal&&$recipe===null)$component=['method'=>'pass'];
    $expected=in_array($host,['alpha.example.com','delta.example.com','gamma.example.com','8.8.8.8'],true)?'multisplit':'multidisorder';
    $response=AsusDpiSiteCheck::response('response');$response['http_status']=($component['method']??null)===$expected?200:403;
    $response['redirect']='https://private.example.com/path?token=DO_NOT_EXPORT_DIAGNOSTIC';
    return $response;
}];
$input=NfqwsStrategyPickerCustomWorker::readInput(fopen('php://stdin','rb'));
echo json_encode((new NfqwsStrategyPickerCustomWorker($s,$deps))->execute($stage,$id,$nonce,$input));
