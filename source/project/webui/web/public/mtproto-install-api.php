<?php
require_once __DIR__.'/update-guard.php';
require_once __DIR__.'/dpi-runtime.php';

/** One local Entware install at a time; the manual server/Docker scripts have their own workflow. */
final class AsusMtprotoInstall
{
    private AsusUpdateStore $store;
    private const PROGRAM='/opt/lib/nfqws2-asus/mtproto/install.sh';
    public function __construct(?AsusUpdateStore $store=null)
    {
        if (NfqwsPlatform::native()) throw new RuntimeException('unsupported_runtime');
        $this->store=$store??new AsusUpdateStore(AsusDpiStore::optPath('/var/lib/nfqws2-asus/mtproto-installer'));
    }
    public static function validate(array $post): void
    {
        $fields=match($post['cmd']??'') {
            'mtprotoinstall'=>['cmd','csrf_token','request_id','port','secret'],
            'mtprotoinstallstatus'=>['cmd','csrf_token'],
            'mtprotoinstalllink'=>['cmd','csrf_token','request_id'],
            default=>throw new RuntimeException('invalid_request')
        };
        $keys=array_keys($post);sort($keys);sort($fields);
        if($keys!==$fields)throw new RuntimeException('invalid_request');
        foreach($post as $value)if(!is_string($value))throw new RuntimeException('invalid_request');
        if(isset($post['request_id'])&&!preg_match('/^[a-f0-9]{32}$/D',$post['request_id']))throw new RuntimeException('invalid_request');
        if(isset($post['port'])&&(!preg_match('/^[1-9][0-9]{3,4}$/D',$post['port'])||(int)$post['port']<1024||
            (int)$post['port']>65535||!preg_match('/^dd[a-f0-9]{32}$/D',$post['secret'])))throw new RuntimeException('invalid_request');
    }
    private function save(array $job): void
    {
        $this->store->writeFile('install.json',json_encode($job,JSON_THROW_ON_ERROR));
    }
    private function read(): ?array
    {
        $raw=$this->store->readFile('install.json',2048);
        return $raw===null ? null : json_decode($raw,true,8,JSON_THROW_ON_ERROR);
    }
    private function current(): ?array
    {
        $job=$this->read();
        if(!$job||!in_array($job['state'],['queued','running'],true))return $job;
        if($job['boot']===AsusUpdateStore::boot()) {
            if($job['state']==='queued'&&AsusUpdateStore::uptime()-$job['since']<15)return $job;
            try { $probe=$this->store->lease('apply.lock'); fclose($probe); }
            catch(RuntimeException $e){if($e->getMessage()==='busy')return $job;throw $e;}
        }
        unset($job['key']);$job['state']='failed';$job['code']='interrupted';$this->save($job);return $job;
    }
    private static function summary(?array $job): ?array
    {
        return $job===null?null:array_intersect_key($job,array_flip(['id','state','code','port']));
    }
    public function dispatch(array $post): array
    {
        self::validate($post);
        return $this->store->withRetryLock(function()use($post){
            $job=$this->current();
            if($post['cmd']==='mtprotoinstallstatus')return ['job'=>self::summary($job)];
            $id=$post['request_id'];
            if($post['cmd']==='mtprotoinstalllink') {
                if(($job['id']??null)!==$id||$job['state']!=='completed')throw new RuntimeException('link_unavailable');
                return $this->connection($job);
            }
            $port=(int)$post['port'];$key=substr($post['secret'],2);$hash=hash('sha256',$key);
            if(($job['id']??null)===$id) {
                if($job['port']!==$port||!hash_equals($job['key_hash'],$hash))throw new RuntimeException('request_conflict');
                return ['job'=>self::summary($job)];
            }
            if(in_array($job['state']??null,['queued','running'],true))throw new RuntimeException('busy');
            if(!is_executable('/opt/bin/opkg')||!is_executable(self::PROGRAM))throw new RuntimeException('unsupported_runtime');
            // The installer checks these paths again, immediately before touching its own files.
            foreach(['/opt/share/nfqws-mtproto','/opt/etc/init.d/S98nfqws-mtproto'] as $path) {
                if(file_exists($path)||is_link($path))throw new RuntimeException('already_installed');
            }
            $job=['id'=>$id,'state'=>'queued','code'=>null,'port'=>$port,'key'=>$key,'key_hash'=>$hash,
                'boot'=>AsusUpdateStore::boot(),'since'=>AsusUpdateStore::uptime()];
            $this->save($job);
            try {
                $bb=AsusDpiRuntime::busybox();
                $command=[$bb,'start-stop-daemon','-S','-b','-p',$this->store->path('launch.pid'),'-x','/opt/bin/php-cgi','--',
                    '-d','register_argc_argv=1','-q','-f','/opt/lib/nfqws2-asus/mtproto/worker.php','--',$id];
                $process=proc_open($command,[['file','/dev/null','r'],['file','/dev/null','a'],['file','/dev/null','a']],$pipes,
                    '/', ['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C']);
                if(!is_resource($process)||proc_close($process)!==0)throw new RuntimeException('launch_failed');
            } catch(Throwable $e) {
                unset($job['key']);$job['state']='failed';$job['code']='launch_failed';$this->save($job);
            }
            return ['job'=>self::summary($job)];
        });
    }
    private function connection(array $job): array
    {
        $path=AsusUpdateStore::installed('share/nfqws-mtproto/config.json');
        AsusUpdateStore::noLinks($path);$s=@lstat($path);
        if(!$s||$s['uid']!==0||($s['mode']&0177777)!==0100600||$s['nlink']!==1||$s['size']>1024)throw new RuntimeException('link_unavailable');
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('link_unavailable');
        try {
            $a=fstat($f);if($a['dev']!==$s['dev']||$a['ino']!==$s['ino'])throw new RuntimeException('link_unavailable');
            $config=json_decode((string)stream_get_contents($f,1025),true);
        } finally {fclose($f);}
        if(($config['port']??null)!==$job['port']||!is_string($config['secret']??null)||
            !hash_equals($job['key_hash'],hash('sha256',$config['secret'])))throw new RuntimeException('link_unavailable');
        return ['port'=>$job['port'],'secret'=>'dd'.$config['secret']];
    }
    public function work(string $id): void
    {
        $owner=$this->store->lease('apply.lock');
        try {
            $input=$this->store->withRetryLock(function()use($id){
                $job=$this->read();
                if(($job['id']??null)!==$id||$job['state']!=='queued'||$job['boot']!==AsusUpdateStore::boot())throw new RuntimeException('interrupted');
                $input=$job['port']."\n".$job['key']."\n";unset($job['key']);
                $job['state']='running';$this->save($job);return $input;
            });
            $lease=null;$code='install_failed';
            try {
                $lease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
                $bb=AsusDpiRuntime::busybox();
                // A fixed shell parent holds both leases if PHP exits; the proxy never inherits them.
                $p=proc_open([$bb,'sh','-c','"$1" sh "$2" 3>&- 4>&-; rc=$?; exit "$rc"','mtproto',$bb,self::PROGRAM],
                    [0=>['pipe','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a'],3=>$owner,4=>$lease],$pipes,
                    '/',['PATH'=>'/opt/bin:/opt/sbin:/usr/bin:/bin','LANG'=>'C','HOME'=>'/']);
                if(!is_resource($p))throw new RuntimeException('launch_failed');
                $written=fwrite($pipes[0],$input);fclose($pipes[0]);$exit=proc_close($p);
                if($written===strlen($input))$code=match($exit){0=>null,18=>'already_installed',19=>'telegram_unreachable',default=>'install_failed'};
            } catch(Throwable $e) {
                if(in_array($e->getMessage(),['busy','launch_failed','recovery_required'],true))$code=$e->getMessage();
            } finally {if(is_resource($lease))fclose($lease);}
            $this->store->withRetryLock(function()use($id,$code){
                $job=$this->read();
                if(($job['id']??null)!==$id||$job['state']!=='running')throw new RuntimeException('invalid_state');
                $job['state']=$code===null?'completed':'failed';$job['code']=$code;$this->save($job);
            });
        } finally {fclose($owner);}
    }
}
