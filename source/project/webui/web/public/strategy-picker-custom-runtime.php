<?php
/** Internal runtime composition. The caller already owns engine.lock and the
 * mutation writer and keeps this exact candidate active for the whole sample.
 * HTTP activation waits for joint ranking, assembly and export validation. */
trait NfqwsStrategyPickerCustomRuntime
{
    /** Reap the exact recorded leaf, never a merely live PID. The guard can
     * stop it before taking locks, but retires metadata only under engine.lock
     * + writer. Previous-boot records never authorize a signal. */
    private function customReap(bool $boot=false,bool $commit=true):bool
    {
        $j=$this->store->read('state.json',$journalPin);$desc=$j['custom_worker']??null;$actor=$j['actuator']??null;
        $bad=static function():never{throw new RuntimeException('recovery_required');};
        if(($j['actuator_attention']??null)!==null||($j['actuator_intent']??null)!==null)$bad();
        $samples=array_key_exists('custom_sample_pending',$j)||array_key_exists('custom_sample_refs',$j);
        if($desc===null&&($actor===null||$boot&&!$samples))return false;
        $this->config->raw(true);
        if(!is_string($j['id']??null)||!preg_match('/^[a-f0-9]{32}$/D',$j['id'])||
            !is_string($j['boot']??null)||($j['boot']===AsusUpdateStore::boot())===$boot)$bad();
        if($desc!==null){
            $keys=is_array($desc)?array_keys($desc):[];sort($keys);
            if($keys!==['deadline','nonce','payload_sha256','stage']||
                !in_array($desc['stage'],['prepare','probe'],true)||
                !is_string($desc['nonce'])||!preg_match('/^[a-f0-9]{32}$/D',$desc['nonce'])||
                !is_string($desc['payload_sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$desc['payload_sha256'])||
                (!is_int($desc['deadline'])&&!is_float($desc['deadline']))||!is_finite((float)$desc['deadline'])||
                (NfqwsStrategyPickerBudget::overallDeadline($j)!==null&&$desc['deadline']>NfqwsStrategyPickerBudget::overallDeadline($j)))$bad();
            if($desc['stage']==='probe'&&($j['custom_manifest_sha256']??null)!==$desc['payload_sha256'])$bad();
        }
        if($actor!==null){
            $keys=is_array($actor)?array_keys($actor):[];sort($keys);
            // Previous-boot legacy records can authorize metadata retirement
            // only. Live cleanup requires the complete source-observed context.
            $legacy=$boot&&$keys===['argv','boot','pid','ticks'];
            if(!$legacy&&$keys!==['argv','boot','cwd','pid','ticks','uid']||!is_int($actor['pid'])||$actor['pid']<2||
                !is_string($actor['ticks'])||!preg_match('/^[0-9]{1,32}$/D',$actor['ticks'])||
                $actor['boot']!==$j['boot']||!is_array($actor['argv'])||!array_is_list($actor['argv']))$bad();
            if(!$legacy&&(!is_int($actor['uid'])||$actor['uid']!==$this->store->owner()||
                !is_string($actor['cwd'])||!str_starts_with($actor['cwd'],'/')||str_contains($actor['cwd'],"\0")))$bad();
            foreach($actor['argv']as $arg)if(!is_string($arg)||str_contains($arg,"\0"))$bad();
            if($desc!==null&&array_slice($actor['argv'],-5)!==[
                __DIR__.'/strategy-picker-custom-worker.php','--',$desc['stage'],$j['id'],$desc['nonce']])$bad();
        }
        $work=$this->actor('work',$j['id']);
        if($work!==null&&$work['pid']!==getmypid())throw new RuntimeException('busy');
        if(!$boot&&$actor!==null){
            if(self::sameProcess($actor,$exited)){
                self::killTree($actor);
                if(self::sameProcess($actor,$exited))throw new RuntimeException('actuator_stop_failed');
            }
            // Context loss is not verified exit, even when PID/ticks match.
            // Neither case can erase a possible-input/attention record.
            if(!$exited)$bad();
        }
        $this->config->raw(true);$v=$this->store->read('state.json',$actualPin);
        if($v!==$j||$actualPin!==$journalPin)throw new RuntimeException('source_changed');
        if($commit){
            unset($v['custom_worker']);$v['actuator']=null;$this->store->write($v);
        }
        return true;
    }
    private function customRecoverPending(string $id):void
    {
        $j=$this->store->read();if(($j['id']??null)!==$id)throw new RuntimeException('stale_state');
        if(!array_key_exists('custom_sample_pending',$j))return;
        require_once __DIR__.'/strategy-picker-custom-samples.php';
        $samples=new NfqwsStrategyPickerCustomSamples($this->store,
            static function():void{throw new RuntimeException('busy');},null,$this->store->owner());
        $samples->recoverPending($id);
    }
    private function customCheckpoint():void
    {
        $this->checkpoint();
    }
    private function customSample(string $role,int $repeat,string $contextSha):array
    {
        if(!preg_match('/^[a-z0-9][a-z0-9_-]{0,63}$/D',$role)||!in_array($repeat,[1,2],true)||
            !preg_match('/^[a-f0-9]{64}$/D',$contextSha))throw new RuntimeException('invalid_request');
        $this->customCheckpoint();
        require_once __DIR__.'/strategy-picker-custom-samples.php';
        $job=$this->store->read();$config=$job['current']??null;
        if(!is_string($config)||!preg_match('/^[a-f0-9]{64}$/D',$config))throw new RuntimeException('stale_state');
        $context=$this->customContext();
        if(!is_array($context))throw new RuntimeException('incomparable_result');
        ksort($context);
        if(hash('sha256',json_encode($context,JSON_THROW_ON_ERROR))!==$contextSha)
            throw new RuntimeException('incomparable_result');
        $deadline=NfqwsStrategyPickerBudget::overallDeadline($job);
        $preparing=($job['custom_manifest']??null)===null;
        // Reserve full bounded child work plus restoration before beginning
        // the phase; checkpoints during a running child retain its own timer.
        $reserve=120+90*($preparing?2:1);
        if($deadline!==null&&$deadline-AsusUpdateStore::uptime()<$reserve)throw new RuntimeException('timed_out');
        $supervisor=$this->customSupervisor();
        if($preparing)$supervisor->prepare($job['custom_hosts']??[]);
        $samples=new NfqwsStrategyPickerCustomSamples($this->store,fn()=>$this->customCheckpoint(),
            fn()=>$this->customContext(),$this->store->owner());
        return $samples->capture($role,$config,$repeat,$contextSha,fn()=>$supervisor->probe());
    }
}
