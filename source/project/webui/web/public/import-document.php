<?php
require_once __DIR__.'/share-bundle.php';
require_once __DIR__.'/share-v4.php';
require_once __DIR__.'/import-config.php';
/** Closed exported JSON only. No paths, URLs or runtime commands from input. */
final class AsusImportDocument
{
    public const LIMIT=4194304;
    public static function read(array $rawDocuments): array
    {
        if(!array_is_list($rawDocuments)||count($rawDocuments)<1||count($rawDocuments)>5)throw new RuntimeException('invalid_import');
        $total=0;$docs=[];$source=null;$ignored=[];
        $add=function(string $kind,string $raw)use(&$docs,&$ignored){
            if(isset($docs[$kind])||in_array($kind,$ignored,true))throw new RuntimeException('duplicate_import_category');
            if(in_array($kind,['report','dpi'],true)){
                $body=AsusSupportSchema::decode($raw,self::LIMIT,'invalid_import');
                AsusSupportSchema::validate($raw,$kind==='dpi'&&($body->type??null)==='nfqws2_dpi_saved'?'dpi_saved':$kind);
                $ignored[]=$kind;return;
            }
            if(!in_array($kind,['strategy','resources','dns'],true))throw new RuntimeException('invalid_import');
            $version=AsusSupportSchema::decode($raw,self::LIMIT,'invalid_import');
            $v=$kind==='strategy'&&($version->schema_version??null)===1
                ?AsusSupportSchema::validate($raw,'strategy'):AsusShareV4Payloads::validate($kind,$raw);$docs[$kind]=$v;
        };
        foreach($rawDocuments as $raw) {
            if(!is_string($raw)||strlen($raw)<1||($total+=strlen($raw))>self::LIMIT)throw new RuntimeException('import_limit');
            $value=AsusSupportSchema::decode($raw,self::LIMIT,'invalid_import');if(!is_object($value))throw new RuntimeException('invalid_import');
            if(property_exists($value,'version')) {
                if(!in_array($value->version,[3,4],true)||!is_string($value->submission_id??null))throw new RuntimeException('unsupported_import_version');
                $env=AsusShareBundle::envelope($raw,$value->submission_id);$source=$env['source']??null;unset($value);
                foreach($env['files'] as $file)$add($file['type'],base64_decode($file['data_base64'],true));
            }else {
                $type=$value->type??null;$kind=['nfqws2_strategy'=>'strategy','nfqws2_resources'=>'resources','nfqws2_dns'=>'dns','nfqws2_dpi_saved'=>'dpi','nfqws2_dpi'=>'dpi'][$type??'']??null;
                if($kind===null&&property_exists($value,'collector_version'))$kind='report';
                if($kind===null)throw new RuntimeException('unsupported_import_version');$add($kind,$raw);
            }
        }
        if(!$docs)throw new RuntimeException('no_importable_data');
        if(isset($docs['strategy'],$docs['resources']))AsusShareV4Payloads::bundle($docs);
        $s=$docs['strategy']??null;$values=[];$ports=[];
        if($s!==null) {
            if($s['mode']==='config') {
                $parsed=AsusImportConfig::parse($s['config']);foreach($parsed as $key=>$value)if(in_array($key,AsusImportConfig::PORTS,true))$ports[$key]=$value;else $values[$key]=$value;
            }else {
                foreach($s['shared']??[] as $key=>$value)$values[$key]=$value;
                foreach($s['blocks'] as $block)$values[$block['key']]=$block['value'];
                // Reuse the static literal guard for edited/exported block values.
                AsusImportConfig::replace('', $values);
            }
        }
        return ['values'=>$values,'ports'=>$ports,'resources'=>$docs['resources']['files']??[],
            'dependencies'=>$s['dependencies']??[],'audit'=>$docs['resources']['audit']??null,
            'dns_sources'=>$docs['dns']['sources']??[],'context'=>$s!==null?array_intersect_key($s,array_flip(['purpose','operator','comment','region','versions'])):($docs['resources']['context']??$docs['dns']['context']??null),
            'source'=>$source,'ignored'=>$ignored,'input_sha256'=>hash('sha256',json_encode($rawDocuments,JSON_THROW_ON_ERROR))];
    }
}
