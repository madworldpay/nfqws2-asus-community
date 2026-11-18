<?php
/** Real Apply/start bodies with no Detector or background process launch. */
function fixtureAppliedLifecycle($r,$s,$cfg,$complete,$running):array
{
    $source='';foreach(['applyWork','start']as $method){
        $m=new ReflectionMethod(NfqwsStrategyPickerRuntime::class,$method);
        $lines=file($m->getFileName());$body=implode('',array_slice($lines,$m->getStartLine()-1,$m->getEndLine()-$m->getStartLine()+1));
        $source.=preg_replace('/private function applyWork/','public function applyWork',$body);
    }
    eval('final class AppliedLifecycleFixture {
      public bool $launched=false;
      private array $synthesisExplored=[];
      public function __construct(private NfqwsStrategyPickerState $store,private NfqwsStrategyPickerConfig $config,private NfqwsStrategyPickerRuntime $runtime){}
      public function __call($name,$args){return (new ReflectionMethod($this->runtime,$name))->invoke($this->runtime,...$args);}
      private function preflight():void{}
      private function checkpoint():void{if(hash("sha256",$this->config->raw())!==$this->store->read()["current"])throw new RuntimeException("source_changed");}
      private function launchPair(string $id):void{$this->launched=true;}
      public static function error(Throwable $e):string{return NfqwsStrategyPickerRuntime::error($e);}
    '.$source.'}');
    $f=new AppliedLifecycleFixture($s,$cfg,$r);$j=$complete;$j['state']='applying';$j['restored']=false;$j['running_before']=$running;
    $s->write($j);$out=[];
    try{
        // Apply with a running original service needs the actual production
        // guard registered before service input, as the ordinary worker does.
        $applyGuard=null;
        try{
            if($running){
                $entry=(new ReflectionClass(NfqwsStrategyPickerRuntime::class))->getFileName();
                $applyGuard=proc_open(['/usr/bin/php8-cgi','-n','-d','register_argc_argv=1','-d','max_execution_time=0','-d','max_input_time=0','-q','-f',$entry,'--','guard',$j['id']],
                    [0=>['file','/dev/null','r'],1=>['file','/tmp/apply-guard.log','w'],2=>['file','/tmp/apply-guard.err','w']],$pipes);
                if(!is_resource($applyGuard))throw new RuntimeException('fixture_apply_guard_launch');
                $guardPid=proc_get_status($applyGuard)['pid'];$ready=false;
                for($i=0;$i<100;$i++){
                    $record=$s->read('actor-guard.json');
                    if(($record['id']??null)===$j['id']&&($record['identity']['pid']??null)===$guardPid&&NfqwsStrategyPickerRuntime::sameActor($record['identity'])){$ready=true;break;}
                    if(!proc_get_status($applyGuard)['running'])break;usleep(20000);
                }
                if(!$ready)throw new RuntimeException('fixture_apply_guard_not_ready');
                $out['apply_guard_registered']=true;
            }
            $f->applyWork();
        }finally{
            if(is_resource($applyGuard)){
                for($i=0;$i<100&&proc_get_status($applyGuard)['running'];$i++)usleep(20000);
                if(proc_get_status($applyGuard)['running'])proc_terminate($applyGuard,9);
                proc_close($applyGuard);
            }
        }
        $applied=$s->read();$raw=$cfg->raw();$out['actually_applied']=$applied['state']==='applied'&&$applied['restored']===false&&$applied['applied_sha256']===hash('sha256',$raw)&&hash('sha256',$raw)!==$complete['original_sha256'];
        $fingerprint=(new ReflectionMethod($r,'resourcesFingerprint'))->invoke($r);
        // A changed config and a verified still-live old actor both block retirement without deleting any evidence.
        $count=count(glob($s->root.'/custom-*.json'));$cfg->replace($raw."# foreign edit\n");
        try{(new ReflectionMethod($r,'clearPrevious'))->invoke($r,$applied);$out['foreign_edits_blocked']=false;}catch(Throwable $e){$out['foreign_edits_blocked']=$e->getMessage()==='source_changed'&&count(glob($s->root.'/custom-*.json'))===$count;}
        $cfg->replace($raw);$applied=$s->read(); // Retain the actual current Config publication binding.
        $child=proc_open(['/bin/sh','-c','sleep .05; exec /bin/sleep 30'],[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes);
        try{
            $childPid=proc_get_status($child)['pid'];$proof=null;
            // proc_open returns before exec; argv is authoritative only after
            // the controlled child reaches its expected final executable.
            for($i=0;$i<100;$i++){
                $proof=NfqwsStrategyPickerRuntime::identity($childPid);
                if(($proof['argv']??null)===['/bin/sleep','30'])break;
                usleep(10000);
            }
            if(($proof['argv']??null)!==['/bin/sleep','30'])throw new RuntimeException('fixture_child_identity_missing');
            $applied['actuator']=$proof;$s->write($applied);
            try{(new ReflectionMethod($r,'clearPrevious'))->invoke($r,$applied);$out['live_actor_blocked']=false;}
            catch(Throwable $e){$out['live_actor_blocked']=$e->getMessage()==='recovery_required'&&count(glob($s->root.'/custom-*.json'))===$count&&NfqwsStrategyPickerRuntime::sameActor($proof);}
        }finally{if(proc_get_status($child)['running'])proc_terminate($child,9);proc_close($child);}
        unset($applied['actuator']);$s->write($applied);
        $beforeAdmission=hash_file('sha256',$s->path('state.json'));$artifacts=count(glob($s->root.'/custom-'.$j['id'].'-*.json'));
        $custom=isset($complete['custom_hosts'])?['hosts'=>$complete['custom_hosts'],'only'=>$complete['custom_only']]:null;
        try{
            $f->start(bin2hex(random_bytes(16)),false,'all',true,$custom,'1');
            $out['inadmissible_pool_retains_previous']=false;
        }catch(Throwable $e){$out['inadmissible_pool_retains_previous']=$e->getMessage()==='concurrency_budget_unavailable'&&
            hash_file('sha256',$s->path('state.json'))===$beforeAdmission&&$cfg->raw()===$raw&&
            count(glob($s->root.'/custom-'.$j['id'].'-*.json'))===$artifacts&&!$f->launched;}
        $pool=$complete['concurrency']??'auto';
        $selection=NfqwsStrategyPickerRequest::selection(false,'all',true,$custom,$pool,'2');
        $plan=$r->previewPlan($selection);
        $out['plan_preview_read_only']=$plan['available']===true&&$plan['concurrency_choice']['requested']===$pool&&
            hash_file('sha256',$s->path('state.json'))===$beforeAdmission&&$cfg->raw()===$raw;
        $cfg->replace($raw."# changed after consent preview\n");
        $beforeStale=hash_file('sha256',$s->path('state.json'));
        try{$f->start(bin2hex(random_bytes(16)),false,'all',true,$custom,$pool,$plan['plan_sha256']);$out['stale_plan_retains_previous']=false;}
        catch(Throwable $e){$out['stale_plan_retains_previous']=$e->getMessage()==='plan_changed'&&
            hash_file('sha256',$s->path('state.json'))===$beforeStale&&
            count(glob($s->root.'/custom-'.$j['id'].'-*.json'))===$artifacts&&!$f->launched;}
        $cfg->replace($raw);
        $f->start(bin2hex(random_bytes(16)),false,'all',true,$custom,$pool,$plan['plan_sha256']);
        $next=$s->read();$out['new_snapshot_is_applied']=$next['id']!==$j['id']&&$next['original_sha256']===hash('sha256',$raw)&&$cfg->raw()===$raw;
        $out['resources_preserved']=$fingerprint===(new ReflectionMethod($r,'resourcesFingerprint'))->invoke($r);
        $out['service_preserved']=is_file('/tmp/fixture-service-on')===$running&&$next['running_before']===$running;
        $out['old_artifacts_retired']=count(glob($s->root.'/custom-'.$j['id'].'-*.json'))===0;
        $out['new_request_launched']=$f->launched;
    }catch(Throwable $e){$out['error']=$e->getMessage();$out['origin']=[basename($e->getFile()),$e->getLine()];}
    return $out;
}
