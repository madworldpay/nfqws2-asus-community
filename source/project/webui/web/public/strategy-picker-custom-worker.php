<?php
require_once __DIR__.'/strategy-picker-runtime.php';
require_once __DIR__.'/strategy-picker-targets.php';
require_once __DIR__.'/dpi-site-check.php';
require_once __DIR__.'/support-json-schema.php';

/** Trusted leaf only. The parent owns engine.lock + writer and the hard timer.
 * No HTTP caller or environment value can choose state paths or dependencies.
 * This is not enabled by an HTTP endpoint until the complete custom goal exists. */
final class NfqwsStrategyPickerCustomWorker
{
    private NfqwsStrategyPickerState $store;
    public function __construct(?NfqwsStrategyPickerState $store=null,private array $deps=[])
    {$this->store=$store??new NfqwsStrategyPickerState(NfqwsPlatform::settings()['web_config'].'/strategy-picker');}

    /** EOF is required before any work; the registered parent bounds this read. */
    public static function readInput($stream):string
    {
        if(!is_resource($stream))throw new RuntimeException('invalid_request');
        $raw=stream_get_contents($stream,8193);
        if(!is_string($raw)||strlen($raw)>8192||!feof($stream))throw new RuntimeException('invalid_request');
        return $raw;
    }
    private static function keys(array $value,array $expected):bool
    {$keys=array_keys($value);sort($keys);sort($expected);return $keys===$expected;}
    private function authorize(string $stage,string $id,string $nonce,string $input):void
    {
        if(!in_array($stage,['prepare','probe'],true)||!preg_match('/^[a-f0-9]{32}$/D',$id)||
            !preg_match('/^[a-f0-9]{32}$/D',$nonce))throw new RuntimeException('invalid_request');
        $j=$this->store->read();$desc=$j['custom_worker']??null;$self=NfqwsStrategyPickerRuntime::identity(getmypid());
        if(($j['id']??null)!==$id||($j['state']??null)!=='running'||!is_array($desc)||
            !self::keys($desc,['stage','nonce','payload_sha256','deadline'])||
            $desc['stage']!==$stage||$desc['nonce']!==$nonce||$desc['payload_sha256']!==hash('sha256',$input)||
            $self===null||($j['actuator']??null)!==$self||
            array_slice($self['argv'],-5)!==[__FILE__,'--',$stage,$id,$nonce])throw new RuntimeException('stale_state');
        $now=AsusUpdateStore::uptime();
        $deadline=NfqwsStrategyPickerBudget::overallDeadline($j);
        if((!is_int($desc['deadline'])&&!is_float($desc['deadline']))||!is_finite((float)$desc['deadline']))throw new RuntimeException('stale_state');
        if($deadline!==null&&$desc['deadline']>$deadline||$desc['deadline']>$now+90)throw new RuntimeException('stale_state');
        if($now>=$desc['deadline']||$deadline!==null&&$now>=$deadline)throw new RuntimeException('timed_out');
        if(file_exists($this->store->path('cancel-'.$id)))throw new RuntimeException('cancelled');
        foreach(['work'=>'interrupted','guard'=>'guard_lost']as $role=>$error){
            $record=$this->store->read('actor-'.$role.'.json');$actor=$record['identity']??null;
            if(($record['id']??null)!==$id||!is_array($actor)||!NfqwsStrategyPickerRuntime::sameActor($actor)||
                $actor['pid']===getmypid()||array_slice($actor['argv'],-4)!==[__DIR__.'/strategy-picker-runtime.php','--',$role,$id])
                throw new RuntimeException($error);
        }
    }
    public static function document(string $input,string $stage):array
    {
        if(strlen($input)>8192||!in_array($stage,['prepare','probe'],true))throw new RuntimeException('invalid_request');
        $document=AsusSupportSchema::decode($input,8192,'invalid_request');
        if(!$document instanceof stdClass)throw new RuntimeException('invalid_request');
        $v=get_object_vars($document);
        $mixed=($v['schema_version']??null)===2;
        $keys=['schema_version','hosts','dns_context'];
        if($mixed)$keys=array_merge($keys,['target_policy_version','targets']);
        if($stage==='probe')$keys=array_merge($keys,['pins','policy','fingerprint']);
        if(!self::keys($v,$keys)||!in_array($v['schema_version'],[1,2],true)||!is_array($v['hosts'])||
            !array_is_list($v['hosts'])||count($v['hosts'])<1||count($v['hosts'])>10||
            !is_string($v['dns_context'])||!preg_match('/^[a-f0-9]{64}$/D',$v['dns_context']))throw new RuntimeException('invalid_request');
        foreach($v['hosts']as $host)if(!is_string($host))throw new RuntimeException('invalid_request');
        $targets=$mixed?NfqwsStrategyPickerTargets::inspectMixed(implode("\n",$v['hosts'])):
            NfqwsStrategyPickerTargets::inspect(implode("\n",$v['hosts']));
        if(!$targets['valid']||$targets['hosts']!==$v['hosts'])throw new RuntimeException('invalid_request');
        if($mixed){
            if(($targets['schema_version']??null)!==2||$v['target_policy_version']!==$targets['target_policy_version']||
                !is_array($v['targets'])||!array_is_list($v['targets'])||count($v['targets'])!==count($v['hosts']))
                throw new RuntimeException('invalid_request');
            foreach($v['targets']as $i=>$target){
                if(!$target instanceof stdClass)throw new RuntimeException('invalid_request');
                $target=get_object_vars($target);
                if(!self::keys($target,['kind','host'])||$target['kind']!==$targets['targets'][$i]['kind']||
                    $target['host']!==$targets['targets'][$i]['host'])throw new RuntimeException('invalid_request');
                $v['targets'][$i]=$target;
            }
        }
        if($stage==='probe'){
            if($v['policy']!==NfqwsIdna::POLICY||$v['fingerprint']!==self::fingerprint($v['schema_version'])||
                !is_array($v['pins'])||!array_is_list($v['pins'])||count($v['pins'])!==count($v['hosts']))throw new RuntimeException('invalid_request');
            foreach($v['pins']as $i=>$pin){
                if(!$pin instanceof stdClass)throw new RuntimeException('invalid_request');
                $pin=get_object_vars($pin);
                if(!self::keys($pin,['host','answer','address'])||$pin['host']!==$v['hosts'][$i]||
                    !is_array($pin['answer']))throw new RuntimeException('invalid_request');
                $answer=NfqwsStrategyPickerTargets::addresses($pin['answer']);
                if($answer!==$pin['answer']||$pin['address']!==$answer[0]||
                    $mixed&&$v['targets'][$i]['kind']==='ipv4'&&$answer!==[$pin['host']])throw new RuntimeException('invalid_request');
                $v['pins'][$i]=$pin;
            }
        }
        return $v;
    }
    public static function fingerprint(int $version):string
    {return match($version){1=>AsusDpiSiteCheckProbe::PINNED_FINGERPRINT,2=>AsusDpiSiteCheckProbe::MIXED_PINNED_FINGERPRINT,
        default=>throw new RuntimeException('invalid_request')};}
    /** Internal canonical identity builder. It never resolves and does not
     * change the separate public Request::custom input boundary. */
    public static function prepareDocument(array $hosts,string $dns):array
    {
        foreach($hosts as $host)if(!is_string($host))throw new RuntimeException('invalid_request');
        $parsed=NfqwsStrategyPickerTargets::inspectMixed(implode("\n",$hosts));
        if(!$parsed['valid']||$parsed['hosts']!==$hosts)throw new RuntimeException('invalid_request');
        $v=['schema_version'=>$parsed['schema_version']??1,'hosts'=>$hosts,'dns_context'=>$dns];
        if($v['schema_version']===2)$v+=['target_policy_version'=>$parsed['target_policy_version'],'targets'=>$parsed['targets']];
        return self::scope($v);
    }
    public static function scope(array $v):array
    {
        $scope=[];foreach(['schema_version','hosts','dns_context']as $key){
            if(!array_key_exists($key,$v))throw new RuntimeException('invalid_request');$scope[$key]=$v[$key];
        }
        if($scope['schema_version']===2)foreach(['target_policy_version','targets']as $key){
            if(!array_key_exists($key,$v))throw new RuntimeException('invalid_request');$scope[$key]=$v[$key];
        }
        return self::document(json_encode($scope,JSON_THROW_ON_ERROR),'prepare');
    }
    public static function response(mixed $v):array
    {
        if(!is_array($v)||!self::keys($v,['outcome','http_status','bytes_read','body_limited','redirect','elapsed_ms','error_code'])||
            !in_array($v['outcome'],['response','read_limited','timeout','tls_error','connection_error','unavailable','blocked_address'],true)||
            !is_int($v['bytes_read'])||$v['bytes_read']<0||$v['bytes_read']>262144||!is_bool($v['body_limited'])||
            $v['http_status']!==null&&(!is_int($v['http_status'])||$v['http_status']<200||$v['http_status']>599)||
            $v['outcome']==='response'&&$v['http_status']===null||
            $v['redirect']!==null&&(!is_string($v['redirect'])||strlen($v['redirect'])>2048||preg_match('/[^\x20-\x7e]/',$v['redirect']))||
            $v['elapsed_ms']!==null&&(!is_int($v['elapsed_ms'])||$v['elapsed_ms']<0||$v['elapsed_ms']>90000)||
            $v['error_code']!==null&&(!is_string($v['error_code'])||!preg_match('/^[a-z0-9_]{1,64}$/D',$v['error_code'])))
            throw new RuntimeException('incomparable_result');
        return $v;
    }
    public function execute(string $stage,string $id,string $nonce,string $input):array
    {
        $this->authorize($stage,$id,$nonce,$input);$v=self::document($input,$stage);
        if($stage==='prepare'){
            $pins=[];
            foreach($v['hosts']as $i=>$host){
                $this->authorize($stage,$id,$nonce,$input);
                $literal=$v['schema_version']===2&&$v['targets'][$i]['kind']==='ipv4';
                $answer=$literal?[$host]:(isset($this->deps['resolve'])?($this->deps['resolve'])($host):gethostbynamel($host));
                $this->authorize($stage,$id,$nonce,$input);
                if(!is_array($answer))throw new RuntimeException('custom_dns_failed');
                $answer=NfqwsStrategyPickerTargets::addresses($answer);
                $pins[]=['host'=>$host,'answer'=>$answer,'address'=>$answer[0]];
            }
            $result=$v+['pins'=>$pins,'policy'=>NfqwsIdna::POLICY,'fingerprint'=>self::fingerprint($v['schema_version'])];
        }else{
            $rows=[];$probe=new AsusDpiSiteCheckProbe();
            foreach($v['pins']as $i=>$pin)foreach(['tls12','tls13']as $tls){
                $this->authorize($stage,$id,$nonce,$input);
                $response=isset($this->deps['probe'])?($this->deps['probe'])($pin['host'],$pin['answer'],$tls,8):
                    ($v['schema_version']===2?$probe->pinnedTarget($v['targets'][$i],$pin['answer'],$tls,8):
                        $probe->pinned($pin['host'],$pin['answer'],$tls,8));
                $this->authorize($stage,$id,$nonce,$input);
                $rows[]=['host'=>$pin['host'],'tls'=>$tls,'response'=>self::response($response)];
            }
            $result=['schema_version'=>$v['schema_version'],'hosts'=>$v['hosts'],'dns_context'=>$v['dns_context'],
                'fingerprint'=>self::fingerprint($v['schema_version']),'observations'=>$rows];
            if($v['schema_version']===2)$result+=['target_policy_version'=>$v['target_policy_version'],'targets'=>$v['targets']];
        }
        if(strlen(json_encode($result,JSON_THROW_ON_ERROR))>65536)throw new RuntimeException('output_limit');
        return $result;
    }
}

