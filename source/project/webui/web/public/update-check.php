<?php
require_once __DIR__.'/update-prepare.php';
require_once __DIR__.'/update-lifecycle.php';

/** A separate bounded read-only job; checking cannot rotate update backups. */
final class AsusUpdateCheck
{
    private NfqwsUpdatePreparation $prepare;
    public function __construct(private AsusUpdateStore $store,?NfqwsUpdatePreparation $prepare=null,private array $options=[])
    {if($prepare===null&&NfqwsPlatform::native()){require_once __DIR__.'/openwrt-update-prepare.php';$prepare=new NfqwsOpenWrtUpdatePrepare($store);}$this->prepare=$prepare??new AsusUpdatePrepare($store);}
    private function task(): ?array
    {
        $raw=$this->store->readFile('check-task.json',4096);if($raw===null)return null;$task=json_decode($raw,true,16,JSON_THROW_ON_ERROR);
        if(!is_array($task)||array_keys($task)!==['schema','id','boot_id','started_uptime','state','guardian','child','code']||$task['schema']!==1||!preg_match('/^[a-f0-9]{32}$/D',$task['id'])||!is_string($task['boot_id'])||!is_numeric($task['started_uptime'])||!in_array($task['state'],['checking','done','failed'],true))throw new RuntimeException('invalid_state');return $task;
    }
    private function save(array $task): void {$this->store->writeFile('check-task.json',json_encode($task,JSON_THROW_ON_ERROR));}
    private function result(string $state,?string $code=null): array
    {return ['state'=>$state,'code'=>$code,'candidate'=>null,'installed_version'=>$this->prepare->environment()['installed']];}
    private function backgroundLock(callable $fn): mixed
    {
        $end=AsusUpdateStore::uptime()+1;
        do{try{return $this->store->withLock($fn);}catch(RuntimeException $e){if($e->getMessage()!=='busy'||AsusUpdateStore::uptime()>=$end)throw $e;usleep(10000);}}while(true);
    }
    private function terminateOwned($process,?array $identity): void
    {
        $status=proc_get_status($process);if(!$status['running']||$identity===null)return;
        $now=AsusUpdateLifecycle::identity((int)$status['pid']);
        if($now===null||$identity['start_ticks']!==$now['start_ticks']||$identity['boot_id']!==$now['boot_id']||$now['uid']!==($this->options['owner']??0))return;
        proc_terminate($process,15);$end=AsusUpdateStore::uptime()+1;
        do{usleep(10000);$status=proc_get_status($process);}while($status['running']&&AsusUpdateStore::uptime()<$end);
        if($status['running'])proc_terminate($process,9);
    }
    private function fail(string $id,string $code): void
    {$this->backgroundLock(function()use($id,$code){$t=$this->task();if(($t['id']??null)===$id&&$t['state']==='checking'){$t['state']='failed';$t['code']=$code;$this->save($t);}});}
    public function status(): array
    {
        return $this->store->withLock(function(){
            $t=$this->task();if($t!==null&&$t['state']==='checking'){
                $age=AsusUpdateStore::uptime()-$t['started_uptime'];
                if($t['boot_id']!==AsusUpdateStore::boot()||$age<0){$this->fail($t['id'],'interrupted');return $this->result('failed','interrupted');}
                if($age>17){$this->fail($t['id'],'timed_out');return $this->result('failed','timed_out');}
                return $this->result('checking');
            }
            if($t!==null&&$t['state']==='failed')return $this->result('failed',$t['code']);
            return $this->prepare->cached()??$this->result('failed','check_required');
        });
    }
    public function request(bool $force=false): array
    {
        try{$id=$this->store->withLock(function()use($force){
            if(!$force&&$this->prepare->cached()!==null)return null;
            $task=$this->task();if($task!==null&&$task['state']==='checking'){
                $age=AsusUpdateStore::uptime()-$task['started_uptime'];if($task['boot_id']===AsusUpdateStore::boot()&&$age>=0&&$age<17)return null;
            }
            // Validate private local config before launching; no connection here.
            if(isset($this->options['channel_probe']))($this->options['channel_probe'])();elseif(!NfqwsPlatform::native())new AsusUpdateTransport();
            $id=bin2hex(random_bytes(16));$this->save(['schema'=>1,'id'=>$id,'boot_id'=>AsusUpdateStore::boot(),'started_uptime'=>AsusUpdateStore::uptime(),'state'=>'checking','guardian'=>null,'child'=>null,'code'=>null]);return $id;
        });}catch(RuntimeException $e){
            if($e->getMessage()==='channel_unconfigured')return $this->result('unconfigured','channel_unconfigured');
            if($e->getMessage()==='invalid_channel')return $this->result('failed','invalid_channel');throw $e;
        }
        if($id===null)return $this->status();
        try{
            if(NfqwsPlatform::native()){require_once __DIR__.'/openwrt-update-launch.php';NfqwsOpenWrtUpdateLaunch::launch($this->store,'check',$id);return $this->status();}
            $busybox=$this->options['busybox']??AsusUpdateStore::installed('libexec/nfqws2-asus/busybox');$entry=$this->options['entry']??AsusUpdateStore::installed('lib/nfqws2-asus/update/check.sh');
            foreach([[$busybox,0],[$entry,$this->options['owner']??0]] as [$path,$owner]){AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0022)!==0||!is_executable($path))throw new RuntimeException('invalid_state');}
            $p=@proc_open([$busybox,'start-stop-daemon','-S','-b','-p',$this->store->path('unused-check-guard.pid'),'-x',$busybox,'--','sh',$entry,$id],
                [0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',
                ['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C','LC_ALL'=>'C','HOME'=>'/']);
            if(!is_resource($p)||proc_close($p)!==0)throw new RuntimeException('launch_failed');
        }catch(Throwable $e){$this->fail($id,AsusUpdatePrepare::code($e));}
        return $this->status();
    }
    public function complete(string $id): void
    {
        $t=$this->task();if(($t['id']??null)!==$id||$t['state']!=='checking'||$t['boot_id']!==AsusUpdateStore::boot())throw new RuntimeException('interrupted');
        $this->prepare->check(true);
        $this->backgroundLock(function()use($id){$t=$this->task();if(($t['id']??null)!==$id||$t['state']!=='checking')throw new RuntimeException('interrupted');$t['state']='done';$this->save($t);});
    }
    /** argv is a fixed installed PHP entry produced by trusted code. */
    public function guard(string $id,array $argv,float $seconds=15): void
    {
        $t=$this->task();if(($t['id']??null)!==$id||$t['state']!=='checking'||$t['boot_id']!==AsusUpdateStore::boot()||$seconds<1||$seconds>15)throw new RuntimeException('invalid_state');
        // Establish supervision before starting a potentially blocked DNS child.
        $this->backgroundLock(function()use($id){$t=$this->task();if(($t['id']??null)!==$id||$t['state']!=='checking')throw new RuntimeException('interrupted');$t['guardian']=AsusUpdateLifecycle::identity(getmypid());$this->save($t);});
        $p=@proc_open($argv,[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',
            ['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C','LC_ALL'=>'C','HOME'=>'/']);if(!is_resource($p)){$this->fail($id,'launch_failed');return;}
        $status=proc_get_status($p);$identity=AsusUpdateLifecycle::identity((int)$status['pid']);$deadline=AsusUpdateStore::uptime()+$seconds;$reason='interrupted';
        try{
            $this->backgroundLock(function()use($id,$identity){$t=$this->task();if(($t['id']??null)!==$id)throw new RuntimeException('interrupted');$t['guardian']=AsusUpdateLifecycle::identity(getmypid());$t['child']=$identity;$this->save($t);});
            while($status['running']){
                if(AsusUpdateStore::uptime()>=$deadline){
                    $reason='timed_out';$this->terminateOwned($p,$identity);
                }usleep(20000);$status=proc_get_status($p);
            }
        }finally{$this->terminateOwned($p,$identity);proc_close($p);$this->fail($id,$reason);}
    }
}
