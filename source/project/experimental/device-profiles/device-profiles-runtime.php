<?php
require_once __DIR__.'/device-profiles-paths.php';
require_once __DIR__.'/device-profiles-queues.php';
require_once __DIR__.'/device-profiles-plan.php';
require_once __DIR__.'/device-profiles-library.php';
require_once __DIR__.'/device-profiles-transaction.php';

/** Optional platform adapters. HTTP fields never select commands or paths. */
final class NfqwsDeviceProfilesRuntime
{
    private NfqwsDeviceProfilesState $store;
    private NfqwsDeviceProfilesLibrary $library;
    private function helper():string{return NfqwsPlatform::settings()['library'].'/device-profiles-'.(NfqwsPlatform::native()?'native':'entware').'.sh';}
    private function root():string{return NfqwsPlatform::native()?'/var/run/nfqws2-native/device-profiles':'/tmp/nfqws2-asus/device-profiles';}
    private function binary():string{return NfqwsPlatform::native()?'/usr/bin/nfqws2':'/opt/usr/bin/nfqws2';}
    private function shell():array{return NfqwsPlatform::native()?['/bin/sh']:['/opt/libexec/nfqws2-asus/busybox','sh'];}
    public static function uplinks(string $raw):string
    {
        $names=preg_split('/\s+/',trim($raw),-1,PREG_SPLIT_NO_EMPTY);
        if(count($names)>64)throw new RuntimeException('invalid_uplinks');
        foreach($names as $name)if(!preg_match('/^[A-Za-z0-9_.:-]{1,15}$/D',$name))throw new RuntimeException('invalid_uplinks');
        return implode(' ',array_unique($names));
    }
    public function __construct()
    {
        $this->store=new NfqwsDeviceProfilesState(NfqwsPlatform::settings()['web_config'].'/device-profiles-lab');
        $this->library=new NfqwsDeviceProfilesLibrary();
    }
    public static function validateRequest(array $post):void
    {
        $fields=['deviceprofilesruntime'=>[],'deviceprofilescapture'=>['name'],
            'deviceprofilesimport'=>['name','document','trusted_lua'],
            'deviceprofilesapply'=>['revision','request_id','consent','start_after']];
        $cmd=$post['cmd']??null;if(!is_string($cmd)||!isset($fields[$cmd]))throw new RuntimeException('invalid_request');
        $keys=array_keys($post);sort($keys);$expected=array_merge(['cmd','csrf_token'],$fields[$cmd]);sort($expected);
        if($keys!==$expected)throw new RuntimeException('invalid_request');
        foreach($post as $key=>$value){
            $limit=$key==='document'?4194304:($key==='name'?256:1024);
            if(!is_string($value)||strlen($value)>$limit||str_contains($value,"\0"))throw new RuntimeException('invalid_request');
        }
        if($cmd==='deviceprofilesapply'&&(!preg_match('/^[a-f0-9]{64}$/D',$post['revision'])||!preg_match('/^[a-f0-9]{32}$/D',$post['request_id'])||$post['consent']!=='apply'||!in_array($post['start_after'],['0','1'],true)))throw new RuntimeException('invalid_request');
        if($cmd==='deviceprofilesimport'&&!in_array($post['trusted_lua'],['0','1'],true))throw new RuntimeException('invalid_request');
    }
    public static function ownedQueue(int $queue,array $instance,array $argv,array $bindings):bool
    {
        $command=$instance['command']??null;$pid=$instance['pid']??null;
        return ($instance['running']??false)===true&&is_int($pid)&&$pid>1&&is_array($command)&&
            in_array($command[0]??null,['/usr/bin/nfqws2','/opt/usr/bin/nfqws2'],true)&&$command===$argv&&
            count(array_keys($command,'--qnum='.$queue,true))===1&&($bindings[(string)$queue]??null)===$pid;
    }
    private function ownedInstance(int $queue,array $instance):bool
    {
        $pid=$instance['pid']??null;$cmd=$instance['command']??null;
        return ($instance['running']??false)===true&&is_int($pid)&&$pid>1&&is_array($cmd)&&
            ($cmd[0]??null)===$this->binary()&&$cmd===$this->argv($pid)&&
            count(array_keys($cmd,'--qnum='.$queue,true))===1&&NfqwsDeviceProfilesQueues::owned($queue,$pid);
    }
    private function run(array $args,float $timeout=15,int $limit=65536):array
    {return NfqwsPlatform::run($args,$timeout,[],$limit);}
    public function available():bool
    {
        $manifest=__DIR__.'/device-profiles-build.json';
        if(is_file($manifest)&&!is_link($manifest)){
            $reader=NfqwsDeviceProfilesPaths::reader($manifest);$raw=$reader->bytes(NfqwsDeviceProfilesPaths::readPath($manifest),16384);
            $install=json_decode($raw,true,8,JSON_THROW_ON_ERROR);
        }else $install=$this->store->read('install.json');
        if(($install['schema_version']??null)!==1||!is_array($install['files']??null)||count($install['files'])!==4)return false;
        $s=NfqwsPlatform::settings();$allowed=NfqwsPlatform::native()?['/usr/lib/nfqws2/nfqws2-native','/usr/lib/nfqws2/control.sh','/usr/lib/nfqws2/firewall.sh','/usr/share/nfqws2-web/index.php']:['/opt/etc/init.d/S51nfqws2','/opt/lib/nfqws2-asus/platform.sh','/opt/lib/nfqws2-asus/lifecycle.sh','/opt/share/nfqws-asus-web/index.php'];
        foreach($install['files']as $path=>$sha){
            if(!in_array($path,$allowed,true)||!is_string($sha)||!preg_match('/^[a-f0-9]{64}$/D',$sha)||is_link($path)||!is_file($path)||hash_file('sha256',$path)!==$sha)return false;
        }
        return true;
    }
    private function configRaw():string
    {
        $path=NfqwsDeviceProfilesPaths::guard(NfqwsPlatform::settings()['config'],'nfqws2.conf');
        $reader=NfqwsDeviceProfilesPaths::reader($path);return $reader->bytes($path,262144);
    }
    private function nativeInstances():array
    {
        $r=$this->run(['/bin/ubus','call','service','list','{"name":"nfqws2-native"}'],4,1048576);
        $json=json_decode(implode("\n",$r['output']),true);
        return $r['status']===0&&is_array($json['nfqws2-native']['instances']??null)?$json['nfqws2-native']['instances']:[];
    }
    private function instances():array
    {
        if(NfqwsPlatform::native())return $this->nativeInstances();$out=[];
        foreach([0,1,2,3]as $slot){
            try{
                $path=NfqwsDeviceProfilesPaths::guard($this->root(),'engine-'.$slot.'.pid');$stat=@lstat($path);
                if(!$stat)continue;
                if($stat['uid']!==0||($stat['mode']&0777)!==0600||$stat['size']>16)continue;
                $raw=trim((string)file_get_contents($path));if(!preg_match('/^[0-9]{1,10}$/D',$raw))continue;$pid=(int)$raw;
                $argv=$this->argv($pid);if(($argv[0]??null)!==$this->binary()||($argv[1]??null)!=='--daemon'||($argv[2]??null)!=='--pidfile='.$path)continue;
                if(realpath($this->binary())!==@readlink('/proc/'.$pid.'/exe'))continue;
                $identity=NfqwsDeviceProfilesPaths::guard($this->root(),'engine-'.$slot.'.identity');
                $lines=explode("\n",trim((string)file_get_contents($identity)));
                $proof=self::identity($pid);
                if(count($lines)!==5||$lines[0]!==$raw||$lines[1]!==($proof['ticks']??null)||$lines[2]!==($proof['boot']??null)||$lines[3]!==strval(41000+$slot)||$lines[4]!==hash('sha256',implode("\0",$argv)."\0"))continue;
                $out['device_profile_'.$slot]=['running'=>true,'pid'=>$pid,'command'=>$argv];
            }catch(Throwable $e){}
        }
        return $out;
    }
    private static function identity(int $pid):?array
    {
        $raw=@file_get_contents('/proc/'.$pid.'/stat');$at=is_string($raw)?strrpos($raw,')'):false;
        if($at===false)return null;$fields=explode(' ',trim(substr($raw,$at+1)));
        $boot=trim((string)@file_get_contents('/proc/sys/kernel/random/boot_id'));
        return isset($fields[19])?['pid'=>$pid,'ticks'=>$fields[19],'boot'=>$boot]:null;
    }
    public function recordActor(string $mode,string $id):void
    {
        if(NfqwsPlatform::native())return;
        if(!in_array($mode,['work','guard'],true)||!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');
        $identity=self::identity(getmypid());if(!$identity)throw new RuntimeException('worker_start_failed');
        $this->store->write('actor-'.$mode.'.json',$identity+['id'=>$id,'argv'=>$this->argv(getmypid())]);
    }
    private function entwareActorAlive(string $id,bool $workerOnly):bool
    {
        foreach($workerOnly?['work']:['work','guard']as $mode){
            $proof=$this->store->read('actor-'.$mode.'.json');if(($proof['id']??null)!==$id||!is_int($proof['pid']??null))continue;
            $identity=self::identity($proof['pid']);if(!$identity||$identity['ticks']!==($proof['ticks']??null)||$identity['boot']!==($proof['boot']??null))continue;
            $argv=$this->argv($proof['pid']);$tail=array_slice($argv,-5);
            if($argv!==($proof['argv']??null)||count($tail)!==5||$tail[0]!=='-f'||realpath($tail[1])!==__FILE__||array_slice($tail,2)!==['--',$mode,$id])continue;
            return true;
        }
        return false;
    }
    private function launchEntware(string $id,array $modes):array
    {
        foreach($modes as $mode){
            if(!in_array($mode,['work','guard'],true))throw new RuntimeException('invalid_request');
            $r=$this->run(['/opt/libexec/nfqws2-asus/busybox','start-stop-daemon','-S','-b','-p',$this->store->path('unused-'.$mode.'.pid'),'-x','/opt/libexec/nfqws2-asus/busybox','--','sh',$this->helper(),$mode,$id],4);
            if($r['status']!==0)return $r;
        }
        return ['status'=>0,'output'=>[]];
    }
    private function bindings():array
    {
        $raw=@file_get_contents('/proc/net/netfilter/nfnetlink_queue',false,null,0,65536);$out=[];
        foreach(explode("\n",is_string($raw)?$raw:'')as $line)if(preg_match('/^\s*([0-9]+)\s+(-?[0-9]+)\s/',$line,$m))$out[$m[1]]=$m[2];return $out;
    }
    private function argv(int $pid):array
    {
        if($pid<2)return [];$raw=@file_get_contents('/proc/'.$pid.'/cmdline',false,null,0,131073);
        return is_string($raw)&&strlen($raw)<=131072?explode("\0",rtrim($raw,"\0")):[];
    }
    private function processRunning():bool
    {
        if(!NfqwsPlatform::native()){
            $r=$this->run(['/opt/etc/init.d/S51nfqws2','diagnostics'],5);$v=json_decode(implode("\n",$r['output']),true);return ($v['process_running']??false)===true;
        }
        $r=$this->run(['/usr/lib/nfqws2/control.sh','process-pid'],3);
        return $r['status']===0&&preg_match('/^[0-9]+$/D',implode('',$r['output']))===1;
    }
    private function queueFreeOrOwned(array $plan):void
    {
        $bindings=$this->bindings();$instances=$this->instances();
        foreach($plan['instances']as $instance){
            $q=$instance['queue'];if(!isset($bindings[$q]))continue;
            $live=$instances['device_profile_'.$instance['slot']]??[];
            if(!$this->ownedInstance($q,$live))throw new RuntimeException('queue_conflict');
        }
    }
    private function compile(array $desired,string $uplinks=''):array
    {
        if(($desired['schema_version']??null)!==1||!is_array($desired['draft']??null))throw new RuntimeException('invalid_draft');
        $draft=NfqwsDeviceProfilesLab::normalize($desired['draft']);
        // The default mode never narrows the pre-existing ASUS config language.
        if($draft['mode']==='common')return ['desired'=>$desired,'strategies'=>[],'plan'=>['mode'=>'common','instances'=>[],'selectors'=>[],'warnings'=>[],'flow_tcp'=>'','flow_udp'=>'']];
        $base=NfqwsNativeConfig::parse($this->configRaw());
        $uplinks=self::uplinks($uplinks);
        $strategies=['current'=>$base];
        foreach($draft['profiles']as $profile)if($draft['mode']==='split'&&$profile['enabled']&&$profile['device_ids']&&$profile['strategy']!=='current'){
            $id=$profile['strategy'];$entry=$id==='stock'?$this->library->stock():$this->library->entry($id);
            $strategies[$id]=$entry['config'];$strategies[$id]['ISP_INTERFACE']=$uplinks;$strategies[$id]['IPV6_ENABLED']=$base['IPV6_ENABLED'];
        }
        $discovery=(new NfqwsDeviceProfilesLab())->status()['discovery'];
        return ['desired'=>$desired,'strategies'=>$strategies,
            'plan'=>NfqwsDeviceProfilesPlan::compile($draft,$discovery,$strategies,(int)$base['NFQUEUE_NUM'])];
    }
    private function artifactDirectory(string $name):string
    {
        if(!preg_match('/^(?:active|pending-[a-f0-9]{32})$/D',$name))throw new RuntimeException('invalid_request');
        foreach([$this->root(),$this->root().'/'.$name]as $dir){
            if(!file_exists($dir)){NfqwsDeviceProfilesPaths::guard(dirname($dir),basename($dir));$mask=umask(0077);try{if(!mkdir($dir,0700))throw new RuntimeException('storage_unavailable');}finally{umask($mask);}}
            $s=lstat($dir);if(is_link($dir)||!is_dir($dir)||$s['uid']!==0||($s['mode']&0777)!==0700)throw new RuntimeException('storage_unavailable');
        }
        return $this->root().'/'.$name;
    }
    private function artifact(string $directory,string $name,?string $data):void
    {
        $path=NfqwsDeviceProfilesPaths::guard($directory,$name);
        if($data===null){if(file_exists($path))unlink($path);return;}
        if(strlen($data)>524288)throw new RuntimeException('runtime_limit');
        $temp=NfqwsDeviceProfilesPaths::guard($directory,'.stage-'.bin2hex(random_bytes(8)));$mask=umask(0077);
        try{$f=fopen($temp,'xb');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(fwrite($f,$data)!==strlen($data)||!fflush($f))throw new RuntimeException('insufficient_space');fclose($f);$f=null;
            NfqwsDeviceProfilesPaths::guard($directory,$name);if(!rename($temp,$path))throw new RuntimeException('storage_unavailable');
        }finally{if(is_resource($f))fclose($f);if(file_exists($temp))unlink($temp);}
    }
    public function prepareArtifacts(string $name,string $uplinks=''):void
    {
        if(!$this->available())throw new RuntimeException('runtime_unavailable');
        if($name==='active')$this->recoverAtBoot();
        if($name==='active')$desired=$this->store->read('active.json')??['schema_version'=>1,'draft'=>['schema_version'=>1,'mode'=>'common','devices'=>[],'profiles'=>[]]];
        else{
            $id=substr($name,8);$job=$this->store->read('job.json');$pending=$this->store->read('pending.json');
            if(($job['id']??null)!==$id||($pending['id']??null)!==$id)throw new RuntimeException('invalid_request');$desired=$pending['desired'];
        }
        $compiled=$this->compile($desired,$uplinks);$plan=$compiled['plan'];$this->queueFreeOrOwned($plan);$directory=$this->artifactDirectory($name);
        $args=[];
        foreach($plan['instances']as $instance){
            $argv=NfqwsDeviceProfilesPlan::arguments($instance['config'],$instance['queue']);
            $r=$this->run([$this->binary(),'--dry-run',...$argv],12);
            if($r['status']!==0)throw new RuntimeException('invalid_profile_engine');$args[$instance['slot']]=implode(' ',$argv);
        }
        foreach([0,1,2,3]as $slot)$this->artifact($directory,'args.'.$slot,$args[$slot]??null);
        $rules=NfqwsDeviceProfilesPlan::rules($plan);
        foreach($rules as $key=>$raw)$this->artifact($directory,'rules-'.$key.'.nft',$raw);
        if(!NfqwsPlatform::native())foreach([4,6]as $family)$this->artifact($directory,'rules-entware'.$family.'.restore',NfqwsDeviceProfilesPlan::entwareRules($plan,$family));
        $this->artifact($directory,'flow-tcp',$plan['mode']==='common'?null:$plan['flow_tcp']);$this->artifact($directory,'flow-udp',$plan['mode']==='common'?null:$plan['flow_udp']);
        $this->artifact($directory,'enabled',$plan['mode']==='split'?"1\n":null);
        (new NfqwsDeviceProfilesState($directory))->write('active.json',$compiled);
    }
    public function check():void
    {
        $r=$this->run(NfqwsPlatform::native()?['/usr/lib/nfqws2/control.sh','check']:['/opt/etc/init.d/S51nfqws2','diagnostics'],5);if($r['status']!==0)throw new RuntimeException('queue_unavailable');
        if(!NfqwsPlatform::native()){$v=json_decode(implode("\n",$r['output']),true);if(($v['process_running']??false)!==true||($v['nfqueue']['state']??null)!=='bound')throw new RuntimeException('queue_unavailable');}
        $compiled=(new NfqwsDeviceProfilesState($this->root().'/active'))->read('active.json');
        if($compiled===null)throw new RuntimeException('runtime_unavailable');
        $bindings=$this->bindings();$instances=$this->instances();
        foreach($compiled['plan']['instances']as $row){$live=$instances['device_profile_'.$row['slot']]??[];
            if(!$this->ownedInstance($row['queue'],$live))throw new RuntimeException('queue_unavailable');}
    }
    public function status():array
    {
        $available=$this->available();$active=$this->store->read('active.json');$job=$this->store->read('job.json');$running=false;
        if($available&&in_array($job['state']??null,['queued','running'],true)&&time()-($job['started_at']??0)>6&&!$this->actorAlive($job['id']))$this->launchGuard($job['id']);
        $coreRunning=$available&&$this->processRunning();
        if($coreRunning)try{$this->check();$running=true;}catch(Throwable $e){}
        return ['available'=>$available,'configured'=>$active!==null,'mode'=>$active['draft']['mode']??'common',
            'running'=>$running,'core_running'=>$coreRunning,'applied_revision'=>$active['revision']??null,'job'=>NfqwsDeviceProfilesTransaction::project($job),
            'limits'=>['additional_processes'=>4,'library'=>8],'templates'=>$this->library->listing()];
    }
    public function blocksUpdate():bool
    {
        if(!$this->available())return false;$active=$this->store->read('active.json');$job=$this->store->read('job.json');
        return ($active['draft']['mode']??null)==='split'||in_array($job['state']??null,['queued','running'],true);
    }
    public function dispatch(array $post):array
    {
        self::validateRequest($post);
        if($post['cmd']==='deviceprofilesruntime')return $this->status();
        if(!$this->available())throw new RuntimeException('runtime_unavailable');
        if($post['cmd']==='deviceprofilescapture')return $this->library->capture($post['name']);
        if($post['cmd']==='deviceprofilesimport')return $this->library->import($post['name'],$post['document'],$post['trusted_lua']==='1');
        return $this->startJob($post);
    }
    private function startJob(array $post):array
    {
        [$job,$launch]=$this->store->locked(function()use($post){
            $previous=$this->store->read('job.json');
            if(($previous['request_id']??null)===$post['request_id'])return [$previous,false];
            if(in_array($previous['state']??'', ['queued','running'],true))throw new RuntimeException('busy');
            $saved=(new NfqwsDeviceProfilesLab())->status();
            if($saved['revision']!==$post['revision'])throw new RuntimeException('stale_revision');
            $id=bin2hex(random_bytes(16));$desired=['schema_version'=>1,'draft'=>$saved['draft'],'revision'=>$saved['revision']];
            $job=['id'=>$id,'request_id'=>$post['request_id'],'revision'=>$post['revision'],'desired'=>$desired,
                'source_sha256'=>hash('sha256',$this->configRaw()),'start_after'=>$post['start_after']==='1',
                'state'=>'queued','phase'=>'queued','code'=>null,'started_at'=>time(),'updated_at'=>time()];
            $this->store->write('job.json',$job);
            return [$job,true];
        });
        if($launch){
            // Release the writer before procd can run the worker. It takes the
            // same lock; retaining it during the ubus RPC creates a spawn race.
            $id=$job['id'];$unit=['name'=>'nfqws2-device-profiles-job','instances'=>['apply'=>[
                'command'=>[...$this->shell(),$this->helper(),'work',$id],'stdout'=>false,'stderr'=>false],
                'guard'=>['command'=>[...$this->shell(),$this->helper(),'guard',$id],'stdout'=>false,'stderr'=>false]]];
            $r=NfqwsPlatform::native()?$this->run(['/bin/ubus','call','service','set',json_encode($unit,JSON_THROW_ON_ERROR)],4):$this->launchEntware($id,['work','guard']);
            if($r['status']!==0&&!$this->actorAlive($id))$this->failQueued($id,'worker_start_failed');
        }
        return NfqwsDeviceProfilesTransaction::project($this->store->read('job.json'));
    }
    public function work(string $id):void
    {
        $job=$this->store->read('job.json');
        if(($job['id']??null)!==$id||($job['state']??null)!=='queued')throw new RuntimeException('invalid_request');
        if(!class_exists('AsusImportTransaction',false))require_once __DIR__.'/import-transaction.php';
        try{(new AsusImportTransaction())->writer(function()use($job,$id){
            (new NfqwsDeviceProfilesTransaction($this->store,$this->driver($job,$id)))->execute($job,$job['desired'],$job['start_after']);
        });}catch(Throwable $e){$this->failQueued($id,NfqwsDeviceProfilesTransaction::error($e));}
    }
    private function driver(array $job,string $id):array
    {
        return [
                'running'=>fn()=>$this->processRunning(),
                'validate'=>function($desired)use($job,$id){
                    if(hash('sha256',$this->configRaw())!==$job['source_sha256'])throw new RuntimeException('source_changed');
                    $saved=(new NfqwsDeviceProfilesLab())->status();if($saved['revision']!==$job['revision'])throw new RuntimeException('stale_revision');
                    $this->store->write('pending.json',['id'=>$id,'desired'=>$desired]);
                    $r=$this->run([...$this->shell(),$this->helper(),'validate',$id],90);
                    $this->cleanupPending($id);
                    if($r['status']!==0){$cause=trim(implode("\n",$r['output']));
                        throw new RuntimeException(in_array($cause,['queue_conflict','invalid_profile_engine','strategy_unavailable','runtime_profile_limit','runtime_limit','invalid_profile_ports'],true)?$cause:'profile_validation_failed');}
                    if(hash('sha256',$this->configRaw())!==$job['source_sha256'])throw new RuntimeException('source_changed');
                },
                'stop'=>function(){if($this->run(NfqwsPlatform::serviceCommand('stop'),30)['status']!==0)throw new RuntimeException('profile_stop_failed');},
                'start'=>function(){if($this->run(NfqwsPlatform::serviceCommand('start'),60)['status']!==0)throw new RuntimeException('profile_start_failed');},
                'check'=>fn()=>$this->check(),
            ];
    }
    private function actorAlive(string $id,bool $workerOnly=false):bool
    {
        if(!NfqwsPlatform::native())return $this->entwareActorAlive($id,$workerOnly);
        $r=$this->run(['/bin/ubus','call','service','list','{"name":"nfqws2-device-profiles-job"}'],3,32768);
        $value=json_decode(implode("\n",$r['output']),true);
        foreach($value['nfqws2-device-profiles-job']['instances']??[]as $name=>$instance){
            if(($instance['running']??false)!==true||!is_int($instance['pid']??null))continue;
            $action=$name==='apply'?'work':($name==='guard'&&!$workerOnly?'guard':null);
            $expected=[...$this->shell(),$this->helper(),$action,$id];
            if($action!==null&&($instance['command']??null)===$expected&&$this->argv($instance['pid'])===$expected)return true;
        }
        return false;
    }
    private function cleanupPending(string $id):void
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');
        $dir=$this->root().'/pending-'.$id;clearstatcache(true,$dir);$stat=@lstat($dir);if(!$stat)return;
        if(is_link($dir)||!is_dir($dir)||$stat['uid']!==0||($stat['mode']&0777)!==0700)throw new RuntimeException('pending_cleanup_failed');
        $files=[];
        foreach(scandir($dir)as $name){
            if($name==='.'||$name==='..')continue;
            if(!preg_match('/^(?:args\.[0-3]|rules-(?:definitions|original|reply)\.nft|flow-(?:tcp|udp)|enabled|active\.json|rules\.full\.nft|rules-entware[46]\.restore|\.stage-(?:[a-f0-9]{16}|[a-f0-9]{32}))$/D',$name))throw new RuntimeException('pending_cleanup_failed');
            $path=NfqwsDeviceProfilesPaths::guard($dir,$name);$s=lstat($path);
            if($s['uid']!==0||($s['mode']&0777)!==0600)throw new RuntimeException('pending_cleanup_failed');$files[]=$path;
            if(count($files)>32)throw new RuntimeException('pending_cleanup_failed');
        }
        foreach($files as $path)if(!unlink($path))throw new RuntimeException('pending_cleanup_failed');
        if(!rmdir($dir))throw new RuntimeException('pending_cleanup_failed');
    }
    private function launchGuard(string $id):void
    {
        $unit=['name'=>'nfqws2-device-profiles-job','instances'=>[
            'guard'=>['command'=>[...$this->shell(),$this->helper(),'guard',$id],'stdout'=>false,'stderr'=>false]]];
        if(NfqwsPlatform::native())$this->run(['/bin/ubus','call','service','set',json_encode($unit,JSON_THROW_ON_ERROR)],4);else $this->launchEntware($id,['guard']);
    }
    public function failQueued(string $id,string $code):void
    {
        $this->store->locked(function()use($id,$code){
            $job=$this->store->read('job.json');if(($job['id']??null)!==$id||($job['state']??null)!=='queued')return;
            $job['state']='failed';$job['code']=$code;$job['original_code']=$code;$job['updated_at']=time();$this->store->write('job.json',$job);
        });
    }
    public function guard(string $id):void
    {
        for($i=0;$i<600;$i++){
            $job=$this->store->read('job.json');
            if(($job['id']??null)!==$id||!in_array($job['state']??null,['queued','running'],true))return;
            if($this->actorAlive($id,true)||time()-($job['started_at']??0)<6){sleep(1);continue;}
            if(!class_exists('AsusImportTransaction',false))require_once __DIR__.'/import-transaction.php';
            (new AsusImportTransaction())->writer(fn()=>(new NfqwsDeviceProfilesTransaction($this->store,$this->driver($job,$id)))->recover($job));
            $this->cleanupPending($id);return;
        }
    }
    private function recoverAtBoot():void
    {
        $job=$this->store->read('job.json');
        if(!in_array($job['state']??null,['queued','running'],true)||$this->actorAlive($job['id']))return;
        // No previous-boot worker can survive a reboot. Restore only a known
        // pointer before an ordinary boot starts any new capture instances.
        if($this->processRunning())throw new RuntimeException('worker_interrupted');
        $this->store->locked(function()use($job){
            $current=$this->store->read('job.json');if(($current['id']??null)!==$job['id'])throw new RuntimeException('busy');
            if(array_key_exists('before_active',$job)){
                $active=$this->store->read('active.json');
                if($active!==$job['before_active']&&$active!==$job['desired'])throw new RuntimeException('recovery_required');
                $this->store->write('active.json',$job['before_active']);
            }
            $job['state']='failed';$job['code']='worker_interrupted';$job['original_code']='worker_interrupted';$job['recovered']=null;$job['updated_at']=time();
            $this->store->write('job.json',$job);
        });
    }
    public function reconcile():void
    {
        if(!$this->available())return;
        $active=$this->store->read('active.json');if(($active['draft']['mode']??null)!=='split')return;
        $compiled=(new NfqwsDeviceProfilesState($this->root().'/active'))->read('active.json');
        if(($compiled['desired']['revision']??null)!==($active['revision']??null))return;
        $this->check();$discovery=(new NfqwsDeviceProfilesLab())->status()['discovery'];
        $config=$compiled['strategies']['current'];
        $plan=NfqwsDeviceProfilesPlan::compile($active['draft'],$discovery,$compiled['strategies'],(int)$config['NFQUEUE_NUM']);
        if(!NfqwsPlatform::native()){
            $directory=$this->root().'/active';
            foreach([4,6]as $family)$this->artifact($directory,'rules-entware'.$family.'.restore',NfqwsDeviceProfilesPlan::entwareRules($plan,$family));
            return;
        }
        $r=$this->run(['/usr/sbin/nft','-j','list','table','inet','nfqws2_native'],4,1048576);
        $table=json_decode(implode("\n",$r['output']),true);$owned=false;$sets=[];
        foreach($table['nftables']??[]as $item){
            if(($item['table']['comment']??null)==='NFQWS2 native OpenWrt')$owned=true;
            if(isset($item['set']))$sets[$item['set']['name']]=$item['set']['type']??null;
        }
        if(!$owned)throw new RuntimeException('firewall_owner_conflict');$lines='';
        foreach($plan['selectors']as $i=>$p)foreach([4,6]as $family){
            $name='dp_'.$i.'_'.$family;if(($sets[$name]??null)!=='ipv'.$family.'_addr')throw new RuntimeException('firewall_owner_conflict');
            $lines.='flush set inet nfqws2_native '.$name."\n";
            if($p['addresses'.$family])$lines.='add element inet nfqws2_native '.$name.' { '.implode(', ',$p['addresses'.$family])." }\n";
        }
        $directory=$this->root().'/active';$this->artifact($directory,'reconcile.nft',$lines);
        $path=$directory.'/reconcile.nft';
        if($this->run(['/usr/sbin/nft','-c','-f',$path],5)['status']!==0||$this->run(['/usr/sbin/nft','-f',$path],5)['status']!==0)throw new RuntimeException('firewall_reconcile_failed');
    }
}