if(realpath($_SERVER['SCRIPT_FILENAME']??($argv[0]??''))===__FILE__){
    if(isset($_SERVER['REQUEST_METHOD'])||isset($_SERVER['REMOTE_ADDR'])||!in_array(PHP_SAPI,['cli','cgi-fcgi'],true))exit(1);
    $args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);
    if(count($args)!==3||!in_array($args[0],['prepare','probe'],true)||
        !preg_match('/^[a-f0-9]{32}$/D',$args[1])||!preg_match('/^[a-f0-9]{32}$/D',$args[2]))exit(2);
    $stream=null;
    try{
        $stream=fopen('php://stdin','rb');$input=NfqwsStrategyPickerCustomWorker::readInput($stream);
        $result=(new NfqwsStrategyPickerCustomWorker())->execute($args[0],$args[1],$args[2],$input);
        echo json_encode($result,JSON_THROW_ON_ERROR);
    }catch(Throwable $e){
        $code=$e->getMessage();
        if(!in_array($code,['invalid_request','stale_state','timed_out','cancelled','interrupted','guard_lost','custom_dns_failed',
            'custom_dns_answer_too_large','custom_non_public_address','incomparable_result','output_limit'],true))$code='interrupted';
        echo json_encode(['error'=>$code],JSON_THROW_ON_ERROR);exit(2);
    }finally{if(is_resource($stream))fclose($stream);}
}
