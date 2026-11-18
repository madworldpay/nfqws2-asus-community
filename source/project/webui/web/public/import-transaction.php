<?php
require_once __DIR__.'/import-plan.php';
require_once __DIR__.'/import-store.php';
require_once __DIR__.'/share-resources.php';
require_once __DIR__.'/smartdns-store.php';
/** Config-last journal commit. No command runner, service or DNS-runtime API. */
final class AsusImportTransaction
{
    private AsusImportStore $store;
    private AsusSmartDnsStore $dns;
    private AsusShareRead $reader;
    private string $root;
    private string $config;
    private AsusShareResources $resources;
    public function __construct(?AsusImportStore $store=null,?AsusSmartDnsStore $dns=null,?string $resourceRoot=null,?string $configPath=null,private int $owner=0,private array $deps=[])
    {
        $this->store=$store??new AsusImportStore();$this->dns=$dns??new AsusSmartDnsStore();$this->root=$resourceRoot??AsusDpiStore::optPath('/etc/nfqws2');$this->config=$configPath??$this->root.'/nfqws2.conf';
        $this->reader=$resourceRoot===null?NfqwsPlatform::reader($owner,true):new AsusShareRead($owner,null,null,true);$this->resources=new AsusShareResources($resourceRoot,$owner);
    }
    public function writer(callable $fn): mixed {return $this->store->locked($fn);}
    /** Read a supplement proposal under the same mutex as panel saves/imports.
     * No recovery, journal commit, service action or mutation lease is used. */
    private function supplementRead(callable $fn,?callable $verify=null):array
    {
        return $this->writer(function()use($fn,$verify){
            $state=$this->store->state();
            if(in_array($state['current']['state']??null,['prepared','committing','undoing','restore_required'],true))
                throw new RuntimeException('busy');
            $raw=$this->raw($this->config);if($raw===null)throw new RuntimeException('strategy_unavailable');
            $result=$fn($raw);$this->checkpoint('supplement_read');
            if($verify!==null)$verify($raw,$result);
            if($this->raw($this->config)!==$raw||$this->store->state()!==$state)throw new RuntimeException('source_changed');
            return $result;
        });
    }
    public function supplementState():array
    {
        require_once __DIR__.'/strategy-supplement.php';
        return $this->supplementRead(function(string $raw){
            $view=NfqwsStrategySupplement::inventory($this->resources);
            return ['mode'=>'supplement-saved-state-v1','binding'=>['config_sha256'=>hash('sha256',$raw),
                'resources_sha256'=>$view['resources_sha256']],'saved_config_bound'=>true,
                'can_apply'=>false,'can_export'=>false,'combined_verified'=>false,'actual_device_calls'=>false];
        });
    }
    public function supplementPreview(array $recipe,array $domains,array $binding):array
    {
        require_once __DIR__.'/strategy-supplement.php';
        return $this->supplementRead(function(string $raw)use($recipe,$domains,$binding){
            $proposal=NfqwsStrategySupplement::prepare($this->resources,$raw,$recipe,$domains,$binding);
            $result=['mode'=>'supplement-saved-preview-v1','binding'=>$binding,'proposal'=>$proposal,
                'saved_config_bound'=>true,'can_apply'=>false,'can_export'=>false,
                'combined_verified'=>false,'actual_device_calls'=>false];
            return $result+['preview_sha256'=>hash('sha256',json_encode($result,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR))];
        });
    }
    /** Internal saved-source binding for the complete portable proposal.
     * The comparison hashes identify inputs, not successful native results.
     * Apply/export and backup/rollback still use their separate gates. */
    public function supplementPortablePreview(array $recipe,array $domains,array $binding,bool $withLocalPlan=false):array
    {
        require_once __DIR__.'/strategy-supplement.php';
        return $this->supplementRead(function(string $raw)use($recipe,$domains,$binding,$withLocalPlan){
            $proposal=NfqwsStrategySupplement::prepare($this->resources,$raw,$recipe,$domains,$binding);
            $portable=NfqwsStrategySupplement::portablePreview($this->resources,$raw,$proposal);
            $preview=$proposal['preview'];
            $comparison=['original_config_sha256'=>hash('sha256',$raw),
                'combined_config_sha256'=>$preview['candidate_sha256'],
                'resources_sha256'=>$preview['resources_sha256'],
                'resource_kit_sha256'=>$proposal['resource_kit_sha256'],
                'proposal_sha256'=>$proposal['proposal_sha256'],'domains'=>$preview['domains']];
            $result=['mode'=>'supplement-saved-portable-preview-v1','binding'=>$binding,
                'proposal'=>$proposal,'portable'=>$portable,'comparison_binding'=>$comparison,
                'saved_config_bound'=>true,'backup_ready'=>false,'can_apply'=>false,'can_export'=>false,
                'combined_verified'=>false,'actual_device_calls'=>false];
            if($withLocalPlan){
                // SAME saved source: compile only CUSTOM against the current
                // inventory. The separate portable kit remains complete, but
                // importing it here could rebind the owner's base blob paths.
                $values=AsusImportConfig::parse($preview['candidate_config']);
                $source=['type'=>'nfqws2_strategy','schema_version'=>1,
                    'versions'=>['core'=>'unverified','web'=>'supplement-local-plan-v1'],
                    'purpose'=>'Локальный вход компилятора дополнения','operator'=>'Не указан',
                    'comment'=>'Входные данные без разрешения на применение, экспорт или native-проверку.',
                    'dependencies'=>[],'mode'=>'blocks',
                    'blocks'=>[['key'=>'NFQWS_ARGS_CUSTOM','value'=>$values['NFQWS_ARGS_CUSTOM']]]];
                $document=AsusImportDocument::read([json_encode($source,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR)]);
                $selection=['blocks'=>$source['blocks'],'shared'=>[],'ports'=>[],'files'=>[],'dns'=>[],
                    'allow_shared_impact'=>false,'allow_incomplete'=>false,'trusted_lua'=>false];
                $plan=AsusImportPlan::prepare($document,$selection,$raw,$this->resources->inventory(),$this->dns->draft());
                if($plan['config']!==$preview['candidate_config']||$plan['files']!==[]||$plan['draft']!==null||
                    array_column($plan['changes'],'key')!==['NFQWS_ARGS_CUSTOM'])throw new RuntimeException('supplement_plan_incompatible');
                $this->checkPlan($plan);
                $result['local_plan']=$plan;
                $result['local_plan_binding']=['original_config_sha256'=>hash('sha256',$raw),
                    'postplan_config_sha256'=>hash('sha256',$plan['config']),
                    'resources_sha256'=>$preview['resources_sha256'],'resource_kit_sha256'=>$proposal['resource_kit_sha256'],
                    'proposal_sha256'=>$proposal['proposal_sha256'],'plan_sha256'=>$plan['digest'],
                    'plan_input_sha256'=>$plan['input_sha256'],'draft_sha256'=>$plan['fingerprints']['draft'],
                    'domains'=>$preview['domains']];
            }
            return $result;
        },function(string $raw,array $result){
            // Re-read resources after serialization/checkpoint, before the
            // existing saved-config and transaction-state checks release lock.
            NfqwsStrategySupplement::recheck($this->resources,$raw,$result['proposal']);
            if(isset($result['local_plan']))$this->checkPlan($result['local_plan']);
        });
    }
    private function checkpoint(string $phase): void {if(isset($this->deps['checkpoint']))($this->deps['checkpoint'])($phase);}
    private function path(string $logical): string
    {if(NfqwsResourcePaths::canonical($logical)!==$logical)throw new RuntimeException('invalid_state');return $this->root.substr($logical,strlen('/opt/etc/nfqws2'));}
    private function raw(string $path,?array &$pin=null): ?string
    {
        $pin=null;$dir=dirname($path);clearstatcache(true,$dir);
        if(@lstat($dir)===false&&preg_match('~^'.preg_quote($this->root,'~').'/(lua|blobs)/imported$~D',$dir)&&$this->reader->directory(dirname($dir)))return null;
        if(!$this->reader->directory($dir))throw new RuntimeException('source_changed');clearstatcache(true,$path);if(@lstat($path)===false)return null;
        if(func_num_args()===1)return $this->reader->bytes($path,262144);
        // Pin the same guarded buffer, not a later pathname observation.
        $before=$this->reader->stat($path);if(!$before)throw new RuntimeException('source_changed');
        $raw=$this->reader->bytes($path,262144);$after=$this->reader->stat($path);
        if(!$after||self::sourceSignature($before)!==self::sourceSignature($after)||!$this->reader->directory($dir))throw new RuntimeException('source_changed');
        $pin=self::sourceSignature($before);return $raw;
    }
    private static function sourceSignature(array $stat):array
    {return array_intersect_key($stat,array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));}
    private static function identity(array $stat):array
    {return ['dev'=>$stat['dev'],'ino'=>$stat['ino'],'uid'=>$stat['uid'],'gid'=>$stat['gid'],'mode'=>$stat['mode']];}
    private static function sameIdentity(string $path,array $identity):bool
    {clearstatcache(true,$path);$s=@lstat($path);if($s===false)return false;foreach(self::identity($s) as $key=>$value)if(($identity[$key]??null)!==$value)return false;return true;}
    private function saveJournal(array $j):void
    {$s=$this->store->state();if(($s['current']['id']??null)!==$j['id'])throw new RuntimeException('invalid_state');$s['current']=$j;$this->store->save($s);}
    /** Durable creation intent, then exact directory identity. A death in the
     * mkdir/identity gap is attention, never ownership inferred from a name. */
    private function directories(array &$j):void
    {
        foreach($j['files'] as $f){
            if(!preg_match('~^/opt/etc/nfqws2/(lua|blobs)/imported/~D',$f['path'],$m))continue;
            $kind=$m[1];$dir=$this->root.'/'.$kind.'/imported';clearstatcache(true,$dir);
            if(@lstat($dir)!==false){if(!$this->reader->directory($dir))throw new RuntimeException('source_changed');if(!isset($j['directories'][$kind])&&!isset($j['parents'][$kind])){$j['parents'][$kind]=self::identity(lstat($dir));$this->saveJournal($j);}continue;}
            if(!$this->reader->directory(dirname($dir)))throw new RuntimeException('source_changed');
            $j['directories'][$kind]=null;$this->saveJournal($j);$this->checkpoint('directory_intent_'.$kind);
            $mask=umask(0022);try{$ok=@mkdir($dir,0755);}finally{umask($mask);}if(!$ok)throw new RuntimeException('source_changed');
            $this->checkpoint('directory_created_'.$kind);
            if(!$this->reader->directory($dir))throw new RuntimeException('source_changed');
            $j['directories'][$kind]=self::identity(lstat($dir));$this->saveJournal($j);$this->checkpoint('directory_'.$kind);
        }
    }
    private function removeDirectories(array $j):void
    {
        foreach($j['directories']??[] as $kind=>$identity){$dir=$this->root.'/'.$kind.'/imported';clearstatcache(true,$dir);if(@lstat($dir)===false)continue;
            if($identity===null||!self::sameIdentity($dir,$identity)||!$this->reader->directory($dir)||!@rmdir($dir))throw new RuntimeException('restore_required');
        }
    }
    private function directoriesMatch(array $j):bool
    {
        foreach($j['parents']??[] as $kind=>$identity){$dir=$this->root.'/'.$kind.'/imported';if(!self::sameIdentity($dir,$identity)||!$this->reader->directory($dir))return false;}
        foreach($j['directories']??[] as $kind=>$identity){$dir=$this->root.'/'.$kind.'/imported';clearstatcache(true,$dir);
            if(@lstat($dir)!==false&&($identity===null||!self::sameIdentity($dir,$identity)||!$this->reader->directory($dir)))return false;
            if(@lstat($dir)!==false){
                $allowed=['.'=>true,'..'=>true];
                foreach($j['files'] as $i=>$file)if(dirname($this->path($file['path']))===$dir){$allowed[basename($file['path'])]=true;$allowed[basename($this->stage($j,$i))]=true;}
                $entries=@scandir($dir);if(!is_array($entries)||count($entries)>258)return false;
                foreach($entries as $name)if(!isset($allowed[$name]))return false;
            }
        }return true;
    }
    private function hash(string $path): ?string {$v=$this->raw($path);return $v===null?null:hash('sha256',$v);}
    private function draftHash(): ?string {$d=$this->dns->draft();return $d===null?null:AsusSmartDnsProfile::hash($d);}
    public function prepare(array $documents,array $selection,?array $catalogScope=null,array $addons=[]): array
    {
        $doc=AsusImportDocument::read($documents);$raw=$this->raw($this->config);if($raw===null)throw new RuntimeException('strategy_unavailable');
        return AsusImportPlan::prepare($doc,$selection,$raw,$this->resources->inventory(),$this->dns->draft(),null,$catalogScope,$addons,fn($file)=>base64_decode($this->resources->read($file['id'],$file['sha256'])['data_base64'],true));
    }
    public function inspect(array $documents): array {return AsusImportDocument::read($documents);}
    private function publicJob(?array $j): array
    {return ['state'=>$j['state']??'idle','id'=>$j['id']??null,'can_undo'=>($j['state']??null)==='committed','config_saved'=>($j['config_changed']??false)&&($j['state']??null)==='committed','dns_draft_saved'=>($j['dns_changed']??false)&&($j['state']??null)==='committed'];}
    public function status(): array {return $this->publicJob($this->store->state()['current']);}
    public function undoDigest(): string
    {
        $j=$this->store->state()['current'];$files=[];
        foreach($j['files']??[]as $f)$files[$f['path']]=$this->hash($this->path($f['path']));
        return hash('sha256',json_encode([$j,$this->hash($this->config),$this->draftHash(),$files],JSON_THROW_ON_ERROR));
    }
    public function receipt(string $id,string $digest): ?array
    {
        foreach(array_merge([$this->store->state()['current']],$this->store->state()['history'])as $j)if($j!==null&&$j['id']===$id){if($j['request_digest']!==$digest)throw new RuntimeException('request_conflict');return $this->publicJob($j);}return null;
    }
    private function checkPlan(array $p): void
    {
        if(($p['ready']??false)!==true)throw new RuntimeException('import_not_ready');$f=$p['fingerprints'];
        if($this->hash($this->config)!==$f['config']||$this->draftHash()!==$f['draft'])throw new RuntimeException('source_changed');
        foreach($f['files']as $logical=>$hash)if($this->hash($this->path($logical))!==$hash)throw new RuntimeException('source_changed');
    }
    private function tempPath(array $j,string $tag): string
    {return dirname($this->config).'/.import-'.$j['id'].'-'.$tag;}
    private function atomicConfig(string $raw,string $expected,array $j,?callable $verify=null): void
    {
        if($this->hash($this->config)!==$expected)throw new RuntimeException('source_changed');$s=$this->reader->stat($this->config);$temp=$this->tempPath($j,'config');$this->writeNew($temp,$raw,0600);$this->checkpoint('config_stage');
        try{if($verify!==null)$verify();if($this->hash($this->config)!==$expected)throw new RuntimeException('source_changed');
            if($s['uid']!==$this->owner&&!@chown($temp,$s['uid']))throw new RuntimeException('storage_unavailable');
            if(!@chgrp($temp,$s['gid'])||!@chmod($temp,$s['mode']&0777)||!@rename($temp,$this->config))throw new RuntimeException('storage_unavailable');
        }finally{if(@lstat($temp)!==false)@unlink($temp);}
    }
    private function writeNew(string $path,string $raw,int $mode=0644): array
    {
        if(!$this->reader->directory(dirname($path)))throw new RuntimeException('source_changed');$mask=umask(0077);try{$f=@fopen($path,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('source_changed');
        $created=fstat($f);if(!$created){fclose($f);throw new RuntimeException('storage_unavailable');}
        try{if(@fwrite($f,$raw)!==strlen($raw)||!@fflush($f)||(function_exists('fsync')&&!@fsync($f))||!@chmod($path,$mode))throw new RuntimeException('insufficient_space');
            $opened=fstat($f);if(!$opened||$created['dev']!==$opened['dev']||$created['ino']!==$opened['ino']||!self::sameIdentity($path,self::identity($opened)))throw new RuntimeException('source_changed');
            return self::identity($opened);
        }catch(Throwable $e){$opened=fstat($f);if($opened&&self::sameIdentity($path,self::identity($opened)))@unlink($path);throw $e;}finally{fclose($f);}
    }
    private function stage(array $j,int $i): string
    {return dirname($this->path($j['files'][$i]['path'])).'/.import-'.$j['id'].'-'.$i;}
    /** Verify the opened inode as well as its name; allow two links only during
     * our no-clobber publication, before the stage name is removed. */
    private function ownedBytes(string $path,array $identity,string $sha,array $links=[1]):bool
    {
        if(!self::sameIdentity($path,$identity)||!$this->reader->directory(dirname($path)))return false;
        $f=@fopen($path,'rb');if(!$f)return false;
        try{$s=fstat($f);if(!$s||array_diff_assoc(self::identity($s),$identity)!==[]||($s['mode']&0170000)!==0100000||!in_array($s['nlink'],$links,true)||$s['size']>262144)return false;
            $raw=stream_get_contents($f,262145);$after=fstat($f);
            return is_string($raw)&&strlen($raw)===$s['size']&&hash('sha256',$raw)===$sha&&array_intersect_key($after,array_flip(['dev','ino','mode','uid','gid','size','nlink','mtime','ctime']))===array_intersect_key($s,array_flip(['dev','ino','mode','uid','gid','size','nlink','mtime','ctime']))&&self::sameIdentity($path,$identity);
        }finally{fclose($f);}
    }
    private function inputsMatch(array $j):bool
    {foreach($j['inputs']??[] as $logical=>$sha)if($this->hash($this->path($logical))!==$sha)return false;return true;}
    private function published(array $j):void
    {
        if(!$this->directoriesMatch($j)||!$this->inputsMatch($j))throw new RuntimeException('source_changed');
        foreach($j['files'] as $f){$path=$this->path($f['path']);if($this->hash($path)!==$f['sha256']||str_contains($f['path'],'/imported/')&&(!isset($f['identity'])||!self::sameIdentity($path,$f['identity'])))throw new RuntimeException('source_changed');}
    }
    /** Replace only the exact reviewed file; new files retain no-clobber linking. */
    private function putFile(array &$j,int $i,string $raw,?string $expected,int $mode): void
    {
        $f=$j['files'][$i];$path=$this->path($f['path']);$tmp=$this->stage($j,$i);
        if(!$this->directoriesMatch($j)||$this->hash($path)!==$expected)throw new RuntimeException('source_changed');
        $identity=$this->writeNew($tmp,$raw,$mode);
        if(isset($f['metadata'])){$m=$f['metadata'];if(($m['uid']!==$this->owner&&!@chown($tmp,$m['uid']))||!@chgrp($tmp,$m['gid'])||!@chmod($tmp,$m['mode']))throw new RuntimeException('storage_unavailable');}
        $now=lstat($tmp);if(!$now||$now['dev']!==$identity['dev']||$now['ino']!==$identity['ino'])throw new RuntimeException('source_changed');
        if(isset($f['metadata']))$identity=self::identity($now);$sha=hash('sha256',$raw);
        if(str_contains($f['path'],'/imported/')){$j['files'][$i]['identity']=$identity;$this->saveJournal($j);}
        $this->checkpoint('stage_'.$i);
        if(!$this->directoriesMatch($j)||!$this->ownedBytes($tmp,$identity,$sha)||$this->hash($path)!==$expected)throw new RuntimeException('source_changed');
        if($expected===null){if(!@link($tmp,$path))throw new RuntimeException('source_changed');$this->checkpoint('linked_'.$i);if(!$this->directoriesMatch($j)||!$this->ownedBytes($tmp,$identity,$sha,[2])||!$this->ownedBytes($path,$identity,$sha,[2]))throw new RuntimeException('source_changed');if(!@unlink($tmp))throw new RuntimeException('storage_unavailable');}
        else {if(!@rename($tmp,$path))throw new RuntimeException('storage_unavailable');$this->checkpoint('linked_'.$i);if(!$this->directoriesMatch($j)||!$this->ownedBytes($path,$identity,$sha))throw new RuntimeException('source_changed');}
    }
    private function cleanupStages(array $j): void
    {
        if(isset($j['source_binding_version'])){
            // A prepared-only snapshot has never published a config, resource
            // or directory stage. A matching name/inode grants no ownership.
            $paths=[$this->tempPath($j,'config')];
            foreach($j['files']as $i=>$_)$paths[]=$this->stage($j,$i);
            foreach($paths as $path){clearstatcache(true,$path);if(@lstat($path)!==false)throw new RuntimeException('restore_required');}
            return;
        }
        if(!$this->directoriesMatch($j))throw new RuntimeException('restore_required');
        foreach($j['files']as $i=>$f){$tmp=$this->stage($j,$i);clearstatcache(true,$tmp);$s=@lstat($tmp);if(!$s)continue;
            $target=$this->path($f['path']);clearstatcache(true,$target);$t=@lstat($target);
            // A crash can leave both hardlink names; drop only our verified stage.
            if(str_contains($f['path'],'/imported/')&&(!isset($f['identity'])||!self::sameIdentity($tmp,$f['identity'])))throw new RuntimeException('restore_required');
            if(($s['mode']&0170000)!==0100000||!in_array($s['uid'],[$this->owner,$f['metadata']['uid']??$this->owner],true)||!in_array($s['mode']&0777,[0600,0644,0666,$f['metadata']['mode']??0644],true)||!in_array($s['nlink'],[1,2],true)||($s['nlink']===2&&(!$t||$s['ino']!==$t['ino']||$s['dev']!==$t['dev']))||$s['size']>262144||!$this->reader->directory(dirname($tmp)))throw new RuntimeException('restore_required');
            if(str_contains($f['path'],'/imported/')&&!$this->ownedBytes($tmp,$f['identity'],$f['sha256'],[1,2]))throw new RuntimeException('restore_required');
            if(!@unlink($tmp))throw new RuntimeException('storage_unavailable');
        }
        $tmp=$this->tempPath($j,'config');clearstatcache(true,$tmp);$s=@lstat($tmp);if($s){if(($s['mode']&0170000)!==0100000||$s['nlink']!==1||!in_array($s['uid'],[$this->owner,65534],true)||!$this->reader->directory(dirname($tmp)))throw new RuntimeException('restore_required');if(!@unlink($tmp))throw new RuntimeException('storage_unavailable');}
    }
    private function matches(array $j,bool $after,bool $partial=false): bool
    {
        if(isset($j['source_binding_version'])){
            // Prepared-only snapshots have no owned source publication. Any
            // inode/metadata drift remains foreign until separately proved.
            $paths=[$this->config=>$j['sources']['config']];
            foreach($j['sources']['files']as $logical=>$pin)$paths[$this->path($logical)]=$pin;
            foreach($paths as $path=>$expected){$pin=null;$this->raw($path,$pin);if($pin!==$expected)return false;}
        }
        if(!$this->directoriesMatch($j)||!$this->inputsMatch($j))return false;
        $cfg=$this->hash($this->config);if($cfg!==$j[$after?'after':'before']&&(!$partial||!in_array($cfg,[$j['before'],$j['after']],true)))return false;
        if($j['dns_changed']){$d=$this->draftHash();if($d!==$j[$after?'draft_after':'draft_before']&&(!$partial||!in_array($d,[$j['draft_before'],$j['draft_after']],true)))return false;}
        foreach($j['files']as $f){$path=$this->path($f['path']);$h=$this->hash($path);$before=$f['before']??null;if($h!==($after?$f['sha256']:$before)&&(!$partial||!in_array($h,[$before,$f['sha256']],true)))return false;
            if($h!==null&&str_contains($f['path'],'/imported/')&&(!isset($f['identity'])||!self::sameIdentity($path,$f['identity'])))return false;
            if(isset($f['before'],$f['metadata'])&&$h!==null){$stat=$this->reader->stat($path);$m=$f['metadata'];if(!$stat||$stat['uid']!==$m['uid']||$stat['gid']!==$m['gid']||($stat['mode']&0777)!==$m['mode'])return false;}
        }return true;
    }
    /** Validate the complete original set before any publication/restoration.
     * Keep these verified buffers for this restore; a later missing backup
     * must not cause an earlier original to be restored only halfway. */
    private function originals(array $j):array
    {
        $read=function(string $name,int $limit=262144)use($j):?string{
            $pin=null;$raw=$this->store->read($name,$limit,$pin);
            if(isset($j['backup_binding_version'])&&($j['backup_binding_version']!==1||$pin!==($j['backups'][$name]??null)))throw new RuntimeException('invalid_state');
            return $raw;
        };
        $config=$read($j['id'].'.conf');
        if($config===null||hash('sha256',$config)!==$j['before'])throw new RuntimeException('invalid_state');
        $files=[];$bytes=0;
        foreach($j['files']as $i=>$file)if(isset($file['before'])){
            $raw=$read($j['id'].'.file-'.$i);
            if($raw===null||hash('sha256',$raw)!==$file['before'])throw new RuntimeException('invalid_state');
            $bytes+=strlen($raw);if($bytes>524288)throw new RuntimeException('output_limit');$files[$i]=$raw;
        }
        $draft=null;
        if($j['dns_changed']&&$j['draft_before']!==null){
            $raw=$read($j['id'].'.draft',65536);
            if($raw===null)throw new RuntimeException('invalid_state');
            $draft=AsusSmartDnsProfile::normalize(json_decode($raw,true,32,JSON_THROW_ON_ERROR));
            if(AsusSmartDnsProfile::hash($draft)!==$j['draft_before'])throw new RuntimeException('invalid_state');
        }
        return ['config'=>$config,'files'=>$files,'draft'=>$draft];
    }
    private function restore(array &$s,string $state): void
    {
        $j=$s['current'];$originals=$this->originals($j);$this->cleanupStages($j);
        if(!$this->matches($j,false,true))throw new RuntimeException('restore_required');
        if($this->hash($this->config)!==$j['before'])$this->atomicConfig($originals['config'],$j['after'],$j);
        $this->checkpoint('undo_config');
        if($j['dns_changed']&&$this->draftHash()!==$j['draft_before'])$this->dns->replaceDraft($originals['draft'],$j['draft_after']);
        $this->checkpoint('undo_draft');
        foreach($j['files']as $i=>$f){$path=$this->path($f['path']);$actual=$this->hash($path);$before=$f['before']??null;
            if(!$this->directoriesMatch($j)||$actual!==null&&str_contains($f['path'],'/imported/')&&(!isset($f['identity'])||!self::sameIdentity($path,$f['identity'])))throw new RuntimeException('restore_required');
            if($actual!==$before){if($actual!==$f['sha256'])throw new RuntimeException('restore_required');
                if($before===null){if(!@unlink($path))throw new RuntimeException('storage_unavailable');}
                else $this->putFile($j,$i,$originals['files'][$i],$f['sha256'],$f['metadata']['mode']);
            }$this->checkpoint('undo_file_'.$i);
        }
        $this->removeDirectories($j);
        $s['current']['state']=$state;$this->store->save($s);
    }
    private function reconcile(): void
    {
        $s=$this->store->state();$j=$s['current'];if($j===null||in_array($j['state'],['committed','undone','rolled_back'],true))return;
        if($j['state']==='restore_required')throw new RuntimeException('restore_required');
        try{$this->cleanupStages($j);
            if($j['state']!=='undoing'&&$j['state']==='committing'&&$this->matches($j,true)){$this->originals($j);$s['current']['state']='committed';$this->store->save($s);return;}
            $this->restore($s,$j['state']==='undoing'?'undone':'rolled_back');
        }catch(Throwable $e){$s['current']['state']='restore_required';$this->store->save($s);throw new RuntimeException('restore_required');}
    }
    public function recover(): array {return $this->writer(function(){$this->reconcile();$this->store->prune();return $this->status();});}
    /** SAME prepared-journal writer for ordinary commits and original-only
     * supplement custody. Preserved resources never enter the publication loop. */
    private function prepareJournal(array $p,string $id,string $requestDigest,array $preserve=[],bool $snapshot=false):array
    {
        $this->checkPlan($p);$s=$this->store->state();
            if($s['current']!==null){array_unshift($s['history'],$s['current']);$s['history']=array_slice($s['history'],0,3);}
            $configPin=null;$raw=$snapshot?$this->raw($this->config,$configPin):$this->raw($this->config);$sources=['config'=>$configPin,'files'=>[]];$newFiles=[];foreach($p['files']as $f)if(!$f['reuse'])$newFiles[$f['path']]=$f;$originalFiles=$newFiles;foreach($preserve as $path=>$f){if(isset($originalFiles[$path]))throw new RuntimeException('invalid_state');$originalFiles[$path]=$f;}if(count($originalFiles)>128)throw new RuntimeException('output_limit');$files=[];$backups=[];$backupBytes=0;
            foreach($originalFiles as $f){$path=$this->path($f['path']);$sourcePin=null;$old=$snapshot?$this->raw($path,$sourcePin):$this->raw($path);if($snapshot){if($sourcePin===null)throw new RuntimeException('source_changed');$sources['files'][$f['path']]=$sourcePin;}$before=$old===null?null:hash('sha256',$old);if($before!==(isset($preserve[$f['path']])?$preserve[$f['path']]['sha256']:$p['fingerprints']['files'][$f['path']]))throw new RuntimeException('source_changed');$row=['path'=>$f['path'],'sha256'=>$f['sha256'],'before'=>$before];
                if($old!==null){$metadata=$this->reader->stat($path);if(!$metadata)throw new RuntimeException('source_changed');$row['metadata']=['uid'=>$metadata['uid'],'gid'=>$metadata['gid'],'mode'=>$metadata['mode']&0777];$backups[count($files)]=$old;$backupBytes+=strlen($old);if($backupBytes>524288)throw new RuntimeException('output_limit');}if(isset($preserve[$f['path']])&&str_contains($f['path'],'/imported/'))$row['identity']=self::identity($metadata);$files[]=$row;
            }
            $j=['id'=>$id,'state'=>'prepared','request_digest'=>$requestDigest,'before'=>hash('sha256',$raw),'after'=>hash('sha256',$p['config']),'config_changed'=>$raw!==$p['config'],'dns_changed'=>$p['draft']!==null,'draft_before'=>$p['fingerprints']['draft'],'draft_after'=>$p['draft']===null?$p['fingerprints']['draft']:AsusSmartDnsProfile::hash($p['draft']),'files'=>$files];
            if($snapshot){$j['source_binding_version']=1;$j['sources']=$sources;}
            $inputs=$p['fingerprints']['files'];foreach($files as $file)unset($inputs[$file['path']]);if($inputs)$j['inputs']=$inputs;
            $this->store->write($id.'.conf',$raw);foreach($backups as $i=>$old)$this->store->write($id.'.file-'.$i,$old);if($j['dns_changed']&&$p['old_draft']!==null)$this->store->write($id.'.draft',json_encode($p['old_draft'],JSON_THROW_ON_ERROR),65536);
            $j['backup_binding_version']=1;$j['backups']=[];$names=[$id.'.conf'];
            foreach($backups as $i=>$_)$names[]=$id.'.file-'.$i;
            if($j['dns_changed']&&$p['old_draft']!==null)$names[]=$id.'.draft';
            foreach($names as $name){$pin=null;if($this->store->read($name,str_ends_with($name,'.draft')?65536:262144,$pin)===null||$pin===null)throw new RuntimeException('invalid_state');$j['backups'][$name]=$pin;}
            $s['current']=$j;$this->store->save($s);$this->store->prune(!$snapshot);$this->checkpoint('journal');
        return [$s,$j,$newFiles];
    }
    /** Internal original custody only; no native/service/Apply/export action. */
    public function supplementPrepareOriginals(array $recipe,array $domains,array $binding):array
    {
        return $this->writer(function()use($recipe,$domains,$binding){
            $saved=$this->supplementPortablePreview($recipe,$domains,$binding,true);$p=$saved['local_plan'];
            if($p['files']!==[]||$p['draft']!==null)throw new RuntimeException('supplement_plan_incompatible');
            $this->store->prune(false);$preserve=[];
            foreach($saved['proposal']['resource_kit']['files']as $file){
                if(NfqwsResourcePaths::canonical($file['path'])!==$file['path']||isset($preserve[$file['path']]))throw new RuntimeException('invalid_state');
                $preserve[$file['path']]=$file;
            }
            $digest=hash('sha256',json_encode($saved['local_plan_binding'],JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR));
            $id=bin2hex(random_bytes(16));$s=null;$j=null;
            try{
                [$s,$j]=$this->prepareJournal($p,$id,$digest,$preserve,true);
                $this->originals($j);$this->checkpoint('supplement_originals');
                NfqwsStrategySupplement::recheck($this->resources,$this->raw($this->config),$saved['proposal']);
                $this->checkPlan($p);if($this->store->state()!==$s)throw new RuntimeException('source_changed');$this->published($j);if(!$this->matches($j,false))throw new RuntimeException('source_changed');
                return ['mode'=>'supplement-prepared-originals-v1','journal_id'=>$id,
                    'local_plan_binding'=>$saved['local_plan_binding'],'originals_binding_sha256'=>$digest,
                    'referenced_original_files'=>count($preserve),'journal_prepared'=>true,
                    'backup_ready'=>false,'can_apply'=>false,'can_export'=>false,'combined_verified'=>false,'actual_device_calls'=>false];
            }catch(Throwable $e){
                // Never recover or overwrite an unknown journal here. A prepared
                // own journal remains durable and blocks input pending attention.
                $actual=$this->store->state();
                if($s!==null&&$actual===$s&&($actual['current']['id']??null)===$id&&($actual['current']['state']??null)==='prepared'){
                    $actual['current']['state']='restore_required';$this->store->save($actual);
                }
                throw $e;
            }
        });
    }
    public function apply(array $p,string $id,?string $requestDigest=null): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');$requestDigest??=$p['digest'];
        return $this->writer(function()use($p,$id,$requestDigest){$this->reconcile();$this->store->prune();$receipt=$this->receipt($id,$requestDigest);if($receipt!==null)return $receipt;[$s,$j,$newFiles]=$this->prepareJournal($p,$id,$requestDigest);
            try{$this->originals($j);$this->directories($j);$i=0;foreach($newFiles as $f){$this->putFile($j,$i,base64_decode($f['data_base64'],true),$j['files'][$i]['before'],$j['files'][$i]['metadata']['mode']??($f['kind']==='lists'?0666:0644));$this->checkpoint('file_'.$i);$i++;}
                $this->published($j);if($j['dns_changed'])$this->dns->replaceDraft($p['draft'],$j['draft_before']);$this->checkpoint('draft');
                $s['current']=$j;$s['current']['state']='committing';$this->store->save($s);$this->checkpoint('committing');
                $this->originals($j);$this->published($j);if($j['config_changed'])$this->atomicConfig($p['config'],$j['before'],$j,fn()=>$this->published($j));$this->checkpoint('config');
                $this->published($j);
                $this->originals($j);$s['current']['state']='committed';$this->store->save($s);$this->checkpoint('committed');return $this->publicJob($s['current']);
            }catch(Throwable $e){try{$this->reconcile();}catch(Throwable $recovery){throw $recovery;}throw $e;}
        });
    }
    public function undo(string $id): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');
        return $this->writer(function()use($id){$this->reconcile();$s=$this->store->state();$j=$s['current'];if($j===null||$j['id']!==$id)throw new RuntimeException('stale_state');if($j['state']==='undone')return $this->publicJob($j);
            if($j['state']!=='committed'||!$this->matches($j,true))throw new RuntimeException('source_changed');$s['current']['state']='undoing';$this->store->save($s);$this->checkpoint('undoing');
            try{$this->restore($s,'undone');}catch(Throwable $e){$s['current']['state']='restore_required';$this->store->save($s);throw $e;}return $this->publicJob($s['current']);});
    }
}
