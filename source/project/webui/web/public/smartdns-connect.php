<?php
/** Pure, conservative edits shared by preflight and the recovery backend. */
final class AsusSmartDnsHook
{
    public const BLOCK = "\n# BEGIN NFQWS2 SMARTDNS MANAGED\nif [ -x /jffs/nfqws2-asus-smartdns/lifecycle.sh ]; then\n    /jffs/nfqws2-asus-smartdns/lifecycle.sh postconf \"\$1\" || exit \$?\nfi\n# END NFQWS2 SMARTDNS MANAGED\n";

    private static function text(string $text, string $error): void
    {
        if (strlen($text)>262144 || str_contains($text,"\0")) throw new RuntimeException($error);
    }

    public static function install(string $text): string
    {
        self::text($text,'hook_conflict');
        $clean=$text;
        if (str_contains($text,'NFQWS2 SMARTDNS MANAGED')) {
            $clean=self::remove($text);
        }
        // A shell parser is deliberately not approximated here. An early exit,
        // exec or return anywhere needs manual review, even in a function.
        $commands=preg_replace('/^[\t ]*#.*$/m','',$clean);
        if (preg_match('/(?:^|[^A-Za-z0-9_])(?:exit|exec|return)(?:[^A-Za-z0-9_]|$)/',$commands)) throw new RuntimeException('hook_conflict');
        $out=$clean===$text?$text.self::BLOCK:$text;
        self::text($out,'hook_conflict');return $out;
    }

    public static function remove(string $text): string
    {
        self::text($text,'hook_conflict');
        if (!str_contains($text,'NFQWS2 SMARTDNS MANAGED')) return $text;
        if (substr_count($text,self::BLOCK)!==1) throw new RuntimeException('hook_conflict');
        $clean=str_replace(self::BLOCK,'',$text);
        if (str_contains($clean,'NFQWS2 SMARTDNS MANAGED')) throw new RuntimeException('hook_conflict');
        return $clean;
    }

    /** Keep local names/DHCP; never silently discard a conditional DNS route. */
    public static function forwarding(string $text, array $serverFiles): string
    {
        self::text($text,'existing_dns_rules'); $kept=[];
        foreach (explode("\n",$text) as $line) {
            $directive=trim($line);
            if ($directive==='' || str_starts_with($directive,'#')) { $kept[]=$line; continue; }
            if (preg_match('/^(conf-file|conf-dir|conf-script)\s*(?:=|$)/',$directive)) throw new RuntimeException('existing_dns_rules');
            if (preg_match('/^server\s*=\s*\//',$directive)) throw new RuntimeException('existing_dns_rules');
            if (preg_match('/^servers-file\s*=\s*(.+)$/D',$directive,$match)) {
                $path=trim($match[1]);
                if (!isset($serverFiles[$path]) || !is_string($serverFiles[$path])) throw new RuntimeException('existing_dns_rules');
                self::text($serverFiles[$path],'existing_dns_rules');
                foreach (explode("\n",$serverFiles[$path]) as $server) {
                    $server=trim($server);
                    if ($server==='' || str_starts_with($server,'#')) continue;
                    if (!preg_match('/^server\s*=\s*[^\/\s#][^\/\s]*$/D',$server)) throw new RuntimeException('existing_dns_rules');
                }
                continue;
            }
            if (preg_match('/^(?:server|resolv-file)\s*=/',$directive) || preg_match('/^(?:no-resolv|all-servers|strict-order)\s*$/D',$directive)) continue;
            $kept[]=$line;
        }
        return rtrim(implode("\n",$kept),"\n")."\nno-resolv\nserver=127.0.0.1#6054\n";
    }

