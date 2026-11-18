<?php
require_once __DIR__.'/strategy-picker-core.php';

/** A finite method grammar, not stored provider profiles or executable input.
 * Knowledge: bol-van/zapret2 v1.0.7 manual and blockcheck2.d/standard.
 * Priors order exploration; actual measurements alone select the result. */
final class NfqwsStrategySynthesis
{
    public const VERSION='zapret2-1.0.7-v4';
    private const HOSTS=['www.google.com','mail.ru','ozon.ru','ya.ru'];
    private const PAYLOADS=['tls_google'=>'tls_clienthello.bin','tls_iana'=>'tls_clienthello_iana_org.bin','tls_gosuslugi'=>'tls_clienthello_gosuslugi_ru.bin','tls_sberbank'=>'tls_clienthello_sberbank_ru.bin','tls_vk'=>'tls_clienthello_vk_com.bin','tls_vk_kyber'=>'tls_clienthello_vk_com_kyber.bin','quic_google'=>'quic_initial.bin','quic_vk'=>'quic_initial_vk_com.bin','quic_facebook'=>'quic_initial_facebook_com.bin','quic_rutracker'=>'quic_initial_rutracker_org.bin','quic_googlevideo'=>'quic_initial_googlevideo.bin'];
    private const TLS_MODS=['none'=>'','random'=>'rnd,dupsid','google'=>'rnd,dupsid,sni=www.google.com','ozon'=>'rnd,dupsid,sni=ozon.ru','ya'=>'rnd,dupsid,sni=ya.ru','rzd'=>'rnd,dupsid,sni=rzd.ru'];
    private const OVERLAPS=[0,1,4,417,480,568,652,664,679,681,2,211,680,700,740];
    private const POSITIONS=['2','1,midsld','midsld','host+1','sniext+1','1,sniext+1,host+1,midsld-2,midsld,midsld+2,endhost-1','1','1,27','1,host+2,midsld+2,endsld-2','2,sniext+1','1,sniext-2','100,midsld-2,endhost-4','sld+1','2,midsld-2','1,host+1,midsld','3','sniext+1,midsld','1,method+2,host+1,sld+1','host+1,method+2','1,host+2,sld+2,sld+5,sniext+1,sniext+2,endhost-2'];
    private const FOOLING=['none','seq','seq1000','seq2','seqnegative','seqlarge','ack','badsum','md5','ts','ts1500','ts5000','autottl'];
    private const PRIORS=['pass'=>0,'http_hostcase'=>1,'http_methodeol'=>2,'http_domcase'=>3,'multisplit'=>4,'multidisorder'=>5,'fake'=>6,'fakedsplit'=>7,'fakeddisorder'=>8,'hostfakesplit'=>9,'syndata'=>6,'tls_client_hello_clone'=>7,'send'=>3];
    private const COST=['fake_prefix'=>2,'repeat'=>1,'host_override'=>2,'overlap'=>2];
    private const METHODS=[
        'http'=>['pass','http_hostcase','http_methodeol','http_domcase','multisplit','multidisorder','fake','hostfakesplit','syndata'],
        'tls'=>['pass','multisplit','multidisorder','fakedsplit','fakeddisorder','hostfakesplit','fake','syndata','tls_client_hello_clone'],
        'quic'=>['pass','fake','send'],
    ];
    public static function blank():array
    {return ['http'=>['method'=>'pass'],'tls'=>['method'=>'pass'],'quic'=>['method'=>'pass'],'overrides'=>[]];}
    public static function compatibleMemory(mixed $version):bool
    {return $version===self::VERSION||$version==='zapret2-1.0.7-v3';}

