<?php
require_once __DIR__.'/platform.php';
require_once __DIR__.'/import-config.php';
require_once __DIR__.'/resource-paths.php';
require_once __DIR__.'/share-read.php';

final class NfqwsStrategyPickerMode
{
    public static function read(string $raw):string
    {
        $v=AsusImportConfig::parse($raw);$extra=$v['NFQWS_EXTRA_ARGS']??'';
        foreach(['MODE_AUTO'=>'auto','MODE_LIST'=>'list','MODE_ALL'=>'all']as $key=>$mode)if(isset($v[$key])&&$extra===$v[$key])return $mode;
        if(preg_match('/(?:^|\s)--hostlist-auto(?:=|\s)/',$extra))return 'auto';
        if(preg_match('/(?:^|\s)--hostlist(?:=|\s)/',$extra))return 'list';
        return 'all';
    }
}

/** Fixed services from the native domain test; no URL or shell input. */
final class NfqwsStrategyPickerGoals
{
    public const DOMAINS=[
        'youtube'=>['youtube.com','www.youtube.com'],
        'discord'=>['discord.com','gateway.discord.gg','media.discordapp.net'],
        'instagram'=>['instagram.com','www.instagram.com'],
        'torrents'=>['nnmclub.to','rutracker.org','rutor.info','tapochek.net'],
    ];
    public static function parse(string $value):string
    {
        if($value==='all')return $value;$parts=explode(',',$value);
        if(!$parts||count($parts)>count(self::DOMAINS)||count(array_unique($parts))!==count($parts))throw new RuntimeException('invalid_request');
        foreach($parts as $part)if(!isset(self::DOMAINS[$part]))throw new RuntimeException('invalid_request');
        return implode(',',array_values(array_intersect(array_keys(self::DOMAINS),$parts)));
    }
    public static function probeDomains(array $stock,string $goal):array
    {
        $goal=self::parse($goal);
        $primary=array_merge(...array_map(fn($s)=>self::DOMAINS[$s],self::selected($goal)));
        return array_values(array_unique(array_merge($primary,$stock)));
    }
    public static function selected(string $goal):array
    {
        $goal=self::parse($goal);
        return $goal==='all'?array_keys(self::DOMAINS):explode(',',$goal);
    }
    public static function service(string $domain):?string
    {
        foreach(self::DOMAINS as $service=>$hosts)if(in_array(strtolower($domain),$hosts,true))return $service;return null;
    }
}

/** Canonical work identity; raw URLs are never persisted in the journal. */
final class NfqwsStrategyPickerRequest
{
    public static function rounds(mixed $value):int
    {
        if(!is_string($value)||!preg_match('/^(?:[1-9]|10)$/D',$value))throw new RuntimeException('invalid_request');
        return (int)$value;
    }
    public static function custom(string $text,string $only):array
    {
        if(!in_array($only,['0','1'],true))throw new RuntimeException('invalid_request');
        require_once __DIR__.'/strategy-picker-targets.php';$targets=NfqwsStrategyPickerTargets::inspectMixed($text);
        if(!$targets['valid'])throw new RuntimeException('invalid_custom_targets');
        $hosts=$targets['hosts'];sort($hosts,SORT_STRING);return ['hosts'=>$hosts,'only'=>$only==='1'];
    }
    public static function selection(bool $extended,string $goal,bool $synthesis,?array $custom=null,mixed $concurrency='auto',mixed $rounds='1'):array
    {
        $selection=['search'=>$synthesis?'synthesis':'profiles','extended'=>$extended,'goal'=>NfqwsStrategyPickerGoals::parse($goal)];
        $concurrency=NfqwsStrategyPickerConcurrency::parse($concurrency);
        // Omit the default so historical AUTO journals retain their digest.
        if($concurrency!=='auto')$selection['concurrency']=$concurrency;
        $rounds=self::rounds($rounds);if(!$synthesis&&$rounds!==1)throw new RuntimeException('invalid_request');
        if($rounds>1)$selection['rounds']=$rounds;
        if($extended&&$synthesis)throw new RuntimeException('invalid_request');
        if($custom===null)return $selection;
        $keys=array_keys($custom);sort($keys);
        if(!$synthesis||$keys!==['hosts','only']||!is_bool($custom['only'])||
            !is_array($custom['hosts'])||!array_is_list($custom['hosts'])||count($custom['hosts'])<1||count($custom['hosts'])>10||
            $custom['only']&&$selection['goal']!=='all')throw new RuntimeException('invalid_request');
        foreach($custom['hosts']as $host)if(!is_string($host))throw new RuntimeException('invalid_request');
        // Canonical INTERNAL selection can carry mixed targets. The separate
        // raw HTTP custom()/preview boundary remains domain-only until UI and
        // complete export/restore integration are ready.
        require_once __DIR__.'/strategy-picker-targets.php';$targets=NfqwsStrategyPickerTargets::inspectMixed(implode("\n",$custom['hosts']));
        if(!$targets['valid']||$targets['hosts']!==$custom['hosts'])throw new RuntimeException('invalid_request');
        $hosts=$targets['hosts'];sort($hosts,SORT_STRING);
        $selection+=['custom_hosts'=>$hosts,'custom_only'=>$custom['only']];
        if(($targets['schema_version']??null)===2){
            $canonical=NfqwsStrategyPickerTargets::inspectMixed(implode("\n",$hosts));
            $selection+=['custom_target_policy'=>$canonical['target_policy_version'],'custom_targets'=>$canonical['targets']];
        }
        return $selection;
    }
    public static function assertTargetIdentity(array $job,array $selection):void
    {
        foreach(['custom_target_policy','custom_targets']as $key)
            if(array_key_exists($key,$job)!==array_key_exists($key,$selection)||
                array_key_exists($key,$selection)&&$job[$key]!==$selection[$key])throw new RuntimeException('invalid_request');
    }
    public static function digest(array $selection):string
    {
        $policy=null;if(isset($selection['custom_hosts'])){require_once __DIR__.'/idna.php';$policy=NfqwsIdna::POLICY;}
        $mixed=false;
        if(is_array($selection['custom_hosts']??null)){
            require_once __DIR__.'/strategy-picker-targets.php';
            foreach($selection['custom_hosts']as $host)if(!is_string($host))throw new RuntimeException('invalid_request');
            $mixed=(NfqwsStrategyPickerTargets::inspectMixed(implode("\n",$selection['custom_hosts']))['schema_version']??null)===2;
        }
        if($mixed||array_key_exists('custom_target_policy',$selection)||array_key_exists('custom_targets',$selection)){
            $canonical=self::selection($selection['extended']??false,$selection['goal']??'',($selection['search']??null)==='synthesis',
                ['hosts'=>$selection['custom_hosts']??null,'only'=>$selection['custom_only']??null],$selection['concurrency']??'auto',(string)($selection['rounds']??1));
            if($canonical!==$selection||!isset($canonical['custom_targets']))throw new RuntimeException('invalid_request');
            return hash('sha256',json_encode([2,$policy,$canonical['custom_target_policy'],$canonical],JSON_THROW_ON_ERROR));
        }
        return hash('sha256',json_encode([1,$policy,$selection],JSON_THROW_ON_ERROR));
    }
    public static function retry(?array $old,string $request,array $selection):bool
    {
        if(($old['request_id']??null)!==$request)return false;
        try{
            if(!is_bool($old['extended']??null)||!in_array($old['search']??null,['synthesis','profiles'],true)||!is_string($old['goal']??null))
                throw new RuntimeException('request_conflict');
            $custom=null;
            if(array_key_exists('custom_hosts',$old)||array_key_exists('custom_only',$old))
                $custom=['hosts'=>$old['custom_hosts']??null,'only'=>$old['custom_only']??null];
            $previous=self::selection($old['extended'],$old['goal'],$old['search']==='synthesis',$custom,
                array_key_exists('concurrency',$old)?$old['concurrency']:'auto',(string)($old['rounds']??1));
            self::assertTargetIdentity($old,$previous);
            $digest=self::digest($previous);
            if(isset($old['selection_sha256'])&&$old['selection_sha256']!==$digest||self::digest($selection)!==$digest)
                throw new RuntimeException('request_conflict');
            return true;
        }catch(Throwable $e){throw new RuntimeException('request_conflict',0,$e);}
    }
}

