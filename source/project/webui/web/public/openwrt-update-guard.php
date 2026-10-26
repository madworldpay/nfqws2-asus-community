<?php
require_once __DIR__.'/openwrt-update-runtime.php';
require_once __DIR__.'/update-lifecycle.php';
require_once __DIR__.'/openwrt-manual-context.php';

/** Native system CGI + immutable application closure + actual manager ancestry. */
final class NfqwsOpenWrtUpdateGuard
{
    public function __construct(private AsusUpdateStore $store,private int $owner=0){}
    private function identity(mixed $v,string $boot):bool
    {
        return is_array($v)&&count($v)===5&&is_int($v['pid']??null)&&$v['pid']>1&&is_string($v['start_ticks']??null)&&preg_match('/^[1-9][0-9]{0,19}$/D',$v['start_ticks'])&&($v['boot_id']??null)===$boot&&is_string($v['exe']??null)&&($v['uid']??null)===$this->owner;
    }
    public static function ancestor(int $wanted):bool
    {
        $pid=getmypid();$seen=[];for($n=0;$n<32&&$pid>1;$n++){
            if($pid===$wanted)return true;if(isset($seen[$pid]))return false;$seen[$pid]=true;$raw=@file_get_contents('/proc/'.$pid.'/status');
            if(!is_string($raw)||!preg_match('/^PPid:\s+([0-9]+)/m',$raw,$m))return false;$pid=(int)$m[1];}
        return false;
    }
    public function ticket():?array
    {
        $raw=$this->store->readFile('native-transaction.json',16384);if($raw===null)return null;$t=json_decode($raw,true,16,JSON_THROW_ON_ERROR);
        $keys=is_array($t)?array_keys($t):[];sort($keys);$expected=['schema','id','boot_id','worker','manager','phase','format','intent'];sort($expected);
        if($keys!==$expected||$t['schema']!==1||!preg_match('/^[a-f0-9]{32}$/D',$t['id']??'')||!is_string($t['boot_id'])||!$this->identity($t['worker'],$t['boot_id'])||($t['manager']!==null&&!$this->identity($t['manager'],$t['boot_id']))||!in_array($t['phase'],['validating','installing','starting','finished'],true)||!in_array($t['format'],['ipk','apk'],true)||!is_array($t['intent'])||!in_array($t['intent']['mode']??null,['running','waiting_for_wan','stopped'],true))throw new RuntimeException('invalid_state');
        return $t;
    }
    private function worker(array $t):bool
    {
        if($t['boot_id']!==AsusUpdateStore::boot()||!AsusUpdateLifecycle::alive($t['worker']))return false;
        $root=$this->store->path('operations/'.$t['id'].'/runtime');$php=realpath('/usr/bin/php-cgi');
        if($php!=='/usr/bin/php8-cgi'||$t['worker']['exe']!==$php)return false;
        $raw=@file_get_contents('/proc/'.$t['worker']['pid'].'/cmdline');if(!is_string($raw))return false;
        $args=explode("\0",rtrim($raw,"\0"));
        if($args!==[$php,'-d','register_argc_argv=1','-q','-f',$root.'/worker.php','--','apply',$t['id']])return false;
        $job=$this->store->readOperation($t['id']);$runtime=NfqwsOpenWrtUpdateRuntime::load($root,$this->owner);
        return ($job['state']??null)==='applying'&&($job['runtime_digest']??null)===$runtime['digest'];
    }
    public function managerAlive(array $t):bool
    {
        $i=$t['manager'];if($i===null||$t['boot_id']!==AsusUpdateStore::boot())return false;
        $expected=realpath($t['format']==='ipk'?'/bin/opkg':'/usr/bin/apk');
        return $expected!==false&&$i['exe']===$expected&&AsusUpdateLifecycle::alive($i);
    }
    public function authorize(string $action):bool
    {
        if(!in_array($action,['core-start','core-stop','web-start','web-stop','hook-prerm','hook-postinst','dns-restore'],true))throw new RuntimeException('invalid_request');
        $t=$this->ticket();
        if($action==='dns-restore'&&($t===null||$t['phase']==='finished'||!AsusUpdateLifecycle::alive($t['worker'])&&!$this->managerAlive($t))&&NfqwsOpenWrtManualContext::authorize())return true;
        if($t===null||!$this->worker($t)||!self::ancestor($t['worker']['pid']))return false;
        $manager=$this->managerAlive($t)&&self::ancestor($t['manager']['pid']);
        if($t['phase']==='installing')return $manager;
        if($t['phase']!=='starting')return false;
        return $action==='web-start'||($action==='core-start'&&$t['intent']['mode']!=='stopped');
    }
    public function context(string $id):array
    {
        $t=$this->ticket();if($t===null||$t['id']!==$id||!$this->worker($t)||!self::ancestor($t['worker']['pid']))throw new RuntimeException('invalid_state');return $t;
    }
    public function mutationLease()
    {
        $f=$this->store->lease('apply.lock',true);
        try{
            $t=$this->ticket();
            // Only the verified worker itself may validate/resume saved DNS
            // after replacing EX with SH and after its manager has exited.
            if($t!==null&&$t['phase']==='starting'&&$t['worker']['pid']===getmypid()&&$this->worker($t)&&!$this->managerAlive($t))return $f;
            if(NfqwsOpenWrtManualContext::activeManager()!==null)throw new RuntimeException('busy');
            if($t!==null&&$t['phase']!=='finished'&&($this->worker($t)||$this->managerAlive($t)))throw new RuntimeException('busy');
            $this->store->reconcile(AsusUpdateStore::boot(),AsusUpdateStore::uptime());$job=$this->store->status()['active'];
            if(($job['state']??null)==='applying'){
                $identity=$job['identity']??null;
                if(is_array($identity)&&AsusUpdateLifecycle::alive($identity)||$identity===null&&AsusUpdateStore::uptime()-($job['apply_uptime']??$job['created_uptime'])<15)throw new RuntimeException('busy');
                $this->store->update($job['id'],['state'=>'interrupted','code'=>'interrupted']);
            }
            return $f;
        }catch(Throwable $e){flock($f,LOCK_UN);fclose($f);throw $e;}
    }
}
