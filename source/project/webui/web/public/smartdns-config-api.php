<?php
require_once __DIR__.'/smartdns-profile.php';
require_once __DIR__.'/smartdns-config-jobs.php';
require_once __DIR__.'/router-checkup.php';
require_once __DIR__.'/smartdns-lifecycle.php';
require_once __DIR__.'/router-wan.php';
require_once __DIR__.'/import-transaction.php';

/** Closed request grammar. Session/CSRF/same-origin checks stay in index.php. */
final class AsusSmartDnsConfigApi
{
    private const INPUTS=[
        'routercheckup'=>[], 'wanaddresses'=>[], 'smartdnsconfigstatus'=>[],
        'smartdnsdraft'=>['profile'],
        'smartdnsvalidate'=>['request_id','profile_hash'],
        'smartdnspreview'=>['preview_id'],
        'smartdnsapply'=>['request_id','preview_id','profile_hash','baseline_hash'],
        'smartdnsconfirm'=>['request_id'], 'smartdnsrollback'=>['request_id'],
    ];
    public static function profile(string $raw): array
    {
        if (strlen($raw)>65536) throw new RuntimeException('invalid_request');
        try {$profile=json_decode($raw,true,32,JSON_THROW_ON_ERROR);}
        catch (Throwable $e) {throw new RuntimeException('invalid_request');}
        if (!is_array($profile) || array_is_list($profile)) throw new RuntimeException('invalid_request');
        return AsusSmartDnsProfile::normalize($profile);
    }
    public static function validate(array $post): void
    {
        $cmd=$post['cmd']??null;
        if (!is_string($cmd) || !array_key_exists($cmd,self::INPUTS)) throw new RuntimeException('invalid_request');
        $expected=array_merge(['cmd','csrf_token'],self::INPUTS[$cmd]);$keys=array_keys($post);sort($expected);sort($keys);
        if ($keys!==$expected) throw new RuntimeException('invalid_request');
        foreach ($post as $value) if (!is_string($value)) throw new RuntimeException('invalid_request');
        if (strlen($post['csrf_token'])>1024) throw new RuntimeException('invalid_request');
        foreach (['request_id','preview_id'] as $key) if (isset($post[$key]) && !preg_match('/^[a-f0-9]{32}$/D',$post[$key])) throw new RuntimeException('invalid_request');
        foreach (['profile_hash','baseline_hash'] as $key) if (isset($post[$key]) && !preg_match('/^[a-f0-9]{64}$/D',$post[$key])) throw new RuntimeException('invalid_request');
        if ($cmd==='smartdnsdraft') self::profile($post['profile']);
    }
    /** Dependencies are trusted local adapters; none can be selected by HTTP. */
    public static function dispatch(array $post,array $deps=[]): array
    {
        self::validate($post);$cmd=$post['cmd'];
        if(NfqwsPlatform::native()&&in_array($cmd,['wanaddresses','routercheckup'],true)){
            require_once __DIR__.'/openwrt-web.php';return $cmd==='wanaddresses'?NfqwsOpenWrtWeb::wan():NfqwsOpenWrtWeb::checkup();
        }
        if ($cmd==='wanaddresses') return (new AsusRouterWan($deps['wan_io']??new AsusReportIO()))->collect();
        $store=$deps['store']??new AsusSmartDnsStore();
        $backend=$deps['backend']??new AsusSmartDnsNativeBackend($store,new AsusSmartDnsInstaller());
        $jobs=new AsusSmartDnsConfigJobs($store,$backend,$deps['jobs_deps']??[]);
        if ($cmd==='smartdnsconfigstatus') {
            $status=$jobs->status();$intent=$store->intent();
            $routing='inactive';$resume=null;
            if (in_array($status['state'],['confirmed','awaiting_confirmation'],true)) {
                $routing=isset($deps['routing'])?($deps['routing'])():$backend->forwarding();
                if (!in_array($routing,['managed','external','unknown'],true)) $routing='unknown';
            }
            if ($intent!==null) {
                if ($status['state']==='confirmed' && $routing!=='managed') $resume=$routing==='external'?'routing_lost':'routing_unknown';
                elseif (!in_array($status['state'],['confirmed','validating','applying','awaiting_confirmation','rolling_back'],true)) $resume='resume_required';
            }
            return ['status'=>$status,'draft'=>$store->draft(),'active_profile'=>$store->active()['profile']??null,'confirmed_profile'=>$intent['profile']??null,
                'routing'=>$routing,'resume_code'=>$resume];
        }
        if ($cmd==='smartdnspreview') return $store->preview($post['preview_id']);
        if ($cmd==='routercheckup') {
            // A second foreign SmartDNS must not be hidden by our own process.
            $managed=false;
            if ($backend->healthy()) {
                try {$managed=!in_array('external_smartdns',$backend->baseline()['conflicts'],true);}catch (Throwable $e) {}
            }
            return (new AsusRouterCheckup(new AsusReportIO(),['managed_identity'=>fn()=>$managed]))->collect();
        }
        $lease=isset($deps['lease'])?($deps['lease'])():(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
        try {
          $writer=$deps['writer']??function($fn){$tx=new AsusImportTransaction();return $tx->writer(function()use($tx,$fn){$tx->recover();return $fn();});};
          return $writer(function()use($jobs,$cmd,$store,$post,$backend){
            $jobs->reconcile();
            if ($cmd==='smartdnsdraft') return ['profile_hash'=>$store->saveDraft(self::profile($post['profile']))];
            if ($cmd==='smartdnsvalidate') return $jobs->start($post['request_id'],$post['profile_hash']);
            if ($cmd==='smartdnsapply') $jobs->awaitValidationRelease($post['preview_id']);
            $connection=new AsusSmartDnsConnection($store,$backend->dependencies());
            $result=match ($cmd) {
                'smartdnsapply'=>$connection->apply($post['request_id'],$post['preview_id'],$post['profile_hash'],$post['baseline_hash']),
                'smartdnsconfirm'=>$connection->confirm($post['request_id']),
                'smartdnsrollback'=>$connection->rollback($post['request_id']),
            };
            if ($cmd==='smartdnsconfirm' && $result['state']==='confirmed') (new AsusSmartDnsLifecycle($store,$backend))->remember();
            if ($cmd==='smartdnsrollback' && $result['state']==='rolled_back') $store->saveIntent(null);
            return $result;
          });
        } finally {if (is_resource($lease)) {flock($lease,LOCK_UN);fclose($lease);}}
    }
    public static function error(Throwable $e): array
    {
        if ($e instanceof AsusSmartDnsProfileError) return ['error'=>'invalid_profile','field'=>$e->field];
        $codes=['busy','invalid_request','invalid_state','invalid_configuration','invalid_profile','consent_required','request_conflict',
            'not_installed','unsupported_runtime','unsupported_binary','unsupported_abi','insufficient_memory','insufficient_space','invalid_clock',
            'stale_draft','stale_preview','stale_baseline','stale_state','restore_required','baseline_unavailable','guard_unavailable','recovery_unavailable',
            'native_fallback_unavailable','primary_dns_unverified','existing_dns_rules','hook_permissions','hook_conflict','dns_restart_failed','dns_validation_failed',
            'runtime_stop_failed','port_busy','timed_out','interrupted','output_limit','validation_failed','connection_failed','storage_unavailable','launch_failed'];
        return ['error'=>in_array($e->getMessage(),$codes,true)?$e->getMessage():'internal_error'];
    }
}
