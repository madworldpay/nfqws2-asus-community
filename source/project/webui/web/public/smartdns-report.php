<?php
require_once __DIR__.'/smartdns-store.php';
require_once __DIR__.'/smartdns-install.php';

/** Deliberate report projection: never serialize private profile fields or paths. */
final class AsusSmartDnsReport
{
    public function __construct(private AsusSmartDnsStore $store,private mixed $installed) {}
    public function collect(): array
    {
        $out=['read_state'=>'missing','engine_installed'=>null,'engine_version'=>null,'journal_state'=>null,'profile_hash'=>null,
            'upstreams'=>[],'fixed_records'=>0,'fixed_suffix_records'=>0,'runtime_verified'=>false];
        try {
            $engine=($this->installed)();$out['engine_installed']=$engine['installed']===true;
            $version=$engine['version']??null;
            if (is_string($version) && preg_match('/^[0-9][0-9a-zA-Z._+-]{0,63}$/D',$version)) $out['engine_version']=$version;
            if ($this->store->directory(false)===null) return $out;
            $view=$this->store->view();$out['read_state']='available';$out['journal_state']=$view['status']['state'];
            $active=$view['active'];
            if ($active===null) return $out;
            $profile=AsusSmartDnsProfile::normalize($active['profile']);
            if (!hash_equals($active['profile_hash'],AsusSmartDnsProfile::hash($profile))) throw new RuntimeException('invalid_state');
            $out['profile_hash']=$active['profile_hash'];
            foreach ($profile['upstreams'] as $server) {
                $suffix=0;foreach ($server['domains'] as $domain) if ($domain['include_subdomains']) $suffix++;
                $out['upstreams'][]=['protocol'=>$server['protocol'],'default'=>$server['default'],'exact_rules'=>count($server['domains'])-$suffix,
                    'suffix_rules'=>$suffix,'bootstrap_addresses'=>count($server['bootstrap']),'tls_verification_required'=>in_array($server['protocol'],['dot','doh'],true)];
            }
            $out['fixed_records']=count($profile['records']);
            foreach ($profile['records'] as $record) if ($record['include_subdomains']) $out['fixed_suffix_records']++;
            return $out;
        } catch (Throwable $e) {
            // A read error is different from no installation or no profile.
            return array_replace($out,['read_state'=>'unavailable','journal_state'=>null,'profile_hash'=>null,'upstreams'=>[],'fixed_records'=>0,'fixed_suffix_records'=>0]);
        }
    }
}
