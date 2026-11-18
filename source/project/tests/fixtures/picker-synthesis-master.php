<?php
umask(0077);$platform=$argv[1]??'';if(!in_array($platform,['asus-entware','openwrt'],true))throw new RuntimeException('fixture_platform');
$mixed=in_array($argv[3]??'',['mixed','mixed-recover'],true);$recover=in_array($argv[3]??'',['recover','mixed-recover','series-recover'],true);
$fromScratch=($argv[3]??'')==='from-scratch';if($fromScratch)file_put_contents('/tmp/fixture-from-scratch','enabled');
$comparison=$argv[3]??'';
$improvement=in_array($comparison,['improvement','strong-original'],true);
if($improvement)file_put_contents('/tmp/fixture-comparison',$comparison);
$limitedStorage=$comparison==='storage-limit';
$native=$platform==='openwrt';$web=$native?'/usr/share/nfqws2-web':'/opt/share/nfqws-asus-web';$library=$native?'/usr/lib/nfqws2':'/opt/lib/nfqws2-asus';
foreach([$web,$library]as $path)if(!is_dir($path))mkdir($path,0755,true);
foreach(new RecursiveIteratorIterator(new RecursiveDirectoryIterator('/fixture-web',FilesystemIterator::SKIP_DOTS),RecursiveIteratorIterator::SELF_FIRST)as $file){
    $dest=$web.'/'.substr($file->getPathname(),strlen('/fixture-web/'));
    if($file->isDir()){if(!is_dir($dest))mkdir($dest,0755);}elseif($file->isFile()&&!$file->isLink()){copy($file->getPathname(),$dest);chmod($dest,0644);}else throw new RuntimeException('fixture_source_type');
}
copy('/fixtures/config.php',$library.'/config.php');chmod($library.'/config.php',0644);
if($native){file_put_contents($web.'/platform-profile.json',"{\"schema_version\":1,\"platform\":\"openwrt\"}\n");chmod($web.'/platform-profile.json',0644);}
require $web.'/strategy-picker-custom-joint.php';$settings=NfqwsPlatform::settings();
foreach([$settings['config'],$settings['web_config'],$settings['share'],dirname($settings['service']),$settings['config'].'/strategy-picker']as $path)if(!is_dir($path))mkdir($path,0755,true);
foreach(glob('/fixture-support/*.schema.json')as $schema){$dest=$settings['share'].'/'.basename($schema);copy($schema,$dest);chmod($dest,0644);}
copy('/fixture-support/dpi-native-defaults.json',$settings['share'].'/dpi-native-defaults.json');chmod($settings['share'].'/dpi-native-defaults.json',0644);
if(!$native){mkdir('/opt/libexec/nfqws2-asus',0755,true);copy('/bin/busybox','/opt/libexec/nfqws2-asus/busybox');chmod('/opt/libexec/nfqws2-asus/busybox',0755);}
$service=<<<'SH'
#!/bin/sh
case "$1" in
stop) rm -f /tmp/fixture-service-on;;
start) touch /tmp/fixture-service-on;;
diagnostics) if [ -f /tmp/fixture-service-on ]; then echo '{"process_running":true,"nfqueue":{"state":"bound"}}'; else echo '{"process_running":false,"nfqueue":{"state":"absent"}}'; fi;;
*) exit 2;;
esac
SH;
file_put_contents($settings['service'],$service);chmod($settings['service'],0755);
if($native){file_put_contents($library.'/control.sh',$service);chmod($library.'/control.sh',0755);}
$canary=NfqwsPlatform::run(NfqwsPlatform::serviceCommand('stop'),8);if($canary['status']!==0)throw new RuntimeException('fixture_service_canary');
$resources=[];$baseline=[];
foreach(['lists','lua','blobs']as $kind)mkdir($settings['config'].'/'.$kind,0755);
foreach(['zapret-lib.lua','zapret-antidpi.lua']as $name){
    $raw=file_get_contents('/fixture-lua/'.$name);$path=$settings['config'].'/lua/'.$name;file_put_contents($path,$raw);chmod($path,0644);
    $baseline['lua/'.$name]=['bytes'=>strlen($raw),'sha256'=>hash('sha256',$raw)];
}
file_put_contents($settings['share'].'/report-baseline.json',json_encode(['resources'=>$baseline]));chmod($settings['share'].'/report-baseline.json',0644);
foreach(['user.list'=>"www.youtube.com\n",'auto.list'=>"original-auto.example.com\n",'exclude.list'=>"excluded.example.com\n",'personal.list'=>'MUST_NOT_EXPORT_PRIVATE']as $name=>$raw){$p=$settings['config'].'/lists/'.$name;file_put_contents($p,$raw);chmod($p,0644);}
chown($settings['config'].'/lists/auto.list',65534);
$base=['NFQWS_BASE_ARGS'=>'--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua',
    'NFQWS_EXTRA_ARGS'=>'--hostlist=/opt/etc/nfqws2/lists/user.list --hostlist-auto=/opt/etc/nfqws2/lists/auto.list --hostlist-exclude=/opt/etc/nfqws2/lists/exclude.list',
    'TCP_PORTS'=>'80,443','UDP_PORTS'=>'443'];