/** A request-pool ceiling for one strategy, never a hardware capacity claim. */
final class NfqwsStrategyPickerConcurrency
{
    public const VERSION='picker-concurrency-v1';
    public static function parse(mixed $value):string
    {
        require_once __DIR__.'/dpi-load-policy.php';
        if(!is_string($value)||$value!=='auto'&&(!preg_match('/^[1-9][0-9]{0,6}$/D',$value)||
            (int)$value>AsusDpiLoadPolicy::REQUEST_MAX))throw new RuntimeException('invalid_request');
        return $value;
    }
    private static function facts(array $facts):array
    {
        $cores=$facts['cores']??null;$memory=$facts['available_kib']??null;$fd=$facts['fd_soft']??null;
        if(!is_int($cores)||$cores<1||!is_int($memory)||$memory<1||$memory>2147483647)
            throw new RuntimeException('unsupported_runtime');
        if($fd!==null&&(!is_int($fd)||$fd<0||$fd>2147483647))throw new RuntimeException('unsupported_runtime');
        return [$cores,$memory,$fd];
    }
    public static function plan(mixed $requested,array $automatic,array $facts):array
    {
        $requested=self::parse($requested);$pool=$automatic['concurrency']??null;
        if(!is_int($pool)||$pool<1||$pool>AsusDpiLoadPolicy::REQUEST_MAX)throw new RuntimeException('invalid_request');
        $result=['policy_version'=>self::VERSION,'requested'=>$requested,'effective'=>$pool,'budget'=>$automatic,'admission'=>null];
        // Preserve legacy budgets and their fallback behaviour byte for byte.
        if($requested==='auto')return $result;
        [$cores,$memory,$fd]=self::facts($facts);$pool=(int)$requested;
        $load=$automatic['load']??null;
        if((!is_int($load)&&!is_float($load))||!is_finite((float)$load)||$load<0)
            throw new RuntimeException('unsupported_runtime');
        $budget=NfqwsStrategyPickerBudget::choose($cores,$memory,(float)$load);
        $admission=AsusDpiLoadPolicy::plan($pool,$cores,$memory,$fd);
        if(!$admission['available'])throw new RuntimeException($admission['code']);
        $budget['concurrency']=$pool;$count=$automatic['domain_count']??35;
        if(!is_int($count)||$count<1||$count>256)throw new RuntimeException('invalid_request');
        try{$budget=NfqwsStrategyPickerBudget::coverDomains($budget,$count);}
        catch(RuntimeException $e){throw new RuntimeException('concurrency_budget_unavailable',0,$e);}
        return array_replace($result,['effective'=>$pool,'budget'=>$budget,'admission'=>$admission+
            ['cores'=>$cores,'available_kib'=>$memory,'fd_soft'=>$fd]]);
    }
    public static function assertRuntime(array $choice,array $facts,bool $launch):void
    {
        $requested=self::parse($choice['requested']??null);$pool=$choice['effective']??null;
        if(($choice['policy_version']??null)!==self::VERSION||!is_int($pool)||$pool<1||$pool>AsusDpiLoadPolicy::REQUEST_MAX||
            $requested!=='auto'&&$pool!==(int)$requested)throw new RuntimeException('invalid_request');
        if($requested==='auto')return;
        [$cores,$memory,$fd]=self::facts($facts);
        // Keep live observations valid without interpreting them as a measured
        // hardware limit. Native errors and restoration are handled normally.
    }
    public static function readFacts():array
    {
        require_once __DIR__.'/dpi-load-policy.php';
        return ['cores'=>AsusDpiLoadPolicy::cores((string)@file_get_contents('/proc/stat',false,null,0,1048577)),
            'available_kib'=>AsusDpiLoadPolicy::availableMemoryKiB((string)@file_get_contents('/proc/meminfo',false,null,0,131072)),
            'fd_soft'=>AsusDpiLoadPolicy::fileDescriptors((string)@file_get_contents('/proc/self/limits',false,null,0,131072))];
    }
    public static function record(array $plan):array
    {
        return array_intersect_key($plan,array_flip(['policy_version','requested','effective','admission']));
    }
    public static function binding(array $selection,array $budget,array $choice,string $config,string $resources,string $boot):string
    {
        foreach([$config,$resources,$boot]as $hash)if(!preg_match('/^[a-f0-9]{64}$/D',$hash))throw new RuntimeException('invalid_request');
        // Resource jitter is expected. Bind eligibility and the complete time
        // budget, rather than invalidating consent on each free-RAM fluctuation.
        unset($budget['available_kib'],$budget['load']);
        unset($choice['admission']['available_kib']);
        return hash('sha256',json_encode(['picker-start-plan-v1',$selection,$budget,$choice,$config,$resources,$boot],JSON_THROW_ON_ERROR));
    }
    private static function selection(array $job,string $requested):array
    {
        if(!is_bool($job['extended']??null)||!in_array($job['search']??null,['profiles','synthesis'],true)||
            !is_string($job['goal']??null))throw new RuntimeException('invalid_request');
        $custom=null;
        if(array_key_exists('custom_hosts',$job)||array_key_exists('custom_only',$job))
            $custom=['hosts'=>$job['custom_hosts']??null,'only'=>$job['custom_only']??null];
        $selection=NfqwsStrategyPickerRequest::selection($job['extended'],$job['goal'],$job['search']==='synthesis',$custom,$requested,(string)($job['rounds']??1));
        NfqwsStrategyPickerRequest::assertTargetIdentity($job,$selection);return $selection;
    }
    /** Reconstruct the admitted budget, without requiring today's free RAM for
     * an already completed report. Missing metadata means historical AUTO. */
    public static function job(array $job):?array
    {
        try{
            $requested=self::parse(array_key_exists('concurrency',$job)?$job['concurrency']:'auto');
            if(!array_key_exists('concurrency_choice',$job)){
                if($requested!=='auto')throw new RuntimeException('invalid_request');
                if(array_key_exists('custom_target_policy',$job)||array_key_exists('custom_targets',$job))throw new RuntimeException('invalid_request');
                if(array_key_exists('custom_hosts',$job)){
                    require_once __DIR__.'/strategy-picker-targets.php';
                    if(!is_array($job['custom_hosts'])||!array_is_list($job['custom_hosts']))throw new RuntimeException('invalid_request');
                    foreach($job['custom_hosts']as $host)if(!is_string($host))throw new RuntimeException('invalid_request');
                    $legacy=NfqwsStrategyPickerTargets::inspect(implode("\n",$job['custom_hosts']));
                    if(!$legacy['valid']||$legacy['hosts']!==$job['custom_hosts'])throw new RuntimeException('invalid_request');
                }
                foreach($job['profiles']??[]as $profile)foreach($profile['runs']??[]as $run)
                    if(array_key_exists('request_pool',$run))throw new RuntimeException('invalid_request');
                if(array_key_exists('selection_sha256',$job)&&$job['selection_sha256']!==NfqwsStrategyPickerRequest::digest(self::selection($job,'auto')))
                    throw new RuntimeException('invalid_request');
                return null;
            }
            $choice=$job['concurrency_choice'];$keys=is_array($choice)?array_keys($choice):[];sort($keys);
            if($keys!==['admission','effective','policy_version','requested']||($choice['requested']??null)!==$requested)
                throw new RuntimeException('invalid_request');
            $budget=$job['budget']??null;$domains=$job['probe_domains']??null;
            if(!is_array($budget)||!is_int($budget['cores']??null)||$budget['cores']<1||
                !is_int($budget['available_kib']??null)||$budget['available_kib']<1||
                (!is_int($budget['load']??null)&&!is_float($budget['load']??null))||
                !is_finite((float)$budget['load'])||$budget['load']<0||
                !is_array($domains)||!array_is_list($domains)||!$domains||count($domains)>256)
                throw new RuntimeException('invalid_request');
            foreach($domains as $domain)if(!is_string($domain))throw new RuntimeException('invalid_request');
            if(count(array_unique($domains))!==count($domains))throw new RuntimeException('invalid_request');
            $selection=self::selection($job,$requested);
            if(($job['selection_sha256']??null)!==NfqwsStrategyPickerRequest::digest($selection))throw new RuntimeException('invalid_request');
            $automatic=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(
                $budget['cores'],$budget['available_kib'],(float)$budget['load']),count($domains));
            $plan=self::plan($requested,$automatic,is_array($choice['admission'])?$choice['admission']:[]);
            // Historical completed journals keep their exact old observation.
            // This compatibility check grants no new input or resource limit.
            if(($choice['admission']['memory_floor_kib']??null)===65536){
                $legacy=$plan['admission'];$legacy['memory_floor_kib']=65536;
                $left=$legacy;$right=$choice['admission'];ksort($left);ksort($right);
                if($left===$right)$plan['admission']=$legacy;
            }
            $expected=!isset($selection['custom_hosts'])?$plan['budget']:NfqwsStrategyPickerBudget::custom($plan['budget'],count($selection['custom_hosts']));
            // State JSON intentionally does not preserve a zero's float type.
            $expected=json_decode(json_encode($expected,JSON_THROW_ON_ERROR),true,32,JSON_THROW_ON_ERROR);
            $stored=json_decode(json_encode($budget,JSON_THROW_ON_ERROR),true,32,JSON_THROW_ON_ERROR);
            if($expected!==$stored||self::record($plan)!==$choice)throw new RuntimeException('invalid_request');
            return $choice;
        }catch(Throwable $e){throw new RuntimeException('invalid_request',0,$e);}
    }
    public static function verifyNative(array $job,array $native):void
    {
        $choice=self::job($job);
        if($choice!==null&&($native['settings']['config']['MAX_CONCURRENT']??null)!==$choice['effective'])
            throw new RuntimeException('incomparable_result');
    }
    public static function admit(array $job,bool $launch):void
    {
        $choice=self::job($job);
        if($choice!==null&&$choice['requested']!=='auto')self::assertRuntime($choice,self::readFacts(),$launch);
    }
    private static function evidence(array $choice):array
    {
        return array_intersect_key($choice,array_flip(['policy_version','requested','effective']));
    }
    public static function measure(array $job,array $native):array
    {
        self::verifyNative($job,$native);$score=NfqwsStrategyPickerScore::measure($native);$choice=self::job($job);
        if($choice!==null)$score['request_pool']=self::evidence($choice);
        return $score;
    }
    public static function verifyRuns(array $job,array $profiles):void
    {
        $choice=self::job($job);if($choice===null)return;$expected=self::evidence($choice);
        foreach($profiles as $profile){
            $runs=$profile['runs']??[];
            if(!is_array($runs)||!array_is_list($runs))throw new RuntimeException('incomparable_result');
            foreach($runs as $run)if(($run['request_pool']??null)!==$expected)throw new RuntimeException('incomparable_result');
        }
    }
}

