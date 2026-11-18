<?php
require_once __DIR__.'/share-strategy.php';
require_once __DIR__.'/resource-paths.php';
/** Bounded static inspection. Nothing here opens a referenced path or runs code. */
final class AsusShareDependencies
{
    private const FILE_OPTIONS=['--hostlist','--hostlist-exclude','--hostlist-auto','--ipset','--ipset-exclude'];
    // Reviewed zapret2 1.0.7 implementations. Names alone do not establish Lua
    // semantics: a custom initializer can replace a global function.
    private const CLONE_LUA=[
        'zapret-lib.lua'=>'6bf528fef1f0fc3c65e189216fc8a06bb873f6e25d1c29d2bfa4695a09b73440',
        'zapret-antidpi.lua'=>'6d1fa9168e5de1682fef91fd174f68b58c50f6739ef00f42ca7db2b940b6246d',
    ];
    private const NON_OVERRIDING_LUA=[
        '23a9b99a776d868d92f4cc0ee5110f5c1f12fe746620d9c0337022dbc2f52df0', // zapret-auto
        '75d91452eae06c672aecebe87d753fa968f939d95452a6103292aed658c533f3', // zapret-obfs
        '6866c37c92fbc62075accf94228da48af618c7f416edc682eba99b2196e05f45', // zapret-pcap
        'a9c1b833a662e73dafffc26baed4f99e113acf45b82d664b89ac9eb2c10bd8ea', // guarded-ts
        'e77f9d5514469bec59d3ee74d90a83514c2408a4a410d7be7f3e1d42a0900791', // tls13-stun
        '3f1f9a59c61681ccff6d7d4ddd239488c1d0ab8f6f1d1fb95eefddf8646afba1', // older tls13-stun
        '99777bc1fd382e807c6e626d97b7421600ebf8b83a7d34d17e0f1047c117f2d0', // tmdb selector
    ];
    // desync.c/lua.c and the six Lua modules at zapret2 1.0.7
    // (038c97e5819df10f8e8c22a2f1fffe57f2f7379b), including plan/ip_id.
    private const DESYNC_FIELDS=['arg','cookie','decrypt_data','dis','func','func_instance','func_n','fwmark','ifin','ifout','ip_id','l7payload','l7proto','outgoing','plan','profile_n','profile_name','reasm_data','reasm_offset','replay','replay_piece','replay_piece_count','replay_piece_last','target','tcp_mss','track'];
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
    /** Model only the simple, ordered TCP clone/fake chain. This checks input
     * dependencies, not network success. Unknown execution remains unresolved. */
    private static function luaBlobUses(array $sources,array $files,array $initializers): array
    {
        $loaded=[];$safe=true;
        foreach($initializers as $tokens)for($i=0;$i<count($tokens);$i++){
            $token=$tokens[$i];$eq=strpos($token,'=');$option=$eq===false?$token:substr($token,0,$eq);
            if($option!=='--lua-init')continue;
            $value=$eq===false?($tokens[++$i]??''):substr($token,$eq+1);
            $path=str_starts_with($value,'@')?NfqwsResourcePaths::canonical(substr($value,1)):null;
            $relative=$path===null?null:NfqwsResourcePaths::relative(substr($path,strlen('/opt/etc/nfqws2/')));
            $file=($relative['kind']??null)==='lua'?($files['lua/'.$relative['name']]??null):null;
            $hash=$file['sha256']??null;$stock=$file['bundled_name']??$file['name']??null;
            if(($file['state']??null)==='available'&&($file['bundled_lua']??false)===true&&
                isset(self::CLONE_LUA[$stock])&&self::CLONE_LUA[$stock]===$hash)$loaded[$stock]=true;
            elseif(($file['state']??null)!=='available'||!in_array($hash,self::NON_OVERRIDING_LUA,true))$safe=false;
        }
        $supported=$safe&&count($loaded)===count(self::CLONE_LUA);$uses=[];
        foreach($sources as $source=>$tokens){
            $profile=0;$udpProfiles=[];
            foreach($tokens as $token){
                if($token==='--new'||str_starts_with($token,'--new='))$profile++;
                elseif(preg_match('/^--(?:filter-udp|filter-icmp|import)(?:=|$)/D',$token))$udpProfiles[$profile]=true;
            }
            $profile=0;$produced=[];$tcp=false;$barrier=false;
            for($i=0;$i<count($tokens);$i++){
                $token=$tokens[$i];$eq=strpos($token,'=');$option=$eq===false?$token:substr($token,0,$eq);
                if($option==='--new'){$profile++;$produced=[];$tcp=false;$barrier=false;continue;}
                if(!in_array($option,['--filter-tcp','--filter-udp','--payload','--in-range','--out-range','--lua-desync'],true))continue;
                $value=$eq===false?($tokens[++$i]??''):substr($token,$eq+1);
                if($option==='--filter-tcp'){$tcp=$value!=='';continue;}
                if($option==='--filter-udp'){$produced=[];continue;}
                if($option!=='--lua-desync'){$produced=[];continue;}
                $parts=explode(':',$value);$function=array_shift($parts);$args=[];$duplicate=false;
                foreach($parts as $part){$pair=explode('=',$part,2);if(isset($args[$pair[0]]))$duplicate=true;$args[$pair[0]]=$pair[1]??true;}
                $gated=array_intersect(array_keys($args),['strategy','iff','dir','direction','instances'])!==[];
                $use=function($name)use(&$uses,$source,$produced,$gated){
                    if(is_string($name)&&!preg_match('/^0x[0-9a-f]+$/iD',$name))$uses[]=['source'=>$source,'name'=>$name,'local'=>!$gated&&isset($produced[$name])];
                };
                if($function==='tls_client_hello_clone'){
                    if(isset($args['fallback']))$use($args['fallback']);
                    $output=$args['blob']??null;
                    if($supported&&$tcp&&!isset($udpProfiles[$profile])&&!$barrier&&!$duplicate&&is_string($output)&&preg_match('/^[A-Za-z_][A-Za-z0-9_]*$/D',$output)&&
                        !in_array($output,self::DESYNC_FIELDS,true)&&is_string($args['fallback']??null)&&array_diff(array_keys($args),['blob','fallback'])===[]){$produced[$output]=true;continue;}
                    $use($output);$produced=[];$barrier=true;continue;
                }
                foreach(['blob','seqovl_pattern']as $key)if(isset($args[$key]))$use($args[$key]);
                if($function!=='fake'||$gated){$produced=[];$barrier=true;}
            }
        }
        return $uses;
    }
    /** Pure initializer-byte eligibility for a synthesis preview. The caller
     * must separately bind these SHA facts to the actual resource snapshot. */
    public static function synthesisInitializers(array $paths,array $resources):bool
    {
        if(!array_is_list($paths)||count($paths)!==count(self::CLONE_LUA))return false;
        $expected=array_values(self::CLONE_LUA);
        foreach($paths as $i=>$path){
            if(!is_string($path)||($canonical=NfqwsResourcePaths::canonical($path))===null||
                ($resources[$canonical]??null)!==$expected[$i])return false;
        }
        return true;
    }

