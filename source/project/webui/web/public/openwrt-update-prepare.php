<?php
require_once __DIR__.'/openwrt-update-manifest.php';
require_once __DIR__.'/openwrt-update-manager.php';
require_once __DIR__.'/openwrt-update-snapshot.php';
require_once __DIR__.'/openwrt-apk-trust.php';

/** Native preparation is read-only with respect to services and installed packages. */
final class NfqwsOpenWrtUpdatePrepare implements NfqwsUpdatePreparation
{
    public function __construct(private AsusUpdateStore $store,private ?AsusUpdateSource $source=null,private array $options=[],private ?string $publicKey=null,private ?AsusUpdateDeadline $deadline=null){}
    public function environment():array
    {
        $e=isset($this->options['platform'])?$this->options:NfqwsOpenWrtUpdateEnvironment::collect();
        return $e+['owner'=>0,'overlay_free'=>disk_free_space(is_dir('/overlay')?'/overlay':'/'),
            'ram_free'=>disk_free_space($this->store->path()),'runtime_bytes'=>16777216,'root'=>'/'];
    }
    private function source():AsusUpdateSource
    {return $this->source??new AsusGithubUpdateSource(0,'/etc/ssl/certs/ca-certificates.crt',['metadata'=>15,'download'=>180],'openwrt');}
    public function key():string
    {
        if($this->publicKey!==null)return $this->publicKey;$p=($this->options['resources']??'/usr/share/nfqws2').'/update-release-key.pem';
        AsusUpdateStore::noLinks($p);$s=@lstat($p);if(!$s||!is_file($p)||$s['uid']!==0||($s['mode']&0022)!==0||$s['size']>8192)throw new RuntimeException('signature_unavailable');
        return (string)file_get_contents($p);
    }
    private function verify(string $raw,string $signature):array
    {
        $schema=isset($this->options['resources'])?$this->options['resources'].'/openwrt-package-manifest.schema.json':null;
        return NfqwsOpenWrtPackageManifest::verify($raw,$signature,$this->key(),$schema);
    }
    public function check(bool $force=false):array
    {
        $lease=$this->store->lease('check.lock');$raw=null;$env=null;
        try{
            try{$env=$this->environment();if(!$force&&($cached=$this->cached())!==null)return $cached;
                $this->deadline?->begin(15);try{$raw=$this->source()->manifest();}finally{$this->deadline?->end();}
                $m=$this->verify($raw['json'],$raw['signature']);$candidate=NfqwsOpenWrtPackageManifest::candidate($m,$env,$env['installed'],$env['build']);
                $result=['state'=>$candidate===null?'current':'available','code'=>null,'candidate'=>$candidate,'installed_version'=>$env['installed']];
            }catch(Throwable $e){$result=['state'=>'failed','code'=>AsusUpdatePrepare::code($e),'candidate'=>null,'installed_version'=>$env['installed']??null];}
            $this->store->withRetryLock(function()use($raw,$result,$env){
                if(in_array($result['state'],['available','current'],true)){$this->store->writeFile('manifest.json',$raw['json']);$this->store->writeFile('manifest.sig',$raw['signature']);}
                $this->store->writeFile('check.json',json_encode(['boot_id'=>AsusUpdateStore::boot(),'uptime'=>AsusUpdateStore::uptime(),'installed'=>$env['installed']??null,'result'=>$result],JSON_THROW_ON_ERROR));
            });return $result;
        }finally{flock($lease,LOCK_UN);fclose($lease);}
    }
    public function cached():?array
    {
        return $this->store->withLock(function(){
            $env=$this->environment();$raw=$this->store->readFile('check.json');if($raw===null)return null;$c=json_decode($raw,true,32,JSON_THROW_ON_ERROR);$now=AsusUpdateStore::uptime();
            if(($c['boot_id']??null)!==AsusUpdateStore::boot()||($c['installed']??null)!==$env['installed']||$now<($c['uptime']??INF)||$now-$c['uptime']>=300)return null;
            return $c['result'];
        });
    }
    public function reserveCached(string $revision,string $requestId):array
    {
        return $this->store->withLock(function()use($revision,$requestId){
            $state=$this->store->status();foreach(array_merge($state['active']?[$state['active']]:[],$state['history'])as $job)if($job['request_id']===$requestId){if($job['revision']!==$revision)throw new RuntimeException('request_conflict');return $job;}
            $checked=$this->cached();if(($checked['state']??null)!=='available'||$checked['candidate']['revision']!==$revision)throw new RuntimeException('stale_revision');
            if(($state['active']['state']??null)==='prepared'&&$state['active']['revision']!==$revision)$this->store->update($state['active']['id'],['state'=>'interrupted','code'=>'stale_revision']);
            $job=$this->store->reserve($revision,$requestId,$checked['candidate']);foreach(['manifest.json','manifest.sig']as $file)$this->store->writeFile('operations/'.$job['id'].'/'.$file,$this->store->readFile($file)??'');return $job;
        });
    }
    public function candidate(string $id,bool $fresh=false):array
    {
        $base='operations/'.$id;$env=$this->environment();$m=$this->verify($this->store->readFile($base.'/manifest.json')??'',$this->store->readFile($base.'/manifest.sig')??'');
        $candidate=NfqwsOpenWrtPackageManifest::candidate($m,$env,$env['installed'],$env['build']);$saved=json_decode($this->store->readFile($base.'/candidate.json')??'',true,32,JSON_THROW_ON_ERROR);
        if($candidate===null||$candidate!==$saved||$candidate['revision']!==$this->store->readOperation($id)['revision'])throw new RuntimeException('stale_revision');
        if($fresh){$check=$this->check(true);if($check['state']!=='available'||$check['candidate']!==$candidate)throw new RuntimeException('stale_revision');}
        return $candidate;
    }
    public function archive(string $id,array $candidate):string{return $this->store->path('operations/'.$id.'/package.'.$candidate['package']['format']);}
    public function inspect(string $id,array $candidate,string $keyName):array
    {
        $env=$this->environment();$keys=null;if($env['format']==='apk'){$keys=$this->store->path('operations/'.$id.'/'.$keyName);NfqwsOpenWrtApkTrust::stage($keys,$this->key());}
        $record=NfqwsOpenWrtUpdatePackage::inspect($this->archive($id,$candidate),$candidate,$env,$keys,$env['owner']);
        $db=NfqwsOpenWrtUpdateManager::installed($env);$args=NfqwsOpenWrtUpdateManager::argv($this->archive($id,$candidate),$env,$db,$record,$keys,true);
        $plan=NfqwsPlatform::run($args,30);if($plan['status']!==0)throw new RuntimeException('dependency_change');NfqwsOpenWrtUpdateManager::plan(implode("\n",$plan['output']),$env['format'],$record);
        return ['record'=>$record,'installed'=>$db,'keys'=>$keys];
    }
    public function completePrepare(string $id,?callable $stage=null):array
    {
        return $this->store->withOperationLock($id,function()use($id,$stage){
            $job=$this->store->readOperation($id);if($job['state']!=='preparing')return $job;
            try{
                $candidate=$this->candidate($id,true);$env=$this->environment();$base='operations/'.$id;$snapshot=NfqwsOpenWrtUpdateSnapshot::estimate($env['root'],$env['owner']);
                NfqwsOpenWrtUpdatePackage::space($env['overlay_free'],$env['ram_free'],$candidate['package'],$snapshot,$env['runtime_bytes']);
                $this->deadline?->begin(180);try{$this->source()->download($candidate['package'],$this->archive($id,$candidate));}finally{$this->deadline?->end();}
                $preflight=$this->inspect($id,$candidate,'apk-keys-prepare');$this->store->writeFile($base.'/native-preflight.json',json_encode($preflight,JSON_THROW_ON_ERROR));
                $patch=['state'=>'prepared','prepared_uptime'=>AsusUpdateStore::uptime(),'code'=>null];
                if($stage!==null){$r=$stage($id,$env);if(!is_array($r)||!preg_match('/^[a-f0-9]{64}$/D',$r['digest']??''))throw new RuntimeException('invalid_state');$patch['runtime_digest']=$r['digest'];}
                return $this->store->update($id,$patch);
            }catch(Throwable $e){return $this->store->update($id,['state'=>'failed','code'=>AsusUpdatePrepare::code($e)]);}
        });
    }
}
