<?php
require $argv[1].'/strategy-picker-runtime.php';
umask(0077);$id=str_repeat('a',32);
$s=new NfqwsStrategyPickerState($argv[2]);
$lock=$s->lock();
(new AsusImportTransaction())->writer(function()use($s,$id){
    $s->write(['id'=>$id,'identity'=>NfqwsStrategyPickerRuntime::identity(getmypid())],'actor-work.json');
    while(true)sleep(1);
});
