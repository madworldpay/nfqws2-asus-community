<?php
require_once __DIR__.'/dpi-catalog.php';
require_once __DIR__.'/support-json-schema.php';
/** Projection is built from literals/known targets; raw strings are never copied. */
final class AsusDpiNormalizer
{
    private static function number(mixed $v,bool $nullable=false,float $max=4294967295): int|float|null
    {
        if($nullable&&$v===null)return null;
        if((!is_int($v)&&!is_float($v))||!is_finite((float)$v)||$v<0||$v>$max)throw new RuntimeException('invalid_dpi');
        return $v;
    }
    private static function token(mixed $value,array $allowed): string
    {return is_string($value)&&in_array($value,$allowed,true)?$value:'unknown';}
    private static function fields(mixed $value,array $keys): void
    {
        if(!is_array($value))throw new RuntimeException('invalid_dpi');
        foreach($keys as $key)if(!array_key_exists($key,$value))throw new RuntimeException('invalid_dpi');
    }
    public static function group(string $raw,int $group,array $catalog): array
    {
        try {
            $v=AsusSupportSchema::decode($raw,524288,'invalid_dpi');
            $keys=array_column($catalog['groups'],'key');
            if(!isset($keys[$group])||!is_object($v)||($v->schema_version??null)!==1||!is_object($v->results??null)||
               array_keys(get_object_vars($v->results))!==[$keys[$group]])throw new RuntimeException();
            $r=json_decode(json_encode($v->results->{$keys[$group]},JSON_THROW_ON_ERROR),true,32,JSON_THROW_ON_ERROR);
            $out=['group'=>$group];$s=$catalog['statuses'];$d=$catalog['details'];
            switch($group) {
                case 0:
                    self::fields($r,['ipv4','ipv6','tun','bypass_tools']);
                    if(!is_array($r['tun'])||!array_is_list($r['tun'])||!is_array($r['bypass_tools'])||!array_is_list($r['bypass_tools']))throw new RuntimeException();
                    foreach(['ipv4','ipv6'] as $ip) {
                        $endpoint=$r[$ip];
                        if($endpoint!==null)self::fields($endpoint,['latency_ms']);
                        $out[$ip]=is_array($endpoint);$out[$ip.'_latency_ms']=$endpoint===null?null:self::number($endpoint['latency_ms']??null);
                    }
                    $out['tun_observed']=!empty($r['tun']);$out['bypass_observed']=!empty($r['bypass_tools']);break;
                case 1:
                    foreach(['doh_ok','doh_total','dot_ok','dot_total','udp_ok','udp_total','resolvers_total','subst_sub','subst_total','fakeip_sub'] as $key)$out[$key]=self::number($r[$key]??null);
                    $out['failures']=[];
                    if(!is_array($r['failures']??null)||count($r['failures'])>9)throw new RuntimeException();
                    foreach($r['failures'] as $row) {
                        $target=null;
                        foreach($catalog['profile']['dns'] as $known)if(($row['provider']??null)===$known['provider']&&($row['protocol']??null)===$known['protocol'])$target=$known['id'];
                        if($target===null)throw new RuntimeException();
                        $out['failures'][]=['target'=>$target,'ok'=>self::number($row['ok']??null),'total'=>self::number($row['total']??null),'status'=>self::token($row['status']??null,$s),'detail'=>self::token($row['detail']??null,$d)];
                    }break;
                case 2: case 3:
                    if(!is_array($r)||!array_is_list($r)||$r===[]||count($r)>($group===2?6:8))throw new RuntimeException();
                    $out['rows']=[];$seen=[];
                    foreach($r as $row) {
                        $target=$row[$group===2?'domain':'id']??null;$allowed=$group===2?$catalog['profile']['domains']:array_column($catalog['profile']['tcp'],'id');
                        if(!is_string($target)||!in_array($target,$allowed,true)||isset($seen[$target]))throw new RuntimeException();
                        $seen[$target]=true;$item=['target'=>$target];
                        foreach($group===2?['http','tls12','tls13','quic']:['status'] as $protocol) {
                            $detail=$group===2?$protocol.'_detail':'detail';self::fields($row,[$protocol,$detail]);$item[$protocol]=self::token($row[$protocol],$s);$item[$detail]=self::token($row[$detail],$d);
                        }
                        $out['rows'][]=$item;
                    }break;
                case 4:$out+=['detected_as'=>self::number($r['detected_as']??null),'found_as'=>self::number($r['found_as']??null)];break;
                case 5:
                    foreach(['download','upload'] as $direction) {
                        $t=$r[$direction]??null;self::fields($t,['status','avg_bps','peak_bps','bytes','drop_at_sec']);$out[$direction]=['status'=>self::token($t['status'],['ok','slow','stalled','blocked','error'])];
                        foreach(['avg_bps','peak_bps','bytes','drop_at_sec'] as $key)$out[$direction][$key]=self::number($t[$key]??null,$key==='drop_at_sec',str_ends_with($key,'bps')?1e12:4294967295);
                    }
                    $out['dc_reachable']=self::number($r['dc_reachable']??null);$out['dc_total']=self::number($r['dc_total']??null);break;
                case 6:
                    if(($r['attempts']??null)!==4||($r['gap_ms']??null)!==250||!is_array($r['domains']??null)||$r['domains']===[]||count($r['domains'])>6)throw new RuntimeException();
                    $out+=['attempts'=>4,'gap_ms'=>250,'rows'=>[]];
                    foreach($r['domains'] as $domain) {
                        if(!in_array($domain['domain']??null,$catalog['profile']['domains'],true)||!is_array($domain['profiles']??null)||count($domain['profiles'])>4)throw new RuntimeException();
                        foreach($domain['profiles'] as $fingerprint=>$row) {
                            if(!in_array($fingerprint,$catalog['fingerprints'],true)||!is_array($row['statuses']??null)||count($row['statuses'])>4)throw new RuntimeException();
                            $out['rows'][]=['target'=>$domain['domain'],'profile'=>$fingerprint,'answered'=>self::number($row['answered']??null),'attempts'=>self::number($row['attempts']??null),
                                'statuses'=>array_map(fn($x)=>self::token($x,$s),$row['statuses']),'detail'=>self::token($row['detail']??null,$d)];
                        }
                    }break;
            }
            $path=NfqwsPlatform::sharedFile('dpi-report.schema.json',dirname(__DIR__,3).'/support/dpi-report.schema.json');
            $schema=json_decode(file_get_contents($path),true,128,JSON_THROW_ON_ERROR);
            AsusSupportSchema::projection(json_decode(json_encode($out,JSON_THROW_ON_ERROR)),$schema['$defs']['group'],$schema);
            return $out;
        } catch(Throwable $e) {throw new RuntimeException('invalid_dpi');}
    }
    public static function report(array $job,array $groups,array $context): string
    {
        $c=AsusDpiCatalog::load();
        $report=['type'=>'nfqws2_dpi','schema_version'=>1,'detector_version'=>$c['version'],'profile_sha256'=>$c['profile_sha256'],'origin'=>'router',
            'started_at'=>gmdate('Y-m-d\TH:i:s\Z',$job['started_at']),'finished_at'=>gmdate('Y-m-d\TH:i:s\Z',$job['finished_at']),
            'ip_family'=>'ipv4','state'=>$job['state'],'selected_tests'=>$job['tests'],'groups'=>array_values($groups),'context'=>$context,
            'coverage'=>['limited'=>true,'dns'=>9,'domains'=>6,'tcp'=>8,'sni'=>16]];
        $raw=json_encode($report,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR)."\n";
        AsusSupportSchema::validate($raw,'dpi');return $raw;
    }
}
