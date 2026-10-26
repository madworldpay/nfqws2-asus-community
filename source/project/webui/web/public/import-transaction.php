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
    private function checkpoint(string $phase): void {if(isset($this->deps['checkpoint']))($this->deps['checkpoint'])($phase);}
    private function path(string $logical): string
    {if(!preg_match('~^/opt/etc/nfqws2/(lists|lua|blobs)/[A-Za-z0-9_.-]{1,128}$~D',$logical))throw new RuntimeException('invalid_state');return $this->root.substr($logical,strlen('/opt/etc/nfqws2'));}
    private function raw(string $path): ?string
    {if(!$this->reader->directory(dirname($path)))throw new RuntimeException('source_changed');clearstatcache(true,$path);if(@lstat($path)===false)return null;return $this->reader->bytes($path,262144);}
    private function hash(string $path): ?string {$v=$this->raw($path);return $v===null?null:hash('sha256',$v);}
    private function draftHash(): ?string {$d=$this->dns->draft();return $d===null?null:AsusSmartDnsProfile::hash($d);}
    public function prepare(array $documents,array $selection): array
    {
        $doc=AsusImportDocument::read($documents);$raw=$this->raw($this->config);if($raw===null)throw new RuntimeException('strategy_unavailable');
        return AsusImportPlan::prepare($doc,$selection,$raw,$this->resources->inventory(),$this->dns->draft());
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
    private function atomicConfig(string $raw,string $expected,array $j): void
    {
        if($this->hash($this->config)!==$expected)throw new RuntimeException('source_changed');$s=$this->reader->stat($this->config);$temp=$this->tempPath($j,'config');$this->writeNew($temp,$raw,0600);$this->checkpoint('config_stage');
        try{if($this->hash($this->config)!==$expected)throw new RuntimeException('source_changed');
            if($s['uid']!==$this->owner&&!@chown($temp,$s['uid']))throw new RuntimeException('storage_unavailable');
            if(!@chgrp($temp,$s['gid'])||!@chmod($temp,$s['mode']&0777)||!@rename($temp,$this->config))throw new RuntimeException('storage_unavailable');
        }finally{if(@lstat($temp)!==false)@unlink($temp);}
    }
    private function writeNew(string $path,string $raw,int $mode=0644): void
    {
        if(!$this->reader->directory(dirname($path)))throw new RuntimeException('source_changed');$mask=umask(0077);try{$f=@fopen($path,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('source_changed');
        try{if(@fwrite($f,$raw)!==strlen($raw)||!@fflush($f)||(function_exists('fsync')&&!@fsync($f))||!@chmod($path,$mode))throw new RuntimeException('insufficient_space');}
        catch(Throwable $e){@unlink($path);throw $e;}finally{fclose($f);}
    }
    private function stage(array $j,int $i): string
    {return dirname($this->path($j['files'][$i]['path'])).'/.import-'.$j['id'].'-'.$i;}
    /** Replace only the exact reviewed file; new files retain no-clobber linking. */
    private function putFile(array $j,int $i,string $raw,?string $expected,int $mode): void
    {
        $f=$j['files'][$i];$path=$this->path($f['path']);$tmp=$this->stage($j,$i);
        if($this->hash($path)!==$expected)throw new RuntimeException('source_changed');
        $this->writeNew($tmp,$raw,$mode);
        if(isset($f['metadata'])){$m=$f['metadata'];if(($m['uid']!==$this->owner&&!@chown($tmp,$m['uid']))||!@chgrp($tmp,$m['gid'])||!@chmod($tmp,$m['mode']))throw new RuntimeException('storage_unavailable');}
        $this->checkpoint('stage_'.$i);
        if($this->hash($path)!==$expected)throw new RuntimeException('source_changed');
        if($expected===null){if(!@link($tmp,$path))throw new RuntimeException('source_changed');$this->checkpoint('linked_'.$i);if(!@unlink($tmp))throw new RuntimeException('storage_unavailable');}
        else {if(!@rename($tmp,$path))throw new RuntimeException('storage_unavailable');$this->checkpoint('linked_'.$i);}
    }
    private function cleanupStages(array $j): void
    {
        foreach($j['files']as $i=>$f){$tmp=$this->stage($j,$i);clearstatcache(true,$tmp);$s=@lstat($tmp);if(!$s)continue;
            $target=$this->path($f['path']);clearstatcache(true,$target);$t=@lstat($target);
            // A crash can leave both hardlink names; drop only our verified stage.
            if(($s['mode']&0170000)!==0100000||!in_array($s['uid'],[$this->owner,$f['metadata']['uid']??$this->owner],true)||!in_array($s['mode']&0777,[0600,0644,0666,$f['metadata']['mode']??0644],true)||!in_array($s['nlink'],[1,2],true)||($s['nlink']===2&&(!$t||$s['ino']!==$t['ino']||$s['dev']!==$t['dev']))||$s['size']>262144||!$this->reader->directory(dirname($tmp)))throw new RuntimeException('restore_required');
            if(!@unlink($tmp))throw new RuntimeException('storage_unavailable');
        }
        $tmp=$this->tempPath($j,'config');clearstatcache(true,$tmp);$s=@lstat($tmp);if($s){if(($s['mode']&0170000)!==0100000||$s['nlink']!==1||!in_array($s['uid'],[$this->owner,65534],true)||!$this->reader->directory(dirname($tmp)))throw new RuntimeException('restore_required');if(!@unlink($tmp))throw new RuntimeException('storage_unavailable');}
    }
    private function matches(array $j,bool $after,bool $partial=false): bool
    {
        $cfg=$this->hash($this->config);if($cfg!==$j[$after?'after':'before']&&(!$partial||!in_array($cfg,[$j['before'],$j['after']],true)))return false;
        if($j['dns_changed']){$d=$this->draftHash();if($d!==$j[$after?'draft_after':'draft_before']&&(!$partial||!in_array($d,[$j['draft_before'],$j['draft_after']],true)))return false;}
        foreach($j['files']as $f){$path=$this->path($f['path']);$h=$this->hash($path);$before=$f['before']??null;if($h!==($after?$f['sha256']:$before)&&(!$partial||!in_array($h,[$before,$f['sha256']],true)))return false;
            if(isset($f['before'],$f['metadata'])&&$h!==null){$stat=$this->reader->stat($path);$m=$f['metadata'];if(!$stat||$stat['uid']!==$m['uid']||$stat['gid']!==$m['gid']||($stat['mode']&0777)!==$m['mode'])return false;}
        }return true;
    }
    private function restore(array &$s,string $state): void
    {
        $j=$s['current'];$this->cleanupStages($j);
        if(!$this->matches($j,false,true))throw new RuntimeException('restore_required');
        if($this->hash($this->config)!==$j['before']){$raw=$this->store->read($j['id'].'.conf');if($raw===null||hash('sha256',$raw)!==$j['before'])throw new RuntimeException('invalid_state');$this->atomicConfig($raw,$j['after'],$j);}
        $this->checkpoint('undo_config');
        if($j['dns_changed']&&$this->draftHash()!==$j['draft_before']){$raw=$this->store->read($j['id'].'.draft',65536);$d=$raw===null?null:json_decode($raw,true,32,JSON_THROW_ON_ERROR);$this->dns->replaceDraft($d,$j['draft_after']);}
        $this->checkpoint('undo_draft');
        foreach($j['files']as $i=>$f){$path=$this->path($f['path']);$actual=$this->hash($path);$before=$f['before']??null;
            if($actual!==$before){if($actual!==$f['sha256'])throw new RuntimeException('restore_required');
                if($before===null){if(!@unlink($path))throw new RuntimeException('storage_unavailable');}
                else {$raw=$this->store->read($j['id'].'.file-'.$i);if($raw===null||hash('sha256',$raw)!==$before)throw new RuntimeException('invalid_state');$this->putFile($j,$i,$raw,$f['sha256'],$f['metadata']['mode']);}
            }$this->checkpoint('undo_file_'.$i);
        }
        $s['current']['state']=$state;$this->store->save($s);
    }
    private function reconcile(): void
    {
        $s=$this->store->state();$j=$s['current'];if($j===null||in_array($j['state'],['committed','undone','rolled_back'],true))return;
        if($j['state']==='restore_required')throw new RuntimeException('restore_required');
        try{$this->cleanupStages($j);
            if($j['state']!=='undoing'&&$j['state']==='committing'&&$this->matches($j,true)){$s['current']['state']='committed';$this->store->save($s);return;}
            $this->restore($s,$j['state']==='undoing'?'undone':'rolled_back');
        }catch(Throwable $e){$s['current']['state']='restore_required';$this->store->save($s);throw new RuntimeException('restore_required');}
    }
    public function recover(): array {return $this->writer(function(){$this->reconcile();$this->store->prune();return $this->status();});}
    public function apply(array $p,string $id,?string $requestDigest=null): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');$requestDigest??=$p['digest'];
        return $this->writer(function()use($p,$id,$requestDigest){$this->reconcile();$this->store->prune();$receipt=$this->receipt($id,$requestDigest);if($receipt!==null)return $receipt;$this->checkPlan($p);$s=$this->store->state();
            if($s['current']!==null){array_unshift($s['history'],$s['current']);$s['history']=array_slice($s['history'],0,3);}
            $raw=$this->raw($this->config);$newFiles=[];foreach($p['files']as $f)if(!$f['reuse'])$newFiles[$f['path']]=$f;$files=[];$backups=[];$backupBytes=0;
            foreach($newFiles as $f){$path=$this->path($f['path']);$old=$this->raw($path);$before=$old===null?null:hash('sha256',$old);if($before!==$p['fingerprints']['files'][$f['path']])throw new RuntimeException('source_changed');$row=['path'=>$f['path'],'sha256'=>$f['sha256'],'before'=>$before];
                if($old!==null){$metadata=$this->reader->stat($path);if(!$metadata)throw new RuntimeException('source_changed');$row['metadata']=['uid'=>$metadata['uid'],'gid'=>$metadata['gid'],'mode'=>$metadata['mode']&0777];$backups[count($files)]=$old;$backupBytes+=strlen($old);if($backupBytes>524288)throw new RuntimeException('output_limit');}$files[]=$row;
            }
            $j=['id'=>$id,'state'=>'prepared','request_digest'=>$requestDigest,'before'=>hash('sha256',$raw),'after'=>hash('sha256',$p['config']),'config_changed'=>$raw!==$p['config'],'dns_changed'=>$p['draft']!==null,'draft_before'=>$p['fingerprints']['draft'],'draft_after'=>$p['draft']===null?$p['fingerprints']['draft']:AsusSmartDnsProfile::hash($p['draft']),'files'=>$files];
            $this->store->write($id.'.conf',$raw);foreach($backups as $i=>$old)$this->store->write($id.'.file-'.$i,$old);if($j['dns_changed']&&$p['old_draft']!==null)$this->store->write($id.'.draft',json_encode($p['old_draft'],JSON_THROW_ON_ERROR),65536);
            $s['current']=$j;$this->store->save($s);$this->store->prune();$this->checkpoint('journal');
            try{$i=0;foreach($newFiles as $f){$this->putFile($j,$i,base64_decode($f['data_base64'],true),$j['files'][$i]['before'],$j['files'][$i]['metadata']['mode']??($f['kind']==='lists'?0666:0644));$this->checkpoint('file_'.$i);$i++;}
                if($j['dns_changed'])$this->dns->replaceDraft($p['draft'],$j['draft_before']);$this->checkpoint('draft');
                $s['current']['state']='committing';$this->store->save($s);$this->checkpoint('committing');
                if($j['config_changed'])$this->atomicConfig($p['config'],$j['before'],$j);$this->checkpoint('config');
                $s['current']['state']='committed';$this->store->save($s);$this->checkpoint('committed');return $this->publicJob($s['current']);
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