$raw=AsusImportConfig::replace('',NfqwsStrategySynthesis::bind(NfqwsStrategySynthesis::blank(),$base));
if($improvement)$raw=AsusImportConfig::replace($raw,[
    'NFQWS_ARGS'=>'--filter-tcp=80,443 --lua-desync=hostfakesplit:host=original.example:midhost=midsld',
    'NFQWS_ARGS_QUIC'=>'--filter-udp=443 --lua-desync=fake:repeats=10',
    'NFQWS_ARGS_CUSTOM'=>'--filter-tcp=443 --hostlist-domains=working.example --lua-desync=multisplit:pos=2']);
$file=$settings['config'].'/nfqws2.conf';file_put_contents($file,$raw);chmod($file,0640);$before=lstat($file);
foreach(['lists','lua','blobs']as $kind)foreach(glob($settings['config'].'/'.$kind.'/*')as $p){$stat=lstat($p);$resources[$p]=['sha256'=>hash_file('sha256',$p),'stat'=>array_intersect_key($stat,array_flip(['uid','gid','mode','ino','nlink']))];}
$s=new NfqwsStrategyPickerState($settings['web_config'].'/strategy-picker');$cfg=new NfqwsStrategyPickerConfig($s,$file);$j=$cfg->snapshot(false);$id=$j['id'];
$stock=array_values(array_filter(array_map('trim',explode("\n",AsusDpiOptions::metadata()['files']['domains.txt'])),fn($line)=>$line!==''&&!str_starts_with($line,'#')));
$domains=NfqwsStrategyPickerGoals::probeDomains($stock,'all');
$budget=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(4,3000000,0),count($domains));
$j+=['request_id'=>bin2hex(random_bytes(16)),'extended'=>false,'search'=>'synthesis','goal'=>'all','custom_only'=>!$native,'custom_hosts'=>['alpha.example.com','beta.example.com','delta.example.com','epsilon.example.com','gamma.example.com'],
    'probe_domains'=>$domains,'budget'=>NfqwsStrategyPickerBudget::custom($budget,5)];
