<?php
require_once __DIR__.'/share-resources.php';
require_once __DIR__.'/share-dependencies.php';
require_once __DIR__.'/share-dns.php';
/** Build only explicitly selected contributions. The API supplies saved config data. */
final class AsusShareContributions
{
    public function __construct(private AsusShareResources $resources,private AsusShareDns $dns) {}
    private static function keys(array $v,array $keys,array $required=[]): void
    {if(array_diff(array_keys($v),$keys)||array_diff($required,array_keys($v)))throw new RuntimeException('invalid_request');}
    public function analyze(array $selection,string $workingConfig): array
    {
        self::keys($selection,['strategy','resource_ids'],['resource_ids']);$ids=$selection['resource_ids'];
        if(!is_array($ids)||!array_is_list($ids)||count($ids)>128)throw new RuntimeException('invalid_request');
        foreach($ids as $id)if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');
        if(count(array_unique($ids))!==count($ids))throw new RuntimeException('invalid_request');
        if(isset($selection['strategy'])) {
            if(!is_array($selection['strategy']))throw new RuntimeException('invalid_request');
            $audit=AsusShareDependencies::analyze($selection['strategy'],$workingConfig,$this->resources->inventory(),$ids);
        }else $audit=['scope'=>'files_only','references'=>[],'missing'=>[],'unresolved'=>[],'blob_bindings'=>(object)[],'complete'=>true];
        return ['config_sha256'=>hash('sha256',$workingConfig),'audit'=>$audit];
    }
    private static function raw(array $v,int $limit): string
    {
        $raw=json_encode($v,JSON_PRETTY_PRINT|JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR)."\n";
        if(strlen($raw)>$limit)throw new RuntimeException('output_limit');return $raw;
    }
    public function prepare(array $selection,string $workingConfig,array $versions): array
    {
        $hasStrategy=isset($selection['strategy']);$hasFiles=isset($selection['resources']);$hasDns=isset($selection['dns']);
        if(!$hasStrategy&&!$hasFiles&&!$hasDns)return [];
        if(!is_array($selection['context']??null))throw new RuntimeException('invalid_request');$context=AsusShareStrategy::context($selection['context']);
        $chosen=[];$reason='';
        if($hasFiles) {
            if(!is_array($selection['resources']))throw new RuntimeException('invalid_request');$r=$selection['resources'];self::keys($r,['files','missing_reason'],['files','missing_reason']);
            if(!is_array($r['files'])||!is_string($r['missing_reason'])||preg_match('//u',$r['missing_reason'])!==1||preg_match_all('/./us',$r['missing_reason'])>2000)throw new RuntimeException('invalid_request');
            $chosen=$this->resources->prepare($r['files']);$reason=trim($r['missing_reason']);
        }
        $strategy=null;$bindings=[];$ids=array_column($chosen,'id');
        if($hasStrategy) {
            $s=$selection['strategy'];if(!is_array($s)||!is_array($s['context']??null)||AsusShareStrategy::context($s['context'])!==$context)throw new RuntimeException('invalid_request');
            if(!in_array($s['mode']??null,['config','blocks'],true))throw new RuntimeException('invalid_request');
            $keys=$s['mode']==='config'?['mode','context','config']:['mode','context','draft'];self::keys($s,$keys,$keys);
            if(!is_string($selection['analysis_config_sha256']??null)||!hash_equals(hash('sha256',$workingConfig),$selection['analysis_config_sha256']))throw new RuntimeException('source_changed');
            $strategy=AsusShareStrategy::extended($s,$workingConfig,$versions,$bindings);
        }
        // One inventory snapshot binds automatic dependencies to the exact hashes
        // checked by the audit; prepare() then verifies those bytes again.
        $inventory=$hasStrategy?$this->resources->inventory():null;
        $audit=$hasStrategy?AsusShareDependencies::analyze($selection['strategy'],$workingConfig,$inventory,$ids):['scope'=>'files_only','references'=>[],'missing'=>[],'unresolved'=>[],'blob_bindings'=>(object)[],'complete'=>true];
        foreach($audit['unresolved'] as $row)if($row['kind']==='global_lua_outside_selection')throw new RuntimeException('strategy_scope_incomplete');
        // A portable strategy collects its referenced Lua/blob bytes. Lists
        // remain an explicit choice: they can contain private browsing data.
        $byInventory=[];foreach($inventory['files']??[] as $file)$byInventory[$file['id']]=$file;
        $automatic=[];
        if($hasStrategy)foreach($audit['references'] as $ref) {
            $file=$byInventory[$ref['resource_id']??'']??null;
            if(in_array($ref['option'],['--lua-init','--blob'],true)&&($ref['state']!=='available'||$file===null))throw new RuntimeException('resource_unavailable');
            if($file===null||!in_array($file['kind'],['lua','blobs'],true)||in_array($file['id'],$ids,true))continue;
            if($file['state']!=='available')throw new RuntimeException('resource_unavailable');
            $automatic[]=['id'=>$file['id'],'source_sha256'=>$file['sha256']];$ids[]=$file['id'];
        }
        if($automatic)$chosen=array_merge($chosen,$this->resources->prepare($automatic));
        if(count($chosen)>AsusShareResources::COUNT_LIMIT||array_sum(array_column($chosen,'byte_length'))>AsusShareResources::TOTAL_LIMIT)throw new RuntimeException('output_limit');
        if($hasStrategy){
            $reviewed=$inventory;$sent=[];foreach($chosen as $file)$sent[$file['id']]=$file;
            foreach($reviewed['files'] as &$row)if(isset($sent[$row['id']])){
                $file=$sent[$row['id']];if($file['sha256']!==$row['sha256']||$file['byte_length']!==$row['byte_length']){unset($row['bundled_lua'],$row['bundled_resource'],$row['bundled_name']);$row['sha256']=$file['sha256'];$row['byte_length']=$file['byte_length'];}
            }unset($row);
            $audit=AsusShareDependencies::analyze($selection['strategy'],$workingConfig,$reviewed,$ids);
        }
        $packageIds=[];
        if($hasStrategy)foreach($chosen as $file) {
            $original=$byInventory[$file['id']]??null;
            if(($original['bundled_resource']??false)===true&&$file['sha256']===$original['sha256']&&$file['byte_length']===$original['byte_length'])$packageIds[$file['id']]=$original['bundled_name'];
        }
        // All aliases bind either exact embedded bytes or an explicit package
        // content reference; neither can invent a receiver filesystem path.
        $byId=[];foreach($chosen as $i=>&$file){$file['aliases']=[];$byId[$file['id']]=$i;}unset($file);
        $refAliases=[];$blobRefs=(array)$audit['blob_bindings'];
        foreach($bindings as $alias=>$binding) {
            $resourceId=null;
            if($binding['kind']==='file') {
                $path=str_starts_with($binding['value'],'@')?substr($binding['value'],1):$binding['value'];
            $path=NfqwsResourcePaths::canonical($path)??$path;
                $ref=substr(hash('sha256',$path),0,32);$refAliases[$ref][]=$alias;
                $relative=str_starts_with($path,'/opt/etc/nfqws2/')?NfqwsResourcePaths::relative(substr($path,strlen('/opt/etc/nfqws2/'))):null;
                if($relative!==null)$resourceId=substr(hash('sha256',$relative['kind']."\0".$relative['name']),0,32);
            }elseif($binding['kind']==='blob') {
                $resourceId=$blobRefs[$binding['value']]??null;
                if($resourceId!==null)foreach($audit['references'] as $ref)if($ref['resource_id']===$resourceId)$refAliases[$ref['id']][]=$alias;
            }
            if($resourceId!==null&&isset($byId[$resourceId]))$chosen[$byId[$resourceId]]['aliases'][]=$alias;
        }
        $included=[];foreach($chosen as $file)foreach($file['aliases'] as $alias)$included[$alias]=true;
        if($strategy!==null)foreach($strategy['dependencies'] as &$dep)$dep['included']=isset($included[$dep['id']]);unset($dep);
        $refs=[];
        foreach($audit['references'] as $i=>$ref) {
            $present=$ref['resource_id']!==null&&isset($byId[$ref['resource_id']]);
            $refs[]=['id'=>'dependency_'.($i+1),'aliases'=>$refAliases[$ref['id']]??[],'resource_id'=>$present?$ref['resource_id']:null,
                'state'=>$present?'included':($ref['state']==='available'?'not_selected':$ref['state'])];
        }
        $unresolved=array_map(fn($row)=>array_intersect_key($row,array_flip(['source','kind'])),$audit['unresolved']);
        $complete=$unresolved===[];
        foreach($refs as $ref)if($ref['state']!=='included')$complete=false;
        $wireAudit=['scope'=>$audit['scope'],'references'=>$refs,'unresolved'=>$unresolved,'missing_reason'=>$reason,'complete'=>$complete];
        $out=[];
        if($strategy!==null)$out['strategy']=self::raw($strategy,65536);
        if($chosen!==[]) {
            $package=[];$embedded=[];
            foreach($chosen as $file) {
                if(isset($packageIds[$file['id']])&&$file['aliases']!==[]) {
                    $package[]=['id'=>$file['id'],'kind'=>$file['kind'],'name'=>$packageIds[$file['id']],
                        'byte_length'=>$file['byte_length'],'sha256'=>$file['sha256'],'aliases'=>$file['aliases']];
                }else $embedded[]=$file;
            }
            $resources=['type'=>'nfqws2_resources','schema_version'=>$hasStrategy?2:1,'context'=>$context,'files'=>$embedded,'audit'=>$wireAudit];
            if($hasStrategy)$resources['package_files']=$package;
            $out['resources']=self::raw($resources,786432);
        }
        if($hasDns) {
            if(!is_array($selection['dns']))throw new RuntimeException('invalid_request');$dns=$this->dns->prepare($selection['dns']);
            $out['dns']=self::raw(['type'=>'nfqws2_dns','schema_version'=>1,'context'=>$context]+$dns,131072);
        }
        return $out;
    }
}
