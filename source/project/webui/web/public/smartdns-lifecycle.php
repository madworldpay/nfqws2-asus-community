<?php
require_once __DIR__.'/smartdns-config-jobs.php';

/** Root package/boot operations. Callers own the ordinary or updater lease. */
final class AsusSmartDnsLifecycle
{
    private NfqwsSmartDnsBackend $backend;
    private AsusSmartDnsInstaller $installer;
    public function __construct(private AsusSmartDnsStore $store,?NfqwsSmartDnsBackend $backend=null,?AsusSmartDnsInstaller $installer=null,private array $deps=[])
    {
        $this->installer=$installer??new AsusSmartDnsInstaller();
        $this->backend=$backend??AsusSmartDnsNativeBackend::create($store,$this->installer);
    }
    public function remember(): void
    {
        $active=$this->store->active();$job=$this->store->transaction();
        if ($active===null || ($job['state']??null)!=='confirmed') throw new RuntimeException('invalid_state');
        $digest=isset($this->deps['digest'])?($this->deps['digest'])():($this->installer->installedArtifact()['sha256']??null);
        if ($digest===null) throw new RuntimeException('not_installed');
        $this->store->saveIntent(['schema_version'=>1,'profile'=>$active['profile'],'profile_hash'=>$active['profile_hash'],'engine_sha'=>$digest,'source_request_id'=>$job['request_id']]);
    }
    public function stop(string $mode): array
    {
        if (!in_array($mode,['upgrade','remove'],true)) throw new RuntimeException('invalid_request');
        $jobs=new AsusSmartDnsConfigJobs($this->store,$this->backend,$this->deps['jobs_deps']??[]);
        $status=isset($this->deps['reconcile'])?($this->deps['reconcile'])():$jobs->reconcile();
        $blocked=isset($this->deps['blocked'])?($this->deps['blocked'])():$jobs->blocksUpdate();
        if ($blocked) throw new RuntimeException('busy');
        if ($this->store->active()!==null) {
            $job=$this->store->transaction();
            if ($mode==='upgrade') $this->repairForUpgrade($job,false);
            $this->remember();
            $status=isset($this->deps['rollback'])?($this->deps['rollback'])($job['request_id']):(new AsusSmartDnsConnection($this->store,$this->backend->dependencies()))->rollback($job['request_id']);
            if ($status['state']!=='rolled_back') throw new RuntimeException('dns_restore_failed');
        }
        if ($mode==='upgrade') $this->verifyUpgradeDns();
        if ($mode==='remove') $this->store->saveIntent(null);
        return $status;
    }
    /** Recheck the current dnsmasq inputs immediately before the package transaction. */
    public function verifyUpgradeDns(): void
    {
        if (!($this->backend instanceof AsusSmartDnsNativeBackend && NfqwsPlatform::current()==='asus-entware') &&
            !($this->backend instanceof NfqwsOpenWrtSmartDnsBackend && NfqwsPlatform::native())) return;
        $intent=$this->store->intent();$job=$this->store->transaction();
        if ($intent===null || ($job['state']??null)!=='rolled_back' ||
            ($job['request_id']??null)!==$intent['source_request_id'] ||
            ($job['profile_hash']??null)!==$intent['profile_hash'] ||
            ($job['boot']??null)!==trim((string)file_get_contents('/proc/sys/kernel/random/boot_id'))) return;
        $this->repairForUpgrade($job,true);
    }
    private function repairForUpgrade(?array $job,bool $restored): void
    {
        if (!is_string($job['backup_id']??null)) return;
        try {
            if ($this->backend instanceof NfqwsOpenWrtSmartDnsBackend && NfqwsPlatform::native()) {
                $this->backend->repairUpgradeIncludes($job,$restored);
            } elseif ($this->backend instanceof AsusSmartDnsNativeBackend && NfqwsPlatform::current()==='asus-entware') {
                $snapshot=$this->store->snapshot($job['backup_id']);
                $fingerprints=$snapshot['baseline']['fingerprints']['dns_includes']??null;
                if (!is_array($fingerprints)) return;
                $this->backend->repairUpgradeIncludes($job,$fingerprints,$restored);
            } else return;
        }
        catch (RuntimeException $e) {
            if (in_array($e->getMessage(),['existing_dns_rules','stale_baseline','unsafe_panel_file'],true))
                throw new RuntimeException('dns_permissions_changed',0,$e);
            throw $e;
        }
        if ($this->store->transaction()!==$job) throw new RuntimeException('stale_baseline');
    }
    /** A validator briefly owns the journal while publishing its result. Only
     * retry this passive read; never replay a DNS switch or confirmation. */
    private static function readStatus(callable $reader,int|float $end): array
    {
        do {
            try { return $reader(); }
            catch (RuntimeException $error) {
                if ($error->getMessage()!=='busy' || hrtime(true)>=$end) throw $error;
                usleep(100000);
            }
        } while (true);
    }
    /** One bounded, private latest outcome, with no profile or resolver data. */
    private function recordBoot(int $attempt,string $boot,array $result): void
    {
        $root=$this->store->directory(false);
        if ($root===null) throw new RuntimeException('storage_unavailable');
        $owner=lstat($root)['uid'];$path=$root.'/boot-status.json';clearstatcache(true,$path);$before=@lstat($path);
        $valid=static fn($s)=>$s===false || (($s['mode']&0170000)===0100000 && $s['uid']===$owner && $s['nlink']===1 && ($s['mode']&0777)===0600 && $s['size']<=4096);
        if (!$valid($before)) throw new RuntimeException('invalid_state');
        $state=$result['state']??'failed';$code=$result['code']??null;
        if (!in_array($state,['starting','idle','validating','preview_ready','applying','awaiting_confirmation','confirmed','rolling_back','rolled_back','failed','conflict','action_required'],true)) $state='failed';
        if ($code!==null && (!is_string($code) || !preg_match('/^[a-z][a-z0-9_]{0,63}$/D',$code))) $code='unavailable';
        $raw=json_encode(['attempt'=>$attempt,'state'=>$state,'code'=>$code,'boot'=>$boot],JSON_THROW_ON_ERROR)."\n";
        $tmp=$root.'/.boot-'.bin2hex(random_bytes(12));$mask=umask(0077);
        try {$file=@fopen($tmp,'xb');}finally {umask($mask);}
        if (!is_resource($file)) throw new RuntimeException('storage_unavailable');
        try {
            if (fwrite($file,$raw)!==strlen($raw) || !fflush($file) || function_exists('fsync') && !fsync($file)) throw new RuntimeException('storage_unavailable');
            fclose($file);$file=null;clearstatcache(true,$path);$after=@lstat($path);
            if (!$valid($after) || ($before===false)!==($after===false)) throw new RuntimeException('invalid_state');
            if ($before!==false) foreach (['dev','ino','size','mtime','ctime'] as $key) if ($before[$key]!==$after[$key]) throw new RuntimeException('invalid_state');
            if (!@rename($tmp,$path)) throw new RuntimeException('storage_unavailable');
        } finally {if (is_resource($file)) fclose($file);if (is_file($tmp)) unlink($tmp);}
    }
    /** Boot callers hold one resume mutex and mutation lease for this entire
     * bounded series. Manual resume deliberately remains a single attempt. */
    public function resumeBoot(): array
    {
        $intent=$this->store->intent();
        if ($intent===null) return ['state'=>'idle','code'=>null];
        $boot=trim((string)@file_get_contents('/proc/sys/kernel/random/boot_id',false,null,0,65));
        if (!preg_match('/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/D',$boot)) throw new RuntimeException('invalid_state');
        $origin=$this->store->transaction();$native=$this->backend->state();$active=$this->store->active();
        if ($active!==null && $active['profile_hash']!==$intent['profile_hash']) return ['state'=>'action_required','code'=>'stale_state'];
        $oldRestore=$origin!==null && $native!==null && in_array($origin['state'],['confirmed','conflict'],true)
            && $origin['request_id']===$intent['source_request_id'] && $origin['profile_hash']===$intent['profile_hash']
            && ($origin['boot']??null)!==$boot && ($origin['boot']??null)===$native['boot_id']
            && $native['request_id']===$origin['request_id'] && $native['profile_hash']===$intent['profile_hash'];
        // Reuse the existing native boot budget: four attempts, waits 2/4/6s.
        // Every operation inside resume has its own bounded deadline.
        for ($attempt=1;$attempt<=4;$attempt++) {
            if ($this->store->intent()!==$intent) return ['state'=>'action_required','code'=>'stale_state'];
            $this->recordBoot($attempt,$boot,['state'=>'starting','code'=>null]);
            $error=null;
            try {$result=$this->resume();}
            catch (Throwable $e) {$error=$e;$result=['state'=>'failed','code'=>$e->getMessage()];}
            $outcome=$result;
            if (($result['state']??null)==='conflict' && method_exists($this->backend,'restoreFailure') && $this->backend->restoreFailure()==='dns_restart_failed') $outcome['code']='dns_restart_failed';
            $this->recordBoot($attempt,$boot,$outcome);
            $retry=false;
            if ($attempt<4 && $this->store->intent()===$intent) {
                $job=$this->store->transaction();$current=$this->backend->state();
                // This is a retry of restoring the consent-bound previous boot,
                // never of a new DNS switch. Inspect the native outcome because
                // rollback's conservative public fallback is hook_conflict.
                if ($error===null && $oldRestore && ($result['state']??null)==='conflict'
                    && ($job['request_id']??null)===$origin['request_id'] && ($job['boot']??null)===$origin['boot']
                    && ($job['profile_hash']??null)===$intent['profile_hash']
                    && $current!==null && $current['request_id']===$native['request_id']
                    && $current['profile_hash']===$native['profile_hash'] && $current['boot_id']===$native['boot_id']
                    && $current['phase']==='conflict' && method_exists($this->backend,'restoreFailure')
                    && $this->backend->restoreFailure()==='dns_restart_failed') $retry=true;
                elseif (in_array($result['code']??null,['baseline_unavailable','stale_baseline'],true)
                    && in_array($result['state']??null,['failed','rolled_back'],true) && $this->store->active()===null) {
                    $priorNative=$current===null ? $native===null : $native!==null && $current['phase']==='rolled_back'
                        && $current['request_id']===$native['request_id'] && $current['profile_hash']===$native['profile_hash'] && $current['boot_id']===$native['boot_id'];
                    $priorJob=$job===null ? $origin===null : $job['profile_hash']===$intent['profile_hash']
                        && (($job['request_id']===$intent['source_request_id'] && $job['state']==='rolled_back')
                            || (in_array($job['state'],['failed','preview_ready'],true) && $job['backup_id']===null
                                && ($job['profile_source']??null)==='confirmed' && ($job['source_request_id']??null)===$intent['source_request_id']
                                && ($job['engine_sha']??null)===$intent['engine_sha']));
                    $retry=$priorNative && $priorJob;
                }
            }
            if (!$retry) {if ($error!==null) throw $error;return $result;}
            if (isset($this->deps['boot_pause'])) ($this->deps['boot_pause'])($attempt*2);
            else sleep($attempt*2);
        }
        throw new RuntimeException('invalid_state');
    }
    /** Resume only prior explicit consent, same engine, and a freshly tested profile. */
    public function resume(): array
    {
        $intent=$this->store->intent();
        if ($intent===null) return ['state'=>'idle','code'=>null];
        $installed=$this->installer->installedArtifact();
        if ($installed===null || !hash_equals($intent['engine_sha'],$installed['sha256'])) return ['state'=>'action_required','code'=>'engine_changed'];
        $job=$this->store->transaction();$connection=new AsusSmartDnsConnection($this->store,$this->backend->dependencies());
        if ($this->backend->healthy() && ($job['state']??null)==='confirmed') return $job['profile_hash']===$intent['profile_hash']?['state'=>'confirmed','code'=>null]:['state'=>'action_required','code'=>'stale_state'];
        if ($job!==null && in_array($job['state'],['confirmed','conflict'],true)) {
            if ($job['request_id']!==$intent['source_request_id'] || $job['profile_hash']!==$intent['profile_hash']) return ['state'=>'action_required','code'=>'stale_state'];
            $restored=$connection->rollback($job['request_id']);
            if ($restored['state']!=='rolled_back') return $restored;
        }
        $jobs=new AsusSmartDnsConfigJobs($this->store,$this->backend,$this->deps['jobs_deps']??[]);$jobs->reconcile();
        if ($jobs->blocksUpdate() || $this->store->active()!==null) return ['state'=>'action_required','code'=>'busy'];
        // Saved consent is independent of an imported or unfinished draft.
        // Its journal binding is checked again at publication and application.
        $hash=$intent['profile_hash'];$id=bin2hex(random_bytes(16));
        if (isset($this->deps['validate'])) ($this->deps['validate'])($id,$hash,'confirmed');
        else $jobs->start($id,$hash,'confirmed');
        $end=hrtime(true)+155000000000;
        do {$status=self::readStatus(fn()=>$jobs->status(),$end);if ($status['request_id']!==$id || $status['state']!=='validating') break;usleep(100000);} while (hrtime(true)<$end);
        if ($status['request_id']!==$id) return ['state'=>'action_required','code'=>'stale_state'];
        if ($status['state']!=='preview_ready') return $status;
        $jobs->awaitValidationRelease($status['preview_id']);
        $preview=$this->store->preview($status['preview_id']);
        $applied=$connection->apply(bin2hex(random_bytes(16)),$preview['id'],$hash,$preview['baseline_hash'],'confirmed');
        if ($applied['state']!=='awaiting_confirmation') return $applied;
        $confirmed=$connection->confirm($applied['request_id']);
        if ($confirmed['state']==='confirmed') $this->remember();
        return $confirmed;
    }
}
