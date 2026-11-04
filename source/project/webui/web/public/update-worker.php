<?php
require_once __DIR__.'/update-prepare.php';
require_once __DIR__.'/update-runtime.php';
require_once __DIR__.'/update-guard.php';
require_once __DIR__.'/update-rollback.php';
require_once __DIR__.'/update-smartdns-resume.php';
require_once __DIR__.'/smartdns-lifecycle.php';

/** Root-only staged implementation. There is no HTTP entry or command input. */
final class AsusUpdateWorker
{
    private AsusUpdatePrepare $prepare;
    private AsusUpdateLifecycle $lifecycle;
    public function __construct(private AsusUpdateStore $store,?AsusUpdatePrepare $prepare=null,?AsusUpdateLifecycle $lifecycle=null,private array $options=[])
    {$this->prepare=$prepare??new AsusUpdatePrepare($store);$this->lifecycle=$lifecycle??new AsusUpdateLifecycle();}
    private function owner(): int {return $this->options['owner']??0;}
    private function dnsJobs(): AsusSmartDnsConfigJobs
    {return new AsusSmartDnsConfigJobs($this->options['dns_store']??new AsusSmartDnsStore(),$this->options['dns_backend']??null);}
    private function assertDnsUpdateReady(): void
    {
        // The exclusive updater lease is already held. Dead processes alone
        // cannot release an unresolved native DNS transaction.
        $jobs=$this->dnsJobs();$jobs->reconcile();
        if ($jobs->blocksUpdate()) throw new RuntimeException('dns_restore_required');
    }
    private function guard(): AsusUpdateGuard {return new AsusUpdateGuard($this->store,$this->owner(),$this->options['opkg']??'/opt/bin/opkg');}
    private function writeTicket(array $ticket): void
    {$this->store->writeFile('transaction.json',json_encode($ticket,JSON_THROW_ON_ERROR));}
    private function guardianChild(mixed $child,array $worker):bool
    {
        if(!is_array($child)||count($child)!==5||array_diff(array_keys($child),['pid','start_ticks','boot_id','exe','uid'])!==[])return false;
        if(!is_string($child['exe'])||!str_starts_with($child['exe'],'/')||strlen($child['exe'])>=4096||strpbrk($child['exe'],"\r\n\0")!==false)return false;
        // context() already proves the live staged PHP/loader and ancestry.
        // The guardian may have sampled this same child before its exec.
        foreach(['pid','start_ticks','boot_id','uid'] as $key)if($child[$key]!==$worker[$key])return false;
        return true;
    }
    private function settings(string $id):string{return $this->store->path('operations/'.$id.'/quiesced-backup');}
    private function original(array $env,array $candidate,string $id):array
    {
        if(!$env['pending'])return ['kind'=>'installed']+AsusUpdateRollback::attest($env);
        if(($candidate['action']??null)!=='configure')throw new RuntimeException('recovery_required');
        AsusUpdatePackage::inspect($this->store->path('operations/'.$id.'/package.ipk'),$candidate,$env['status'],$env['abi'],$env['machine'],$env['opt'],$env['owner']);
        $db=AsusUpdatePackage::database($env['status'],true);ksort($db);foreach($db as &$row)ksort($row);unset($row);
        return ['kind'=>'configure','schema'=>1,'version'=>$env['installed'],'architecture'=>$db['nfqws2-asus']['Architecture'],
            'sha256'=>hash('sha256',json_encode([$db,$candidate['package']['sha256'],AsusUpdateSnapshot::stable($env['opt'],$env['owner'])],JSON_THROW_ON_ERROR))];
    }
    private function quiesce(string $id):?array
    {
        $raw=$this->store->readFile('operations/'.$id.'/quiesce.json');if($raw===null)return null;$v=json_decode($raw,true,24,JSON_THROW_ON_ERROR);
        if(!is_array($v)||array_keys($v)!==['schema','id','boot_id','worker','installer','attestation','checkpoint_sha256','intent','web_running','phase']||$v['schema']!==1||$v['id']!==$id||$v['boot_id']!==AsusUpdateStore::boot()||!is_array($v['worker'])||!is_array($v['installer'])||!is_array($v['attestation'])||!is_string($v['checkpoint_sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$v['checkpoint_sha256'])||!is_bool($v['web_running'])||!in_array($v['phase'],['stop-requested','stopped','captured','web-stopped','restoring','restored'],true))throw new RuntimeException('recovery_required');
        $directory=$this->store->path('operations/'.$id.'/service-state');$checkpoint=$this->lifecycle->checkpointState($directory);
        if($checkpoint['intent']!==$v['intent']||!hash_equals($v['checkpoint_sha256'],hash_file('sha256',$directory.'/snapshot.json')))throw new RuntimeException('recovery_required');return $v;
    }
    private function quiescePhase(string $id,array $v,string $phase):array
    {$v['phase']=$phase;$this->store->writeFile('operations/'.$id.'/quiesce.json',json_encode($v,JSON_THROW_ON_ERROR));return $v;}
    private function restoreQuiesced(string $id,array $ticket):void
    {
        if($this->store->readFile('operations/'.$id.'/boundary.json',1024)!==null||$this->store->readFile('operations/'.$id.'/rollback-finalized.json',1024)!==null)throw new RuntimeException('recovery_required');
        $v=$this->quiesce($id);if($v===null)throw new RuntimeException('recovery_required');$this->runtime($id);
        $env=$this->prepare->environment();$candidate=json_decode($this->store->readFile('operations/'.$id.'/candidate.json')??'',true,32,JSON_THROW_ON_ERROR);
        if($this->original($env,$candidate,$id)!==$v['attestation'])throw new RuntimeException('recovery_required');
        $installer=$this->installer($id);$this->ticket($id,'stopping',['installer'=>$installer,'intent'=>$v['intent']]);
        $this->lifecycle->stop(true);if($this->lifecycle->intent()['mode']!=='stopped')throw new RuntimeException('core_stop_failed');
        $verified=is_file($this->settings($id).'/snapshot.json')&&AsusUpdateSnapshot::verify($env['opt'],$this->settings($id),$this->owner());
        $this->quiescePhase($id,$v,'restoring');$this->ticket($id,'starting');
        $core=$this->lifecycle->restoreCheckpoint($this->store->path('operations/'.$id.'/service-state'));
        if($v['web_running']){$this->lifecycle->web();if(!$this->webHealth())throw new RuntimeException('web_health_failed');}
        $this->store->writeFile('operations/'.$id.'/quiesce-result.json',json_encode(['core_state'=>$core,'version'=>$env['installed'],'restored'=>true,'settings_verified'=>$verified],JSON_THROW_ON_ERROR));$this->quiescePhase($id,$v,'restored');
    }
    private function ticket(string $id,string $phase,array $patch=[]): array
    {return $this->store->withLock(function()use($id,$phase,$patch){$t=$this->guard()->context($id);$t=array_replace($t,$patch,['phase'=>$phase]);$this->writeTicket($t);return $t;});}
    private function validate(string $id,bool $fresh): array
    {
        $job=$this->store->readOperation($id);if($job['state']!=='applying'||$job['boot_id']!==AsusUpdateStore::boot())throw new RuntimeException('interrupted');
        $base='operations/'.$id;$runtime=$this->store->path($base.'/runtime');$closure=AsusUpdateRuntime::load($runtime,$this->owner());
        if(!is_string($job['runtime_digest']??null)||!hash_equals($job['runtime_digest'],$closure['digest']))throw new RuntimeException('runtime_changed');
        $env=$this->prepare->environment();$manifest=AsusPackageManifest::verify($this->store->readFile($base.'/manifest.json')??'',
            $this->store->readFile($base.'/manifest.sig')??'',file_get_contents($runtime.'/resources/update-release-key.pem'));
        $candidate=AsusPackageManifest::candidate($manifest,$env['family'],$env['installed'],$env['pending']);
        $saved=json_decode($this->store->readFile($base.'/candidate.json')??'',true,32,JSON_THROW_ON_ERROR);
        if($candidate===null||$candidate!==$saved||$candidate['revision']!==$job['revision'])throw new RuntimeException('stale_revision');
        if($fresh){$check=$this->prepare->check(true);if($check['state']!=='available'||$check['candidate']!==$candidate)throw new RuntimeException('stale_revision');}
        AsusUpdatePackage::inspect($this->store->path($base.'/package.ipk'),$candidate,$env['status'],$env['abi'],$env['machine'],$env['opt'],$env['owner']);
        AsusUpdateSnapshot::estimate($env['opt'],$this->owner());
        AsusUpdatePackage::space($env['free'],0,0,0);return [$env,$candidate];
    }
    private function runtime(string $id):array
    {
        $job=$this->store->readOperation($id);$runtime=AsusUpdateRuntime::load($this->store->path('operations/'.$id.'/runtime'),$this->owner());
        if(!is_string($job['runtime_digest']??null)||!hash_equals($job['runtime_digest'],$runtime['digest']))throw new RuntimeException('runtime_changed');return $runtime;
    }
    private function installer(string $id):array
    {
        $status=@file_get_contents('/proc/self/status');if(!is_string($status)||!preg_match('/^PPid:\s+([0-9]+)/m',$status,$m))throw new RuntimeException('invalid_state');
        $installer=AsusUpdateLifecycle::identity((int)$m[1]);$expected=$this->store->path('operations/'.$id.'/runtime/update-launch');
        if($installer===null||$installer['exe']!==$expected||$installer['uid']!==$this->owner())throw new RuntimeException('invalid_state');return $installer;
    }
    private function rollbackEnvironment(string $id):array
    {$env=$this->prepare->rollbackEnvironment();$env['candidate_version']=$this->store->readOperation($id)['package_version'];return $env;}
    private function rollbackPreflight(string $id,string $action,array $t):void
    {
        $this->runtime($id);if(!in_array($t['phase'],['stopping','installing','starting'],true)||$this->store->readFile('operations/'.$id.'/boundary.json',1024)===null)throw new RuntimeException('rollback_failed');
        $env=$this->rollbackEnvironment($id);$directory=$this->store->path('operations/'.$id.'/rollback');$settings=$this->settings($id);
        $m=AsusUpdateRollback::load($directory,$this->owner());AsusUpdateRollback::assertForeign($env,$m);$installer=$this->installer($id);
        if($action==='rollback-verify'){
            if($this->store->readFile('operations/'.$id.'/rollback-finalized.json',1024)===null)throw new RuntimeException('rollback_failed');
            $verified=AsusUpdateRollback::verifyInstalled($env,$directory,$settings);$this->quiesceDns($id,'after');
            $this->ticket($id,'starting',['installer'=>$installer]);$q=$this->quiesce($id);if($q===null||$q['web_running']){$this->lifecycle->web();if(!$this->webHealth())throw new RuntimeException('web_health_failed');}
            // A completed stop and a fresh start are required. Never accept the
            // old daemon's already-running shortcut after detached firewall.
            if($this->lifecycle->intent()['mode']!=='stopped')throw new RuntimeException('rollback_failed');
            $core=$q===null?$this->lifecycle->restore($t['intent']):$this->lifecycle->restoreCheckpoint($this->store->path('operations/'.$id.'/service-state'));$this->store->writeFile('operations/'.$id.'/rollback-result.json',json_encode(['version'=>$verified['version'],'core_state'=>$core,'settings_verified'=>true],JSON_THROW_ON_ERROR));return;
        }
        $this->ticket($id,'stopping',['installer'=>$installer]);$this->store->update($id,['phase'=>'stopping']);
        if($this->store->readFile('operations/'.$id.'/services-stopped.json',1024)===null)throw new RuntimeException('rollback_failed');
        $this->lifecycle->stop();if($this->lifecycle->intent()['mode']!=='stopped')throw new RuntimeException('rollback_failed');
        $this->ticket($id,'installing');if($this->store->readFile('operations/'.$id.'/web-started.json',1024)!==null)$this->lifecycle->webStop();$this->store->update($id,['phase'=>'installing']);
    }
    /** Fixed snapshot postinst, under the real opkg process and its POSIX mutex. */
    public function rollbackFinalize(string $id):void
    {
        $stage='runtime';
        try{
            $this->runtime($id);$stage='context';$t=$this->guard()->context($id);$stage='authorization';
            if($t['phase']!=='installing'||!$this->guard()->authorize('hook-postinst'))throw new RuntimeException('rollback_failed');
            $stage='environment';$env=$this->rollbackEnvironment($id);
            $stage='restore';AsusUpdateRollback::finalize($env,$this->store->path('operations/'.$id.'/rollback'),$this->settings($id));
            $stage='receipt';$this->store->writeFile('operations/'.$id.'/rollback-finalized.json',json_encode(['restored'=>true],JSON_THROW_ON_ERROR));
        }catch(Throwable $e){
            try{$this->store->writeFile('operations/'.$id.'/rollback-finalize-error.json',json_encode(['schema'=>1,'stage'=>$stage,'code'=>AsusUpdatePrepare::code($e),'guard'=>$this->guard()->diagnostic($id)],JSON_THROW_ON_ERROR));}catch(Throwable $ignored){}
            throw $e;
        }
    }
    /** Native launcher owns the opkg POSIX mutex throughout this child check. */
    public function preflight(string $id,string $action='install'): void
    {
        $f=$this->store->lease('operations/'.$id.'/critical.lock');
        try{
            $t=$this->guard()->context($id);if($action==='rollback-verify'&&$this->store->readFile('operations/'.$id.'/boundary.json',1024)===null){$this->restoreQuiesced($id,$t);return;}
            if(in_array($action,['rollback','rollback-verify'],true)){$this->rollbackPreflight($id,$action,$t);return;}
            if($t['phase']!=='validating'||$t['installer']!==null)throw new RuntimeException('invalid_state');
            if($this->store->readFile('operations/'.$id.'/cancel.json',1024)!==null)throw new RuntimeException('timed_out');
            $raw=$this->store->readFile('operations/'.$id.'/guard.json',4096);$guard=$raw===null?null:json_decode($raw,true,16,JSON_THROW_ON_ERROR);
            if(!is_array($guard)||!$this->guardianChild($guard['child']??null,$t['worker'])||!is_numeric($guard['deadline']??null)||AsusUpdateStore::uptime()>=$guard['deadline'])throw new RuntimeException('timed_out');
            [$env,$candidate]=$this->validate($id,false);
            if(!in_array($action,['install','configure'],true)||$action!==($candidate['action']??'install'))throw new RuntimeException('invalid_state');
            $installer=$this->installer($id);
            $checkpoint=$this->lifecycle->checkpoint($this->store->path('operations/'.$id.'/service-state'));
            $q=['schema'=>1,'id'=>$id,'boot_id'=>AsusUpdateStore::boot(),'worker'=>$t['worker'],'installer'=>$installer,'attestation'=>$this->original($env,$candidate,$id),
                'checkpoint_sha256'=>hash_file('sha256',$this->store->path('operations/'.$id.'/service-state/snapshot.json')),'intent'=>$checkpoint['intent'],'web_running'=>$this->lifecycle->webRunning(),'phase'=>'stop-requested'];
            $this->store->writeFile('operations/'.$id.'/quiesce.json',json_encode($q,JSON_THROW_ON_ERROR));
            $this->ticket($id,'stopping',['installer'=>$installer,'intent'=>$checkpoint['intent']]);$this->store->update($id,['intent'=>$checkpoint['intent'],'phase'=>'stopping']);
            $this->quiesceDns($id,'before');$this->assertDnsUpdateReady();(new AsusSmartDnsLifecycle(new AsusSmartDnsStore()))->stop('upgrade');
            $this->lifecycle->stop(true);if($this->lifecycle->intent()['mode']!=='stopped')throw new RuntimeException('core_stop_failed');$q=$this->quiescePhase($id,$q,'stopped');
            if($this->original($this->prepare->environment(),$candidate,$id)!==$q['attestation'])throw new RuntimeException('settings_changed');
            $this->store->update($id,['phase'=>'backing_up']);
            AsusUpdateSnapshot::capture($env['opt'],$this->settings($id),$this->owner());
            if($action==='install'){
                $argv=array_merge($this->runtime($id)['argv'],['--','rollback-finalize',$id]);
                $postinst="#!/bin/sh\nexec ".implode(' ',array_map('escapeshellarg',$argv))."\n";
                $env['defaults']=AsusUpdatePackage::stockDefaults($this->store->path('operations/'.$id.'/package.ipk'),$env['opt'],$this->owner());
                AsusUpdateRollback::capture($env,$this->store->path('operations/'.$id.'/rollback'),$this->settings($id),$postinst);
            }
            $q=$this->quiescePhase($id,$q,'captured');
            // Published guards permit the installer's web-stop only in this
            // phase. The absent sticky boundary still forbids any opkg exec.
            $this->ticket($id,'installing');if($q['web_running'])$this->lifecycle->webStop();$this->quiescePhase($id,$q,'web-stopped');
            $this->store->writeFile('operations/'.$id.'/services-stopped.json',json_encode(['stopped'=>true],JSON_THROW_ON_ERROR));
            $this->ticket($id,'installing');$this->store->update($id,['phase'=>'installing']);
            if(AsusUpdateStore::uptime()>=$guard['deadline']||$this->store->readFile('operations/'.$id.'/cancel.json',1024)!==null)throw new RuntimeException('timed_out');
            // Sticky boundary is serialized with guardian cancellation. From
            // here neither the worker nor opkg may be killed by that deadline.
            $this->store->writeFile('operations/'.$id.'/boundary.json',json_encode(['phase'=>'installing'],JSON_THROW_ON_ERROR));
        }finally{flock($f,LOCK_UN);fclose($f);}
    }
    private function install(string $id,array $candidate): void
    {
        $action=$candidate['action']??'install';$argv=[$this->store->path('operations/'.$id.'/runtime/update-launch'),$id];if($action!=='install')$argv[]=$action;
        $log=$action==='rollback'?'rollback-opkg.log':($action==='rollback-verify'?'rollback-verify.log':'opkg.log');
        $this->store->writeFile('operations/'.$id.'/'.$log,'');
        $mask=umask(0077);try{$p=@proc_open($argv,
            [0=>['file','/dev/null','r'],1=>['file',$this->store->path('operations/'.$id.'/'.$log),'a'],2=>['file',$this->store->path('operations/'.$id.'/'.$log),'a']],$pipes,'/',
            ['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C','LC_ALL'=>'C']);}finally{umask($mask);}
        if(!is_resource($p))throw new RuntimeException('launch_failed');$exit=null;
        try{do{$status=proc_get_status($p);if(!$status['running']){$exit=$status['exitcode'];break;}usleep(25000);}while(true);}
        finally{$closed=proc_close($p);if($exit===null||$exit<0)$exit=$closed;}
        if($exit!==0){
            if(in_array($action,['rollback','rollback-verify'],true))throw new RuntimeException('rollback_failed');
            $raw=$this->store->readFile('operations/'.$id.'/preflight-error.json',1024);
            if($raw!==null){$value=json_decode($raw,true,4,JSON_THROW_ON_ERROR);throw new RuntimeException($value['code']??'install_failed');}
            if($exit===73&&$this->store->readFile('operations/'.$id.'/boundary.json',1024)===null)throw new RuntimeException('opkg_busy');
            throw new RuntimeException('install_failed');
        }
    }
    private function webHealth(): bool
    {
        if(isset($this->options['web_health']))return (bool)($this->options['web_health'])();
        $run=$this->options['web_run']??'/tmp/nfqws-asus-web';AsusUpdateStore::noLinks($run);$dir=@lstat($run);
        $path=$run.'/lighttpd.conf';AsusUpdateStore::noLinks($path);$file=@lstat($path);
        if(!$dir||($dir['mode']&0170000)!==0040000||$dir['uid']!==$this->owner()||($dir['mode']&0777)!==0700||!$file||($file['mode']&0170000)!==0100000||$file['uid']!==$this->owner()||$file['nlink']!==1||($file['mode']&0777)!==0600||$file['size']>16384)throw new RuntimeException('invalid_state');
        // The staged Entware PHP deliberately runs without optional extensions.
        // Validate a literal IPv4 bind without requiring php8-mod-filter.
        $octet='(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])';
        $config=@file_get_contents($path);if(!is_string($config)||preg_match_all('/^server\.bind\s*=\s*"([^"\r\n]+)"\s*$/m',$config,$matches)!==1||preg_match('~^'.$octet.'(?:\.'.$octet.'){3}$~D',$matches[1][0])!==1)throw new RuntimeException('invalid_state');
        $address=$matches[1][0];$port=$this->options['health_port']??90;if(!is_int($port)||$port<1||$port>65535)throw new RuntimeException('invalid_state');
        $end=AsusUpdateStore::uptime()+10;
        do{$errno=0;$error='';$socket=@stream_socket_client('tcp://'.$address.':'.$port,$errno,$error,1,STREAM_CLIENT_CONNECT);
            if(is_resource($socket)){stream_set_timeout($socket,1);fwrite($socket,"GET / HTTP/1.0\r\nHost: ".$address.':'.$port."\r\nConnection: close\r\n\r\n");$line=fgets($socket,1024);fclose($socket);if(is_string($line)&&preg_match('~^HTTP/1\.[01] 200 ~',$line))return true;}
            usleep(100000);
        }while(AsusUpdateStore::uptime()<$end);return false;
    }
    private function quiesceDns(string $id,string $phase):void
    {
        $result=(new AsusUpdateSmartDnsResume($this->options['dns_resume_options']??[]))->quiesce();
        $this->store->writeFile('operations/'.$id.'/dns-resume-quiesced-'.$phase.'.json',json_encode($result,JSON_THROW_ON_ERROR));
    }
    private function resumeDns(string $id):void
    {
        // This subprocess loads freshly installed code only after our updater
        // lease is released. A failed queue keeps the consent-bound intent.
        $result=['state'=>'skipped'];$process=null;
        try{
            $env=$this->prepare->rollbackEnvironment();$path=$env['opt'].'/lib/nfqws2-asus/smartdns/control.sh';AsusUpdateStore::noLinks($path);$s=@lstat($path);
            if($s){
                if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner()||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>16384)throw new RuntimeException('invalid_state');
                $process=@proc_open(['/bin/sh',$path,'queue-resume'],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C','LC_ALL'=>'C']);
                if(!is_resource($process))throw new RuntimeException('launch_failed');$end=AsusUpdateStore::uptime()+5;$exit=null;
                do{$status=proc_get_status($process);if(!$status['running']){$exit=$status['exitcode'];break;}if(AsusUpdateStore::uptime()>=$end){proc_terminate($process,15);usleep(100000);$status=proc_get_status($process);if($status['running'])proc_terminate($process,9);throw new RuntimeException('timed_out');}usleep(20000);}while(true);
                $closed=proc_close($process);$process=null;if($exit===null||$exit<0)$exit=$closed;if($exit!==0)throw new RuntimeException('launch_failed');$result=['state'=>'queued'];
            }
        }catch(Throwable $e){$result=['state'=>'failed','code'=>AsusUpdatePrepare::code($e)];}
        finally{if(is_resource($process))proc_close($process);}
        $this->store->writeFile('operations/'.$id.'/dns-resume.json',json_encode($result,JSON_THROW_ON_ERROR));
    }
    /** Fixed guardian callback: verifies/restores only; never applies a package. */
    public function recoverBeforeInstall(string $id):array
    {
        $apply=null;$work=null;$critical=null;$claimed=false;
        try{
            $job=$this->store->readOperation($id);
            if($job['state']!=='applying'||$this->store->readFile('operations/'.$id.'/boundary.json',1024)!==null||$this->store->readFile('operations/'.$id.'/quiesce.json')===null)return ['state'=>'skipped'];
            $this->runtime($id);$q=$this->quiesce($id);
            if($q===null||in_array($q['phase'],['restoring','restored'],true))throw new RuntimeException('recovery_required');
            $apply=$this->store->lease('apply.lock');$work=$this->store->lease('operations/'.$id.'/work.lock');
            // A killed apply child does not own its native installer's POSIX
            // mutex. Wait for that exact descendant to finish; never kill it.
            $until=AsusUpdateStore::uptime()+60;
            do{
                try{$critical=$this->store->lease('operations/'.$id.'/critical.lock');$this->guard()->recover($id,$q['worker'],$q['installer']);$claimed=true;break;}
                catch(RuntimeException $e){if($critical!==null){flock($critical,LOCK_UN);fclose($critical);$critical=null;}if($e->getMessage()!=='busy'||AsusUpdateStore::uptime()>=$until)throw $e;usleep(20000);}
            }while(true);
            flock($critical,LOCK_UN);fclose($critical);$critical=null;
            // Native rollback-verify is a no-opkg action. Its dedicated absent-
            // boundary branch reattests old payload/settings under the mutex.
            $this->install($id,['action'=>'rollback-verify']);
            $r=json_decode($this->store->readFile('operations/'.$id.'/quiesce-result.json',1024)??'',true,8,JSON_THROW_ON_ERROR);
            if(!is_array($r)||($r['restored']??null)!==true)throw new RuntimeException('recovery_required');
            $failure=$this->store->readFile('operations/'.$id.'/update-failure.json',1024);$cancel=$this->store->readFile('operations/'.$id.'/cancel.json',1024);
            $code=$cancel!==null?'timed_out':($failure===null?'interrupted':(json_decode($failure,true,4,JSON_THROW_ON_ERROR)['code']??'interrupted'));
            $this->resumeDns($id);$this->ticket($id,'finished');
            $this->store->update($id,['state'=>'failed','code'=>$code,'core_state'=>$r['core_state'],'installed_version'=>$r['version'],'settings_verified'=>$r['settings_verified'],'phase'=>'finished']);return ['state'=>'restored'];
        }catch(Throwable $e){
            // Rejected/duplicate entrypoints have no authority to terminalize
            // the genuine apply or a different recovery still holding leases.
            if(!$claimed)return ['state'=>'failed'];
            $this->store->writeFile('operations/'.$id.'/quiesce-recovery-error.json',json_encode(['code'=>AsusUpdatePrepare::code($e)],JSON_THROW_ON_ERROR));
            try{$this->ticket($id,'finished');}catch(Throwable $ignored){}
            $job=$this->store->readOperation($id);if($job['state']==='applying')$this->store->update($id,['state'=>'failed','code'=>'recovery_required','settings_verified'=>false]);return ['state'=>'failed'];
        }finally{foreach([$critical,$work,$apply] as $f)if(is_resource($f)){flock($f,LOCK_UN);fclose($f);}}
    }
    public function apply(string $id): array
    {
        $apply=$this->store->lease('apply.lock');
        try{return $this->store->withOperationLock($id,function()use($id){
            $job=$this->store->readOperation($id);if($job['state']!=='applying')return $job;$ticket=false;
            try{
                $this->assertDnsUpdateReady();
                $identity=AsusUpdateLifecycle::identity(getmypid());$runtime=$this->store->path('operations/'.$id.'/runtime').'/';
                if($identity===null||$identity['uid']!==$this->owner()||!str_starts_with($identity['exe'],$runtime)||($identity['exe']!==$runtime.'php'&&!preg_match('~^lib/ld[a-zA-Z0-9_.-]+$~D',substr($identity['exe'],strlen($runtime)))))throw new RuntimeException('invalid_state');
                $this->writeTicket(['schema'=>1,'id'=>$id,'boot_id'=>AsusUpdateStore::boot(),'worker'=>$identity,'installer'=>null,'phase'=>'validating','intent'=>['mode'=>'stopped']]);$ticket=true;
                $blocker=$job['identity']??null;
                if(!is_array($blocker)||($blocker['uid']??null)!==$this->owner()||!AsusUpdateLifecycle::alive($blocker)||!AsusUpdateGuard::ancestor($blocker['pid']))$blocker=$identity;
                $this->store->update($id,['identity'=>$blocker,'phase'=>'validating']);
                [$env,$candidate]=$this->validate($id,true);
                $this->install($id,$candidate);
                $after=$this->prepare->environment();if($after['installed']!==$candidate['package_version']||$after['pending'])throw new RuntimeException('version_mismatch');
                AsusUpdateSnapshot::verify($env['opt'],$this->settings($id),$this->owner(),true);
                $t=$this->ticket($id,'starting');$this->store->update($id,['phase'=>'verifying','installed_version'=>$after['installed'],'settings_verified'=>true]);
                $q=$this->quiesce($id);if($q===null)throw new RuntimeException('recovery_required');
                if($q['web_running']){$this->store->writeFile('operations/'.$id.'/web-started.json',json_encode(['started'=>true],JSON_THROW_ON_ERROR));$this->lifecycle->web();if(!$this->webHealth())throw new RuntimeException('web_health_failed');}
                $core=$this->lifecycle->restoreCheckpoint($this->store->path('operations/'.$id.'/service-state'));
                $this->quiesceDns($id,'after');$this->resumeDns($id);$this->ticket($id,'finished');return $this->store->update($id,['state'=>'succeeded','code'=>null,'phase'=>'finished','core_state'=>$core]);
            }catch(Throwable $e){
                $code=AsusUpdatePrepare::code($e);$patch=[];
                try{$this->store->failure($id,$code);}catch(Throwable $ignored){}
                if($ticket&&$this->store->readFile('operations/'.$id.'/boundary.json',1024)===null&&$this->store->readFile('operations/'.$id.'/quiesce.json')!==null){
                    $this->store->writeFile('operations/'.$id.'/update-failure.json',json_encode(['code'=>$code],JSON_THROW_ON_ERROR));
                    try{$this->install($id,['action'=>'rollback-verify']);$r=json_decode($this->store->readFile('operations/'.$id.'/quiesce-result.json',1024)??'',true,8,JSON_THROW_ON_ERROR);
                        if(($r['restored']??null)!==true)throw new RuntimeException('recovery_required');$patch=['core_state'=>$r['core_state'],'installed_version'=>$r['version'],'settings_verified'=>$r['settings_verified'],'phase'=>'finished'];$this->resumeDns($id);
                    }catch(Throwable $restore){$this->store->writeFile('operations/'.$id.'/quiesce-recovery-error.json',json_encode(['code'=>AsusUpdatePrepare::code($restore)],JSON_THROW_ON_ERROR));$code='recovery_required';$patch=['settings_verified'=>false];}
                }
                if($ticket&&$this->store->readFile('operations/'.$id.'/boundary.json',1024)!==null&&is_dir($this->store->path('operations/'.$id.'/rollback'))){
                    $this->store->writeFile('operations/'.$id.'/update-failure.json',json_encode(['code'=>$code],JSON_THROW_ON_ERROR));
                    try{
                        if(in_array($code,['core_stop_failed','web_stop_failed'],true))throw new RuntimeException('rollback_failed');
                        $this->install($id,['action'=>'rollback']);$this->install($id,['action'=>'rollback-verify']);
                        $result=json_decode($this->store->readFile('operations/'.$id.'/rollback-result.json',1024)??'',true,4,JSON_THROW_ON_ERROR);
                        if(!is_array($result)||($result['settings_verified']??null)!==true||!in_array($result['core_state']??null,['running','waiting_for_wan','stopped'],true))throw new RuntimeException('rollback_failed');
                        $this->resumeDns($id);$patch=['core_state'=>$result['core_state'],'installed_version'=>$result['version'],'settings_verified'=>true,'phase'=>'finished'];$code='update_rolled_back';
                    }catch(Throwable $rollback){$this->store->writeFile('operations/'.$id.'/rollback-failure.json',json_encode(['code'=>AsusUpdatePrepare::code($rollback)],JSON_THROW_ON_ERROR));$patch=['settings_verified'=>false];$code='rollback_failed';}
                }
                if($ticket){try{$this->ticket($id,'finished');}catch(Throwable $ignored){}}
                return $this->store->update($id,array_merge($patch,['state'=>'failed','code'=>$code]));
            }
        });}finally{flock($apply,LOCK_UN);fclose($apply);}
    }
}
