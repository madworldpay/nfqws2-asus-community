<?php
require_once __DIR__.'/smartdns-native.php';
require_once __DIR__.'/update-guard.php';

/** Read-only projection is separate from durable, lease-protected reconciliation. */
final class AsusSmartDnsConfigJobs
{
    private NfqwsSmartDnsBackend $backend;
    private int $owner;
    public function __construct(private AsusSmartDnsStore $store,?NfqwsSmartDnsBackend $backend=null,private array $deps=[])
    { $this->backend=$backend??AsusSmartDnsNativeBackend::create($store,new AsusSmartDnsInstaller());$this->owner=$deps['owner']??0; }
    private function now(): float
    { return isset($this->deps['uptime'])?($this->deps['uptime'])():(float)explode(' ',file_get_contents('/proc/uptime'))[0]; }
    private function native(): ?array
    { return isset($this->deps['native'])?($this->deps['native'])():$this->backend->state(); }
    private function healthy(): bool
    { return isset($this->deps['healthy'])?($this->deps['healthy'])()===true:$this->backend->healthy(); }
    private function nativeCode(string $id): ?string
    { return isset($this->deps['native_code'])?($this->deps['native_code'])($id):$this->backend->lastCode($id); }
    private function privateDirectory(string $path,bool $create=false): void
    {
        if ($create && !file_exists($path)) {
            $mask=umask(0077);try {$ok=@mkdir($path,0700);}finally {umask($mask);}
            if (!$ok) throw new RuntimeException('storage_unavailable');
        }
        clearstatcache(true,$path);$s=@lstat($path);
        if (!$s || ($s['mode']&0170000)!==0040000 || $s['uid']!==$this->owner || ($s['mode']&0777)!==0700) throw new RuntimeException('invalid_state');
    }
    private function launch(string $id,string $run): void
    {
        if (isset($this->deps['launch'])) {($this->deps['launch'])($id);return;}
        $bb=AsusDpiRuntime::busybox();
        $p=@proc_open([$bb,'start-stop-daemon','-S','-b','-p',$run.'/guard-launch.pid','-x','/bin/sh','--',NfqwsPlatform::translate('/opt/lib/nfqws2-asus/smartdns/config-worker.sh'),$id],
            [0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C']);
        if (!is_resource($p) || proc_close($p)!==0) throw new RuntimeException('launch_failed');
    }
    /** Bounded cleanup only by a mutator; unknown files/owners are retained. */
    public function cleanup(): void
    {
        $root=$this->store->directory(false);if ($root===null || !file_exists($root.'/jobs')) return;
        $this->privateDirectory($root.'/jobs');$entries=@scandir($root.'/jobs');
        if (!is_array($entries) || count($entries)>130) throw new RuntimeException('output_limit');
        $keep=array_filter([$this->store->transaction()['request_id']??null,$this->native()['request_id']??null]);$eligible=[];
        foreach ($entries as $id) {
            if (!preg_match('/^[a-f0-9]{32}$/D',$id) || in_array($id,$keep,true)) continue;
            $path=$root.'/jobs/'.$id;
            try {$this->privateDirectory($path);}catch (Throwable $e) {continue;}
            $owner=$this->validationOwner(['request_id'=>$id]);
            if (!$owner['known'] || $owner['guard_alive'] || $owner['anchor_alive'] || $owner['worker_alive']) continue;
            $names=@scandir($path);if (!is_array($names) || count($names)>80) continue;
            $files=[];$dirs=[];$safe=true;
            foreach (array_diff($names,['.','..']) as $name) {
                if (preg_match('/^attempt-[1-9][0-9]{0,2}$/D',$name)) {
                    $child=$path.'/'.$name;
                    try {$this->privateDirectory($child);}catch (Throwable $e) {$safe=false;break;}
                    $children=@scandir($child);
                    if (!is_array($children) || array_diff($children,['.','..','candidate.conf','candidate.pid'])) {$safe=false;break;}
                    foreach (array_diff($children,['.','..']) as $file) $files[]=$child.'/'.$file;
                    $dirs[]=$child;continue;
                }
                if (!in_array($name,['guard','anchor','worker','done','outcome','.guard','.anchor','.outcome','runtime.conf','runtime.pid','engine.digest','guard-launch.pid','guardian-launch.pid'],true)) {$safe=false;break;}
                $files[]=$path.'/'.$name;
            }
            foreach ($files as $file) {
                $s=@lstat($file);
                if (!$s || ($s['mode']&0170000)!==0100000 || $s['uid']!==$this->owner || ($s['mode']&0777)!==0600 || $s['nlink']!==1 || $s['size']>65536) {$safe=false;break;}
            }
            if ($safe) $eligible[]=['path'=>$path,'files'=>$files,'dirs'=>$dirs,'mtime'=>filemtime($path)];
        }
        usort($eligible,fn($a,$b)=>$b['mtime']<=>$a['mtime']);
        foreach (array_slice($eligible,3) as $run) {
            foreach ($run['files'] as $file) if (!@unlink($file)) throw new RuntimeException('storage_unavailable');
            foreach ($run['dirs'] as $dir) if (!@rmdir($dir)) throw new RuntimeException('storage_unavailable');
            if (!@rmdir($run['path'])) throw new RuntimeException('storage_unavailable');
        }
    }
    /** The HTTP lease is handed off to the native guardian before returning. */
    public function start(string $id,string $hash,string $source='draft'): array
    {
        if (!preg_match('/^[a-f0-9]{32}$/D',$id) || !preg_match('/^[a-f0-9]{64}$/D',$hash) || !in_array($source,['draft','confirmed'],true)) throw new RuntimeException('invalid_request');
        $lease=isset($this->deps['lease'])?($this->deps['lease'])():(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
        try {
            $this->reconcile();$receipt=$this->store->receipt($id);
            if ($receipt!==null) {
                if ($receipt['job']['profile_hash']!==$hash || !array_key_exists('preview_id',$receipt['job']) || $receipt['job']['backup_id']!==null) throw new RuntimeException('request_conflict');
                if (($receipt['job']['profile_source']??'draft')!==$source) throw new RuntimeException('request_conflict');
                if ($source==='confirmed') $this->store->candidate($receipt['job']);
                return $receipt['status'];
            }
            if ($this->store->active()!==null) throw new RuntimeException('restore_required');
            $baseline=isset($this->deps['baseline'])?($this->deps['baseline'])():$this->backend->baseline();
            $root=$this->store->directory(true);$this->privateDirectory($root.'/jobs',true);
            $this->cleanup();
            $run=$root.'/jobs/'.$id;
            // Never adopt or replay a preexisting run, including stale proofs.
            if (file_exists($run) || is_link($run)) throw new RuntimeException('invalid_state');
            $result=$this->store->beginValidation($id,$hash,$baseline['hash'],$source);
            try {
                $this->privateDirectory($run,true);$this->launch($id,$run);
                $end=hrtime(true)+3000000000;
                do {
                    $job=$this->store->transaction();
                    if (($job['request_id']??null)!==$id) throw new RuntimeException('invalid_state');
                    if ($job['state']!=='validating') return $this->status();
                    $proof=$this->validationOwner($job);
                    if ($proof['guard_alive'] && $proof['anchor_alive']) return $this->status();
                    usleep(10000);
                } while (hrtime(true)<$end);
                throw new RuntimeException('launch_failed');
            } catch (Throwable $e) {
                $job=$this->store->transaction();$proof=$this->validationOwner($job);
                if ($proof['known'] && !$proof['guard_alive'] && !$proof['anchor_alive'] && !$proof['worker_alive'] && $job['state']==='validating')
                    $this->store->transition($id,['validating'],['state'=>'failed','code'=>'launch_failed']);
                throw new RuntimeException('launch_failed');
            }
        } finally {if (is_resource($lease)) {flock($lease,LOCK_UN);fclose($lease);}}
    }
    /** A published preview can precede the validator releasing its lease.
     * Observe its fixed owners before starting another guard; never replay a
     * validation, signal a process, or change the DNS journal while waiting. */
    public function awaitValidationRelease(string $previewId,float $budget=8): void
    {
        $end=hrtime(true)+min(8,max(0,$budget))*1000000000;
        do {
            try {$job=$this->store->transaction();}
            catch (RuntimeException $error) {
                if ($error->getMessage()!=='busy' || hrtime(true)>=$end) throw $error;
                usleep(100000);continue;
            }
            if ($job===null || $job['state']!=='preview_ready' || ($job['preview_id']??null)!==$previewId) return;
            $owner=$this->validationOwner($job);
            if ($owner['known'] && !$owner['guard_alive'] && !$owner['anchor_alive'] && !$owner['worker_alive']) return;
            if (hrtime(true)>=$end) throw new RuntimeException('busy');
            usleep(100000);
        } while (true);
    }
    private function validationOwner(array $job): array
    {
        if (isset($this->deps['validation_owner'])) return ($this->deps['validation_owner'])($job);
        $result=['known'=>true,'guard_alive'=>false,'anchor_alive'=>false,'worker_alive'=>false,'code'=>null];
        $root=$this->store->directory(false);if ($root===null) return $result;
        $run=$root.'/jobs/'.$job['request_id'];
        foreach ([$root.'/jobs',$run] as $dir) {
            $s=@lstat($dir);if (!$s) return $result;
            if (($s['mode']&0170000)!==0040000 || $s['uid']!==$this->owner || ($s['mode']&0777)!==0700) { $result['known']=false;return $result; }
        }
        foreach (['guard'=>4,'anchor'=>3,'worker'=>3] as $name=>$fields) {
            $path=$run.'/'.$name;$s=@lstat($path);if (!$s) continue;
            if (($s['mode']&0170000)!==0100000 || $s['uid']!==$this->owner || $s['nlink']!==1 || ($s['mode']&0777)!==0600 || $s['size']>512) {$result['known']=false;continue;}
            $raw=@file_get_contents($path);$v=is_string($raw)?explode(' ',trim($raw)):[];
            if (count($v)!==$fields || !preg_match('/^[1-9][0-9]{0,9}$/D',$v[0]??'') || !preg_match('/^[1-9][0-9]{0,19}$/D',$v[1]??'') || !preg_match('/^[a-f0-9-]{36}$/D',$v[2]??'')) {$result['known']=false;continue;}
            $identity=AsusDpiRuntime::identity((int)$v[0]);
            if ($identity!==null && $identity['boot_id']===$v[2] && $identity['starttime']===$v[1]) {
                $status=@file_get_contents('/proc/'.$v[0].'/status');
                if (is_string($status) && preg_match('/^Uid:\s+'.$this->owner.'\s+'.$this->owner.'\s+'.$this->owner.'\s+'.$this->owner.'\s*$/m',$status)) $result[$name.'_alive']=true;
                else $result['known']=false;
            }
        }
        if ($result['guard_alive'] || $result['anchor_alive'] || $result['worker_alive']) $result['known']=true;
        $path=$run.'/outcome';$s=@lstat($path);
        if ($s) {
            if (($s['mode']&0170000)!==0100000 || $s['uid']!==$this->owner || $s['nlink']!==1 || ($s['mode']&0777)!==0600 || $s['size']>32) $result['known']=false;
            else {$code=trim((string)@file_get_contents($path));if (!in_array($code,['finished','worker_lost','interrupted','timed_out'],true)) $result['known']=false;else $result['code']=$code==='timed_out'?'timed_out':'interrupted';}
        }
        return $result;
    }
    private function projection(): array
    {
        $view=$this->store->view();$status=$view['status'];$job=$view['job'];$patch=null;
        try {$native=$this->native();}catch (Throwable $e) {
            $status['state']='conflict';$status['code']='invalid_state';
            return ['status'=>$status,'job'=>$job,'patch'=>$job===null?null:['state'=>'conflict','code'=>'invalid_state']];
        }
        if ($job===null) {
            if ($native!==null && $native['phase']!=='rolled_back') {$status['state']='conflict';$status['code']='invalid_state';$status['request_id']=$native['request_id'];}
            return ['status'=>$status,'job'=>null,'patch'=>null];
        }
        if ($job['state']==='validating') {
            $owner=$this->validationOwner($job);
            $alive=$owner['guard_alive'] || $owner['anchor_alive'] || $owner['worker_alive'];
            if (!$owner['known']) $status['code']='invalid_state';
            elseif (!$alive && $this->now()-(float)($job['started_uptime']??$this->now())>=10) {
                $status['state']='failed';$status['code']=$owner['code']??'interrupted';$patch=['state'=>'failed','code'=>$status['code']];
            }
            return ['status'=>$status,'job'=>$job,'patch'=>$patch];
        }
        if (!in_array($job['state'],['applying','awaiting_confirmation','confirmed','rolling_back','conflict'],true)) return ['status'=>$status,'job'=>$job,'patch'=>null];
        if ($native===null || $native['request_id']!==$job['request_id'] || $native['profile_hash']!==$job['profile_hash']) {
            // During initial preparation no new native record exists yet.
            if ($job['state']==='applying' && $native!==null && $native['phase']==='rolled_back') return ['status'=>$status,'job'=>$job,'patch'=>null];
            $patch=['state'=>'conflict','code'=>'invalid_state'];
        } else {
            $phase=$native['phase'];
            if ($phase==='rolled_back') $patch=['state'=>'rolled_back','active'=>null,'code'=>$this->nativeCode($job['request_id'])??$job['code']??null];
            elseif ($phase==='awaiting_confirmation' || $phase==='confirmed') {
                if (!$this->healthy()) $patch=['state'=>'conflict','code'=>'guard_unavailable'];
                elseif ($phase==='awaiting_confirmation') $patch=['state'=>$phase,'code'=>null,'deadline_uptime'=>(float)$native['deadline']];
                else {
                    try {
                        $snapshot=$this->store->snapshot($job['backup_id']);$profile=$snapshot['candidate_profile']??null;
                        if (!is_array($profile) || !hash_equals($job['profile_hash'],AsusSmartDnsProfile::hash($profile))) throw new RuntimeException('invalid_state');
                        $patch=['state'=>'confirmed','code'=>null,'active'=>['profile'=>$profile,'profile_hash'=>$job['profile_hash'],'backup_id'=>$job['backup_id']]];
                    } catch (Throwable $e) {$patch=['state'=>'conflict','code'=>'invalid_state'];}
                }
            } elseif ($phase==='rolling_back') $patch=['state'=>'rolling_back','code'=>$this->nativeCode($job['request_id'])??$job['code']??null];
            elseif ($phase==='conflict') $patch=['state'=>'conflict','code'=>$this->nativeCode($job['request_id'])??$job['code']??'connection_failed'];
            elseif ($job['state']!=='applying') $patch=['state'=>'conflict','code'=>'invalid_state'];
        }
        if ($patch!==null) {
            $status['state']=$patch['state'];$status['code']=$patch['code'];
            if (array_key_exists('active',$patch)) $status['active_profile_hash']=$patch['active']['profile_hash']??null;
            $status['deadline_remaining_s']=$patch['state']==='awaiting_confirmation'?max(0,(int)ceil($patch['deadline_uptime']-$this->now())):null;
        }
        return ['status'=>$status,'job'=>$job,'patch'=>$patch];
    }
    public function status(): array { return $this->projection()['status']; }
    /** Caller owns the shared mutation lease (or the updater's exclusive lease). */
    public function reconcile(): array
    {
        $p=$this->projection();$job=$p['job'];$patch=$p['patch'];
        if ($job!==null && $patch!==null) {
            $changed=false;
            foreach ($patch as $key=>$value) {
                if ($key==='active') {$current=$this->store->active();if ($current!==$value) $changed=true;}
                elseif (!array_key_exists($key,$job) || $job[$key]!==$value) $changed=true;
            }
            if ($changed) $this->store->transition($job['request_id'],[$job['state']],$patch);
        }
        return $this->status();
    }
    public function blocksUpdate(): bool
    {
        $job=$this->store->transaction();
        if ($job!==null && in_array($job['state'],['validating','applying','awaiting_confirmation','rolling_back','conflict'],true)) return true;
        try {$native=$this->native();}catch (Throwable $e) {return true;}
        if ($native===null) return ($job['state']??null)==='confirmed';
        if ($native['phase']==='rolled_back') return ($job['state']??null)==='confirmed';
        return $native['phase']!=='confirmed' || ($job['state']??null)!=='confirmed' || $native['request_id']!==$job['request_id'] || $native['profile_hash']!==$job['profile_hash'] || !$this->healthy();
    }
}
