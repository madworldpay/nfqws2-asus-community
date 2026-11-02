<?php
/** Compatibility for published coordinators that stop DNS but never resume it. */
declare(strict_types=1);
require_once __DIR__.'/update-guard.php';
require_once __DIR__.'/update-package.php';
require_once __DIR__.'/smartdns-store.php';
final class AsusUpdatePostinstResume
{
    private const LEGACY=['da69354b3835b9026c6aebac0961028e4a45ec406b0761cfe179285d18faf513','d46f0f2cb1ab9030804fe11f40c392f5ac74ca999caff50c08b5a02110b3f60b'];
    private int $owner;
    private string $opt;
    public function __construct(private AsusUpdateStore $store,private array $options=[])
    {$this->owner=$options['owner']??0;$this->opt=$options['opt']??dirname(AsusDpiStore::optPath('/var'));}
    private static function keys(array $a,array $want):bool{$keys=array_keys($a);sort($keys);sort($want);return $keys===$want;}
    private function json(string $name,int $limit=131072):array
    {$raw=$this->store->readFile($name,$limit);if($raw===null)throw new RuntimeException('invalid_state');try{$v=json_decode($raw,true,24,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}if(!is_array($v))throw new RuntimeException('invalid_state');return $v;}
    private function write(string $id,array $v):void{$this->store->writeFile('operations/'.$id.'/dns-resume.json',json_encode($v,JSON_THROW_ON_ERROR));}
    private function intent():?string
    {$dns=$this->options['dns']??$this->opt.'/etc/nfqws-asus-web/smartdns';$value=(new AsusSmartDnsStore($dns,$this->owner))->intent();return $value===null?null:hash('sha256',json_encode($value,JSON_THROW_ON_ERROR));}
    /** Existing job's protected digest binds every immutable staged byte. */
    private function seal(array $job):?string
    {
        $id=$job['id'];$runtime=$this->store->path('operations/'.$id.'/runtime');$raw=$this->store->readFile('operations/'.$id.'/runtime/closure.json');
        if($raw===null||!is_string($job['runtime_digest']??null)||!hash_equals($job['runtime_digest'],hash('sha256',$raw)))throw new RuntimeException('runtime_changed');
        $m=json_decode($raw,true,24,JSON_THROW_ON_ERROR);if(!is_array($m)||!self::keys($m,['schema','files','loader','bytes'])||$m['schema']!==1||!is_array($m['files'])||count($m['files'])>256||!is_int($m['bytes'])||$m['bytes']>33554432||!is_string($m['loader'])||!preg_match('/^ld[a-zA-Z0-9_.-]+$/D',$m['loader']))throw new RuntimeException('runtime_changed');
        $legacy=$m['files']['app/update-worker.php']['sha256']??null;if(!in_array($legacy,self::LEGACY,true))return null;if(!in_array($job['identity']['exe']??null,[$runtime.'/php',$runtime.'/lib/'.$m['loader']],true))throw new RuntimeException('runtime_changed');$total=0;
        foreach($m['files'] as $name=>$v){if(!is_string($name)||!preg_match('~^(?:php|worker\.php|check\.sh|run\.sh|update-launch|(?:app|lib|resources)/[a-zA-Z0-9_+.-]+)$~D',$name)||!is_array($v)||!self::keys($v,['mode','size','sha256'])||!in_array($v['mode'],[0600,0700],true)||!is_int($v['size'])||$v['size']<0||$v['size']>16777216||!is_string($v['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$v['sha256']))throw new RuntimeException('runtime_changed');
            $p=$runtime.'/'.$name;AsusUpdateStore::noLinks($p);$s=@lstat($p);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||($s['mode']&0777)!==$v['mode']||$s['size']!==$v['size']||!hash_equals($v['sha256'],hash_file('sha256',$p)))throw new RuntimeException('runtime_changed');$total+=$s['size'];if($total>33554432)throw new RuntimeException('runtime_changed');
        }
        foreach(['php','worker.php','update-launch','app/update-worker.php','lib/'.$m['loader']] as $name)if(!isset($m['files'][$name]))throw new RuntimeException('runtime_changed');if($total!==$m['bytes'])throw new RuntimeException('runtime_changed');return $legacy;
    }
    private function command(array $argv):bool
    {
        $p=@proc_open($argv,[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C','LC_ALL'=>'C']);if(!is_resource($p))return false;$end=AsusUpdateStore::uptime()+5;$exit=-1;
        try{do{$s=proc_get_status($p);if(!$s['running']){$exit=$s['exitcode'];break;}if(AsusUpdateStore::uptime()>=$end){proc_terminate($p,15);usleep(100000);if(proc_get_status($p)['running'])proc_terminate($p,9);break;}usleep(10000);}while(true);}finally{$closed=proc_close($p);if($exit<0)$exit=$closed;}return $exit===0;
    }
    /** Called only from the authorized installed postinst descendant of opkg. */
    public function schedule():array
    {
        $guard=new AsusUpdateGuard($this->store,$this->owner,$this->options['opkg']??'/opt/bin/opkg');if(!$guard->authorize('hook-postinst'))throw new RuntimeException('invalid_state');$ticket=$this->json('transaction.json',16384);$id=$ticket['id'];$ticket=$guard->context($id);$job=$this->store->readOperation($id);
        if($ticket['phase']!=='installing'||$job['state']!=='applying'||($job['phase']??null)!=='installing'||$job['boot_id']!==AsusUpdateStore::boot())throw new RuntimeException('invalid_state');
        $legacy=$this->seal($job);if($legacy===null)return ['state'=>'coordinator_owned'];
        if(($job['identity']??null)!==$ticket['worker'])throw new RuntimeException('invalid_state');$intent=$this->intent();if($intent===null)return ['state'=>'skipped'];
        $proof=['schema'=>1,'id'=>$id,'runtime_digest'=>$job['runtime_digest'],'worker'=>$ticket['worker'],'version'=>$job['package_version'],'legacy'=>$legacy,'intent_sha256'=>$intent,'state'=>'scheduled','code'=>null];$this->write($id,$proof);
        $entry=$this->options['entry']??[$this->opt.'/bin/php-cgi','-n','-d','register_argc_argv=1','-q','-f',$this->opt.'/share/nfqws-asus-web/update-postinst-resume.php','--'];$busybox=$this->options['busybox']??$this->opt.'/libexec/nfqws2-asus/busybox';
        $ok=$this->command(array_merge([$busybox,'start-stop-daemon','-S','-b','-p',$this->opt.'/var/run/nfqws2-legacy-dns-resume.pid','-x',$entry[0],'--'],array_slice($entry,1),['resume',$id]));
        if(!$ok){$proof['state']='failed';$proof['code']='launch_failed';$this->write($id,$proof);}return ['state'=>$ok?'scheduled':'failed'];
    }
    /** No DNS action before final legacy job success and release of apply.lock. */
    public function resume(string $id):array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');$shared=null;$exclusive=null;$proof=null;
        try{$guard=new AsusUpdateGuard($this->store,$this->owner,$this->options['opkg']??'/opt/bin/opkg');$end=AsusUpdateStore::uptime()+($this->options['wait']??90);
            do{try{$shared=$guard->mutationLease();break;}catch(Throwable $e){if($e->getMessage()!=='busy'||AsusUpdateStore::uptime()>=$end)throw $e;usleep(100000);}}while(true);
            $exclusive=$this->store->lease('operations/'.$id.'/critical.lock');$proof=$this->json('operations/'.$id.'/dns-resume.json');
            if(!self::keys($proof,['schema','id','runtime_digest','worker','version','legacy','intent_sha256','state','code'])||$proof['schema']!==1||$proof['id']!==$id||!in_array($proof['legacy'],self::LEGACY,true))throw new RuntimeException('invalid_state');if($proof['state']!=='scheduled')return ['state'=>'skipped'];
            $ticket=$this->json('transaction.json',16384);$job=$this->store->readOperation($id);
            if(($ticket['id']??null)!==$id||($ticket['phase']??null)!=='finished'||($ticket['worker']??null)!==$proof['worker']||($proof['worker']['boot_id']??null)!==AsusUpdateStore::boot()||$job['boot_id']!==AsusUpdateStore::boot()||($job['identity']??null)!==$proof['worker']||$job['runtime_digest']!==$proof['runtime_digest']||$this->seal($job)!==$proof['legacy'])throw new RuntimeException('runtime_changed');
            if($job['state']!=='succeeded'||($job['phase']??null)!=='finished'||($job['settings_verified']??null)!==true||($job['installed_version']??null)!==$proof['version']||$job['package_version']!==$proof['version'])throw new RuntimeException('update_not_succeeded');
            $status=$this->opt.'/lib/opkg/status';AsusUpdateStore::noLinks($status);$s=@lstat($status);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>2097152)throw new RuntimeException('invalid_state');$db=AsusUpdatePackage::database(file_get_contents($status));$own=$db['nfqws2-asus']??[];if(($own['Version']??null)!==$proof['version']||!preg_match('/^install (?:ok|user) installed$/D',$own['Status']??''))throw new RuntimeException('version_mismatch');
            if($this->intent()!==$proof['intent_sha256'])throw new RuntimeException('settings_changed');$proof['state']='dispatching';$this->write($id,$proof);
        }catch(Throwable $e){if(is_array($proof)&&($proof['id']??null)===$id){$proof['state']='skipped';$proof['code']=in_array($e->getMessage(),['busy','runtime_changed','update_not_succeeded','version_mismatch','settings_changed','invalid_state'],true)?$e->getMessage():'invalid_state';$this->write($id,$proof);}return ['state'=>'skipped'];}
        finally{foreach([$exclusive,$shared] as $f)if(is_resource($f)){flock($f,LOCK_UN);fclose($f);}}
        $path=$this->opt.'/lib/nfqws2-asus/smartdns/control.sh';AsusUpdateStore::noLinks($path);$s=@lstat($path);$ok=$s&&($s['mode']&0170000)===0100000&&$s['uid']===$this->owner&&$s['nlink']===1&&($s['mode']&0022)===0&&$s['size']<=16384&&$this->command(['/bin/sh',$path,'queue-resume']);$proof['state']=$ok?'queued':'failed';$proof['code']=$ok?null:'launch_failed';$this->write($id,$proof);return ['state'=>$proof['state']];
    }
}
// Public helper files expose no HTTP operation. Only this fixed root CLI does work.
if(realpath($_SERVER['SCRIPT_FILENAME']??($argv[0]??''))===__FILE__&&!isset($_SERVER['REQUEST_METHOD'])){
    if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(1);
    $args=$argv;array_shift($args);if(($args[0]??null)==='--')array_shift($args);$mode=array_shift($args);
    try{$helper=new AsusUpdatePostinstResume(new AsusUpdateStore());if($mode==='queue'&&$args===[])$result=$helper->schedule();elseif($mode==='resume'&&count($args)===1)$result=$helper->resume($args[0]);else exit(1);echo json_encode($result,JSON_THROW_ON_ERROR)."\n";}
    catch(Throwable $e){echo '{"state":"failed","code":"dns_resume_compat_failed"}'."\n";exit(0);}
}
