<?php
umask(0077);[$web,$root]=array_slice($argv,1,2);[$stage,$id,$nonce]=array_slice($argv,-3);
require $web.'/strategy-picker-custom-worker.php';$s=new NfqwsStrategyPickerState($root);
$deps=['probe'=>static function()use($id){
    file_put_contents('/tmp/custom-guard-ready-'.$id,'child');
    while(true)usleep(10000);
}];
$input=NfqwsStrategyPickerCustomWorker::readInput(fopen('php://stdin','rb'));
echo json_encode((new NfqwsStrategyPickerCustomWorker($s,$deps))->execute($stage,$id,$nonce,$input));
