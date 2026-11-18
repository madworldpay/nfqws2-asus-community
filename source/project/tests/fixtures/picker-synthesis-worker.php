<?php
umask(0077);[$web,$root,$id]=array_slice($argv,1,3);require $web.'/strategy-picker-custom-supervisor.php';
final class SynthesisFixtureRuntime
{
    use NfqwsStrategySynthesisRuntime;
    use NfqwsStrategyPickerCustomRuntime;
    public function __construct(private NfqwsStrategyPickerState $store,private NfqwsStrategyPickerConfig $config,
        private NfqwsStrategyPickerRuntime $runtime,private string $web){}
    private function delegate(string $name,...$args):mixed{return(new ReflectionMethod($this->runtime,$name))->invoke($this->runtime,...$args);}
    private function checkpoint():void{$this->delegate('checkpoint');}
    private function assertOriginal():void{$this->delegate('assertOriginal');}
    private function resourcesFingerprint():string{return $this->delegate('resourcesFingerprint');}
    // Detector/service are doubles in this fixture; source and recovery are real.
    private function preflight():void{$this->assertOriginal();}
    private function budget():array{return $this->delegate('budget');}
    private function phase(string $name,array $values=[]):void{
        $this->delegate('phase',$name,$values);
        if($name==='switching'&&is_file('/tmp/fixture-from-scratch')){
            $path='/tmp/fixture-native-trials.json';$rows=is_file($path)?json_decode(file_get_contents($path),true):[];$j=$this->store->read();
            $rows[]=['round'=>$j['series']['current']??1,'name'=>$values['current_name'],'basis'=>$values['active_recipe']['basis']??'empty','phases'=>[]];file_put_contents($path,json_encode($rows));
        }
    }
    private function service(string $action):void{$this->delegate('service',$action);}
    private function candidate(array $entry):string{return $this->delegate('candidate',$entry);}
    private function resetAuto(array $entry):void{$this->delegate('resetAuto',$entry);}
    private function library():NfqwsDeviceProfilesLibrary{return $this->delegate('library');}
    private function restore():void{$this->delegate('restore');}
    private function skip(string $id,Throwable $e):void{$this->delegate('skip',$id,$e);}
    private function customContext():array{return ['nfqws'=>is_file('/tmp/fixture-service-on')?'running':'stopped',
        'ark'=>'absent','tun_observed'=>false,'dns'=>['schema_version'=>1,'state'=>'known','sha256'=>str_repeat('c',64)]];}
    private function customSupervisor():NfqwsStrategyPickerCustomSupervisor
    {
        $transport=function($args,$seconds,$input,$check){
            $actual=['/usr/bin/php8-cgi','-n','-d','register_argc_argv=1','-d','max_execution_time=0',
                '-d','max_input_time=0','-d','memory_limit=64M','-q','-f','/fixtures/leaf.php','--',$this->web,$this->store->root,...array_slice($args,-5)];
            return $this->delegate('actuator',$actual,$seconds,$input,$check);
        };
        return new NfqwsStrategyPickerCustomSupervisor($this->store,fn()=>$this->customCheckpoint(),$transport,
            static fn()=>['schema_version'=>1,'state'=>'known','sha256'=>str_repeat('c',64)]);
    }
    private function probe(array $groups):array
    {
        if($this->synthesisCustom($this->store->read()))$this->customCheckpoint();else $this->checkpoint();
        if($groups!==[2,3]||!is_file('/tmp/fixture-service-on'))throw new RuntimeException('fixture_native_context');
        $corrupt=is_file('/tmp/fixture-corrupt-pool')?'/tmp/fixture-corrupt-pool':
            (($this->store->read()['series']['current']??1)===2&&is_file('/tmp/fixture-corrupt-pool-round2')?'/tmp/fixture-corrupt-pool-round2':null);
        if($corrupt!==null){
            unlink($corrupt);$j=$this->store->read();$j['budget']['concurrency']++;
            $this->store->write($j);$this->checkpoint();throw new RuntimeException('fixture_corrupt_pool_accepted');
        }
        $values=AsusImportConfig::parse($this->config->raw());
        if(!preg_match('/(?:^|\s)--hostlist-auto=(\S+)/',$values['NFQWS_EXTRA_ARGS']??'',$m))throw new RuntimeException('fixture_auto_missing');
        $path=NfqwsDeviceProfilesPaths::readPath($m[1]);
        if(!str_starts_with($path,NfqwsPlatform::settings()['config'].'/strategy-picker/'.$this->store->read()['id'].'/'))throw new RuntimeException('fixture_original_auto_write_refused');
        file_put_contents($path,"learned.example.org\n",FILE_APPEND);
        $ctx=$this->customContext();
        $planned=$this->store->read()['probe_domains']??[];
        if(!$planned||count(array_unique($planned))!==count($planned))throw new RuntimeException('fixture_stock_domains');
        $domains=[];foreach($planned as $host)
            $domains[]=['domain'=>NfqwsStrategySynthesis::host($host),'http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'quic_server_hello'];
        $tcp=[];for($i=1;$i<=110;$i++)$tcp[]=['id'=>'fixture-control-'.$i,'ip'=>'8.8.8.8','port'=>443,'sni'=>'cdn-'.$i.'.example.net','status'=>'ok'];
        if(is_file('/tmp/fixture-comparison')){
            $job=$this->store->read();$recipe=$job['active_recipe']??null;
            $strongOriginal=file_get_contents('/tmp/fixture-comparison')==='strong-original';
            $hasTls=($recipe['tls']['method']??'pass')!=='pass';
            foreach($recipe['overrides']??[] as $rule)
                if($rule['protocol']==='tls'&&$rule['component']['method']!=='pass')$hasTls=true;
            // Synthetic observations only. In one experiment the original is
            // always better. In the other, only round one improves on it.
            foreach($domains as $i=>&$row){
                if($strongOriginal)$fails=$recipe!==null;
                elseif($recipe===null)$fails=$i===1;
                else $fails=!$hasTls||(($job['series']['current']??1)>1&&$i===1);
                if($fails)$row['tls13']='error';
            }unset($row);
        }
        if(is_file('/tmp/fixture-from-scratch')){
            $j=$this->store->read();$recipe=$j['active_recipe']??[];$on=['http'=>false,'tls'=>false,'quic'=>false];
            foreach($on as $protocol=>$_)$on[$protocol]=($recipe[$protocol]['method']??'pass')!=='pass';
            foreach($recipe['overrides']??[]as $rule)if(($rule['component']['method']??'pass')!=='pass')$on[$rule['protocol']]=true;
            foreach($domains as &$row){$row['http']=$on['http']?'ok':'error';$row['tls12']=$on['tls']?'ok':'error';$row['tls13']=$on['tls']?'ok':'error';$row['quic']=$on['quic']?'quic_server_hello':'error';}unset($row);
            foreach($tcp as &$row)$row['status']=$on['tls']?'ok':'timeout';unset($row);
            $path='/tmp/fixture-native-trials.json';$rows=json_decode(file_get_contents($path),true);$rows[count($rows)-1]['phases'][]=$j['phase'];file_put_contents($path,json_encode($rows));
        }
        $native=['state'=>'completed','context'=>['before'=>$ctx,'after'=>$ctx,'changed'=>false],
            'coverage'=>['domains'=>count($domains),'tcp'=>count($tcp)],'groups'=>[
                ['group'=>2,'document'=>['results'=>['domain_inspection'=>$domains]]],
                ['group'=>3,'document'=>['results'=>['tcp16'=>$tcp]]]]];
        $j=$this->store->read();
        if(isset($j['concurrency_choice']))$native['settings']=['config'=>['MAX_CONCURRENT'=>$j['budget']['concurrency']]];
        NfqwsStrategyPickerConcurrency::verifyNative($j,$native);return $native;
    }
    public function run():void{$this->synthesisWork();}
}
$s=new NfqwsStrategyPickerState($root);$config=new NfqwsStrategyPickerConfig($s,NfqwsPlatform::settings()['config'].'/nfqws2.conf');
$runtime=new NfqwsStrategyPickerRuntime($s,$config);$lock=$s->lock();$lease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
try{
    $s->write(['id'=>$id,'identity'=>NfqwsStrategyPickerRuntime::identity(getmypid())],'actor-work.json');
    for($i=0;$i<100;$i++){$g=$s->read('actor-guard.json');if(($g['id']??null)===$id&&NfqwsStrategyPickerRuntime::sameActor($g['identity']??null))break;usleep(100000);}
    (new AsusImportTransaction())->writer(function()use($s,$config,$runtime,$web){(new SynthesisFixtureRuntime($s,$config,$runtime,$web))->run();});
    echo json_encode(['completed'=>true,'peak'=>memory_get_peak_usage(true),'heap'=>ini_get('memory_limit')])."\n";
}catch(Throwable $e){
    (new ReflectionMethod($runtime,'fail'))->invoke($runtime,NfqwsStrategyPickerRuntime::error($e));
    echo json_encode(['error'=>$e->getMessage(),'origin'=>[basename($e->getFile()),$e->getLine()]])."\n";
}finally{foreach([$lease,$lock]as $f){flock($f,LOCK_UN);fclose($f);}}
