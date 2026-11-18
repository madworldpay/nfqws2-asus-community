<?php
umask(0077);[$web,$root,$id,$stage]=array_slice($argv,1,4);
require $web.'/strategy-picker-custom-supervisor.php';
require_once $web.'/strategy-picker-custom-samples.php';
$s=new NfqwsStrategyPickerState($root);$cfg=new NfqwsStrategyPickerConfig($s,NfqwsPlatform::settings()['config'].'/nfqws2.conf');
$r=new NfqwsStrategyPickerRuntime($s,$cfg);$lock=$s->lock();
(new AsusImportTransaction())->writer(function()use($s,$r,$web,$root,$id,$stage){
    $s->write(['id'=>$id,'identity'=>NfqwsStrategyPickerRuntime::identity(getmypid())],'actor-work.json');
    for($i=0;$i<100;$i++){
        $g=$s->read('actor-guard.json');
        if(($g['id']??null)===$id&&NfqwsStrategyPickerRuntime::sameActor($g['identity']??null))break;
        usleep(100000);
    }
    $ready='/tmp/custom-guard-ready-'.$id;
    if($stage==='foreign'){
        $j=$s->read();$j['custom_worker']=['stage'=>'prepare','nonce'=>'foreign'];
        $j['actuator']=json_decode(file_get_contents('/tmp/custom-guard-foreign-proof.json'),true);$s->write($j);
        file_put_contents($ready,'foreign');while(true)usleep(10000);
    }
    $check=function()use($s,$r,$stage,$ready){
        (new ReflectionMethod($r,'customCheckpoint'))->invoke($r);
        $j=$s->read();$p=$j['custom_sample_pending']??null;
        if(in_array($stage,['empty','full'],true)&&is_array($p['identity']??null)){
            $file=$s->root.'/custom-'.$j['id'].'-'.$p['id'].'.json';clearstatcache(true,$file);
            if(is_file($file)&&($stage==='empty'?filesize($file)===0:filesize($file)>0)){
                file_put_contents($ready,$stage);while(true)usleep(10000);
            }
        }
    };
    $j=$s->read();$manifest=$j['custom_manifest'];$dns=$manifest['dns_context'];
    $ctx=['nfqws'=>'running','ark'=>'absent','tun_observed'=>false,
        'dns'=>['schema_version'=>1,'state'=>'known','sha256'=>$dns]];
    $context=$ctx;ksort($context);$contextSha=hash('sha256',json_encode($context,JSON_THROW_ON_ERROR));
    $probe=function()use($s,$r,$web,$root,$id,$stage,$check,$manifest,$dns){
        if($stage==='child'){
            $transport=function($args,$seconds,$input,$checkpoint)use($r,$web,$root){
                $actual=['/usr/bin/php8-cgi','-n','-d','register_argc_argv=1','-d','max_execution_time=0',
                    '-d','max_input_time=0','-q','-f','/fixtures/custom-leaf.php','--',$web,$root,...array_slice($args,-5)];
                return (new ReflectionMethod($r,'actuator'))->invoke($r,$actual,$seconds,$input,$checkpoint);
            };
            $sup=new NfqwsStrategyPickerCustomSupervisor($s,$check,$transport,
                static fn()=>['schema_version'=>1,'state'=>'known','sha256'=>$dns]);
            return $sup->probe();
        }
        $response=AsusDpiSiteCheck::response('response');$response['http_status']=200;
        return ['schema_version'=>1,'hosts'=>$manifest['hosts'],'dns_context'=>$dns,
            'fingerprint'=>$manifest['fingerprint'],'manifest_sha256'=>hash('sha256',json_encode($manifest,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR)),
            'observations'=>[['host'=>'example.com','tls'=>'tls12','response'=>$response],['host'=>'example.com','tls'=>'tls13','response'=>$response]]];
    };
    $samples=new NfqwsStrategyPickerCustomSamples($s,$check,static fn()=>$ctx);
    $samples->capture('fixture',$j['current'],1,$contextSha,$probe);
    throw new RuntimeException('fixture_did_not_pause');
});
