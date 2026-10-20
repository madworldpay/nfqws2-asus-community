<?php
require_once __DIR__.'/support-json-schema.php';
require_once __DIR__.'/dpi-options.php';
final class AsusDpiNative
{
    public const KEYS=['network_info','dns_availability','domain_inspection','tcp16','whitelist_sni','telegram','fingerprint_burst'];
    public static function group(string $raw,int $group): array
    {
        $v=AsusSupportSchema::decode($raw,1048576,'invalid_dpi');
        if(!isset(self::KEYS[$group])||!is_object($v)||($v->schema_version??null)!==1||!is_object($v->results??null)||array_keys(get_object_vars($v->results))!==[self::KEYS[$group]])throw new RuntimeException('invalid_dpi');
        $r=$v->results->{self::KEYS[$group]};
        if(in_array($group,[2,3],true)?!is_array($r):!is_object($r))throw new RuntimeException('invalid_dpi');
        return ['group'=>$group,'document'=>json_decode($raw,true,32,JSON_THROW_ON_ERROR)];
    }
    public static function document(array $job,array $groups,array $context,array $settings,array $coverage,array $messages,int $limit=1048576): string
    {
        $doc=['type'=>'nfqws2_dpi_native','schema_version'=>1,'detector_version'=>AsusDpiOptions::metadata()['version'],'origin'=>'router',
            'started_at'=>gmdate('Y-m-d\TH:i:s\Z',$job['started_at']),'finished_at'=>gmdate('Y-m-d\TH:i:s\Z',$job['finished_at']),
            'state'=>$job['state'],'selected_tests'=>$job['tests'],'settings'=>$settings,'coverage'=>$coverage,'context'=>$context,'groups'=>array_values($groups),'messages'=>$messages];
        if($job['messages_truncated']??false)$doc['messages_truncated']=true;
        $raw=json_encode($doc,JSON_THROW_ON_ERROR|JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES)."\n";
        if(strlen($raw)>min($limit,1048576))throw new RuntimeException('output_limit');return $raw;
    }
}
