<?php
require_once __DIR__.'/openwrt-update-prepare.php';
require_once __DIR__.'/openwrt-update-hook.php';
require_once __DIR__.'/openwrt-update-payload.php';
require_once __DIR__.'/openwrt-apk-commit.php';
require_once __DIR__.'/openwrt-web.php';
require_once __DIR__.'/smartdns-lifecycle.php';

/** Detached native transaction. Package-manager execution is never deadline-killed. */
final class NfqwsOpenWrtUpdateWorker
{
    private NfqwsOpenWrtUpdatePrepare $prepare;
    public function __construct(private AsusUpdateStore $store,?NfqwsOpenWrtUpdatePrepare $prepare=null,private array $options=[])
    {$this->prepare=$prepare??new NfqwsOpenWrtUpdatePrepare($store);}
    private function guard():NfqwsOpenWrtUpdateGuard{return new NfqwsOpenWrtUpdateGuard($this->store);}
    private function ticket(string $id,string $phase,array $patch=[]):array
    {
        $t=$this->guard()->context($id);$t=array_replace($t,$patch,['phase'=>$phase]);
        $this->store->writeFile('native-transaction.json',json_encode($t,JSON_THROW_ON_ERROR));return $t;
    }
    private function service(string $component,string $action):bool
    {
        $targets=['core'=>'/usr/lib/nfqws2/nfqws2-native','web'=>'/usr/lib/nfqws2-web/nfqws2-native-web'];
        if(!isset($targets[$component])||!in_array($action,['start','enabled','enable','disable','running'],true))throw new RuntimeException('invalid_state');
        $target=$targets[$component];$path='/etc/init.d/'.basename($target);$s=@lstat($target);
        if(!is_link($path)||readlink($path)!==$target||!$s||!is_file($target)||is_link($target)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0022)!==0||!is_executable($target))throw new RuntimeException('invalid_state');
        AsusUpdateStore::noLinks($target);
        return NfqwsPlatform::run([$path,$action],45)['status']===0;
    }
    private function intent():array
    {
        if(isset($this->options['intent']))return ($this->options['intent'])();$d=NfqwsOpenWrtWeb::diagnostics();
        return ['mode'=>($d['process_running']??false)?(($d['capture']??null)==='waiting_uplink'?'waiting_for_wan':'running'):'stopped',
            'enabled'=>$this->service('core','enabled'),'web_enabled'=>$this->service('web','enabled'),'web_running'=>$this->service('web','running')];
    }
    private function health():bool
    {
        if(isset($this->options['web_health']))return (bool)($this->options['web_health'])();
        if(!$this->service('web','running'))return false;
        $r=NfqwsPlatform::run(['/sbin/uci','-q','get','nfqws2-web.main.port'],5);$text=trim(implode("\n",$r['output']));if($r['status']!==0&&$text==='')$text='90';
        if(!preg_match('/^[0-9]{1,5}$/D',$text)||($port=(int)$text)<1||$port>65535)throw new RuntimeException('invalid_state');
        $end=AsusUpdateStore::uptime()+10;
        do{$socket=@stream_socket_client('tcp://127.0.0.1:'.$port,$errno,$error,1);if(is_resource($socket)){stream_set_timeout($socket,1);fwrite($socket,"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");$line=fgets($socket,1024);fclose($socket);if(is_string($line)&&preg_match('~^HTTP/1\.[01] (?:200|401) ~',$line))return true;}usleep(100000);}while(AsusUpdateStore::uptime()<$end);return false;
    }
    private function restore(array $intent):string
    {
        if(isset($this->options['restore']))return ($this->options['restore'])($intent);
        foreach(['core'=>'enabled','web'=>'web_enabled']as $name=>$field)if(!$this->service($name,($intent[$field]??false)?'enable':'disable'))throw new RuntimeException('intent_mismatch');
        if($intent['web_running']){if(!$this->service('web','start'))throw new RuntimeException('web_start_failed');if(!$this->health())throw new RuntimeException('web_health_failed');}
        $d=NfqwsOpenWrtWeb::diagnostics();
        if($intent['mode']==='stopped'){if($d['process_running']??false)throw new RuntimeException('intent_mismatch');return 'stopped';}
        if(!($d['process_running']??false)&&!$this->service('core','start'))throw new RuntimeException('core_start_failed');$d=NfqwsOpenWrtWeb::diagnostics();
        if(!($d['process_running']??false)||($d['nfqueue']['state']??null)!=='bound')throw new RuntimeException('core_start_failed');
        return ($d['capture']??null)==='waiting_uplink'?'waiting_for_wan':'running';
    }
    private function resume():void
    {
        $r=isset($this->options['dns_resume'])?($this->options['dns_resume'])():(new AsusSmartDnsLifecycle(new AsusSmartDnsStore()))->resume();
        if(!in_array($r['state']??null,['idle','confirmed'],true))throw new RuntimeException('dns_restore_failed');
    }
    private function install(string $id,array $args,array $environment):void
    {
        $critical=$this->store->lease('operations/'.$id.'/critical.lock');$gate=null;
        try{
            if($this->store->readFile('operations/'.$id.'/cancel.json',1024)!==null)throw new RuntimeException('timed_out');
            $this->store->writeFile('operations/'.$id.'/boundary.json',json_encode(['phase'=>'installing'],JSON_THROW_ON_ERROR));
            $this->ticket($id,'installing');$this->store->update($id,['phase'=>'installing']);
            if($environment['format']==='apk')$gate=NfqwsOpenWrtApkCommit::install($this->store,$id);
        }finally{flock($critical,LOCK_UN);fclose($critical);}
        try{
            $name='operations/'.$id.'/manager.log';$this->store->writeFile($name,'');
            $p=@proc_open($args,[0=>['file','/dev/null','r'],1=>['file',$this->store->path($name),'a'],2=>['file',$this->store->path($name),'a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C','LC_ALL'=>'C']);
            if(!is_resource($p))throw new RuntimeException('launch_failed');$exit=null;
            try{
                $status=proc_get_status($p);$expected=realpath($environment['format']==='ipk'?'/bin/opkg':'/usr/bin/apk');$end=AsusUpdateStore::uptime()+2;
                do{$manager=AsusUpdateLifecycle::identity((int)$status['pid']);if(($manager['exe']??null)===$expected)break;$status=proc_get_status($p);if(!$status['running'])break;usleep(1000);}while(AsusUpdateStore::uptime()<$end);
                if(($manager['exe']??null)===$expected)$this->ticket($id,'installing',['manager'=>$manager]);
                // Once launched, wait even when identity publication failed. A
                // manager can already be restoring DNS in its old hook.
                while($status['running']){usleep(20000);$status=proc_get_status($p);}$exit=$status['exitcode'];
            }finally{$closed=proc_close($p);if($exit===null||$exit<0)$exit=$closed;}
            if($exit!==0)throw new RuntimeException('install_failed');
        }finally{if($gate!==null&&!NfqwsOpenWrtApkCommit::remove($gate))throw new RuntimeException('invalid_state');}
    }
    private function recoveryEnvironment(array $before):array
    {
        try{return NfqwsOpenWrtUpdateEnvironment::collect();}
        catch(RuntimeException $e){
            if($e->getMessage()!=='pending_packages'||$before['format']!=='ipk')throw $e;
            // OPKG marks the old row deinstall before preinst. On abort the
            // installed bytes can remain exact while this want flag survives.
            // The caller has already proved the full original payload; never
            // edit the shared database or accept an unpacked/partial row here.
            $r=NfqwsPlatform::run(['/bin/opkg','status','nfqws2-native'],5);if($r['status']!==0)throw $e;
            $v=AsusUpdatePackage::fields(implode("\n",$r['output']));$status=preg_split('/\s+/',trim($v['Status']??''));$flags=explode(',',$status[1]??'');
            if(count($status)!==3||$status[0]!=='deinstall'||$status[2]!=='installed'||array_diff($flags,['ok','user','prefer','hold'])||($v['Version']??null)!==$before['installed']||($v['Architecture']??null)!==$before['arch'])throw $e;
            $profile=json_decode((string)file_get_contents(NfqwsPlatform::sharedFile('platform.json','/usr/share/nfqws2/platform.json')),true,32,JSON_THROW_ON_ERROR);
            return NfqwsOpenWrtUpdateEnvironment::resolve((string)file_get_contents('/etc/openwrt_release'),$profile,['name'=>$v['Package']??null,'version'=>$v['Version'],'arch'=>$v['Architecture']])+['recovery_pending'=>true];
        }
    }
    public function apply(string $id):array
    {
        $lease=$this->store->lease('apply.lock');$ticket=false;$original=null;$environment=null;$managerStarted=false;
        try{return $this->store->withOperationLock($id,function()use($id,&$lease,&$ticket,&$original,&$environment,&$managerStarted){
            $job=$this->store->readOperation($id);if($job['state']!=='applying')return $job;$base='operations/'.$id;$root=$this->options['root']??'/';
            try{
                $closure=NfqwsOpenWrtUpdateRuntime::load($this->store->path($base.'/runtime'));
                if(($job['runtime_digest']??null)!==$closure['digest']||$job['boot_id']!==AsusUpdateStore::boot())throw new RuntimeException('runtime_changed');
                $identity=AsusUpdateLifecycle::identity(getmypid());if($identity===null||$identity['uid']!==0)throw new RuntimeException('invalid_state');
                $environment=$this->prepare->environment();$intent=$this->intent();
                $this->store->writeFile('native-transaction.json',json_encode(['schema'=>1,'id'=>$id,'boot_id'=>AsusUpdateStore::boot(),'worker'=>$identity,'manager'=>null,'phase'=>'validating','format'=>$environment['format'],'intent'=>$intent],JSON_THROW_ON_ERROR));$ticket=true;
                $this->store->update($id,['identity'=>$identity,'intent'=>$intent,'phase'=>'validating']);$this->guard()->context($id);
                $candidate=$this->prepare->candidate($id,true);$preflight=$this->prepare->inspect($id,$candidate,'apk-keys-apply');
                NfqwsOpenWrtUpdatePackage::space($environment['overlay_free'],$environment['ram_free'],$candidate['package'],NfqwsOpenWrtUpdateSnapshot::estimate($root),$environment['runtime_bytes']);
                $this->store->writeFile($base.'/native-preflight.json',json_encode($preflight,JSON_THROW_ON_ERROR));
                $original=NfqwsOpenWrtUpdatePayload::capture($environment['format']);$this->store->writeFile($base.'/original-payload.json',json_encode($original,JSON_THROW_ON_ERROR));
                $args=NfqwsOpenWrtUpdateManager::argv($this->prepare->archive($id,$candidate),$environment,$preflight['installed'],$preflight['record'],$preflight['keys']);$managerStarted=true;$this->install($id,$args,$environment);
                $after=NfqwsOpenWrtUpdateEnvironment::collect();if($after['installed']!==$candidate['package_version'])throw new RuntimeException('version_mismatch');
                $db=NfqwsOpenWrtUpdateManager::installed($after);$expected=$preflight['installed'];unset($db['nfqws2-native'],$expected['nfqws2-native']);if($db!==$expected)throw new RuntimeException('dependency_change');
                if(json_decode($this->store->readFile($base.'/quiesced.json',1024)??'',true)!==['captured'=>true])throw new RuntimeException('invalid_state');
                NfqwsOpenWrtUpdateSnapshot::verify($this->store->path($base.'/backup'),$root);
                $t=$this->ticket($id,'starting');$this->store->update($id,['phase'=>'verifying','installed_version'=>$after['installed'],'settings_verified'=>true]);$core=$this->restore($t['intent']);
                if($t['intent']['web_running']&&!$this->health())throw new RuntimeException('web_health_failed');
                // Package replacement is finished. SH still prevents another
                // update, while fresh isolated DNS validators can also hold SH.
                if(!flock($lease,LOCK_SH))throw new RuntimeException('busy');$this->resume();NfqwsOpenWrtUpdateSnapshot::verify($this->store->path($base.'/backup'),$root);
                (new NfqwsOpenWrtUpdateHook($this->store,$this->options))->complete($t);$this->ticket($id,'finished');return $this->store->update($id,['state'=>'succeeded','code'=>null,'phase'=>'finished','core_state'=>$core]);
            }catch(Throwable $e){
                $patch=['state'=>'failed','code'=>AsusUpdatePrepare::code($e)];
                if($ticket&&$managerStarted&&$original!==null&&NfqwsOpenWrtUpdatePayload::unchanged($original)){
                    try{if(is_dir($this->store->path($base.'/backup')))NfqwsOpenWrtUpdateSnapshot::verify($this->store->path($base.'/backup'),$root);$after=$this->recoveryEnvironment($environment);if($after['installed']!==$environment['installed'])throw new RuntimeException('version_mismatch');
                        $current=NfqwsOpenWrtUpdateManager::installed($after,true);$old=json_decode($this->store->readFile($base.'/native-preflight.json')??'',true,32,JSON_THROW_ON_ERROR)['installed']??null;if(!is_array($old))throw new RuntimeException('invalid_state');unset($old['nfqws2-native']);if($current!==$old)throw new RuntimeException('dependency_change');if($after['recovery_pending']??false)$patch['code']='pending_packages';$t=$this->ticket($id,'starting');$patch['core_state']=$this->restore($t['intent']);
                        if(!flock($lease,LOCK_SH))throw new RuntimeException('busy');$this->resume();(new NfqwsOpenWrtUpdateHook($this->store,$this->options))->complete($t);$patch['installed_version']=$after['installed'];
                    }catch(Throwable $recovery){$patch['code']=AsusUpdatePrepare::code($recovery);}
                }
                if($ticket){try{$this->ticket($id,'finished');}catch(Throwable $ignored){}}
                return $this->store->update($id,$patch);
            }
        });}finally{flock($lease,LOCK_UN);fclose($lease);}
    }
}