// Include from authenticated dispatcher is harmless. Only this fixed root CLI
// entry may launch native actuators; HTTP fields cannot choose CLI operations.
if(NfqwsDeviceProfilesPaths::cliEntry(__FILE__,$_SERVER,$argv??[])){
    if(!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(2);
    $args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);$mode=array_shift($args);

    try{
        $runtime=new NfqwsDeviceProfilesRuntime();
        if(in_array($mode,['work','guard'],true)&&count($args)===1)$runtime->recordActor($mode,$args[0]);
        if($mode==='preflight'&&count($args)===1)$runtime->prepareArtifacts('active',$args[0]);
        elseif($mode==='pending'&&count($args)===2&&preg_match('/^[a-f0-9]{32}$/D',$args[0]))$runtime->prepareArtifacts('pending-'.$args[0],$args[1]);
        elseif($mode==='check'&&$args===[])$runtime->check();
        elseif($mode==='reconcile'&&$args===[])$runtime->reconcile();
        elseif($mode==='work'&&count($args)===1&&preg_match('/^[a-f0-9]{32}$/D',$args[0]))$runtime->work($args[0]);
        elseif($mode==='guard'&&count($args)===1&&preg_match('/^[a-f0-9]{32}$/D',$args[0]))$runtime->guard($args[0]);
        elseif($mode==='queued-failure'&&count($args)===1&&preg_match('/^[a-f0-9]{32}$/D',$args[0]))$runtime->failQueued($args[0],'package_operation_active');
        else exit(2);
        exit(0);
    }catch(Throwable $e){file_put_contents('php://stderr',NfqwsDeviceProfilesTransaction::error($e)."\n");exit(1);}
}
