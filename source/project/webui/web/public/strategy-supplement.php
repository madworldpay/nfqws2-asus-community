<?php
require_once __DIR__.'/strategy-synthesis.php';
require_once __DIR__.'/share-resources.php';
require_once __DIR__.'/share-dependencies.php';

/** Local proposal preparation only. The existing resource reader owns all file
 * access. A complete kit is not a trial result, transaction or public export. */
final class NfqwsStrategySupplement
{
    private static function encode(array $value):string
    {return json_encode($value,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);}

    private static function view(AsusShareResources $store):array
    {
        $inventory=$store->inventory();
        if(($inventory['scan_truncated']??true)!==false)throw new RuntimeException('resource_inventory_incomplete');
        $resources=[];$byId=[];
        foreach($inventory['files']as $file){
            $path='/opt/etc/nfqws2/'.$file['kind'].'/'.$file['name'];
            // Unsupported names remain in the source directory. They cannot
            // become operands in the compiler's closed resource grammar.
            if(NfqwsResourcePaths::canonical($path)!==$path||$file['state']!=='available')continue;
            $resources[$path]=$file['sha256'];$byId[$file['id']]=$file+['path'=>$path];
        }
        ksort($resources,SORT_STRING);
        return ['inventory'=>$inventory,'by_id'=>$byId,'resources'=>$resources,
            'resources_sha256'=>hash('sha256',self::encode($resources))];
    }

    /** UI may retain this digest, but prepare() obtains its own fresh view. */
    public static function inventory(AsusShareResources $store):array
    {
        $view=self::view($store);
        return ['resources'=>$view['resources'],'resources_sha256'=>$view['resources_sha256']];
    }

    public static function prepare(AsusShareResources $store,string $current,array $recipe,array $domains,array $binding):array
    {
        $view=self::view($store);
        $preview=NfqwsStrategySynthesis::supplementPreview($current,$recipe,$domains,$view['resources'],$binding);
        $audit=AsusShareDependencies::analyze(['mode'=>'config','config'=>$preview['candidate_config']],
            $preview['candidate_config'],$view['inventory'],array_keys($view['by_id']));
        if(!$audit['complete'])throw new RuntimeException('supplement_dependencies_incomplete');
        $required=[];
        foreach($audit['references']as $ref){
            $file=$view['by_id'][$ref['resource_id']??'']??null;
            if($file===null||$ref['state']!=='available')throw new RuntimeException('source_changed');
            $required[$file['path']]=$file;
        }
        ksort($required,SORT_STRING);$picks=[];
        foreach($required as $file)$picks[]=['id'=>$file['id'],'source_sha256'=>$file['sha256']];
        // No edited text, no package-only references: this private proposal
        // needs the actual bytes of every referenced list, Lua and blob.
        $copied=$store->prepare($picks);$files=[];
        foreach($copied as $file){
            $original=$view['by_id'][$file['id']];
            $raw=base64_decode($file['data_base64'],true);
            if(!is_string($raw)||strlen($raw)!==$file['byte_length']||$file['sha256']!==$original['sha256']||
                hash('sha256',$raw)!==$original['sha256'])throw new RuntimeException('source_changed');
            $files[]=['path'=>$original['path'],'id'=>$file['id'],'kind'=>$file['kind'],
                'byte_length'=>strlen($raw),'sha256'=>$file['sha256'],'data_base64'=>$file['data_base64']];
        }
        $fresh=self::view($store);
        if($fresh['resources']!==$view['resources'])throw new RuntimeException('source_changed');
        $kit=['schema_version'=>1,'complete'=>true,'files'=>$files];
        $result=['mode'=>'supplement-current-resource-proposal-v1','preview'=>$preview,'resource_kit'=>$kit,
            'resource_kit_sha256'=>hash('sha256',self::encode($kit)),
            'resource_inventory_bound'=>true,'resources_bundled'=>true,
            'config_source_proved'=>false,'can_apply'=>false,'can_export'=>false,
            'combined_verified'=>false,'actual_device_calls'=>false];
        return $result+['proposal_sha256'=>hash('sha256',self::encode($result))];
    }

    /** Keep serialization/rebinding inside the existing operand grammar.
     * A resource-looking literal must not become a transport alias merely
     * because the privacy serializer recognizes its spelling. */
    private static function portableGrammar(string $config):void
    {
        foreach(AsusShareStrategy::referenceInputs(['mode'=>'config','config'=>$config],$config)as $value){
            // supplementPreview has already accepted the closed, unquoted
            // literal grammar. These are data tokens, never shell evaluation.
            $tokens=preg_split('/\s+/',trim($value),-1,PREG_SPLIT_NO_EMPTY);
            $canonical=NfqwsResourcePaths::arguments($tokens,'asus-entware');
            $native=NfqwsResourcePaths::arguments($canonical,'openwrt');
            foreach($tokens as $i=>$token){
                if(preg_match('/\b(?:RESOURCE|BLOB|NETWORK|VARIABLE)_[1-9][0-9]*\b/',$token)||
                    preg_match('~(?:/opt)?/etc/nfqws2/~',$token)&&$canonical[$i]===$native[$i])
                    throw new RuntimeException('supplement_portable_incompatible');
            }
        }
    }