final class NfqwsStrategyPickerBudget
{
    public const CUSTOM_LEAF_SECONDS=90;
    public const RESTORE_SECONDS=120;
    public const STOP_GRACE_SECONDS=90;
    public const RECOVERY_LOCK_SECONDS=90;
    private const MAX_CUSTOM_SECONDS=14400;
    /** Null is a source-created job with no overall duration cutoff.
     * Legacy jobs retain their original finite deadline. */
    public static function overallDeadline(array $job):?float
    {
        if(!array_key_exists('deadline',$job))throw new RuntimeException('stale_state');
        $end=$job['deadline'];
        if($end===null){
            $start=$job['started_uptime']??null;
            if((!is_int($start)&&!is_float($start))||!is_finite((float)$start)||$start<0)throw new RuntimeException('stale_state');
            return null;
        }
        if((!is_int($end)&&!is_float($end))||!is_finite((float)$end)||$end<0)throw new RuntimeException('stale_state');
        return (float)$end;
    }
    public static function customProbeSeconds(array $budget):int
    {
        $probe=$budget['probe_seconds']??null;
        if(!is_int($probe)||$probe<1||$probe>1800)throw new RuntimeException('invalid_request');
        // Native guard teardown, status publication and polling fit inside a
        // separately bounded wait; a lost native task cannot spend the job.
        return $probe+30;
    }
    public static function customTrialSeconds(array $budget,int $repeats,bool $warm,bool $prepare):int
    {
        if(!in_array($repeats,[1,2],true))throw new RuntimeException('invalid_request');
        return 3*60+($repeats+(int)$warm)*self::customProbeSeconds($budget)+self::CUSTOM_LEAF_SECONDS*($repeats+(int)$prepare);
    }
    public static function custom(array $budget,int $hosts):array
    {
        if($hosts<1||$hosts>10)throw new RuntimeException('invalid_request');
        if(!is_int($budget['available_kib']??null)||$budget['available_kib']<1)
            throw new RuntimeException('insufficient_memory');
        // Control, zero baseline, at least one exploratory trial and final
        // repeated verification must fit at their full bounds, not averages.
        $minimum=self::customTrialSeconds($budget,2,true,true)+self::customTrialSeconds($budget,2,false,false)+
            self::customTrialSeconds($budget,1,false,false)+self::customTrialSeconds($budget,2,true,false)+self::RESTORE_SECONDS;
        $deadline=(int)ceil(($minimum+60)/60)*60;
        return array_replace($budget,['deadline_seconds'=>$deadline,'custom'=>[
            'max_hosts'=>$hosts,'leaf_seconds'=>self::CUSTOM_LEAF_SECONDS,'restore_seconds'=>self::RESTORE_SECONDS,
            'minimum_exploratory_trials'=>1,'minimum_series_seconds'=>$minimum]]);
    }
    public static function guardIterations():int
    {
        // Each healthy/contended iteration sleeps at least one second. Keep
        // both independent recovery windows beyond the longest admitted job.
        return self::MAX_CUSTOM_SECONDS+self::STOP_GRACE_SECONDS+self::RECOVERY_LOCK_SECONDS+10+1;
    }
    public static function coverDomains(array $budget,int $count):array
    {
        if($count<1||$count>256)throw new RuntimeException('invalid_request');
        $group=max(240,(int)ceil($count*4*8/$budget['concurrency'])+60);
        if(2*$group+30>1800)throw new RuntimeException('invalid_request');
        return array_replace($budget,['group_seconds'=>$group,'probe_seconds'=>2*$group+30,'domain_count'=>$count]);
    }
    public static function choose(int $cores,int $availableKiB,float $load):array
    {
        if($availableKiB<1)throw new RuntimeException('unsupported_runtime');
        $small=$cores<2||$availableKiB<98304;$busy=$load>max(1,$cores)*0.8;
        $concurrency=$busy?2:($small?($cores>=2&&$availableKiB>=65536?4:2):10);
        // Full domain coverage includes four protocols per target. A small
        // worker pool needs more time, rather than silently truncating tests.
        $groupSeconds=max(240,(int)ceil(35*4*8/$concurrency)+60);
        return ['cores'=>max(1,$cores),'available_kib'=>$availableKiB,'load'=>$load,
            'concurrency'=>$concurrency,'max_profiles'=>$small?3:5,'max_repeats'=>$small||$busy?4:6,
            'group_seconds'=>$groupSeconds,'probe_seconds'=>2*$groupSeconds+30,
            'deadline_seconds'=>$small?3600:2700,'timeout'=>8,'small'=>$small,'busy'=>$busy];
    }
}

/** Expand only already validated methods; never invent Lua or shell operands. */
final class NfqwsStrategyPickerRecipes
{
    public static function expand(array $config,int $maxRepeats):array
    {
        $out=[];$seen=[];
        // Isolate protocol changes first, then try a bounded combination.
        // Custom service/game and generic UDP rules stay byte-for-byte intact.
        foreach([[2,null],[null,2],[4,4],[4,null],[null,4],[6,6]]as [$tcp,$quic]){
            if(max($tcp??0,$quic??0)>$maxRepeats)continue;$v=$config;$changed=false;$labels=[];
            foreach(['NFQWS_ARGS'=>$tcp,'NFQWS_ARGS_QUIC'=>$quic]as $key=>$repeats){
                if($repeats===null)continue;$old=$v[$key]??'';
                $v[$key]=preg_replace_callback('/(?<=:)repeats=([1-9][0-9]?)(?=[:\\s]|$)/',function($m)use($repeats,&$changed){if((int)$m[1]!==$repeats)$changed=true;return 'repeats='.$repeats;},$old);
                if($v[$key]!==$old)$labels[]=($key==='NFQWS_ARGS'?'TCP':'QUIC').' repeats='.$repeats;
            }
            if($changed){$sha=hash('sha256',json_encode($v));if(!isset($seen[$sha])){$out[]=['name'=>implode(' + ',$labels),'config'=>$v];$seen[$sha]=true;}}
        }
        return $out;
    }
}

