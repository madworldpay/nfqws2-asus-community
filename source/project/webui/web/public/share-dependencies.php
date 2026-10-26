<?php
require_once __DIR__.'/share-strategy.php';
require_once __DIR__.'/resource-paths.php';
/** Bounded static inspection. Nothing here opens a referenced path or runs code. */
final class AsusShareDependencies
{
    private const FILE_OPTIONS=['--hostlist','--hostlist-exclude','--hostlist-auto','--ipset','--ipset-exclude'];
    private static function tokens(string $text,array &$unresolved,string $source): array
    {
        if(strlen($text)>262144||preg_match('//u',$text)!==1||str_contains($text,'$(')||str_contains($text,'`')) {
            $unresolved[]=['source'=>$source,'kind'=>'unsupported_syntax'];return [];
        }
        $out=[];$token='';$quote='';$started=false;
        for($i=0;$i<strlen($text);$i++) {
            $c=$text[$i];
            if($quote!=="'"&&$c==='\\') {
                if(++$i>=strlen($text)){$unresolved[]=['source'=>$source,'kind'=>'unsupported_syntax'];return [];}
                if($text[$i]!=="\n")$token.=$text[$i];$started=true;continue;
            }
            if(($c==='"'||$c==="'")&&($quote===''||$quote===$c)){$quote=$quote===''?$c:'';$started=true;continue;}
            if($quote===''&&str_contains(" \t\r\n",$c)) {
                if($started){$out[]=$token;$token='';$started=false;}continue;
            }
            $token.=$c;$started=true;
        }
        if($quote!==''){$unresolved[]=['source'=>$source,'kind'=>'unsupported_syntax'];return [];}
        if($started)$out[]=$token;
        if(count($out)>8192){$unresolved[]=['source'=>$source,'kind'=>'token_limit'];return [];}
        return $out;
    }
    public static function analyze(array $selection,string $workingConfig,array $inventory,array $selected=[]): array
    {
        $inputs=AsusShareStrategy::referenceInputs($selection,$workingConfig);$references=[];$unresolved=[];$blobDefinitions=[];$blobUses=[];
        $files=[];
        foreach($inventory['files']??[] as $file)if(is_array($file)&&isset($file['kind'],$file['name'],$file['id']))$files[$file['kind'].'/'.$file['name']]=$file;
        $add=function(string $path,string $source,string $option)use(&$references,&$unresolved,$files,$selected):?string {
            $path=str_starts_with($path,'@')?substr($path,1):$path;
            if($path===''||str_contains($path,'$')){$unresolved[]=['source'=>$source,'kind'=>'unresolved_path'];return null;}
            $path=NfqwsResourcePaths::canonical($path)??$path;
            $key=$path;$id=substr(hash('sha256',$path),0,32);
            if(!isset($references[$key])&&count($references)>=128){$unresolved[]=['source'=>'analysis','kind'=>'reference_limit'];return null;}
            $name=basename($path);$state='outside';$resource=null;$bundled=false;
            if(preg_match('~^/opt/etc/nfqws2/(lists|lua|blobs)/([^/]+)$~D',$path,$m)&&$m[2]!=='.'&&$m[2]!=='..') {
                $file=$files[$m[1].'/'.$m[2]]??null;$resource=$file['id']??null;
                $state=$file===null?'missing':(($file['state']??null)==='available'?'available':'unavailable');
                $bundled=$state==='available'&&$m[1]==='lua'&&($file['bundled_lua']??false)===true;
            }
            if(!isset($references[$key]))$references[$key]=['id'=>$id,'name'=>$name,'option'=>$option,'resource_id'=>$resource,'state'=>$state,'selected'=>$bundled||($resource!==null&&in_array($resource,$selected,true)),'sources'=>[]];
            if(!in_array($source,$references[$key]['sources'],true))$references[$key]['sources'][]=$source;
            return $id;
        };
        foreach($inputs as $source=>$text) {
            $tokens=self::tokens($text,$unresolved,$source);
            for($i=0;$i<count($tokens);$i++) {
                $token=$tokens[$i];$eq=strpos($token,'=');$option=$eq===false?$token:substr($token,0,$eq);
                $recognized=in_array($option,array_merge(self::FILE_OPTIONS,['--blob','--lua-init']),true);
                if($recognized) {
                    $value=$eq===false?($tokens[++$i]??''):substr($token,$eq+1);
                    if($value===''||str_starts_with($value,'--')){$unresolved[]=['source'=>$source,'kind'=>'missing_operand'];continue;}
                    if(in_array($option,self::FILE_OPTIONS,true))$add($value,$source,$option);
                    elseif($option==='--lua-init') {
                        if(str_starts_with($value,'@'))$add($value,$source,$option);
                        else $unresolved[]=['source'=>$source,'kind'=>'inline_lua'];
                    }elseif(preg_match('/^([A-Za-z_][A-Za-z0-9_]*):(.*)$/sD',$value,$m)) {
                        if(isset($blobDefinitions[$m[1]]))$unresolved[]=['source'=>$source,'kind'=>'duplicate_blob'];
                        if(str_starts_with($m[2],'@'))$blobDefinitions[$m[1]]=$add($m[2],$source,$option)??false;
                        elseif(preg_match('/^0x[0-9a-f]+$/iD',$m[2]))$blobDefinitions[$m[1]]=true;
                        else {$blobDefinitions[$m[1]]=false;$unresolved[]=['source'=>$source,'kind'=>'unresolved_blob_definition'];}
                    }else $unresolved[]=['source'=>$source,'kind'=>'unresolved_blob_definition'];
                }
                if(str_contains($token,'$'))$unresolved[]=['source'=>$source,'kind'=>'unresolved_variable'];
                if($option==='--lua-desync') {
                    $value=$eq===false?($tokens[++$i]??''):substr($token,$eq+1);
                    if($value===''||str_starts_with($value,'--')){$unresolved[]=['source'=>$source,'kind'=>'missing_operand'];continue;}
                    if(str_contains($value,'$'))$unresolved[]=['source'=>$source,'kind'=>'unresolved_variable'];
                    preg_match_all('/(?:^|:)(?:blob|seqovl_pattern)=([^:\s]+)/',$value,$matches);
                    foreach($matches[1] as $value)if(!preg_match('/^0x[0-9a-f]+$/iD',$value))$blobUses[]=['source'=>$source,'name'=>$value];
                }
            }
        }
        foreach($blobUses as $use)if(!array_key_exists($use['name'],$blobDefinitions)&&!in_array($use['name'],AsusShareStrategy::BUILTIN_BLOBS,true))$unresolved[]=['source'=>$use['source'],'kind'=>'unbound_blob','name'=>$use['name']];
        if(($inventory['scan_truncated']??false)===true)$unresolved[]=['source'=>'inventory','kind'=>'inventory_partial'];
        $unique=[];foreach($unresolved as $row)$unique[$row['source'].'|'.$row['kind'].'|'.($row['name']??'')]=$row;$unresolved=array_values($unique);if(count($unresolved)>128)$unresolved=array_merge(array_slice($unresolved,0,127),[['source'=>'analysis','kind'=>'reference_limit']]);
        $refs=array_values($references);usort($refs,fn($a,$b)=>strcmp($a['id'],$b['id']));
        $missing=array_values(array_filter($refs,fn($r)=>!$r['selected']));
        $blobBindings=[];
        foreach($blobDefinitions as $name=>$reference)if(is_string($reference)) {
            foreach($refs as $row)if($row['id']===$reference)$blobBindings[$name]=$row['resource_id'];
        }
        return ['scope'=>'static_explicit_references','references'=>$refs,'missing'=>$missing,'unresolved'=>$unresolved,'blob_bindings'=>(object)$blobBindings,'complete'=>$missing===[]&&$unresolved===[]];
    }
}