if($mixed)$j['custom_hosts']=['1.1.1.1','8.8.4.4','8.8.8.8','alpha.example.com','beta.example.com'];
if($improvement||$fromScratch){unset($j['custom_hosts'],$j['custom_only']);$j['budget']=$budget;}
$pool=$argv[2]??null;
if($pool!==null){
    $selection=NfqwsStrategyPickerRequest::selection(false,'all',true,($improvement||$fromScratch)?null:['hosts'=>$j['custom_hosts'],'only'=>$j['custom_only']],$pool,$argv[4]??'1');
    $choice=NfqwsStrategyPickerConcurrency::plan($pool,$budget,['cores'=>4,'available_kib'=>3000000,'fd_soft'=>2048]);
    $j=array_replace($j,$selection,['selection_sha256'=>NfqwsStrategyPickerRequest::digest($selection),
        'concurrency_choice'=>NfqwsStrategyPickerConcurrency::record($choice),'probe_domains'=>$domains,
        'budget'=>($improvement||$fromScratch)?$choice['budget']:NfqwsStrategyPickerBudget::custom($choice['budget'],5)]);
}
$j['resources_sha256']=(new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'resourcesFingerprint'))->invoke(new NfqwsStrategyPickerRuntime($s,$cfg));
$j['deadline']=null;$j['started_uptime']=AsusUpdateStore::uptime();$s->write($j);
if($recover)file_put_contents(($j['rounds']??1)>1?'/tmp/fixture-corrupt-pool-round2':'/tmp/fixture-corrupt-pool','once');
$prefix=['/usr/bin/php8-cgi','-n','-d','register_argc_argv=1','-d','max_execution_time=0','-d','max_input_time=0','-d','memory_limit=64M','-q','-f'];
$runtime=$web.'/strategy-picker-runtime.php';$work=null;$guard=null;
function awaitActor($s,$role,$id,$process){for($i=0;$i<100;$i++){$r=$s->read('actor-'.$role.'.json');if(($r['id']??null)===$id&&NfqwsStrategyPickerRuntime::sameActor($r['identity']??null))return $r['identity'];if(!proc_get_status($process)['running'])throw new RuntimeException('fixture_'.$role.'_early_exit');usleep(100000);}throw new RuntimeException('fixture_'.$role.'_missing');}
try{
    $work=proc_open([...$prefix,'/fixtures/worker.php','--',$web,$s->root,$id,$runtime,'--','work',$id],
        [0=>['file','/dev/null','r'],1=>['file','/tmp/worker.log','w'],2=>['file','/tmp/worker.err','w']],$pipes);
    $workProof=awaitActor($s,'work',$id,$work);
    $guard=proc_open([...$prefix,$runtime,'--','guard',$id],
        [0=>['file','/dev/null','r'],1=>['file','/tmp/guard.log','w'],2=>['file','/tmp/guard.err','w']],$pipes);
    $guardProof=awaitActor($s,'guard',$id,$guard);
    for($i=0;$i<900&&proc_get_status($work)['running'];$i++)usleep(100000);
    if(proc_get_status($work)['running'])throw new RuntimeException('fixture_worker_timeout');proc_close($work);$work=null;
    for($i=0;$i<250&&proc_get_status($guard)['running'];$i++)usleep(100000);
    if(proc_get_status($guard)['running'])throw new RuntimeException('fixture_guard_timeout: '.json_encode([$s->read()['state'],$s->read()['phase'],substr(file_get_contents('/tmp/worker.log'),0,3000)]));proc_close($guard);$guard=null;
    $j=$s->read();
    if($recover||$limitedStorage||$comparison==='strong-original'){
        $sourceResources=true;
        foreach($resources as $path=>$expected){clearstatcache(true,$path);$stat=lstat($path);$sourceResources=$sourceResources&&hash_file('sha256',$path)===$expected['sha256']&&array_intersect_key($stat,array_flip(['uid','gid','mode','ino','nlink']))===$expected['stat'];}
        clearstatcache(true,$file);$after=lstat($file);
        $operations=[];
        if($comparison==='strong-original'){
            $runtimeObject=new NfqwsStrategyPickerRuntime($s,$cfg);
            $beforeAttempt=hash_file('sha256',$s->path('state.json'));
            foreach(['pickerapply','pickerexport'] as $command){
                try{$runtimeObject->dispatch(['cmd'=>$command,'id'=>$id,'csrf_token'=>'fixture']);$operations[$command]='accepted';}
                catch(Throwable $error){$operations[$command]=$error->getMessage();}
            }
            $operations['unchanged']=hash_file('sha256',$s->path('state.json'))===$beforeAttempt;
        }
        echo json_encode(['state'=>$j['state'],'code'=>$j['code']??null,'restored'=>$j['restored']??false,
            'generation'=>$j['generation']??null,'winner'=>$j['winner']??null,'generated'=>$j['generated']??null,'operations'=>$operations,
            'original_config'=>$cfg->raw()===$raw,'config_metadata'=>array_intersect_key($before,array_flip(['uid','gid','mode']))===array_intersect_key($after,array_flip(['uid','gid','mode'])),
            'source_resources'=>$sourceResources,'service_off'=>!is_file('/tmp/fixture-service-on'),
            'worker_gone'=>!NfqwsStrategyPickerRuntime::sameActor($workProof),'guard_gone'=>!NfqwsStrategyPickerRuntime::sameActor($guardProof),'series'=>$j['series']??null])."\n";
        return;
    }
    if($j['state']!=='completed'||!($j['generation']['verified']??false))throw new RuntimeException('fixture_generation_failed: '.json_encode([
        'state'=>$j['state'],'phase'=>$j['phase'],'code'=>$j['code']??null,'profiles'=>count($j['profiles']),
        'samples'=>count($j['custom_sample_refs']??[]),'last_worker_memory'=>$j['last_worker_memory']??null,'restored'=>$j['restored']??null,
        'worker'=>file_get_contents('/tmp/worker.log')]));
    $sourceResources=true;foreach($resources as $path=>$expected){clearstatcache(true,$path);$stat=lstat($path);$sourceResources=$sourceResources&&hash_file('sha256',$path)===$expected['sha256']&&array_intersect_key($stat,array_flip(['uid','gid','mode','ino','nlink']))===$expected['stat'];}
    $fresh=[];foreach(['pickerstatus','pickerreport','pickerexport']as $command){
        $read=NfqwsPlatform::run(['/usr/bin/php8-cgi','-n','-d','register_argc_argv=1','-d','memory_limit=8M','-q','-f','/fixtures/read.php','--',$web,$s->root,$id,$command],20,[],4096);
        if($read['status']!==0)throw new RuntimeException('fixture_fresh_'.$command.': '.json_encode($read));
        $fresh[]=json_decode(implode("\n",$read['output']),true,32,JSON_THROW_ON_ERROR);
    }
    $runtimeObject=new NfqwsStrategyPickerRuntime($s,$cfg);$bundle=(new ReflectionMethod($runtimeObject,'synthesisExport'))->invoke($runtimeObject,$id,false);$doc=AsusImportDocument::read([$bundle['raw']]);
    $selected=null;$zero=null;foreach($j['profiles']as $i=>$profile){
        if($profile['id'].':'.($profile['recipe']??'')===$j['generated'])$selected=$i;
        if(($profile['rank']['reason']??null)==='zero_baseline')$zero=$i;
    }
    if($selected===null||$zero===null)throw new RuntimeException('fixture_final_profile');
    if($fromScratch){
        // A missing port setting makes the saved variant incomplete. Checking
        // the result must leave both the real fixture config and journal alone.
        $incomplete=$j;
        unset($incomplete['profiles'][$selected]['variant']['TCP_PORTS']);
        $s->write($incomplete);
        try{
            $beforeCheck=hash_file('sha256',$s->path('state.json'));
            $recheck=[];
            foreach(['apply','export'] as $operation){
                try{
                    if($operation==='export')$runtimeObject->dispatch(['cmd'=>'pickerexport','id'=>$id,'csrf_token'=>'fixture']);
                    else $runtimeObject->apply($id);
                    $recheck[$operation]='accepted';
                }catch(Throwable $error){$recheck[$operation]=$error->getMessage();}
            }
            $recheck['unchanged']=$cfg->raw()===$raw&&hash_file('sha256',$s->path('state.json'))===$beforeCheck;
        }finally{$s->write($j);}
        $currentBased=0;$reports=[];
        for($n=1;$n<=($j['rounds']??1);$n++){
            $round=$s->round($n)->read();$reports[]=$round!==null;
            foreach($round['profiles']??[]as $profile)if(($profile['components']['basis']??'empty')==='current')$currentBased++;
        }
        $trace=json_decode(file_get_contents('/tmp/fixture-native-trials.json'),true,64,JSON_THROW_ON_ERROR);$cold=[];
        foreach($trace as $i=>$trial)if(($trial['phases'][0]??null)!=='warming')$cold[]=$i+1;
        $emptyOriginal=true;foreach(AsusImportConfig::parse($raw)as $key=>$value)if(str_starts_with($key,'NFQWS_ARGS')){preg_match_all('/--lua-desync=([^\s]+)/',$value,$methods);foreach($methods[1]as $method)if($method!=='pass')$emptyOriginal=false;}
        $beforeRetry=hash_file('sha256',$s->path('state.json'));
        try{$runtimeObject->start(bin2hex(random_bytes(16)),false,'all',true,null,$pool,null,'1');$single='accepted';}catch(Throwable $e){$single=$e->getMessage();}
        $singleUnchanged=hash_file('sha256',$s->path('state.json'))===$beforeRetry&&$cfg->raw()===$raw;
        $same=$runtimeObject->start($j['request_id'],false,'all',true,null,$pool,null);
        $newPlan=$runtimeObject->dispatch(['cmd'=>'pickerplan','csrf_token'=>'fixture','search'=>'synthesis','extended'=>'0','goal'=>'all','concurrency'=>$pool]);
        echo json_encode(['state'=>$j['state'],'restored'=>$j['restored'],'winner'=>is_string($j['winner']??null),'generated'=>is_string($j['generated']??null),
            'original_config'=>$cfg->raw()===$raw,'source_resources'=>$sourceResources,'service_off'=>!is_file('/tmp/fixture-service-on'),
            'worker_gone'=>!NfqwsStrategyPickerRuntime::sameActor($workProof),'guard_gone'=>!NfqwsStrategyPickerRuntime::sameActor($guardProof),
            'empty_original_without_strategy'=>$emptyOriginal,'isolated_new_user_no_previous_history'=>true,
            'requested'=>$j['concurrency_choice']['requested'],'effective'=>$j['concurrency_choice']['effective'],
            'series'=>$j['series'],'round_reports'=>$reports,'trace'=>$trace,'current_based_candidates'=>$currentBased,'cold_trials'=>$cold,
            'incomplete_variant'=>$recheck,
            'new_one_round_result'=>$single,'new_one_round_journal_and_config_unchanged'=>$singleUnchanged,
            'same_missing_count_request_id_preserved'=>($same['job']['id']??null)===$id,'new_default_preview_rounds'=>$newPlan['selection']['rounds']??null])."\n";
        return;
    }
    if($improvement){
        $profile=$j['profiles'][$selected];$lib=(new ReflectionMethod($runtimeObject,'library'))->invoke($runtimeObject);$entry=$lib->entry($profile['id']);
        $matchesBase=($profile['components']['basis']??'empty')==='empty'&&$entry['id']===$j['profiles'][$zero]['id']&&
            $profile['variant']===NfqwsStrategySynthesis::bind($profile['components'],$entry['config']);
        $changed=$j;$changed['profiles'][$selected]['variant']['NFQWS_ARGS_CUSTOM'].=' --lua-desync=drop';$s->write($changed);
        $tamper=[];foreach(['export','apply','apply_worker']as $operation){
            if($operation==='apply_worker'){$applying=$changed;$applying['state']='applying';$applying['restored']=false;$s->write($applying);}
            $hash=hash_file('sha256',$s->path('state.json'));
            try{
                if($operation==='export')(new ReflectionMethod($runtimeObject,'synthesisExport'))->invoke($runtimeObject,$id,false);
                elseif($operation==='apply_worker')(new ReflectionMethod($runtimeObject,'applyWork'))->invoke($runtimeObject);
                else $runtimeObject->apply($id);
                $tamper[$operation]='accepted';
            }catch(Throwable $e){$tamper[$operation]=$e->getMessage();}
            $tamper[$operation.'_unchanged']=$cfg->raw()===$raw&&!is_file('/tmp/fixture-service-on')&&hash_file('sha256',$s->path('state.json'))===$hash;
        }
        $s->write($j);
        $out=['state'=>$j['state'],'restored'=>$j['restored'],'winner'=>$j['winner']!==null,'generated'=>$j['generated']!==null,
            'original_config'=>$cfg->raw()===$raw,'source_resources'=>$sourceResources,'service_off'=>!is_file('/tmp/fixture-service-on'),
            'worker_gone'=>!NfqwsStrategyPickerRuntime::sameActor($workProof),'guard_gone'=>!NfqwsStrategyPickerRuntime::sameActor($guardProof),
            'selected_matches_empty_kit'=>$matchesBase,
            'complete_dependencies'=>$doc['audit']['complete'],'generation'=>$j['generation'],'matrix'=>$j['matrix'],
            'requested'=>$j['concurrency_choice']['requested'],'effective'=>$j['concurrency_choice']['effective'],'current_variant_tamper'=>$tamper,
            'series'=>$j['series']??null,'round_reports'=>isset($j['series'])?array_map(fn($i)=>$s->round($i)->read()!==null,range(1,$j['rounds'])):[]];
        require '/fixtures/applied.php';$out['applied_lifecycle']=fixtureAppliedLifecycle($runtimeObject,$s,$cfg,$j,false);
        echo json_encode($out)."\n";
        return;
    }
    $tamper=[];
    $cases=['replayed_sample','edited_recipe','edited_variant','missing_repeat','missing_zero','duplicate_zero',
        'duplicate_selected','changed_hosts','claims_only','native_regression','deleted_artifact','edited_artifact'];
    if($mixed)$cases=array_merge($cases,['missing_ip','changed_manifest','missing_tcp_shields','target_policy_demotion']);
    foreach($cases as $case){
        $changed=$j;$artifact=null;$artifactRaw=null;$held=null;
        switch($case){
            case 'replayed_sample':$changed['profiles'][$selected]['custom_runs'][1]=$changed['profiles'][$selected]['custom_runs'][0];break;
            case 'edited_recipe':$changed['profiles'][$selected]['components']=NfqwsStrategySynthesis::blank();break;
            case 'edited_variant':$changed['profiles'][$selected]['variant']['NFQWS_ARGS'].=' --lua-desync=drop';break;
            case 'missing_repeat':array_pop($changed['profiles'][$selected]['custom_runs']);break;
            case 'missing_zero':array_splice($changed['profiles'],$zero,1);break;
            case 'duplicate_zero':$changed['profiles'][]=$changed['profiles'][$zero];break;
            case 'duplicate_selected':$changed['profiles'][]=$changed['profiles'][$selected];break;
            case 'changed_hosts':$changed['custom_hosts'][0]='omega.example.com';sort($changed['custom_hosts']);break;
            case 'claims_only':$changed['generation']['from_zero']['gain']=999;break;
            case 'native_regression':$changed['profiles'][$selected]['runs'][0]['metrics']['tls12']['ok']=0;break;
            case 'missing_ip':
                foreach($changed['profiles'][$selected]['components']['overrides']as &$o)if(isset($o['addresses'])){array_pop($o['addresses']);break;}unset($o);break;
            case 'changed_manifest':$changed['custom_manifest']['pins'][0]['address']='9.9.9.9';break;
            case 'missing_tcp_shields':
                $recipe=&$changed['profiles'][$selected]['components'];
                $recipe['custom_scope']['protected_domains']=array_values(array_filter($recipe['custom_scope']['protected_domains'],static fn($h)=>!str_starts_with($h,'cdn-')));
                foreach($recipe['overrides']as &$o)if(isset($o['domains']))$o['domains']=array_values(array_filter($o['domains'],static fn($h)=>!str_starts_with($h,'cdn-')));unset($o,$recipe);break;
            case 'target_policy_demotion':unset($changed['custom_target_policy'],$changed['custom_targets']);break;
            default:
                $sample=$j['profiles'][$selected]['custom_runs'][0]['sample_id'];
                $sampleRoot=isset($j['series'])?$s->round($j['series']['selected'])->root:$s->root;
                $artifact=$sampleRoot.'/custom-'.$id.'-'.$sample.'.json';
                $artifactRaw=file_get_contents($artifact);
                if($case==='deleted_artifact'){$held=$artifact.'.held';rename($artifact,$held);}
                else file_put_contents($artifact,$artifactRaw."\n");
        }
        $s->write($changed);$journalBefore=hash_file('sha256',$s->path('state.json'));$result=[];
        try{
            foreach(['export','apply','apply_worker']as $operation){
                if($operation==='apply_worker'){
                    $applying=$changed;$applying['state']='applying';$applying['restored']=false;$s->write($applying);
                    $workerBefore=hash_file('sha256',$s->path('state.json'));
                }
                try{
                    if($operation==='export')(new ReflectionMethod($runtimeObject,'synthesisExport'))->invoke($runtimeObject,$id,false);
                    elseif($operation==='apply_worker')(new ReflectionMethod($runtimeObject,'applyWork'))->invoke($runtimeObject);
                    else $runtimeObject->apply($id);
                    $result[$operation]='accepted';
                }catch(Throwable $e){$result[$operation]=$e->getMessage();}
                if($operation==='apply_worker'){
                    $result['worker_no_mutation']=hash_file('sha256',$s->path('state.json'))===$workerBefore;$s->write($changed);
                }
            }
            $result['no_mutation']=$cfg->raw()===$raw&&!is_file('/tmp/fixture-service-on')&&
                hash_file('sha256',$s->path('state.json'))===$journalBefore;
            $public=$runtimeObject->status()['job'];$result['status_blocked']=$public['can_apply']===false&&
                $public['can_export']===false&&$public['generation']['verified']===false;
            $tamper[$case]=$result;
        }finally{
            if($held!==null)rename($held,$artifact);
            elseif($artifact!==null)file_put_contents($artifact,$artifactRaw);
            $s->write($j);
        }
    }
    $validApply=[];foreach(['admission','worker']as $stage){
        if($stage==='worker'){$applying=$j;$applying['state']='applying';$applying['restored']=false;$s->write($applying);}
        try{if($stage==='worker')(new ReflectionMethod($runtimeObject,'applyWork'))->invoke($runtimeObject);else $runtimeObject->apply($id);$validApply[$stage]='accepted';}
        catch(Throwable $e){$validApply[$stage]=$e->getMessage();}
        finally{$s->write($j);}
    }
    $retries=[];$post=['cmd'=>'pickersynthesize','csrf_token'=>'fixture','consent'=>'test','request_id'=>$j['request_id'],
        'goal'=>'all','custom_sites'=>implode("\n",array_map(static fn($h)=>'https://'.strtoupper($h).'/private?token=DO_NOT_EXPORT_DIAGNOSTIC',array_reverse($j['custom_hosts']))),
        'custom_only'=>$j['custom_only']?'1':'0'];
    if($pool!==null)$post['concurrency']=$pool;
    if(isset($j['rounds']))$post['rounds']=(string)$j['rounds'];
    $mixedDispatch=null;
    if($mixed)$mixedDispatch=($runtimeObject->dispatch($post)['job']['id']??null)===$id;
    $retryBefore=hash_file('sha256',$s->path('state.json'));
    foreach(['same','host_change','mode_change','search_change','new_request']as $case){
        $request=$post;
        if($case==='host_change')$request['custom_sites']='other.example.com';
        if($case==='mode_change')$request['custom_only']=$request['custom_only']==='1'?'0':'1';
        if($case==='search_change'){$request['cmd']='pickerstart';unset($request['custom_sites'],$request['custom_only']);}
        if($case==='new_request')$request['request_id']=bin2hex(random_bytes(16));
        try{
            $answer=$runtimeObject->dispatch($request);
            $retries[$case]=($answer['job']['id']??null)===$id?'same_job':'wrong_job';}
        catch(Throwable $e){$retries[$case]=$e->getMessage();}
        if(hash_file('sha256',$s->path('state.json'))!==$retryBefore)throw new RuntimeException('fixture_retry_mutated_report');
    }
    $list=null;foreach($doc['resources']as $resource)if($resource['name']==='synthesis-user.list')$list=base64_decode($resource['data_base64'],true);
    $scope=$list===null?[]:array_values(array_filter(explode("\n",trim($list))));sort($scope);
    $allDeps=true;foreach($doc['dependencies']as $dep)$allDeps=$allDeps&&$dep['included'];clearstatcache(true,$file);$after=lstat($file);
    $decoded='';foreach(json_decode($bundle['raw'],true)['files']as $f)$decoded.=base64_decode($f['data_base64'],true);
    $concurrencyTamper=null;
    if($pool!==null){
        // Even a coherently rebound request/budget cannot relabel old scores.
        $changed=$j;$changed['concurrency']='33';$changed['concurrency_choice']['requested']='33';
        $changed['concurrency_choice']['effective']=33;$changed['budget']['concurrency']=33;
        $selection=NfqwsStrategyPickerRequest::selection(false,'all',true,['hosts'=>$j['custom_hosts'],'only'=>$j['custom_only']],'33');
        $changed['selection_sha256']=NfqwsStrategyPickerRequest::digest($selection);$s->write($changed);
        $beforeTamper=hash_file('sha256',$s->path('state.json'));$concurrencyTamper=[];
        foreach(['export','apply','apply_worker']as $operation){
            try{
                if($operation==='export')(new ReflectionMethod($runtimeObject,'synthesisExport'))->invoke($runtimeObject,$id,false);
                elseif($operation==='apply_worker')(new ReflectionMethod($runtimeObject,'applyWork'))->invoke($runtimeObject);
                else $runtimeObject->apply($id);
                $concurrencyTamper[$operation]='accepted';
            }catch(Throwable $e){$concurrencyTamper[$operation]=$e->getMessage();}
        }
        $concurrencyTamper['no_mutation']=$cfg->raw()===$raw&&!is_file('/tmp/fixture-service-on')&&hash_file('sha256',$s->path('state.json'))===$beforeTamper;
        $s->write($j);
    }
    $out=['matrix'=>$j['matrix'],'platform'=>$platform,'state'=>$j['state'],'restored'=>$j['restored'],'generation'=>$j['generation'],
        'winner'=>$j['winner']!==null,'generated'=>$j['generated']!==null,'profiles'=>count($j['profiles']),
        'samples'=>count($j['custom_sample_refs']??[]),'scope'=>$scope,'resource_count'=>count($doc['resources']),
        'complete_dependencies'=>$allDeps,'personal_file_not_exported'=>!in_array('personal.list',array_column($doc['resources'],'name'),true)&&!str_contains($decoded,'MUST_NOT_EXPORT_PRIVATE'),
        'diagnostics_not_exported'=>!str_contains($decoded,'DO_NOT_EXPORT_DIAGNOSTIC'),'journal_bytes'=>filesize($s->path('state.json')),
        'original_config'=>$cfg->raw()===$raw,'config_metadata'=>array_intersect_key($before,array_flip(['uid','gid','mode']))===array_intersect_key($after,array_flip(['uid','gid','mode'])),
        'source_resources'=>$sourceResources,'service_off'=>!is_file('/tmp/fixture-service-on'),
        'worker_gone'=>!NfqwsStrategyPickerRuntime::sameActor($workProof),'guard_gone'=>!NfqwsStrategyPickerRuntime::sameActor($guardProof),
        'worker'=>json_decode(trim(file_get_contents('/tmp/worker.log')),true),'fresh_requests'=>$fresh,'tamper_checks'=>$tamper,'valid_apply_gate'=>$validApply,'request_retries'=>$retries,
        'public_status'=>$runtimeObject->status(),'export_context'=>$decoded,'concurrency_tamper'=>$concurrencyTamper,
        'mixed'=>$mixed,'mixed_dispatch_verified'=>$mixedDispatch,'selected_components'=>$mixed?$j['profiles'][$selected]['components']:null,'series'=>$j['series']??null,
        'round_sample_counts'=>isset($j['series'])?array_map(fn($i)=>count($s->round($i)->read()['custom_sample_refs']??[]),range(1,$j['rounds'])):[]];
    require '/fixtures/applied.php';$out['applied_lifecycle']=fixtureAppliedLifecycle($runtimeObject,$s,$cfg,$j,$native);
    echo json_encode($out,JSON_THROW_ON_ERROR)."\n";
}finally{
    foreach([$guard,$work]as $p)if(is_resource($p)){if(proc_get_status($p)['running'])proc_terminate($p,9);proc_close($p);}
    foreach(['/tmp/worker.err','/tmp/guard.err']as $p)if(is_file($p)&&filesize($p))file_put_contents('php://stderr',file_get_contents($p));
}
