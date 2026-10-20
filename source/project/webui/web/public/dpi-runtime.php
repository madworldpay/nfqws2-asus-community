<?php
require_once __DIR__.'/dpi-store.php';
final class AsusDpiRuntime
{
    private const ROOT='/opt/var/lib/nfqws2-asus/dpi-detector';
    public const BUSYBOX='/opt/libexec/nfqws2-asus/busybox';
    public function capabilities(): array
    {
        $status=@file_get_contents('/proc/self/status');
        if(!is_string($status)||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',$status))return ['available'=>false,'code'=>'root_required'];
        foreach(['CapInh','CapAmb'] as $key)if(preg_match('/^'.$key.':\s+(\S+)/m',$status,$m)&&trim($m[1],'0')!=='')return ['available'=>false,'code'=>'unsupported_privileges'];
        foreach(['proc_open','proc_get_status','stream_select','hash_file','chown','chgrp'] as $name)if(!function_exists($name))return ['available'=>false,'code'=>'unsupported_runtime'];
        if(!is_executable(self::BUSYBOX)||!is_executable('/opt/bin/php-cgi')||!is_file('/opt/lib/nfqws2-asus/dpi/guard.sh'))return ['available'=>false,'code'=>'unsupported_runtime'];
        return ['available'=>true,'code'=>'ready'];
    }
    public static function identity(int $pid): ?array
    {
        if($pid<2)return null;$stat=@file_get_contents('/proc/'.$pid.'/stat');$exe=@readlink('/proc/'.$pid.'/exe');
        if(!is_string($stat)||!is_string($exe)||!preg_match('/\) (.*)$/s',$stat,$m))return null;
        $fields=explode(' ',trim($m[1]));
        if(($fields[0]??'Z')==='Z'||!preg_match('/^[0-9]+$/D',$fields[19]??''))return null;
        return ['pid'=>$pid,'starttime'=>$fields[19],'exe'=>$exe,'boot_id'=>trim(file_get_contents('/proc/sys/kernel/random/boot_id'))];
    }
    public function launch(string $jobId,string $kind): array
    {
        $cap=$this->capabilities();if(!$cap['available'])throw new RuntimeException($cap['code']);
        if(!preg_match('/^[0-9a-f]{32}$/D',$jobId)||!in_array($kind,['run','install'],true))throw new RuntimeException('invalid_request');
        $store=new AsusDpiStore();$job=$store->status()['active'];
        if(($job['id']??null)!==$jobId||$job['kind']!==$kind)throw new RuntimeException('missing_job');
        $root=self::ROOT.'/runs';if(is_link($root))throw new RuntimeException('invalid_state');
        if(!is_dir($root)&&!mkdir($root,0700))throw new RuntimeException('invalid_state');
        $run=$root.'/'.$jobId;
        if(is_dir($run)) {
            if(is_link($run))throw new RuntimeException('invalid_state');
            $identity=$job['identity']??null;
            if(is_array($identity)&&self::identity($identity['pid'])===$identity)return $job;
            throw new RuntimeException('interrupted');
        }
        if(!mkdir($run,0700))throw new RuntimeException('invalid_state');
        $deadline=(float)explode(' ',file_get_contents('/proc/uptime'))[0]+($kind==='install'?120:($store->readOptions($jobId)['limits']['total_seconds']));
        file_put_contents($run.'/deadline',(string)$deadline."\n",LOCK_EX);chmod($run.'/deadline',0600);
        $p=@proc_open([self::BUSYBOX,'start-stop-daemon','-S','-b','-p',$run.'/unused-guard-lookup.pid','-x',self::BUSYBOX,'--','sh','/opt/lib/nfqws2-asus/dpi/guard.sh',$jobId],
            [0=>['pipe','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',
            ['PATH'=>'/opt/bin:/usr/bin:/bin','LANG'=>'C','HOME'=>'/'],['bypass_shell'=>true]);
        if(!is_resource($p))throw new RuntimeException('launch_failed');fclose($pipes[0]);$exit=proc_close($p);
        $end=microtime(true)+2;
        do {if(is_file($run.'/ack'))break;usleep(25000);}while(microtime(true)<$end);
        if($exit!==0||!is_file($run.'/ack')){file_put_contents($run.'/cancel',"cancel\n",LOCK_EX);throw new RuntimeException('launch_failed');}
        $fields=preg_split('/\s+/',trim(file_get_contents($run.'/guard.pid')));$identity=self::identity((int)$fields[0]);
        if(!$identity||$identity['starttime']!==($fields[1]??null)){if($store->status()['active']===null)return $job;file_put_contents($run.'/cancel',"cancel\n",LOCK_EX);throw new RuntimeException('launch_failed');}
        $store->attachIdentity($jobId,$identity);return $job;
    }
    public function workdir(string $jobId): string
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$jobId))throw new RuntimeException('invalid_request');
        $base='/tmp/nfqws2-dpi';if(is_link($base))throw new RuntimeException('invalid_state');
        if(!is_dir($base)&&(!mkdir($base,0711)||!chmod($base,0711)))throw new RuntimeException('invalid_state');
        $s=lstat($base);if($s['uid']!==0||($s['mode']&0777)!==0711)throw new RuntimeException('invalid_state');
        $path=$base.'/'.$jobId;if(file_exists($path)||is_link($path)||!mkdir($path,0700))throw new RuntimeException('invalid_state');
        if(!chown($path,65534)||!chgrp($path,65534))throw new RuntimeException('unsupported_privileges');
        return $path;
    }
    /** Only trusted coordinator code supplies argv/cwd. Not exposed by the API. */
    public function probe(string $jobId,array $argv,string $cwd,int $seconds): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$jobId)||$seconds<1||$seconds>1800||count($argv)<1||count($argv)>48)throw new RuntimeException('invalid_request');
        foreach($argv as $arg)if(!is_string($arg)||strlen($arg)>4096||strpbrk($arg,"\r\n\0")!==false)throw new RuntimeException('invalid_request');
        if($cwd!=='/'&&$cwd!=='/tmp/nfqws2-dpi/'.$jobId)throw new RuntimeException('invalid_state');
        $run=self::ROOT.'/runs/'.$jobId;
        if(!is_dir($run)||is_link($run)||!is_file($run.'/ack'))throw new RuntimeException('invalid_state');
        if(is_file($run.'/cancel'))throw new RuntimeException('cancelled');
        if(is_file($run.'/closing'))throw new RuntimeException(self::endingReason($run));
        foreach(['probe.pid','probe.exe','probe.deadline','probe.exit','probe.cwd','probe.request','probe.request.new','g0.stdout','g0.stderr','args'] as $file){if(is_link($run.'/'.$file))throw new RuntimeException('invalid_state');@unlink($run.'/'.$file);}
        foreach(['args'=>implode("\n",$argv)."\n",'probe.deadline'=>(string)((float)explode(' ',file_get_contents('/proc/uptime'))[0]+$seconds)."\n",'g0.stdout'=>'','g0.stderr'=>''] as $file=>$raw){$f=fopen($run.'/'.$file,'xb');if(!$f)throw new RuntimeException('invalid_state');chmod($run.'/'.$file,0600);try{if(fwrite($f,$raw)!==strlen($raw))throw new RuntimeException('invalid_state');}finally{fclose($f);}}
        file_put_contents($run.'/probe.cwd',$cwd."\n",LOCK_EX);chmod($run.'/probe.cwd',0600);
        file_put_contents($run.'/probe.request.new',"ready\n",LOCK_EX);chmod($run.'/probe.request.new',0600);
        if(!rename($run.'/probe.request.new',$run.'/probe.request'))throw new RuntimeException('invalid_state');
        // The guardian spawns and owns the child before any shell registration.
        while(true){clearstatcache();if(is_file($run.'/probe.exit'))break;
            if(is_file($run.'/cancel'))throw new RuntimeException('cancelled');
            if(is_file($run.'/closing'))throw new RuntimeException(self::endingReason($run));
            $fields=preg_split('/\s+/',trim((string)@file_get_contents($run.'/guard.pid')));
            $identity=self::identity((int)($fields[0]??0));
            if(!$identity||$identity['starttime']!==($fields[1]??null))throw new RuntimeException('interrupted');
            usleep(25000);
        }
        $rawExit=trim((string)file_get_contents($run.'/probe.exit'));if(!preg_match('/^[0-9]{1,3}$/D',$rawExit))throw new RuntimeException('invalid_state');$exit=(int)$rawExit;
        $out=@file_get_contents($run.'/g0.stdout',false,null,0,1048577);$err=@file_get_contents($run.'/g0.stderr',false,null,0,65537);
        @unlink($run.'/probe.deadline');@unlink($run.'/g0.stdout');@unlink($run.'/g0.stderr');
        if(!is_string($out)||!is_string($err)||strlen($out)>1048576||strlen($err)>65536)throw new RuntimeException('output_limit');
        if(is_file($run.'/cancel'))throw new RuntimeException('cancelled');
        return ['exit'=>$exit,'stdout'=>$out,'stderr'=>$err];
    }
    private static function endingReason(string $run): string
    {$reason=is_link($run.'/ending.reason')?'':trim((string)@file_get_contents($run.'/ending.reason',false,null,0,32));return in_array($reason,['timed_out','output_limit','cancelled'],true)?$reason:'interrupted';}
    public function stop(string $jobId): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$jobId))throw new RuntimeException('invalid_request');
        $job=(new AsusDpiStore())->status()['active'];
        if(($job['id']??null)!==$jobId)throw new RuntimeException('missing_job');
        $identity=$job['identity']??null;
        if(!is_array($identity)||self::identity($identity['pid'])!==$identity)throw new RuntimeException('interrupted');
        $run=self::ROOT.'/runs/'.$jobId;
        if(is_link($run)||is_link($run.'/cancel'))throw new RuntimeException('invalid_state');
        file_put_contents($run.'/cancel',"cancel\n",LOCK_EX);chmod($run.'/cancel',0600);
        return ['id'=>$jobId,'state'=>'stopping'];
    }
}