    /** Internal read-only wire preview, not an export permission or a saved
     * transaction. A future caller still needs the existing saved-config lock,
     * combined trial evidence and separate Apply/export gates. */
    public static function portablePreview(AsusShareResources $store,string $current,array $proposal):array
    {
        require_once __DIR__.'/share-contributions.php';
        require_once __DIR__.'/import-document.php';
        $fresh=self::recheck($store,$current,$proposal);$preview=$fresh['preview'];
        $candidate=$preview['candidate_config'];self::portableGrammar($candidate);
        $context=['purpose'=>'Предпросмотр дополнения текущей стратегии','operator'=>'Не указан',
            'comment'=>'Объединённая стратегия ещё не проверена повторными измерениями. Это локальное предложение, не разрешение на применение или экспорт.'];
        $picks=[];$kit=[];
        foreach($fresh['resource_kit']['files']as $file){
            $kit[$file['id']]=$file;$picks[]=['id'=>$file['id'],'source_sha256'=>$file['sha256']];
        }
        $selection=['context'=>$context,'strategy'=>['mode'=>'config','context'=>$context,'config'=>$candidate],
            'resources'=>['files'=>$picks,'missing_reason'=>''],'analysis_config_sha256'=>hash('sha256',$candidate)];
        // Versions label this data-only preview, not an observed device build.
        $documents=(new AsusShareContributions($store,new AsusShareDns()))->prepare($selection,$candidate,
            ['core'=>'unverified','web'=>'supplement-preview-v1']);
        if(!isset($documents['strategy'],$documents['resources']))throw new RuntimeException('supplement_dependencies_incomplete');
        $resources=AsusShareV4Payloads::validate('resources',$documents['resources']);$sent=[];$embedded=[];
        foreach(array_merge($resources['files'],$resources['package_files']??[])as $file){
            $original=$kit[$file['id']]??null;
            if($original===null||isset($sent[$file['id']])||$file['kind']!==$original['kind']||
                $file['sha256']!==$original['sha256']||$file['byte_length']!==$original['byte_length'])throw new RuntimeException('source_changed');
            $raw=base64_decode($original['data_base64'],true);
            if(!is_string($raw)||strlen($raw)!==$file['byte_length']||hash('sha256',$raw)!==$file['sha256']||
                isset($file['data_base64'])&&$file['data_base64']!==$original['data_base64'])throw new RuntimeException('source_changed');
            // Portable supplement kits always carry the actual bytes, including
            // stock Lua/blobs that ordinary shares may reference by package SHA.
            $file['encoding']=$file['kind']!=='blobs'&&preg_match('//u',$raw)===1&&!str_contains($raw,"\0")?'utf8':'base64';
            $file['source_sha256']=$original['sha256'];$file['data_base64']=$original['data_base64'];
            $embedded[]=$file;$sent[$file['id']]=true;
        }
        if(count($sent)!==count($kit))throw new RuntimeException('supplement_dependencies_incomplete');
        $resources['files']=$embedded;$resources['package_files']=[];
        $documents['resources']=self::encode($resources);
        AsusShareV4Payloads::validate('resources',$documents['resources']);
        $stamp=gmdate('Y-m-d_H-i-s');$files=[];
        foreach(['strategy','resources']as $kind)$files[]=AsusShareBundle::file($kind,'NFQWS2_'.strtoupper($kind).'_'.$stamp.'Z.json',$documents[$kind]);
        $id=bin2hex(random_bytes(16));$id=substr($id,0,8).'-'.substr($id,8,4).'-4'.substr($id,13,3).'-8'.substr($id,17,3).'-'.substr($id,20,12);
        $raw=json_encode(['version'=>4,'submission_id'=>$id,'files'=>$files],JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR)."\n";
        $document=AsusImportDocument::read([$raw]);
        if(($document['audit']['complete']??false)!==true||($document['package_files']??[])!==[]||count($document['resources'])!==count($kit))
            throw new RuntimeException('supplement_dependencies_incomplete');
        foreach($document['dependencies']as $dependency)if(($dependency['included']??false)!==true)throw new RuntimeException('supplement_dependencies_incomplete');
        self::recheck($store,$current,$fresh);
        return ['mode'=>'supplement-portable-preview-v1','raw'=>$raw,'sha256'=>hash('sha256',$raw),
            'base_sha256'=>$preview['base_sha256'],'resources_sha256'=>$preview['resources_sha256'],'proposal_sha256'=>$fresh['proposal_sha256'],
            'config_source_proved'=>false,'can_apply'=>false,'can_export'=>false,'combined_verified'=>false,'actual_device_calls'=>false];
    }

    /** Rebuild from fresh guarded reads; never consume caller-provided kit
     * buffers or authority flags. The caller must supply the current config
     * through its existing saved-config transaction and lock. */
    public static function recheck(AsusShareResources $store,string $current,array $proposal):array
    {
        $preview=$proposal['preview']??null;
        if(!is_array($preview)||!is_array($preview['recipe']??null)||!is_array($preview['domains']??null)||
            !is_string($preview['base_sha256']??null)||!is_string($preview['resources_sha256']??null))
            throw new RuntimeException('source_changed');
        $fresh=self::prepare($store,$current,$preview['recipe'],$preview['domains'],
            ['config_sha256'=>$preview['base_sha256'],'resources_sha256'=>$preview['resources_sha256']]);
        if($fresh!==$proposal)throw new RuntimeException('source_changed');
        return $fresh;
    }
}