    private static function moduleRows():array
    {
        static $rows;
        return $rows??=json_decode(file_get_contents(__DIR__.'/zapret2-pack/priors.json'),true,16,JSON_THROW_ON_ERROR);
    }
    public static function exampleAttributions(array $recipe):array
    {
        $credits=[];
        foreach(self::moduleRows() as $protocol=>$rows){
            $components=[$recipe[$protocol]??null];
            foreach($recipe['overrides']??[] as $rule)if(($rule['protocol']??null)===$protocol)$components[]=$rule['component'];
            foreach($rows as $row)if(in_array($row['component'],$components,false)){
                $credits[$row['attribution']]=true;
                if(count($credits)>=3)return array_keys($credits);
            }
        }
        return array_keys($credits);
    }
    private static function moduleExamples():array
    {
        static $examples;
        if($examples===null){
            $rows=self::moduleRows();
            foreach(['http','tls','quic'] as $protocol){
                $examples[$protocol]=[];
                foreach($rows[$protocol] as $row){
                    $component=$row['component'];
                    self::component($protocol,$component);
                    $examples[$protocol][]=$component;
                }
            }
        }
        return $examples;
    }
    public static function matrix(array $budget):array
    {
        $small=($budget['small']??false)||($budget['busy']??false);$limit=min(6,max(1,(int)($budget['max_repeats']??4)));
        $initial=[];
        $http=[['method'=>'http_hostcase'],['method'=>'http_methodeol'],['method'=>'http_domcase'],['method'=>'multisplit','pos'=>'host+1'],['method'=>'multisplit','pos'=>'2','fake'=>true,'fooling'=>'seq'],['method'=>'multidisorder','pos'=>'host+1']];
        $tls=[['method'=>'multisplit','pos'=>'1,midsld'],['method'=>'multidisorder','pos'=>'1,midsld'],['method'=>'fakedsplit','pos'=>'midsld','fooling'=>'seq'],['method'=>'hostfakesplit','fooling'=>'seq'],['method'=>'multisplit','pos'=>'1,midsld','fake'=>true,'fooling'=>'seq','repeats'=>min(2,$limit)],['method'=>'multidisorder','pos'=>'1,midsld','fake'=>true,'fooling'=>'ack','repeats'=>min(2,$limit)]];
        $quic=[['method'=>'fake','repeats'=>min(2,$limit)],['method'=>'fake','repeats'=>min(4,$limit)],['method'=>'fake','fooling'=>'autottl','repeats'=>min(2,$limit)],['method'=>'pass'],['method'=>'fake','repeats'=>1],['method'=>'fake','fooling'=>'autottl','repeats'=>min(4,$limit)]];
        foreach($tls as $i=>$c)$initial[]=['http'=>$http[$i],'tls'=>$c,'quic'=>$quic[$i],'overrides'=>[]];
        // SYN-window experiments require the engine's hostname cache and a
        // warm-up. Never add an unscoped phase-zero profile to bypass lists.
        foreach([
            ['method'=>'multidisorder','pos'=>self::POSITIONS[5]],
            ['method'=>'pass','window'=>1],
            ['method'=>'multisplit','pos'=>'1,midsld','window'=>1],
            ['method'=>'multidisorder','pos'=>self::POSITIONS[5],'window'=>1],
        ]as $component)$initial[]=['http'=>$http[0],'tls'=>$component,'quic'=>$quic[0],'overrides'=>[]];
        // Shared parameter axes, not a count of distinct compiled programs or
        // domain overrides. Never allocate their Cartesian product on a router.
        $dimensions=['http_methods'=>self::METHODS['http'],'tls_methods'=>self::METHODS['tls'],'split_positions'=>self::POSITIONS,'tcp_fooling'=>self::FOOLING,'fake_prefix'=>[false,true],'sequence_overlap'=>self::OVERLAPS,'fake_hosts'=>self::HOSTS,'tls_modifiers'=>array_keys(self::TLS_MODS),'fake_payloads'=>array_merge(['default','zero64'],self::budgetPayloads($budget)),'tls_window_scale'=>[null,1],'repeats'=>array_values(array_filter([1,2,3,4,5,6],fn($n)=>$n<=$limit)),'quic_fooling'=>['none','autottl']];
        return ['knowledge_version'=>self::VERSION,'independent_of_catalog'=>true,
            'dimensions'=>$dimensions,'space_kind'=>'factorized_grid','module_examples'=>array_map('count',self::moduleExamples()),
            'priors'=>self::PRIORS,'cost_weights'=>self::COST,
            'space_size'=>array_product(array_map('count',$dimensions)),
            'max_trials'=>$small?16:24,'max_rules'=>$small?16:24,'initial'=>$initial];
    }
    /** Fixed inert package assets; actual availability is freshly source-bound
     * by Library. An imported recipe supplies neither bytes nor paths. */
    public static function packagedPayloads():array
    {
        static $samples;
        if($samples===null){
            $extra=json_decode(file_get_contents(__DIR__.'/zapret2-pack/samples.json'),true,8,JSON_THROW_ON_ERROR);
            $samples=self::PAYLOADS+array_map(static fn(array $row):string=>$row['name'],$extra);
        }
        return $samples;
    }
    public static function availablePayloads(array $base):array
    {
        $args=$base['NFQWS_BASE_ARGS']??'';if(!is_string($args))self::bad();$out=[];
        foreach(self::packagedPayloads() as $id=>$name)if(preg_match('~(?:^|\\s)--blob=synthesis_'.preg_quote($id,'~').':@[^\\s]+(?:\\s|$)~D',$args))$out[]=$id;
        return $out;
    }
    private static function requiredPayloads(array $recipe):array
    {
        preg_match_all('~(?:^|[ :])blob=synthesis_([a-z][a-z0-9_]*)(?=[: \r\n]|$)~',implode(' ',self::compile($recipe)),$m);
        return array_values(array_intersect($m[1],array_keys(self::packagedPayloads())));
    }
    private static function budgetPayloads(array $budget):array
    {
        $ids=$budget['synthesis_payloads']??[];
        if(!is_array($ids)||!array_is_list($ids)||count($ids)>count(self::packagedPayloads()))self::bad();
        foreach($ids as $id)if(!is_string($id)||!isset(self::packagedPayloads()[$id]))self::bad();return array_values(array_unique($ids));
    }
    /** Individual supported primitives, not imported orchestration programs. */
    private static function components(string $protocol,array $budget):array
    {
        $max=min(6,max(1,(int)($budget['max_repeats']??4)));$two=min(2,$max);
        if($protocol==='http')$out=[
            ['method'=>'http_hostcase'],['method'=>'http_methodeol'],
            ['method'=>'hostfakesplit','host'=>'mail.ru','fooling'=>'ts','fake'=>true,'repeats'=>$two],
            ['method'=>'syndata'],['method'=>'http_domcase'],
            ['method'=>'multisplit','pos'=>'host+1'],['method'=>'multidisorder','pos'=>'host+1'],
            ['method'=>'fake','fooling'=>'seq','repeats'=>$two],
            ['method'=>'multisplit','pos'=>'2','fake'=>true,'fooling'=>'seq','repeats'=>$two]];
        elseif($protocol==='quic')$out=[['method'=>'fake','repeats'=>1],['method'=>'fake','repeats'=>$two],['method'=>'send'],['method'=>'fake','fooling'=>'autottl','repeats'=>$two]];
        else $out=[['method'=>'multisplit','pos'=>'1,midsld'],['method'=>'multidisorder','pos'=>'1,midsld'],
            ['method'=>'fake','fooling'=>'seq','repeats'=>$two],['method'=>'syndata'],
            ['method'=>'tls_client_hello_clone','fooling'=>'seq','repeats'=>$two],
            ['method'=>'fakedsplit','pos'=>'midsld','fooling'=>'seq'],['method'=>'fakeddisorder','pos'=>'midsld','fooling'=>'seq'],
            ['method'=>'hostfakesplit','fooling'=>'seq'],['method'=>'pass','window'=>1],
            ['method'=>'multisplit','pos'=>'1,midsld','window'=>1],
            ['method'=>'multidisorder','pos'=>self::POSITIONS[5],'window'=>1]];
        if($protocol!=='quic'){
            foreach(($protocol==='tls'?self::POSITIONS:['1','2','host+1','1,host+2,midsld+2,endsld-2'])as $pos)
                foreach(($protocol==='tls'?['multisplit','multidisorder','fakedsplit','fakeddisorder']:['multisplit','multidisorder'])as $method){
                    $c=['method'=>$method,'pos'=>$pos];if(in_array($method,['fakedsplit','fakeddisorder'],true))$c['fooling']='seq';$out[]=$c;
                }
            foreach(['multisplit','multidisorder','hostfakesplit','fake']as $method)foreach(self::FOOLING as $fool){
                $c=['method'=>$method,'fooling'=>$fool,'repeats'=>$two];
                if(in_array($method,['multisplit','multidisorder'],true)){$c['pos']=$protocol==='tls'?'1,midsld':'host+1';$c['fake']=true;}$out[]=$c;
            }
            foreach(self::HOSTS as $host)$out[]=['method'=>'hostfakesplit','host'=>$host,'fooling'=>'ts','repeats'=>$two];
            foreach(self::OVERLAPS as $overlap)if($overlap)$out[]=['method'=>'multisplit','pos'=>$protocol==='tls'?'1,midsld':'host+1','seqovl'=>$overlap];
        }
        $available=$protocol==='http'?[]:array_values(array_filter(self::budgetPayloads($budget),fn($id)=>str_starts_with($id,$protocol==='quic'?'quic_':'tls_')));
        if($available)$out[$protocol==='tls'?2:1]['payload']=$available[0];
        foreach(['none','autottl']as $fool)foreach([1,2,3,4,5,6]as $n)if($n<=$max)$out[]=['method'=>'fake','fooling'=>$fool,'repeats'=>$n];
        if($protocol==='tls')foreach(array_keys(self::TLS_MODS)as $mod)if($mod!=='none')$out[]=['method'=>'fake','fooling'=>'seq','tls_mod'=>$mod,'repeats'=>$two];
        foreach(self::budgetPayloads($budget)as $id)if($protocol!=='http'&&str_starts_with($id,$protocol==='quic'?'quic_':'tls_'))
            $out[]=['method'=>'fake','payload'=>$id,'fooling'=>$protocol==='quic'?'none':'ts','repeats'=>$two];
        if($protocol!=='quic')$out[]=['method'=>'fake','payload'=>'zero64','fooling'=>'seq','repeats'=>$two];
        $eligible=[];
        foreach(self::moduleExamples()[$protocol] as $c){
            if(($c['repeats']??1)>$max)continue;
            $sample=$c['payload']??null;
            if($sample!==null&&$sample!=='zero64'&&!in_array($sample,$available,true))continue;
            $eligible[]=$c;
        }
        // Alternate independent examples and original exploration. The queue
        // deduplicates compiled forms and owns the same trial and history caps.
        $mixed=[];
        for($i=0;$i<max(count($out),count($eligible));$i++){
            if(isset($out[$i]))$mixed[]=$out[$i];
            if(isset($eligible[$i]))$mixed[]=$eligible[$i];
        }
        return $mixed;
    }
    private static function failedDomains(?array $control,string $protocol,string $goal):array
    {
        $runs=$control['runs']??[];if(count($runs)!==2||!is_string($runs[0]['targets']??null)||
            ($runs[1]['targets']??null)!==$runs[0]['targets'])return [];
        $selected=$goal==='all'?null:array_merge(...array_map(fn($s)=>NfqwsStrategyPickerGoals::DOMAINS[$s],explode(',',$goal)));
        $columns=match($protocol){'http'=>['http'],'tls'=>['tls12','tls13'],'quic'=>['quic']};$out=[];
        foreach($runs[0]['domains']??[]as $target=>$values){
            if(!is_string($target)||($host=self::host($target))===null||$selected!==null&&!in_array($host,$selected,true))continue;
            foreach($columns as $column){
                $a=$values[$column]??null;$b=$runs[1]['domains'][$target][$column]??null;
                if(is_bool($a)&&is_bool($b)&&(!$a||!$b)){$out[$host]=true;break;}
            }
        }
        $hosts=array_keys($out);sort($hosts,SORT_STRING);
        if($goal==='all'){
            $primary=array_merge(...array_values(NfqwsStrategyPickerGoals::DOMAINS));
            $failed=array_values(array_intersect($primary,$hosts));
            if($failed)$hosts=$failed;
        }
        return array_slice($hosts,0,128);
    }
    /** Bounded proposals. Prior coverage changes priority, never measurement
     * or winner authority. The runtime alone supplies a captured current base. */
    public static function queue(array $budget,array $history=[],array $explored=[],?array $control=null,string $goal='all',?int $limit=null):array
    {
        $goal=NfqwsStrategyPickerGoals::parse($goal);$max=self::matrix($budget)['max_trials'];$limit??=$max;
        if($limit<1||$limit>$max||!array_is_list($history)||count($history)>8||!array_is_list($explored)||count($explored)>64)self::bad();
        foreach($explored as $key)if(!is_string($key)||!preg_match('/^[a-f0-9]{64}$/D',$key))self::bad();
        $old=array_fill_keys($explored,true);$axes=[];$protected=[];$ordinary=[];$out=[];$seen=[];
        foreach(['tls','http','quic']as $protocol){
            $axes[$protocol]=self::components($protocol,$budget);$hosts=self::failedDomains($control,$protocol,$goal);
            if($hosts)foreach($axes[$protocol]as $component){
                $recipe=self::blank();$recipe['basis']='current';
                $recipe['overrides']=[['protocol'=>$protocol,'domains'=>$hosts,'component'=>$component]];
                $protected[$protocol][]=$recipe;
            }
        }
        for($i=0;$i<max(array_map('count',$axes));$i++)foreach(['tls','http','quic']as $protocol)if(isset($axes[$protocol][$i])){
            $recipe=self::blank();$recipe[$protocol]=$axes[$protocol][$i];$ordinary[]=$recipe;
        }
        $priority=function(array $rows)use($old):array{
            $fresh=[];$repeat=[];$seen=[];
            foreach($rows as $r){$key=self::key($r);if(isset($seen[$key]))continue;$seen[$key]=true;
                if(isset($old[$key]))$repeat[]=$r;else $fresh[]=$r;}
            return array_merge($fresh,$repeat);
        };
        $ordinary=$priority($ordinary);$current=[];
        for($i=0;$i<max(array_map('count',$protected?:[[]]));$i++)foreach(['tls','http','quic']as $p)
            if(isset($protected[$p][$i]))$current[]=$protected[$p][$i];
        $current=$priority($current);
        $add=function(array $recipe)use(&$out,&$seen,$old,$limit):void{
            $key=self::key($recipe);if(count($out)<$limit&&!isset($old[$key])&&!isset($seen[$key])&&$key!==self::key(self::blank())){$out[]=$recipe;$seen[$key]=true;}
        };
        foreach(array_slice($history,0,min(4,max(1,intdiv($limit,6))))as $recipe){
            try{if(!array_diff(self::requiredPayloads($recipe),self::budgetPayloads($budget))&&($recipe['basis']??'empty')==='empty'&&!isset($recipe['custom_scope'])&&($recipe['overrides']??[])===[])$add($recipe);}catch(Throwable $e){}
        }
        foreach(array_slice($current,0,intdiv($limit,3))as $recipe)$add($recipe);
        // Novelty is not permission to spend every slot on the largest axis.
        // Keep live coverage of all protocols even when older keys fill a pool.
        $reserved=['tls'=>[],'http'=>[],'quic'=>[]];
        foreach($ordinary as $recipe)foreach($reserved as $protocol=>$_)
            if($recipe[$protocol]!==['method'=>'pass'])$reserved[$protocol][]=$recipe;
        $quota=min(4,max(1,intdiv($limit-count($out),3)));
        for($i=0;$i<$quota;$i++)foreach($reserved as $protocol=>$_)while($reserved[$protocol]){
            $recipe=array_shift($reserved[$protocol]);if(isset($seen[self::key($recipe)]))continue;
            $add($recipe);break;
        }
        foreach($ordinary as $recipe)$add($recipe);
        return $out;
    }
    /** Only actual repeated measurements can make an improvement eligible.
     * Original-relative search never trades a working protocol for another. */
    public static function improvementCompare(array $baseline,array $candidate,string $goal='all'):array
    {
        $rank=NfqwsStrategyPickerScore::compare($baseline,$candidate,$goal);
        if(in_array($rank['reason'],['incomparable_result','youtube_regression','tls_regression','goal_regression'],true))return $rank;
        foreach(NfqwsStrategyPickerScore::PROTOCOLS as $p){
            $a=min($baseline[0]['metrics'][$p]['ok'],$baseline[1]['metrics'][$p]['ok']);
            $b=min($candidate[0]['metrics'][$p]['ok'],$candidate[1]['metrics'][$p]['ok']);
            if($b<$a)return ['eligible'=>false,'reason'=>'protocol_regression','gain'=>0];
        }
        return $rank;
    }
    /** Exploratory priority only; one run is never repeated quality evidence. */
    public static function bestImprovements(array $observations,array $control,string $goal='all',int $limit=3):array
    {
        $goal=NfqwsStrategyPickerGoals::parse($goal);if($limit<1||$limit>4)self::bad();
        $baseline=$control['runs']??[];if(count($baseline)!==2)return [];$ranked=[];
        foreach(self::usable($observations)as $i=>$row){
            if(($row['recipe']['basis']??'empty')!=='current'||count($row['runs'])<1||count($row['runs'])>2)continue;
            $all=array_merge($baseline,$row['runs']);$target=$baseline[0]['targets']??null;$valid=is_string($target);$loss=0;$worst=0;$gain=0;$youtube=0;
            foreach($all as $run)if(($run['targets']??null)!==$target)$valid=false;
            foreach(NfqwsStrategyPickerScore::PROTOCOLS as $p){
                $total=$baseline[0]['metrics'][$p]['total']??null;
                foreach($all as $run){$v=$run['metrics'][$p]??[];if(!is_int($total)||($v['total']??null)!==$total||!is_int($v['ok']??null)||$v['ok']<0||$v['ok']>$total)$valid=false;}
                if(!$valid)break;
                $a=min(array_map(fn($r)=>$r['metrics'][$p]['ok'],$baseline));
                $b=min(array_map(fn($r)=>$r['metrics'][$p]['ok'],$row['runs']));$loss+=max(0,$a-$b);$worst=max($worst,$a-$b);$gain+=$b-$a;
            }
            if(!$valid)continue;
            foreach(['http','tls12','tls13','quic']as $p)if(($baseline[0]['youtube'][$p]??false)&&($baseline[1]['youtube'][$p]??false))
                foreach($row['runs']as $run)if(($run['youtube'][$p]??null)!==true){$youtube++;break;}
            $primaryGain=0;
            foreach(NfqwsStrategyPickerGoals::selected($goal)as $service){
                if($goal==='all'&&!array_key_exists($service,$baseline[0]['services']??[]))continue;
                foreach(['http','tls12','tls13','quic']as $p){
                    foreach($all as $run)if(!is_int($run['services'][$service][$p]['ok']??null))$valid=false;
                    if(!$valid)break 2;
                    $primaryGain+=min(array_map(fn($r)=>$r['services'][$service][$p]['ok'],$row['runs']))-
                        min(array_map(fn($r)=>$r['services'][$service][$p]['ok'],$baseline));
                }
            }
            if(!$valid)continue;
            $protocols=array_values(array_unique(array_column($row['recipe']['overrides'],'protocol')));sort($protocols);
            $ranked[]=['recipe'=>$row['recipe'],'protocols'=>implode(',',$protocols),
                'priority'=>[$youtube,$worst,$loss,-$primaryGain,-$gain,self::cost($row['recipe']),$i]];
        }
        usort($ranked,fn($a,$b)=>$a['priority']<=>$b['priority']);$out=[];$seen=[];$protocols=[];
        foreach([true,false]as $diverse)foreach($ranked as $row){
            $key=self::key($row['recipe']);if(isset($seen[$key])||$diverse&&isset($protocols[$row['protocols']]))continue;
            $out[]=$row['recipe'];$seen[$key]=true;$protocols[$row['protocols']]=true;if(count($out)>=$limit)return $out;
        }
        return $out;
    }
    public static function finalists(array $independent,array $improvements,array $control,string $goal='all',int $maxRules=24):array
    {
        $current=self::blank();$current['basis']='current';$protocols=[];
        foreach(self::bestImprovements($improvements,$control,$goal,3)as $recipe){
            $measured=null;foreach($improvements as $row)if(self::key($row['recipe'])===self::key($recipe)){$measured=$row;break;}
            if($measured===null||!self::improvementCompare($control['runs'],$measured['runs'],$goal)['eligible'])continue;
            foreach($recipe['overrides']as $rule)if(!isset($protocols[$rule['protocol']])){
                $current['overrides'][]=$rule;$protocols[$rule['protocol']]=true;
            }
        }
        $out=[];
        if($current['overrides']){self::compile($current);$out[]=$current;}
        $recipe=self::assemble($independent,$goal,$maxRules);
        if(!$out||self::key($recipe)!==self::key(self::blank()))$out[]=$recipe;
        return $out;
    }
    private static function bad():never{throw new RuntimeException('invalid_synthesis_recipe');}
    private static function component(string $protocol,array $c):string
    {
        if(!isset(self::METHODS[$protocol])||array_diff(array_keys($c),['method','pos','fake','fooling','repeats','seqovl','window','host','payload','tls_mod']))self::bad();
        if(array_key_exists('window',$c)&&($protocol!=='tls'||$c['window']!==1))self::bad();
        $m=$c['method']??null;if(!is_string($m)||!in_array($m,self::METHODS[$protocol],true))self::bad();
        $pos=$c['pos']??'1,midsld';$fake=$c['fake']??false;$fool=$c['fooling']??'none';$n=$c['repeats']??1;$overlap=$c['seqovl']??0;
        $host=$c['host']??'www.google.com';$payload=$c['payload']??'default';$mod=$c['tls_mod']??'none';
        if(!is_string($pos)||!in_array($pos,self::POSITIONS,true)||!is_bool($fake)||!is_int($n)||!in_array($n,[1,2,3,4,5,6],true)||!is_int($overlap)||!in_array($overlap,self::OVERLAPS,true)||!is_string($fool)||!in_array($fool,$protocol==='quic'?['none','autottl']:self::FOOLING,true)||!is_string($host)||!in_array($host,self::HOSTS,true)||!is_string($payload)||!in_array($payload,array_merge(['default','zero64'],array_keys(self::packagedPayloads())),true)||!is_string($mod)||!isset(self::TLS_MODS[$mod]))self::bad();
        $seg=in_array($m,['multisplit','multidisorder','fakedsplit','fakeddisorder'],true);
        if((isset($c['pos'])&&!$seg)||($overlap&&!in_array($m,['multisplit','multidisorder'],true))||($fake&&($protocol==='quic'||in_array($m,['pass','syndata','tls_client_hello_clone','send'],true)))||($m==='pass'&&array_diff(array_keys($c),['method','window']))||isset($c['host'])&&$m!=='hostfakesplit'||isset($c['tls_mod'])&&($protocol!=='tls'||$m!=='fake'&&!$fake)||isset($c['payload'])&&$m!=='fake'&&!$fake||isset(self::packagedPayloads()[$payload])&&!str_starts_with($payload,$protocol==='quic'?'quic_':'tls_'))self::bad();
        if($m==='pass')return '--lua-desync=pass';
        if($m==='send'){if(array_diff(array_keys($c),['method']))self::bad();return '--lua-desync=send:ipfrag:ipfrag_pos_udp=8';}
        if($m==='syndata'){if(array_diff(array_keys($c),['method']))self::bad();return '--lua-desync=syndata';}
        $f=['none'=>'','seq'=>':tcp_seq=10000','seq1000'=>':tcp_seq=1000','seq2'=>':tcp_seq=2','seqnegative'=>':tcp_seq=-10000','seqlarge'=>':tcp_seq=10000000','ack'=>':tcp_ack=-66000','badsum'=>':badsum','md5'=>':tcp_md5','ts'=>':tcp_ts=-600000:tcp_ts_up','ts1500'=>':tcp_ts=-1500:tcp_ts_up','ts5000'=>':tcp_ts=-5000:tcp_ts_up','autottl'=>':ip_autottl=-2,3-20:ip6_autottl=-2,3-20'][$fool];
        $blob=$payload==='default'?'fake_default_'.($protocol==='tls'?'tls':($protocol==='http'?'http':'quic')):($payload==='zero64'?'0x'.str_repeat('00',64):'synthesis_'.$payload);
        $modifier=$mod==='none'?'':':tls_mod='.self::TLS_MODS[$mod];
        $prefix=$fake?'--lua-desync=fake:blob='.$blob.$modifier.$f.':repeats='.$n.' ':'';
        if($m==='fake')return '--lua-desync=fake:blob='.$blob.$modifier.$f.':repeats='.$n;
        if($m==='tls_client_hello_clone')return '--lua-desync=tls_client_hello_clone:blob=fake_default_tls:fallback=fake_default_tls --lua-desync=fake:blob=fake_default_tls'.$f.':repeats='.$n;
        if($seg){$v='--lua-desync='.$m.':pos='.$pos;if(in_array($m,['fakedsplit','fakeddisorder'],true))$v.=$f;
            if($overlap)$v.=':seqovl='.$overlap.':seqovl_pattern='.$blob;return $prefix.$v;}
        if($m==='hostfakesplit')return $prefix.'--lua-desync=hostfakesplit:host='.$host.':midhost=midsld'.$f.':repeats='.$n;
        return $prefix.'--lua-desync='.$m;
    }
    public static function domain(string $host):bool
    {
        if(strlen($host)>253||!preg_match('/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$/D',$host))return false;
        $tld=substr($host,strrpos($host,'.')+1);
        if(str_starts_with($tld,'xn--')){
            require_once __DIR__.'/idna.php';if(NfqwsIdna::ascii($host)!==$host)return false;
        }
        foreach(['t.me','telegram.org','telegram.me','telesco.pe']as $excluded)if($host===$excluded||str_ends_with($host,'.'.$excluded))return false;
        return true;
    }
    public static function host(string $target):?string
    {
        if(strlen($target)>2048||preg_match('/[\s\\\\\x00-\x1f\x7f]/',$target))return null;
        $v=parse_url(str_contains($target,'://')?$target:'https://'.$target);
        if(!is_array($v)||!in_array(strtolower($v['scheme']??''),['http','https'],true)||isset($v['user'])||isset($v['pass'])||!is_string($v['host']??null))return null;
        $host=strtolower($v['host']);return self::domain($host)?$host:null;
    }
    private static function encode(array $v):string
    {return json_encode($v,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);}
    private static function keys(array $v,array $keys):bool
    {$a=array_keys($v);sort($a);sort($keys);return $a===$keys;}
    private static function protectedDomains(array $manifest,array $nativeTargets):array
    {
        $domains=[];
        foreach($nativeTargets as $target){
            if(!is_string($target)||($host=self::host($target))===null)self::bad();$domains[]=$host;
        }
        foreach($manifest['targets']as $target)if($target['kind']==='domain')$domains[]=$target['host'];
        $domains=array_values(array_unique($domains));sort($domains,SORT_STRING);return $domains;
    }
    /** Scope metadata is bound to the immutable manifest, never fresh DNS or
     * editable per-host score flags. The trusted joint adapter owns provenance. */
    private static function scope(array $recipe):?array
    {
        if(!array_key_exists('custom_scope',$recipe))return null;
        try{
            require_once __DIR__.'/strategy-picker-custom-worker.php';
            $scope=$recipe['custom_scope'];
            if(!is_array($scope)||!self::keys($scope,['manifest','manifest_sha256','protected_domains'])||
                !is_array($scope['manifest'])||!is_string($scope['manifest_sha256'])||
                hash('sha256',self::encode($scope['manifest']))!==$scope['manifest_sha256']||
                !is_array($scope['protected_domains'])||!array_is_list($scope['protected_domains'])||
                count($scope['protected_domains'])>256)self::bad();
            $manifest=NfqwsStrategyPickerCustomWorker::document(self::encode($scope['manifest']),'probe');
            if($manifest['schema_version']!==2)self::bad();
            $previous=null;
            foreach($scope['protected_domains']as $host){
                if(!is_string($host)||!self::domain($host)||$previous!==null&&strcmp($previous,$host)>=0)self::bad();
                $previous=$host;
            }
            $ips=[];
            foreach($manifest['targets']as $target){
                if($target['kind']==='ipv4')$ips[]=$target['host'];
                elseif(!in_array($target['host'],$scope['protected_domains'],true))self::bad();
            }
            return ['manifest'=>$manifest,'ips'=>$ips,'protected_domains'=>$scope['protected_domains']];
        }catch(Throwable $e){self::bad();}
    }
    /** Discovery candidates need explicit no-SNI destination rules too. Keep
     * domain-only recipes byte-identical. Existing assembled scope is immutable. */
    public static function forTargets(array $recipe,array $manifest,array $nativeTargets):array
    {
        require_once __DIR__.'/strategy-picker-custom-worker.php';
        $identity=NfqwsStrategyPickerCustomWorker::scope($manifest);self::compile($recipe);
        if($identity['schema_version']===1){if(isset($recipe['custom_scope']))self::bad();return $recipe;}
        $manifest=NfqwsStrategyPickerCustomWorker::document(self::encode($manifest),'probe');
        $scope=['manifest'=>$manifest,'manifest_sha256'=>hash('sha256',self::encode($manifest)),
            'protected_domains'=>self::protectedDomains($manifest,$nativeTargets)];
        if(array_key_exists('custom_scope',$recipe)){
            if($recipe['custom_scope']!==$scope)self::bad();return $recipe;
        }
        if(($recipe['overrides']??[])!==[])self::bad();
        $recipe['custom_scope']=$scope;$recipe['overrides']=[];$ips=[];
        foreach($manifest['targets']as $target)if($target['kind']==='ipv4')$ips[]=$target['host'];
        foreach(array_chunk($scope['protected_domains'],128)as $domains)
            $recipe['overrides'][]=['protocol'=>'tls','domains'=>$domains,'component'=>$recipe['tls']];
        $recipe['overrides'][]=['protocol'=>'tls','addresses'=>$ips,'component'=>$recipe['tls']];
        self::compile($recipe);return $recipe;
    }
    private static function rule(string $p,array $c,array $domains=[],array $addresses=[]):string
    {
        self::component($p,$c);$window=$p==='tls'&&isset($c['window']);$syn=$c['method']==='syndata';
        $rule='--filter-l3=ipv4 '.match($p){'http'=>$syn?'--filter-tcp=80 --payload=all':'--filter-tcp=80 --filter-l7=http --payload=http_req','tls'=>$window||$syn?'--filter-tcp=443 --payload=all':'--filter-tcp=443 --filter-l7=tls --payload=tls_client_hello','quic'=>'--filter-udp=443 --filter-l7=quic --payload=quic_initial',default=>self::bad()};
        if($domains)$rule.=' --hostlist-domains='.implode(',',$domains);
        if($addresses)$rule.=' --ipset-ip='.implode(',',$addresses);
        return $rule.' --out-range=-d8 '.($window?'--lua-desync=wssize:wsize=1:scale=1:dir=out --payload=tls_client_hello ':'').self::component($p,$c);
    }
    public static function compile(array $recipe):array
    {
        if(array_diff(array_keys($recipe),['http','tls','quic','overrides','custom_scope','basis']))self::bad();
        $basis=$recipe['basis']??'empty';if(!in_array($basis,['empty','current'],true))self::bad();
        foreach(['http','tls','quic']as $p)if(!is_array($recipe[$p]??null))self::bad();
        $scope=self::scope($recipe);$overrides=$recipe['overrides']??[];
        if($basis==='current'){
            if($scope!==null||!$overrides)self::bad();
            foreach(['http','tls','quic']as $p)if($recipe[$p]!==['method'=>'pass'])self::bad();
        }
        // An IP program has two exclusion pass guards: fixed Telegram names
        // here and the owner's exclusion file at bind(). Both consume rules.
        if(!is_array($overrides)||!array_is_list($overrides)||count($overrides)+($scope===null?0:2)>24)self::bad();
        $custom=[];$seenIps=[];$domainShields=[];$ipStarted=false;
        if($scope!==null)$custom[]=self::rule('tls',['method'=>'pass'],['t.me','telegram.org','telegram.me','telesco.pe']);
        foreach($overrides as $o){
            if(is_array($o)&&array_key_exists('addresses',$o)){
                if($scope===null||!self::keys($o,['protocol','addresses','component'])||$o['protocol']!=='tls'||
                    !is_array($o['addresses'])||!array_is_list($o['addresses'])||!$o['addresses']||count($o['addresses'])>5||
                    !is_array($o['component']))self::bad();
                foreach($o['addresses']as $address){
                    if(!is_string($address)||!in_array($address,$scope['ips'],true)||in_array($address,$seenIps,true))self::bad();
                    $seenIps[]=$address;
                }
                $ipStarted=true;$custom[]=self::rule('tls',$o['component'],[],$o['addresses']);continue;
            }
            if(!is_array($o)||array_diff(array_keys($o),['protocol','domains','component'])||!in_array($o['protocol']??null,['http','tls','quic'],true)||!is_array($o['domains']??null)||!array_is_list($o['domains'])||!$o['domains']||count($o['domains'])>128||!is_array($o['component']??null))self::bad();
            if($ipStarted)self::bad();
            foreach($o['domains']as $host){
                if(!is_string($host)||!self::domain($host)||$scope!==null&&!in_array($host,$scope['protected_domains'],true))self::bad();
                if($o['protocol']==='tls')$domainShields[]=$host;
            }
            $custom[]=self::rule($o['protocol'],$o['component'],$o['domains']);
        }
        if($scope!==null){
            $expected=$scope['ips'];sort($expected,SORT_STRING);sort($seenIps,SORT_STRING);if($expected!==$seenIps)self::bad();
            foreach($scope['protected_domains']as $host){
                $found=false;foreach($domainShields as $parent)if($host===$parent||str_ends_with($host,'.'.$parent)){$found=true;break;}
                if(!$found)self::bad();
            }
        }
        return ['NFQWS_ARGS'=>self::rule('http',$recipe['http']).' --new '.self::rule('tls',$recipe['tls']),
            'NFQWS_ARGS_QUIC'=>self::rule('quic',$recipe['quic']),'NFQWS_ARGS_UDP'=>'','NFQWS_ARGS_CUSTOM'=>implode(' --new ',$custom)];
    }
    public static function key(array $recipe):string
    {
        $rules=self::compile($recipe);
        return hash('sha256',json_encode(($recipe['basis']??'empty')==='current'?['basis'=>'current','rules'=>$rules]:$rules,JSON_THROW_ON_ERROR));
    }
    /** Optional scope extension, never a claim that these extra sites were tested. */
    public static function torrentSites(array $config,array $recipe):array
    {
        require_once __DIR__.'/import-torrent-sites.php';
        $plain=self::bind($recipe,$config);
        $suffix=' --hostlist-domains='.implode(',',AsusImportTorrentSites::SITES).' --comment=nfqws2-synthesis-trackers';
        if(($recipe['tls']['method']??'pass')==='pass')throw new RuntimeException('torrent_sites_incompatible');
        foreach(['NFQWS_ARGS','NFQWS_ARGS_QUIC','NFQWS_ARGS_CUSTOM','NFQWS_ARGS_UDP']as $key){
            $allowed=$plain[$key];
            if(($config[$key]??null)!==$allowed&&($key!=='NFQWS_ARGS'||!in_array($config[$key]??null,[$allowed.$suffix,$allowed.$suffix.'-beta'],true)))throw new RuntimeException('torrent_sites_incompatible');
        }
        $config['NFQWS_ARGS']=$plain['NFQWS_ARGS'].$suffix;
        return $config;
    }
    private static function componentCost(string $protocol,array $c):int
    {
        self::component($protocol,$c);
        return self::PRIORS[$c['method']]+(isset($c['window'])?12:0)+(($c['fake']??false)?self::COST['fake_prefix']:0)+max(0,($c['repeats']??1)-1)*self::COST['repeat']+($c['seqovl']??0)*self::COST['overlap'];
    }
    public static function cost(array $recipe):int
    {
        self::compile($recipe);$cost=(count($recipe['overrides']??[])+(isset($recipe['custom_scope'])?2:0))*self::COST['host_override'];
        if(($recipe['basis']??'empty')==='current')foreach($recipe['overrides']as $rule)$cost+=self::componentCost($rule['protocol'],$rule['component']);
        foreach(['http','tls','quic']as $p)$cost+=self::componentCost($p,$recipe[$p]);return $cost;
    }
    /** The common launcher appends EXTRA once, to the last TCP profile only. */
    public static function bind(array $recipe,array $base):array
    {
        $extra=$base['NFQWS_EXTRA_ARGS']??'';
        if(!is_string($extra)||!preg_match('~(?:^|\s)--hostlist-exclude=(\S+)~',$extra,$m)||!str_contains($extra,'--hostlist='))self::bad();
        $rules=self::compile($recipe);
        if(array_diff(self::requiredPayloads($recipe),self::availablePayloads($base)))throw new RuntimeException('synthesis_payload_unavailable');
        if(str_contains(implode(' ',$rules),'--lua-desync=wssize:')||str_contains(implode(' ',$rules),'--lua-desync=syndata')){
            $baseArgs=$base['NFQWS_BASE_ARGS']??'';if(!is_string($baseArgs))self::bad();
            if(!preg_match('/(?:^|\s)--ipcache-hostname(?:\s|$)/D',$baseArgs))$base['NFQWS_BASE_ARGS']=trim($baseArgs.' --ipcache-hostname');
        }
        if(($recipe['basis']??'empty')==='current'){
            // The runtime supplies its freshly captured, measured original
            // library entry. A recipe selects finite scoped additions only;
            // it neither supplies an original config nor authorizes a write.
            $count=count($recipe['overrides']);$ipset=trim($base['NFQWS_ARGS_IPSET']??'')!=='';
            foreach(['NFQWS_ARGS','NFQWS_ARGS_QUIC','NFQWS_ARGS_UDP','NFQWS_ARGS_CUSTOM']as $key){
                $old=$base[$key]??'';if(!is_string($old))self::bad();
                if(trim($old)!=='')$count+=(1+preg_match_all('/(?:^|\s)--new(?:\s|$)/',$old))*
                    ($ipset&&in_array($key,['NFQWS_ARGS','NFQWS_ARGS_QUIC'],true)?2:1);
            }
            if($count>24)throw new RuntimeException('synthesis_rule_limit');
            $added=str_replace(' --out-range=',
                ' --hostlist-exclude='.$m[1].' --hostlist-exclude-domains=t.me,telegram.org,telegram.me,telesco.pe --out-range=',
                $rules['NFQWS_ARGS_CUSTOM']);
            $old=$base['NFQWS_ARGS_CUSTOM']??'';
            $base['NFQWS_ARGS_CUSTOM']=$added.(trim($old)===''?'':' --new '.$old);
            return $base;
        }
        // Each intermediate TCP profile needs its own include/auto/exclude.
        // The launcher's normal append supplies the last TCP and QUIC scopes.
        $rules['NFQWS_ARGS']=str_replace(' --new ',' '.$extra.' --new ',$rules['NFQWS_ARGS']);
        if($rules['NFQWS_ARGS_CUSTOM']!==''){
            $parts=explode(' --new ',$rules['NFQWS_ARGS_CUSTOM']);
            foreach($parts as $i=>&$part)if(!isset($recipe['custom_scope'])||$i!==0&&!str_contains($part,' --ipset-ip='))
                // Window programs have two payload phases in one profile;
                // the engine accepts each exclusion file only once per profile.
                $part=preg_replace_callback('/ --payload=/',static fn()=>' --hostlist-exclude='.$m[1].' --payload=',$part,1);
            unset($part);
            if(isset($recipe['custom_scope'])){
                // Even an exclude-only hostlist prevents a no-SNI profile
                // match in the pinned engine. Protect exclusions before the
                // IP rule using a pass profile, not a hostlist on the IP rule.
                array_unshift($parts,str_replace(' --payload=',' --hostlist='.$m[1].' --payload=',self::rule('tls',['method'=>'pass'])));
            }
            $rules['NFQWS_ARGS_CUSTOM']=implode(' --new ',$parts);
        }
        return array_replace($base,$rules);
    }
    private static function supplementBad():never
    {throw new RuntimeException('supplement_incompatible');}
    /** Canonical unquoted argv only; this never evaluates a shell or Lua. */
    private static function supplementPairs(string $text):array
    {
        require_once __DIR__.'/import-keenetic.php';
        if(strlen($text)>65536||preg_match('/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\'"`$\\\\]/',$text))self::supplementBad();
        $words=preg_split('/\s+/',trim($text),-1,PREG_SPLIT_NO_EMPTY);if(count($words)>8192)self::supplementBad();$out=[];
        foreach($words as $word)if($word===''||str_starts_with($word,'#'))self::supplementBad();
        for($i=0;$i<count($words);$i++){
            $parts=explode('=',$words[$i],2);$name=$parts[0];$arity=AsusImportKeenetic::OPTIONS[$name]??null;
            if($arity===null||in_array($name,['--template','--import','--skip','--filter-ssid','--filter-ssid-neg','--filter-mark'],true))self::supplementBad();
            if($name==='--new'){if(count($parts)!==1)self::supplementBad();$value='';}
            elseif($arity===0){if(count($parts)!==1)self::supplementBad();$value='';}
            elseif($arity===2)$value=$parts[1]??'';
            else{$value=$parts[1]??($words[++$i]??'');if($value===''||str_starts_with($value,'--'))self::supplementBad();}
            if(str_starts_with($name,'--filter-')&&str_contains($value,'~'))self::supplementBad();
            if($name==='--lua-desync'){
                $call=explode(':',$value);$function=array_shift($call);
                if(!in_array($function,array_unique(array_merge(...array_values(self::METHODS))),true))self::supplementBad();
                foreach($call as $part){$pair=explode('=',$part,2);if(!in_array($pair[0],['pos','blob','repeats','tcp_seq','tcp_ack','badsum','tcp_md5','ip_autottl','ip6_autottl','seqovl','seqovl_pattern','host','midhost'],true)||isset($pair[1])&&!preg_match('/^[A-Za-z0-9_.,+\-]+$/D',$pair[1]))self::supplementBad();}
            }
            $out[]=[$name,$value];
        }
        return $out;
    }
    private static function supplementPort(string $ports,int $wanted):bool
    {
        $found=false;
        foreach(explode(',',$ports)as $part){if(!preg_match('/^([1-9][0-9]{0,4})(?:[:-]([1-9][0-9]{0,4}))?$/D',$part,$m))self::supplementBad();$a=(int)$m[1];$z=(int)($m[2]??$m[1]);if($a>$z||$z>65535)self::supplementBad();if($a<=$wanted&&$wanted<=$z)$found=true;}
        return $found;
    }
    /** Read-only stage of supplement-current. No provider, file mutation,
     * export, trial, Apply or compatibility authority is supplied here. */
    public static function supplementPreview(string $current,array $recipe,array $domains,array $resources,array $binding):array
    {
        require_once __DIR__.'/share-dependencies.php';
        if(!self::keys($binding,['config_sha256','resources_sha256'])||!is_string($binding['config_sha256'])||!is_string($binding['resources_sha256'])||
            !hash_equals(hash('sha256',$current),$binding['config_sha256'])||count($resources)>128)self::supplementBad();
        foreach($resources as $path=>$sha)if(!is_string($path)||NfqwsResourcePaths::canonical($path)!==$path||!is_string($sha)||!preg_match('/^[a-f0-9]{64}$/D',$sha))self::supplementBad();
        ksort($resources,SORT_STRING);$resourceSha=hash('sha256',self::encode($resources));
        if(!hash_equals($resourceSha,$binding['resources_sha256']))self::supplementBad();
        if(!array_is_list($domains)||count($domains)<1||count($domains)>5||count(array_unique($domains,SORT_REGULAR))!==count($domains))self::supplementBad();
        foreach($domains as $host)if(!is_string($host)||!self::domain($host))self::supplementBad();sort($domains,SORT_STRING);
        self::compile($recipe);
        if(($recipe['overrides']??[])!==[]||isset($recipe['custom_scope']))self::supplementBad();
        $values=AsusImportConfig::parse($current);$pairs=[];$required=[];$initializers=[];$exclusions=[];
        $reference=function(string $value)use(&$required,$resources):string{
            $canonical=NfqwsResourcePaths::canonical($value);
            if($canonical===null||!isset($resources[$canonical]))self::supplementBad();
            $required[$canonical]=$resources[$canonical];return $canonical;
        };
        foreach(array_merge(AsusImportConfig::BLOCKS,['NFQWS_BASE_ARGS','NFQWS_EXTRA_ARGS','NFQWS_ARGS_IPSET'])as $key){
            $pairs[$key]=self::supplementPairs($values[$key]??'');$previousNew=true;
            foreach($pairs[$key]as [$name,$value]){
                if($name==='--new'){if($key!=='NFQWS_ARGS_CUSTOM'||$previousNew)self::supplementBad();$previousNew=true;continue;}$previousNew=false;
                if($key==='NFQWS_BASE_ARGS'&&!in_array($name,['--lua-init','--blob','--lua-gc','--debug','--fastpath-workaround','--ctrack-timeouts','--ipcache-lifetime','--ipcache-hostname'],true))self::supplementBad();
                if($key==='NFQWS_EXTRA_ARGS'&&!in_array($name,['--hostlist','--hostlist-auto','--hostlist-domains','--hostlist-exclude','--hostlist-exclude-domains','--hostlist-auto-fail-threshold','--hostlist-auto-fail-time','--hostlist-auto-retrans-threshold','--hostlist-auto-retrans-maxseq','--hostlist-auto-retrans-reset','--hostlist-auto-incoming-maxseq','--hostlist-auto-udp-in','--hostlist-auto-udp-out'],true))self::supplementBad();
                if(in_array($name,['--hostlist','--hostlist-exclude','--hostlist-auto','--ipset','--ipset-exclude'],true))$reference($value);
                if($name==='--lua-init'){
                    if($key!=='NFQWS_BASE_ARGS'||!str_starts_with($value,'@'))self::supplementBad();$initializers[]=$reference(substr($value,1));
                }
                if($name==='--blob'){
                    if($key!=='NFQWS_BASE_ARGS'||!preg_match('/^([A-Za-z_][A-Za-z0-9_]*):@(.+)$/D',$value,$m)||in_array($m[1],['fake_default_http','fake_default_tls','fake_default_quic'],true))self::supplementBad();$reference($m[2]);
                }
                if($key==='NFQWS_EXTRA_ARGS'&&in_array($name,['--hostlist-exclude','--hostlist-exclude-domains'],true))$exclusions[]=$name.'='.$value;
            }
            if($pairs[$key]&&$previousNew)self::supplementBad();
        }
        if(!AsusShareDependencies::synthesisInitializers($initializers,$resources))self::supplementBad();
        if(trim($values['NFQWS_ARGS']??'')==='')self::supplementBad();
        $profiles=[];
        foreach(['http','tls','quic']as $protocol){
            if($recipe[$protocol]['method']==='pass')continue;
            if(!self::supplementPort($values[$protocol==='quic'?'UDP_PORTS':'TCP_PORTS']??'',$protocol==='http'?80:443))self::supplementBad();
            $profiles[]=self::rule($protocol,$recipe[$protocol],$domains).' --hostlist-exclude-domains=t.me,telegram.org,telegram.me,telesco.pe'.($exclusions?' '.implode(' ',$exclusions):'').' --comment=nfqws2-supplement-preview-v1';
        }
        if(!$profiles)self::supplementBad();
        $count=count($profiles);$ipset=trim($values['NFQWS_ARGS_IPSET']??'')!=='';
        foreach(['NFQWS_ARGS_CUSTOM','NFQWS_ARGS_UDP','NFQWS_ARGS_QUIC','NFQWS_ARGS']as $key)if(trim($values[$key]??'')!==''){
            $n=1;foreach($pairs[$key]as [$name])if($name==='--new')$n++;
            $count+=$n+($ipset&&in_array($key,['NFQWS_ARGS','NFQWS_ARGS_QUIC'],true)?$n:0);
        }
        if($count>24)self::supplementBad();
        $old=$values['NFQWS_ARGS_CUSTOM']??'';$custom=implode(' --new ',$profiles).(trim($old)===''?'':' --new '.$old);
        $candidate=AsusImportConfig::replace($current,['NFQWS_ARGS_CUSTOM'=>$custom]);ksort($required,SORT_STRING);
        $proof=['mode'=>'supplement-current-preview-v1','base_sha256'=>$binding['config_sha256'],'resources_sha256'=>$resourceSha,
            'candidate_sha256'=>hash('sha256',$candidate),'recipe'=>$recipe,'domains'=>$domains,'resource_bindings'=>$required];
        return $proof+['preview_sha256'=>hash('sha256',self::encode($proof)),'candidate_config'=>$candidate,'added_profiles'=>$profiles,
            'changed_keys'=>['NFQWS_ARGS_CUSTOM'],'profile_count'=>$count,'can_apply'=>false,'can_export'=>false,'combined_verified'=>false,
            'resources_bundled'=>false,'resource_inventory_proved'=>false,'actual_device_calls'=>false];
    }