    public static function analyze(array $selection,string $workingConfig,array $inventory,array $selected=[]): array
    {
        $inputs=AsusShareStrategy::referenceInputs($selection,$workingConfig);$references=[];$unresolved=[];$blobDefinitions=[];$sourceTokens=[];
        $files=[];
        foreach($inventory['files']??[] as $file)if(is_array($file)&&isset($file['kind'],$file['name'],$file['id']))$files[$file['kind'].'/'.$file['name']]=$file;
        $add=function(string $path,string $source,string $option)use(&$references,&$unresolved,$files,$selected):?string {
            $path=str_starts_with($path,'@')?substr($path,1):$path;
            if($path===''||str_contains($path,'$')){$unresolved[]=['source'=>$source,'kind'=>'unresolved_path'];return null;}
            $path=NfqwsResourcePaths::canonical($path)??$path;
            $key=$path;$id=substr(hash('sha256',$path),0,32);
            if(!isset($references[$key])&&count($references)>=128){$unresolved[]=['source'=>'analysis','kind'=>'reference_limit'];return null;}
            $name=basename($path);$state='outside';$resource=null;$bundled=false;
            $relative=str_starts_with($path,'/opt/etc/nfqws2/')?NfqwsResourcePaths::relative(substr($path,strlen('/opt/etc/nfqws2/'))):null;
            if($relative!==null) {
                $file=$files[$relative['kind'].'/'.$relative['name']]??null;$resource=$file['id']??null;
                $state=$file===null?'missing':(($file['state']??null)==='available'?'available':'unavailable');
                $bundled=$state==='available'&&$relative['kind']==='lua'&&($file['bundled_lua']??false)===true;
            }
            if(!isset($references[$key]))$references[$key]=['id'=>$id,'name'=>$name,'option'=>$option,'resource_id'=>$resource,'state'=>$state,'selected'=>$bundled||($resource!==null&&in_array($resource,$selected,true)),'sources'=>[]];
            if(!in_array($source,$references[$key]['sources'],true))$references[$key]['sources'][]=$source;
            return $id;
        };
        foreach($inputs as $source=>$text) {
            $tokens=self::tokens($text,$unresolved,$source);$sourceTokens[$source]=$tokens;
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
                }
            }
        }
        $initializers=$sourceTokens;
        if(($selection['mode']??null)==='blocks'){
            // --lua-init is global even when written in an unselected profile.
            $effective=AsusShareStrategy::referenceInputs(['mode'=>'config','config'=>$workingConfig],$workingConfig);
            foreach($effective as $source=>$text)if(!isset($initializers[$source])){
                $ignored=[];$initializers[$source]=self::tokens($text,$ignored,$source);
                if($ignored!==[])$initializers[$source][]='--lua-init=unknown';
                // Lua initializers are global and ordered. A block-only export
                // cannot silently move an initializer out of an omitted block.
                foreach($initializers[$source] as $token)if(preg_match('/^--lua-init(?:=|$)/D',$token)){
                    $unresolved[]=['source'=>$source,'kind'=>'global_lua_outside_selection'];break;
                }
            }
        }
        foreach(self::luaBlobUses($sourceTokens,$files,$initializers)as $use)if(!$use['local']&&!array_key_exists($use['name'],$blobDefinitions)&&!in_array($use['name'],AsusShareStrategy::BUILTIN_BLOBS,true))$unresolved[]=['source'=>$use['source'],'kind'=>'unbound_blob','name'=>$use['name']];
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
