<?php
require_once __DIR__.'/dpi-install.php';
require_once __DIR__.'/dpi-normalize.php';
require_once __DIR__.'/dpi-analysis.php';
/** All dependencies are internal; no browser-selected command, target, path or environment. */
final class AsusDpiJobs
{
    private AsusDpiStore $store;
    public function __construct(?AsusDpiStore $store=null,private array $deps=[]){$this->store=$store??new AsusDpiStore();}
    private function available(): void
    {
        $cap=isset($this->deps['available'])?($this->deps['available'])():(new AsusDpiInstaller())->availability();
        if(!$cap['available'])throw new RuntimeException($cap['code']);
    }
    private function start(string $request,string $kind,array $params): array
    {
        $this->available();$job=$this->store->reserve($request,$kind,$params);
        if($this->store->claimLaunch($job['id'])) {
            try{if(isset($this->deps['launch']))($this->deps['launch'])($job['id'],$kind);else (new AsusDpiRuntime())->launch($job['id'],$kind);}
            catch(Throwable $e){$this->store->update($job['id'],['state'=>'failed','finished_at'=>time(),'code'=>self::code($e->getMessage())]);throw new RuntimeException(self::code($e->getMessage()));}
        }
        return self::publicJob($job);
    }
    public static function code(string $code): string
    {
        return in_array($code,['ready','consent_required','invalid_request','busy','request_conflict','missing_job','result_unavailable','root_required','unsupported_privileges','unsupported_runtime','unsupported_abi','invalid_state','invalid_clock','insufficient_memory','insufficient_space','https_unavailable','download_failed','download_hash','download_size','download_redirect','untrusted_download','unsupported_binary','not_installed','launch_failed','timed_out','cancelled','output_limit','invalid_dpi','interrupted'],true)?$code:'failed';
    }
    public function startInstall(string $requestId,bool $consent): array
    {if(!$consent)throw new RuntimeException('consent_required');return $this->start($requestId,'install',[]);}
    public function startRun(string $requestId,array $groups,array $heavyConsent,array $options=[]): array
    {
        if($groups===[]||count($groups)>7||array_values(array_unique($groups,SORT_REGULAR))!==$groups)throw new RuntimeException('invalid_request');
        foreach($groups as $g)if(!is_int($g)||$g<0||$g>6)throw new RuntimeException('invalid_request');
        $sort=$groups;sort($sort);if($sort!==$groups)throw new RuntimeException('invalid_request');
        $heavy=array_values(array_intersect($groups,[5,6]));
        if($heavyConsent!==$heavy)throw new RuntimeException($heavy!==[]?'consent_required':'invalid_request');
        $installed=isset($this->deps['installed'])?($this->deps['installed'])():(new AsusDpiInstaller())->installed()['installed'];
        if(!$installed)throw new RuntimeException('not_installed');
        $options=AsusDpiOptions::normalize($options);foreach($groups as $g)AsusDpiOptions::compile($options,$g,'/native');
        return $this->start($requestId,'run',['tests'=>$groups,'heavy_consent'=>$heavyConsent,'options'=>$options]);
    }
    public static function publicJob(array $job): array
    {
        return ['id'=>$job['id'],'kind'=>$job['kind'],'state'=>$job['state'],'started_at'=>$job['started_at'],'finished_at'=>$job['finished_at'],
            'code'=>$job['code'],'tests'=>$job['params']['tests']??[],'completed_tests'=>array_column($job['groups'],'group'),'current_group'=>$job['current_group']??null,'native_available'=>$job['native_available']??false];
    }
    public function status(): array
    {
        $s=$this->store->status();$job=$s['active'];
        if($job!==null) {
            $run='/opt/var/lib/nfqws2-asus/dpi-detector/runs/'.$job['id'];$outcome=null;
            if(is_file($run.'/outcome')&&!is_link($run.'/outcome'))$outcome=trim(file_get_contents($run.'/outcome',false,null,0,32));
            elseif(time()-$job['started_at']>4&&(!isset($job['identity'])||AsusDpiRuntime::identity($job['identity']['pid'])!==$job['identity']))$outcome='interrupted';
            if($outcome!==null) {
                $state=in_array($outcome,['cancelled','timed_out','interrupted'],true)?$outcome:($job['groups']!==[]?'partial':'failed');
                // Unknown death time is conservatively the original start, never
                // the time a browser happens to reopen this panel.
                $endUp=$job['started_uptime'];$finished=$job['started_at'];
                $recorded=trim((string)@file_get_contents($run.'/ended.uptime',false,null,0,32));
                if(is_numeric($recorded)&&(float)$recorded>=$endUp&&(float)$recorded<=$endUp+($job['kind']==='install'?125:1805)){
                    $endUp=(float)$recorded;$finished=min(time(),$job['started_at']+(int)floor($endUp-$job['started_uptime']));
                }
                $patch=['state'=>$state,'finished_at'=>$finished,'finished_uptime'=>$endUp,'code'=>self::code($outcome),'current_group'=>null];
                if($job['kind']==='run'&&$job['groups']!==[]) {
                    $before=$job['context_before']??AsusDpiWorker::unknownContext();$after=AsusDpiWorker::context();
                    if(isset($job['groups'][0]['document']))$patch=array_merge($patch,AsusDpiWorker::resultPatch($job,$job['groups'],$this->store->readOptions($job['id']),$state,$finished,$before,$after,$job['messages']??[]));
                    else $patch['result']=AsusDpiNormalizer::report(['started_at'=>$job['started_at'],'finished_at'=>$finished,'state'=>$state,'tests'=>$job['params']['tests']],$job['groups'],['before'=>$before,'after'=>$after,'changed'=>$before!==$after]);
                }
                $this->store->update($job['id'],$patch);$s=$this->store->status();
            }
        }
        $installer=new AsusDpiInstaller();
        $this->store->cleanupArtifacts(fn($active)=>$installer->cleanupStages($active));
        return ['available'=>$installer->availability(),'installed'=>$installer->installed(),'version'=>AsusDpiCatalog::load()['version'],'default_tests'=>[1,2],
            'active'=>$s['active']===null?null:self::publicJob($s['active']),'history'=>array_map([self::class,'publicJob'],$s['history'])];
    }
    public function stop(string $jobId): array{return (new AsusDpiRuntime())->stop($jobId);}
    public function result(string $jobId): string{return $this->store->readResult($jobId);}
    public function native(string $jobId): string{return $this->store->readNative($jobId);}
    public function deleteResult(string $jobId): void{$this->store->deleteResult($jobId);}
}
final class AsusDpiWorker
{
    private AsusDpiStore $store;
    public function __construct(?AsusDpiStore $store=null,private array $deps=[]){$this->store=$store??new AsusDpiStore();}
    public static function profile(): array {return AsusDpiOptions::metadata()['config'];}
    public static function arguments(string $binary,int $g,array $options=[]): array
    {return AsusDpiOptions::compile($options,$g,$binary)['argv'];}
    public static function resultPatch(array $job,array $groups,array $options,string $state,int $finished,array $before,array $after,array $messages): array
    {
        $c=AsusDpiOptions::compile($options,0,'/native');
        $metadata=['started_at'=>$job['started_at'],'finished_at'=>$finished,'state'=>$state,'tests'=>$job['params']['tests']];
        $context=['before'=>$before,'after'=>$after,'changed'=>$before!==$after];$outcome=[];
        try{$raw=AsusDpiNative::document($metadata,$groups,$context,$c['public_settings'],$c['coverage'],$messages);}
        catch(RuntimeException $e){
            if($e->getMessage()!=='output_limit'||$messages===[])throw $e;
            // Completed groups were checked with terminal headroom. Optional later diagnostics cannot erase them.
            $metadata['state']=in_array($state,['cancelled','timed_out','interrupted'],true)?$state:'partial';
            $metadata['messages_truncated']=true;
            $raw=AsusDpiNative::document($metadata,$groups,$context,$c['public_settings'],$c['coverage'],[['group'=>null,'text'=>'Native output limit reached; later messages omitted.','truncated'=>true]]);
            $outcome=['state'=>$metadata['state'],'code'=>'output_limit'];
        }
        if($groups===[])return array_merge(['native'=>$raw],$outcome);
        try{return array_merge(['native'=>$raw,'result'=>AsusDpiAnalysis::report(json_decode($raw,true,32,JSON_THROW_ON_ERROR))],$outcome);}
        catch(Throwable $e){$doc=json_decode($raw,true,32,JSON_THROW_ON_ERROR);$doc['state']='partial';return ['native'=>json_encode($doc,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR)."\n",'state'=>'partial','code'=>strlen($raw)>262144?'output_limit':'invalid_dpi'];}
    }
    public static function unknownContext(): array{return ['nfqws'=>'unknown','ark'=>'unknown','tun_observed'=>false];}
    public static function context(): array
    {
        $context=self::unknownContext();$modules=@file_get_contents('/proc/modules');
        if(is_string($modules))$context['ark']=preg_match('/^ark\s/m',$modules)?'loaded':'absent';
        $context['nfqws']='stopped';
        foreach(glob('/proc/[0-9]*/comm')?:[] as $file){$name=trim((string)@file_get_contents($file));if(in_array($name,['nfqws','nfqws2'],true)){$context['nfqws']='running';break;}}
        foreach(glob('/sys/class/net/*/tun_flags')?:[] as $file)if(is_file($file)){$context['tun_observed']=true;break;}
        return $context;
    }
    private function work(string $id,array $options): string
    {
        if(isset($this->deps['work']))return ($this->deps['work'])($id);
        $work=(new AsusDpiRuntime())->workdir($id);
        foreach(AsusDpiOptions::compile($options,0,'/native')['files'] as $name=>$raw) {
            $f=fopen($work.'/'.$name,'xb');if(!$f)throw new RuntimeException('invalid_state');chmod($work.'/'.$name,0640);chgrp($work.'/'.$name,65534);
            try{if(fwrite($f,$raw)!==strlen($raw))throw new RuntimeException('insufficient_space');}finally{fclose($f);}
        }
        if(!mkdir($work.'/dpi-detector',0700)||!chown($work.'/dpi-detector',65534)||!chgrp($work.'/dpi-detector',65534))throw new RuntimeException('invalid_state');
        return $work;
    }
    public function run(string $id): void
    {
        $job=$this->store->status()['active'];if(($job['id']??null)!==$id||$job['state']!=='queued')throw new RuntimeException('missing_job');
        $options=$this->store->readOptions($id);$this->store->update($id,['state'=>'running']);$groups=[];$messages=[];$messageBytes=0;$before=self::unknownContext();$after=$before;$state='failed';$code=null;
        try {
            if($job['kind']==='install'){(new AsusDpiInstaller())->install($id);$this->store->update($id,['state'=>'completed','finished_at'=>time()]);return;}
            $context=$this->deps['context']??[self::class,'context'];$before=$context();$this->store->update($id,['context_before'=>$before]);
            $work=$this->work($id,$options);$binary=isset($this->deps['binary'])?($this->deps['binary'])():(new AsusDpiInstaller())->binary();
            foreach($job['params']['tests'] as $g) {
                $this->store->update($id,['current_group'=>$g]);$args=self::arguments($binary,$g,$options);
                $r=isset($this->deps['probe'])?($this->deps['probe'])($id,$args,$work,$options['limits']['group_seconds']):(new AsusDpiRuntime())->probe($id,$args,$work,$options['limits']['group_seconds']);
                $err=$r['stderr']??'';$messageBytes+=strlen($err);if($messageBytes>65536)throw new RuntimeException('output_limit');if($err!=='')$messages[]=['group'=>$g,'text'=>json_decode(json_encode($err,JSON_INVALID_UTF8_SUBSTITUTE))];
                if(($r['exit']??-1)!==0)throw new RuntimeException('probe_failed');
                $candidate=AsusDpiNative::group($r['stdout'],$g);$compiled=AsusDpiOptions::compile($options,$g,$binary);
                AsusDpiNative::document(['started_at'=>$job['started_at'],'finished_at'=>time(),'state'=>'running','tests'=>$job['params']['tests']],array_merge($groups,[$candidate]),['before'=>$before,'after'=>$before,'changed'=>false],$compiled['public_settings'],$compiled['coverage'],$messages,1047552);
                $groups[]=$candidate;$this->store->update($id,['groups'=>$groups,'messages'=>$messages]);
            }
            $state='completed';
        }catch(Throwable $e){$code=AsusDpiJobs::code($e->getMessage());$state=in_array($code,['cancelled','timed_out','interrupted'],true)?$code:($groups!==[]?'partial':'failed');}
        $after=isset($this->deps['context'])?($this->deps['context'])():self::context();
        $patch=['state'=>$state,'finished_at'=>time(),'code'=>$code,'groups'=>$groups,'context_after'=>$after,'current_group'=>null];
        if($job['kind']==='run'){
            try{$patch=array_merge($patch,self::resultPatch($job,$groups,$options,$state,time(),$before,$after,$messages));}
            catch(Throwable $e){$patch['state']='partial';$patch['code']=AsusDpiJobs::code($e->getMessage());}
        }
        $this->store->update($id,$patch);
    }
}
