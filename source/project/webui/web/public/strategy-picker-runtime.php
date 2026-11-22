<?php
require_once __DIR__.'/strategy-picker-core.php';
require_once __DIR__.'/strategy-picker-admission.php';
require_once __DIR__.'/strategy-picker-metrics.php';
require_once __DIR__.'/dpi-jobs.php';
require_once __DIR__.'/update-guard.php';
require_once __DIR__.'/profile-catalog-transport.php';
require_once __DIR__.'/share-resources.php';
require_once __DIR__.'/import-plan.php';
require_once __DIR__.'/import-transaction.php';
require_once __DIR__.'/strategy-synthesis-runtime.php';
require_once __DIR__.'/strategy-picker-custom-runtime.php';
$pickerSources=is_file(__DIR__.'/device-profiles-library.php')?__DIR__:dirname(__DIR__,3).'/experimental/device-profiles';
if(!class_exists('NfqwsNativeConfig',false)&&!is_file(NfqwsPlatform::settings()['library'].'/config.php'))require_once dirname(__DIR__,3).'/openwrt/config.php';
require_once $pickerSources.'/device-profiles-library.php';
require_once $pickerSources.'/device-profiles-transaction.php';
unset($pickerSources);

/** All actuators are fixed package code. HTTP selects neither shell nor paths. */
final class NfqwsStrategyPickerRuntime
{
    use NfqwsStrategySynthesisRuntime;
    use NfqwsStrategyPickerCustomRuntime;
    private NfqwsStrategyPickerState $store;
    private NfqwsStrategyPickerConfig $config;
    private const ACTIVE=['preparing','running','restoring','applying'];
    public function __construct(?NfqwsStrategyPickerState $store=null,?NfqwsStrategyPickerConfig $config=null)
    {
        $s=NfqwsPlatform::settings();$this->store=$store??new NfqwsStrategyPickerState($s['web_config'].'/strategy-picker');
        $this->config=$config??new NfqwsStrategyPickerConfig($this->store,$s['config'].'/nfqws2.conf');
    }
    public static function validateRequest(array $p):void
    {
        $fields=['pickerstatus'=>[],'pickerreport'=>[],'pickertargets'=>['custom_sites'],'pickerplan'=>['search','extended'],'pickerstart'=>['request_id','consent'],'pickerextended'=>['request_id','consent'],'pickersynthesize'=>['request_id','consent'],'pickerresult'=>['id','result'],'pickerexport'=>['id'],'pickercancel'=>['id'],'pickerapply'=>['id']];
        $fields['pickerwindow']=['request_id','window_id','presence'];
        $cmd=$p['cmd']??null;if(!is_string($cmd)||!isset($fields[$cmd]))throw new RuntimeException('invalid_request');
        $keys=array_keys($p);sort($keys);$expected=array_merge(['cmd','csrf_token'],$fields[$cmd]);sort($expected);
        if(in_array($cmd,['pickerstart','pickerextended','pickersynthesize','pickerplan'],true)&&array_key_exists('goal',$p)){$expected[]='goal';sort($expected);}
        if(in_array($cmd,['pickerstart','pickerextended','pickersynthesize','pickerplan'],true)&&array_key_exists('concurrency',$p)){$expected[]='concurrency';sort($expected);}
        if(($cmd==='pickersynthesize'||$cmd==='pickerplan'&&($p['search']??null)==='synthesis')&&array_key_exists('rounds',$p)){$expected[]='rounds';sort($expected);}
        if(in_array($cmd,['pickerstart','pickerextended','pickersynthesize'],true)&&array_key_exists('plan_sha256',$p)){$expected[]='plan_sha256';sort($expected);}
        if(in_array($cmd,['pickerstart','pickerextended','pickersynthesize'],true)&&array_key_exists('window_id',$p)){$expected[]='window_id';sort($expected);}
        if(in_array($cmd,['pickerexport','pickerapply'],true)&&array_key_exists('torrent_sites',$p)){$expected[]='torrent_sites';sort($expected);}
        if($cmd==='pickerexport'&&array_key_exists('result',$p)){$expected[]='result';sort($expected);}
        if(($cmd==='pickersynthesize'||$cmd==='pickerplan'&&($p['search']??null)==='synthesis')&&(array_key_exists('custom_sites',$p)||array_key_exists('custom_only',$p))){$expected=array_merge($expected,['custom_sites','custom_only']);sort($expected);}
        if($keys!==$expected)throw new RuntimeException('invalid_request');
        foreach($p as $key=>$v)if(!is_string($v)||strlen($v)>($key==='custom_sites'?4096:128))throw new RuntimeException('invalid_request');
        foreach(['id','request_id','result','window_id']as $k)if(isset($p[$k])&&!preg_match('/^[a-f0-9]{32}$/D',$p[$k]))throw new RuntimeException('invalid_request');
        if($cmd==='pickerwindow'&&!in_array($p['presence'],['open','closed'],true))throw new RuntimeException('invalid_request');
        if(isset($p['consent'])&&$p['consent']!=='test')throw new RuntimeException('consent_required');
        if(isset($p['goal']))NfqwsStrategyPickerGoals::parse($p['goal']);
        if(isset($p['concurrency']))NfqwsStrategyPickerConcurrency::parse($p['concurrency']);
        if(isset($p['rounds']))NfqwsStrategyPickerRequest::rounds($p['rounds']);
        if(isset($p['plan_sha256'])&&!preg_match('/^[a-f0-9]{64}$/D',$p['plan_sha256']))throw new RuntimeException('invalid_request');
        if($cmd==='pickerplan'&&(!in_array($p['search'],['profiles','synthesis'],true)||!in_array($p['extended'],['0','1'],true)))throw new RuntimeException('invalid_request');
        if(isset($p['torrent_sites'])&&!in_array($p['torrent_sites'],['0','1'],true))throw new RuntimeException('invalid_request');
        if(isset($p['result'],$p['torrent_sites'])&&$p['torrent_sites']!=='0')throw new RuntimeException('invalid_request');
        if(isset($p['custom_only'])&&!in_array($p['custom_only'],['0','1'],true))throw new RuntimeException('invalid_request');
    }
    public static function identity(int $pid):?array
    {
        if($pid<2)return null;return NfqwsStrategyPickerAdmission::identity($pid);
    }
    public static function sameActor(?array $actor):bool
    {return $actor!==null&&is_int($actor['pid']??null)&&self::identity($actor['pid'])===$actor;}
    private function actor(string $name,string $id,?array &$recordPin=null):?array
    {
        $recordPin=null;
        $r=$this->store->read('actor-'.$name.'.json',$observedPin);
        if(($r['id']??null)!==$id)return null;$a=$r['identity']??null;
        if(!is_array($a)||!is_int($a['pid']??null)||$a['pid']<2)throw new RuntimeException('recovery_required');
        if(!self::sameProcess($a,$exited)){
            if($exited)return null;throw new RuntimeException('recovery_required');
        }
        $argv=$a['argv'];$tail=array_slice($argv,-4);
        if(count($tail)!==4||realpath($tail[0])!==__FILE__||array_slice($tail,1)!==['--',$name,$id])throw new RuntimeException('recovery_required');$recordPin=$observedPin;return $a;
    }
    /** Archive an already restored, reaped fixed stop without reusing its input. */
    private function recoveredStopArchivable(?array $j):bool
    {
        try{
            if(($j['state']??null)!=='recovery_required'||($j['restored']??null)!==true||($j['running_before']??null)!==false||($j['library_namespace']??null)!=='job-v1'||($j['custom_worker']??null)!==null)return false;
            $id=$j['id']??null;$boot=trim((string)file_get_contents('/proc/sys/kernel/random/boot_id'));
            if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id)||($j['boot']??null)!==$boot||$this->store->read('state.json',$pin)!==$j)return false;
            $intent=$j['actuator_intent']??null;$attention=$j['actuator_attention']??null;$a=$j['actuator']??null;
            if(!is_array($intent)||count($intent)!==5||($intent['argv']??null)!==NfqwsPlatform::serviceCommand('stop')||($intent['possible_input']??null)!==true||!is_numeric($intent['deadline']??null)||!is_finite((float)$intent['deadline'])||!is_string($intent['nonce']??null)||!preg_match('/^[a-f0-9]{32}$/D',$intent['nonce']))return false;
            if(!is_array($attention)||count($attention)!==4||($attention['intent']??null)!==$intent||($attention['reason']??null)!=='recovery_required'||($attention['resource_reaped']??null)!==true||!is_array($a)||($attention['resource_pid']??null)!==($a['pid']??null))return false;
            $records=[];
            foreach(['work','guard']as $role){
                $r=$this->store->read('actor-'.$role.'.json',$actorPin);$actor=$r['identity']??null;
                if(($r['id']??null)!==$id||!is_array($actor)||($actor['boot']??null)!==$boot||array_slice($actor['argv']??[],-4)!==[__FILE__,'--',$role,$id])return false;
                if(self::sameProcess($actor,$exited)||!$exited)return false;
                if($role==='guard'&&(($j['engine_trial']['guard']??null)!==$actor||($j['engine_trial']['guard_pin']??null)!==$actorPin))return false;
                $records[$role]=$r;
            }
            if(($intent['parent']??null)!==$records['work']['identity']||($a['boot']??null)!==$boot||array_slice($a['argv']??[],-2)!==NfqwsPlatform::serviceCommand('stop')||self::sameProcess($a,$exited)||!$exited||$this->running())return false;
            foreach($records as $role=>$r)if($this->store->read('actor-'.$role.'.json')!==$r)return false;
            return $this->store->read('state.json',$after)===$j&&$after===$pin;
        }catch(Throwable $e){return false;}
    }
    public function active():bool{return in_array($this->store->read()['state']??null,self::ACTIVE,true);}
    private function budget():array
    {
        $cpu=(string)@file_get_contents('/proc/cpuinfo');$cores=max(1,preg_match_all('/^processor\s*:/m',$cpu));
        $raw=(string)@file_get_contents('/proc/meminfo');$mem=[];
        foreach(['MemAvailable','MemFree','Buffers','Cached']as $key){preg_match('/^'.$key.':\s*([0-9]+)/m',$raw,$m);$mem[$key]=(int)($m[1]??0);}
        $load=explode(' ',trim((string)file_get_contents('/proc/loadavg')))[0];
        return NfqwsStrategyPickerBudget::choose($cores,$mem['MemAvailable']?:$mem['MemFree']+$mem['Buffers']+$mem['Cached'],(float)$load);
    }
    private function running():bool
    {
        $r=NfqwsPlatform::run(NfqwsPlatform::serviceCommand('diagnostics'),8,[],65536);
        $d=json_decode(implode("\n",$r['output']),true);
        if(!is_bool($d['process_running']??null))throw new RuntimeException('service_state_unknown');
        return $d['process_running'];
    }
    private static function sameProcess(?array $proof,?bool &$exited=null):bool
    {
        // The optional result describes observed absence/exited state only;
        // it never lets a caller turn partial context into signal authority.
        $exited=false;if(self::sameActor($proof))return true;
        if(!$proof||!is_int($proof['pid']??null)||$proof['pid']<2)return false;
        $proc='/proc/'.$proof['pid'];$raw=@file_get_contents($proc.'/stat',false,null,0,131073);clearstatcache(true,$proc);
        if($raw===false&&!is_dir($proc)){$exited=true;return false;}
        if(is_string($raw)&&strlen($raw)<=131072&&($end=strrpos($raw,')'))!==false){
            $parts=explode(' ',trim(substr($raw,$end+1)));
            if(($parts[0]??null)==='Z'&&is_string($proof['ticks']??null)&&($parts[19]??null)===$proof['ticks']&&($proof['boot']??null)===trim((string)file_get_contents('/proc/sys/kernel/random/boot_id')))$exited=true;
        }
        return false;
    }
    private static function killTree(array $root):void
    {
        if(!self::sameProcess($root,$exited)){if($exited)return;throw new RuntimeException('recovery_required');}$owned=[$root['pid']=>$root];
        for($pass=0;$pass<8;$pass++){
            $added=false;
            foreach(glob('/proc/[0-9]*/stat')?:[]as $path){
                $raw=@file_get_contents($path);$end=is_string($raw)?strrpos($raw,')'):false;if($end===false)continue;
                $parts=explode(' ',trim(substr($raw,$end+1)));$ppid=(int)($parts[1]??0);$pid=(int)basename(dirname($path));
                if(!isset($owned[$pid])&&isset($owned[$ppid])&&self::sameProcess($owned[$ppid])){
                    $proof=self::identity($pid);if($proof){$owned[$pid]=$proof;$added=true;}
                }
            }if(!$added)break;
        }
        $bb=NfqwsPlatform::native()?['/bin/kill']:[NfqwsPlatform::busybox(),'kill'];
        foreach(['-TERM','-KILL']as $signal){
            foreach(array_reverse($owned,true)as $proof)if(self::sameProcess($proof))NfqwsPlatform::run([...$bb,$signal,(string)$proof['pid']],2);
            usleep(300000);
        }
        foreach($owned as $proof){if(self::sameProcess($proof,$exited))throw new RuntimeException('actuator_stop_failed');if(!$exited)throw new RuntimeException('recovery_required');}
    }
    private static function closeProcess($process,int $observed):int
    {
        $closed=proc_close($process);
        // A fast child can exit between proc_get_status and /proc identity.
        // Conversely, PHP may already have consumed its exit code in status.
        return $observed>=0?$observed:$closed;
    }
    private static function readPipes(array $pipes,string $raw):string
    {
        foreach($pipes as $f){
            if(strlen($raw)>65536)break;
            $next=stream_get_contents($f,65537-strlen($raw));
            if($next!==false)$raw.=$next;
        }
        return $raw;
    }
    private function actuator(array $argv,int $seconds,?string $input=null,?callable $checkpoint=null,bool $waitForServiceLock=false):array
    {
        $pending=$this->store->read();if(($pending['actuator_attention']??null)!==null||($pending['actuator_intent']??null)!==null)throw new RuntimeException('recovery_required');
        if($input!==null)return $this->inputActuator($argv,$seconds,$input,$checkpoint);
        if($checkpoint!==null)$checkpoint();
        if($seconds<1)throw new RuntimeException('invalid_request');
        $job=$this->store->read();$id=$job['id']??null;$phase=$job['phase']??null;$parent=self::identity(getmypid());
        if(!is_string($id)||!is_string($phase)||$parent===null)throw new RuntimeException('invalid_state');
        if(($job['actuator_attention']??null)!==null||($job['actuator_intent']??null)!==null)throw new RuntimeException('recovery_required');
        if(($job['actuator']??null)!==null)throw new RuntimeException('busy');
        // The original timer includes intent persistence and process startup.
        // A possible-input record precedes proc_open; it grants no ownership.
        $until=microtime(true)+$seconds;$intent=['nonce'=>bin2hex(random_bytes(16)),'parent'=>$parent,'argv'=>$argv,'deadline'=>$until,'possible_input'=>true];
        $this->phase($phase,['actuator_intent'=>$intent]);
        $publish=function(array $extra)use($id,$intent):void{
            $current=$this->store->read();
            if(($current['id']??null)!==$id||($current['actuator_intent']??null)!==$intent)throw new RuntimeException('recovery_required');
            $this->phase($current['phase'],$extra);
        };
        $pipes=[];$p=null;$proof=null;$pid=null;$raw='';$exit=-1;$unknown=false;
        try{
            if(microtime(true)>=$until)throw new RuntimeException('timed_out');
            if($checkpoint!==null)$checkpoint();
            $environment=['PATH'=>'/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin'];
            if($waitForServiceLock)$environment['NFQWS_CORE_LOCK_WAIT']='1';
            $p=proc_open($argv,[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes,null,$environment);
            if(!is_resource($p))throw new RuntimeException('launch_failed');
            foreach($pipes as $f)stream_set_blocking($f,false);
            $status=proc_get_status($p);$pid=$status['pid'];
            // A null or inherited pre-exec cmdline is not a completed child.
            // The parent still owns the exact proc_resource during this wait.
            while($status['running']){
                if($checkpoint!==null)$checkpoint();
                if(microtime(true)>=$until)throw new RuntimeException('recovery_required');
                $candidate=self::identity($pid);
                if($candidate!==null&&$candidate['argv']!==$parent['argv']){$proof=$candidate;$publish(['actuator'=>$proof]);break;}
                usleep(1000);$status=proc_get_status($p);
            }
            if(!$status['running'])$exit=$status['exitcode'];
            while($status['running']){
                if($checkpoint!==null)$checkpoint();
                $raw=self::readPipes($pipes,$raw);$status=proc_get_status($p);
                if(!$status['running']){$exit=$status['exitcode'];break;}
                if(microtime(true)>=$until||strlen($raw)>65536){self::killTree($proof);break;}
                usleep(50000);
            }
        }catch(Throwable $error){$unknown=true;throw $error;
        }finally{
            if(is_resource($p)){
                $status=proc_get_status($p);
                if($status['running']){
                    // Reuse the existing inputActuator resource-custody rule.
                    // This cannot authorize signals to a looked-up PID/tree.
                    $unknown=true;@proc_terminate($p,9);
                }elseif($exit<0)$exit=$status['exitcode'];
                $raw=self::readPipes($pipes,$raw);foreach($pipes as $f)if(is_resource($f))fclose($f);$exit=self::closeProcess($p,$exit);
            }
            if($unknown){
                // Reaping this resource alone says nothing about descendants,
                // original service state or restoration. Preserve the proof.
                $publish(['actuator_attention'=>['reason'=>'recovery_required','intent'=>$intent,'resource_pid'=>$pid,'resource_reaped'=>is_resource($p)===false]]);
            }else $publish(['actuator'=>null,'actuator_intent'=>null]);
        }
        return ['status'=>$exit,'output'=>substr($raw,0,65536)];
    }
    /** Caller holds the existing picker engine.lock and mutation writer.
     * Trusted leaf workers only: no children, no network work until a complete
     * stdin document and the recorded job/identity have been verified. Register
     * before writing, so the independent guard retains cleanup authority even
     * when this parent dies. A partial/empty document must never activate work. */
    private function inputActuator(array $argv,int $seconds,string $input,?callable $checkpoint):array
    {
        if(strlen($input)>8192||$seconds<1||$seconds>90||$checkpoint===null)throw new RuntimeException('invalid_request');
        $checkpoint();$job=$this->store->read();if(($job['actuator_attention']??null)!==null||($job['actuator_intent']??null)!==null)throw new RuntimeException('recovery_required');$id=$job['id']??null;
        if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id)||!is_string($job['phase']??null))throw new RuntimeException('invalid_request');
        if(($job['actuator']??null)!==null)throw new RuntimeException('busy');
        $now=static function():float{$t=hrtime();return $t[0]+$t[1]/1e9;};$deadline=$now()+$seconds;
        $pipes=[];$p=null;$proof=null;$exit=-1;$raw='';$sent=0;
        try{
            // The source-owned parent and CGI leaf use the same application directory.
            // Inherit it so CGI startup cannot invalidate the registered cwd.
            $p=@proc_open($argv,[0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes,null,
                ['PATH'=>NfqwsPlatform::native()?'/usr/sbin:/usr/bin:/sbin:/bin':'/opt/bin:/usr/bin:/bin','LANG'=>'C','HOME'=>'/'],['bypass_shell'=>true]);
            if(!is_resource($p))throw new RuntimeException('launch_failed');
            foreach($pipes as $f)stream_set_blocking($f,false);
            $status=proc_get_status($p);$pid=$status['pid'];
            // A just-forked child can still expose an empty/pre-exec cmdline.
            // Keep stdin closed to work until the exact expected argv is live.
            while($status['running']){
                $checkpoint();if($now()>=$deadline)throw new RuntimeException('timed_out');
                $candidate=self::identity($pid);
                if($candidate!==null&&$candidate['argv']===$argv){$proof=$candidate;break;}
                usleep(1000);$status=proc_get_status($p);
            }
            if(!$status['running'])$exit=$status['exitcode'];
            if($proof!==null){
                $current=$this->store->read();
                if(($current['id']??null)!==$id||($current['actuator']??null)!==null)throw new RuntimeException('stale_state');
                $this->phase($current['phase'],['actuator'=>$proof]);
            }
            while($status['running']){
                $checkpoint();if($now()>=$deadline)throw new RuntimeException('timed_out');
                $raw=self::readPipes([$pipes[1],$pipes[2]],$raw);
                if(strlen($raw)>65536)throw new RuntimeException('output_limit');
                $status=proc_get_status($p);
                if(!$status['running']){
                    // Keep the first observed exit code; status may consume it.
                    $exit=$status['exitcode'];$raw=self::readPipes([$pipes[1],$pipes[2]],$raw);
                    if(strlen($raw)>65536)throw new RuntimeException('output_limit');
                    break;
                }
                if(isset($pipes[0])){
                    // No bytes are sent until the durable actor write above.
                    if($sent<strlen($input)){
                        $n=@fwrite($pipes[0],substr($input,$sent));
                        if($n===false){$s=proc_get_status($p);if($s['running'])throw new RuntimeException('launch_failed');$exit=$s['exitcode'];break;}
                        $sent+=$n;
                    }
                    if($sent===strlen($input)){fclose($pipes[0]);unset($pipes[0]);}
                }
                usleep(20000);
            }
            $raw=self::readPipes([$pipes[1],$pipes[2]],$raw);
            if(strlen($raw)>65536)throw new RuntimeException('output_limit');
        }finally{
            if(is_resource($p)){
                // proc_open owns this exact leaf; no PID/group lookup or other
                // session is signalled. Keep the journal proof until reaped.
                $s=proc_get_status($p);
                if($s['running'])@proc_terminate($p,9);elseif($exit<0)$exit=$s['exitcode'];
                foreach($pipes as $f)if(is_resource($f))fclose($f);
                $exit=self::closeProcess($p,$exit);
                if($proof!==null){
                    $current=$this->store->read();
                    if(($current['id']??null)===$id&&($current['actuator']??null)===$proof)
                        $this->phase($current['phase'],['actuator'=>null]);
                }
            }
        }
        return ['status'=>$exit,'output'=>$raw];
    }
    private function customSupervisor():NfqwsStrategyPickerCustomSupervisor
    {
        require_once __DIR__.'/strategy-picker-custom-supervisor.php';
        return new NfqwsStrategyPickerCustomSupervisor($this->store,fn()=>$this->customCheckpoint(),
            fn(array $argv,int $seconds,string $input,callable $check)=>$this->actuator($argv,$seconds,$input,$check));
    }
    private function customContext():array{return AsusDpiWorker::context();}
    private function service(string $action):void
    {
        $raw=$this->config->raw(true);$sha=hash('sha256',$raw);$j=$this->store->read();$id=$j['id']??null;$guard=null;$guardPin=null;$trial=$j['engine_trial']??null;$profile=null;$metadataPin=null;$lib=null;
        $base=NfqwsDeviceProfilesPaths::readPath(NfqwsPlatform::settings()['config'].'/strategy-picker/'.$id);
        if($trial!==null){
            $keys=is_array($trial)?array_keys($trial):[];sort($keys);
            if($keys!==['config_sha256','guard','guard_pin','metadata','profile','state']||!in_array($trial['state'],['starting','running'],true)||$trial['config_sha256']!==$sha)throw new RuntimeException('recovery_required');
            if($action==='start')throw new RuntimeException('busy');
        }
        if($action==='start'||$trial!==null){
            if(!is_string($id)||preg_match('/^[a-f0-9]{32}$/D',$id)!==1)throw new RuntimeException('invalid_state');
            $guard=$this->actor('guard',$id,$guardPin);if($guard===null)throw new RuntimeException('guard_lost');
        }
        $profileId=$trial['profile']??($j['trial_profile']??null);
        if($trial!==null||$action==='start'&&str_contains($raw,$base.'/')){
            if(!is_string($profileId)||!preg_match('/^(stock|saved-[a-f0-9]{16})$/D',$profileId)||!str_contains($raw,$base.'/'.$profileId.'/'))throw new RuntimeException('source_changed');
            $lib=$this->library();$profile=$lib->entry($profileId,$metadataPin);
            if(($profile['resource_binding_version']??null)!==1||!is_array($profile['resource_directories']??null))throw new RuntimeException('source_changed');
            if($trial!==null&&($trial['metadata']!==$metadataPin||$trial['guard']!==$guard||$trial['guard_pin']!==$guardPin))throw new RuntimeException('source_changed');
        }
        $check=function()use($action,$id,$guard,$guardPin,$sha,&$trial,$lib,$profile,$metadataPin):void{
            if(hash('sha256',$this->config->raw(true))!==$sha)throw new RuntimeException('source_changed');$current=$this->store->read();
            if(($current['id']??null)!==$id||($current['engine_trial']??null)!==$trial)throw new RuntimeException('source_changed');
            if($action==='start'||$guard!==null){
                $actual=$this->actor('guard',$id,$actualPin);if($actual===null)throw new RuntimeException('guard_lost');
                if($actual!==$guard||$actualPin!==$guardPin)throw new RuntimeException('source_changed');
            }
            if($profile!==null&&($lib->entry($profile['id'],$actualMetadataPin)!==$profile||$actualMetadataPin!==$metadataPin))throw new RuntimeException('source_changed');
        };
        $observe=function(bool $running)use($base,$profile,$check):array{
            $check();$job=$this->store->read();$out=[];$total=0;$fields=array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']);$stable=array_flip(['dev','ino','mode','uid','gid','nlink']);$parents=array_flip(['dev','ino','mode','uid','gid']);$reader=NfqwsDeviceProfilesPaths::reader($base,$this->store->owner());
            if(!is_array($job['mutable_resources'][$profile['id']]??[]))throw new RuntimeException('source_changed');
            foreach($profile['files']as $relative=>$sha){
                $mutable=in_array($relative,$profile['mutable_files'],true);$created=$profile['resource_bindings'][$relative];$expected=$mutable?($job['mutable_resources'][$profile['id']][$relative]??null):['identity'=>$created['identity'],'sha256'=>$sha];
                if(!is_array($expected)||!is_array($expected['identity']??null)||!is_string($expected['sha256']??null))throw new RuntimeException('source_changed');
                $path=NfqwsDeviceProfilesPaths::guard(dirname($base.'/'.$profile['id'].'/'.$relative),basename($relative),$this->store->owner());clearstatcache(true,dirname($path));
                if(array_intersect_key(lstat(dirname($path)),$parents)!==$created['parent'])throw new RuntimeException('source_changed');$pin=array_intersect_key($reader->stat($path)??[],$fields);
                if($running&&$mutable){if(array_intersect_key($pin,$stable)!==array_intersect_key($created['identity'],$stable))throw new RuntimeException('source_changed');}
                elseif($pin!==$expected['identity'])throw new RuntimeException('source_changed');
                $bytes=$reader->bytes($path,262144);if(($total+=strlen($bytes))>2097152)throw new RuntimeException('output_limit');
                if(array_intersect_key($reader->stat($path)??[],$fields)!==$pin||!($running&&$mutable)&&hash('sha256',$bytes)!==$expected['sha256'])throw new RuntimeException('source_changed');
                if($mutable)$out[$relative]=['identity'=>$pin,'sha256'=>hash('sha256',$bytes)];
            }
            $check();return $out;
        };
        $publish=function(?array $nextTrial,?array $observed=null)use(&$trial,$profile,$check):void{
            $check();$old=$this->store->read('state.json',$pin);$next=$old;$next['engine_trial']=$nextTrial;if($observed!==null)$next['mutable_resources'][$profile['id']]=$observed;
            if($this->store->read('state.json',$actualPin)!==$old||$actualPin!==$pin)throw new RuntimeException('source_changed');$this->store->write($next);$trial=$nextTrial;$check();
        };
        $check();
        if($action==='start'&&$profile!==null){
            if(array_key_exists('resources_sha256',$j)&&$this->resourcesFingerprint()!==$j['resources_sha256'])throw new RuntimeException('source_changed');$observe(false);
            // The same source-created copy may learn only during this actual
            // guarded service cycle. A record alone never adopts an old write.
            $publish(['profile'=>$profile['id'],'metadata'=>$metadataPin,'config_sha256'=>$sha,'guard'=>$guard,'guard_pin'=>$guardPin,'state'=>'starting']);
        }
        $r=$this->actuator(NfqwsPlatform::serviceCommand($action),60,null,$check,true);$check();
        if($r['status']!==0){$this->phase($this->store->read()['phase'],['service_failure'=>['action'=>$action,'reason'=>'command_exit','status'=>$r['status'],'output'=>$r['output']]]);throw new RuntimeException('service_'.$action.'_failed');}
        if($action==='start'){
            for($i=0;$i<10;$i++){
                $check();$r=NfqwsPlatform::run(NfqwsPlatform::serviceCommand('diagnostics'),8);$check();$d=json_decode(implode("\n",$r['output']),true);
                if(($d['process_running']??false)===true&&($d['nfqueue']['state']??null)==='bound'){
                    if($trial!==null){$next=$trial;$next['state']='running';$publish($next);}$check();return;
                }
                usleep(500000);
            }
            throw new RuntimeException('service_check_failed');
        }
        if($action==='stop'&&$this->running()){$this->phase($this->store->read()['phase'],['service_failure'=>['action'=>'stop','reason'=>'still_running','status'=>0,'output'=>$r['output']]]);throw new RuntimeException('service_stop_failed');}
        if($action==='stop'&&$trial!==null){
            // Accept only stable same-copy AUTO after the fixed controller has
            // actually stopped it; retain the trial on uncertain observations.
            $observed=$observe(true);$current=$this->store->read();if(array_key_exists('resources_sha256',$current)&&$this->resourcesFingerprint()!==$current['resources_sha256'])throw new RuntimeException('source_changed');$publish(null,$observed);
        }
        $check();
    }
    public function status():array
    {
        $j=$this->store->read();$active=in_array($j['state']??null,self::ACTIVE,true);$available=['installed'=>false,'available'=>false];$budget=null;$error=null;
        try{
            // Admission verified the binary under the shared writer. While the
            // operation owns it, polling must not hash it again on a weak CPU.
            if($active)$available=['installed'=>true,'available'=>true,'verification'=>'admission','verified_at'=>$j['started_at']??null];
            else{$installer=new AsusDpiInstaller();$available=$installer->installed()+$installer->availability();}
            $budget=$this->budget();
        }catch(Throwable $e){$error=self::error($e);}
        $public=$j===null?null:array_intersect_key($j,array_flip(['id','state','phase','current_name','started_at','finished_at','request_id','running_before','restored','profiles','skipped','winner','code','budget','extended','goal','progress','dns','original_sha256','applied_sha256','search','matrix','generation','generated','torrent_sites','custom_hosts','custom_only','concurrency','rounds','series']));
        if($public!==null){
            $public['measured_results']=[];
            foreach($j['measured_results']??[]as $item)$public['measured_results'][]=
                array_intersect_key($item,array_flip(['id','number','round','name','sample_type']))+
                ['document_available'=>is_array($item['document']??null)];
            if($active&&isset($j['series']))$public['progress']=min(99,(int)floor(100*($j['series']['completed']+($j['progress']??0)/100)/$j['series']['total']));
            $public['can_restart']=$this->recoveredStopArchivable($j);
            if($active&&array_key_exists('deadline',$j)&&$j['deadline']===null){
                NfqwsStrategyPickerBudget::overallDeadline($j);
                $public['remaining_seconds']=null;$public['elapsed_seconds']=max(0,(int)floor(AsusUpdateStore::uptime()-$j['started_uptime']));
            }
            elseif($active&&is_numeric($j['deadline']??null)&&is_int($j['budget']['deadline_seconds']??null)){
                $public['remaining_seconds']=max(0,(int)ceil((float)$j['deadline']-AsusUpdateStore::uptime()));
                $public['elapsed_seconds']=max(0,$j['budget']['deadline_seconds']-$public['remaining_seconds']);
            }
            foreach($public['profiles']as &$p)unset($p['variant']);unset($p);
            $seed=$j['state']==='completed'&&($j['winner']??null)!==null?$this->store->read('winner-auto.json'):null;
            $public['can_apply']=$seed!==null&&($seed['id']??null)===$j['id']&&($seed['winner']??null)===$j['winner']&&is_array($seed['files']??null)&&($j['restored']??false);
            $generated=$j['state']==='completed'&&($j['generated']??null)!==null?$this->store->read('generated-auto.json'):null;
            $public['can_export']=$generated!==null&&($generated['id']??null)===$j['id']&&($generated['generated']??null)===$j['generated']&&is_array($generated['files']??null)&&($j['restored']??false)&&($j['generation']['verified']??false);
            try{
                $public['concurrency_choice']=NfqwsStrategyPickerConcurrency::job($j);
                NfqwsStrategyPickerConcurrency::verifyRuns($j,$j['profiles']);$public['concurrency_valid']=true;
            }catch(Throwable $e){
                $public['concurrency_choice']=null;$public['concurrency_valid']=false;
                $public['can_apply']=false;$public['can_export']=false;
                if(isset($public['generation']))$public['generation']['verified']=false;
            }
            if($j['state']==='completed'&&($j['search']??null)==='synthesis'&&($public['can_export']||$public['can_apply'])){
                try{$this->synthesisVerifiedProfile($j['generated']??'',(bool)$public['can_apply']);}
                catch(Throwable $e){$public['can_apply']=false;$public['can_export']=false;$public['generation']['verified']=false;}
            }
            $public['can_add_torrent_sites']=false;
            if($public['can_export'])foreach($j['profiles']as $p)if($p['id'].':'.($p['recipe']??'')===$j['generated']){
                try{NfqwsStrategySynthesis::torrentSites($p['variant']??[],$p['components']??[]);$public['can_add_torrent_sites']=true;}
                catch(RuntimeException $e){/* Older reports remain exportable without this optional extension. */}
            }
        }
        $generator=$budget===null?null:NfqwsStrategySynthesis::matrix($budget);if($generator!==null)unset($generator['initial']);
        $customCapability=['available'=>false,'code'=>'unsupported_runtime'];
        if($budget!==null)try{
            $stock=array_values(array_filter(array_map('trim',explode("\n",AsusDpiOptions::metadata()['files']['domains.txt'])),fn($line)=>$line!==''&&!str_starts_with($line,'#')));
            $customBudget=NfqwsStrategyPickerBudget::custom(NfqwsStrategyPickerBudget::coverDomains($budget,count(NfqwsStrategyPickerGoals::probeDomains($stock,'all'))),10);
            $customCapability=['available'=>true,'budget'=>$customBudget,'scope'=>'all_controls'];
        }catch(Throwable $e){$customCapability=['available'=>false,'code'=>self::error($e)];}
        return ['experimental'=>true,'detector'=>$available,'budget'=>$budget,'generator'=>$generator,'custom_capability'=>$customCapability,'error'=>$error,'active'=>$active,'job'=>$public,'metrics'=>NfqwsStrategyPickerMetrics::sample()];
    }
    private function phase(string $phase,array $extra=[]):void
    {
        $j=$this->store->read();$stats=[];
        foreach(['work'=>'worker','guard'=>'guard']as $actor=>$label){
            $proof=$this->store->read('actor-'.$actor.'.json');
            if(($proof['id']??null)===$j['id']&&($proof['identity']['pid']??null)===getmypid())$stats['last_'.$label.'_memory']=['pid'=>getmypid(),'phase'=>$phase,'peak'=>memory_get_peak_usage(true)];
        }
        $this->store->write(array_replace($j,['phase'=>$phase],$stats,$extra));
    }
    private function launch(string $mode,string $id):void
    {
        $bb=NfqwsPlatform::busybox();
        $php=NfqwsPlatform::translate('/opt/bin/php-cgi');
        $unused=$this->store->path('unused-'.$mode.'-'.$id.'.pid');
        if(file_exists($unused))throw new RuntimeException('invalid_state');
        $r=NfqwsPlatform::run([$bb,'start-stop-daemon','-S','-b','-p',$unused,'-x',$php,'--','-d','register_argc_argv=1','-d','max_execution_time=0','-d','max_input_time=0','-d','memory_limit=64M','-q','-f',__FILE__,'--',$mode,$id],5);
        if($r['status']!==0)throw new RuntimeException('launch_failed');
    }
    private function launchPair(string $id):void
    {
        $this->launch('guard',$id);
        for($i=0;$i<50&&$this->actor('guard',$id)===null;$i++)usleep(100000);
        if($this->actor('guard',$id)===null)throw new RuntimeException('launch_failed');
        $this->launch('work',$id);
    }
    private function preflight():void
    {
        if(!(new AsusDpiInstaller())->installed()['installed'])throw new RuntimeException('not_installed');
        if((new AsusDpiJobs())->active()!==null)throw new RuntimeException('busy');
        (new AsusDpiTerminalLifecycle())->idle(fn()=>null);
        $s=new NfqwsDeviceProfilesState(NfqwsPlatform::settings()['web_config'].'/device-profiles-lab');
        if(($s->read('active.json')['draft']['mode']??'common')!=='common')throw new RuntimeException('split_mode_active');
        if((new AsusSmartDnsStore())->status()['state']!=='idle'&&in_array((new AsusSmartDnsStore())->status()['state'],['validating','applying','awaiting_confirmation','rolling_back','conflict'],true))throw new RuntimeException('busy');
        $mode=NfqwsStrategyPickerMode::read($this->config->raw());
        if(!in_array(strtolower($mode),['auto','list'],true))throw new RuntimeException('all_mode_not_supported');
        if(disk_free_space(dirname($this->store->root))<33554432)throw new RuntimeException('insufficient_space');
    }
    private function resourcesFingerprint():string
    {
        // Candidate profiles use their own copied AUTO. The original resource
        // tree, including AUTO, has no implicit permission to change meanwhile.
        $owner=$this->store->owner();
        $root=NfqwsDeviceProfilesPaths::readPath($this->store->configDirectory);
        $reader=NfqwsDeviceProfilesPaths::reader($root,$owner);
        $resources=new AsusShareResources($root,$owner,AsusShareResources::packageLua('/opt',$owner),$reader);
        $inventory=$resources->inventory();
        if($inventory['scan_truncated'])throw new RuntimeException('output_limit');
        $files=[];$pins=[];$directories=[];
        $fields=array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']);
        $directoryFields=array_flip(['dev','ino','mode','uid','gid']);
        foreach(['','/lists','/lua','/lua/imported','/blobs','/blobs/imported']as $suffix){
            $path=$root.$suffix;clearstatcache(true,$path);$s=@lstat($path);
            if($s===false){$directories[$path]=null;continue;}
            if(!$reader->directory($path))throw new RuntimeException('source_changed');
            $directories[$path]=array_intersect_key($s,$directoryFields);
        }
        foreach($inventory['files']as $row){
            $name=$row['kind'].'/'.$row['name'];
            if(NfqwsResourcePaths::relative($name)===null||$row['state']!=='available')throw new RuntimeException('source_changed');
            // Observe original data through the bounded reader. A readable
            // retained list may have permissions that prohibit panel writes.
            $path=$root.'/'.$name;
            $pin=array_intersect_key($reader->stat($path)??[],$fields);
            if(count($pin)!==9)throw new RuntimeException('source_changed');
            $raw=$reader->bytes($path,AsusShareResources::FILE_LIMIT);
            if(array_intersect_key($reader->stat($path)??[],$fields)!==$pin||
                strlen($raw)!==$row['byte_length']||hash('sha256',$raw)!==$row['sha256'])throw new RuntimeException('source_changed');
            $files[$name]=['sha256'=>$row['sha256'],'identity'=>$pin];$pins[$path]=$pin;
        }
        if($resources->inventory()!==$inventory)throw new RuntimeException('source_changed');
        foreach($pins as $path=>$pin)if(array_intersect_key($reader->stat($path)??[],$fields)!==$pin)throw new RuntimeException('source_changed');
        foreach($directories as $path=>$pin){
            clearstatcache(true,$path);$s=@lstat($path);
            if($pin===null?$s!==false:($s===false||!$reader->directory($path)||array_intersect_key($s,$directoryFields)!==$pin))throw new RuntimeException('source_changed');
        }
        ksort($files);return hash('sha256',json_encode(['mode'=>'observed-original-resources-v1',
            'files'=>$files,'directories'=>$directories,'skipped'=>$inventory['skipped']],JSON_THROW_ON_ERROR));
    }
    private function planSelection(array $selection):array
    {
        $budget=$this->budget();
        $stock=array_values(array_filter(array_map('trim',explode("\n",AsusDpiOptions::metadata()['files']['domains.txt'])),fn($line)=>$line!==''&&!str_starts_with($line,'#')));
        $domains=NfqwsStrategyPickerGoals::probeDomains($stock,$selection['goal']);$budget=NfqwsStrategyPickerBudget::coverDomains($budget,count($domains));
        $requested=$selection['concurrency']??'auto';
        $choice=NfqwsStrategyPickerConcurrency::plan($requested,$budget,$requested==='auto'?[]:NfqwsStrategyPickerConcurrency::readFacts());
        $budget=$choice['budget'];
        if(isset($selection['custom_hosts']))$budget=NfqwsStrategyPickerBudget::custom($budget,count($selection['custom_hosts']));
        return ['selection'=>$selection,'concurrency_choice'=>NfqwsStrategyPickerConcurrency::record($choice),'budget'=>$budget,'probe_domains'=>$domains];
    }
    private function planBinding(array $plan):string
    {
        return NfqwsStrategyPickerConcurrency::binding($plan['selection'],$plan['budget'],$plan['concurrency_choice'],
            hash('sha256',$this->config->raw()),$this->resourcesFingerprint(),hash('sha256',trim((string)file_get_contents('/proc/sys/kernel/random/boot_id'))));
    }
    public function previewPlan(array $selection):array
    {
        if(($selection['search']??null)==='synthesis'&&($selection['rounds']??1)<2)throw new RuntimeException('invalid_request');
        if($this->active())throw new RuntimeException('busy');
        if(($this->store->read()['state']??null)==='recovery_required'&&!$this->recoveredStopArchivable($this->store->read()))throw new RuntimeException('recovery_required');
        $plan=$this->planSelection($selection);$plan['plan_sha256']=$this->planBinding($plan);
        unset($plan['probe_domains']);return ['available'=>true,'version'=>'picker-start-plan-v1']+$plan;
    }
    public function start(string $request,bool $extended=false,string $goal='all',bool $synthesis=false,?array $custom=null,mixed $concurrency='auto',?string $planSha=null,mixed $rounds=null,?string $window=null):array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$request))throw new RuntimeException('invalid_request');
        if($window!==null&&!preg_match('/^[a-f0-9]{32}$/D',$window))throw new RuntimeException('invalid_request');
        if($planSha!==null&&!preg_match('/^[a-f0-9]{64}$/D',$planSha))throw new RuntimeException('invalid_request');
        $selection=NfqwsStrategyPickerRequest::selection($extended,$goal,$synthesis,$custom,$concurrency,$rounds??($synthesis?'2':'1'));$goal=$selection['goal'];
        $admissionLease=null;$lease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();$lock=$this->store->lock();
        try{return (new AsusImportTransaction())->writer(function()use($request,$extended,$goal,$synthesis,$custom,$concurrency,$rounds,$selection,$planSha,$window,&$j,&$admissionLease){
            $old=$this->store->read();
            // An old request without a count retains its recorded identity.
            // Only the exact same-request retry can return before the new minimum.
            if($rounds===null&&($old['request_id']??null)===$request)
                $selection=NfqwsStrategyPickerRequest::selection($extended,$goal,$synthesis,$custom,$concurrency,(string)($old['rounds']??1));
            if(NfqwsStrategyPickerRequest::retry($old,$request,$selection))return $this->status();
            if($synthesis&&($selection['rounds']??1)<2)throw new RuntimeException('invalid_request');
            if($this->active())throw new RuntimeException('busy');
            if(($old['state']??null)==='recovery_required'&&!$this->recoveredStopArchivable($old))throw new RuntimeException('recovery_required');
            $this->preflight();$plan=$this->planSelection($selection);$budget=$plan['budget'];$domains=$plan['probe_domains'];$choice=$plan['concurrency_choice'];
            if($planSha!==null&&!hash_equals($planSha,$this->planBinding($plan)))throw new RuntimeException('plan_changed');
            $admissionLease=(new NfqwsStrategyPickerAdmission())->enter($request,NfqwsStrategyPickerRequest::digest($selection),$planSha);
            $this->clearPrevious($old);$memory=$synthesis?$this->synthesisMemory($this->synthesisHistoryRecipes($goal,$selection),$selection,$this->synthesisExplored):null;
            $j=$this->config->snapshot($this->running());$j['library_namespace']='job-v1';if($memory!==null)$j['synthesis_memory']=$memory;
            $j+=['request_id'=>$request,'extended'=>$extended,'search'=>$synthesis?'synthesis':'profiles','goal'=>$goal,'probe_domains'=>$domains,'budget'=>$budget,'deadline'=>null,'started_uptime'=>AsusUpdateStore::uptime(),'progress'=>0,'resources_sha256'=>$this->resourcesFingerprint()];
            $j+=$selection+['selection_sha256'=>NfqwsStrategyPickerRequest::digest($selection),'concurrency_choice'=>$choice];
            if(file_exists($this->store->path('cancel-'.$j['id'])))throw new RuntimeException('source_changed');
            if($window!==null){$j['window_id']=$window;$this->store->openBrowser($j);}
            if($planSha!==null)$j['plan_sha256']=$planSha;$this->store->write($j);
            if($admissionLease!==null)$admissionLease->accepted($j['id']);
            $this->launchPair($j['id']);return $this->status();
        });}catch(Throwable $e){
            if(isset($j)&&($this->store->read()['id']??null)===$j['id']){
                $this->assertOriginal();$this->phase('complete',['state'=>'failed','code'=>self::error($e),'restored'=>true,'finished_at'=>time()]);
            }
            throw $e;
        }finally{if($admissionLease!==null)$admissionLease->release();flock($lock,LOCK_UN);fclose($lock);flock($lease,LOCK_UN);fclose($lease);}
    }
    public function cancel(string $id):array
    {
        $j=$this->store->read();if(($j['id']??null)!==$id)throw new RuntimeException('stale_state');
        if(in_array($j['state'],self::ACTIVE,true)){$p=$this->store->path('cancel-'.$id);$mask=umask(0077);try{$f=@fopen($p,'xb');if($f)fclose($f);}finally{umask($mask);}}
        return $this->status();
    }
    private function checkpoint():void
    {
        $j=$this->store->read();if(($j['actuator_attention']??null)!==null||($j['actuator_intent']??null)!==null)throw new RuntimeException('recovery_required');if($this->actor('guard',$j['id'])===null)throw new RuntimeException('guard_lost');if($this->stopRequested($j))throw new RuntimeException('cancelled');
        $deadline=NfqwsStrategyPickerBudget::overallDeadline($j);if($deadline!==null&&AsusUpdateStore::uptime()>=$deadline)throw new RuntimeException('timed_out');
        NfqwsStrategyPickerConcurrency::admit($j,false);
        if(hash('sha256',$this->config->raw(true))!==$j['current'])throw new RuntimeException('source_changed');
    }
    private function stopRequested(array $job):bool
    {
        return file_exists($this->store->path('cancel-'.$job['id']))||$this->store->browserState($job)==='closed';
    }
    /** Do not switch strategies if the starting window closed before acknowledging Start. */
    private function awaitBrowser(array $job):bool
    {
        if(!isset($job['window_id']))return true;
        do{
            $state=$this->store->browserState($job);
            if($this->actor('guard',$job['id'])===null)throw new RuntimeException('guard_lost');
            if($state==='closed'||file_exists($this->store->path('cancel-'.$job['id']))){
                if($this->running()!==$job['running_before'])throw new RuntimeException('service_state_unknown');
                $this->assertOriginal();
                $this->phase('complete',['state'=>'cancelled','code'=>'cancelled','restored'=>true,'finished_at'=>time()]);
                return false;
            }
            if($state==='present')return true;
            usleep(200000);
        }while(true);
    }
    private function library():NfqwsDeviceProfilesLibrary
    {
        $j=$this->store->read();$parent=dirname($this->store->profileRoot($j['id']));
        if(!file_exists($parent)){
            NfqwsDeviceProfilesPaths::guard(dirname($parent),basename($parent));
            $mask=umask(0077);try{if(!mkdir($parent,0755)||!chmod($parent,0755))throw new RuntimeException('storage_unavailable');}finally{umask($mask);}
        }
        return $this->store->profileLibrary($j);
    }
    private function clearPrevious(?array $old):void
    {
        $j=$this->store->read('state.json',$journalPin);
        if($j!==$old)throw new RuntimeException('source_changed');
        $id=$j['id']??null;
        $recoveredStop=$this->recoveredStopArchivable($j);
        $fresh=$recoveredStop||in_array($j['state']??null,['completed','failed','cancelled','interrupted'],true)&&($j['restored']??false)===true;
        $intent=$j['actuator_intent']??null;$attention=$j['actuator_attention']??null;
        $copyRetirement=$fresh&&is_string($id)&&preg_match('/^[a-f0-9]{32}$/D',$id)&&
            is_array($intent)&&count($intent)===3&&($intent['kind']??null)==='picker-stage-retirement-v1'&&($intent['job']??null)===$id&&
            is_array($intent['profiles']??null)&&array_is_list($intent['profiles'])&&count($intent['profiles'])<=9&&
            ($attention===null||is_array($attention)&&count($attention)===2&&($attention['kind']??null)==='picker-stage-retirement-uncertain'&&($attention['job']??null)===$id);
        if($copyRetirement)foreach($intent['profiles']as $profile)if(!is_string($profile)||!preg_match('/^(?:stock|saved-[a-f0-9]{16})$/D',$profile))$copyRetirement=false;
        if(($attention!==null||$intent!==null)&&!$copyRetirement&&!$recoveredStop)throw new RuntimeException('recovery_required');
        if(isset($j['library_namespace'])&&$j['library_namespace']!=='job-v1')throw new RuntimeException('invalid_state');
        $private=NfqwsDeviceProfilesPaths::readPath(isset($j['library_namespace'])?$this->store->root.'/job-'.$id:$this->store->root);
        $dir=$private.'/library';
        if($j===null){
            // A first start has no Config journal until the following snapshot.
            // An orphaned profile library still needs recovery, never deletion.
            clearstatcache(true,$dir);if(@lstat($dir)!==false)throw new RuntimeException('recovery_required');
            if($this->store->read('state.json',$actualPin)!==null||$actualPin!==$journalPin)throw new RuntimeException('source_changed');
            return;
        }
        // A restored terminal job describes its past input. A new ordinary
        // request observes today's input, including edits made between runs.
        $baselineConfig=$fresh?$this->config->observe():null;
        $baselineResources=$fresh?$this->resourcesFingerprint():null;
        // Copy-only cleanup attention is archived with the old job. A new
        // restored-terminal request observes today's Config/resources below;
        // it neither restores the old input nor deletes its remaining copies.
        $check=function()use(&$j,&$journalPin,$id,$fresh,$copyRetirement,$recoveredStop,$baselineConfig,$baselineResources):void{
            if($this->store->read('state.json',$actualPin)!==$j||$actualPin!==$journalPin)throw new RuntimeException('source_changed');
            if(!$recoveredStop&&(($j['actuator_attention']??null)!==null&&!$copyRetirement||($j['actuator']??null)!==null||($j['custom_worker']??null)!==null||($j['engine_trial']??null)!==null))throw new RuntimeException('recovery_required');
            if($recoveredStop&&!$this->recoveredStopArchivable($j))throw new RuntimeException('recovery_required');
            if(in_array($j['state']??null,self::ACTIVE,true))throw new RuntimeException('busy');
            if(is_string($id)&&($this->actor('work',$id)!==null||$this->actor('guard',$id)!==null))throw new RuntimeException('busy');
            if($fresh){
                if($this->config->observe()!==$baselineConfig||$this->resourcesFingerprint()!==$baselineResources)throw new RuntimeException('source_changed');
            }else{
                $this->config->raw(true);$resources=($j['state']??null)==='applied'?($j['applied_resources_sha256']??null):($j['resources_sha256']??null);
                if($resources!==null&&$this->resourcesFingerprint()!==$resources)throw new RuntimeException('source_changed');
            }
            if($this->store->read('state.json',$afterPin)!==$j||$afterPin!==$journalPin)throw new RuntimeException('source_changed');
        };
        $check();
        if($fresh){
            // Finish an interrupted sample before its journal becomes history.
            // The existing recovery validates its identity and leaves committed samples alone.
            if(($j['custom_sample_cleanup']??null)!==null)throw new RuntimeException('recovery_required');
            if(($j['custom_sample_pending']??null)!==null){
                $expected=$j;unset($expected['custom_sample_pending']);
                $this->customRecoverPending($id);
                $j=$this->store->read('state.json',$journalPin);
                if($j!==$expected)throw new RuntimeException('source_changed');
                $check();
            }
            // Keep completed measurements and copied resources for another
            // round. Starting a new job never needs to delete the old tree.
            // Copy-only retirement attention stays attached to its old job;
            // it grants no restore, apply, or cleanup authority to the next one.
            $history=new NfqwsStrategyPickerState($this->store->root.'/job-'.$id,$this->store->owner(),$this->store->configDirectory);
            $previous=$history->read();if($previous!==null&&$previous!==$j)throw new RuntimeException('source_changed');
            if($previous===null){$check();$history->write($j);$check();}
            foreach(['winner-auto.json','generated-auto.json']as $name){
                $seed=$this->store->read($name);if($seed===null||($seed['id']??null)!==$id)continue;
                $prior=$history->read($name);if($prior!==null&&$prior!==$seed)throw new RuntimeException('source_changed');
                if($prior===null){$check();$history->write($seed,$name);$check();}
            }
            return;
        }
        $files=[];$metas=[];$tree=[];$entries=[];$base=null;$reader=NfqwsDeviceProfilesPaths::reader($dir,$this->store->owner());
        $fields=array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']);$parentFields=array_flip(['dev','ino','mode','uid','gid']);$stableFields=array_flip(['dev','ino','mode','uid','gid','nlink']);
        $directory=function(string $path,array $names,?array $expected=null)use(&$tree,$parentFields):void{
            NfqwsStrategyPickerResources::directory($path,$this->store->owner());clearstatcache(true,$path);$pin=array_intersect_key(lstat($path),$parentFields);
            if($expected!==null&&$pin!==$expected)throw new RuntimeException('source_changed');sort($names);$actual=array_values(array_diff(scandir($path),['.','..']));sort($actual);
            if($actual!==$names)throw new RuntimeException('source_changed');$tree[$path]=['pin'=>$pin,'names'=>$names];
        };
        clearstatcache(true,$dir);
        if(@lstat($dir)!==false){
            if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('storage_unavailable');
            NfqwsStrategyPickerResources::directory($dir,$this->store->owner());$names=array_values(array_diff(scandir($dir),['.','..']));if(count($names)>9)throw new RuntimeException('output_limit');
            $base=$this->store->profileRoot($id);$canonical=NfqwsDeviceProfilesPaths::readPath($base);$raw=$this->config->raw(true);
            if(str_contains($raw,$base.'/')||str_contains($raw,$canonical.'/'))throw new RuntimeException('source_changed');
            $base=$canonical;
            $lib=$this->store->profileLibrary($j);$parentPin=null;
            foreach($names as $name){
                if(!preg_match('/^(stock|saved-[a-f0-9]{16})\.json$/D',$name,$m))throw new RuntimeException('source_changed');
                $entry=$lib->entry($m[1],$metaPin);
                // Only our actual source entry supplies creation observations.
                // Legacy content hashes and caller copies do not own deletion.
                if(($entry['resource_binding_version']??null)!==1||!is_array($entry['resource_directories']??null))throw new RuntimeException('source_changed');
                $entries[$entry['id']]=$entry;$profile=$base.'/'.$entry['id'];$dirs=$entry['resource_directories'];
                if($parentPin!==null&&$parentPin!==$dirs['..'])throw new RuntimeException('source_changed');$parentPin=$dirs['..'];$children=[];
                foreach($dirs as $relative=>$pin){if($relative==='..')continue;$path=$relative==='.'?$profile:$profile.'/'.$relative;$children[$path]=[];}
                foreach($children as $path=>$unused)if($path!==$profile)$children[dirname($path)][]=basename($path);
                foreach($entry['files']as $relative=>$sha){
                    $created=$entry['resource_bindings'][$relative];$record=['identity'=>$created['identity'],'sha256'=>$sha];
                    if(in_array($relative,$entry['mutable_files'],true)&&array_key_exists($relative,$j['mutable_resources'][$entry['id']]??[]))$record=$j['mutable_resources'][$entry['id']][$relative];
                    $keys=is_array($record)?array_keys($record):[];sort($keys);
                    if($keys!==['identity','sha256']||!is_array($record['identity'])||!is_string($record['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$record['sha256']))throw new RuntimeException('source_changed');
                    $keys=array_keys($record['identity']);sort($keys);if($keys!==['ctime','dev','gid','ino','mode','mtime','nlink','size','uid'])throw new RuntimeException('source_changed');
                    foreach($record['identity']as $value)if(!is_int($value)||$value<0)throw new RuntimeException('source_changed');
                    if(array_intersect_key($record['identity'],$stableFields)!==array_intersect_key($created['identity'],$stableFields))throw new RuntimeException('source_changed');
                    $path=NfqwsDeviceProfilesPaths::guard(dirname($profile.'/'.$relative),basename($relative),$this->store->owner());$pin=array_intersect_key($reader->stat($path)??[],$fields);
                    if($pin!==$record['identity'])throw new RuntimeException('source_changed');$bytes=$reader->bytes($path,262144);
                    if(hash('sha256',$bytes)!==$record['sha256']||array_intersect_key($reader->stat($path)??[],$fields)!==$pin)throw new RuntimeException('source_changed');
                    $files[$path]=['pin'=>$pin,'raw'=>$bytes];$children[dirname($path)][]=basename($path);
                }
                foreach($children as $path=>$members){$relative=$path===$profile?'.':substr($path,strlen($profile)+1);$directory($path,$members,$dirs[$relative]);}
                $path=NfqwsDeviceProfilesPaths::guard($dir,$name,$this->store->owner());$bytes=$reader->bytes($path,262144);
                if(array_intersect_key($reader->stat($path)??[],$fields)!==$metaPin||json_decode($bytes,true,32,JSON_THROW_ON_ERROR)!==$entry)throw new RuntimeException('source_changed');$metas[$path]=['pin'=>$metaPin,'raw'=>$bytes];
            }
            if(array_key_exists('mutable_resources',$j)){
                if(!is_array($j['mutable_resources']))throw new RuntimeException('source_changed');
                foreach($j['mutable_resources']as $profile=>$records){if(!isset($entries[$profile])||!is_array($records)||array_diff(array_keys($records),$entries[$profile]['mutable_files']))throw new RuntimeException('source_changed');}
            }
            $directory($dir,$names);
            if($entries)$directory($base,array_keys($entries),$parentPin);
            elseif(@lstat($base)!==false)throw new RuntimeException('source_changed');
        }
        if(count($files)>2304)throw new RuntimeException('output_limit');
        $verify=function()use(&$tree,&$files,&$metas,$reader,$fields,$parentFields,$check):void{
            $check();foreach($tree as $path=>$record){NfqwsStrategyPickerResources::directory($path,$this->store->owner());clearstatcache(true,$path);$names=array_values(array_diff(scandir($path),['.','..']));sort($names);
                if(array_intersect_key(lstat($path),$parentFields)!==$record['pin']||$names!==$record['names'])throw new RuntimeException('source_changed');}
            foreach($files+$metas as $path=>$record)if(array_intersect_key($reader->stat($path)??[],$fields)!==$record['pin']||$reader->bytes($path,262144)!==$record['raw']||array_intersect_key($reader->stat($path)??[],$fields)!==$record['pin'])throw new RuntimeException('source_changed');$check();
        };
        $verify();
        // Retire custom artifacts only AFTER the entire profile set preflight.
        foreach(['custom_worker','custom_sample_refs','custom_sample_pending','custom_sample_cleanup','custom_sample_attempts','custom_samples_retired']as $field){
            if($old!==null&&array_key_exists($field,$old)){
                require_once __DIR__.'/strategy-picker-custom-samples.php';
                $samples=new NfqwsStrategyPickerCustomSamples($this->store,static function():void{throw new RuntimeException('busy');},null,$this->store->owner());
                $applied=null;
                if(($old['state']??null)==='applied')$applied=function(array $j)use($old):void{
                    if(($j['id']??null)!==$old['id']||$this->actor('work',$j['id'])!==null||$this->actor('guard',$j['id'])!==null)throw new RuntimeException('busy');
                    // Successful Apply is a new baseline, never a reason to
                    // restore the pre-search configuration or delete its kit.
                    if(!preg_match('/^[a-f0-9]{64}$/D',$j['applied_sha256']??'')||
                        !preg_match('/^[a-f0-9]{64}$/D',$j['applied_resources_sha256']??'')||
                        hash('sha256',$this->config->raw())!==$j['applied_sha256']||
                        $this->resourcesFingerprint()!==$j['applied_resources_sha256'])throw new RuntimeException('source_changed');
                };
                $samples->retire($old['id'],$applied);$next=$this->store->read('state.json',$nextPin);$before=$j;$after=$next;
                foreach(['custom_sample_refs','custom_sample_pending','custom_sample_cleanup','custom_samples_retired']as $key){unset($before[$key],$after[$key]);}
                if($before!==$after)throw new RuntimeException('source_changed');$j=$next;$journalPin=$nextPin;break;
            }
        }
        $verify();if(!$entries)return;
        $next=$j;$next['actuator_intent']=['kind'=>'picker-stage-retirement-v1','job'=>$id,'profiles'=>array_keys($entries)];
        $this->store->write($next,'state.json',$nextPin);$j=$next;$journalPin=$nextPin;$possibleInput=false;
        try{
            $verify();$remove=function(string $path,bool $isDirectory=false)use(&$files,&$metas,&$tree,&$possibleInput,$check,$reader,$fields,$parentFields):void{
                $check();$parent=dirname($path);$record=$tree[$parent];NfqwsStrategyPickerResources::directory($parent,$this->store->owner());clearstatcache(true,$parent);
                if(array_intersect_key(lstat($parent),$parentFields)!==$record['pin'])throw new RuntimeException('source_changed');$df=fopen($parent,'r');
                try{
                    if(!$df||array_intersect_key(fstat($df),$parentFields)!==$record['pin'])throw new RuntimeException('source_changed');
                    if($isDirectory){NfqwsStrategyPickerResources::directory($path,$this->store->owner());clearstatcache(true,$path);if(array_intersect_key(lstat($path),$parentFields)!==$tree[$path]['pin']||scandir($path)!==['.','..'])throw new RuntimeException('source_changed');}
                    else{$file=$files[$path]??$metas[$path];if(array_intersect_key($reader->stat($path)??[],$fields)!==$file['pin']||$reader->bytes($path,262144)!==$file['raw']||array_intersect_key($reader->stat($path)??[],$fields)!==$file['pin'])throw new RuntimeException('source_changed');}
                    $check();$possibleInput=true;if(!($isDirectory?rmdir($path):unlink($path)))throw new RuntimeException('storage_unavailable');
                    unset($files[$path],$metas[$path],$tree[$path]);$tree[$parent]['names']=array_values(array_diff($record['names'],[basename($path)]));
                    if(!fsync($df))throw new RuntimeException('storage_unavailable');clearstatcache(true,$parent);$names=array_values(array_diff(scandir($parent),['.','..']));sort($names);
                    if(array_intersect_key(fstat($df),$parentFields)!==$record['pin']||array_intersect_key(lstat($parent),$parentFields)!==$record['pin']||$names!==$tree[$parent]['names'])throw new RuntimeException('source_changed');
                }finally{if(is_resource($df))fclose($df);}$check();
            };
            foreach(array_keys($files)as $path)$remove($path);
            $directories=array_values(array_diff(array_keys($tree),[$dir,$base]));usort($directories,static fn($a,$b)=>strlen($b)<=>strlen($a));foreach($directories as $path)$remove($path,true);
            foreach(array_keys($metas)as $path)$remove($path);
            // The job directory's parent is retained, not recursively cleaned.
            $parent=dirname($base);NfqwsStrategyPickerResources::directory($parent,$this->store->owner());clearstatcache(true,$parent);$tree[$parent]=['pin'=>array_intersect_key(lstat($parent),$parentFields),'names'=>array_values(array_diff(scandir($parent),['.','..']))];sort($tree[$parent]['names']);$remove($base,true);unset($tree[$parent]);
            $verify();$next=$j;unset($next['mutable_resources'],$next['trial_profile']);$next['actuator_intent']=null;$this->store->write($next,'state.json',$nextPin);$j=$next;$journalPin=$nextPin;$verify();
        }catch(Throwable $e){
            if($possibleInput){try{if($this->store->read('state.json',$actualPin)===$j&&$actualPin===$journalPin){$j['actuator_attention']=['kind'=>'picker-stage-retirement-uncertain','job'=>$id];$this->store->write($j);}}catch(Throwable $ignored){/* Preserve the unknown journal and remaining objects. */}}
            throw $e;
        }
    }
    private function stage():array
    {
        $lib=$this->library();$current=$lib->capture('Текущая стратегия');$profiles=[$current+['source'=>'current']];
        try{$stock=$lib->stock();$profiles[]=['id'=>$stock['id'],'name'=>$stock['name'],'source'=>'stock'];}catch(Throwable $e){$this->skip('stock',$e);}
        $catalog=new AsusProfileCatalogTransport();
        try{
            $index=$catalog->catalog();$wanted=['hardcorp74','fake_tls_auto','alt11'];$entries=$index['profiles'];
            $priority=static function($entry)use($wanted){foreach($wanted as $i=>$name)if(str_ends_with($entry['id'],$name)||str_ends_with($entry['id'],str_replace('_','-',$name)))return $i;return 100;};
            usort($entries,fn($a,$b)=>$priority($a)<=>$priority($b));
            $attempted=0;
            foreach($entries as $entry){
                if(count($profiles)>=$this->store->read()['budget']['max_profiles'])break;
                if(($entry['category']??null)!=='global'||$entry['min_build']>$catalog->build())continue;
                if(++$attempted>$this->store->read()['budget']['max_profiles']*2)break;
                $this->checkpoint();
                try{
                    $raw=$catalog->document($entry['id'],$entry['sha256']);
                    // No unattended opt-in to unverified Lua or incomplete dependencies.
                    $profile=$lib->import($entry['id'],$raw,false);
                    $profiles[]=$profile+['source'=>$entry['id']];
                }catch(Throwable $e){$this->skip($entry['id'],$e);}
            }
        }catch(Throwable $e){$this->skip('catalog',$e);}
        return $profiles;
    }
    private function skip(string $id,Throwable $e):void
    {$j=$this->store->read();if(count($j['skipped'])<32)$j['skipped'][]=['id'=>$id,'code'=>self::error($e)];$this->store->write($j);}
    private function candidate(array $entry):string
    {
        $j=$this->store->read();$base=base64_decode($j['original'],true);
        if(!is_string($base))throw new RuntimeException('invalid_state');
        return NfqwsStrategyPickerConfig::candidate($base,$entry['config']);
    }
    private function resetAuto(array $entry):void
    {
        $j=$this->store->read('state.json',$journalPin);
        if(($j['actuator_attention']??null)!==null||($j['actuator_intent']??null)!==null||($j['engine_trial']??null)!==null)throw new RuntimeException('recovery_required');
        $id=$j['id']??null;if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('source_changed');
        $guard=$this->actor('guard',$id,$guardPin);if($guard===null)throw new RuntimeException('guard_lost');
        $this->config->raw(true);
        $base=NfqwsPlatform::settings()['config'].'/strategy-picker/'.$id;NfqwsStrategyPickerResources::directory($base);
        $lib=$this->library();$profile=$lib->entry($entry['id']??'',$metaPin);
        // Creation records are read from our actual private library. Caller
        // entry fields, hashes and flags do not authorize a file mutation.
        if(($profile['resource_binding_version']??null)!==1||!isset($profile['resource_bindings']))throw new RuntimeException('source_changed');
        $reader=NfqwsDeviceProfilesPaths::reader($base,$this->store->owner());$fields=array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']);
        $parentFields=array_flip(['dev','ino','mode','uid','gid']);$stableFields=array_flip(['dev','ino','mode','uid','gid','nlink']);
        $check=function()use(&$j,&$journalPin,$id,$guard,$guardPin,$lib,$profile,$metaPin):void{
            $this->config->raw(true);$v=$this->store->read('state.json',$actualPin);
            if($v!==$j||$actualPin!==$journalPin)throw new RuntimeException('source_changed');
            $actual=$this->actor('guard',$id,$actualGuardPin);
            if($actual===null||$actual!==$guard||$actualGuardPin!==$guardPin)throw new RuntimeException('guard_lost');
            if($lib->entry($profile['id'],$actualMetaPin)!==$profile||$actualMetaPin!==$metaPin)throw new RuntimeException('source_changed');
            if(array_key_exists('resources_sha256',$j)&&$this->resourcesFingerprint()!==$j['resources_sha256'])throw new RuntimeException('source_changed');
            if($this->store->read('state.json',$afterPin)!==$j||$afterPin!==$journalPin)throw new RuntimeException('source_changed');
        };
        $check();$plan=[];$total=0;$seen=[];
        foreach($profile['mutable_files']as $name){
            if(!is_string($name)||!preg_match('~^lists/[A-Za-z0-9_.-]{1,128}$~D',$name)||isset($seen[$name])||
                !isset($profile['files'][$name],$profile['resource_bindings'][$name]))throw new RuntimeException('source_changed');$seen[$name]=true;
            $created=$profile['resource_bindings'][$name];$record=['identity'=>$created['identity'],'sha256'=>$profile['files'][$name]];
            if(array_key_exists('mutable_resources',$j)){
                if(!is_array($j['mutable_resources'])||isset($j['mutable_resources'][$profile['id']])&&!is_array($j['mutable_resources'][$profile['id']]))throw new RuntimeException('source_changed');
                if(array_key_exists($name,$j['mutable_resources'][$profile['id']]??[]))$record=$j['mutable_resources'][$profile['id']][$name];
            }
            $keys=is_array($record)?array_keys($record):[];sort($keys);
            if($keys!==['identity','sha256']||!is_array($record['identity'])||!is_string($record['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$record['sha256']))throw new RuntimeException('source_changed');
            $keys=array_keys($record['identity']);sort($keys);if($keys!==['ctime','dev','gid','ino','mode','mtime','nlink','size','uid'])throw new RuntimeException('source_changed');
            foreach($record['identity']as $value)if(!is_int($value)||$value<0)throw new RuntimeException('source_changed');
            if(array_intersect_key($record['identity'],$stableFields)!==array_intersect_key($created['identity'],$stableFields))throw new RuntimeException('source_changed');
            $path=NfqwsDeviceProfilesPaths::guard(dirname($base.'/'.$profile['id'].'/'.$name),basename($name));clearstatcache(true,dirname($path));
            if(array_intersect_key(lstat(dirname($path)),$parentFields)!==$created['parent'])throw new RuntimeException('source_changed');
            $pin=array_intersect_key($reader->stat($path)??[],$fields);if($pin!==$record['identity'])throw new RuntimeException('source_changed');
            $raw=$reader->bytes($path,262144);if(hash('sha256',$raw)!==$record['sha256']||array_intersect_key($reader->stat($path)??[],$fields)!==$pin)throw new RuntimeException('source_changed');
            if(($total+=strlen($raw))>2097152)throw new RuntimeException('output_limit');$plan[]=['name'=>$name,'path'=>$path,'pin'=>$pin,'raw'=>$raw,'parent'=>$created['parent']];
        }
        $check();$possibleInput=false;
        try{foreach($plan as $file){
            $path=$file['path'];$check();clearstatcache(true,dirname($path));
            if(array_intersect_key(lstat(dirname($path)),$parentFields)!==$file['parent']||array_intersect_key($reader->stat($path)??[],$fields)!==$file['pin']||$reader->bytes($path,262144)!==$file['raw'])throw new RuntimeException('source_changed');
            $f=@fopen($path,'r+be');if(!$f)throw new RuntimeException('storage_unavailable');
            try{
                if(array_intersect_key(fstat($f),$fields)!==$file['pin'])throw new RuntimeException('source_changed');
                $observed=$file['pin'];
                if($file['raw']!==''){
                    $next=$j;$next['actuator_intent']=['kind'=>'picker-auto-reset-v1','job'=>$id,'profile'=>$profile['id'],'file'=>$file['name'],'before_sha256'=>hash('sha256',$file['raw'])];
                    $this->store->write($next,'state.json',$nextPin);$j=$next;$journalPin=$nextPin;$check();
                    if(array_intersect_key(fstat($f),$fields)!==$file['pin']||array_intersect_key($reader->stat($path)??[],$fields)!==$file['pin']||$reader->bytes($path,262144)!==$file['raw'])throw new RuntimeException('source_changed');
                    $possibleInput=true;if(!ftruncate($f,0)||!fflush($f)||!fsync($f))throw new RuntimeException('storage_unavailable');
                    $observed=array_intersect_key(fstat($f),$fields);$expected=$file['pin'];$expected['size']=0;$expected['mtime']=$observed['mtime'];$expected['ctime']=$observed['ctime'];
                    if($observed!==$expected)throw new RuntimeException('source_changed');
                }
                clearstatcache(true,dirname($path));
                if(array_intersect_key(lstat(dirname($path)),$parentFields)!==$file['parent']||array_intersect_key($reader->stat($path)??[],$fields)!==$observed||$reader->bytes($path,262144)!==''||array_intersect_key(fstat($f),$fields)!==$observed)throw new RuntimeException('source_changed');
                $check();$next=$j;$next['mutable_resources'][$profile['id']][$file['name']]=['identity'=>$observed,'sha256'=>hash('sha256','')];
                if($file['raw']!=='')$next['actuator_intent']=null;
                if($next!==$j){$this->store->write($next,'state.json',$nextPin);$j=$next;$journalPin=$nextPin;}
                $check();if(array_intersect_key(fstat($f),$fields)!==$observed||array_intersect_key($reader->stat($path)??[],$fields)!==$observed||$reader->bytes($path,262144)!=='')throw new RuntimeException('source_changed');
            }finally{fclose($f);}
        }
        $check();if(($j['trial_profile']??null)!==$profile['id']){$next=$j;$next['trial_profile']=$profile['id'];$this->store->write($next,'state.json',$nextPin);$j=$next;$journalPin=$nextPin;}$check();
        }catch(Throwable $e){
            // Never clear possible-input authority because a PID disappeared.
            // Mark uncertainty only while the exact journal we wrote is current.
            if($possibleInput){try{
                if($this->store->read('state.json',$actualPin)===$j&&$actualPin===$journalPin){$j['actuator_attention']=['kind'=>'picker-auto-reset-uncertain','job'=>$id];$this->store->write($j);}
            }catch(Throwable $ignored){/* Preserve unknown journal and stage. */}}
            throw $e;
        }
    }

    private function probe(array $groups,?callable $onNative=null,?AsusDpiJobs $jobs=null,?callable $beforeNative=null):array
    {
        if($beforeNative!==null&&$onNative===null)throw new RuntimeException('invalid_request');
        $this->checkpoint();$jobs??=new AsusDpiJobs();$j=$this->store->read();$req=bin2hex(random_bytes(16));
        $custom=$this->synthesisCustom($j);
        $probeDeadline=$custom?AsusUpdateStore::uptime()+NfqwsStrategyPickerBudget::customProbeSeconds($j['budget']):null;
        if($custom)$this->customCheckpoint();
        \NfqwsStrategyPickerConcurrency::admit($j,true);
        $uuid=substr($req,0,8).'-'.substr($req,8,4).'-4'.substr($req,13,3).'-8'.substr($req,17,3).'-'.substr($req,20,12);
        $j['dpi_request']=$uuid;$this->store->write($j);
        $options=['config'=>['IP_VERSION'=>'ipv4','TLS_FINGERPRINT'=>'rustls','MAX_CONCURRENT'=>$j['budget']['concurrency'],'TIMEOUT'=>8],'limits'=>['total_seconds'=>$j['budget']['probe_seconds'],'group_seconds'=>$j['budget']['group_seconds']]];
        if(isset($j['probe_domains']))$options['targets']=['domains'=>$j['probe_domains']];
        if($beforeNative!==null){
            // Trusted INTERNAL collector admission/intent, before startRun can
            // reserve or launch input. Returned data/booleans are no permit.
            if($beforeNative($uuid)!==null)throw new RuntimeException('invalid_request');
            $this->checkpoint();$current=$this->store->read();
            if(($current['id']??null)!==$j['id']||($current['request_id']??null)!==($j['request_id']??null)||
                ($current['boot']??null)!==($j['boot']??null)||($current['phase']??null)!==$j['phase']||
                ($current['dpi_request']??null)!==$uuid||($current['dpi_job']??null)!==($j['dpi_job']??null)||
                ($current['current']??null)!==($j['current']??null)||
                hash('sha256',$this->config->raw())!==($j['current']??null)||
                ($current['resources_sha256']??null)!==($j['resources_sha256']??null)||
                $this->resourcesFingerprint()!==($j['resources_sha256']??null))throw new RuntimeException('source_changed');
        }
        $job=$jobs->startRun($uuid,$groups,[],$options);$this->phase($j['phase'],['dpi_job'=>$job['id']]);
        while(true){
            if($custom)$this->customCheckpoint();else $this->checkpoint();
            if($probeDeadline!==null&&AsusUpdateStore::uptime()>=$probeDeadline)throw new RuntimeException('timed_out');
            $active=$jobs->active();
            if(($active['id']??null)===$job['id']){sleep(1);continue;}
            if($onNative===null)$raw=$jobs->native($job['id']);
            else{
                $snapshot=$jobs->nativeSnapshot($job['id'],$uuid);
                // Preserve the actual source buffers inside the original
                // callback before decoding or parent/context postchecks.
                $onNative($snapshot);$this->checkpoint();$current=$this->store->read();
                if(($current['id']??null)!==$j['id']||($current['request_id']??null)!==($j['request_id']??null)||
                    ($current['dpi_job']??null)!==$job['id']||($current['dpi_request']??null)!==$uuid||
                    ($current['current']??null)!==($j['current']??null)||
                    hash('sha256',$this->config->raw())!==($j['current']??null)||
                    ($current['resources_sha256']??null)!==($j['resources_sha256']??null)||
                    $this->resourcesFingerprint()!==($j['resources_sha256']??null))throw new RuntimeException('source_changed');
                $raw=$snapshot['native']['raw'];
            }
            $native=json_decode($raw,true,32,JSON_THROW_ON_ERROR);
            if(($native['state']??null)!=='completed')throw new RuntimeException('detector_failed');
            \NfqwsStrategyPickerConcurrency::verifyNative($j,$native);
            return $native;
        }
    }
    private function stopOwnedProbe():void
    {
        $j=$this->store->read();$s=(new AsusDpiStore())->status();$active=$s['active'];
        if($active!==null&&($active['request_id']??null)===($j['dpi_request']??null)){
            try{(new AsusDpiJobs())->stop($active['id']);}
            catch(RuntimeException $e){
                if($e->getMessage()!=='interrupted')throw $e;
                // Our caller can die between reserve and attachIdentity. The
                // request-id proof authorizes only this private run's cancel
                // marker; it never authorizes signalling an unverified PID.
                $run=NfqwsPlatform::translate('/opt/var/lib/nfqws2-asus/dpi-detector/runs/').$active['id'];
                if(!is_dir($run)){
                    (new AsusDpiStore())->update($active['id'],['state'=>'interrupted','code'=>'interrupted','finished_at'=>time()]);return;
                }
                $path=NfqwsDeviceProfilesPaths::guard($run,'cancel');$mask=umask(0077);try{$f=@fopen($path,'xb');if($f){fwrite($f,"cancel\n");fclose($f);}}finally{umask($mask);}
            }
            for($i=0;$i<12;$i++){if((new AsusDpiJobs())->active()===null)return;sleep(1);}
            throw new RuntimeException('detector_stop_failed');
        }
    }
    private function restore(bool $boot=false):void
    {
        $j=$this->store->read();$actual=hash('sha256',$this->config->raw(true));
        if(($j['actuator_attention']??null)!==null||($j['actuator_intent']??null)!==null)throw new RuntimeException('recovery_required');
        if(!in_array($actual,$j['known'],true))throw new RuntimeException('source_changed');
        if(array_key_exists('resources_sha256',$j)&&$this->resourcesFingerprint()!==$j['resources_sha256'])throw new RuntimeException('source_changed');
        $cleanup=null;
        $custom=($j['custom_worker']??null)!==null||!$boot&&isset($j['actuator'])||$boot&&
            (array_key_exists('custom_sample_pending',$j)||array_key_exists('custom_sample_refs',$j));
        if($custom)$this->customReap($boot);
        if(!$boot){
            try{$this->stopOwnedProbe();}catch(Throwable $e){$cleanup??='detector_stop_failed';}
            $this->service('stop');
        }
        if(array_key_exists('resources_sha256',$j)&&$this->resourcesFingerprint()!==$j['resources_sha256'])throw new RuntimeException('source_changed');
        $this->config->restore();$this->phase($this->store->read()['phase'],['restored'=>false]);
        if(!$boot&&$j['running_before'])$this->service('start');
        if(array_key_exists('resources_sha256',$j)&&$this->resourcesFingerprint()!==$j['resources_sha256'])throw new RuntimeException('source_changed');
        $this->phase($this->store->read()['phase'],['restored'=>true]);
        if($cleanup!==null)throw new RuntimeException($cleanup);
    }
    public function work(string $id):void
    {
        $lock=null;$lease=null;$accepted=false;
        try{
            for($attempt=0;$attempt<50;$attempt++){
                if(($this->store->read()['id']??null)!==$id)return;
                try{$lock=$this->store->lock();break;}catch(RuntimeException $e){if($e->getMessage()!=='busy')throw $e;usleep(100000);}
            }
            if($lock===null)return;$j=$this->store->read();
            if(($j['id']??null)!==$id||!in_array($j['state'],['preparing','applying'],true))throw new RuntimeException('invalid_request');
            $accepted=true;
            $this->store->write(['id'=>$id,'identity'=>self::identity(getmypid())],'actor-work.json');
            $lease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
            (new AsusImportTransaction())->writer(function()use($j){
                if($j['state']==='applying'){$this->applyWork();return;}
                $this->assertOriginal();if(!$this->awaitBrowser($j))return;$this->preflight();
                if(($j['search']??null)==='synthesis'){$this->synthesisWork();return;}
                $this->phase('catalog',['state'=>'running']);$profiles=$this->stage();$this->phase('dns');
                $dns=$this->probe([1]);$this->phase('profiles',['dns'=>$dns['groups'][0]['document']['results']['dns_availability']??[]]);
                $baseline=null;$winner=null;$best=0;$count=count($profiles);$progressTotal=$count+($j['extended']?3:0);$lib=$this->library();
                for($i=0;$i<count($profiles);$i++){
                    $p=$profiles[$i];$this->checkpoint();NfqwsStrategyPickerConcurrency::admit($this->store->read(),true);$entry=$lib->entry($p['id']);
                    if(isset($p['variant']))$entry['config']=$p['variant'];
                    $this->phase('switching',['progress'=>(int)floor($i/max($progressTotal,1)*90),'current_name'=>$p['name']]);
                    try{
                        $this->service('stop');$this->resetAuto($entry);$raw=$this->candidate($entry);$this->config->replace($raw);$this->service('start');
                        $this->phase('warming');$this->probe([2,3]);$runs=[];
                        for($repeat=0;$repeat<2;$repeat++){$this->phase('measuring_'.($repeat+1));$runs[]=NfqwsStrategyPickerConcurrency::measure($this->store->read(),$this->probe([2,3]));}
                        if($baseline===null){$baseline=$runs;$rank=['eligible'=>false,'reason'=>'baseline','gain'=>0];}
                        else $rank=NfqwsStrategyPickerScore::compare($baseline,$runs,$j['goal']??'all');
                        $p['runs']=$runs;$p['rank']=$rank;$p['config_sha256']=hash('sha256',$raw);
                        if($rank['eligible']&&$rank['gain']>$best){
                            $key=$p['id'].(isset($p['recipe'])?':'.$p['recipe']:'');
                            $source=NfqwsPlatform::settings()['config'].'/strategy-picker/'.$j['id'].'/'.$entry['id'];
                            // Freeze the winner's AUTO after its daemon exits,
                            // before another recipe can reset the shared copy.
                            $this->service('stop');
                            $this->store->write(['id'=>$j['id'],'winner'=>$key,'files'=>NfqwsStrategyPickerResources::snapshotMutable($entry,$source,0,$this->store)],'winner-auto.json');
                            $winner=$key;$best=$rank['gain'];
                        }
                    }catch(Throwable $e){
                        if($i===0||in_array($e->getMessage(),['cancelled','timed_out','source_changed','insufficient_memory'],true))throw $e;
                        $this->stopOwnedProbe();$p['error']=self::error($e);
                    }
                    $this->service('stop');$this->config->restore();$this->phase($this->store->read()['phase'],['restored'=>false]);$current=$this->store->read();$current['profiles'][]=$p;$current['winner']=$winner;$current['progress']=(int)floor(($i+1)/max($progressTotal,1)*90);$this->store->write($current);
                    if($i===$count-1&&$j['extended']&&$winner===null){
                        $source=$lib->entry($profiles[0]['id']);$variants=NfqwsStrategyPickerRecipes::expand($source['config'],$j['budget']['max_repeats']);
                        foreach(array_slice($variants,0,3)as $n=>$variant)$profiles[]=['id'=>$source['id'],'name'=>'Текущая · '.$variant['name'],'source'=>'recipe','recipe'=>(string)$n,'variant'=>$variant['config']];
                    }
                }
                $this->phase('restoring',['state'=>'restoring']);$this->restore();$this->phase('complete',['state'=>'completed','finished_at'=>time(),'progress'=>100]);
            });
        }catch(Throwable $e){
            if($accepted){$this->recordFailure($e);$this->fail(self::error($e));}
        }finally{foreach([$lease,$lock]as $f)if(is_resource($f)){flock($f,LOCK_UN);fclose($f);}}
    }
    /** Capture before restoration frees memory; no exception arguments or config bytes. */
    private function recordFailure(Throwable $error):void
    {
        try{
            $j=$this->store->read();$raw=(string)@file_get_contents('/proc/meminfo',false,null,0,16384);$memory=[];
            foreach(['MemAvailable','MemFree','Buffers','Cached','SwapFree','Slab']as $key){
                if(preg_match('/^'.$key.':\s+([0-9]+) kB\s*$/m',$raw,$m))$memory[$key]=(int)$m[1];
            }
            $processes=[];
            foreach(glob('/proc/[0-9]*/comm')?:[]as $path){
                $name=trim((string)@file_get_contents($path,false,null,0,64));
                if(!in_array($name,['php-cgi','nfqws','nfqws2','dpi-detector'],true))continue;
                $status=(string)@file_get_contents(dirname($path).'/status',false,null,0,8192);$rss=null;
                if(preg_match('/^VmRSS:\s+([0-9]+) kB\s*$/m',$status,$m))$rss=(int)$m[1];
                $processes[]=['pid'=>(int)basename(dirname($path)),'name'=>$name,'rss_kib'=>$rss];
                if(count($processes)>=32)break;
            }
            $trace=[];
            foreach(array_slice($error->getTrace(),0,8)as $frame){
                $trace[]=['file'=>substr(basename((string)($frame['file']??'')),0,128),'line'=>(int)($frame['line']??0),
                    'class'=>substr((string)($frame['class']??''),0,128),'function'=>substr((string)($frame['function']??''),0,128)];
            }
            $j['failure_diagnostics']=['code'=>self::error($error),'phase'=>$j['phase']??null,
                'available_kib'=>AsusDpiInstaller::availableMemoryKiB($raw),'memory_kib'=>$memory,
                'php_used_bytes'=>memory_get_usage(true),'php_peak_bytes'=>memory_get_peak_usage(true),'processes'=>$processes,
                'origin'=>['file'=>substr(basename($error->getFile()),0,128),'line'=>$error->getLine()],
                'trace'=>$trace];
            $this->store->write($j);
        }catch(Throwable $ignored){/* Diagnostic I/O must never prevent original recovery. */}
    }
    private function fail(string $code,?string $guardId=null):void
    {
        try{$this->phase('restoring',['state'=>'restoring','code'=>$code]);$this->restore();$this->phase('complete',['state'=>$code==='cancelled'?'cancelled':'failed','finished_at'=>time()]);$this->customRecoverPending($this->store->read()['id']);}
        catch(Throwable $e){if($guardId!==null)$this->diagnoseGuard($guardId,$e);$this->phase('recovery_required',['state'=>'recovery_required','code'=>self::error($e),'finished_at'=>time()]);}
    }
    /** First guard exception is private and independent of the shared phase.
     * Diagnostic I/O never delays recovery or authorizes process cleanup. */
    private function diagnoseGuard(string $id,Throwable $error):void
    {
        try{
            $j=$this->store->read();if(($j['id']??null)!==$id)return;
            if(($this->store->read('failure-guard.json')['id']??null)===$id)return;
            $actors=[];
            foreach(['work','guard']as $name){
                $a=$this->store->read('actor-'.$name.'.json')['identity']??null;
                $actors[$name]=['pid'=>is_array($a)&&is_int($a['pid']??null)?$a['pid']:null,
                    'same'=>is_array($a)&&self::sameActor($a)];
            }
            $trace=[];
            foreach(array_slice($error->getTrace(),0,4)as $frame)$trace[]=[
                'file'=>substr(basename((string)($frame['file']??'')),0,128),'line'=>(int)($frame['line']??0),
                'class'=>substr((string)($frame['class']??''),0,64),'function'=>substr((string)($frame['function']??''),0,64)];
            $record=['id'=>$id,'kind'=>'guard_exception','class'=>get_class($error),'code'=>self::error($error),
                'message'=>json_decode(json_encode(substr($error->getMessage(),0,512),JSON_INVALID_UTF8_SUBSTITUTE|JSON_THROW_ON_ERROR),true),
                'file'=>substr(basename($error->getFile()),0,128),'line'=>$error->getLine(),
                'state'=>is_string($j['state']??null)?substr($j['state'],0,64):null,
                'phase'=>is_string($j['phase']??null)?substr($j['phase'],0,64):null,
                'trigger'=>is_string($j['code']??null)?substr($j['code'],0,64):null,'uptime'=>AsusUpdateStore::uptime(),
                'deadline'=>is_numeric($j['deadline']??null)?(float)$j['deadline']:null,'peak'=>memory_get_peak_usage(true),'actors'=>$actors,'trace'=>$trace];
            if(strlen(json_encode($record,JSON_THROW_ON_ERROR))>4096)unset($record['trace']);
            // An id-bound diagnostic is not an atomic job CAS and has no mutation authority.
            if(($this->store->read()['id']??null)===$id)$this->store->write($record,'failure-guard.json');
        }catch(Throwable $ignored){/* Keep the original recovery path even if storage failed. */}
    }
    public function guard(string $id):void
    {
        // Keep the update exclusion alive even after the worker is killed.
        $lease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
        try{
            $guardIdentity=self::identity(getmypid());if($guardIdentity===null)throw new RuntimeException('guard_lost');
            $this->store->write(['id'=>$id,'identity'=>$guardIdentity],'actor-guard.json');
            $registered=$this->store->read('actor-guard.json',$guardPin);
            if($registered!==['id'=>$id,'identity'=>$guardIdentity]||$guardPin===null)throw new RuntimeException('source_changed');
            // Recovery has no authority from matching PIDs or content alone.
            // Reuse the actual Config binding and this guard's observed record.
            $verify=function()use($id,$guardIdentity,$guardPin):void{
                $this->config->raw(true);$current=$this->store->read();
                if(($current['id']??null)!==$id||!in_array($current['state']??null,self::ACTIVE,true))throw new RuntimeException('source_changed');
                if(($current['actuator_attention']??null)!==null||($current['actuator_intent']??null)!==null)throw new RuntimeException('recovery_required');
                if(array_key_exists('resources_sha256',$current)&&$this->resourcesFingerprint()!==$current['resources_sha256'])throw new RuntimeException('source_changed');
                $actual=$this->actor('guard',$id,$actualPin);if($actual===null)throw new RuntimeException('guard_lost');
                if($actual!==$guardIdentity||$actualPin!==$guardPin)throw new RuntimeException('source_changed');
                $this->config->raw(true);
            };
            $stopSince=null;$recoverySince=null;
            for($i=0;;$i++){
                $j=$this->store->read();if(($j['id']??null)!==$id||!in_array($j['state'],self::ACTIVE,true))return;
                $actor=$this->actor('work',$id);$deadline=NfqwsStrategyPickerBudget::overallDeadline($j);$expired=$deadline!==null&&AsusUpdateStore::uptime()>=$deadline;$cancel=$this->stopRequested($j);
                if($expired||$cancel)$stopSince??=AsusUpdateStore::uptime();
                if($actor!==null&&(!$expired&&!$cancel||AsusUpdateStore::uptime()-$stopSince<NfqwsStrategyPickerBudget::STOP_GRACE_SECONDS)){
                    $recoverySince=null;
                    sleep(1);continue;
                }
                if($actor===null&&$i<10){sleep(1);continue;}
                $verify();if($actor!==null)self::killTree($actor);$verify();
                $recoverySince??=AsusUpdateStore::uptime();
                $current=$this->store->read();if(($current['id']??null)!==$id||!in_array($current['state']??null,self::ACTIVE,true))return;
                if($this->actor('work',$id)!==null){sleep(1);continue;}
                // Old package children may have inherited a mutex before the
                // close-on-exec fix. Stop only our verified actuator/probe so
                // their inherited descriptors cannot obstruct recovery.
                $verify();$this->customReap(false,false);
                $verify();try{$this->stopOwnedProbe();}catch(Throwable $e){/* restore retries cleanup under the writer boundary */}
                $verify();
                $lock=null;
                try{
                    $lock=$this->store->lock();$current=$this->store->read();
                    if(($current['id']??null)!==$id||!in_array($current['state']??null,self::ACTIVE,true))return;
                    (new AsusImportTransaction())->writer(function()use($verify,$cancel,$expired,$id):void{$verify();$this->fail($cancel?'cancelled':($expired?'timed_out':'interrupted'),$id);});
                    return;
                }catch(RuntimeException $e){
                    if($e->getMessage()!=='busy'||AsusUpdateStore::uptime()-$recoverySince>=NfqwsStrategyPickerBudget::RECOVERY_LOCK_SECONDS){
                        $this->diagnoseGuard($id,$e);
                        $this->phase('recovery_required',['state'=>'recovery_required','code'=>self::error($e),'finished_at'=>time()]);return;
                    }
                }finally{if(is_resource($lock)){flock($lock,LOCK_UN);fclose($lock);}}
                sleep(1);
            }
            throw new RuntimeException('timed_out');
        }catch(Throwable $e){
            $current=$this->store->read();
            if(($current['id']??null)===$id&&in_array($current['state']??null,self::ACTIVE,true)){$this->diagnoseGuard($id,$e);$this->phase('recovery_required',['state'=>'recovery_required','code'=>self::error($e),'finished_at'=>time()]);}
        }finally{flock($lease,LOCK_UN);fclose($lease);}
    }
    public function recoverBoot():bool
    {
        $j=$this->store->read();if(!$j)return true;
        $sameBoot=$j['boot']===trim((string)file_get_contents('/proc/sys/kernel/random/boot_id'));
        // A failed recovery is never permission to start its temporary profile.
        // After reboot, process cleanup is no longer needed and verified bytes
        // can still be restored. Foreign edits remain a blocking conflict.
        if(($j['state']??null)==='recovery_required'&&$sameBoot&&!$this->recoveredStopArchivable($j))throw new RuntimeException('recovery_required');
        if(!in_array($j['state'],array_merge(self::ACTIVE,['recovery_required']),true)||$sameBoot)return true;
        $lock=$this->store->lock();try{$this->restore(true);$this->phase('complete',['state'=>'interrupted','code'=>'interrupted','finished_at'=>time()]);$this->customRecoverPending($j['id']);return $j['running_before'];}
        catch(Throwable $e){$this->phase('recovery_required',['state'=>'recovery_required','code'=>self::error($e),'finished_at'=>time()]);throw $e;}
        finally{flock($lock,LOCK_UN);fclose($lock);}
    }
    private function verifiedConcurrency(array $job):void
    {
        try{NfqwsStrategyPickerConcurrency::verifyRuns($job,$job['profiles']);}
        catch(Throwable $e){throw new RuntimeException('synthesis_unverified',0,$e);}
    }
    public function apply(string $id,bool $torrentSites=false):array
    {
        $lease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();$lock=$this->store->lock();
        try{return (new AsusImportTransaction())->writer(function()use($id,$torrentSites){$j=$this->store->read();if(($j['id']??null)!==$id||$j['state']!=='completed'||$j['winner']===null||!$j['restored'])throw new RuntimeException('stale_state');
            $this->verifiedConcurrency($j);
            if(($j['search']??null)==='synthesis')$this->synthesisVerifiedProfile($j['winner'],true);
            if($torrentSites&&(($j['search']??null)!=='synthesis'||!($j['generation']['verified']??false)))throw new RuntimeException('synthesis_unverified');
            $this->assertOriginal();
            $this->preflight();
            $j['comparison_running_before']=$j['running_before'];$j['running_before']=$this->running();
            $j['torrent_sites']=$torrentSites;
            unset($j['window_id']);
            $j['state']='applying';$j['phase']='applying';$j['deadline']=AsusUpdateStore::uptime()+180;$j['restored']=false;$this->store->write($j);
            $this->launchPair($id);return $this->status();
        });}finally{foreach([$lock,$lease]as $f){flock($f,LOCK_UN);fclose($f);}}
    }
    private function assertOriginal():void
    {
        $j=$this->store->read();
        if(hash('sha256',$this->config->raw(true))!==$j['original_sha256']||$this->resourcesFingerprint()!==$j['resources_sha256'])throw new RuntimeException('source_changed');
    }
    private function applyWork():void
    {
        $this->assertOriginal();$j=$this->store->read();$selected=null;foreach($j['profiles']as $p)if($p['id'].(isset($p['recipe'])?':'.$p['recipe']:'')===$j['winner'])$selected=$p;
        $this->verifiedConcurrency($j);
        if(($j['search']??null)==='synthesis')$selected=$this->synthesisVerifiedProfile($j['winner'],true);
        $this->preflight();$this->checkpoint();
        if(!$selected)throw new RuntimeException('invalid_state');$entry=$this->library()->entry($selected['id']);if(isset($selected['variant']))$entry['config']=$selected['variant'];
        if($j['torrent_sites']??false)$entry['config']=NfqwsStrategySynthesis::torrentSites($entry['config'],$selected['components']);
        $seed=$this->store->read('winner-auto.json');
        if(($seed['id']??null)!==$j['id']||($seed['winner']??null)!==$j['winner']||!is_array($seed['files']??null))throw new RuntimeException('stale_state');
        $this->service('stop');
        $source=NfqwsPlatform::settings()['config'].'/strategy-picker/'.$j['id'].'/'.$entry['id'];
        $entry['config']=NfqwsStrategyPickerResources::retain($entry,$source,NfqwsPlatform::settings()['config'],0,$seed['files'],$this->store);
        $raw=$this->candidate($entry);$this->config->replace($raw);
        if($j['running_before'])$this->service('start');
        $this->phase('applied',['state'=>'applied','applied_sha256'=>hash('sha256',$raw),'applied_resources_sha256'=>$this->resourcesFingerprint(),'finished_at'=>time()]);
    }
    public function dispatch(array $post):array
    {
        self::validateRequest($post);
        if($post['cmd']==='pickerwindow'){
            return ['recorded'=>$this->store->updateBrowser($post['request_id'],$post['window_id'],$post['presence']==='closed')];
        }
        if($post['cmd']==='pickertargets'){require_once __DIR__.'/strategy-picker-targets.php';return NfqwsStrategyPickerTargets::inspectMixed($post['custom_sites']);}
        if($post['cmd']==='pickerresult')return $this->synthesisMeasuredView($post['id'],$post['result']);
        if($post['cmd']==='pickerexport'&&isset($post['result']))return $this->synthesisMeasuredExport($post['id'],$post['result']);
        if($post['cmd']==='pickerplan')return $this->previewPlan(NfqwsStrategyPickerRequest::selection($post['extended']==='1',$post['goal']??'all',$post['search']==='synthesis',isset($post['custom_sites'])?NfqwsStrategyPickerRequest::custom($post['custom_sites'],$post['custom_only']):null,$post['concurrency']??'auto',$post['rounds']??($post['search']==='synthesis'?'2':'1')));
        return match($post['cmd']){
            'pickerstart','pickerextended'=>$this->start($post['request_id'],$post['cmd']==='pickerextended',$post['goal']??'all',
                false,null,$post['concurrency']??'auto',$post['plan_sha256']??null,null,$post['window_id']??null),
            'pickersynthesize'=>$this->start($post['request_id'],false,$post['goal']??'all',true,
                isset($post['custom_sites'])?NfqwsStrategyPickerRequest::custom($post['custom_sites'],$post['custom_only']):null,
                $post['concurrency']??'auto',$post['plan_sha256']??null,$post['rounds']??null,$post['window_id']??null),
            'pickerexport'=>$this->synthesisExport($post['id'],($post['torrent_sites']??'0')==='1'),
            'pickercancel'=>$this->cancel($post['id']),
            'pickerapply'=>$this->apply($post['id'],($post['torrent_sites']??'0')==='1'),
            default=>$this->status(),
        };
    }
    public static function error(Throwable $e):string
    {
        $v=$e->getMessage();$known=['admission_closed','admission_busy','admission_mismatch','invalid_admission','invalid_request','consent_required','busy','source_changed','stale_state','recovery_required','not_installed','unsupported_abi','unsupported_runtime','insufficient_memory','insufficient_space','storage_unavailable','output_limit','launch_failed','cancelled','timed_out','interrupted','service_state_unknown','service_start_failed','service_stop_failed','service_check_failed','detector_failed','detector_stop_failed','incomparable_result','youtube_not_tested','split_mode_active','all_mode_not_supported','previous_result_retained','guard_lost','actuator_stop_failed','profile_import_incomplete','lua_trust','unresolved_profile_resource','catalog_unavailable','catalog_version'];
        return in_array($v,array_merge($known,['synthesis_lua_unavailable','invalid_synthesis_recipe','synthesis_unverified','synthesis_rule_limit','custom_budget_unavailable','concurrency_budget_unavailable','torrent_sites_incompatible','invalid_custom_targets','request_conflict','plan_changed']),true)?$v:'failed';
    }
}

if(NfqwsDeviceProfilesPaths::cliEntry(__FILE__,$_SERVER,$argv??[])){
    if(!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)file_get_contents('/proc/self/status')))exit(2);
    $args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);$mode=array_shift($args);
    try{$r=new NfqwsStrategyPickerRuntime();
        if($mode==='boot'&&$args===[])exit($r->recoverBoot()?0:3);
        if(!in_array($mode,['work','guard'],true)||count($args)!==1||!preg_match('/^[a-f0-9]{32}$/D',$args[0]))exit(2);
        // CGI can leave its input timer armed despite max_execution_time=0;
        // set_time_limit(0) does not reliably clear it on either router. Both
        // limits are disabled in the trusted launcher before CGI startup.
        // Our independent monotonic guard still enforces the operation budget.
        if((int)ini_get('max_input_time')>0||(int)ini_get('max_execution_time')>0)throw new RuntimeException('unsupported_runtime');
        // Bounded root-private crash evidence. Reserve memory so a PHP memory
        // limit failure can be recorded without exposing it through the API.
        $reserve=str_repeat('x',1048576);$jobId=$args[0];
        register_shutdown_function(function()use(&$reserve,$mode,$jobId){
            $reserve=null;$error=error_get_last();
            if(!$error||!in_array($error['type'],[E_ERROR,E_PARSE,E_CORE_ERROR,E_COMPILE_ERROR],true))return;
            try{$store=new NfqwsStrategyPickerState(NfqwsPlatform::settings()['web_config'].'/strategy-picker');
                if(($store->read()['id']??null)!==$jobId||($mode==='guard'&&($store->read('failure-guard.json')['id']??null)===$jobId))return;
                $store->write(['id'=>$jobId,'type'=>$error['type'],'file'=>basename($error['file']),'line'=>$error['line'],'peak'=>memory_get_peak_usage(true),'phase'=>$store->read()['phase'],'message'=>substr($error['message'],0,512)],'failure-'.$mode.'.json');
            }catch(Throwable $ignored){}
        });
        $r->$mode($args[0]);exit(0);
    }catch(Throwable $e){
        if(in_array($mode,['work','guard'],true)&&isset($args[0])&&preg_match('/^[a-f0-9]{32}$/D',$args[0])){
            try{$store=new NfqwsStrategyPickerState(NfqwsPlatform::settings()['web_config'].'/strategy-picker');
                if(($store->read()['id']??null)===$args[0]&&($mode!=='guard'||($store->read('failure-guard.json')['id']??null)!==$args[0]))$store->write(['id'=>$args[0],'kind'=>'exception','class'=>get_class($e),'code'=>NfqwsStrategyPickerRuntime::error($e),'file'=>basename($e->getFile()),'line'=>$e->getLine(),'peak'=>memory_get_peak_usage(true),'phase'=>$store->read()['phase']],'failure-'.$mode.'.json');
            }catch(Throwable $ignored){}
        }
        file_put_contents('php://stderr',NfqwsStrategyPickerRuntime::error($e)."\n");exit(1);
    }
}