    /** Preserve LAN answers, but don't claim a profile can override them. */
    public static function profileRouting(string $text,array $profile): bool
    {
        self::text($text,'existing_dns_rules');$profile=AsusSmartDnsProfile::normalize($profile);$wanted=$profile['records'];$local=[];
        foreach ($profile['upstreams'] as $server) $wanted=array_merge($wanted,$server['domains']);
        foreach (explode("\n",$text) as $line) {
            $line=trim($line);if ($line==='' || str_starts_with($line,'#')) continue;
            if (preg_match('/^(address|local)\s*=\s*(\/.*)$/D',$line,$m)) {
                $domains=array_slice(explode('/',$m[2]),1,-1);
                foreach ($domains as $name) {
                    if ($name==='#') return false;
                    if ($name==='') {foreach ($wanted as $target) if (!str_contains($target['name'],'.')) return false;continue;}
                    if (str_starts_with($name,'*.')) $name=substr($name,2);
                    $local[]=['name'=>ltrim($name,'.'),'include_subdomains'=>true];
                }
            } elseif (preg_match('/^(host-record|cname|interface-name)\s*=\s*(.*)$/D',$line,$m)) {
                $names=explode(',',$m[2]);if ($m[1]!=='host-record') $names=array_slice($names,0,1);
                foreach ($names as $name) {
                    $name=trim($name);if (@inet_pton($name)!==false) break;
                    $local[]=['name'=>$name,'include_subdomains'=>false];
                }
            }
        }
        foreach ($local as $entry) {
            try {$entry['name']=AsusSmartDnsProfile::domain($entry['name'],'local');}
            catch (Throwable $e) {
                // dnsmasq also owns service names such as _dns.resolver.arpa.
                // They are DNS names, though not hostnames accepted by the
                // profile editor. Keep them and still check parent overlaps.
                $name=strtolower(rtrim($entry['name'],'.'));
                if (strlen($name)>253 || !str_contains($name,'_') || !preg_match('/^[a-z0-9_-]{1,63}(?:\\.[a-z0-9_-]{1,63})*$/D',$name)) return false;
                $entry['name']=$name;
            }
            foreach ($wanted as $target) {
                if ($entry['name']===$target['name'] || $entry['include_subdomains'] && str_ends_with($target['name'],'.'.$entry['name']) || $target['include_subdomains'] && str_ends_with($entry['name'],'.'.$target['name'])) return false;
            }
        }
        return true;
    }
}

require_once __DIR__.'/smartdns-store.php';

/** A native owner could not prove cleanup; retain its backup and update block. */
final class AsusSmartDnsUnresolvedGuard extends RuntimeException {}

