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
        $digest=isset($this->deps['digest'])?($this->deps['digest'])():$this->installer->artifact()['sha256'];
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
            $this->remember();$job=$this->store->transaction();
            $status=isset($this->deps['rollback'])?($this->deps['rollback'])($job['request_id']):(new AsusSmartDnsConnection($this->store,$this->backend->dependencies()))->rollback($job['request_id']);
            if ($status['state']!=='rolled_back') throw new RuntimeException('dns_restore_failed');
        }
        if ($mode==='remove') $this->store->saveIntent(null);
        return $status;
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
    /** Resume only prior explicit consent, same engine, and a freshly tested profile. */
    public function resume(): array
    {
        $intent=$this->store->intent();
        if ($intent===null) return ['state'=>'idle','code'=>null];
        $installed=$this->installer->installed();
        if (!$installed['installed'] || !hash_equals($intent['engine_sha'],$this->installer->artifact()['sha256'])) return ['state'=>'action_required','code'=>'engine_changed'];
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
