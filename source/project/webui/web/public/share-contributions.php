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
        // Byte-identical package Lua is already supplied by the receiving IPK.
        // Retain only its canonical package path; never attach its bytes unless
        // explicitly selected. Custom/changed Lua keeps an unresolved alias.
        $native=[];$packageIds=[];
        foreach($bindings as $alias=>$binding) {
            if($binding['kind']!=='file')continue;
            $path=str_starts_with($binding['value'],'@')?substr($binding['value'],1):$binding['value'];
            if(!preg_match('~^/opt/etc/nfqws2/lua/([^/]+)$~D',$path,$m))continue;
            $resource=substr(hash('sha256',"lua\0".$m[1]),0,32);
            foreach($inventory['files'] as $file)if($file['id']===$resource&&($file['bundled_lua']??false)===true) {
                $name=$file['bundled_name']??$file['name'];
                if(!preg_match('/^[A-Za-z0-9_.-]+\.lua$/D',$name))continue;
                $native[$alias]='@/opt/etc/nfqws2/lua/'.$name;$packageIds[$resource]=true;break;
            }
        }
        if($native!==[]) {
            $rewrite=static fn($value)=>preg_replace_callback('/\bRESOURCE_[1-9][0-9]*\b/',static fn($m)=>$native[$m[0]]??$m[0],$value);
            if(isset($strategy['config']))$strategy['config']=$rewrite($strategy['config']);
            foreach($strategy['blocks']??[] as $i=>$block)$strategy['blocks'][$i]['value']=$rewrite($block['value']);
            foreach($strategy['shared']??[] as $key=>$value)$strategy['shared'][$key]=$rewrite($value);
            $strategy['dependencies']=array_values(array_filter($strategy['dependencies'],static fn($dep)=>!isset($native[$dep['id']])));
            $bindings=array_diff_key($bindings,$native);
        }
        // Selection is the only authority for attached bytes. Dependencies
        // describe completeness, but never force uploads or explanations.
        $byId=[];foreach($chosen as $i=>&$file){$file['aliases']=[];$byId[$file['id']]=$i;}unset($file);
        $refAliases=[];$blobRefs=(array)$audit['blob_bindings'];
        foreach($bindings as $alias=>$binding) {
            $resourceId=null;
            if($binding['kind']==='file') {
                $path=str_starts_with($binding['value'],'@')?substr($binding['value'],1):$binding['value'];
                $ref=substr(hash('sha256',$path),0,32);$refAliases[$ref][]=$alias;
                if(preg_match('~^/opt/etc/nfqws2/(lists|lua|blobs)/([^/]+)$~D',$path,$m))$resourceId=substr(hash('sha256',$m[1]."\0".$m[2]),0,32);
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
            if(isset($packageIds[$ref['resource_id']??'']))continue;
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
        if($chosen!==[])$out['resources']=self::raw(['type'=>'nfqws2_resources','schema_version'=>1,'context'=>$context,'files'=>$chosen,'audit'=>$wireAudit],786432);
        if($hasDns) {
            if(!is_array($selection['dns']))throw new RuntimeException('invalid_request');$dns=$this->dns->prepare($selection['dns']);
            $out['dns']=self::raw(['type'=>'nfqws2_dns','schema_version'=>1,'context'=>$context]+$dns,131072);
        }
        return $out;
    }
}
