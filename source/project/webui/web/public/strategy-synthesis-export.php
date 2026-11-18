<?php
require_once __DIR__.'/strategy-synthesis.php';
require_once __DIR__.'/share-contributions.php';
require_once __DIR__.'/import-document.php';

/** Export only a verified generated program and its referenced immutable kit. */
final class NfqwsStrategySynthesisExport
{
    public static function bundle(array $entry,string $source,array $seed,int $owner=0,bool $torrentSites=false,?array $job=null,?array $measuredProfile=null):array
    {
        $scope=$entry['synthesis_recipe']['custom_scope']??null;
        $mixed=isset($job['custom_target_policy']);
        if($scope!==null||$mixed){
            if(!$mixed||!is_array($scope)||($scope['manifest']??null)!==($job['custom_manifest']??null)||
                ($scope['manifest_sha256']??null)!==($job['custom_manifest_sha256']??null)||
                NfqwsStrategySynthesis::bind($entry['synthesis_recipe'],$entry['config'])!==$entry['config'])
                throw new RuntimeException('synthesis_unverified');
        }
        if($torrentSites)$entry['config']=NfqwsStrategySynthesis::torrentSites($entry['config'],$entry['synthesis_recipe']??[]);
        return self::document($entry,$source,$seed,$owner,$torrentSites,$job,$measuredProfile);
    }
    /** An unchanged measured control is a normal config export. It never
     * enters the generated-program Apply or scoped-recipe authority path. */
    public static function measuredControl(array $entry,string $source,array $seed,int $owner,array $job,array $profile):array
    {
        if(($profile['source']??null)!=='current'||isset($profile['components'])||
            isset($entry['synthesis_recipe'])||($profile['variant']??null)!==($entry['config']??null))
            throw new RuntimeException('synthesis_unverified');
        return self::document($entry,$source,$seed,$owner,false,$job,$profile);
    }
    private static function document(array $entry,string $source,array $seed,int $owner,bool $torrentSites,?array $job,?array $measuredProfile):array
    {
        $choice=$job===null?null:NfqwsStrategyPickerConcurrency::job($job);
        $scope=$entry['synthesis_recipe']['custom_scope']??null;$mixed=$scope!==null;
        $alias=$source;$source=realpath($source);if($source===false)throw new RuntimeException('storage_unavailable');
        $values=array_intersect_key($entry['config'],array_flip(array_merge(AsusImportConfig::BLOCKS,AsusImportConfig::SHARED,AsusImportConfig::PORTS)));
        $refs=[];
        foreach($values as $value)if(preg_match_all('~(?:^|[=@:])(/[^\s,:]+)~',$value,$m))foreach($m[1]as $path)$refs[$path]=true;
        $store=new AsusShareResources($source,$owner,[],NfqwsDeviceProfilesPaths::reader($source,$owner));$inventory=$store->inventory();$selected=[];$mapping=[];$found=[];
        foreach($inventory['files']as $file){
            $relative=$file['kind'].'/'.$file['name'];$path=$source.'/'.$relative;$pathAlias=$alias.'/'.$relative;
            if(!isset($refs[$path])&&!isset($refs[$pathAlias]))continue;
            if($file['state']!=='available'||!isset($entry['files'][$relative]))throw new RuntimeException('source_changed');
            $expected=$entry['files'][$relative];
            if(in_array($relative,$entry['mutable_files']??[],true)){
                $raw=isset($seed[$relative]['data'])?base64_decode($seed[$relative]['data'],true):false;
                if(!is_string($raw)||hash('sha256',$raw)!==($seed[$relative]['sha256']??null))throw new RuntimeException('source_changed');
                $expected=$seed[$relative]['sha256'];
            }
            if($file['sha256']!==$expected)throw new RuntimeException('source_changed');
            $selected[]=['id'=>$file['id'],'source_sha256'=>$expected];$mapping[$path]='/opt/etc/nfqws2/'.$relative;$mapping[$pathAlias]='/opt/etc/nfqws2/'.$relative;$found[$path]=true;$found[$pathAlias]=true;
        }
        foreach($refs as $path=>$_)if(!isset($found[$path]))throw new RuntimeException('unresolved_profile_resource');
        foreach($values as &$value)$value=strtr($value,$mapping);unset($value);$raw=AsusImportConfig::replace('',$values);
        $context=['purpose'=>'Локально собранная стратегия','operator'=>'Не указан','comment'=>'Синтез из методов '.NfqwsStrategySynthesis::VERSION.'. Результаты относятся только к проверенному подключению.'];
        if($measuredProfile!==null){
            $context['purpose']='Измеренный вариант · '.($measuredProfile['name']??'');
            $context['comment']='Выбранный измеренный вариант. Сравните его результаты с исходной стратегией перед применением.';
        }
        if(is_array($entry['synthesis_recipe']??null)){
            $credits=NfqwsStrategySynthesis::exampleAttributions($entry['synthesis_recipe']);
            if($credits)$context['comment'].="\nПримеры приёмов · ".implode(', ',$credits)."\n";
        }
        if($choice!==null)$context['comment'].=' Generator request pool: requested='.$choice['requested'].'; effective='.$choice['effective'].'; policy='.$choice['policy_version'].'.';
        if($mixed){
            $ips=[];foreach($scope['manifest']['targets']as $target)if($target['kind']==='ipv4')$ips[]=$target['host'];
            $context['comment'].=' Назначения IPv4: '.implode(', ',$ips).'. Правила HTTPS действуют на адрес целиком и могут затронуть другие сайты на нём. Ошибка TLS сама по себе не подтверждает блокировку.';
        }
        if($torrentSites)$context['comment'].=' Дополнение: четыре сайта торрент-трекеров добавлены к области HTTPS выбранного метода. Базовые результаты получены до добавления дополнения; после добавления требуется повторная проверка.';
        $selection=['context'=>$context,'strategy'=>['mode'=>'config','context'=>$context,'config'=>$raw],
            'resources'=>['files'=>$selected,'missing_reason'=>''],'analysis_config_sha256'=>hash('sha256',$raw)];
        $docs=(new AsusShareContributions($store,new AsusShareDns()))->prepare($selection,$raw,['core'=>'1.0.7','web'=>'local-synthesis-v1']);
        $files=[];foreach(['strategy','resources']as $kind)if(isset($docs[$kind]))$files[]=AsusShareBundle::file($kind,'NFQWS2_'.strtoupper($kind).'_'.gmdate('Y-m-d_H-i-s').'Z.json',$docs[$kind]);
        $uuid=bin2hex(random_bytes(16));$uuid=substr($uuid,0,8).'-'.substr($uuid,8,4).'-4'.substr($uuid,13,3).'-8'.substr($uuid,17,3).'-'.substr($uuid,20,12);
        $result=json_encode(['version'=>4,'submission_id'=>$uuid,'files'=>$files],JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR)."\n";
        $doc=AsusImportDocument::read([$result]);foreach($doc['dependencies']as $dep)if(!($dep['included']??false))throw new RuntimeException('unresolved_profile_resource');
        return ['filename'=>'NFQWS2_SYNTHESIS_'.gmdate('Y-m-d_H-i-s').'Z.json','raw'=>$result,'sha256'=>hash('sha256',$result)];
    }
}
