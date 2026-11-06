<?php
require_once __DIR__.'/import-addon-catalog.php';
require_once __DIR__.'/import-keenetic.php';
require_once __DIR__.'/import-torrent-sites.php';
final class AsusImportAddonScopeError extends RuntimeException
{
    public function __construct(public readonly string $remedy){parent::__construct('addon_scope_incompatible');}
}
/** Data-only unions. The selected base continues to own algorithms and filters. */
final class AsusImportAddons
{
    public static function requested(array $selection): array
    {
        if(!array_key_exists('addons',$selection))return [];$rows=$selection['addons'];
        if(!is_array($rows)||!array_is_list($rows)||count($rows)>8)throw new RuntimeException('invalid_import_selection');$seen=[];
        foreach($rows as $row){if(!is_array($row))throw new RuntimeException('invalid_import_selection');$keys=array_keys($row);sort($keys);
            if($keys!==['id','sha256']||!is_string($row['id'])||!preg_match('/^[a-z0-9][a-z0-9-]{0,63}$/D',$row['id'])||!is_string($row['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$row['sha256'])||isset($seen[$row['id']]))throw new RuntimeException('invalid_import_selection');$seen[$row['id']]=true;
        }return $rows;
    }
    /** Distinguish empty/comment-only lists from genuinely scoped includes. */
    private static function listData(string $path,array $virtual,array $files,?callable $readList): ?string
    {
        $path=NfqwsResourcePaths::canonical($path)??$path;
        if(!preg_match('~^/opt/etc/nfqws2/lists/([A-Za-z0-9_.-]{1,128})$~D',$path,$m))return null;
        foreach($virtual as $file)if($file['kind']==='lists'&&$file['name']===$m[1]&&($file['state']??null)==='available'){
            foreach($files as $picked)if($picked['kind']==='lists'&&($picked['target_name']??$picked['name'])===$m[1])return base64_decode($picked['data_base64'],true);
            if($readList!==null){$raw=$readList($file);if(!is_string($raw)||strlen($raw)>262144||!hash_equals($file['sha256'],hash('sha256',$raw)))throw new RuntimeException('source_changed');return $raw;}
        }return null;
    }
    /** getopt_long_only accepts aliases; only reviewed full spellings are safe. */
    private static function canonical(array $words): void
    {
        $options=AsusImportKeenetic::OPTIONS+['--bind-fix4'=>0,'--bind-fix6'=>0,'--fwmark'=>1,'--writable'=>2];
        for($i=0;$i<count($words);$i++){
            $parts=explode('=',$words[$i],2);$name=$parts[0];
            if(!isset($options[$name]))throw new AsusImportAddonScopeError('Use canonical full option names; abbreviations, single-dash aliases and trailing operands cannot prove profile boundaries.');
            $arity=$options[$name];if($arity===0&&count($parts)!==1)throw new AsusImportAddonScopeError('Use canonical options with their documented operands.');
            if($arity===1){$value=$parts[1]??($words[++$i]??'');if($value===''||str_starts_with($value,'--'))throw new AsusImportAddonScopeError('Use canonical options with their documented operands.');}
            if(in_array($name,['--template','--import','--skip'],true))throw new AsusImportAddonScopeError('Templates, imported profiles and skipped programs need a conventional explicit base hostlist/AUTO strategy.');
        }
    }
    private static function specialized(array $words): bool
    {
        for($i=0;$i<count($words);$i++)if($words[$i]==='--comment='.AsusImportTorrentSites::MARKER||($words[$i]==='--comment'&&($words[$i+1]??null)===AsusImportTorrentSites::MARKER))return true;
        return false;
    }
    private static function scope(array $words,array $virtual,array $files,?callable $readList): array
    {
        $positive=false;$domains=[];$excluded=[];$unknown=false;$exemptions=false;
        for($i=0;$i<count($words);$i++){
            $parts=explode('=',$words[$i],2);$name=$parts[0];
            if(!in_array($name,['--hostlist','--hostlist-auto','--hostlist-domains','--hostlist-exclude','--hostlist-exclude-domains'],true))continue;
            $value=$parts[1]??($words[++$i]??'');if($value===''||str_starts_with($value,'--'))throw new AsusImportAddonScopeError('Use a complete hostlist option with its path or domain value.');
            $exclude=str_starts_with($name,'--hostlist-exclude');
            if(str_ends_with($name,'-domains'))$entries=explode(',',$value);
            else{
                $raw=self::listData($value,$virtual,$files,$readList);
                if($raw===null||preg_match('/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/',$raw)||preg_match('//u',$raw)!==1){$unknown=true;continue;}
                if($name==='--hostlist-auto')$positive=true;
                $entries=preg_split('/\r?\n/',$raw);
                // Pinned core reads files with fgets(4096); malformed CR or a
                // chunked long comment cannot prove an unrestricted/positive scope.
                if(preg_match('/\r(?!\n)/',$raw)||array_filter($entries,fn($line)=>strlen($line)>4095)){$unknown=true;continue;}
            }
            foreach($entries as $line){$line=ltrim($line," \t");if($line===''||in_array($line[0],['#',';','/'],true))continue;
                // The actual core reads the first word and honors ^/! flags.
                $domain=strtolower(preg_split('/[ \t\r]/',$line)[0]);
                if(preg_match('/^[\^!]*!/',$domain)){$unknown=true;$exemptions=true;}
                if($exclude)$excluded[]=$domain;else{$positive=true;$domains[]=$domain;}
            }
        }
        return ['positive'=>$positive,'domains'=>$domains,'excluded'=>$excluded,'unknown'=>$unknown,'exemptions'=>$exemptions];
    }
    private static function covers(array $known,string $domain): bool
    {
        foreach($known as $name){$strict=str_starts_with($name,'^');$name=ltrim(strtolower($name),'^');if($domain===$name||(!$strict&&str_ends_with($domain,'.'.$name)))return true;}return false;
    }
    private static function append(string $value,array $domains): string
    {return $domains?rtrim($value).($value===''?'':' ').'--hostlist-domains='.implode(',',$domains):$value;}
    public static function compose(array $changes,array $current,array $blocks,array $resolved,array $picks,array $virtual,array $files,callable $words,?callable $readList=null): array
    {
        if(count($picks)!==count($resolved))throw new RuntimeException('invalid_addon_source');$sources=[];$documents=[];
        foreach($picks as $i=>$pick){$source=$resolved[$i];$entry=$source['entry']??[];$document=$source['document']??[];
            if(($entry['id']??null)!==$pick['id']||($entry['sha256']??null)!==$pick['sha256']||($document['id']??null)!==$pick['id']||!is_int($source['catalog_revision']??null))throw new RuntimeException('invalid_addon_source');
            $document=AsusImportAddonCatalog::document(json_encode($document,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR));
            if($document['title']!==($entry['title']??null)||$document['description']!==($entry['description']??null))throw new RuntimeException('invalid_addon_source');
            $documents[]=$document;$sources[]=['id'=>$pick['id'],'sha256'=>$pick['sha256'],'catalog_revision'=>$source['catalog_revision'],'entry_sha256'=>hash('sha256',json_encode($entry,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR))];
        }
        if(!$blocks)throw new AsusImportAddonScopeError('Select at least one imported base strategy block.');$effective=$changes+$current;
        foreach(array_merge(AsusImportConfig::BLOCKS,['NFQWS_BASE_ARGS','NFQWS_EXTRA_ARGS','NFQWS_ARGS_IPSET'])as $key){
            $value=$effective[$key]??'';
            if(str_contains($value,'--hostlist')&&strpbrk($value,"'\"\\")!==false)throw new AsusImportAddonScopeError('The core treats inner quotes and backslashes as literal hostlist bytes; use an explicit unquoted hostlist/AUTO scope.');
            self::canonical($words($value));
        }
        // BASE_ARGS precedes CUSTOM/UDP and does not apply to every profile. A
        // profile filter there cannot be generalized safely into shared EXTRA_ARGS.
        foreach($words($effective['NFQWS_BASE_ARGS']??'')as $word)if(preg_match('/^--(?:new|hostlist(?:-|=|$)|ipset(?:-|=|$)|filter-)/',$word))throw new RuntimeException('addon_scope_incompatible');
        $extraWords=$words($effective['NFQWS_EXTRA_ARGS']??'');foreach($extraWords as $word)if($word==='--new'||str_starts_with($word,'--new='))throw new RuntimeException('addon_scope_incompatible');
        $segments=[];$sharedSafe=true;$sharedConsumers=[];
        foreach(['NFQWS_ARGS','NFQWS_ARGS_QUIC']as $key){$value=$effective[$key]??'';if($key==='NFQWS_ARGS_QUIC'&&trim($value)==='')continue;$tokens=$words($value);
            foreach($tokens as $word)if($word==='--new'||str_starts_with($word,'--new='))throw new RuntimeException('addon_scope_incompatible');
            $scope=self::scope(array_merge($tokens,$extraWords),$virtual,$files,$readList);$sharedConsumers[$key]=$scope;
            if(!$scope['positive']||$scope['unknown']||self::specialized(array_merge($tokens,$extraWords)))$sharedSafe=false;
        }
        // Only a selected HTTP/QUIC base may authorize shared extension.
        $useShared=$sharedSafe&&(isset($blocks['NFQWS_ARGS'])||isset($blocks['NFQWS_ARGS_QUIC']))&&$sharedConsumers;
        if($useShared)$segments['NFQWS_EXTRA_ARGS']=[['text'=>$effective['NFQWS_EXTRA_ARGS']??'','scope'=>self::scope($extraWords,$virtual,$files,$readList),'added'=>[],'shared'=>true]];
        foreach($blocks as $key=>$_){$value=$effective[$key];$tokens=$words($value);$parts=[[]];
            foreach($tokens as $word){if($word==='--new'||str_starts_with($word,'--new=')){$parts[]=['separator'=>$word];}else $parts[count($parts)-1][]=$word;}
            if(in_array($key,['NFQWS_ARGS','NFQWS_ARGS_QUIC'],true)&&$useShared)continue;
            foreach($parts as $part){$separator=$part['separator']??null;unset($part['separator']);$tokens=array_values($part);$extra=in_array($key,['NFQWS_ARGS','NFQWS_ARGS_QUIC'],true)?$extraWords:[];
                $scope=self::scope(array_merge($tokens,$extra),$virtual,$files,$readList);$parallel=false;
                if($extra&&trim($effective['NFQWS_ARGS_IPSET']??'')!==''){
                    $own=self::scope($tokens,$virtual,$files,$readList);
                    if(!$own['positive']||$own['unknown']){$scope['positive']=false;$parallel=true;}
                }
                $segments[$key][]=['text'=>implode(' ',$tokens),'separator'=>$separator,'scope'=>$scope,'added'=>[],'shared'=>false,'unsafe_parallel'=>$parallel,'specialized'=>self::specialized(array_merge($tokens,$extra))];
            }
        }
        foreach($segments as $parts)foreach($parts as $part){
            if($part['specialized']??false)continue;
            if($part['scope']['exemptions'])throw new AsusImportAddonScopeError('Preserve include-list exemptions in a reviewed exclusion list before extending this scope.');
            if($part['scope']['unknown'])throw new AsusImportAddonScopeError('Choose a readable plain hostlist/AUTO base; unknown or compressed lists cannot prove a safe domain union.');
            if($part['unsafe_parallel']??false)throw new AsusImportAddonScopeError('Keep the parallel IPSET profile unrestricted; choose a base with its own positive domain scope.');
        }
        $general=false;foreach($segments as $parts)foreach($parts as $part)if(!($part['specialized']??false))$general=true;
        if(!$general)throw new AsusImportAddonScopeError('Select a general base strategy; the specialized torrent website segment remains unchanged.');
        $previews=[];
        foreach($documents as $document){$added=[];$blocked=[];
            foreach($segments as &$parts)foreach($parts as &$part){if($part['specialized']??false)continue;$scope=$part['scope'];
                if(($part['shared']??false)===true){
                    foreach($document['domains']as $domain){$needed=false;
                        foreach($sharedConsumers as $consumerKey=>$consumer){
                            if(!isset($blocks[$consumerKey]))continue;
                            if(self::covers($consumer['excluded'],$domain)){$blocked[]=$domain;continue;}
                            if(!self::covers(array_merge($consumer['domains'],$part['added']),$domain))$needed=true;
                        }
                        if($needed&&!self::covers(array_merge($scope['domains'],$part['added']),$domain)){$part['added'][]=$domain;$added[]=$domain;}
                    }
                }else foreach($document['domains']as $domain){
                    if(self::covers($scope['excluded'],$domain)){$blocked[]=$domain;continue;}
                    if($scope['positive']&&!self::covers(array_merge($scope['domains'],$part['added']),$domain)){$part['added'][]=$domain;$added[]=$domain;}
                }
            }unset($part,$parts);
            $added=array_values(array_unique($added));$blocked=array_values(array_unique($blocked));
            if(!$added&&$blocked)throw new AsusImportAddonScopeError('Existing exclusions prevent the requested scope: '.implode(', ',$blocked).'. Keep those exclusions and deselect this add-on.');
            $note=$added?'Uses the selected base algorithms and existing ports/client scope. Existing exclusions remain authoritative.':'No positive filter was added: unrestricted paths already cover these domains, or the domains are already in the selected scope. Existing exclusions remain authoritative.';
            if($blocked){
                $shown=[];foreach($blocked as $domain){$candidate=implode(', ',array_merge($shown,[$domain]));if(strlen($note)+strlen($candidate)>3900)break;$shown[]=$domain;}
                $note.=' Excluded domains left unchanged: '.implode(', ',$shown).'.';
                if(count($shown)<count($blocked))$note.=' Additional exclusions remain visible in the configuration preview.';
            }
            $previews[]=['id'=>$document['id'],'title'=>$document['title'],'kind'=>$document['kind'],'domains'=>$added,'action'=>$added?'scope_extended':'already_covered','note'=>$note];
        }
        foreach($segments as $key=>$parts){$changed=false;$texts=[];foreach($parts as $part){if($part['separator']??null)$texts[]=$part['separator'];$texts[]=self::append($part['text'],$part['added']);$changed=$changed||$part['added']!==[];}
            if($changed)$changes[$key]=implode(' ',$texts);
        }
        return ['changes'=>$changes,'preview'=>$previews,'sources'=>$sources,'shared_changed'=>isset($segments['NFQWS_EXTRA_ARGS'])&&($changes['NFQWS_EXTRA_ARGS']??$effective['NFQWS_EXTRA_ARGS']??'')!==($effective['NFQWS_EXTRA_ARGS']??'')];
    }
}
