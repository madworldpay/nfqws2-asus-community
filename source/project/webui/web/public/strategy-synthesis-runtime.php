<?php
require_once __DIR__.'/strategy-synthesis.php';
require_once __DIR__.'/strategy-synthesis-export.php';

/** Runs under the picker's existing process guard and shared mutation writer. */
trait NfqwsStrategySynthesisRuntime
{
    private array $synthesisExplored=[];
    private float $synthesisProbePeak=0;
    private function synthesisCustom(array $job):bool
    {
        if(!array_key_exists('custom_hosts',$job))return false;
        require_once __DIR__.'/strategy-picker-targets.php';
        $hosts=$job['custom_hosts'];
        if(!is_array($hosts)||!array_is_list($hosts)||count($hosts)<1||count($hosts)>10)
            throw new RuntimeException('invalid_request');
        foreach($hosts as $host)if(!is_string($host))throw new RuntimeException('invalid_request');
        $targets=NfqwsStrategyPickerTargets::inspectMixed(implode("\n",$hosts));
        if(!$targets['valid']||$targets['hosts']!==$hosts)throw new RuntimeException('invalid_request');
        if(($targets['schema_version']??null)===2){
            $selection=NfqwsStrategyPickerRequest::selection($job['extended']??false,$job['goal']??'all',true,
                ['hosts'=>$hosts,'only'=>$job['custom_only']??null],$job['concurrency']??'auto',(string)($job['rounds']??1));
            NfqwsStrategyPickerRequest::assertTargetIdentity($job,$selection);
            if(($job['selection_sha256']??null)!==NfqwsStrategyPickerRequest::digest($selection)||
                !array_key_exists('concurrency_choice',$job))throw new RuntimeException('invalid_request');
        }
        return true;
    }
    private function synthesisScopeRecipe(array $recipe,?array $control=null):array
    {
        $j=$this->store->read();
        if(!isset($j['custom_target_policy']))return $recipe;
        if($control===null){
            $controls=array_values(array_filter($j['profiles']??[],static fn($p)=>($p['rank']['reason']??null)==='baseline'));
            if(count($controls)!==1)throw new RuntimeException('incomparable_result');$control=$controls[0];
        }
        return $this->synthesisJoint()->scopeRecipe($recipe,$control);
    }
    private function synthesisTrial(array $entry,string $name,?array $recipe,int $repeats,bool $warm=false,?callable $onNative=null,?callable $beforeNative=null):array
    {
        if(!in_array($repeats,[1,2],true))throw new RuntimeException('invalid_request');
        if($beforeNative!==null&&$onNative===null)throw new RuntimeException('invalid_request');
        if($onNative!==null){
            require_once __DIR__.'/strategy-picker-native-capture.php';
            // The existing source callback always owns a real reservation.
            // An external observer/preflight cannot replace it with a label.
            $capture=new NfqwsStrategyPickerNativeCapture($this->store,function():void{$this->checkpoint();},$this->store->owner());
            $observer=$onNative;$preflight=$beforeNative;
            $onNative=function(array $snapshot,array $input)use($capture,$observer):void{
                $capture->capture($snapshot,$input);$observer($snapshot,$input);
            };
            $beforeNative=function(string $request,array $input)use($capture,$preflight):void{
                $capture->reserve($request,$input);
                if($preflight!==null&&$preflight($request,$input)!==null)throw new RuntimeException('invalid_request');
            };
        }
        $this->checkpoint();$j=$this->store->read();NfqwsStrategyPickerConcurrency::admit($j,true);$custom=$this->synthesisCustom($j);
        if($custom){
            $this->customCheckpoint();
            // Admission includes the full registered native bound, all custom
            // children, three service calls and independent restoration time.
            // Never fund a new trial with only its previous average duration.
            $seconds=NfqwsStrategyPickerBudget::RESTORE_SECONDS+
                NfqwsStrategyPickerBudget::customTrialSeconds($j['budget'],$repeats,$warm,($j['custom_manifest']??null)===null);
            $deadline=NfqwsStrategyPickerBudget::overallDeadline($j);if($deadline!==null&&$deadline-AsusUpdateStore::uptime()<$seconds)throw new RuntimeException('timed_out');
        }
        $p=['id'=>$entry['id'],'name'=>$name,'source'=>$recipe===null?'current':'synthesis','sample_type'=>$repeats===1?'exploratory':'repeated'];
        if($custom){$p['custom_role']='trial-'.bin2hex(random_bytes(12));$p['custom_runs']=[];}
        if($recipe!==null){
            $recipe=$this->synthesisScopeRecipe($recipe);
            if(($recipe['basis']??'empty')==='current'){
                if($custom||($j['current_basis_entry']??null)!==$entry['id']||
                    $this->library()->entry($entry['id'])['config']!==$entry['config'])throw new RuntimeException('source_changed');
            }
            $p['recipe']='s-'.substr(NfqwsStrategySynthesis::key($recipe),0,16);$p['components']=$recipe;
            $entry['config']=NfqwsStrategySynthesis::bind($recipe,$entry['config']);
        }
        $p['variant']=$entry['config'];
        $this->phase('switching',['current_name'=>$name,'active_recipe'=>$recipe]);$this->service('stop');$this->resetAuto($entry);
        $raw=$this->candidate($entry);$this->config->replace($raw);$this->service('start');$p['config_sha256']=hash('sha256',$raw);$p['runs']=[];
        for($i=$warm?-1:0;$i<$repeats;$i++){
            $this->phase($i<0?'warming':($repeats===1?'discovering':'measuring_'.($i+1)));$start=AsusUpdateStore::uptime();
            try{
                // Internal input binding only. The trusted collector must
                // preserve the original snapshot before any postchecks. This
                // callback supplies no accepted receipt or Apply authority.
                if($onNative===null)$native=$this->probe([2,3]);
                else{
                    $input=['mode'=>'picker-trial-native-input-v1','parent_id'=>$j['id'],
                        'parent_request_id'=>$j['request_id']??null,'parent_boot'=>$j['boot']??null,
                        'profile_id'=>$p['id'],'source'=>$p['source'],'recipe'=>$p['recipe']??null,
                        'config_sha256'=>$p['config_sha256'],'resource_fingerprint_sha256'=>$j['resources_sha256'],
                        'resource_binding_scope'=>'existing_fingerprint_excludes_mutable_AUTO',
                        'warmup'=>$i<0,'repeat'=>$i<0?null:$i+1];
                    $prepare=$beforeNative===null?null:fn(string $request)=>$beforeNative($request,$input);
                    $native=$this->probe([2,3],function(array $snapshot)use($onNative,$input):void{
                        $onNative($snapshot,$input);$this->checkpoint();$current=$this->store->read();
                        if(($current['id']??null)!==$input['parent_id']||
                            ($current['request_id']??null)!==$input['parent_request_id']||
                            ($current['boot']??null)!==$input['parent_boot']||
                            ($current['current']??null)!==$input['config_sha256']||
                            hash('sha256',$this->config->raw())!==$input['config_sha256']||
                            ($current['resources_sha256']??null)!==$input['resource_fingerprint_sha256']||
                            $this->resourcesFingerprint()!==$input['resource_fingerprint_sha256'])
                            throw new RuntimeException('source_changed');
                    },null,$prepare);
                }
                if($i>=0){
                    $score=NfqwsStrategyPickerConcurrency::measure($j,$native);$p['runs'][]=$score;
                    if($custom)$p['custom_runs'][]=$this->customSample($p['custom_role'],$i+1,$score['context_sha256']);
                }
            }finally{$this->synthesisProbePeak=max($this->synthesisProbePeak,AsusUpdateStore::uptime()-$start);}
        }
        // Preserve completed measurements before a later actuator can fail.
        // AUTO is accepted only after the existing stop observer has closed
        // engine_trial and committed the stable, same-copy resource identity.
        $p=$this->synthesisKeepMeasurement($p,$raw);
        $this->service('stop');$p=$this->synthesisSealMeasured($p,$entry,$raw);
        $this->config->restore();$this->phase($this->store->read()['phase'],['restored'=>false]);return $p;
    }
    private function synthesisKeepMeasurement(array $profile,string $raw):array
    {
        $this->checkpoint();$job=$this->store->read();$sha=hash('sha256',$raw);
        $count=($profile['sample_type']??null)==='repeated'?2:1;
        if(!is_array($profile['runs']??null)||count($profile['runs'])!==$count||
            ($profile['config_sha256']??null)!==$sha||($job['current']??null)!==$sha||
            $this->config->raw()!==$raw||$this->resourcesFingerprint()!==($job['resources_sha256']??null))
            throw new RuntimeException('source_changed');
        NfqwsStrategyPickerConcurrency::verifyRuns($job,[$profile]);
        $round=$job['series']['current']??1;
        $binding=array_intersect_key($job,array_flip(['request_id','boot','original_sha256','resources_sha256']));
        $ref=$this->store->createMeasuredResult(['job_id'=>$job['id'],'kind'=>'measurement','round'=>$round,
            'profile'=>$profile,'native_config_base64'=>base64_encode($raw),'binding'=>$binding]);
        $current=$this->store->read();
        if(($current['id']??null)!==$job['id']||array_intersect_key($current,$binding)!==$binding||
            ($current['current']??null)!==$sha||$this->config->raw()!==$raw)
            throw new RuntimeException('source_changed');
        $catalog=$current['measured_results']??[];
        if(!is_array($catalog)||!array_is_list($catalog))throw new RuntimeException('source_changed');
        $catalog[]=['id'=>$ref['id'],'reference'=>$ref,'number'=>count($catalog)+1,'round'=>$round,
            'name'=>$profile['name'],'sample_type'=>$profile['sample_type'],'document'=>null];
        $current['measured_results']=$catalog;$this->store->write($current);
        $profile['measured_reference']=$ref;return $profile;
    }
    private function synthesisMeasuredBundle(array $entry,array $profile):array
    {
        $job=$this->store->read();$source=$this->store->profileRoot($job['id']).'/'.$entry['id'];
        $entry['config']=$profile['variant'];
        if(isset($profile['components']))$entry['synthesis_recipe']=$profile['components'];
        $seed=NfqwsStrategyPickerResources::snapshotMutable($entry,$source,$this->store->owner(),$this->store);
        $bundle=isset($profile['components'])
            ?NfqwsStrategySynthesisExport::bundle($entry,$source,$seed,$this->store->owner(),false,$job,$profile)
            :NfqwsStrategySynthesisExport::measuredControl($entry,$source,$seed,$this->store->owner(),$job,$profile);
        if(NfqwsStrategyPickerResources::snapshotMutable($entry,$source,$this->store->owner(),$this->store)!==$seed)
            throw new RuntimeException('source_changed');
        return $bundle;
    }
    private function synthesisSealMeasured(array $profile,array $entry,string $raw):array
    {
        $this->checkpoint();$job=$this->store->read();$ref=$profile['measured_reference']??null;
        if(!is_array($ref)||($job['current']??null)!==hash('sha256',$raw)||$this->config->raw()!==$raw)
            throw new RuntimeException('source_changed');
        $measured=$this->store->measuredResult($ref,$job['id']);
        if(($measured['kind']??null)!=='measurement'||($measured['profile']['config_sha256']??null)!==hash('sha256',$raw))
            throw new RuntimeException('source_changed');
        try{
            $bundle=$this->synthesisMeasuredBundle($entry,$profile);
        }catch(RuntimeException $error){
            // A measurement can be valid even when its full kit exceeds the
            // portable document limits. Keep the sample and continue testing.
            if(in_array($error->getMessage(),['output_limit','import_limit','unresolved_profile_resource'],true))
                return $profile;
            throw $error;
        }
        $document=$this->store->createMeasuredDocument(['job_id'=>$job['id'],'measurement'=>$ref,
            'round'=>$measured['round'],'config_sha256'=>hash('sha256',$raw)],$bundle['raw']);
        $current=$this->store->read();$matches=0;
        if(($current['id']??null)!==$job['id']||($current['current']??null)!==hash('sha256',$raw)||$this->config->raw()!==$raw)
            throw new RuntimeException('source_changed');
        foreach($current['measured_results']as &$item)if(($item['reference']??null)===$ref){
            if(($item['document']??null)!==null)throw new RuntimeException('source_changed');
            $item['document']=$document;$matches++;
        }unset($item);
        if($matches!==1)throw new RuntimeException('source_changed');
        $this->store->write($current);return $profile;
    }
    private function synthesisRecord(array $p,array $rank):void
    {
        $j=$this->store->read();
        if(isset($p['measured_reference'])){
            $matches=0;
            foreach($j['measured_results']as &$item){
                if($item['reference']!==$p['measured_reference'])continue;
                $item['rank']=array_intersect_key($rank,array_flip(['eligible','reason','gain']));
                $matches++;
            }
            unset($item);
            if($matches!==1)throw new RuntimeException('source_changed');
            unset($p['measured_reference']);
        }
        $p['rank']=$rank;$index=null;
        foreach($j['profiles']as $i=>$old)if(($old['id']??null)===$p['id']&&($old['recipe']??null)===($p['recipe']??null)){$index=$i;break;}
        if($index===null)$j['profiles'][]=$p;
        else{
            $old=$j['profiles'][$index];$attempts=$old['previous_attempts']??[];unset($old['previous_attempts']);
            $attempts[]=$old;$p['previous_attempts']=$attempts;$j['profiles'][$index]=$p;
        }
        $j['progress']=min(90,5+count($j['profiles'])*5);$this->store->write($j);
    }
    private function synthesisJoint():NfqwsStrategyPickerCustomJoint
    {
        require_once __DIR__.'/strategy-picker-custom-joint.php';
        $j=$this->store->read();$original=is_string($j['original']??null)?base64_decode($j['original'],true):false;
        if(!is_string($original)||hash('sha256',$original)!==($j['original_sha256']??null))
            throw new RuntimeException('incomparable_result');
        $samples=new NfqwsStrategyPickerCustomSamples($this->store,fn()=>$this->customCheckpoint(),
            fn()=>$this->customContext(),$this->store->owner());
        return new NfqwsStrategyPickerCustomJoint($samples,$j['id'],$original);
    }
    private function synthesisRank(array $baseline,array $candidate,string $goal):array
    {
        $j=$this->store->read();
        if(!$this->synthesisCustom($j))return NfqwsStrategySynthesis::improvementCompare($baseline['runs'],$candidate['runs'],$goal);
        $only=$j['custom_only']??false;if(!is_bool($only))throw new RuntimeException('invalid_request');
        return $this->synthesisJoint()->compare($baseline,$candidate,$goal,$only);
    }
    private function synthesisObservation(array $profile,array $recipe):array
    {
        if($this->synthesisCustom($this->store->read()))return $this->synthesisJoint()->observation($profile);
        return ['recipe'=>$recipe,'runs'=>$profile['runs']];
    }
    private function synthesisCheckRecordedProfile(array $job,array $profile):void
    {
        // Older journals have no separate measurement files. They still go
        // through the same recipe, library and repeated-score checks below.
        if(!array_key_exists('measured_results',$job))return;
        $round=$job['series']['selected']??$job['series']['current']??1;
        unset($profile['rank'],$profile['previous_attempts']);
        foreach($job['measured_results'] as $item){
            if($item['round']!==$round||$item['name']!==$profile['name']||
                $item['sample_type']!==$profile['sample_type'])continue;
            $saved=$this->synthesisMeasuredSelection($job['id'],$item['id'],$job);
            if($saved['profile']===$profile)return;
        }
        throw new RuntimeException('synthesis_unverified');
    }
    /** Completion flags are presentation metadata, never Apply/export authority.
     * Reopen the committed evidence even after the live trial has ended. */
    private function synthesisVerifiedProfile(string $key,bool $apply=false):array
    {
        try{
            $j=$this->store->read();NfqwsStrategyPickerConcurrency::verifyRuns($j,$j['profiles']);$matches=[];
            foreach($j['profiles']as $profile)
                if($profile['id'].':'.($profile['recipe']??'')===$key)$matches[]=$profile;
            if(count($matches)!==1)throw new RuntimeException('synthesis_unverified');
            $selected=$matches[0];$custom=$this->synthesisCustom($j);
            $currentBasis=($selected['components']['basis']??null)==='current'||
                ($selected['source']??null)==='synthesis'&&($j['current_basis_entry']??null)===$selected['id'];
            if(($j['search']??null)!=='synthesis'||($j['generated']??null)!==$key||
                ($j['generation']['verified']??null)!==true||($selected['source']??null)!=='synthesis'||
                ($selected['sample_type']??null)!=='repeated'||
                ($selected['recipe']??null)!=='s-'.substr(NfqwsStrategySynthesis::key($selected['components']),0,16))
                throw new RuntimeException('synthesis_unverified');
            $controls=['baseline'=>[],'zero_baseline'=>[]];
            foreach($j['profiles']as $profile){$reason=$profile['rank']['reason']??null;
                if(is_string($reason)&&isset($controls[$reason]))$controls[$reason][]=$profile;
            }
            if(count($controls['baseline'])!==1||count($controls['zero_baseline'])!==1)
                throw new RuntimeException('synthesis_unverified');
            $control=$controls['baseline'][0];$zero=$controls['zero_baseline'][0];
            if(($control['source']??null)!=='current'||($control['sample_type']??null)!=='repeated'||
                ($zero['source']??null)!=='synthesis'||($zero['sample_type']??null)!=='repeated'||
                ($zero['components']??null)!==$this->synthesisScopeRecipe(NfqwsStrategySynthesis::blank(),$control)||
                $selected['components']!==$this->synthesisScopeRecipe($selected['components'],$control))throw new RuntimeException('synthesis_unverified');
            $entry=$this->library()->entry($selected['id']);
            if(NfqwsStrategySynthesis::bind($selected['components'],$entry['config'])!==$selected['variant'])
                throw new RuntimeException('synthesis_unverified');
            if($currentBasis){
                if($custom||($selected['components']['basis']??null)!=='current'||
                    ($j['current_basis_entry']??null)!==$selected['id']||$control['id']!==$selected['id']||
                    $control['variant']!==$entry['config'])throw new RuntimeException('synthesis_unverified');
            }elseif($selected['id']!==$zero['id']){
                throw new RuntimeException('synthesis_unverified');
            }
            foreach([$selected,$control,$zero] as $profile)$this->synthesisCheckRecordedProfile($j,$profile);
            $fromZero=$this->synthesisRank($zero,$selected,$j['goal']??'all');
            $versusCurrent=$this->synthesisRank($control,$selected,$j['goal']??'all');
            if(!$fromZero['eligible']||($custom||$currentBasis)&&!in_array($versusCurrent['reason'],['improved','no_improvement'],true)||
                $fromZero!==($j['generation']['from_zero']??null)||
                $versusCurrent!==($j['generation']['versus_current']??null)||$versusCurrent!==($selected['rank']??null)||
                $apply&&(($j['winner']??null)!==$key||!$versusCurrent['eligible']))throw new RuntimeException('synthesis_unverified');
            return $selected;
        }catch(Throwable $e){throw new RuntimeException('synthesis_unverified',0,$e);}
    }
    private function synthesisAdmission():void
    {
        $j=$this->store->read();if(!$this->synthesisCustom($j))return;
        $this->customCheckpoint();
        $policy=NfqwsStrategyPickerBudget::custom($j['budget'],count($j['custom_hosts']));
        $deadline=NfqwsStrategyPickerBudget::overallDeadline($j);
        if(($j['budget']['custom']??null)!==$policy['custom']||
            ($j['budget']['deadline_seconds']??null)!==$policy['deadline_seconds'])
            throw new RuntimeException('stale_state');
        // Compare absolute bounds from one clock sample. Subtracting two
        // fractional uptimes can round an exact boundary outside its policy.
        $now=AsusUpdateStore::uptime();
        if($deadline!==null&&$deadline>$now+$policy['deadline_seconds'])throw new RuntimeException('stale_state');
        if($deadline!==null&&$deadline<$now+$policy['custom']['minimum_series_seconds'])throw new RuntimeException('timed_out');
    }
    private function synthesisTime():bool
    {
        $j=$this->store->read();
        if($this->synthesisCustom($j)){
            $reserve=NfqwsStrategyPickerBudget::customTrialSeconds($j['budget'],1,false,($j['custom_manifest']??null)===null)+
                NfqwsStrategyPickerBudget::customTrialSeconds($j['budget'],2,true,false)+NfqwsStrategyPickerBudget::RESTORE_SECONDS;
        }else $reserve=max(180,3*$this->synthesisProbePeak*1.5+120);
        $deadline=NfqwsStrategyPickerBudget::overallDeadline($j);return $deadline===null||$deadline-AsusUpdateStore::uptime()>$reserve;
    }
    /** A small carry-forward pool contains grammar recipes, never scores,
     * copied resources, old target manifests, or Apply/export authority. */
    private function synthesisMemory(array $recipes,?array $selection=null,array $explored=[]):array
    {
        $j=$selection??$this->store->read();$out=[];$seen=[];
        foreach($recipes as $recipe){
            try{
                if(!is_array($recipe))continue;NfqwsStrategySynthesis::compile($recipe);$proposals=[$recipe];
                // An old IPv4 manifest cannot authorize today's trial. Keep
                // protocol and per-destination leaders as fresh base proposals;
                // only the current joint observer may scope today's trials.
                if(isset($recipe['custom_scope'])||($recipe['overrides']??[])!==[]){
                    $base=($recipe['basis']??'empty')==='current'?NfqwsStrategySynthesis::blank():$recipe;
                    unset($base['custom_scope'],$base['basis']);$base['overrides']=[];$proposals=[$base];
                    foreach($recipe['overrides']as $rule){$variant=$base;$variant[$rule['protocol']]=$rule['component'];$proposals[]=$variant;}
                }
                foreach($proposals as $proposal){
                    $key=NfqwsStrategySynthesis::key($proposal);
                    if($key===NfqwsStrategySynthesis::key(NfqwsStrategySynthesis::blank())||isset($seen[$key]))continue;
                    $out[]=$proposal;$seen[$key]=true;if(count($out)>=8)break 2;
                }
            }catch(Throwable $e){continue;}
        }
        $explored=array_values(array_unique(array_filter($explored,static fn($k)=>is_string($k)&&preg_match('/^[a-f0-9]{64}$/D',$k))));
        return ['version'=>'picker-recipe-memory-v1','knowledge_version'=>NfqwsStrategySynthesis::VERSION,
            'scope'=>['goal'=>$j['goal']??'all','custom_hosts'=>$j['custom_hosts']??[],'custom_only'=>$j['custom_only']??false],
            'recipes'=>$out,'explored'=>array_slice($explored,0,64)];
    }
    /** Archived measurements only propose finite recipes. Every proposal is
     * measured again against this run's original and zero-method controls. */
    private function synthesisHistoryRecipes(string $goal,?array $selection=null):array
    {
        $current=$this->store->read();$selection=$selection??$current;$selection['goal']=$goal;
        $basis=$this->synthesisMemory([],$selection);$out=[];$seen=[];$this->synthesisExplored=[];
        $add=function(array $recipes)use(&$out,&$seen,$selection):void{
            foreach($this->synthesisMemory($recipes,$selection)['recipes']as $recipe){
                $key=NfqwsStrategySynthesis::key($recipe);
                if(!isset($seen[$key])&&count($out)<8){$out[]=$recipe;$seen[$key]=true;}
            }
        };
        $coverage=function(array $keys):void{
            foreach($keys as $key)if(is_string($key)&&preg_match('/^[a-f0-9]{64}$/D',$key)&&!in_array($key,$this->synthesisExplored,true)&&count($this->synthesisExplored)<64)$this->synthesisExplored[]=$key;
        };
        $memory=function($document)use($basis,$add,$coverage):void{
            if(!is_array($document)||array_diff(array_keys($document),array_keys($basis))||
                ($document['version']??null)!==$basis['version']||!NfqwsStrategySynthesis::compatibleMemory($document['knowledge_version']??null)||
                ($document['scope']??null)!==$basis['scope']||!is_array($document['recipes']??null)||
                !array_is_list($document['recipes'])||count($document['recipes'])>8||
                isset($document['explored'])&&(!is_array($document['explored'])||!array_is_list($document['explored'])||count($document['explored'])>64))return;
            $add($document['recipes']);
            $coverage($document['explored']??[]);
        };
        // Reserve bounded slots for the just-finished round before older jobs.
        $memory($current['synthesis_memory']??null);
        $this->store->path('state.json');$archives=[];
        foreach(scandir($this->store->root)as $name){
            if(!preg_match('/^job-([a-f0-9]{32})$/D',$name,$m))continue;
            $path=$this->store->root.'/'.$name;clearstatcache(true,$path);$s=@lstat($path);
            if(!$s||($s['mode']&0177777)!==0040700||$s['uid']!==$this->store->owner())continue;
            $archives[]=['id'=>$m[1],'path'=>$path,'mtime'=>$s['mtime']];
        }
        usort($archives,static fn($a,$b)=>$b['mtime']<=>$a['mtime']?:strcmp($a['id'],$b['id']));
        foreach(array_slice($archives,0,8)as $archive){
            try{
                $history=(new NfqwsStrategyPickerState($archive['path'],$this->store->owner()))->read();
                if(($history['id']??null)!==$archive['id']||
                    !in_array($history['state']??null,['completed','failed','cancelled','interrupted'],true)||
                    ($history['restored']??null)!==true||($history['search']??null)!=='synthesis'||
                    !is_array($history['profiles']??null)||count($history['profiles'])>64||
                    $this->synthesisMemory([],$history)['scope']!==$basis['scope'])continue;
                if($history['state']==='completed'){
                    $rows=[];
                    foreach($history['profiles']as $profile)if(is_array($profile['components']??null)&&is_array($profile['runs']??null)&&!isset($profile['components']['custom_scope']))
                        $rows[]=['recipe'=>$profile['components'],'runs'=>$profile['runs']];
                    try{$add(NfqwsStrategySynthesis::bestForRetest($rows,$goal));}catch(Throwable $e){}
                }
                foreach($history['profiles']as $profile){
                    try{if(is_array($profile['components']??null))$coverage([NfqwsStrategySynthesis::key($profile['components'])]);}catch(Throwable $e){}
                }
                // A restored failed/cancelled round carries preceding proposals,
                // not its partial measurements or an invented successful score.
                $memory($history['synthesis_memory']??null);
            }catch(Throwable $e){continue;} // Preserve unreadable/foreign history; never repair it.
        }
        return $out;
    }
    /** Keep this series' completed-round coverage without enlarging its
     * persisted 8-recipe/64-key memory or reusing old measurement scores. */
    private function synthesisPreviouslyExplored(array $job):array
    {
        $keys=array_fill_keys($this->synthesisExplored,true);
        if(!isset($job['series']))return $keys;
        $series=$job['series'];$total=NfqwsStrategyPickerRequest::rounds((string)($job['rounds']??1));
        $number=$series['current']??null;
        if(!is_int($number)||$number<1||$number>$total||($series['total']??null)!==$total||
            ($series['completed']??null)!==$number-1)throw new RuntimeException('source_changed');
        $basis=$this->synthesisMemory([],$job);
        for($n=1;$n<$number;$n++){
            $round=$this->store->round($n)->read();$memory=$round['synthesis_memory']??null;
            if(($round['id']??null)!==($job['id']??null)||($round['series_round']??null)!==$n||
                ($round['state']??null)!=='completed'||($round['restored']??null)!==true||
                !is_array($memory)||array_diff(array_keys($memory),array_keys($basis))||
                ($memory['version']??null)!==$basis['version']||!NfqwsStrategySynthesis::compatibleMemory($memory['knowledge_version']??null)||
                ($memory['scope']??null)!==$basis['scope']||!is_array($memory['explored']??null)||
                !array_is_list($memory['explored'])||count($memory['explored'])>64)throw new RuntimeException('source_changed');
            foreach($memory['explored']as $key){
                if(!is_string($key)||!preg_match('/^[a-f0-9]{64}$/D',$key))throw new RuntimeException('source_changed');
                $keys[$key]=true;
            }
        }
        return $keys;
    }
    private function synthesisWork():void
    {
        $job=$this->store->read();$total=NfqwsStrategyPickerRequest::rounds((string)($job['rounds']??1));
        if($total===1){$this->synthesisRound();$this->phase('complete',['state'=>'completed','finished_at'=>time(),'progress'=>100]);return;}
        $series=['total'=>$total,'current'=>1,'completed'=>0,'selected'=>null,'runs'=>[],'archive_version'=>2];$best=null;$priority=null;
        $this->phase('synthesis_setup',['series'=>$series]);
        for($number=1;$number<=$total;$number++){
            if($number>1){
                // The same existing work/guard pair still owns the series.
                // Each round starts only after actual original restoration,
                // a fresh source/admission check, and no pending actuator.
                $this->checkpoint();$this->assertOriginal();$this->preflight();
                $next=$this->store->read();NfqwsStrategyPickerConcurrency::admit($next,true);
                if(($next['restored']??false)!==true||($next['actuator']??null)!==null||
                    ($next['engine_trial']??null)!==null||($next['custom_worker']??null)!==null||
                    ($next['custom_sample_pending']??null)!==null||($next['custom_sample_cleanup']??null)!==null)
                    throw new RuntimeException('recovery_required');
                foreach(['profiles','skipped']as $key)$next[$key]=[];
                foreach(['winner','generated','generation','matrix','current_basis_entry','active_recipe',
                    'custom_sample_refs','custom_sample_attempts','custom_manifest','custom_manifest_sha256','custom_samples_retired']as $key)unset($next[$key]);
                $next['winner']=null;$next['state']='running';$next['progress']=0;
                $series['current']=$number;$series['selected']=null;$next['series']=$series;$this->store->write($next);
            }
            $this->synthesisRound();$this->checkpoint();$this->assertOriginal();$done=$this->store->read();
            if(($done['restored']??false)!==true)throw new RuntimeException('recovery_required');
            $archive=$this->store->round($number);
            if($archive->read()!==null)throw new RuntimeException('source_changed');
            $report=$done;$report['state']='completed';$report['phase']='complete';$report['finished_at']=time();$report['series_round']=$number;
            $archive->write($report);
            foreach(['generated-auto.json','winner-auto.json']as $name){$seed=$this->store->read($name);if($seed!==null)$archive->write($seed,$name);}
            $rank=$done['generation']['versus_current']??[];
            $quality=[(int)($rank['eligible']??false),(int)in_array($rank['reason']??null,['improved','no_improvement','goal_no_improvement'],true),
                (int)($done['generation']['verified']??false),(int)($rank['gain']??0)];
            if($best===null||$quality>$priority){$best=$number;$priority=$quality;}
            $series['completed']=$number;$series['runs'][]=['number'=>$number,'state'=>'completed','restored'=>true,
                'winner'=>$done['winner']??null,'generated'=>$done['generated']??null,'comparison'=>$rank,'tested'=>$done['matrix']['tested']??0];
            $this->phase('series_between',['series'=>$series,'progress'=>0]);
        }
        $selectedStore=$this->store->round($best);$selected=$selectedStore->read();
        $current=$this->store->read();
        // Keep the latest physical Config/resource bindings. Only the selected
        // round's measured result and its own immutable copied kit return here.
        foreach(['profiles','skipped','winner','generated','generation','matrix','current_basis_entry','active_recipe',
            'custom_sample_refs','custom_sample_attempts','custom_manifest','custom_manifest_sha256','custom_samples_retired']as $key){
            unset($current[$key]);if(array_key_exists($key,$selected))$current[$key]=$selected[$key];
        }
        $series['selected']=$best;$current['series']=$series;$this->store->write($current);
        foreach(['generated-auto.json','winner-auto.json']as $name){$seed=$selectedStore->read($name);if($seed!==null)$this->store->write($seed,$name);}
        $this->phase('complete',['state'=>'completed','finished_at'=>time(),'progress'=>100]);
    }
    private function synthesisRound():void
    {
        $this->synthesisAdmission();
        $j=$this->store->read();$custom=$this->synthesisCustom($j);$customOnly=$custom?($j['custom_only']??false):false;
        if(!is_bool($customOnly))throw new RuntimeException('invalid_request');
        $matrix=NfqwsStrategySynthesis::matrix($j['budget']);
        // The existing custom artifact limit includes warm-ups, two controls,
        // repeated leaders and the final verification. Do not raise that cap.
        if($custom)$matrix['max_trials']=min(11,$matrix['max_trials']);
        $history=$this->synthesisHistoryRecipes($j['goal']??'all');
        $summary=$matrix;unset($summary['initial']);$summary+=['tested'=>0,'stopped_by_budget'=>false,'history_candidates'=>count($history),'best_retested'=>0];
        $this->phase('synthesis_setup',['state'=>'running','matrix'=>$summary,'synthesis_memory'=>$this->synthesisMemory($history,null,$this->synthesisExplored)]);$lib=$this->library();$captured=$lib->capture('Исходная стратегия · контроль');
        $control=$this->synthesisTrial($lib->entry($captured['id']),$captured['name'],null,2,true);$this->synthesisRecord($control,['eligible'=>false,'reason'=>'baseline','gain'=>0]);
        $this->phase('synthesis_setup',['current_basis_entry'=>$captured['id']]);
        $scope=array_keys($control['runs'][0]['domains']);
        foreach($control['runs'][0]['probe_hosts']??[]as $host)$scope[]=$host;
        if($custom)$scope=array_merge($scope,$j['custom_hosts']);
        $scope=array_values(array_unique(array_filter(array_map([NfqwsStrategySynthesis::class,'host'],$scope))));
        $fresh=$lib->synthesis($scope);$entry=$lib->entry($fresh['id']);$searchBudget=$j['budget'];
        $searchBudget['synthesis_payloads']=NfqwsStrategySynthesis::availablePayloads($entry['config']??[]);
        $space=NfqwsStrategySynthesis::matrix($searchBudget);
        foreach(['dimensions','space_size']as $key)$summary[$key]=$space[$key];
        $blank=$this->synthesisScopeRecipe(NfqwsStrategySynthesis::blank(),$control);
        $none=$this->synthesisTrial($entry,'Без методов обхода · контроль',$blank,2,true);$this->synthesisRecord($none,['eligible'=>false,'reason'=>'zero_baseline','gain'=>0]);
        $observations=[$this->synthesisObservation($none,$blank)];$improvements=[];$seen=[NfqwsStrategySynthesis::key($blank)=>true];
        $previouslyExplored=$this->synthesisPreviouslyExplored($j);
        // New generation starts from the independent empty kit. The captured
        // original is a comparison/restoration control, never a candidate base.
        $seedLimit=max(3,intdiv($matrix['max_trials'],2));
        $remainingCoarse=NfqwsStrategySynthesis::queue($searchBudget,$history,$this->synthesisExplored,null,$j['goal']??'all',$matrix['max_trials']);
        $queue=array_splice($remainingCoarse,0,$seedLimit);$tested=0;
        $oldKeys=array_fill_keys(array_map([NfqwsStrategySynthesis::class,'key'],$history),true);
        $summary['policy_version']='from-scratch-adaptive-v3';$summary['coarse_candidates']=count($queue);$summary['feedback_batches']=0;$summary['history_available']=count($history);
        $summary['history_candidates']=count(array_filter($queue,fn($r)=>isset($oldKeys[NfqwsStrategySynthesis::key($r)])));
        $summary['current_basis_candidates']=count(array_filter($queue,fn($r)=>($r['basis']??'empty')==='current'));
        while($tested<$matrix['max_trials']){
            $this->checkpoint();if(!$this->synthesisTime()){$summary['stopped_by_budget']=true;break;}
            if(!$queue){$queue=array_merge(NfqwsStrategySynthesis::refine($observations,$searchBudget,$j['goal']??'all',$customOnly),$remainingCoarse);$remainingCoarse=[];$summary['feedback_batches']++;$this->phase('discovering',['matrix'=>$summary]);}
            $recipe=null;while($queue){$r=$this->synthesisScopeRecipe(array_shift($queue),$control);$key=NfqwsStrategySynthesis::key($r);if(!isset($previouslyExplored[$key])&&!isset($seen[$key])){$recipe=$r;$seen[$key]=true;break;}}
            if($recipe===null)break;$tested++;
            $this->synthesisExplored=array_slice(array_values(array_unique(array_merge([NfqwsStrategySynthesis::key($recipe)],$this->synthesisExplored))),0,64);
            $this->phase('discovering',['synthesis_memory'=>$this->synthesisMemory($history,null,$this->synthesisExplored)]);
            try{
                $current=($recipe['basis']??'empty')==='current';
                $p=$this->synthesisTrial($current?$lib->entry($captured['id']):$entry,($current?'Улучшение исходной стратегии · ':'Вариант обхода · ').$tested,$recipe,1,true);
                if($current)$improvements[]=['recipe'=>$recipe,'runs'=>$p['runs']];else $observations[]=$this->synthesisObservation($p,$recipe);
                $this->synthesisRecord($p,['eligible'=>false,'reason'=>'exploratory','gain'=>0]);
            }catch(Throwable $e){
                if($custom||in_array($e->getMessage(),['cancelled','timed_out','source_changed','insufficient_memory','guard_lost'],true))throw $e;
                $this->stopOwnedProbe();$this->service('stop');$this->config->restore();$this->phase('discovering',['restored'=>false]);$this->skip('matrix-'.$tested,$e);
            }
            $summary['tested']=$tested;$summary['distinct_programs']=count($seen)-1;$this->phase('discovering',['matrix'=>$summary]);
        }
        $repeated=[$observations[0]];$repeatedImprovements=[];$repeatedComposite=null;$compositeGain=-1;
        $currentRecipes=$custom?[]:NfqwsStrategySynthesis::bestImprovements($improvements,$control,$j['goal']??'all',3);
        $retest=array_merge($currentRecipes,NfqwsStrategySynthesis::bestForRetest($observations,$j['goal']??'all',$customOnly,$custom?3:4-count($currentRecipes)));
        foreach($retest as $recipe){
            $this->checkpoint();$current=($recipe['basis']??'empty')==='current';
            $p=$this->synthesisTrial($current?$lib->entry($captured['id']):$entry,'Лучшие варианты · повторная проверка',$recipe,2,true);
            if($current)$repeatedImprovements[]=['recipe'=>$recipe,'runs'=>$p['runs']];
            elseif($custom&&($recipe['overrides']??[])!==[]){
                // The joint observer accepts base discovery recipes only.
                // Compare a freshly repeated composite as a whole through
                // the existing artifact-backed final-quality comparison.
                $rank=$this->synthesisRank($none,$p,$j['goal']??'all');
                if($rank['eligible']&&$rank['gain']>$compositeGain){$repeatedComposite=$recipe;$compositeGain=$rank['gain'];}
            }else $repeated[]=$this->synthesisObservation($p,$recipe);
            $this->synthesisRecord($p,['eligible'=>false,'reason'=>'retested','gain'=>0]);
            $summary['best_retested']++;$this->phase('assembling',['matrix'=>$summary]);
        }
        $this->phase('assembling');
        $finalists=$custom?[$repeatedComposite??NfqwsStrategySynthesis::assemble($repeated,$j['goal']??'all',$matrix['max_rules'],$customOnly)]:
            NfqwsStrategySynthesis::finalists($repeated,$repeatedImprovements,$control,$j['goal']??'all',$matrix['max_rules']);
        $choice=null;$summary['finalists_tested']=0;
        foreach($finalists as $proposed){
            $current=($proposed['basis']??'empty')==='current';$candidateEntry=$current?$lib->entry($captured['id']):$entry;
            $measured=$this->synthesisTrial($candidateEntry,'Собранная стратегия · повторная проверка',$proposed,2,true);
            $this->synthesisExplored=array_slice(array_values(array_unique(array_merge([NfqwsStrategySynthesis::key($proposed)],$this->synthesisExplored))),0,64);
            $zeroRank=$this->synthesisRank($none,$measured,$j['goal']??'all');$originalRank=$this->synthesisRank($control,$measured,$j['goal']??'all');
            $this->synthesisRecord($measured,$originalRank);$summary['finalists_tested']++;
            $priority=[(int)$originalRank['eligible'],(int)in_array($originalRank['reason'],['no_improvement','goal_no_improvement'],true),
                (int)$zeroRank['eligible'],$originalRank['gain'],-NfqwsStrategySynthesis::cost($proposed)];
            if($choice===null||$priority>$choice['priority'])$choice=['priority'=>$priority,'recipe'=>$proposed,'final'=>$measured,
                'entry'=>$candidateEntry,'from_zero'=>$zeroRank,'versus_current'=>$originalRank];
        }
        $recipe=$choice['recipe'];$final=$choice['final'];$selectedEntry=$choice['entry'];
        $fromZero=$choice['from_zero'];$versusCurrent=$choice['versus_current'];
        $key=$final['id'].':'.$final['recipe'];$generated=null;$winner=null;
        if($fromZero['eligible']&&(!$custom||in_array($versusCurrent['reason'],['improved','no_improvement'],true))){
            $generated=$key;$source=NfqwsPlatform::settings()['config'].'/strategy-picker/'.$j['id'].'/'.$selectedEntry['id'];
            $seed=['id'=>$j['id'],'generated'=>$key,'files'=>NfqwsStrategyPickerResources::snapshotMutable($selectedEntry,$source,0,$this->store)];$this->store->write($seed,'generated-auto.json');
            if($versusCurrent['eligible']){$winner=$key;unset($seed['generated']);$seed['winner']=$key;$this->store->write($seed,'winner-auto.json');}
        }
        $leaders=NfqwsStrategySynthesis::bestForRetest($repeated,$j['goal']??'all',$customOnly);
        // The final composite already has its artifact-backed comparison. It
        // is a proposal here, never a fabricated per-method observation.
        $memory=$this->synthesisMemory(array_merge($generated===null?[]:[$recipe],$currentRecipes,$leaders,$history),null,$this->synthesisExplored);
        $this->phase('restoring',['state'=>'restoring','winner'=>$winner,'generated'=>$generated,'matrix'=>$summary,'synthesis_memory'=>$memory,'generation'=>[
            'independent_of_catalog'=>true,'knowledge_version'=>NfqwsStrategySynthesis::VERSION,'from_zero'=>$fromZero,'versus_current'=>$versusCurrent,'overrides'=>count($recipe['overrides']),
            'scope_guard_rules'=>isset($recipe['custom_scope'])?2:0,'custom_profile_count'=>count($recipe['overrides'])+(isset($recipe['custom_scope'])?2:0),'verified'=>$generated!==null]]);
        $this->restore();
    }
    private function synthesisMeasuredSelection(string $id,string $result,?array $job=null):array
    {
        $job??=$this->store->read();$items=[];
        if(($job['id']??null)!==$id)throw new RuntimeException('stale_state');
        foreach($job['measured_results']??[]as $item)if(($item['id']??null)===$result)$items[]=$item;
        if(count($items)!==1)throw new RuntimeException('invalid_request');$item=$items[0];
        if(($item['reference']['id']??null)!==$result)throw new RuntimeException('source_changed');
        $measurement=$this->store->measuredResult($item['reference'],$id);$profile=$measurement['profile']??null;
        $raw=is_string($measurement['native_config_base64']??null)?base64_decode($measurement['native_config_base64'],true):false;
        if(($measurement['kind']??null)!=='measurement'||!is_array($profile)||!is_string($raw)||
            hash('sha256',$raw)!==($profile['config_sha256']??null)||($measurement['round']??null)!==($item['round']??null)||
            ($profile['name']??null)!==($item['name']??null)||($profile['sample_type']??null)!==($item['sample_type']??null)||
            ($measurement['binding']??null)!==array_intersect_key($job,array_flip(['request_id','boot','original_sha256','resources_sha256'])))
            throw new RuntimeException('source_changed');
        NfqwsStrategyPickerConcurrency::verifyRuns($job,[$profile]);
        if(($item['document']??null)!==null){
            $doc=$this->store->measuredResult($item['document'],$id);
            if(($doc['kind']??null)!=='profile'||($doc['measurement']??null)!==$item['reference']||
                ($doc['round']??null)!==$item['round']||
                ($doc['config_sha256']??null)!==$profile['config_sha256'])throw new RuntimeException('source_changed');
        }
        return ['job'=>$job,'item'=>$item,'profile'=>$profile];
    }
    private static function synthesisMeasuredExportable(array $job,array $item):bool
    {
        return is_array($item['document']??null)&&($job['restored']??false)===true&&
            ($job['engine_trial']??null)===null&&($job['actuator_intent']??null)===null&&($job['actuator_attention']??null)===null&&
            in_array($job['state']??null,['completed','failed','cancelled','interrupted','applied'],true);
    }
    private function synthesisMeasuredView(string $id,string $result):array
    {
        $selected=$this->synthesisMeasuredSelection($id,$result);
        $profile=$selected['profile'];
        unset($profile['variant']);
        if(isset($selected['item']['rank']))$profile['rank']=$selected['item']['rank'];
        return ['id'=>$result,'round'=>$selected['item']['round'],'profile'=>$profile,
            'can_export'=>self::synthesisMeasuredExportable($selected['job'],$selected['item'])];
    }
    private function synthesisMeasuredExport(string $id,string $result):array
    {
        // Only immutable journal artifacts are read. The existing engine
        // lock rules out racing a different Start or Apply.
        $lock=$this->store->lock();
        try{
            $selected=$this->synthesisMeasuredSelection($id,$result);
            if(!self::synthesisMeasuredExportable($selected['job'],$selected['item']))
                throw new RuntimeException('synthesis_unverified');
            $raw=$this->store->measuredDocument($selected['item']['document'],$id);
            AsusImportDocument::read([$raw]);
            if($this->store->read()!==$selected['job'])throw new RuntimeException('source_changed');
            return ['filename'=>'NFQWS2_MEASURED_'.$result.'.json','raw'=>$raw,'sha256'=>hash('sha256',$raw)];
        }finally{
            flock($lock,LOCK_UN);fclose($lock);
        }
    }
    private function synthesisExport(string $id,bool $torrentSites=false):array
    {
        $lease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();$lock=$this->store->lock();
        try{return (new AsusImportTransaction())->writer(function()use($id,$torrentSites){
            $j=$this->store->read();$seed=$this->store->read('generated-auto.json');
            if(($j['id']??null)!==$id||$j['state']!=='completed'||!($j['restored']??false)||!($j['generation']['verified']??false)||($seed['id']??null)!==$id||($seed['generated']??null)!==($j['generated']??null))throw new RuntimeException('synthesis_unverified');
            $selected=$this->synthesisVerifiedProfile($j['generated']);
            if(!$selected||($selected['sample_type']??null)!=='repeated'||count($selected['runs'])!==2)throw new RuntimeException('synthesis_unverified');
            $entry=$this->library()->entry($selected['id']);$entry['config']=$selected['variant'];
            $entry['synthesis_recipe']=$selected['components'];
            return NfqwsStrategySynthesisExport::bundle($entry,NfqwsPlatform::settings()['config'].'/strategy-picker/'.$id.'/'.$entry['id'],$seed['files'],0,$torrentSites,$j);
        });}finally{foreach([$lock,$lease]as $f){flock($f,LOCK_UN);fclose($f);}}
    }
}
