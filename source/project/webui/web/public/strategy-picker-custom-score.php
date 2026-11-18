<?php
require_once __DIR__.'/strategy-picker-custom-worker.php';

/** Pure, separate OpenSSL root-response score; not native Rustls/QUIC.
 * The future owned artifact writer must issue a new sample id only after a
 * real complete probe. Neither an id nor a digest alone proves execution.
 * No HTTP/custom goal calls this until joint scoring and storage are ready. */
final class NfqwsStrategyPickerCustomScore
{
    public const FINGERPRINT='custom-pinned-root-score-v1';
    public const MIXED_FINGERPRINT='custom-pinned-root-score-v2';
    private static function keys(array $v,array $keys):bool
    {$a=array_keys($v);sort($a);sort($keys);return $a===$keys;}
    private static function encode(array $v):string
    {return json_encode($v,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);}
    private static function sha(mixed $v):bool
    {return is_string($v)&&preg_match('/^[a-f0-9]{64}$/D',$v)===1;}
    private static function flags(mixed $outcome,mixed $status):array
    {
        if(!is_string($outcome)||!in_array($outcome,['response','read_limited','timeout','tls_error',
            'connection_error','unavailable','blocked_address'],true)||
            $status!==null&&(!is_int($status)||$status<200||$status>599))throw new RuntimeException('incomparable_result');
        $responded=in_array($outcome,['response','read_limited'],true);
        if($responded&&$status===null)throw new RuntimeException('incomparable_result');
        // A redirect or refusal is a response, not restored site access.
        return ['responded'=>$responded,'root_ok'=>$responded&&$status>=200&&$status<300];
    }
    private static function targets(array $v):string
    {
        $version=$v['schema_version']??null;
        if(!in_array($version,[1,2],true)||($v['fingerprint']??null)!==($version===2?self::MIXED_FINGERPRINT:self::FINGERPRINT)||
            ($v['probe_fingerprint']??null)!==NfqwsStrategyPickerCustomWorker::fingerprint($version)||
            !is_array($v['hosts']??null)||!self::sha($v['dns_context']??null)||
            !self::sha($v['context_sha256']??null)||!self::sha($v['manifest_sha256']??null))
            throw new RuntimeException('incomparable_result');
        $scope=['schema_version'=>$version,'hosts'=>$v['hosts'],'dns_context'=>$v['dns_context']];
        if($version===2)$scope+=['target_policy_version'=>$v['target_policy_version']??null,'targets'=>$v['target_identities']??null];
        $scope=NfqwsStrategyPickerCustomWorker::scope($scope);
        if($version===2)return hash('sha256',self::encode([$version,$v['fingerprint'],$v['probe_fingerprint'],
            $scope['target_policy_version'],$scope['targets'],$v['hosts'],$v['dns_context'],$v['context_sha256'],$v['manifest_sha256']]));
        return hash('sha256',self::encode([$v['fingerprint'],$v['probe_fingerprint'],$v['hosts'],
            $v['dns_context'],$v['context_sha256'],$v['manifest_sha256']]));
    }
    public static function measure(array $envelope,string $contextSha,string $sampleId):array
    {
        try{
            $raw=self::encode($envelope);
            $mixed=($envelope['schema_version']??null)===2;
            $keys=['schema_version','hosts','dns_context','fingerprint','observations','manifest_sha256'];
            if($mixed)$keys=array_merge($keys,['target_policy_version','targets']);
            if(strlen($raw)>65536||!self::keys($envelope,$keys))throw new RuntimeException('incomparable_result');
            $v=['schema_version'=>$envelope['schema_version'],'fingerprint'=>$mixed?self::MIXED_FINGERPRINT:self::FINGERPRINT,
                'probe_fingerprint'=>$envelope['fingerprint'],'hosts'=>$envelope['hosts'],
                'dns_context'=>$envelope['dns_context'],'context_sha256'=>$contextSha,
                'manifest_sha256'=>$envelope['manifest_sha256'],'sample_id'=>$sampleId,
                'sample_sha256'=>hash('sha256',$raw),'cells'=>[]];
            if($mixed)$v+=['target_policy_version'=>$envelope['target_policy_version'],'target_identities'=>$envelope['targets']];
            $v['targets']=self::targets($v);
            if(!preg_match('/^[a-f0-9]{32}$/D',$sampleId)||!is_array($envelope['observations'])||
                !array_is_list($envelope['observations'])||count($envelope['observations'])!==count($v['hosts'])*2)
                throw new RuntimeException('incomparable_result');
            $i=0;
            foreach($v['hosts']as $host)foreach(['tls12','tls13']as $tls){
                $row=$envelope['observations'][$i++];
                if(!is_array($row)||!self::keys($row,['host','tls','response'])||$row['host']!==$host||
                    $row['tls']!==$tls)throw new RuntimeException('incomparable_result');
                $response=NfqwsStrategyPickerCustomWorker::response($row['response']);
                if($response['body_limited']!==($response['outcome']==='read_limited')||
                    $response['outcome']==='response'&&$response['error_code']!==null||
                    $response['outcome']==='read_limited'&&($response['bytes_read']!==262144||$response['error_code']!=='body_limit'))
                    throw new RuntimeException('incomparable_result');
                $v['cells'][]=['host'=>$host,'tls'=>$tls,'outcome'=>$response['outcome'],
                    'http_status'=>$response['http_status']]+self::flags($response['outcome'],$response['http_status']);
            }
            return $v;
        }catch(Throwable $e){throw new RuntimeException('incomparable_result',0,$e);}
    }
    private static function compact(array $v):void
    {
        $keys=['schema_version','fingerprint','probe_fingerprint','hosts','dns_context','context_sha256',
            'manifest_sha256','sample_id','sample_sha256','cells','targets'];
        if(($v['schema_version']??null)===2)$keys=array_merge($keys,['target_policy_version','target_identities']);
        if(!self::keys($v,$keys)||
            !is_string($v['sample_id'])||!preg_match('/^[a-f0-9]{32}$/D',$v['sample_id'])||
            !self::sha($v['sample_sha256'])||$v['targets']!==self::targets($v)||
            !is_array($v['cells'])||!array_is_list($v['cells'])||count($v['cells'])!==count($v['hosts'])*2)
            throw new RuntimeException('incomparable_result');
        $i=0;
        foreach($v['hosts']as $host)foreach(['tls12','tls13']as $tls){
            $c=$v['cells'][$i++];
            if(!is_array($c)||!self::keys($c,['host','tls','outcome','http_status','responded','root_ok'])||
                $c['host']!==$host||$c['tls']!==$tls)throw new RuntimeException('incomparable_result');
            $f=self::flags($c['outcome'],$c['http_status']);
            if($c['responded']!==$f['responded']||$c['root_ok']!==$f['root_ok'])throw new RuntimeException('incomparable_result');
        }
    }
    /** One-run exploration may guide assembly, but never claims a verified
     * pair. Only compare() can establish a repeated nonregressive gain. */
    public static function minimum(array $runs):array
    {
        if(!array_is_list($runs)||!in_array(count($runs),[1,2],true))throw new RuntimeException('incomparable_result');
        $ids=[];$targets=null;
        foreach($runs as $run){
            if(!is_array($run))throw new RuntimeException('incomparable_result');self::compact($run);
            if(in_array($run['sample_id'],$ids,true)||$targets!==null&&$run['targets']!==$targets)
                throw new RuntimeException('incomparable_result');
            $ids[]=$run['sample_id'];$targets=$run['targets'];
        }
        $total=count($runs[0]['cells']);$minimum=['targets'=>$targets,'hosts'=>$runs[0]['hosts'],'repeats'=>count($runs),
            'root_ok'=>['ok'=>0,'total'=>$total],'responded'=>['ok'=>0,'total'=>$total],'cells'=>[]];
        foreach($runs[0]['cells']as $i=>$first){
            $cell=['host'=>$first['host'],'tls'=>$first['tls']];
            foreach(['responded','root_ok']as $field){
                $ok=true;foreach($runs as $run)$ok=$ok&&$run['cells'][$i][$field];
                $cell[$field]=$ok;if($ok)$minimum[$field]['ok']++;
            }
            $minimum['cells'][]=$cell;
        }
        return $minimum;
    }
    public static function compare(array $baseline,array $candidate):array
    {
        $no=static fn($reason)=>['eligible'=>false,'reason'=>$reason,'gain'=>0];
        try{
            if(!array_is_list($baseline)||!array_is_list($candidate)||count($baseline)!==2||count($candidate)!==2)
                return $no('incomparable_result');
            $all=array_merge($baseline,$candidate);$ids=[];$targets=null;
            foreach($all as $v){
                if(!is_array($v))return $no('incomparable_result');self::compact($v);
                if(in_array($v['sample_id'],$ids,true)||$targets!==null&&$v['targets']!==$targets)return $no('incomparable_result');
                $ids[]=$v['sample_id'];$targets=$v['targets'];
            }
            $total=count($baseline[0]['cells']);$gain=0;
            $min=['root_ok'=>['ok'=>0,'total'=>$total],'responded'=>['ok'=>0,'total'=>$total],'cells'=>[]];
            for($i=0;$i<$total;$i++){
                $cell=['host'=>$candidate[0]['cells'][$i]['host'],'tls'=>$candidate[0]['cells'][$i]['tls']];
                foreach(['responded','root_ok']as $field){
                    $a=$baseline[0]['cells'][$i][$field]&&$baseline[1]['cells'][$i][$field];
                    $b=$candidate[0]['cells'][$i][$field]&&$candidate[1]['cells'][$i][$field];
                    if($a&&!$b)return $no('custom_regression');
                    $cell[$field]=$b;if($b)$min[$field]['ok']++;
                    if($field==='root_ok')$gain+=(int)$b-(int)$a;
                }
                $min['cells'][]=$cell;
            }
            return ['eligible'=>$gain>0,'reason'=>$gain>0?'improved':'no_improvement','gain'=>$gain,'minimum'=>$min];
        }catch(Throwable $e){return $no('incomparable_result');}
    }
}
