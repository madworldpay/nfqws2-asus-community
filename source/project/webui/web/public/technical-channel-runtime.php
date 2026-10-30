<?php
/** One outbound arranged support session. Does not alter routing, DNS, firewall or VPN. */
final class AsusTechnicalChannel
{
    private array $c;
    private $permissionLock=null;
    public function __construct(array $trusted=[])
    {
        $p=NfqwsPlatform::settings();
        $this->c=$trusted+['temporary_parent'=>'/tmp','runtime'=>'/tmp/nfqws2-technical-channel','journal'=>$p['web_config'].'/technical-channel/journal.json','owner'=>0,
            'public_key'=>$p['share'].'/technical-channel-public.pem','library'=>$p['library'].'/technical-channel',
            'php'=>NfqwsPlatform::native()?'/usr/bin/php-cgi':'/opt/bin/php-cgi',
            'busybox'=>NfqwsPlatform::native()?'/bin/busybox':'/opt/libexec/nfqws2-asus/busybox',
            'ssh'=>NfqwsPlatform::native()?'/usr/bin/dbclient':'/usr/bin/ssh'];
    }
    private function path(string $name): string{return $this->c['runtime'].'/'.$name;}
    private function read(string $name): ?array{return AsusTechnicalFiles::json($this->path($name),$this->c['owner']);}
    private function save(string $name,array $v): void{AsusTechnicalFiles::write($this->path($name),json_encode($v,JSON_THROW_ON_ERROR),0600,$this->c['owner']);}
    private function lock()
    {
        $lease=$this->c['journal'].'.permissions.lock';AsusTechnicalFiles::read($lease,$this->c['owner']);
        $this->permissionLock=fopen($lease,'c+');
        if(!$this->permissionLock||!chmod($lease,0600)||!flock($this->permissionLock,LOCK_EX))throw new RuntimeException('busy');
        $h=null;
        try{
            $this->permissions()->prepare();AsusTechnicalFiles::directory($this->c['runtime'],$this->c['owner']);$s=lstat($this->c['runtime']);
            if($s['uid']!==$this->c['owner']||($s['mode']&0777)!==0700)throw new RuntimeException('unsafe_key_file');
            $path=$this->path('lock');AsusTechnicalFiles::read($path,$this->c['owner']);$h=fopen($path,'c+');
            if(!$h||!chmod($path,0600)||!flock($h,LOCK_EX))throw new RuntimeException('busy');return $h;
        }catch(Throwable $e){try{$this->permissions()->restore();}finally{if(is_resource($h))fclose($h);$this->unlock(null);}throw $e;}
    }
    private function permissions(): AsusTechnicalPermissions{return new AsusTechnicalPermissions($this->c['journal'].'.permissions',$this->c['temporary_parent'],$this->c['owner']);}
    private function unlock($lock): void
    {
        try{
            if(is_resource($lock)){
                try{
                    try{$s=$this->read('state.json');}catch(Throwable $e){$this->permissions()->restore();throw $e;}
                    if(!$s||!in_array($s['state']??null,['connecting','connected'],true))$this->permissions()->restore();
                }
                finally{flock($lock,LOCK_UN);fclose($lock);}
            }
        }finally{if(is_resource($this->permissionLock)){flock($this->permissionLock,LOCK_UN);fclose($this->permissionLock);$this->permissionLock=null;}}
    }
    private function journal(): AsusTechnicalJournal{return new AsusTechnicalJournal($this->c['journal'],$this->c['owner']);}
    private static function display(?array $s): array
    {return ['state'=>$s['state']??'idle','session_id'=>$s['session_id']??null,'expires_at'=>$s['expires_at']??null,'code'=>$s['code']??null]+(isset($s['diagnostic'])?['diagnostic'=>$s['diagnostic']]:[]);}
    private function clean(array $s,string $state,?string $code=null): array
    {
        $current=$this->read('state.json');
        if(($current['activation_id']??null)!==($s['activation_id']??null))return $current??$s;
        // Invalidate the command guard before closing the owned transport.
        if($state==='failed'){
            $stage=in_array($s['stage']??null,['prepare','local_server','transport'],true)?$s['stage']:'prepare';
            $log=AsusTechnicalFiles::sample($this->path('ssh.log'),$this->c['owner']);$raw=$log['raw']??'';
            $reason=$code??'interrupted';
            foreach(['multicall_usage'=>'~multi.?call|Available applets~i','host_key_mismatch'=>'~host key mismatch|host key verification failed|not in the trusted hosts~i','authentication_failed'=>'~permission denied|no auth methods|authentication failed~i','connection_refused'=>'~connection refused~i','connection_timeout'=>'~timed out|timeout~i','unsupported_option'=>'~invalid option|unknown option|unrecognized option~i'] as $name=>$pattern)if(preg_match($pattern,$raw)){$reason=$name;break;}
            $s['diagnostic']=['stage'=>$stage,'reason'=>$reason];
        }
        $s['state']=$state;$s['code']=$code;$this->save('state.json',$s);
        AsusTechnicalProcess::kill($s['transport']??null);AsusTechnicalProcess::kill($s['server_process']??null);
        $this->journal()->restore();
        foreach(['invitation','tunnel.key','stop','ssh.log'] as $name){$path=$this->path($name);if(AsusTechnicalFiles::sample($path,$this->c['owner'])!==null&&!unlink($path))throw new RuntimeException('unsafe_key_file');}
        return $s;
    }
    private function recover(?array $s): ?array
    {
        if($s&&in_array($s['state'],['connecting','connected'],true)){
            if(($s['identity']??null)===null&&time()-($s['started_at']??0)<12)return $s;
            if(AsusTechnicalProcess::active($s,time(),AsusTechnicalProcess::uptime()))return $s;
            $expired=time()>=($s['expires_at']??0)||AsusTechnicalProcess::uptime()>=($s['uptime_deadline']??0);
            return $this->clean($s,$expired?'expired':'failed',$expired?'expired':'interrupted');
        }
        // A power loss may remove /tmp but leaves our persistent public-key journal.
        $this->journal()->restore();return $s;
    }
    public function status(): array
    {$lock=$this->lock();try{return self::display($this->recover($this->read('state.json')));}finally{$this->unlock($lock);}}
    public function stop(): array
    {
        $lock=$this->lock();try{
            $s=$this->recover($this->read('state.json'));if(!$s)return self::display(null);
            if(in_array($s['state'],['connecting','connected'],true)){
                AsusTechnicalFiles::write($this->path('stop'),'stop',0600,$this->c['owner']);
                // Mark stopped immediately: the command guard fails closed, even before worker wakes.
                $s=$this->clean($s,'stopped');
            }
            return self::display($s);
        }finally{$this->unlock($lock);}
    }
    public function start(string $link): array
    {
        $key=AsusTechnicalFiles::read($this->c['public_key'],$this->c['owner']);
        if(!$key)throw new RuntimeException('unsupported_runtime');$v=AsusTechnicalInvite::verify($link,$key['raw'],time());
        $lock=$this->lock();$created=null;try{
            $old=$this->recover($this->read('state.json'));
            if($old&&in_array($old['state'],['connecting','connected'],true))throw new RuntimeException('busy');
            foreach(['php','busybox','ssh'] as $k)if(!is_executable($this->c[$k]))throw new RuntimeException('unsupported_runtime');
            if(!is_file($this->c['library'].'/session.sh')||!is_file($this->c['library'].'/guard.sh'))throw new RuntimeException('unsupported_runtime');
            $s=['state'=>'connecting','stage'=>'prepare','code'=>null,'session_id'=>$v['session_id'],'activation_id'=>bin2hex(random_bytes(16)),'expires_at'=>$v['expires_at'],
                'uptime_deadline'=>AsusTechnicalProcess::uptime()+$v['expires_at']-time(),'started_at'=>time(),'identity'=>null,'transport'=>null];
            $created=$s;$this->save('state.json',$s);AsusTechnicalFiles::write($this->path('invitation'),$link,0600,$this->c['owner']);
            $p=@proc_open([$this->c['busybox'],'start-stop-daemon','-S','-b','-p',$this->path('unused-launch.pid'),'-x',$this->c['busybox'],'--','sh',$this->c['library'].'/session.sh',$s['activation_id']],
                [0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes,'/',['PATH'=>NfqwsPlatform::native()?'/usr/sbin:/usr/bin:/sbin:/bin':'/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C']);
            if(!is_resource($p)||proc_close($p)!==0)throw new RuntimeException('launch_failed');
        }catch(Throwable $e){
            if($created!==null){
                try{$this->clean($created,'failed',AsusTechnicalApi::error($e));}
                finally{
                    // The guardian cannot adopt this activation while we hold
                    // the runtime lock. If even terminal-state storage failed,
                    // remove only our unclaimed activation before unlocking.
                    $current=$this->read('state.json');
                    if(($current['activation_id']??null)===$created['activation_id']&&($current['identity']??null)===null&&in_array($current['state']??null,['connecting','connected'],true)&&!unlink($this->path('state.json')))throw new RuntimeException('unsafe_key_file');
                }
            }
            throw $e;
        }finally{$this->unlock($lock);}
        return self::display($s);
    }
    /** Entry from root-owned session.sh, never from a request parameter. */
    public function run(string $id): void
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_state');
        $p=null;$server=null;$lock=$this->lock();
        try{
            $s=$this->read('state.json');if(($s['activation_id']??null)!==$id||$s['state']!=='connecting'||($s['identity']??null)!==null)throw new RuntimeException('interrupted');
            $link=AsusTechnicalFiles::read($this->path('invitation'),$this->c['owner']);$key=AsusTechnicalFiles::read($this->c['public_key'],$this->c['owner']);
            $v=AsusTechnicalInvite::verify($link['raw']??'',$key['raw']??'',time());
            if($v['session_id']!==$s['session_id'])throw new RuntimeException('invalid_invitation');
            $s['identity']=AsusTechnicalProcess::identity(getmypid());$this->save('state.json',$s);
            [$login,$home]=$this->rootAccount();$known=$home.'/.ssh/known_hosts';
            $authorized=NfqwsPlatform::native()?'/etc/dropbear/authorized_keys':$home.'/.ssh/authorized_keys';
            $original=AsusTechnicalFiles::read($authorized,$this->c['owner']);
            if(str_contains($original['raw']??'',$v['operator_key']))throw new RuntimeException('key_conflict');
            $hosts=AsusTechnicalFiles::read($known,$this->c['owner']);$pinned=false;
            foreach(explode("\n",$hosts['raw']??'') as $line){
                $parts=preg_split('/\s+/',trim($line));if(in_array($v['server'],explode(',',$parts[0]??''),true)){if(($parts[1]??'').' '.($parts[2]??'')!==$v['host_key'])throw new RuntimeException('key_conflict');$pinned=true;}
            }
            $tag='nfqws2-technical-'.$id;
            $guard=$this->c['library'].'/guard.sh';if(!preg_match('~^/[a-zA-Z0-9_./-]+$~D',$guard))throw new RuntimeException('invalid_state');
            $line='no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty,command="'.$guard.' '.$id.'" '.$v['operator_key'].' '.$tag;
            $changes=[['path'=>$authorized,'line'=>$line]];if(!$pinned)$changes[]=['path'=>$known,'line'=>$v['server'].' '.$v['host_key']];
            $this->journal()->apply($changes);
            AsusTechnicalFiles::write($this->path('tunnel.key'),base64_decode($v['tunnel_key']),0600,$this->c['owner']);
            unlink($this->path('invitation'));unset($link);
            $s['stage']='local_server';$this->save('state.json',$s);
            [$server,$port]=$this->localServer($id);$serverStatus=proc_get_status($server);$s['server_process']=AsusTechnicalProcess::identity($serverStatus['pid']);$this->save('state.json',$s);
            $s['stage']='transport';$this->save('state.json',$s);
            $args=[$this->c['ssh'],'-T','-N','-K','15','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-o','PasswordAuthentication=no',
                '-i',$this->path('tunnel.key'),'-R','127.0.0.1:'.$v['remote_port'].':127.0.0.1:'.$port,'-p',(string)$v['server_port'],$v['server_user'].'@'.$v['server']];
            AsusTechnicalFiles::write($this->path('ssh.log'),'',0600,$this->c['owner']);
            $p=@proc_open($args,[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file',$this->path('ssh.log'),'a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C']);
            if(!is_resource($p))throw new RuntimeException('launch_failed');$ps=proc_get_status($p);
            $s['transport']=AsusTechnicalProcess::identity($ps['pid']);$s['login']=$login;$this->save('state.json',$s);
        }catch(Throwable $e){
            if(isset($s)&&($s['activation_id']??null)===$id)$this->clean($s,'failed',AsusTechnicalApi::error($e));
            if(is_resource($p)){proc_terminate($p,9);proc_close($p);}if(is_resource($server)){proc_terminate($server,9);proc_close($server);}throw $e;
        }finally{$this->unlock($lock);}
        $begin=AsusTechnicalProcess::uptime();
        try{
            while(true){
                usleep(200000);$lock=$this->lock();try{
                    $current=$this->read('state.json');if(($current['activation_id']??null)!==$id||!in_array($current['state']??null,['connecting','connected'],true))break;
                    $s=$current;
                    if(!AsusTechnicalProcess::active($s,time(),AsusTechnicalProcess::uptime())){$this->clean($s,'expired','expired');break;}
                    $ps=proc_get_status($p);if(!$ps['running']){$this->clean($s,'failed','connection_failed');break;}
                    $log=AsusTechnicalFiles::sample($this->path('ssh.log'),$this->c['owner']);if($log['truncated']??false){$this->clean($s,'failed','connection_failed');break;}
                    // Guard marks connected only after an operator actually reaches this router.
                    // Waiting for the arranged administrator is bounded by the signed deadline.
                }finally{$this->unlock($lock);}
            }
        }finally{
            if(is_resource($p)){proc_terminate($p,9);proc_close($p);}if(is_resource($server)){proc_terminate($server,9);proc_close($server);}
            $lock=$this->lock();try{$s=$this->read('state.json');if(($s['activation_id']??null)===$id&&in_array($s['state'],['connecting','connected'],true))$this->clean($s,'failed','interrupted');}finally{$this->unlock($lock);}
        }
    }
    private function rootAccount(): array
    {
        $raw=file_get_contents('/etc/passwd');foreach(explode("\n",$raw) as $line){$f=explode(':',$line);
            if(count($f)===7&&$f[2]==='0'&&preg_match('/^[a-zA-Z0-9_-]{1,32}$/D',$f[0])){
                $home=realpath($f[5]);if($home===false)throw new RuntimeException('unsafe_key_file');AsusTechnicalFiles::directory($home,$this->c['owner']);return [$f[0],$home];
            }}throw new RuntimeException('root_required');
    }
    private function localServer(string $id): array
    {
        // A separate loopback-only instance always forces our guard, including
        // routers whose normal SSH server deliberately accepts a blank password.
        $binary=null;$keys=[];
        foreach(glob('/proc/[0-9]*/comm') as $file){if(trim((string)@file_get_contents($file))!=='dropbear')continue;
            $pid=basename(dirname($file));$exe=@readlink('/proc/'.$pid.'/exe');if(is_string($exe)&&is_executable($exe))$binary=$exe;
            $args=explode("\0",(string)@file_get_contents('/proc/'.$pid.'/cmdline'));
            for($n=0;$n<count($args)-1;$n++)if($args[$n]==='-r')$keys[]=$args[$n+1];
        }
        foreach(['/etc/dropbear/dropbear_ed25519_host_key','/etc/dropbear/dropbear_ecdsa_host_key','/etc/dropbear/dropbear_rsa_host_key'] as $path)if(is_file($path))$keys[]=$path;
        $keys=array_values(array_unique($keys));if(!$binary||!$keys)throw new RuntimeException('unsupported_runtime');
        $reserve=@stream_socket_server('tcp://127.0.0.1:0',$errno,$error);if(!$reserve)throw new RuntimeException('launch_failed');
        $address=stream_socket_get_name($reserve,false);$port=(int)substr($address,strrpos($address,':')+1);fclose($reserve);
        $args=array_merge(AsusTechnicalProcess::serverPrefix($binary),['-F','-E','-s','-j','-k','-p','127.0.0.1:'.$port,'-c',$this->c['library'].'/guard.sh '.$id]);
        foreach($keys as $path){$resolved=realpath($path);$st=$resolved===false?false:@lstat($resolved);
            if(!$st||($st['mode']&0170000)!==0100000||$st['uid']!==0||($st['mode']&0077)!==0)throw new RuntimeException('unsafe_key_file');
            $args[]='-r';$args[]=$resolved;
        }
        AsusTechnicalFiles::write($this->path('ssh.log'),'',0600,$this->c['owner']);
        $p=@proc_open($args,[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file',$this->path('ssh.log'),'a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C']);
        if(!is_resource($p))throw new RuntimeException('launch_failed');
        usleep(100000);if(!proc_get_status($p)['running']){proc_close($p);throw new RuntimeException('launch_failed');}
        return [$p,$port];
    }
    /** Called by a forced-command key. No command or session secret comes from the invitation. */
    public function command(string $id): int
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id)||!preg_match('/^127\.0\.0\.1 [0-9]+ 127\.0\.0\.1 [0-9]+$/D',getenv('SSH_CONNECTION')?:''))return 126;
        $cmd=getenv('SSH_ORIGINAL_COMMAND');if(!is_string($cmd)||$cmd===''||strlen($cmd)>16384||str_contains($cmd,"\0"))return 126;
        $lock=$this->lock();try{$s=$this->read('state.json');if(($s['activation_id']??null)!==$id||!AsusTechnicalProcess::active($s,time(),AsusTechnicalProcess::uptime()))return 126;
            $admitted=$s['identity'];$s['state']='connected';$this->save('state.json',$s);
        }finally{$this->unlock($lock);}
        $dir=$this->path('command.'.bin2hex(random_bytes(12)));AsusTechnicalFiles::directory($dir,$this->c['owner']);
        AsusTechnicalFiles::write($dir.'/pid','',0600,$this->c['owner']);$child=null;$exit=126;
        // SSD is shipped on all targets and creates a new session internally.
        // Its double fork means the command PID differs from the process group.
        $shell=<<<'SH'
set -f
umask 077
guard=$1; expected=$2; command=$3; donefile=$4; busybox=$5
exec 0<"/proc/$guard/fd/0" 1>"/proc/$guard/fd/1" 2>"/proc/$guard/fd/2" || exit 126
IFS= read -r stat < /proc/$$/stat || exit 126
rest=${stat##*) }; set -- $rest; group=$3
/bin/sh -c "$command" <&0 &
child=$!
while :; do
    if ! IFS= read -r stat < "/proc/$guard/stat"; then /bin/kill -KILL -"$group"; exit 126; fi
    rest=${stat##*) }; set -- $rest
    if [ "${20}" != "$expected" ] || [ "$1" = Z ] || [ "$1" = X ]; then /bin/kill -KILL -"$group"; exit 126; fi
    if [ -n "$child" ] && ! kill -0 "$child" 2>/dev/null; then
        wait "$child"; result=$?; printf '%s' "$result" > "$donefile"; child=
    fi
    "$busybox" usleep 100000
 done
SH;
        $self=AsusTechnicalProcess::identity(getmypid());
        try{
            $launch=@proc_open([$this->c['busybox'],'start-stop-daemon','-S','-b','-m','-p',$dir.'/pid','-x',$this->c['busybox'],'--','sh','-c',$shell,'nfqws-command',(string)getmypid(),$self['starttime'],$cmd,$dir.'/exit',$this->c['busybox']],
                [0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes,'/',['PATH'=>NfqwsPlatform::native()?'/usr/sbin:/usr/bin:/sbin:/bin':'/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C']);
            if(!is_resource($launch)||proc_close($launch)!==0)return 126;
            $deadline=AsusTechnicalProcess::uptime()+2;
            do{$pid=AsusTechnicalFiles::read($dir.'/pid',$this->c['owner'],32);if($pid&&preg_match('/^[0-9]+\n?$/D',$pid['raw']))$child=AsusTechnicalProcess::groupIdentity((int)$pid['raw']);if($child)break;usleep(10000);}while(AsusTechnicalProcess::uptime()<$deadline);
            if(!$child)return 126;
            while(true){
                $s=$this->read('state.json');if(($s['activation_id']??null)!==$id||($s['identity']??null)!==$admitted||!AsusTechnicalProcess::active($s,time(),AsusTechnicalProcess::uptime()))break;
                $done=AsusTechnicalFiles::read($dir.'/exit',$this->c['owner'],4);
                if($done&&preg_match('/^[0-9]{1,3}$/D',$done['raw'])){$exit=min(255,(int)$done['raw']);break;}
                $live=AsusTechnicalProcess::groupIdentity($child['pid']);if(!$live||$live['starttime']!==$child['starttime']||$live['boot_id']!==$child['boot_id']||$live['group']!==$child['group']||$live['session']!==$child['session'])break;
                usleep(100000);
            }
        }finally{
            AsusTechnicalProcess::killGroup($child);
            foreach(['pid','exit'] as $name)if(AsusTechnicalFiles::read($dir.'/'.$name,$this->c['owner'],32)!==null)unlink($dir.'/'.$name);
            rmdir($dir);
        }
        return $exit;
    }
}
