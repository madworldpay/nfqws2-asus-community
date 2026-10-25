<?php
require_once __DIR__.'/import-document.php';
require_once __DIR__.'/share-dependencies.php';
require_once __DIR__.'/smartdns-profile.php';
/** Deterministic, read-only proposal. The transaction consumes the same bytes. */
final class AsusImportPlan
{
    private static function keys(array $v,array $keys): void
    {$a=array_keys($v);sort($a);sort($keys);if($a!==$keys)throw new RuntimeException('invalid_import_selection');}
    private static function picks(array $rows,array $allowed,array $source): array
    {
        if(!array_is_list($rows)||count($rows)>count($allowed))throw new RuntimeException('invalid_import_selection');$out=[];
        foreach($rows as $row){if(!is_array($row))throw new RuntimeException('invalid_import_selection');self::keys($row,['key','value']);$k=$row['key'];if(!is_string($k)||!in_array($k,$allowed,true)||!array_key_exists($k,$source)||isset($out[$k])||!is_string($row['value']))throw new RuntimeException('invalid_import_selection');$out[$k]=$row['value'];}
        AsusImportConfig::replace('',$out);return $out;
    }
    private static function port(string $value): void
    {
        if($value==='')return;
        foreach(explode(',',$value)as $p){if(!preg_match('/^([0-9]{1,5})(?::([0-9]{1,5}))?$/D',$p,$m)||(int)$m[1]<1||(int)$m[1]>65535||(isset($m[2])&&((int)$m[2]<(int)$m[1]||(int)$m[2]>65535)))throw new RuntimeException('invalid_import_ports');}
    }
    private static function words(string $value): array
    {
        $out=[];$word='';$quote='';$started=false;
        for($i=0;$i<strlen($value);$i++){$c=$value[$i];
            if($quote===''&&str_contains(" \t\r\n",$c)){if($started){$out[]=$word;$word='';$started=false;}continue;}
            $started=true;
            if($c==='\\'&&$quote!=="'"){if(!isset($value[++$i]))throw new RuntimeException('unsupported_import_argument');$word.=$value[$i];continue;}
            if(($c==='"'||$c==="'")&&($quote===''||$quote===$c)){$quote=$quote===''?$c:'';continue;}$word.=$c;
        }
        if($quote!=='')throw new RuntimeException('unsupported_import_argument');if($started)$out[]=$word;
        if(count($out)>8192)throw new RuntimeException('import_limit');
        // Core's pinned startup does word splitting without eval. A token that
        // still contains whitespace could not retain its intended grouping.
        foreach($out as $word)if(preg_match('/\s/u',$word))throw new RuntimeException('unsupported_import_argument');return $out;
    }
    private static function bind(string $value,array $aliases,array &$problems,?string $profile=null): string
    {
        if(preg_match('/\b(?:NETWORK|VARIABLE)_[1-9][0-9]*\b/',$value))$problems[]=['code'=>'unresolved_identity'];
        $words=self::words($value);$fileOperand=false;
        foreach($words as &$word){$at=$fileOperand||preg_match('/^--(?:lua-init|blob)=/',$word);$fileOperand=in_array($word,['--lua-init','--blob'],true);
            // Exports can retain the original @ before an anonymized path.
            // Canonicalize the file marker instead of producing @@/opt/...
            $word=preg_replace_callback('/(@?)\b(RESOURCE_[1-9][0-9]*)\b/',function($m)use($aliases,&$problems,$at){if(!isset($aliases[$m[2]])){$problems[]=['code'=>'unresolved_file','alias'=>$m[2]];return $m[0];}return ($at?'@':$m[1]).$aliases[$m[2]];},$word);
        }unset($word);return implode(' ',NfqwsResourcePaths::arguments($words,$profile));
    }
    private static function dns(array $rows,array $sources,?array $old,array &$problems,array &$warnings): ?array
    {
        if(!array_is_list($rows)||count($rows)>3)throw new RuntimeException('invalid_import_selection');if(!$rows)return null;
        $byId=[];foreach($sources as $s)$byId[$s['id']]=$s;$seen=[];$servers=[];$records=[];
        foreach($rows as $row){if(!is_array($row))throw new RuntimeException('invalid_import_selection');self::keys($row,['source_id','source_sha256','upstreams','records']);$id=$row['source_id'];
            if(!is_string($id)||!isset($byId[$id])||isset($seen[$id])||$row['source_sha256']!==$byId[$id]['sha256']||!is_array($row['upstreams'])||!array_is_list($row['upstreams'])||!is_array($row['records'])||!array_is_list($row['records']))throw new RuntimeException('invalid_import_selection');$seen[$id]=true;$source=$byId[$id];$serverIds=[];
            if(!$source['complete'])$warnings[]=['source'=>'dns-'.$id,'kind'=>'partial_dns_source'];
            foreach($row['upstreams']as $u){if(!is_array($u)||!is_string($u['id']??null)||!in_array($u['id'],array_column($source['profile']['upstreams'],'id'),true)||isset($serverIds[$u['id']]))throw new RuntimeException('invalid_import_selection');$serverIds[$u['id']]=true;$u['id']='imp'.substr(hash('sha256',$id.'|'.$u['id']),0,20);$servers[]=$u;}
            foreach($row['records']as $r){if(!is_array($r))throw new RuntimeException('invalid_import_selection');self::keys($r,['index','value']);if(!is_int($r['index'])||!isset($source['profile']['records'][$r['index']])||!is_array($r['value']))throw new RuntimeException('invalid_import_selection');$records[]=$r['value'];}
        }
        if(!$servers&&!$records){$problems[]=['code'=>'empty_dns_selection'];return null;}
        // A full export commonly contains the same active profile and draft.
        // Source-scoped IDs differ, but identical DNS entries are one choice.
        $uniqueServers=[];$serverValues=[];
        foreach($servers as $server){$value=$server;unset($value['id']);if(in_array($value,$serverValues,true))continue;$serverValues[]=$value;$uniqueServers[]=$server;}
        $uniqueRecords=[];foreach($records as $record)if(!in_array($record,$uniqueRecords,true))$uniqueRecords[]=$record;
        $servers=$uniqueServers;$records=$uniqueRecords;
        $subset=['schema_version'=>1,'upstreams'=>$servers,'records'=>$records];
        try{AsusShareDns::validateExport($subset);}
        catch(AsusSmartDnsProfileError $e){$problems[]=['code'=>'invalid_dns_profile','field'=>$e->field];return null;}
        // Records alone can extend an existing draft without inventing a DNS.
        if(!$servers&&$old!==null){$servers=$old['upstreams'];$merged=[];foreach(array_merge($old['records'],$records)as $r)$merged[$r['name'].'|'.(int)$r['include_subdomains']]=$r;$records=array_values($merged);}
        try{return AsusSmartDnsProfile::normalize(['schema_version'=>1,'upstreams'=>$servers,'records'=>$records]);}
        catch(AsusSmartDnsProfileError $e){$problems[]=['code'=>'invalid_dns_profile','field'=>$e->field];return null;}
    }
    public static function prepare(array $document,array $selection,string $currentConfig,array $inventory,?array $currentDraft,?string $profile=null): array
    {
        $profile??=NfqwsPlatform::current();NfqwsPlatform::settings($profile);
        self::keys($selection,['blocks','shared','ports','files','dns','allow_shared_impact','allow_incomplete','trusted_lua']);
        foreach(['allow_shared_impact','allow_incomplete','trusted_lua']as $key)if(!is_bool($selection[$key]))throw new RuntimeException('invalid_import_selection');
        foreach(['blocks','shared','ports','files','dns']as $key)if(!is_array($selection[$key]))throw new RuntimeException('invalid_import_selection');
        $blocks=self::picks($selection['blocks'],AsusImportConfig::BLOCKS,$document['values']);$shared=self::picks($selection['shared'],AsusImportConfig::SHARED,$document['values']);$ports=self::picks($selection['ports'],AsusImportConfig::PORTS,$document['ports']);foreach($ports as $v)self::port($v);
        $problems=[];$required=['files'=>[],'shared'=>[]];$filePicks=[];
        if(!array_is_list($selection['files'])||count($selection['files'])>128)throw new RuntimeException('invalid_import_selection');
        $available=[];foreach($document['resources']as $file)$available[$file['id']]=$file;
        foreach($selection['files']as $row){if(!is_array($row)||array_diff(array_keys($row),['id','text'])||!is_string($row['id']??null)||!isset($available[$row['id']])||isset($filePicks[$row['id']]))throw new RuntimeException('invalid_import_selection');$filePicks[$row['id']]=$row;}
        $local=[];foreach($inventory['files']??[] as $row)if(($row['state']??null)==='available')$local[$row['kind'].'/'.$row['name']]=$row;
        $aliases=[];$targets=[];$files=[];$total=0;$fingerprints=[];$virtual=$inventory['files']??[];$selectedTargets=[];
        foreach($available as $id=>$file) {
            $raw=base64_decode($file['data_base64'],true);$pick=$filePicks[$id]??null;
            if($pick!==null&&array_key_exists('text',$pick)){if($file['encoding']!=='utf8'||!is_string($pick['text'])||strlen($pick['text'])>262144||preg_match('//u',$pick['text'])!==1||str_contains($pick['text'],"\0"))throw new RuntimeException('invalid_resource');$raw=$pick['text'];}
            $hash=hash('sha256',$raw);$name=$file['name'];
            if($file['kind']==='lua')foreach($local as $candidate)if($candidate['kind']==='lua'&&($candidate['bundled_lua']??false)===true&&$candidate['sha256']===$hash){$canonical=$candidate['bundled_name']??$candidate['name'];$name=isset($local['lua/'.$canonical])&&$local['lua/'.$canonical]['sha256']===$hash?$canonical:$candidate['name'];break;}
            $key=$file['kind'].'/'.$name;
            if(!preg_match('/^[A-Za-z0-9_.-]{1,128}$/D',$name)||$name==='.'||$name==='..'){if($pick!==null)$problems[]=['code'=>'invalid_file_name','name'=>$name];continue;}
            $reuse=isset($local[$key])&&$local[$key]['sha256']===$hash;$replace=isset($local[$key])&&!$reuse;$path='/opt/etc/nfqws2/'.$key;$targets[$id]=['path'=>$path,'selected'=>$pick!==null,'reuse'=>$reuse,'sha256'=>$hash,'kind'=>$file['kind'],'name'=>$name];
            foreach($file['aliases']as $alias)$aliases[$alias]=$path;
            if($pick!==null){
                if(isset($selectedTargets[$path])&&$selectedTargets[$path]!==$hash)$problems[]=['code'=>'file_conflict','name'=>$name];
                $selectedTargets[$path]=$hash;$total+=strlen($raw);if($total>524288)throw new RuntimeException('output_limit');
                $files[]=$file+['path'=>$path,'reuse'=>$reuse,'replace'=>$replace];$n=count($files)-1;$files[$n]['sha256']=$hash;$files[$n]['byte_length']=strlen($raw);$files[$n]['data_base64']=base64_encode($raw);$files[$n]['target_name']=$name;$fingerprints[$path]=$local[$key]['sha256']??null;
                $virtual=array_values(array_filter($virtual,fn($f)=>($f['kind'].'/'.$f['name'])!==$key));
            }
            if($pick!==null||$reuse)$virtual[]=['id'=>$id,'kind'=>$file['kind'],'name'=>$name,'byte_length'=>strlen($raw),'sha256'=>$hash,'state'=>'available'];
        }
        foreach($targets as &$target)if(isset($selectedTargets[$target['path']])&&$selectedTargets[$target['path']]!==$target['sha256'])$target['reuse']=false;unset($target);
        $current=($blocks||$shared||$ports||$files)?AsusImportConfig::parse($currentConfig):[];$changes=[];
        foreach($blocks+$shared+$ports as $key=>$value)$changes[$key]=self::bind($value,$aliases,$problems,$profile);
        $hypothetical=$blocks+$shared;
        if($blocks)foreach(['NFQWS_BASE_ARGS','NFQWS_EXTRA_ARGS','NFQWS_ARGS_IPSET']as $key)if(isset($document['values'][$key])&&!isset($shared[$key])){
            $bound=self::bind($document['values'][$key],$aliases,$problems,$profile);$hypothetical[$key]=$document['values'][$key];
            if(($current[$key]??'')!==$bound){$required['shared'][]=$key;$problems[]=['code'=>'missing_shared','key'=>$key];}
        }
        foreach($hypothetical as $value)foreach($available as $id=>$file)foreach($file['aliases']as $alias)if(str_starts_with($alias,'RESOURCE_')&&preg_match('/\b'.preg_quote($alias,'/').'\b/',$value)&&(!isset($targets[$id])||(!$targets[$id]['selected']&&!$targets[$id]['reuse'])))$required['files'][]=$id;
        $required['files']=array_values(array_unique($required['files']));foreach($required['files']as $id)$problems[]=['code'=>'missing_file','id'=>$id];
        $affected=[];$sharedChanged=false;foreach($shared as $key=>$_)if(($current[$key]??'')!==$changes[$key])$sharedChanged=true;
        if($sharedChanged)foreach(AsusImportConfig::BLOCKS as $key)if(!isset($blocks[$key])&&trim($current[$key]??'')!=='')$affected[]=$key;
        foreach($files as $file)if($file['replace'])foreach(AsusImportConfig::BLOCKS as $key)if(!isset($blocks[$key])&&trim($current[$key]??'')!==''){
            $uses=implode(' ',array_map(fn($k)=>$current[$k]??'',[$key,'NFQWS_BASE_ARGS','NFQWS_EXTRA_ARGS','NFQWS_ARGS_IPSET']));
            foreach(NfqwsResourcePaths::forms($file['path'])as $path)if(preg_match('~'.preg_quote($path,'~').'(?![A-Za-z0-9_.-])~',$uses)){$affected[]=$key;break;}
        }
        $affected=array_values(array_unique($affected));
        if($affected&&!$selection['allow_shared_impact'])$problems[]=['code'=>'shared_impact'];
        $hasLua=false;foreach($files as $file)if($file['kind']==='lua')$hasLua=true;foreach($changes as $value)if(preg_match('/--lua-init(?:=|\s)/',$value))$hasLua=true;
        $trustedLua=[];foreach($local as $row)if($row['kind']==='lua'&&($row['bundled_lua']??false)===true)$trustedLua['/opt/etc/nfqws2/lua/'.$row['name']]=true;
        $luaTrustNeeded=false;foreach($files as $file)if($file['kind']==='lua'&&(!$file['reuse']||!isset($trustedLua[$file['path']])))$luaTrustNeeded=true;
        foreach($changes as $value){$words=self::words($value);for($i=0;$i<count($words);$i++){if($words[$i]==='--lua-init')$operand=$words[++$i]??'';elseif(str_starts_with($words[$i],'--lua-init='))$operand=substr($words[$i],11);else continue;$path=NfqwsResourcePaths::canonical(substr($operand,1))??substr($operand,1);if(!str_starts_with($operand,'@')||!isset($trustedLua[$path]))$luaTrustNeeded=true;}}
        if($luaTrustNeeded&&!$selection['trusted_lua'])$problems[]=['code'=>'lua_trust'];
        $newConfig=AsusImportConfig::replace($currentConfig,$changes);$warnings=[];
        if($luaTrustNeeded)$warnings[]=['source'=>'lua','kind'=>'lua_dependencies_unchecked'];
        if($blocks||$shared){$draftBlocks=[];foreach(array_merge(AsusImportConfig::BLOCKS,[])as $key)if(isset($blocks[$key]))$draftBlocks[]=['key'=>$key,'value'=>$changes[$key]];
            if(!$draftBlocks)foreach(AsusImportConfig::BLOCKS as $key)if(trim($current[$key]??'')!=='')$draftBlocks[]=['key'=>$key,'value'=>$current[$key]];
            if($draftBlocks){$auditSelection=$sharedChanged?['mode'=>'config','config'=>$newConfig]:['mode'=>'blocks','draft'=>['blocks'=>$draftBlocks]];
                $verified=array_values(array_filter($virtual,fn($f)=>($f['state']??null)==='available'&&is_string($f['sha256']??null)));
                $audit=AsusShareDependencies::analyze($auditSelection,$newConfig,['files'=>$virtual,'scan_truncated'=>$inventory['scan_truncated']??false],array_column($verified,'id'));
                foreach($audit['missing']as $row)$problems[]=['code'=>'unresolved_file','name'=>$row['name']];
                foreach($audit['references']as $ref){if($ref['state']!=='available')$problems[]=['code'=>'unresolved_file','name'=>$ref['name']];foreach($verified as $row){$path='/opt/etc/nfqws2/'.$row['kind'].'/'.$row['name'];if(substr(hash('sha256',$path),0,32)===$ref['id']&&isset($local[$row['kind'].'/'.$row['name']])&&!array_key_exists($path,$fingerprints))$fingerprints[$path]=$row['sha256'];}}
                foreach($audit['unresolved']as $row){if(in_array($row['kind'],['unbound_blob','duplicate_blob','unresolved_blob_definition'],true))$problems[]=['code'=>'unresolved_blob','detail'=>$row];else $warnings[]=$row;}
            }
        }
        $draft=self::dns($selection['dns'],$document['dns_sources'],$currentDraft,$problems,$warnings);
        if($warnings&&!$selection['allow_incomplete'])$problems[]=['code'=>'incomplete_analysis'];
        if(!$blocks&&!$shared&&!$ports&&!$files&&!$selection['dns'])$problems[]=['code'=>'empty_selection'];
        $diff=[];foreach($changes as $key=>$value)$diff[]=['key'=>$key,'before'=>$current[$key]??null,'after'=>$value];
        $out=['ready'=>$problems===[],'problems'=>$problems,'warnings'=>$warnings,'required'=>$required,'affected_blocks'=>$affected,
            'config'=>$newConfig,'changes'=>$diff,'files'=>$files,'draft'=>$draft,'old_draft'=>$currentDraft,'fingerprints'=>['config'=>hash('sha256',$currentConfig),'draft'=>$currentDraft===null?null:AsusSmartDnsProfile::hash($currentDraft),'files'=>$fingerprints],'input_sha256'=>$document['input_sha256']];
        $out['digest']=hash('sha256',json_encode($out,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR));return $out;
    }
}
