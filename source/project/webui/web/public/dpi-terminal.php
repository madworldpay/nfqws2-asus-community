<?php
require_once __DIR__.'/dpi-install.php';
require_once __DIR__.'/dpi-store.php';

/** A browser-bound, fixed Detector terminal. Constructor paths are trusted
 * dependencies; HTTP callers can only send terminal bytes and window sizes. */
final class AsusDpiTerminal
{
    private const FIELDS=['dpiterminalinfo'=>[],'dpiterminalstart'=>['cols','rows','language','request_id'],'dpiterminalpoll'=>['terminal_id','offset'],'dpiterminalinput'=>['terminal_id','data'],'dpiterminalresize'=>['terminal_id','cols','rows'],'dpiterminalstop'=>['terminal_id'],'dpiterminalremove'=>['consent','delete_reports']];
    public function __construct(private string $browser,private ?string $root=null,private int $owner=0,private ?string $helper=null,private mixed $verifiedBinary=null,private mixed $remover=null,private ?AsusDpiStore $admissionStore=null)
    {if(!preg_match('/^[a-f0-9]{64}$/D',$browser))throw new RuntimeException('invalid_state');}

    public static function validate(array $post): void
    {
        $cmd=$post['cmd']??null;if(!is_string($cmd)||!isset(self::FIELDS[$cmd]))throw new RuntimeException('invalid_request');
        $keys=array_keys($post);sort($keys);$expected=array_merge(['cmd','csrf_token'],self::FIELDS[$cmd]);sort($expected);
        if($keys!==$expected)throw new RuntimeException('invalid_request');
        foreach($post as $key=>$value)if(!is_string($value)||strlen($value)>($key==='data'?1368:128))throw new RuntimeException('invalid_request');
        if(isset($post['terminal_id'])&&!preg_match('/^[a-f0-9]{32}$/D',$post['terminal_id']))throw new RuntimeException('invalid_request');
        if(isset($post['request_id'])&&!preg_match('/^[a-f0-9]{32}$/D',$post['request_id']))throw new RuntimeException('invalid_request');
        foreach(['cols'=>[80,240],'rows'=>[10,80],'offset'=>[0,2097152]] as $key=>$bounds)if(isset($post[$key])&&(!preg_match('/^(?:0|[1-9][0-9]{0,6})$/D',$post[$key])||(int)$post[$key]<$bounds[0]||(int)$post[$key]>$bounds[1]))throw new RuntimeException('invalid_request');
        if(isset($post['language'])&&!in_array($post['language'],['ru','en'],true))throw new RuntimeException('invalid_request');
        if($cmd==='dpiterminalremove'&&($post['consent']!=='remove'||!in_array($post['delete_reports'],['0','1'],true)))throw new RuntimeException('invalid_request');
        if(isset($post['data'])){$raw=base64_decode($post['data'],true);if($raw===false||strlen($raw)<1||strlen($raw)>1024||base64_encode($raw)!==$post['data'])throw new RuntimeException('invalid_request');}
    }
    public static function error(Throwable $e): string
    {return in_array($e->getMessage(),['invalid_request','invalid_state','missing_terminal','busy','not_installed','helper_unavailable','launch_failed','unsupported_runtime','unsupported_abi','remove_failed','reports_not_removed'],true)?$e->getMessage():'terminal_failed';}
    private static function noLinks(string $path): void
    {
        if($path===''||$path[0]!=='/'||str_contains($path,"\0"))throw new RuntimeException('invalid_state');
        for($p=$path;$p!=='/';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');
    }
    private function file(string $name,int $max,bool $socket=false): ?array
    {
        $path=$this->root.'/'.$name;clearstatcache(true,$path);$s=@lstat($path);if(!$s)return null;
        if(($s['mode']&0170000)!==($socket?0140000:0100000)||$s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>$max)throw new RuntimeException('invalid_state');
        return $s;
    }
    private function read(string $name,int $max): ?string
    {
        $s=$this->file($name,$max);if(!$s)return null;$f=@fopen($this->root.'/'.$name,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$actual=fstat($f);if($s['ino']!==$actual['ino']||$s['dev']!==$actual['dev'])throw new RuntimeException('invalid_state');$raw=stream_get_contents($f,$max+1);if(!is_string($raw)||strlen($raw)>$max)throw new RuntimeException('invalid_state');return $raw;}finally{fclose($f);}
    }
    private function binary(): string
    {return $this->verifiedBinary!==null?($this->verifiedBinary)():(new AsusDpiInstaller())->binary();}
    private function helper(): string
    {
        $path=$this->helper??(NfqwsPlatform::native()?'/usr/lib/nfqws2/dpi-terminal':AsusDpiStore::optPath('/libexec/nfqws2-asus/dpi-terminal'));
        self::noLinks($path);clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||($s['mode']&0777)!==0755||$s['nlink']!==1||!is_executable($path))throw new RuntimeException('helper_unavailable');
        return $path;
    }
    private function info(): array
    {
        $installed=false;$code=null;
        try{$this->binary();$installed=true;}catch(Throwable $e){$code=$e->getMessage()==='not_installed'?'not_installed':self::error($e);}
        if(!$installed&&$code==='not_installed'&&$this->verifiedBinary===null){
            $cap=(new AsusDpiInstaller())->availability();
            if(($cap['code']??null)==='unsupported_abi')$code='unsupported_abi';
        }
        try{$this->helper();}catch(Throwable $e){return ['available'=>false,'installed'=>$installed,'code'=>self::error($e)];}
        return ['available'=>$installed,'installed'=>$installed,'code'=>$code];
    }
    private function prepare(): void
    {
        $this->root??='/tmp/nfqws2-dpi-terminal';self::noLinks($this->root);
        $missing=[];for($p=dirname($this->root);!is_dir($p);$p=dirname($p))$missing[]=$p;
        foreach(array_reverse($missing) as $p)if(!@mkdir($p,0755)&&!is_dir($p))throw new RuntimeException('invalid_state');
        $mask=umask(0077);try{if(!is_dir($this->root)&&!@mkdir($this->root,0700)&&!is_dir($this->root))throw new RuntimeException('invalid_state');}finally{umask($mask);}
        clearstatcache(true,$this->root);$s=lstat($this->root);
        if(($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700||realpath($this->root)!==$this->root||strlen($this->root.'/control.sock')>107)throw new RuntimeException('invalid_state');
    }
    private function lock(string $name)
    {
        $s=$this->file($name,0);$mask=umask(0077);
        try{$f=@fopen($this->root.'/'.$name,$s?'r+b':'x+b');}finally{umask($mask);}
        if(!$f)$f=@fopen($this->root.'/'.$name,'r+b');if(!$f)throw new RuntimeException('invalid_state');
        $s=$this->file($name,0);$a=fstat($f);if(!$s||$s['ino']!==$a['ino']||$s['dev']!==$a['dev']){fclose($f);throw new RuntimeException('invalid_state');}return $f;
    }
    private function meta(): ?array
    {
        $raw=$this->read('terminal.json',256);if($raw===null)return null;
        try{$m=json_decode($raw,true,8,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(!is_array($m)||array_keys($m)!==['terminal_id','browser','request_id']||!is_string($m['terminal_id'])||!preg_match('/^[a-f0-9]{32}$/D',$m['terminal_id'])||!is_string($m['browser'])||!preg_match('/^[a-f0-9]{64}$/D',$m['browser'])||!is_string($m['request_id'])||!preg_match('/^[a-f0-9]{32}$/D',$m['request_id']))throw new RuntimeException('invalid_state');return $m;
    }
    private function brokerActive(): bool
    {
        $f=$this->lock('broker.lock');try{$free=flock($f,LOCK_EX|LOCK_NB);if($free)flock($f,LOCK_UN);return !$free;}finally{fclose($f);}
    }
    private static function readBytes($f,int $length): string
    {
        $out='';while(strlen($out)<$length){$chunk=fread($f,$length-strlen($out));if($chunk===false||$chunk==='')throw new RuntimeException('terminal_failed');$out.=$chunk;}return $out;
    }
    private function request(string $id,string $command): array
    {
        if($this->file('control.sock',0,true)===null)throw new RuntimeException('terminal_failed');
        $f=@stream_socket_client('unix://'.$this->root.'/control.sock',$errno,$error,1,STREAM_CLIENT_CONNECT);if(!$f)throw new RuntimeException('terminal_failed');
        try{stream_set_timeout($f,2);$sent=0;while($sent<strlen($command)){$n=fwrite($f,substr($command,$sent));if(!$n)throw new RuntimeException('terminal_failed');$sent+=$n;}
            $header=fgets($f,128);if(!is_string($header)||!preg_match('/^DPT1 (running|exited|stopped|expired|output_limit|failed) ([0-9]{1,7}) (-1|[0-9]{1,3}) ([0-9]{1,5})\n$/D',$header,$m)||(int)$m[2]>2097152||(int)$m[4]>32768)throw new RuntimeException('terminal_failed');
            return ['terminal_id'=>$id,'state'=>$m[1],'offset'=>(int)$m[2],'data'=>base64_encode(self::readBytes($f,(int)$m[4])),'exit_code'=>$m[3]==='-1'?null:(int)$m[3]];
        }finally{fclose($f);}
    }
    private function retained(string $id,int $offset=0): array
    {
        $raw=$this->read('status',96);if($raw===null||!preg_match('/^(running|exited|stopped|expired|output_limit|failed) (-1|[0-9]{1,3}) ([0-9]{1,7})\n$/D',$raw,$m)||(int)$m[3]>2097152)throw new RuntimeException('invalid_state');
        $state=$m[1]==='running'?'failed':$m[1];$size=(int)$m[3];if($offset>$size)throw new RuntimeException('invalid_request');
        $s=$this->file('output',2097152);if(!$s||$s['size']!==$size)throw new RuntimeException('invalid_state');
        $f=@fopen($this->root.'/output','rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$a=fstat($f);if($a['ino']!==$s['ino']||$a['dev']!==$s['dev']||fseek($f,$offset))throw new RuntimeException('invalid_state');$data=self::readBytes($f,min(32768,$size-$offset));}finally{fclose($f);}
        return ['terminal_id'=>$id,'state'=>$state,'offset'=>$offset+strlen($data),'data'=>base64_encode($data),'exit_code'=>$m[2]==='-1'?null:(int)$m[2]];
    }
    private function cleanup(): void
    {
        foreach(scandir($this->root) as $name)if(!in_array($name,['.','..','control.lock','broker.lock','terminal.json','control.sock','output','status'],true))throw new RuntimeException('invalid_state');
        foreach(['terminal.json'=>256,'control.sock'=>0,'output'=>2097152,'status'=>96] as $name=>$max)if($this->file($name,$max,$name==='control.sock')!==null&&!@unlink($this->root.'/'.$name))throw new RuntimeException('invalid_state');
    }
    private function start(array $p): array
    {
        $old=$this->meta();
        $active=$this->brokerActive();
        if($old&&hash_equals($old['browser'],$this->browser)&&hash_equals($old['request_id'],$p['request_id'])){
            return $active?$this->request($old['terminal_id'],"P 0\n"):$this->retained($old['terminal_id']);
        }
        if($active){
            if(!$old)throw new RuntimeException('busy');
            $status=$this->read('status',96);
            if(is_string($status)&&str_starts_with($status,'running ')){
                throw new RuntimeException('busy');
            }
            $this->request($old['terminal_id'],"S\n");$end=microtime(true)+2;
            while($this->brokerActive()){if(microtime(true)>=$end)throw new RuntimeException('busy');usleep(10000);}
        }
        $binary=$this->binary();$helper=$this->helper();$this->cleanup();
        $id=bin2hex(random_bytes(16));$meta=json_encode(['terminal_id'=>$id,'browser'=>$this->browser,'request_id'=>$p['request_id']],JSON_THROW_ON_ERROR);
        $mask=umask(0077);try{$f=@fopen($this->root.'/terminal.json','xb');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('invalid_state');try{if(fwrite($f,$meta)!==strlen($meta)||!fflush($f))throw new RuntimeException('invalid_state');}finally{fclose($f);}
        $proc=@proc_open([$helper,$this->root,$binary,dirname($binary),$p['cols'],$p['rows'],$p['language']],
            [0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',[],['bypass_shell'=>true]);
        if(!is_resource($proc)||proc_close($proc)!==0)throw new RuntimeException('launch_failed');
        return $this->request($id,"P 0\n");
    }
    public function handle(array $post): array
    {
        self::validate($post);if($post['cmd']==='dpiterminalinfo')return $this->info();
        if($post['cmd']==='dpiterminalstart'){
            $store=$this->admissionStore??new AsusDpiStore();
            return $store->mutation(function()use($post,$store){
                require_once __DIR__.'/dpi-jobs.php';
                if((new AsusDpiJobs($store))->active()!==null)throw new RuntimeException('busy');
                return $this->lockedHandle($post);
            });
        }
        $value=$this->lockedHandle($post);
        return $post['cmd']==='dpiterminalremove'?$this->remove($post['delete_reports']==='1'):$value;
    }
    private function lockedHandle(array $post): array
    {
        $this->prepare();$lock=$this->lock('control.lock');
        try{if(!flock($lock,LOCK_EX))throw new RuntimeException('invalid_state');
            if($post['cmd']==='dpiterminalstart')return $this->start($post);
            if($post['cmd']==='dpiterminalremove'){$this->stopOwned();return [];}
            $m=$this->meta();if(!$m||!hash_equals($m['browser'],$this->browser)||!hash_equals($m['terminal_id'],$post['terminal_id']))throw new RuntimeException('missing_terminal');
            if(!$this->brokerActive())return $this->retained($m['terminal_id'],isset($post['offset'])?(int)$post['offset']:0);
            $command=match($post['cmd']){'dpiterminalpoll'=>'P '.$post['offset']."\n",'dpiterminalinput'=>'I '.strlen(base64_decode($post['data'],true))."\n".base64_decode($post['data'],true),'dpiterminalresize'=>'R '.$post['cols'].' '.$post['rows']."\n",'dpiterminalstop'=>"S\n"};
            return $this->request($m['terminal_id'],$command);
        }finally{flock($lock,LOCK_UN);fclose($lock);}
    }
    private function stopOwned(): void
    {
        if($this->brokerActive()){
            $m=$this->meta();if(!$m||!hash_equals($m['browser'],$this->browser))throw new RuntimeException('busy');
            $this->request($m['terminal_id'],"S\n");$end=microtime(true)+2;
            while($this->brokerActive()){if(microtime(true)>=$end)throw new RuntimeException('busy');usleep(10000);}
        }
    }
    private function remove(bool $reports): array
    {
        if($this->remover!==null)return ($this->remover)($reports);
        require_once __DIR__.'/dpi-remove.php';
        return (new AsusDpiRemoval(null,null,$this->admissionStore))->remove($reports);
    }
}
