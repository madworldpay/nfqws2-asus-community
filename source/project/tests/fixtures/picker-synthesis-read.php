<?php
umask(0077);[$web,$root,$id,$command]=array_slice($argv,1,4);$initial=ini_get('memory_limit');
// Execute the real panel entry's early PHP policy. Keep session/auth outside
// this resource/export fixture; the picker has no standalone HTTP entry.
$index=file_get_contents($web.'/index.php');$end=strpos($index,'require_once');
if($end===false||!str_starts_with($index,'<?php'))throw new RuntimeException('fixture_panel_bootstrap');
eval(substr($index,5,$end-5));
require $web.'/strategy-picker-runtime.php';
$store=new NfqwsStrategyPickerState($root);$runtime=new NfqwsStrategyPickerRuntime($store);
$request=['cmd'=>$command,'csrf_token'=>''];if($command==='pickerexport')$request['id']=$id;
$response=$runtime->dispatch($request);$bytes=strlen(json_encode($response,JSON_THROW_ON_ERROR));
$journal=$store->read();
echo json_encode(['initial_heap'=>$initial,'heap'=>ini_get('memory_limit'),'peak'=>memory_get_peak_usage(true),
    'state'=>$journal['state'],'bytes'=>$bytes,'visible_custom'=>$command==='pickerexport'?null:
      ['hosts'=>$response['job']['custom_hosts']??null,'only'=>$response['job']['custom_only']??null,
       'can_apply'=>$response['job']['can_apply'],'can_export'=>$response['job']['can_export']]],JSON_THROW_ON_ERROR)."\n";
