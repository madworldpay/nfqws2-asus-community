<?php
require_once __DIR__.'/smartdns-candidate.php';
require_once __DIR__.'/smartdns-probe.php';
require_once __DIR__.'/smartdns-baseline.php';

/** Background validation only. Never installs a hook or switches system DNS. */
final class AsusSmartDnsValidationJob
{
    public function __construct(private AsusSmartDnsStore $store,private ?AsusSmartDnsInstaller $installer=null,private array $deps=[])
    { $this->installer??=new AsusSmartDnsInstaller(); }
    private function baseline(): array
    {
        $value=isset($this->deps['baseline'])?($this->deps['baseline'])():(new AsusSmartDnsBaseline(new AsusReportIO(),$this->installer))->collect();
        if (!is_array($value) || !is_string($value['hash']??null) || !preg_match('/^[a-f0-9]{64}$/D',$value['hash'])) throw new RuntimeException('baseline_unavailable');
        return $value;
    }
    public function work(string $id): void
    {
        if (!preg_match('/^[a-f0-9]{32}$/D',$id)) throw new RuntimeException('invalid_request');
        $job=$this->store->transaction();
        if (($job['request_id']??null)!==$id) throw new RuntimeException('stale_state');
        if (in_array($job['state'],['preview_ready','failed'],true)) return;
        if ($job['state']!=='validating' || ($job['boot']??null)!==trim(file_get_contents('/proc/sys/kernel/random/boot_id'))) throw new RuntimeException('stale_state');
        $candidate=new AsusSmartDnsCandidate($this->installer,$id);
        if (isset($this->deps['authenticate'])) {
            if (($this->deps['authenticate'])()!==true) throw new RuntimeException('guard_unavailable');
        } else $candidate->authenticate();
        try {
            $profile=$this->store->candidate($job);
            if (!hash_equals($job['baseline_hash'],$this->baseline()['hash'])) throw new RuntimeException('stale_baseline');
            $dependencies=['candidate'=>$this->deps['candidate']??[$candidate,'run'],'baseline'=>fn()=>$this->baseline()];
            if (isset($this->deps['bundle'])) $dependencies['bundle']=$this->deps['bundle'];
            $preview=(new AsusSmartDnsProbe($this->installer,$dependencies))->validate($profile,$id);
            // An automatic WAN refresh, hook edit, or engine replacement while
            // testing invalidates the whole preview, even if DNS answers worked.
            if (!hash_equals($job['baseline_hash'],$preview['baseline_hash']) || !hash_equals($job['baseline_hash'],$this->baseline()['hash'])) throw new RuntimeException('stale_baseline');
            $this->store->savePreview($preview);
            $this->store->transition($id,['validating'],['state'=>'preview_ready','code'=>null,'preview_id'=>$preview['id'],'checks'=>$preview['checks']]);
        } catch (Throwable $error) {
            $allowed=['stale_draft','stale_preview','stale_baseline','baseline_unavailable','guard_unavailable','dns_validation_failed','invalid_configuration','port_busy','timed_out','interrupted','output_limit','unsupported_binary','insufficient_space','insufficient_memory'];
            $code=in_array($error->getMessage(),$allowed,true)?$error->getMessage():'validation_failed';
            $checks=$error instanceof AsusSmartDnsValidationError?$error->checks:[];
            $this->store->transition($id,['validating'],['state'=>'failed','code'=>$code,'checks'=>$checks]);
        }
    }
}