/** Conservative comparisons: missing, changed or partial probes never win. */
final class NfqwsStrategyPickerScore
{
    public const PROTOCOLS=['tcp','http','tls12','tls13','quic'];
    public static function measure(array $native):array
    {
        if(($native['state']??null)!=='completed'||($native['context']['changed']??false))throw new RuntimeException('incomparable_result');
        $context=null;
        if(isset($native['context'])){
            $before=$native['context']['before']??null;$after=$native['context']['after']??null;
            if(!is_array($before)||!is_array($after)||$before!==$after)throw new RuntimeException('incomparable_result');
            if(array_key_exists('dns',$before)){
                $dns=$before['dns'];$keys=is_array($dns)?array_keys($dns):[];sort($keys);
                if($keys!==['schema_version','sha256','state']||$dns['schema_version']!==1||$dns['state']!=='known'||
                    !is_string($dns['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$dns['sha256']))throw new RuntimeException('incomparable_result');
            }
            $context=$before;ksort($context);
        }
        $groups=[];foreach($native['groups']??[]as $g)$groups[$g['group']]=$g['document']['results']??[];
        $domains=$groups[2]['domain_inspection']??null;$tcp=$groups[3]['tcp16']??null;
        if(!is_array($domains)||!is_array($tcp)||!$domains||!$tcp||count($domains)>256||count($tcp)>256)throw new RuntimeException('incomparable_result');
        if(($native['coverage']['domains']??null)!==count($domains)||($native['coverage']['tcp']??null)!==count($tcp))throw new RuntimeException('incomparable_result');
        $domainIds=array_map(fn($r)=>strtolower($r['domain']??''),$domains);$tcpIds=array_column($tcp,'id');
        if(count(array_unique($domainIds))!==count($domains)||count($tcpIds)!==count($tcp)||count(array_unique($tcpIds))!==count($tcp))throw new RuntimeException('incomparable_result');
        $m=array_fill_keys(self::PROTOCOLS,['ok'=>0,'total'=>0]);$targets=[];$youtube=null;$services=[];$rows=[];
        foreach($domains as $row){
            if(!is_string($row['domain']??null))throw new RuntimeException('incomparable_result');
            $targets[]=['domain',$row['domain']];$v=[];
            foreach(['http','tls12','tls13','quic']as $p){
                if(!is_string($row[$p]??null))throw new RuntimeException('incomparable_result');
                $ok=$row[$p]==='ok'||($p==='quic'&&$row[$p]==='quic_ok');$v[$p]=$ok;
                $excluded=in_array($row[$p],['unsupported','not_supported','quic_unsupported','skipped'],true);
                $rows[strtolower($row['domain'])][$p]=$excluded?null:$ok;
                $targets[]=['coverage',$row['domain'],$p,!$excluded];
                if(!$excluded){$m[$p]['total']++;if($ok)$m[$p]['ok']++;}
                $service=NfqwsStrategyPickerGoals::service($row['domain']);
                if($service!==null){
                    $services[$service]??=array_fill_keys(['http','tls12','tls13','quic'],['ok'=>0,'total'=>0]);
                    if(!$excluded){$services[$service][$p]['total']++;if($ok)$services[$service][$p]['ok']++;}
                }
            }
            if(in_array(strtolower($row['domain']),['youtube.com','www.youtube.com'],true))$youtube=$v;
        }
        $probeHosts=[];foreach($tcp as $row){
            if(!is_string($row['id']??null)||!is_string($row['status']??null))throw new RuntimeException('incomparable_result');
            $targets[]=['tcp',$row['id'],$row['ip']??null,$row['port']??null,$row['sni']??null];
            $m['tcp']['total']++;if($row['status']==='ok')$m['tcp']['ok']++;
            if(is_string($row['sni']??null)&&preg_match('/^[a-z0-9.-]{1,253}$/D',strtolower($row['sni'])))$probeHosts[]=strtolower($row['sni']);
        }
        if($youtube===null)throw new RuntimeException('youtube_not_tested');
        return ['metrics'=>$m,'youtube'=>$youtube,'services'=>$services,'domains'=>$rows,'probe_hosts'=>array_values(array_unique($probeHosts)),'context_sha256'=>hash('sha256',json_encode($context,JSON_THROW_ON_ERROR)),'targets'=>hash('sha256',json_encode([$targets,$native['settings']??[],$context],JSON_THROW_ON_ERROR))];
    }
    public static function compare(array $baseline,array $candidate,string $goal='all'):array
    {
        $goal=NfqwsStrategyPickerGoals::parse($goal);
        $no=fn($reason)=>['eligible'=>false,'reason'=>$reason,'gain'=>0];
        if(count($baseline)!==2||count($candidate)!==2)return $no('incomparable_result');
        $all=array_merge($baseline,$candidate);$target=$all[0]['targets']??null;
        foreach($all as $run)if(!is_string($target)||($run['targets']??null)!==$target)return $no('incomparable_result');
        if(in_array('torrents',explode(',',$goal),true))foreach($all as $run)foreach(NfqwsStrategyPickerGoals::DOMAINS['torrents']as $host){
            if(!is_array($run['domains'][$host]??null))return $no('incomparable_result');
        }
        foreach(['http','tls12','tls13','quic']as $p){
            $was=$baseline[0]['youtube'][$p]&&$baseline[1]['youtube'][$p];
            if($was&&(!$candidate[0]['youtube'][$p]||!$candidate[1]['youtube'][$p]))return $no('youtube_regression');
        }
        $gain=0;$min=[];
        foreach(self::PROTOCOLS as $p){
            $total=$baseline[0]['metrics'][$p]['total'];
            foreach($all as $run)if(($run['metrics'][$p]['total']??null)!==$total)return $no('incomparable_result');
            $a=min($baseline[0]['metrics'][$p]['ok'],$baseline[1]['metrics'][$p]['ok']);
            $b=min($candidate[0]['metrics'][$p]['ok'],$candidate[1]['metrics'][$p]['ok']);
            if(in_array($p,['tls12','tls13'],true)&&$b<$a)return $no('tls_regression');
            $gain+=$b-$a;$min[$p]=['ok'=>$b,'total'=>$total];
        }
        // Old reports can contain fewer named services. Validate every service
        // actually present in their baseline; fresh all-service probes include
        // the complete fixed set through probeDomains(). Never invent cells.
        $services=$goal==='all'?array_values(array_intersect(array_keys(NfqwsStrategyPickerGoals::DOMAINS),array_keys($baseline[0]['services']??[]))):explode(',',$goal);
        $selected=[];$serviceGain=0;
        if($services){
            foreach($services as $service)foreach(['http','tls12','tls13','quic']as $p){
                $total=$baseline[0]['services'][$service][$p]['total']??null;
                if(!is_int($total))return $no('incomparable_result');
                foreach($all as $run)if(($run['services'][$service][$p]['total']??null)!==$total||!is_int($run['services'][$service][$p]['ok']??null))return $no('incomparable_result');
                $a=min($baseline[0]['services'][$service][$p]['ok'],$baseline[1]['services'][$service][$p]['ok']);
                $b=min($candidate[0]['services'][$service][$p]['ok'],$candidate[1]['services'][$service][$p]['ok']);
                if($b<$a)return $no('goal_regression');
                $serviceGain+=$b-$a;$selected[$service][$p]=['ok'=>$b,'total'=>$total];
            }
            if($goal!=='all')return ['eligible'=>$serviceGain>0,'reason'=>$serviceGain>0?'improved':'goal_no_improvement','gain'=>$serviceGain,'minimum'=>$min,'selected'=>$selected,'goal'=>$goal];
        }
        return ['eligible'=>$gain>0,'reason'=>$gain>0?'improved':'no_improvement','gain'=>$gain,'minimum'=>$min]+($selected?['selected'=>$selected,'goal'=>$goal,'primary_gain'=>$serviceGain]:[]);
    }
}

/** One bounded persistent journal. Names and paths are never HTTP inputs. */
final class NfqwsStrategyPickerState
{
    private const BROWSER_START_SECONDS=45;
    private const BROWSER_IDLE_SECONDS=150;
    private const BROWSER_PHASES=['preparing','running','restoring'];

    private static function safe(string $directory,string $name,int $owner):string
    {return class_exists('NfqwsDeviceProfilesPaths',false)?NfqwsDeviceProfilesPaths::guard($directory,$name,$owner):NfqwsPlatform::guardFile($directory,$name,$owner);}
    public readonly string $configDirectory;
    public function __construct(public readonly string $root,private int $owner=0,?string $configDirectory=null)
    {$this->configDirectory=$configDirectory??NfqwsPlatform::settings()['config'];}
    public function owner():int{return $this->owner;}
    public function profileRoot(string $jobId):string
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$jobId))throw new RuntimeException('source_changed');
        return $this->configDirectory.'/strategy-picker/'.$jobId;
    }
    /** Both the measurement and its optional diagnostic read the same job library. */
    public function profileLibrary(array $job):NfqwsDeviceProfilesLibrary
    {
        if(isset($job['library_namespace'])&&$job['library_namespace']!=='job-v1')throw new RuntimeException('invalid_state');
        $base=$this->profileRoot($job['id']??'');
        $private=isset($job['library_namespace'])?$this->root.'/job-'.$job['id']:$this->root;
        return new NfqwsDeviceProfilesLibrary($private,$base,$this->configDirectory,$this->owner);
    }
    /** Round journals and samples share one job-bound namespace. Historical
     * series keep their original paths; no old archive is migrated or reused. */
    public function round(int $number):self
    {
        $j=$this->read();$id=$j['id']??null;$series=$j['series']??null;
        $total=NfqwsStrategyPickerRequest::rounds((string)($j['rounds']??1));
        $version=$series['archive_version']??1;
        if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id)||!is_array($series)||
            ($series['total']??null)!==$total||$number<1||$number>$total||
            !in_array($version,[1,2],true))throw new RuntimeException('source_changed');
        return new self($this->root.'/round-'.($version===2?$id.'-':'').$number,$this->owner,$this->configDirectory);
    }
    public function path(string $name):string
    {
        if(!in_array($name,['state.json','browser.json','engine.lock','actor-work.json','actor-guard.json','failure-work.json','failure-guard.json','winner-auto.json','generated-auto.json'],true)&&!preg_match('/^(?:result-[a-f0-9]{32}\.json|\.stage-[a-f0-9]{16}|cancel-[a-f0-9]{32}|unused-(?:work|guard)-[a-f0-9]{32}\.pid)$/D',$name))throw new RuntimeException('invalid_request');
        if(!file_exists($this->root)){
            self::safe(dirname($this->root),basename($this->root),$this->owner);
            $mask=umask(0077);try{if(!mkdir($this->root,0700))throw new RuntimeException('storage_unavailable');}finally{umask($mask);}
            self::syncDirectory(dirname($this->root),$this->owner);
        }
        return self::safe($this->root,$name,$this->owner);
    }
    private $journalLock=null;
    /** Serialize the short read/publication, never the whole worker lifetime. */
    private function journal(callable $fn):mixed
    {
        if(is_resource($this->journalLock))return $fn();
        $directory=dirname($this->path('state.json'));$fields=array_flip(['dev','ino','uid','gid','mode']);
        clearstatcache(true,$directory);$before=@lstat($directory);$f=@fopen($directory,'rbe');
        if(!$before||!is_resource($f))throw new RuntimeException('storage_unavailable');
        try{
            if(!flock($f,LOCK_EX))throw new RuntimeException('storage_unavailable');
            self::safe($directory,'.picker-sync-check',$this->owner);clearstatcache(true,$directory);$named=@lstat($directory);
            $identity=array_intersect_key($before,$fields);
            if(!$named||array_intersect_key(fstat($f),$fields)!==$identity||array_intersect_key($named,$fields)!==$identity)throw new RuntimeException('source_changed');
            $this->journalLock=$f;$result=$fn();
            self::safe($directory,'.picker-sync-check',$this->owner);clearstatcache(true,$directory);$named=@lstat($directory);
            if(!$named||array_intersect_key(fstat($f),$fields)!==$identity||array_intersect_key($named,$fields)!==$identity)throw new RuntimeException('source_changed');
            return $result;
        }finally{$this->journalLock=null;flock($f,LOCK_UN);fclose($f);}
    }
    public function read(string $name='state.json',?array &$pin=null):?array
    {
        $pin=null;return $this->journal(function()use($name,&$pin):?array{
            $file=$this->buffer($name);if(!$file)return null;
            $v=json_decode($file['raw'],true,32,JSON_THROW_ON_ERROR);
            if(!is_array($v))throw new RuntimeException('storage_unavailable');$pin=$file['pin'];return $v;
        });
    }
    public function openBrowser(array $job):void
    {
        $this->write([
            'job'=>$job['id'],
            'window'=>$job['window_id'],
            'state'=>'waiting',
            'until'=>AsusUpdateStore::uptime()+self::BROWSER_START_SECONDS,
        ],'browser.json');
    }
    private function browserRecord(array $job):?array
    {
        $record=$this->read('browser.json');
        if(($record['job']??null)!==$job['id']||($record['window']??null)!==$job['window_id']||
            !in_array($record['state']??null,['waiting','present'],true)||
            !is_numeric($record['until']??null)||AsusUpdateStore::uptime()>=$record['until'])return null;
        return $record;
    }
    public function browserState(array $job):string
    {
        if(!isset($job['window_id'])||!in_array($job['state'],self::BROWSER_PHASES,true))return 'present';
        return $this->browserRecord($job)['state']??'closed';
    }
    public function updateBrowser(string $request,string $window,bool $closed):bool
    {
        return $this->journal(function()use($request,$window,$closed):bool{
            $job=$this->read();
            if(($job['request_id']??null)!==$request||($job['window_id']??null)!==$window||
                !in_array($job['state']??null,self::BROWSER_PHASES,true)||$job['boot']!==AsusUpdateStore::boot())return false;
            $record=$this->browserRecord($job);
            if($record===null)return false;
            $record['state']=$closed?'closed':'present';
            $record['until']=$closed?0:AsusUpdateStore::uptime()+self::BROWSER_IDLE_SECONDS;
            $this->writeHeld($record,'browser.json',$pin);
            return true;
        });
    }
    private static function signature(array $s):array
    {return array_intersect_key($s,array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));}
    private static function syncDirectory(string $directory,int $owner):void
    {
        self::safe($directory,'.picker-sync-check',$owner);clearstatcache(true,$directory);$before=@lstat($directory);
        if(!$before||($before['mode']&0170000)!==0040000)throw new RuntimeException('source_changed');
        $f=@fopen($directory,'r');if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(self::signature(fstat($f))!==self::signature($before))throw new RuntimeException('source_changed');
            if(!fsync($f))throw new RuntimeException('storage_unavailable');
            self::safe($directory,'.picker-sync-check',$owner);clearstatcache(true,$directory);$after=@lstat($directory);
            if(!$after||self::signature(fstat($f))!==self::signature($before)||self::signature($after)!==self::signature($before))throw new RuntimeException('source_changed');
        }finally{fclose($f);}
    }
    /** Same bounded guarded bytes and named inode around every writer check. */
    private function buffer(string $name):?array
    {
        $path=$this->path($name);clearstatcache(true,$path);$before=@lstat($path);if(!$before)return null;
        if(($before['mode']&0177777)!==0100600||$before['uid']!==$this->owner||$before['nlink']!==1||$before['size']>1048576)throw new RuntimeException('source_changed');
        $f=@fopen($path,'rbe');if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(self::signature(fstat($f))!==self::signature($before))throw new RuntimeException('source_changed');
            $raw=stream_get_contents($f,1048577);$this->path($name);clearstatcache(true,$path);$after=@lstat($path);
            if(!is_string($raw)||strlen($raw)!==$before['size']||!$after||self::signature(fstat($f))!==self::signature($before)||self::signature($after)!==self::signature($before))throw new RuntimeException('source_changed');
            return ['raw'=>$raw,'pin'=>self::signature($before)];
        }finally{fclose($f);}
    }
    public function write(array $v,string $name='state.json',?array &$observedPin=null):void
    {
        $this->journal(function()use($v,$name,&$observedPin):void{$this->writeHeld($v,$name,$observedPin);});
    }
    /** A measured program keeps its own AUTO/sample snapshot after later trials.
     * Publication uses the existing bounded writer and never replaces a result. */
    public function createMeasuredResult(array $value):array
    {
        return $this->journal(function()use($value):array{
            $job=$this->read();$id=$value['job_id']??null;
            if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id)||($job['id']??null)!==$id)
                throw new RuntimeException('source_changed');
            $value['version']='picker-measured-result-v1';$token=bin2hex(random_bytes(16));$name='result-'.$token.'.json';
            $target=$this->measuredStore($id);
            return $target->journal(function()use($target,$name,$value,$token):array{
                if($target->buffer($name)!==null)throw new RuntimeException('source_changed');
                $target->writeHeld($value,$name,$pin);$file=$target->buffer($name);
                if($file===null||$file['pin']!==$pin)throw new RuntimeException('source_changed');
                return ['id'=>$token,'sha256'=>hash('sha256',$file['raw'])];
            });
        });
    }
    /** The existing per-job library/history namespace also owns its results. */
    private function measuredStore(string $job):self
    {return basename($this->root)==='job-'.$job?$this:new self($this->root.'/job-'.$job,$this->owner,$this->configDirectory);}
    public function measuredResult(array $reference,string $job):array
    {
        $keys=array_keys($reference);sort($keys);
        if($keys!==['id','sha256']||!is_string($reference['id'])||!preg_match('/^[a-f0-9]{32}$/D',$reference['id'])||
            !is_string($reference['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$reference['sha256'])||!preg_match('/^[a-f0-9]{32}$/D',$job))
            throw new RuntimeException('invalid_request');
        return $this->journal(function()use($reference,$job):array{
            if(($this->read()['id']??null)!==$job)throw new RuntimeException('source_changed');
            $target=$this->measuredStore($job);
            $file=$target->journal(fn()=>$target->buffer('result-'.$reference['id'].'.json'));
            if($file===null||!hash_equals($reference['sha256'],hash('sha256',$file['raw'])))throw new RuntimeException('source_changed');
            $value=json_decode($file['raw'],true,32,JSON_THROW_ON_ERROR);
            if(!is_array($value)||($value['version']??null)!=='picker-measured-result-v1'||($value['job_id']??null)!==$job)
                throw new RuntimeException('source_changed');
            return $value;
        });
    }
    /** Keep the complete existing import/export document without increasing the
     * State file limit. Every part uses the same create-once job-bound writer. */
    public function createMeasuredDocument(array $value,string $raw):array
    {
        require_once __DIR__.'/import-document.php';
        $bytes=strlen($raw);
        if($bytes<1||$bytes>AsusImportDocument::LIMIT||isset($value['document'])||isset($value['kind']))
            throw new RuntimeException('output_limit');
        return $this->journal(function()use($value,$raw,$bytes):array{
            $job=$value['job_id']??null;
            if(!is_string($job)||($this->read()['id']??null)!==$job)throw new RuntimeException('source_changed');
            $parts=[];
            for($offset=0;$offset<$bytes;$offset+=262144){
                $part=substr($raw,$offset,262144);
                $parts[]=$this->createMeasuredResult(['job_id'=>$job,'kind'=>'document-part',
                    'index'=>count($parts),'data'=>base64_encode($part)]);
            }
            $value['kind']='profile';$value['document']=['bytes'=>$bytes,'sha256'=>hash('sha256',$raw),'parts'=>$parts];
            return $this->createMeasuredResult($value);
        });
    }
    public function measuredDocument(array $reference,string $job):string
    {
        require_once __DIR__.'/import-document.php';
        $value=$this->measuredResult($reference,$job);$doc=$value['document']??null;
        if(($value['kind']??null)!=='profile'||!is_array($doc)||
            !is_int($doc['bytes']??null)||$doc['bytes']<1||$doc['bytes']>AsusImportDocument::LIMIT||
            !is_string($doc['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$doc['sha256'])||
            !is_array($doc['parts']??null)||!array_is_list($doc['parts'])||
            count($doc['parts'])!==(int)ceil($doc['bytes']/262144))throw new RuntimeException('source_changed');
        $raw='';
        foreach($doc['parts']as $i=>$partReference){
            if(!is_array($partReference))throw new RuntimeException('source_changed');
            $part=$this->measuredResult($partReference,$job);
            $bytes=is_string($part['data']??null)?base64_decode($part['data'],true):false;
            $expected=min(262144,$doc['bytes']-$i*262144);
            if(($part['kind']??null)!=='document-part'||($part['index']??null)!==$i||
                !is_string($bytes)||strlen($bytes)!==$expected)throw new RuntimeException('source_changed');
            $raw.=$bytes;
        }
        if(strlen($raw)!==$doc['bytes']||!hash_equals($doc['sha256'],hash('sha256',$raw)))
            throw new RuntimeException('source_changed');
        return $raw;
    }
    private function writeHeld(array $v,string $name,?array &$observedPin):void
    {
        $observedPin=null;$path=$this->path($name);$raw=json_encode($v,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
        if(strlen($raw)>1048576)throw new RuntimeException('output_limit');$before=$this->buffer($name);$stageName='.stage-'.bin2hex(random_bytes(8));$tmp=$this->path($stageName);
        $mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('insufficient_space');$created=fstat($f);
        try{if(fwrite($f,$raw)!==strlen($raw)||!fflush($f)||!fsync($f))throw new RuntimeException('insufficient_space');
            $opened=fstat($f);$stage=$this->buffer($stageName);
            if(!$created||!$opened||!$stage||$opened['dev']!==$created['dev']||$opened['ino']!==$created['ino']||self::signature($opened)!==$stage['pin']||$stage['raw']!==$raw)throw new RuntimeException('source_changed');
            fclose($f);$f=null;
            if($this->buffer($name)!==$before||$this->buffer($stageName)!==$stage)throw new RuntimeException('source_changed');
            if(!rename($tmp,$path))throw new RuntimeException('storage_unavailable');
            self::syncDirectory($this->root,$this->owner);$published=$this->buffer($name);$expected=$stage['pin'];
            if(!$published)throw new RuntimeException('source_changed');
            // Only our successful rename may advance ctime. All other stage
            // fields and the entire observed published pin remain exact.
            $expected['ctime']=$published['pin']['ctime'];
            if($published['pin']!==$expected||$published['raw']!==$raw||$this->buffer($name)!==$published)throw new RuntimeException('source_changed');
            $observedPin=$published['pin'];
        }finally{
            if(is_resource($f))fclose($f);
            // Partial or swapped stages are evidence, never name-only cleanup.
            try{$remaining=$this->buffer($stageName);
                if($created&&$remaining&&$remaining['pin']['dev']===$created['dev']&&$remaining['pin']['ino']===$created['ino']&&$remaining['raw']===$raw&&$this->buffer($stageName)===$remaining)@unlink($tmp);
            }catch(Throwable $ignored){/* Unknown files remain for attention. */}
        }
    }
    public function lock()
    {
        $path=$this->path('engine.lock');$mask=umask(0077);try{$f=fopen($path,'c+be');}finally{umask($mask);}
        if(!$f||!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');
        $s=lstat($path);$a=fstat($f);if($s['ino']!==$a['ino']||$s['dev']!==$a['dev']||($s['mode']&0777)!==0600){fclose($f);throw new RuntimeException('storage_unavailable');}return $f;
    }
}

/** Writes intent first. Foreign edits are a conflict, never rollback authority. */
final class NfqwsStrategyPickerConfig
{
    public static function candidate(string $original,array $values):string
    {
        $changes=[];
        foreach(array_merge(AsusImportConfig::BLOCKS,['NFQWS_BASE_ARGS','NFQWS_EXTRA_ARGS','NFQWS_ARGS_IPSET'],AsusImportConfig::PORTS)as $key)
            $changes[$key]=$values[$key]??'';
        $raw=AsusImportConfig::replace($original,$changes);
        if(!in_array(NfqwsStrategyPickerMode::read($raw),['auto','list'],true))throw new RuntimeException('all_mode_not_supported');
        return $raw;
    }
    private static function safe(string $directory,string $name,int $owner):string
    {return class_exists('NfqwsDeviceProfilesPaths',false)?NfqwsDeviceProfilesPaths::guard($directory,$name,$owner):NfqwsPlatform::guardFile($directory,$name,$owner);}
    public function __construct(private NfqwsStrategyPickerState $store,private string $file,private int $owner=0){}
    private static function signature(array $s):array
    {return array_intersect_key($s,array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));}
    private static function parentIdentity(array $s):array
    {return array_intersect_key($s,array_flip(['dev','ino','mode','uid','gid']));}
    /** The actual bounded FD, named inode and guarded parent of these bytes. */
    private function buffer(string $path):?array
    {
        $path=self::safe(dirname($path),basename($path),$this->owner);$directory=dirname($path);clearstatcache(true,$directory);$parent=@lstat($directory);
        clearstatcache(true,$path);$before=@lstat($path);if(!$before)return null;
        if(!$parent||($parent['mode']&0170000)!==0040000||($before['mode']&0170000)!==0100000||$before['nlink']!==1)throw new RuntimeException('source_changed');
        if($before['size']>262144)throw new RuntimeException('output_limit');$f=@fopen($path,'rbe');if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(self::signature(fstat($f))!==self::signature($before))throw new RuntimeException('source_changed');
            $raw=stream_get_contents($f,262145);$named=self::safe($directory,basename($path),$this->owner);clearstatcache(true,$path);$after=@lstat($path);clearstatcache(true,$directory);$lastParent=@lstat($directory);
            if(!is_string($raw)||strlen($raw)!==$before['size']||$named!==$path||!$after||!$lastParent||self::signature(fstat($f))!==self::signature($before)||self::signature($after)!==self::signature($before)||self::parentIdentity($lastParent)!==self::parentIdentity($parent))throw new RuntimeException('source_changed');
            return ['raw'=>$raw,'pin'=>self::signature($before),'parent'=>self::parentIdentity($parent)];
        }finally{fclose($f);}
    }
    private function syncDirectory(string $directory,array $parent):void
    {
        self::safe($directory,'.picker-sync-check',$this->owner);clearstatcache(true,$directory);$before=@lstat($directory);
        if(!$before||self::parentIdentity($before)!==$parent)throw new RuntimeException('source_changed');$f=@fopen($directory,'r');if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(self::signature(fstat($f))!==self::signature($before))throw new RuntimeException('source_changed');
            if(!fsync($f))throw new RuntimeException('storage_unavailable');self::safe($directory,'.picker-sync-check',$this->owner);clearstatcache(true,$directory);$after=@lstat($directory);
            if(!$after||self::signature(fstat($f))!==self::signature($before)||self::signature($after)!==self::signature($before))throw new RuntimeException('source_changed');
        }finally{fclose($f);}
    }
    /** Current read-only input for a new request, never restore authority. */
    public function observe():array
    {
        $v=$this->buffer($this->file);if(!$v)throw new RuntimeException('storage_unavailable');return $v;
    }
    public function raw(bool $journalBound=false):string
    {
        $v=$this->buffer($this->file);if(!$v)throw new RuntimeException('storage_unavailable');
        if($journalBound){
            // This mode only tightens a read against our actual private journal;
            // no caller-supplied pin or flag can grant publication authority.
            $j=$this->store->read('state.json',$journalPin);if(!$j)throw new RuntimeException('invalid_state');$this->binding($j,$v);
            $after=$this->store->read('state.json',$afterPin);
            if($after!==$j||$afterPin!==$journalPin||$this->buffer($this->file)!==$v)throw new RuntimeException('source_changed');
        }
        return $v['raw'];
    }
    /** New source-observed journals refuse drift across separate calls.
     * Legacy journals lacking BOTH fields retain their content-only recovery. */
    private function binding(array $j,array $actual):bool
    {
        $hasVersion=array_key_exists('config_binding_version',$j);$hasBinding=array_key_exists('config_binding',$j);
        if(!$hasVersion&&!$hasBinding)return false;
        if(!$hasVersion||!$hasBinding||$j['config_binding_version']!==1||!is_array($j['config_binding']))throw new RuntimeException('invalid_state');
        $b=$j['config_binding'];$keys=array_keys($b);sort($keys);if($keys!==['current','file','original','parent'])throw new RuntimeException('invalid_state');
        $pinKeys=['ctime','dev','gid','ino','mode','mtime','nlink','size','uid'];
        $meta=$j['metadata']??null;$keys=is_array($meta)?array_keys($meta):[];sort($keys);
        if($keys!==['gid','mode','uid']||!is_int($meta['uid'])||!is_int($meta['gid'])||!is_int($meta['mode']))throw new RuntimeException('invalid_state');
        $original=base64_decode($j['original']??'',true);
        if(!is_string($original)||strlen($original)>262144||hash('sha256',$original)!==($j['original_sha256']??null))throw new RuntimeException('invalid_state');
        foreach(['original','current']as $part){
            $p=$b[$part];$keys=is_array($p)?array_keys($p):[];sort($keys);if($keys!==$pinKeys)throw new RuntimeException('invalid_state');
            foreach($p as $value)if(!is_int($value))throw new RuntimeException('invalid_state');
            if(($p['mode']&0170000)!==0100000||($p['mode']&0002)!==0||$p['nlink']!==1||$p['size']<0||$p['size']>262144||!in_array($p['uid'],[$this->owner,65534],true)||$p['uid']!==$meta['uid']||$p['gid']!==$meta['gid']||($p['mode']&0777)!==$meta['mode'])throw new RuntimeException('invalid_state');
        }
        if($b['original']['size']!==strlen($original))throw new RuntimeException('invalid_state');
        $keys=is_array($b['parent'])?array_keys($b['parent']):[];sort($keys);if($keys!==['dev','gid','ino','mode','uid'])throw new RuntimeException('invalid_state');
        foreach($b['parent']as $value)if(!is_int($value))throw new RuntimeException('invalid_state');
        if(!is_string($b['file'])||$b['file']!==self::safe(dirname($this->file),basename($this->file),$this->owner))throw new RuntimeException('invalid_state');
        foreach($b['parent']as $key=>$value)if($value!==$actual['parent'][$key])throw new RuntimeException('source_changed');
        foreach($b['current']as $key=>$value)if($value!==$actual['pin'][$key])throw new RuntimeException('source_changed');
        if(hash('sha256',$actual['raw'])!==($j['current']??null))throw new RuntimeException('source_changed');return true;
    }
    public function snapshot(bool $running):array
    {
        $before=$this->buffer($this->file);if(!$before)throw new RuntimeException('storage_unavailable');$raw=$before['raw'];$s=$before['pin'];
        $j=['id'=>bin2hex(random_bytes(16)),'state'=>'preparing','phase'=>'backup','started_at'=>time(),'boot'=>trim((string)file_get_contents('/proc/sys/kernel/random/boot_id')),
            'original'=>base64_encode($raw),'original_sha256'=>hash('sha256',$raw),'known'=>[hash('sha256',$raw)],'current'=>hash('sha256',$raw),'metadata'=>['uid'=>$s['uid'],'gid'=>$s['gid'],'mode'=>$s['mode']&0777],
            'running_before'=>$running,'profiles'=>[],'skipped'=>[],'code'=>null,'restored'=>false,'winner'=>null];
        $j['config_binding_version']=1;$j['config_binding']=['file'=>self::safe(dirname($this->file),basename($this->file),$this->owner),'original'=>$before['pin'],'current'=>$before['pin'],'parent'=>$before['parent']];
        $this->store->write($j);if($this->buffer($this->file)!==$before)throw new RuntimeException('source_changed');return $j;
    }
    public function replace(string $raw):void
    {
        if(strlen($raw)>262144)throw new RuntimeException('output_limit');$j=$this->store->read();$before=$this->buffer($this->file);
        if(!$j||!$before||hash('sha256',$before['raw'])!==$j['current'])throw new RuntimeException('source_changed');
        $bound=$this->binding($j,$before);$sha=hash('sha256',$raw);if(!in_array($sha,$j['known'],true))$j['known'][]=$sha;if($bound)$j['restored']=false;$this->store->write($j);
        $published=$this->atomic($raw,$before,$j['metadata']);$j['current']=$sha;if($bound)$j['config_binding']['current']=$published['pin'];$this->store->write($j);
        if($this->buffer($this->file)!==$published)throw new RuntimeException('source_changed');
    }
    private function atomic(string $raw,array $before,array $meta):array
    {
        if($this->buffer($this->file)!==$before)throw new RuntimeException('source_changed');
        $tmp=self::safe(dirname($this->file),'.picker-'.bin2hex(random_bytes(8)),$this->owner);$mask=umask(0077);
        try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('insufficient_space');$created=fstat($f);
        $stage=function()use(&$f,$tmp,$raw,$created,$before):array{
            $v=$this->buffer($tmp);$opened=fstat($f);
            if(!$v||!$created||!$opened||$opened['dev']!==$created['dev']||$opened['ino']!==$created['ino']||self::signature($opened)!==$v['pin']||$v['raw']!==$raw||$v['parent']!==$before['parent'])throw new RuntimeException('source_changed');return $v;
        };
        try{if(fwrite($f,$raw)!==strlen($raw)||!fflush($f))throw new RuntimeException('insufficient_space');
            // Metadata changes are permitted only while the named file is our
            // actual complete stage. A pathname alone never grants ownership.
            $stage();if($meta['uid']!==$this->owner&&!chown($tmp,$meta['uid']))throw new RuntimeException('storage_unavailable');
            $stage();if(!chgrp($tmp,$meta['gid']))throw new RuntimeException('storage_unavailable');
            $stage();if(!chmod($tmp,$meta['mode']))throw new RuntimeException('storage_unavailable');$staged=$stage();
            if($staged['pin']['uid']!==$meta['uid']||$staged['pin']['gid']!==$meta['gid']||($staged['pin']['mode']&07777)!==$meta['mode'])throw new RuntimeException('source_changed');
            if(!fsync($f))throw new RuntimeException('insufficient_space');
            if($stage()!==$staged||$this->buffer($this->file)!==$before||$stage()!==$staged)throw new RuntimeException('source_changed');
            if(!rename($tmp,$this->file))throw new RuntimeException('storage_unavailable');$this->syncDirectory(dirname($tmp),$before['parent']);
            $published=$this->buffer($this->file);$expected=$staged['pin'];if(!$published)throw new RuntimeException('source_changed');
            // Our verified rename may advance ctime; all other fields and the
            // complete observed published pin must stay exact around readback.
            $expected['ctime']=$published['pin']['ctime'];
            if($published['pin']!==$expected||$published['raw']!==$raw||$published['parent']!==$before['parent']||self::signature(fstat($f))!==$published['pin']||$this->buffer($this->file)!==$published)throw new RuntimeException('source_changed');return $published;
        }finally{
            if(is_resource($f))fclose($f);
            try{$remaining=$this->buffer($tmp);
                if($created&&$remaining&&$remaining['pin']['dev']===$created['dev']&&$remaining['pin']['ino']===$created['ino']&&$remaining['parent']===$before['parent']&&$remaining['raw']===$raw&&$this->buffer($tmp)===$remaining)@unlink($tmp);
            }catch(Throwable $ignored){/* Preserve partial, swapped or unknown stages. */}
        }
    }
    public function restore():void
    {
        $j=$this->store->read();if(!$j)throw new RuntimeException('invalid_state');$before=$this->buffer($this->file);if(!$before)throw new RuntimeException('source_changed');$actual=hash('sha256',$before['raw']);
        $bound=$this->binding($j,$before);if(!in_array($actual,$j['known'],true))throw new RuntimeException('source_changed');
        $raw=base64_decode($j['original'],true);if(!is_string($raw)||hash('sha256',$raw)!==$j['original_sha256'])throw new RuntimeException('invalid_state');
        $published=$actual!==$j['original_sha256']?$this->atomic($raw,$before,$j['metadata']):$before;
        $j['current']=$j['original_sha256'];$j['restored']=true;if($bound)$j['config_binding']['current']=$published['pin'];$this->store->write($j);
        if($this->buffer($this->file)!==$published)throw new RuntimeException('source_changed');
    }
}

/** Export the winner into ordinary managed folders without replacing originals. */
final class NfqwsStrategyPickerResources
{
    public static function directory(string $path,int $owner=0):string
    {
        // Validate the directory as a parent, rather than treating it as a
        // regular file. The guard still rejects symlinks and unsafe ownership.
        return dirname(self::safe($path,'.picker-directory-check',$owner));
    }
    public static function fingerprint(array $inventory,array $mutable):string
    {
        $files=[];foreach($inventory['files']as $f){$name=$f['kind'].'/'.$f['name'];if(!in_array($name,$mutable,true))$files[$name]=[$f['state'],$f['sha256']??null];}
        ksort($files);return hash('sha256',json_encode($files,JSON_THROW_ON_ERROR));
    }
    private static function safe(string $directory,string $name,int $owner):string
    {return class_exists('NfqwsDeviceProfilesPaths',false)?NfqwsDeviceProfilesPaths::guard($directory,$name,$owner):NfqwsPlatform::guardFile($directory,$name,$owner);}
    public static function snapshotMutable(array $entry,string $source,int $owner=0,?NfqwsStrategyPickerState $store=null):array
    {
        $seed=[];$total=0;$profile=null;$metadataPin=null;$journal=null;$journalPin=null;$lib=null;
        $fields=array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']);$parents=array_flip(['dev','ino','mode','uid','gid']);$reader=class_exists('NfqwsDeviceProfilesPaths',false)?NfqwsDeviceProfilesPaths::reader($source,$owner):new AsusShareRead($owner,null,null,true);
        if($store!==null){
            $journal=$store->read('state.json',$journalPin);if(($journal['actuator_attention']??null)!==null||($journal['actuator_intent']??null)!==null||($journal['engine_trial']??null)!==null)throw new RuntimeException('recovery_required');
            $id=$journal['id']??null;if(!is_string($id))throw new RuntimeException('source_changed');
            $base=$store->profileRoot($id);$lib=$store->profileLibrary($journal);$profile=$lib->entry($entry['id']??'',$metadataPin);
            if(($profile['resource_binding_version']??null)!==1||NfqwsDeviceProfilesPaths::readPath($source)!==NfqwsDeviceProfilesPaths::readPath($base.'/'.$profile['id']))throw new RuntimeException('source_changed');
            foreach(['files','mutable_files','resource_bindings','resource_directories']as $key)if(($entry[$key]??null)!==($profile[$key]??null))throw new RuntimeException('source_changed');
        }
        foreach($entry['mutable_files']??[]as $relative){
            if(!isset($entry['files'][$relative])||!preg_match('~^lists/([A-Za-z0-9_.-]{1,128})$~D',$relative,$m))throw new RuntimeException('invalid_state');
            $path=self::safe($source.'/lists',$m[1],$owner);$s=$reader->stat($path);$pin=array_intersect_key($s??[],$fields);if(!$s)throw new RuntimeException('source_changed');
            if($s['size']>262144)throw new RuntimeException('output_limit');
            try{$raw=$reader->bytes($path,262144);}catch(RuntimeException $e){if($e->getMessage()==='resource_unavailable')throw new RuntimeException('storage_unavailable',0,$e);throw $e;}
            if(array_intersect_key($reader->stat($path)??[],$fields)!==$pin)throw new RuntimeException('source_changed');
            if($store!==null){
                $current=$journal['mutable_resources'][$profile['id']][$relative]??null;clearstatcache(true,dirname($path));
                if(!is_array($current)||($current['identity']??null)!==$pin||($current['sha256']??null)!==hash('sha256',$raw)||array_intersect_key(lstat(dirname($path)),$parents)!==$profile['resource_bindings'][$relative]['parent'])throw new RuntimeException('source_changed');
            }
            if(($total+=strlen($raw))>393216)throw new RuntimeException('output_limit');$seed[$relative]=['sha256'=>hash('sha256',$raw),'data'=>base64_encode($raw)];
        }
        if($store!==null&&($store->read('state.json',$actualPin)!==$journal||$actualPin!==$journalPin||$lib->entry($profile['id'],$actualMetadataPin)!==$profile||$actualMetadataPin!==$metadataPin))throw new RuntimeException('source_changed');
        return $seed;
    }
    public static function retain(array $entry,string $source,string $target,int $owner=0,?array $seed=null,?NfqwsStrategyPickerState $store=null):array
    {
        $sourceAlias=$source;$source=realpath($source);
        if($source===false)throw new RuntimeException('storage_unavailable');
        if($store!==null)self::snapshotMutable($entry,$source,$owner,$store);
        $reader=class_exists('NfqwsDeviceProfilesPaths',false)?NfqwsDeviceProfilesPaths::reader($source,$owner):new AsusShareRead($owner,null,null,true);$fields=array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']);
        $copies=[];$mapping=[];$bytes=0;
        foreach($entry['files']as $relative=>$sha){
            $identity=NfqwsResourcePaths::relative($relative);if($identity===null)throw new RuntimeException('invalid_state');
            $kind=$identity['kind'];$name=basename($identity['name']);
            $from=self::safe(dirname($source.'/'.$relative),$name,$owner);$s=$reader->stat($from);if(!$s)throw new RuntimeException('source_changed');$pin=array_intersect_key($s,$fields);
            if($s['size']>262144)throw new RuntimeException('output_limit');
            $mutable=in_array($relative,$entry['mutable_files']??[],true);
            if($mutable&&$seed!==null){
                $saved=$seed[$relative]??null;$raw=is_array($saved)&&is_string($saved['data']??null)?base64_decode($saved['data'],true):false;
                if(!is_string($raw)||strlen($raw)>262144||hash('sha256',$raw)!==($saved['sha256']??null))throw new RuntimeException('source_changed');
            }else{$raw=$reader->bytes($from,262144);}
            if(array_intersect_key($reader->stat($from)??[],$fields)!==$pin||!$mutable&&isset($entry['resource_bindings'][$relative])&&$pin!==$entry['resource_bindings'][$relative]['identity'])throw new RuntimeException('source_changed');
            if(strlen($raw)>262144||($bytes+=strlen($raw))>2097152)throw new RuntimeException('output_limit');
            if(!$mutable&&hash('sha256',$raw)!==$sha)throw new RuntimeException('source_changed');
            $dir=$target.'/'.$kind;$imported=str_starts_with($identity['name'],'imported/');
            if($imported){
                self::directory($dir,$owner);$dir.='/imported';clearstatcache(true,$dir);
                if(@lstat($dir)===false){$mask=umask(0022);try{$created=@mkdir($dir,0755);}finally{umask($mask);}if(!$created)throw new RuntimeException('source_changed');}
                self::directory($dir,$owner);$name=basename(NfqwsResourcePaths::imported($kind,hash('sha256',$raw)));
            }
            $to=self::safe($dir,$name,$owner);
            if($imported&&is_file($to)&&hash_file('sha256',$to)!==hash('sha256',$raw))throw new RuntimeException('source_changed');
            if(!$imported&&(!is_file($to)||hash_file('sha256',$to)!==hash('sha256',$raw))){
                $name='picker-'.substr(hash('sha256',$raw),0,16).'-'.substr($name,0,100);$to=self::safe($dir,$name,$owner);
                if(is_file($to)&&hash_file('sha256',$to)!==hash('sha256',$raw))throw new RuntimeException('source_changed');
            }
            $logical=$dir.'/'.basename($to);
            $mapping[$source.'/'.$relative]=$logical;$mapping[$sourceAlias.'/'.$relative]=$logical;
            if(!is_file($to))$copies[]=[$to,$raw,$mutable];
        }
        if($store!==null)self::snapshotMutable($entry,$source,$owner,$store);
        foreach($copies as [$to,$raw,$mutable]){
            $mask=umask(0077);try{$f=fopen($to,'xb');}finally{umask($mask);}
            try{if(!$f||fwrite($f,$raw)!==strlen($raw)||!fflush($f)||!chmod($to,0644))throw new RuntimeException('insufficient_space');
                if($mutable&&$owner===0&&!chown($to,65534))throw new RuntimeException('storage_unavailable');
                if(!fsync($f))throw new RuntimeException('storage_unavailable');$published=array_intersect_key(fstat($f),$fields);
                if(array_intersect_key($reader->stat($to)??[],$fields)!==$published||$reader->bytes($to,262144)!==$raw)throw new RuntimeException('source_changed');
                $df=fopen(dirname($to),'r');try{if(!$df||!fsync($df))throw new RuntimeException('storage_unavailable');}finally{if(is_resource($df))fclose($df);}
                if(array_intersect_key(fstat($f),$fields)!==$published||array_intersect_key($reader->stat($to)??[],$fields)!==$published)throw new RuntimeException('source_changed');
            }finally{if(is_resource($f))fclose($f);}
        }
        $config=$entry['config'];foreach($config as $key=>&$value)if(str_starts_with($key,'NFQWS_'))$value=strtr($value,$mapping);unset($value);
        return $config;
    }
}
