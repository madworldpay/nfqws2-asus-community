<?php
require_once __DIR__.'/smartdns-profile.php';
require_once __DIR__.'/dpi-store.php';

/** Private files and compare-and-swap journal; no process or DNS side effects. */
final class AsusSmartDnsStore
{
    private string $root;
    private const STATES = ['idle','validating','preview_ready','applying','awaiting_confirmation','confirmed','rolling_back','rolled_back','failed','conflict'];
    private const LIVE = ['validating','applying','awaiting_confirmation','rolling_back','conflict'];
    public function __construct(?string $root=null, private int $owner=0, private array $deps=[])
    { $this->root = $root ?? AsusDpiStore::optPath('/etc/nfqws-asus-web/smartdns'); }
    private function now(): float { return isset($this->deps['uptime']) ? (float)($this->deps['uptime'])() : (float)explode(' ',file_get_contents('/proc/uptime'))[0]; }
    private function boot(): string { return isset($this->deps['boot']) ? ($this->deps['boot'])() : trim(file_get_contents('/proc/sys/kernel/random/boot_id')); }
    private static function id(mixed $value): bool { return is_string($value) && (bool)preg_match('/^[a-f0-9]{32}$/D',$value); }
    private static function hash(mixed $value): bool { return is_string($value) && (bool)preg_match('/^[a-f0-9]{64}$/D',$value); }
    public function directory(bool $create=false): ?string
    {
        for ($p=$this->root; $p!=='/' && $p!=='.'; $p=dirname($p)) if (is_link($p)) throw new RuntimeException('invalid_state');
        if (!file_exists($this->root)) {
            if (!$create) return null;
            $mask=umask(0077);
            try { if (!@mkdir($this->root,0700,true) && !is_dir($this->root)) throw new RuntimeException('storage_unavailable'); }
            finally { umask($mask); }
        }
        $s=lstat($this->root);
        if (($s['mode']&0170000)!==0040000 || $s['uid']!==$this->owner || ($s['mode']&0777)!==0700) throw new RuntimeException('invalid_state');
        return $this->root;
    }
    private function regular(string $path, int $limit): ?array
    {
        clearstatcache(true,$path); $s=@lstat($path); if (!$s) return null;
        if (($s['mode']&0170000)!==0100000 || $s['uid']!==$this->owner || $s['nlink']!==1 || ($s['mode']&0777)!==0600 || $s['size']>$limit) throw new RuntimeException('invalid_state');
        return $s;
    }
    private function read(string $name, int $limit=262144): ?array
    {
        $path=$this->root.'/'.$name; if ($this->regular($path,$limit)===null) return null;
        $raw=@file_get_contents($path); if (!is_string($raw) || strlen($raw)>$limit) throw new RuntimeException('invalid_state');
        try { $v=json_decode($raw,true,32,JSON_THROW_ON_ERROR); }
        catch (Throwable $e) { throw new RuntimeException('invalid_state'); }
        if (!is_array($v)) throw new RuntimeException('invalid_state'); return $v;
    }
    private function write(string $name, array $value, int $limit=262144): void
    {
        $this->regular($this->root.'/'.$name,$limit);
        $raw=json_encode($value,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);
        if (strlen($raw)>$limit) throw new RuntimeException('output_limit');
        $tmp=$this->root.'/.write-'.bin2hex(random_bytes(16)); $mask=umask(0077);
        try { $f=@fopen($tmp,'xb'); } finally { umask($mask); }
        if (!$f) throw new RuntimeException('insufficient_space');
        try {
            if (@fwrite($f,$raw)!==strlen($raw) || !@fflush($f) || (function_exists('fsync') && !@fsync($f))) throw new RuntimeException('insufficient_space');
            fclose($f); $f=null;
            if (!@rename($tmp,$this->root.'/'.$name)) throw new RuntimeException('invalid_state');
        } finally { if (is_resource($f)) fclose($f); if (is_file($tmp)) unlink($tmp); }
    }
    private function locked(callable $fn, bool $write=true): mixed
    {
        if ($this->directory($write)===null) return $fn();
        $path=$this->root.'/state.lock'; $exists=$this->regular($path,0)!==null;
        if (!$exists && !$write) return $fn();
        $mask=umask(0077);
        try { $f=@fopen($path,$write?'c':'r'); } finally { umask($mask); }
        if (!$f) throw new RuntimeException('invalid_state');
        // Status polls briefly hold a shared lock. Wait only for acquisition:
        // the journal callback (and every native DNS action outside it) runs once.
        $end=hrtime(true)+1000000000;
        try {
            do {
                if (flock($f,($write?LOCK_EX:LOCK_SH)|LOCK_NB)) return $fn();
                if (hrtime(true)>=$end) throw new RuntimeException('busy');
                usleep(10000);
            } while (true);
        }
        finally { flock($f,LOCK_UN); fclose($f); }
    }
    private function journal(): array
    {
        $j=$this->read('state.json')??['schema_version'=>1,'job'=>null,'history'=>[],'backups'=>[],'active'=>null];
        if (count($j)!==5 || !array_key_exists('job',$j) || !array_key_exists('active',$j) || ($j['schema_version']??null)!==1 || !is_array($j['history']??null) || !array_is_list($j['history']) || count($j['history'])>16 || !is_array($j['backups']??null) || !array_is_list($j['backups']) || count($j['backups'])>8) throw new RuntimeException('invalid_state');
        foreach (array_merge([$j['job']],$j['history']) as $job) if ($job!==null) {
            if (!is_array($job) || !is_string($job['request_id']??null) || !self::id($job['request_id']) || !in_array($job['state']??null,self::STATES,true) || !is_string($job['profile_hash']??null) || !self::hash($job['profile_hash']) || !is_string($job['baseline_hash']??null) || !self::hash($job['baseline_hash']) || !array_key_exists('backup_id',$job) || ($job['backup_id']!==null && (!is_string($job['backup_id']) || !self::id($job['backup_id'])))) throw new RuntimeException('invalid_state');
        }
        foreach ($j['backups'] as $id) if (!is_string($id) || !self::id($id)) throw new RuntimeException('invalid_state');
        if ($j['active']!==null && (!is_array($j['active']) || !is_string($j['active']['profile_hash']??null) || !self::hash($j['active']['profile_hash']) || !is_string($j['active']['backup_id']??null) || !self::id($j['active']['backup_id']))) throw new RuntimeException('invalid_state');
        return $j;
    }
    public function saveDraft(array $profile): string
    {
        $profile=AsusSmartDnsProfile::normalize($profile); $hash=AsusSmartDnsProfile::hash($profile);
        return $this->locked(function()use($profile,$hash){$this->write('draft.json',$profile,65536);return $hash;});
    }
    public function draft(): ?array
    { return $this->locked(fn()=>($p=$this->read('draft.json',65536))===null?null:AsusSmartDnsProfile::normalize($p),false); }
    /** Resolve a journal-bound source without ever replacing the editor draft. */
    private function selectedProfile(array $binding,string $error): array
    {
        $source=$binding['profile_source']??'draft';
        if ($source==='draft') $profile=$this->read('draft.json',65536);
        elseif ($source==='confirmed') {
            $raw=$this->read('resume-intent.json',131072);$intent=$raw===null?null:self::checkedIntent($raw);
            if ($intent===null || ($binding['source_request_id']??null)!==$intent['source_request_id'] ||
                ($binding['engine_sha']??null)!==$intent['engine_sha']) throw new RuntimeException($error);
            $profile=$intent['profile'];
        } else throw new RuntimeException('invalid_state');
        if ($profile===null || !self::hash($binding['profile_hash']??null) ||
            !hash_equals(AsusSmartDnsProfile::hash($profile),$binding['profile_hash'])) throw new RuntimeException($error);
        return AsusSmartDnsProfile::normalize($profile);
    }
    public function candidate(array $binding): array
    { return $this->locked(fn()=>$this->selectedProfile($binding,($binding['profile_source']??'draft')==='draft'?'stale_draft':'stale_preview'),false); }
    private static function sourceFields(array $binding): array
    { return array_intersect_key($binding,array_flip(['profile_source','source_request_id','engine_sha'])); }
    /** Import/undo changes only the draft, including restoring its absence. */
    public function replaceDraft(?array $profile, ?string $expectedHash): ?string
    {
        if ($expectedHash!==null && !self::hash($expectedHash)) throw new RuntimeException('invalid_request');
        if ($profile!==null) $profile=AsusSmartDnsProfile::normalize($profile);
        $hash=$profile===null?null:AsusSmartDnsProfile::hash($profile);
        return $this->locked(function()use($profile,$hash,$expectedHash){
            $old=$this->read('draft.json',65536);
            $actual=$old===null?null:AsusSmartDnsProfile::hash(AsusSmartDnsProfile::normalize($old));
            if ($actual!==$expectedHash) throw new RuntimeException('stale_draft');
            if ($profile!==null) $this->write('draft.json',$profile,65536);
            elseif ($this->regular($this->root.'/draft.json',65536)!==null && !@unlink($this->root.'/draft.json')) throw new RuntimeException('storage_unavailable');
            return $hash;
        });
    }
    public function savePreview(array $preview): void
    {
        if (!self::id($preview['id']??null) || !self::hash($preview['profile_hash']??null) || !self::hash($preview['baseline_hash']??null) || !is_numeric($preview['expires_uptime']??null) || !is_finite((float)$preview['expires_uptime'])) throw new RuntimeException('invalid_request');
        $preview['boot']=$this->boot();
        $this->locked(function()use($preview){
            $job=$this->journal()['job'];
            // Only a root-started validation journal can select saved consent.
            if (isset($preview['profile_source'])) throw new RuntimeException('invalid_request');
            if (($job['state']??null)==='validating') $preview+=self::sourceFields($job);
            $this->selectedProfile($preview,'stale_preview');
            if ($job!==null && in_array($job['state'],self::LIVE,true)) {
                if ($job['state']!=='validating') throw new RuntimeException('busy');
                if ($job['profile_hash']!==$preview['profile_hash'] || $job['baseline_hash']!==$preview['baseline_hash']) throw new RuntimeException('stale_preview');
                $preview['validation_request_id']=$job['request_id'];
            }
            $this->write('preview.json',$preview,131072);
        });
    }
    private function checkedPreview(string $id): array
    {
        $p=$this->read('preview.json',131072);
        if ($p===null || !self::id($id) || ($p['id']??null)!==$id || ($p['boot']??null)!==$this->boot() || !self::hash($p['profile_hash']??null) || !self::hash($p['baseline_hash']??null) || !is_numeric($p['expires_uptime']??null) || !is_finite((float)$p['expires_uptime']) || $this->now()>=(float)$p['expires_uptime']) throw new RuntimeException('stale_preview');
        $this->selectedProfile($p,'stale_preview');
        if (isset($p['validation_request_id'])) {
            $job=$this->journal()['job'];
            if (($job['state']??null)!=='preview_ready' || ($job['request_id']??null)!==$p['validation_request_id'] || ($job['preview_id']??null)!==$id) throw new RuntimeException('stale_preview');
        }
        return $p;
    }
    public function preview(string $id): array { return $this->locked(fn()=>$this->checkedPreview($id),false); }
    private function publicStatus(array $j, ?array $job=null): array
    {
        $v=$job??$j['job']; $left=null;
        if (($v['state']??'')==='awaiting_confirmation' && isset($v['deadline_uptime'])) $left=max(0,(int)ceil((float)$v['deadline_uptime']-$this->now()));
        return ['schema_version'=>1,'state'=>$v['state']??'idle','request_id'=>$v['request_id']??null,'code'=>$v['code']??null,
            'preview_id'=>($v['state']??'')==='preview_ready'?($v['preview_id']??null):null,
            'active_profile_hash'=>$j['active']['profile_hash']??null,'deadline_remaining_s'=>$left,'checks'=>$v['checks']??[],'conflicts'=>$v['conflicts']??[]];
    }
    public function beginValidation(string $requestId, string $profileHash, string $baselineHash,string $source='draft'): array
    {
        if (!self::id($requestId) || !self::hash($profileHash) || !self::hash($baselineHash) || !in_array($source,['draft','confirmed'],true)) throw new RuntimeException('invalid_request');
        return $this->locked(function()use($requestId,$profileHash,$baselineHash,$source){
            $j=$this->journal();
            $binding=['profile_hash'=>$profileHash];
            if ($source==='confirmed') {
                $raw=$this->read('resume-intent.json',131072);$intent=$raw===null?null:self::checkedIntent($raw);
                if ($intent===null) throw new RuntimeException('stale_preview');
                $binding+=['profile_source'=>'confirmed','source_request_id'=>$intent['source_request_id'],'engine_sha'=>$intent['engine_sha']];
            }
            $this->selectedProfile($binding,$source==='draft'?'stale_draft':'stale_preview');
            foreach (array_filter(array_merge([$j['job']],$j['history'])) as $job) if ($job['request_id']===$requestId) {
                if ($job['profile_hash']!==$profileHash || $job['baseline_hash']!==$baselineHash || self::sourceFields($job)!==self::sourceFields($binding)) throw new RuntimeException('request_conflict');
                return $this->publicStatus($j,$job);
            }
            if ($j['job']!==null && in_array($j['job']['state'],self::LIVE,true)) throw new RuntimeException('busy');
            // Invalidate first: a failed journal write must never leave an old
            // preview eligible after a new validation attempt.
            if ($this->regular($this->root.'/preview.json',131072)!==null && !unlink($this->root.'/preview.json')) throw new RuntimeException('invalid_state');
            if ($j['job']!==null) {array_unshift($j['history'],$j['job']);$j['history']=array_slice($j['history'],0,16);}
            $j['job']=['request_id'=>$requestId,'state'=>'validating','code'=>null,'profile_hash'=>$profileHash,'baseline_hash'=>$baselineHash,'preview_id'=>null,'boot'=>$this->boot(),'started_uptime'=>$this->now(),'backup_id'=>null]+self::sourceFields($binding);
            $this->write('state.json',$j); return $this->publicStatus($j);
        });
    }
    public function begin(string $requestId, string $profileHash, string $baselineHash): array
    {
        if (!self::id($requestId) || !self::hash($profileHash) || !self::hash($baselineHash)) throw new RuntimeException('invalid_request');
        return $this->locked(function()use($requestId,$profileHash,$baselineHash){
            $j=$this->journal();
            foreach (array_filter(array_merge([$j['job']],$j['history'])) as $job) if ($job['request_id']===$requestId) {
                if ($job['profile_hash']!==$profileHash || $job['baseline_hash']!==$baselineHash) throw new RuntimeException('request_conflict');
                return $this->publicStatus($j,$job);
            }
            if ($j['job']!==null && in_array($j['job']['state'],self::LIVE,true)) throw new RuntimeException('busy');
            $p=$this->read('preview.json',131072); if ($p===null) throw new RuntimeException('stale_preview');
            $p=$this->checkedPreview($p['id']);
            if ($p['profile_hash']!==$profileHash || $p['baseline_hash']!==$baselineHash) throw new RuntimeException('stale_preview');
            if ($j['job']!==null) {array_unshift($j['history'],$j['job']);$j['history']=array_slice($j['history'],0,16);}
            $j['job']=['request_id'=>$requestId,'state'=>'applying','code'=>null,'profile_hash'=>$profileHash,'baseline_hash'=>$baselineHash,'preview_id'=>$p['id'],'boot'=>$this->boot(),'started_uptime'=>$this->now(),'backup_id'=>null]+self::sourceFields($p);
            $this->write('state.json',$j); return $this->publicStatus($j);
        });
    }
    public function status(): array { return $this->locked(fn()=>$this->publicStatus($this->journal()),false); }
    /** One consistent internal read; raw job/profile metadata never goes to HTTP. */
    public function view(): array
    { return $this->locked(function(){ $j=$this->journal();return ['status'=>$this->publicStatus($j),'job'=>$j['job'],'active'=>$j['active']]; },false); }
    /** Internal replay lookup: never replace a newer job to answer a lost reply. */
    public function receipt(string $requestId): ?array
    {
        if (!self::id($requestId)) throw new RuntimeException('invalid_request');
        return $this->locked(function()use($requestId){
            $j=$this->journal();
            foreach (array_filter(array_merge([$j['job']],$j['history'])) as $job) if ($job['request_id']===$requestId)
                return ['job'=>$job,'status'=>$this->publicStatus($j,$job)];
            return null;
        },false);
    }
    /** Internal trusted owner metadata, not exposed by HTTP status. */
    public function transaction(): ?array { return $this->locked(fn()=>$this->journal()['job'],false); }
    public function transition(string $requestId, array $expectedStates, array $patch): array
    {
        return $this->locked(function()use($requestId,$expectedStates,$patch){
            $j=$this->journal(); $v=$j['job'];
            if ($v===null || $v['request_id']!==$requestId || !in_array($v['state'],$expectedStates,true)) throw new RuntimeException('stale_state');
            $allowed=['state','code','checks','conflicts','deadline_uptime','identity','guard_identity','backup_id','engine_sha','active','preview_id'];
            foreach ($patch as $key=>$value) if (!in_array($key,$allowed,true)) throw new RuntimeException('invalid_request');
            if (array_key_exists('preview_id',$patch) && !self::id($patch['preview_id'])) throw new RuntimeException('invalid_request');
            if (isset($patch['state']) && !in_array($patch['state'],self::STATES,true)) throw new RuntimeException('invalid_request');
            if (isset($patch['code']) && (!is_string($patch['code']) || !preg_match('/^[a-z0-9_]{1,64}$/D',$patch['code']))) throw new RuntimeException('invalid_request');
            if (array_key_exists('active',$patch)) {
                $a=$patch['active'];
                if ($a!==null && (!is_array($a) || !self::hash($a['profile_hash']??'') || !self::id($a['backup_id']??'') || !hash_equals(AsusSmartDnsProfile::hash($a['profile']??[]),$a['profile_hash']))) throw new RuntimeException('invalid_state');
                $j['active']=$a; unset($patch['active']);
            }
            $j['job']=array_replace($v,$patch); $this->write('state.json',$j); return $this->publicStatus($j);
        });
    }
    public function backup(array $snapshot): string
    {
        return $this->locked(function()use($snapshot){
            $j=$this->journal(); $id=bin2hex(random_bytes(16)); $this->write('backup-'.$id.'.json',$snapshot,524288);
            array_unshift($j['backups'],$id);
            if ($j['job']!==null && in_array($j['job']['state'],self::LIVE,true) && $j['job']['backup_id']===null) $j['job']['backup_id']=$id;
            $keep=array_unique(array_filter(array_merge(array_slice($j['backups'],0,3),[$j['job']['backup_id']??null,$j['active']['backup_id']??null])));
            $remove=array_diff($j['backups'],$keep); $j['backups']=array_values(array_intersect($j['backups'],$keep));
            $this->write('state.json',$j);
            foreach ($remove as $old) {if (!self::id($old)) throw new RuntimeException('invalid_state'); $path=$this->root.'/backup-'.$old.'.json';if ($this->regular($path,524288)!==null) unlink($path);}
            return $id;
        });
    }
    public function snapshot(string $id): array
    { if (!self::id($id)) throw new RuntimeException('invalid_request'); return $this->locked(fn()=>$this->read('backup-'.$id.'.json',524288)??throw new RuntimeException('invalid_state'),false); }
    public function active(): ?array { return $this->locked(fn()=>$this->journal()['active'],false); }
    private static function checkedIntent(array $value): array
    {
        $keys=array_keys($value);sort($keys);$expected=['schema_version','profile','profile_hash','engine_sha','source_request_id'];sort($expected);
        if ($keys!==$expected || $value['schema_version']!==1 || !self::hash($value['profile_hash']) || !self::hash($value['engine_sha']) || !self::id($value['source_request_id']) || !is_array($value['profile'])) throw new RuntimeException('invalid_state');
        $value['profile']=AsusSmartDnsProfile::normalize($value['profile']);
        if (!hash_equals($value['profile_hash'],AsusSmartDnsProfile::hash($value['profile']))) throw new RuntimeException('invalid_state');
        return $value;
    }
    public function intent(): ?array
    { return $this->locked(fn()=>($v=$this->read('resume-intent.json',131072))===null?null:self::checkedIntent($v),false); }
    public function saveIntent(?array $value): void
    {
        if ($value===null && $this->directory(false)===null) return;
        if ($value!==null) $value=self::checkedIntent($value);
        $this->locked(function()use($value){
            if ($value!==null) {$this->write('resume-intent.json',$value,131072);return;}
            if ($this->regular($this->root.'/resume-intent.json',131072)!==null && !@unlink($this->root.'/resume-intent.json')) throw new RuntimeException('storage_unavailable');
        });
    }
}