/** Transaction policy. Side effects require a trusted, independently guarded backend. */
final class AsusSmartDnsConnection
{
    public function __construct(private AsusSmartDnsStore $store, private array $deps=[]) {}
    private function now(): float
    {
        $n=isset($this->deps['uptime'])?($this->deps['uptime'])():(float)explode(' ',file_get_contents('/proc/uptime'))[0];
        if (!is_numeric($n) || !is_finite((float)$n) || $n<0) throw new RuntimeException('invalid_state');
        return (float)$n;
    }
    private function call(string $operation, mixed ...$arguments): mixed
    {
        if (!isset($this->deps[$operation]) || !is_callable($this->deps[$operation])) throw new RuntimeException('guard_unavailable');
        return ($this->deps[$operation])(...$arguments);
    }
    private static function id(string $value): bool { return (bool)preg_match('/^[a-f0-9]{32}$/D',$value); }
    private static function digest(mixed $value): bool { return is_string($value) && (bool)preg_match('/^[a-f0-9]{64}$/D',$value); }
    private static function code(Throwable $error): string
    {
        $allowed=['guard_unavailable','recovery_unavailable','stale_baseline','existing_dns_rules','native_fallback_unavailable','primary_dns_unverified','hook_conflict','dns_restart_failed','dns_validation_failed','insufficient_space','port_busy','timed_out','interrupted','invalid_state'];
        return in_array($error->getMessage(),$allowed,true)?$error->getMessage():'connection_failed';
    }
    public function baseline(): array
    {
        $b=$this->call('baseline');
        if (!is_array($b) || !self::digest($b['hash']??null) || !is_array($b['snapshot']??null) || !is_array($b['conflicts']??null)) throw new RuntimeException('baseline_unavailable');
        return $b;
    }
    private function job(string $id): array
    {
        if (!self::id($id)) throw new RuntimeException('invalid_request');
        $j=$this->store->transaction();
        if ($j===null || $j['request_id']!==$id) throw new RuntimeException('stale_state');
        return $j;
    }
    public function status(): array { return $this->store->status(); }
    public function apply(string $requestId,string $previewId,string $profileHash,string $baselineHash,string $source='draft'): array
    {
        if (!self::id($requestId) || !self::id($previewId) || !self::digest($profileHash) || !self::digest($baselineHash) || !in_array($source,['draft','confirmed'],true)) throw new RuntimeException('invalid_request');
        $receipt=$this->store->receipt($requestId);$old=$receipt['job']??null;
        if ($old!==null) {
            if (($old['profile_source']??'draft')!==$source) throw new RuntimeException('stale_preview');
            if ($old['profile_hash']!==$profileHash || $old['baseline_hash']!==$baselineHash || $old['preview_id']!==$previewId) throw new RuntimeException('request_conflict');
            return $receipt['status'];
        }
        // Replacing a confirmed listener on the same port needs its own swap
        // protocol. Until then use the explicit, verified Restore action first.
        if ($this->store->active()!==null) throw new RuntimeException('restore_required');
        $preview=$this->store->preview($previewId);
        if (($preview['profile_source']??'draft')!==$source) throw new RuntimeException('stale_preview');
        foreach (['prepare','guard','forward','dns','confirm','restore','stop','release'] as $name)
            if (!isset($this->deps[$name]) || !is_callable($this->deps[$name])) throw new RuntimeException('guard_unavailable');
        if ($preview['profile_hash']!==$profileHash || $preview['baseline_hash']!==$baselineHash) throw new RuntimeException('stale_preview');
        $baseline=$this->baseline();
        if (!hash_equals($baselineHash,$baseline['hash'])) throw new RuntimeException('stale_baseline');
        if ($baseline['conflicts']) {
            // Keep actionable local checks distinct from conditional DNS rules.
            // Unknown collector details remain behind the existing safe error.
            foreach (['hook_permissions','hook_conflict','native_fallback_unavailable'] as $code)
                if (in_array($code,$baseline['conflicts'],true)) throw new RuntimeException($code);
            throw new RuntimeException('existing_dns_rules');
        }
        $profile=$this->store->candidate($preview);
        $this->store->begin($requestId,$profileHash,$baselineHash);$guardReady=false;
        try {
            $backup=$this->store->backup(['baseline'=>$baseline['snapshot'],'candidate_profile'=>$profile]);
            $job=$this->job($requestId);
            $this->call('prepare',$job,$this->store->snapshot($backup));
            // Preparing recovery files must not quietly accept a hook edit.
            if (!hash_equals($baselineHash,$this->baseline()['hash'])) throw new RuntimeException('stale_baseline');
            $identity=$this->call('guard',$job,$profile);
            if (!is_array($identity) || !is_array($identity['guard_identity']??null) || !is_array($identity['identity']??null)) throw new RuntimeException('guard_unavailable');
            $guardReady=true;
            $this->store->transition($requestId,['applying'],$identity);
            $switch=$this->call('forward',$this->job($requestId));$deadline=$switch['deadline_uptime']??null;
            if (!is_numeric($deadline) || !is_finite((float)$deadline) || $deadline<=$this->now() || $deadline>$this->now()+120) throw new RuntimeException('invalid_state');
            $this->store->transition($requestId,['applying'],['state'=>'awaiting_confirmation','deadline_uptime'=>(float)$deadline]);
            if ($this->call('dns')!==true) throw new RuntimeException('dns_validation_failed');
            return $this->status();
        } catch (Throwable $error) {
            if ($error instanceof AsusSmartDnsUnresolvedGuard)
                return $this->store->transition($requestId,['applying'],['state'=>'conflict','code'=>self::code($error)]);
            if ($guardReady) return $this->rollback($requestId,self::code($error));
            return $this->store->transition($requestId,['applying'],['state'=>'failed','code'=>self::code($error)]);
        }
    }
    public function confirm(string $requestId): array
    {
        $job=$this->job($requestId);
        if ($job['state']==='confirmed') return $this->status();
        if ($job['state']!=='awaiting_confirmation') throw new RuntimeException('stale_state');
        if ($this->now()>=(float)($job['deadline_uptime']??0)) return $this->rollback($requestId,'timed_out');
        if ($this->call('dns')!==true || $this->call('confirm',$job)!==true) return $this->rollback($requestId,'dns_validation_failed');
        $snapshot=$this->store->snapshot($job['backup_id']);$profile=$snapshot['candidate_profile']??null;
        if (!is_array($profile) || !hash_equals($job['profile_hash'],AsusSmartDnsProfile::hash($profile))) throw new RuntimeException('invalid_state');
        $result=$this->store->transition($requestId,['awaiting_confirmation'],['state'=>'confirmed','code'=>null,
            'active'=>['profile'=>$profile,'profile_hash'=>$job['profile_hash'],'backup_id'=>$job['backup_id']]]);
        $this->call('release',$this->job($requestId));return $result;
    }
    public function rollback(string $requestId, ?string $reason=null): array
    {
        $job=$this->job($requestId);
        if ($job['state']==='rolled_back') return $this->status();
        if (!in_array($job['state'],['applying','awaiting_confirmation','confirmed','rolling_back','conflict'],true)) throw new RuntimeException('stale_state');
        $this->store->transition($requestId,[$job['state']],['state'=>'rolling_back','code'=>$reason]);
        try {
            $job=$this->job($requestId);
            // The backend returns true only after restoring native forwarding
            // AND probing DNS53. Candidate/guard must survive any conflict.
            if ($this->call('restore',$job,$this->store->snapshot($job['backup_id']))!==true) throw new RuntimeException('hook_conflict');
            if ($this->call('stop',$job)!==true) throw new RuntimeException('runtime_stop_failed');
            $result=$this->store->transition($requestId,['rolling_back'],['state'=>'rolled_back','active'=>null]);
            $this->call('release',$this->job($requestId));return $result;
        } catch (Throwable $error) {
            return $this->store->transition($requestId,['rolling_back'],['state'=>'conflict','code'=>self::code($error)]);
        }
    }
}
