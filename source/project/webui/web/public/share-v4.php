<?php
require_once __DIR__.'/support-json-schema.php';
require_once __DIR__.'/share-dns.php';
/** Semantic checks in addition to the closed JSON schemas. Never runs payloads. */
final class AsusShareV4Payloads
{
    public static function validate(string $type,string $raw): array
    {
        $kind=['strategy'=>'strategy2','resources'=>'resources','dns'=>'dns_share'][$type]??null;
        if($kind===null)throw new RuntimeException('invalid_share');
        $v=AsusSupportSchema::validate($raw,$kind);
        if($type==='resources') {
            $ids=[];$aliases=[];$total=0;
            foreach($v['files'] as $file) {
                if(in_array($file['name'],['.','..'],true)||isset($ids[$file['id']]))throw new RuntimeException('invalid_resource');$ids[$file['id']]=true;
                $data=base64_decode($file['data_base64'],true);
                if(!is_string($data)||base64_encode($data)!==$file['data_base64']||strlen($data)!==$file['byte_length']||!hash_equals(hash('sha256',$data),$file['sha256']))throw new RuntimeException('invalid_resource');
                if($file['encoding']==='utf8'&&($file['kind']==='blobs'||preg_match('//u',$data)!==1||str_contains($data,"\0")))throw new RuntimeException('invalid_resource');
                $total+=strlen($data);if($total>524288)throw new RuntimeException('output_limit');
                foreach($file['aliases'] as $alias){if(isset($aliases[$alias]))throw new RuntimeException('invalid_resource');$aliases[$alias]=$file['id'];}
            }
            $refs=[];$missing=false;
            foreach($v['audit']['references'] as $row) {
                if(isset($refs[$row['id']]))throw new RuntimeException('invalid_resource');$refs[$row['id']]=true;
                if(count(array_unique($row['aliases']))!==count($row['aliases']))throw new RuntimeException('invalid_resource');
                if($row['state']==='included') {
                    if(!is_string($row['resource_id'])||!isset($ids[$row['resource_id']]))throw new RuntimeException('invalid_resource');
                    foreach($row['aliases'] as $alias)if(($aliases[$alias]??null)!==$row['resource_id'])throw new RuntimeException('invalid_resource');
                }else {if($row['resource_id']!==null)throw new RuntimeException('invalid_resource');$missing=true;}
            }
            $incomplete=$missing||$v['audit']['unresolved']!==[];
            if($v['audit']['complete']!==!$incomplete)throw new RuntimeException('invalid_resource');
            if($v['audit']['scope']==='files_only'&&($v['audit']['references']||$v['audit']['unresolved']))throw new RuntimeException('invalid_resource');
        }elseif($type==='dns') {
            $ids=[];
            foreach($v['sources'] as $source) {
                if($source['id']!==$source['origin']||isset($ids[$source['id']])||$source['complete']!==($source['warnings']===[]))throw new RuntimeException('invalid_dns_resource');$ids[$source['id']]=true;
                AsusShareDns::validateExport($source['profile']);
            }
        }else {
            if(trim($v['operator'])===''||trim($v['purpose'])==='')throw new RuntimeException('invalid_strategy');
        }
        return $v;
    }
    public static function bundle(array $documents): void
    {
        $resources=$documents['resources']??null;$strategy=$documents['strategy']??null;$aliases=[];
        foreach($resources['files']??[] as $file)foreach($file['aliases'] as $alias)$aliases[$alias]=$file['id'];
        $deps=[];
        foreach($strategy['dependencies']??[] as $dep) {
            $prefix=['file'=>'RESOURCE','blob'=>'BLOB','network'=>'NETWORK','variable'=>'VARIABLE'][$dep['kind']];
            if(isset($deps[$dep['id']])||!str_starts_with($dep['id'],$prefix.'_'))throw new RuntimeException('invalid_strategy');$deps[$dep['id']]=$dep;
            if($dep['included']!==isset($aliases[$dep['id']]))throw new RuntimeException('invalid_resource');
        }
        foreach($aliases as $id=>$_)if(!isset($deps[$id])||!in_array($deps[$id]['kind'],['file','blob'],true))throw new RuntimeException('invalid_resource');
        foreach($resources['audit']['references']??[] as $row)foreach($row['aliases'] as $id)if(!isset($deps[$id]))throw new RuntimeException('invalid_resource');
    }
}