    private static function usable(array $observations):array
    {
        $out=[];$target=$observations[0]['runs'][0]['targets']??null;
        $custom=isset($observations[0])&&array_key_exists('custom_runs',$observations[0]);$customTarget=null;
        foreach($observations as $o){
            if(!is_array($o['recipe']??null)||!is_array($o['runs']??null)||!$o['runs']||count($o['runs'])>2){
                if($custom)throw new RuntimeException('incomparable_result');continue;
            }
            $valid=is_string($target);
            foreach($o['runs']as $r)if(($r['targets']??null)!==$target||!is_array($r['metrics']??null))$valid=false;
            if($custom!==array_key_exists('custom_runs',$o))throw new RuntimeException('incomparable_result');
            if(!$valid){if($custom)throw new RuntimeException('incomparable_result');continue;}
            self::compile($o['recipe']);unset($o['custom_minimum']);
            if($custom){
                require_once __DIR__.'/strategy-picker-custom-score.php';
                if(!is_array($o['custom_runs'])||!array_is_list($o['runs'])||count($o['custom_runs'])!==count($o['runs']))
                    throw new RuntimeException('incomparable_result');
                $minimum=NfqwsStrategyPickerCustomScore::minimum($o['custom_runs']);
                foreach($o['runs']as $i=>$run)if(($run['context_sha256']??null)!==$o['custom_runs'][$i]['context_sha256'])
                    throw new RuntimeException('incomparable_result');
                if($customTarget!==null&&$minimum['targets']!==$customTarget)throw new RuntimeException('incomparable_result');
                if(($o['custom_runs'][0]['schema_version']??null)===2){
                    try{
                        $manifest=$o['custom_manifest']??null;
                        if(!is_array($manifest))throw new RuntimeException('incomparable_result');
                        $manifest=NfqwsStrategyPickerCustomWorker::document(self::encode($manifest),'probe');
                        if($manifest['schema_version']!==2)throw new RuntimeException('incomparable_result');
                        $sha=hash('sha256',self::encode($manifest));
                        foreach($o['custom_runs']as $run)if($run['manifest_sha256']!==$sha||$run['hosts']!==$manifest['hosts']||
                            $run['dns_context']!==$manifest['dns_context']||$run['target_policy_version']!==$manifest['target_policy_version']||
                            $run['target_identities']!==$manifest['targets'])throw new RuntimeException('incomparable_result');
                        if(!isset($o['recipe']['custom_scope'])||
                            self::forTargets($o['recipe'],$manifest,array_merge(array_keys($o['runs'][0]['domains']??[]),$o['runs'][0]['probe_hosts']??[]))!==$o['recipe'])
                            throw new RuntimeException('incomparable_result');
                        $o['custom_manifest']=$manifest;
                    }catch(Throwable $e){throw new RuntimeException('incomparable_result',0,$e);}
                }else foreach($minimum['hosts']as $host)if(!self::domain($host))throw new RuntimeException('incomparable_result');
                $customTarget=$minimum['targets'];$o['custom_minimum']=$minimum;
            }
            $out[]=$o;
        }return $out;
    }
    private static function value(array $o,string $p,string $goal,?string $host=null):int
    {
        $columns=match($p){'http'=>['http'],'tls'=>['tls12','tls13'],'quic'=>['quic']};$score=0;
        {
            $hosts=$host!==null?[$host]:array_merge(...array_map(fn($s)=>NfqwsStrategyPickerGoals::DOMAINS[$s],NfqwsStrategyPickerGoals::selected($goal)));
            foreach($hosts as $h)foreach($columns as $column){
                $targets=array_values(array_filter(array_keys($o['runs'][0]['domains']??[]),fn($id)=>self::host($id)===$h));if(!$targets)continue;
                $ok=true;foreach($o['runs']as $run)foreach($targets as $id)$ok=$ok&&(($run['domains'][$id][$column]??null)===true);if($ok)$score++;
            }
        }
        return $score;
    }
    private static function controlValue(array $row,string $protocol,?string $host):int
    {
        if($host!==null)return self::value($row,$protocol,'all',$host);
        $columns=match($protocol){'http'=>['http'],'tls'=>['tls12','tls13','tcp'],'quic'=>['quic']};$score=0;
        foreach($columns as $column)$score+=min(array_map(fn($r)=>(int)($r['metrics'][$column]['ok']??0),$row['runs']));
        return $score;
    }
    private static function selectionValue(array $row,string $protocol,string $goal,?string $host,bool $customOnly):array
    {
        $control=self::controlValue($row,$protocol,$host);
        $value=$customOnly?$control:self::value($row,$protocol,$goal,$host);
        if($protocol==='tls'&&isset($row['custom_minimum'])){
            $root=0;$responded=0;$selected=$host===null;
            foreach($row['custom_minimum']['cells']as $cell)if($host===null||$cell['host']===$host){
                $selected=true;$root+=(int)$cell['root_ok'];$responded+=(int)$cell['responded'];
            }
            if($goal==='all'&&!$customOnly&&$host===null)$control+=$root;
            else $value=$customOnly&&$selected?$root:$value+$root;
            $control+=$responded;
        }
        return [$value,$control];
    }
    private static function selectBase(array $o,string $goal,bool $customOnly):array
    {
        $recipe=self::blank();$selected=[];
        foreach(['http','tls','quic']as $p){
            $best=-1;$control=-1;$index=0;$cost=PHP_INT_MAX;
            // Equal goal results are not equal measurements when measured
            // control results differ. Preserve coverage before minimizing work.
            foreach($o as $i=>$row){[$v,$g]=self::selectionValue($row,$p,$goal,null,$customOnly);$c=self::componentCost($p,$row['recipe'][$p]);if($v>$best||$v===$best&&($g>$control||$g===$control&&$c<$cost)){$best=$v;$control=$g;$index=$i;$cost=$c;}}
            $recipe[$p]=$o[$index]['recipe'][$p];$selected[$p]=$index;
        }
        return [$recipe,$selected];
    }
    public static function assemble(array $observations,string $goal='all',int $maxRules=24,bool $customOnly=false):array
    {
        if($maxRules<1||$maxRules>24)self::bad();
        $goal=NfqwsStrategyPickerGoals::parse($goal);$o=self::usable($observations);
        if(!$o)return self::blank();
        if($customOnly&&!isset($o[0]['custom_minimum']))throw new RuntimeException('incomparable_result');
        [$recipe,$selected]=self::selectBase($o,$goal,$customOnly);
        $mixed=($o[0]['custom_runs'][0]['schema_version']??null)===2;
        $ips=[];$customScope=null;
        if($mixed){
            $manifest=$o[0]['custom_manifest'];
            foreach($manifest['targets']as $target)if($target['kind']==='ipv4')$ips[]=$target['host'];
            $customScope=['manifest'=>$manifest,'manifest_sha256'=>hash('sha256',self::encode($manifest)),
                'protected_domains'=>self::protectedDomains($manifest,array_merge(array_keys($o[0]['runs'][0]['domains']??[]),$o[0]['runs'][0]['probe_hosts']??[]))];
        }
        // Specific rules precede ordinary AUTO fallback. They carry their own
        // domain restriction; global include/auto lists must not be unioned in.
        $scope=array_merge(array_keys($o[0]['runs'][0]['domains']??[]),$mixed?($o[0]['runs'][0]['probe_hosts']??[]):[],$o[0]['custom_minimum']['hosts']??[]);
        $hosts=array_values(array_unique(array_filter(array_map([self::class,'host'],$scope))));
        usort($hosts,fn($a,$b)=>strlen($a)<=>strlen($b)?:strcmp($a,$b));$overrides=[];$desired=[];
        foreach($hosts as $host){
            foreach(['http','tls','quic']as $p){
                $index=$selected[$p];[$best,$control]=self::selectionValue($o[$index],$p,'all',$host,$customOnly);$wanted=$index;
                foreach($o as $i=>$row){[$v,$g]=self::selectionValue($row,$p,'all',$host,$customOnly);if($v>$best||$v===$best&&$g>$control){$best=$v;$control=$g;$wanted=$i;}}
                $desired[$p][$host]=$o[$wanted]['recipe'][$p];
            }
        }
        foreach(['http','tls','quic']as $p){
            $needed=[];
            foreach($hosts as $host){
                $inherited=$recipe[$p];$length=0;
                foreach($needed as $parent=>$component)if(strlen($parent)>$length&&str_ends_with($host,'.'.$parent)){
                    $length=strlen($parent);$inherited=$component;
                }
                if($mixed&&$p==='tls'&&$length===0||self::component($p,$desired[$p][$host])!==self::component($p,$inherited))$needed[$host]=$desired[$p][$host];
            }
            // Emit leaf exceptions first. Equal unrelated leaves share a rule;
            // a parent/child/grandchild A/B/A chain must stay in three layers.
            while($needed){
                $ready=[];
                foreach($needed as $host=>$component){
                    $leaf=true;foreach($needed as $child=>$_)if($child!==$host&&str_ends_with($child,'.'.$host)){$leaf=false;break;}
                    if($leaf)$ready[$host]=$component;
                }
                if(!$ready)self::bad();$groups=[];
                foreach($ready as $host=>$component){$key=self::component($p,$component);$groups[$key]??=['component'=>$component,'domains'=>[]];$groups[$key]['domains'][]=$host;unset($needed[$host]);}
                foreach($groups as $group)foreach(array_chunk($group['domains'],128)as $domains){
                    $overrides[]=['protocol'=>$p,'domains'=>$domains,'component'=>$group['component']];
                    if(count($overrides)+($mixed?2:0)>$maxRules)throw new RuntimeException('synthesis_rule_limit');
                }
            }
        }
        if($mixed){
            $groups=[];
            foreach($ips as $ip){
                $wanted=$selected['tls'];[$best,$control]=self::selectionValue($o[$wanted],'tls','all',$ip,$customOnly);
                foreach($o as $i=>$row){[$v,$g]=self::selectionValue($row,'tls','all',$ip,$customOnly);
                    if($v>$best||$v===$best&&$g>$control){$best=$v;$control=$g;$wanted=$i;}}
                $component=$o[$wanted]['recipe']['tls'];$key=self::component('tls',$component);
                $groups[$key]??=['component'=>$component,'addresses'=>[]];$groups[$key]['addresses'][]=$ip;
            }
            foreach($groups as $group){
                $overrides[]=['protocol'=>'tls','addresses'=>$group['addresses'],'component'=>$group['component']];
                if(count($overrides)+2>$maxRules)throw new RuntimeException('synthesis_rule_limit');
            }
            $recipe['custom_scope']=$customScope;
        }
        $recipe['overrides']=$overrides;self::compile($recipe);return $recipe;
    }
    /** Recipes selected by past measurements still require fresh repeated
     * trials. These rows grant neither export nor Apply authority. */
    public static function bestForRetest(array $observations,string $goal='all',bool $customOnly=false,int $limit=4):array
    {
        if($limit<1||$limit>4)self::bad();
        $rows=self::usable($observations);if(!$rows)return [];
        [, $indices]=self::selectBase($rows,NfqwsStrategyPickerGoals::parse($goal),$customOnly);
        $out=[];$seen=[];$blank=self::key(self::blank());
        // Keep measured per-site exceptions as well as protocol-wide leaders.
        $recipes=[self::assemble($rows,$goal,24,$customOnly)];
        foreach($indices as $i)$recipes[]=$rows[$i]['recipe'];
        foreach($recipes as $recipe){$key=self::key($recipe);$zero=$blank;
            // The mixed-target pass-through includes explicit scoped pass
            // rules. It remains a control, never a leader that overwrites it.
            if(isset($recipe['custom_scope']))$zero=self::key(self::forTargets(self::blank(),
                $recipe['custom_scope']['manifest'],$recipe['custom_scope']['protected_domains']));
            if($key!==$zero&&!isset($seen[$key])){$out[]=$recipe;$seen[$key]=true;}if(count($out)>=$limit)break;}
        return $out;
    }
    public static function refine(array $observations,array $budget,string $goal='all',bool $customOnly=false):array
    {
        $o=self::usable($observations);if(!$o)return [];
        [$base]=self::selectBase($o,NfqwsStrategyPickerGoals::parse($goal),$customOnly);
        $seen=[];$groups=['http'=>[],'tls'=>[],'quic'=>[]];$protocol='http';$max=min(6,max(1,(int)($budget['max_repeats']??4)));
        foreach($o as $row)$seen[self::key($row['recipe'])]=true;
        $add=function($r)use(&$groups,&$protocol,&$seen){$key=self::key($r);if(!isset($seen[$key])){$groups[$protocol][]=$r;$seen[$key]=true;}};
        // Compose observed protocol leaders, then vary one protocol at a time.
        foreach(self::components('http',$budget)as $component){$r=$base;$r['http']=$component;$add($r);}
        $method=$base['http']['method'];
        if(in_array($method,['multisplit','multidisorder'],true))foreach(self::POSITIONS as $pos){$r=$base;$r['http']['pos']=$pos;$add($r);}
        if(!in_array($method,['pass','syndata','send'],true))foreach(['seq','ack','badsum','md5','ts']as $fool){$r=$base;$r['http']['fooling']=$fool;if(!in_array($method,['fake','tls_client_hello_clone'],true))$r['http']['fake']=true;$r['http']['repeats']=min(2,$max);$add($r);}
        $protocol='tls';foreach(self::components('tls',$budget)as $component){$r=$base;$r['tls']=$component;$add($r);}$method=$base['tls']['method'];
        if(in_array($method,['multisplit','multidisorder','fakedsplit','fakeddisorder'],true))foreach(self::POSITIONS as $pos){$r=$base;$r['tls']['pos']=$pos;$add($r);}
        if(!in_array($method,['pass','syndata','send'],true))foreach(['seq','ack','badsum','md5','ts']as $fool){$r=$base;$r['tls']['fooling']=$fool;if(in_array($method,['multisplit','multidisorder'],true))$r['tls']['fake']=true;$r['tls']['repeats']=min(2,$max);$add($r);}
        foreach(['fakeddisorder','hostfakesplit','multidisorder']as $family){$r=$base;$r['tls']=['method'=>$family,'fooling'=>'seq','fake'=>true,'repeats'=>min(2,$max)];$add($r);}
        $protocol='quic';
        foreach(self::components('quic',$budget)as $component){$r=$base;$r['quic']=$component;$add($r);}
        foreach([1,2,3,4,5,6]as $repeat)if($repeat<=$max){$r=$base;$r['quic']=['method'=>'fake','repeats'=>$repeat];$add($r);}
        foreach($groups as &$rows)usort($rows,fn($a,$b)=>self::cost($a)<=>self::cost($b));unset($rows);$out=[];
        for($i=0;$i<max(array_map('count',$groups));$i++)foreach($groups as $rows)if(isset($rows[$i]))$out[]=$rows[$i];
        return $out;
    }
}
