<?php
require_once __DIR__.'/strategy-picker-custom-worker.php';
require_once __DIR__.'/dpi-dns-context.php';

/** Internal only. Caller holds engine.lock + the shared mutation writer.
 * Transport is the registered stdin actuator; no HTTP caller chooses code,
 * paths, dependencies or a manifest. Detailed observations are returned to
 * the future bounded report store, never accumulated in the job journal. */
final class NfqwsStrategyPickerCustomSupervisor
{
    private Closure $checkpoint;
    private Closure $transport;
    private Closure $dns;
    public function __construct(private NfqwsStrategyPickerState $store,callable $checkpoint,callable $transport,?callable $dns=null)
    {
        $this->checkpoint=Closure::fromCallable($checkpoint);
        $this->transport=Closure::fromCallable($transport);
        $this->dns=Closure::fromCallable($dns??static fn()=>AsusDpiDnsContext::collect());
    }
    private static function keys(array $value,array $expected):bool
    {$keys=array_keys($value);sort($keys);sort($expected);return $keys===$expected;}
    private static function encode(array $value):string
    {return json_encode($value,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);}
    private static function descriptor(string $stage,string $nonce,string $input,float $deadline):array
    {
        // JSON stores an integral float as an integer. Freeze that exact wire
        // representation before strict read-back and cleanup comparisons.
        return json_decode(self::encode(['stage'=>$stage,'nonce'=>$nonce,'payload_sha256'=>hash('sha256',$input),
            'deadline'=>$deadline]),true,16,JSON_THROW_ON_ERROR);
    }
    private function job(?string $id=null):array
    {
        ($this->checkpoint)();$j=$this->store->read();$now=AsusUpdateStore::uptime();
        if(!is_array($j)||!is_string($j['id']??null)||!preg_match('/^[a-f0-9]{32}$/D',$j['id'])||
            $id!==null&&$j['id']!==$id||($j['state']??null)!=='running')throw new RuntimeException('stale_state');
        $deadline=NfqwsStrategyPickerBudget::overallDeadline($j);if($deadline!==null&&$now>=$deadline)throw new RuntimeException('timed_out');
        return $j;
    }
    private function context():string
    {
        ($this->checkpoint)();$v=($this->dns)();($this->checkpoint)();
        if(!is_array($v)||!self::keys($v,['schema_version','state','sha256'])||$v['schema_version']!==1||
            $v['state']!=='known'||!is_string($v['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$v['sha256']))
            throw new RuntimeException('dns_context_unknown');
        return $v['sha256'];
    }
    private function manifest(array $j):array
    {
        $v=$j['custom_manifest']??null;$sha=$j['custom_manifest_sha256']??null;
        if(!is_array($v)||!is_string($sha)||!preg_match('/^[a-f0-9]{64}$/D',$sha)||
            hash('sha256',self::encode($v))!==$sha)throw new RuntimeException('stale_state');
        try{$v=NfqwsStrategyPickerCustomWorker::document(self::encode($v),'probe');}
        catch(Throwable $e){throw new RuntimeException('stale_state',0,$e);}
        if(($j['custom_hosts']??null)!==$v['hosts'])throw new RuntimeException('stale_state');
        return $v;
    }
    private function unchanged(string $id,string $sha):array
    {
        $j=$this->job($id);$v=$this->manifest($j);
        if($j['custom_manifest_sha256']!==$sha)throw new RuntimeException('stale_state');
        return $j;
    }
    private static function document(string $raw):stdClass
    {
        if(strlen($raw)>65536)throw new RuntimeException('incomparable_result');
        $v=AsusSupportSchema::decode($raw,65536,'incomparable_result');
        if(!$v instanceof stdClass)throw new RuntimeException('incomparable_result');return $v;
    }
    private function run(string $stage,array $input,string $id,?string $manifestSha=null):string
    {
        $j=$manifestSha===null?$this->job($id):$this->unchanged($id,$manifestSha);
        if(($j['custom_worker']??null)!==null||($j['actuator']??null)!==null)throw new RuntimeException('busy');
        $raw=self::encode($input);if(strlen($raw)>8192)throw new RuntimeException('invalid_request');
        $now=AsusUpdateStore::uptime();$deadline=NfqwsStrategyPickerBudget::overallDeadline($j);$seconds=$deadline===null?90:min(90,(int)floor($deadline-$now));
        if($seconds<1)throw new RuntimeException('timed_out');
        $nonce=bin2hex(random_bytes(16));
        $desc=self::descriptor($stage,$nonce,$raw,$now+$seconds);
        $j['custom_worker']=$desc;$this->store->write($j);
        try{
            $argv=[NfqwsPlatform::translate('/opt/bin/php-cgi'),'-d','register_argc_argv=1','-d','max_execution_time=0',
                '-d','max_input_time=0','-d','memory_limit=64M','-q','-f',__DIR__.'/strategy-picker-custom-worker.php','--',$stage,$id,$nonce];
            $r=($this->transport)($argv,$seconds,$raw,$this->checkpoint);
            $current=$this->job($id);
            if(($current['custom_worker']??null)!==$desc)throw new RuntimeException('stale_state');
            if($manifestSha!==null)$this->unchanged($id,$manifestSha);
            if(!is_array($r)||!self::keys($r,['status','output'])||!is_int($r['status'])||!is_string($r['output']))
                throw new RuntimeException('incomparable_result');
            $v=self::document($r['output']);
            if($r['status']!==0){
                $e=get_object_vars($v);
                $allowed=['invalid_request','stale_state','timed_out','cancelled','interrupted','guard_lost','custom_dns_failed',
                    'custom_dns_answer_too_large','custom_non_public_address','incomparable_result','output_limit'];
                if(self::keys($e,['error'])&&is_string($e['error'])&&in_array($e['error'],$allowed,true))throw new RuntimeException($e['error']);
                throw new RuntimeException('incomparable_result');
            }
            return $r['output'];
        }finally{
            $current=$this->store->read();
            if(($current['id']??null)===$id&&($current['custom_worker']??null)===$desc){
                unset($current['custom_worker']);$this->store->write($current);
            }
        }
    }
    public function prepare(array $hosts):array
    {
        // The request boundary normalizes URLs separately; this layer accepts
        // only the exact complete canonical target list.
        NfqwsStrategyPickerCustomWorker::prepareDocument($hosts,str_repeat('0',64));
        $j=$this->job();$id=$j['id'];
        if(($j['custom_manifest']??null)!==null)throw new RuntimeException('stale_state');
        if(isset($j['custom_hosts'])&&$j['custom_hosts']!==$hosts)throw new RuntimeException('stale_state');
        $dns=$this->context();$input=NfqwsStrategyPickerCustomWorker::prepareDocument($hosts,$dns);
        $raw=$this->run('prepare',$input,$id);
        try{$manifest=NfqwsStrategyPickerCustomWorker::document($raw,'probe');}
        catch(Throwable $e){throw new RuntimeException('incomparable_result',0,$e);}
        if(NfqwsStrategyPickerCustomWorker::scope($manifest)!==$input)throw new RuntimeException('incomparable_result');
        if($this->context()!==$dns)throw new RuntimeException('dns_context_changed');
        $current=$this->job($id);
        if(($current['custom_manifest']??null)!==null||($current['custom_worker']??null)!==null||($current['actuator']??null)!==null||
            isset($current['custom_hosts'])&&$current['custom_hosts']!==$hosts)throw new RuntimeException('stale_state');
        $current['custom_hosts']=$hosts;$current['custom_manifest']=$manifest;
        $current['custom_manifest_sha256']=hash('sha256',self::encode($manifest));$this->store->write($current);
        return $manifest;
    }
    public function probe():array
    {
        $j=$this->job();$id=$j['id'];$manifest=$this->manifest($j);$sha=$j['custom_manifest_sha256'];
        if($this->context()!==$manifest['dns_context'])throw new RuntimeException('dns_context_changed');
        $raw=$this->run('probe',$manifest,$id,$sha);$v=get_object_vars(self::document($raw));
        $keys=['schema_version','hosts','dns_context','fingerprint','observations'];
        if($manifest['schema_version']===2)$keys=array_merge($keys,['target_policy_version','targets']);
        if(!self::keys($v,$keys)||
            $v['fingerprint']!==$manifest['fingerprint']||!is_array($v['observations'])||
            !array_is_list($v['observations'])||count($v['observations'])!==count($manifest['hosts'])*2)
            throw new RuntimeException('incomparable_result');
        try{$scope=NfqwsStrategyPickerCustomWorker::scope($v);}
        catch(Throwable $e){throw new RuntimeException('incomparable_result',0,$e);}
        if($scope!==NfqwsStrategyPickerCustomWorker::scope($manifest))throw new RuntimeException('incomparable_result');
        if($manifest['schema_version']===2)$v['targets']=$scope['targets'];
        $rows=[];$i=0;
        foreach($manifest['hosts']as $host)foreach(['tls12','tls13']as $tls){
            $row=$v['observations'][$i++];
            if(!$row instanceof stdClass)throw new RuntimeException('incomparable_result');$row=get_object_vars($row);
            if(!self::keys($row,['host','tls','response'])||$row['host']!==$host||$row['tls']!==$tls||!$row['response']instanceof stdClass)
                throw new RuntimeException('incomparable_result');
            $row['response']=NfqwsStrategyPickerCustomWorker::response(get_object_vars($row['response']));$rows[]=$row;
        }
        if($this->context()!==$manifest['dns_context'])throw new RuntimeException('dns_context_changed');
        $current=$this->unchanged($id,$sha);
        if(($current['custom_worker']??null)!==null||($current['actuator']??null)!==null)throw new RuntimeException('stale_state');
        $v['observations']=$rows;$v['manifest_sha256']=$sha;return $v;
    }
}
