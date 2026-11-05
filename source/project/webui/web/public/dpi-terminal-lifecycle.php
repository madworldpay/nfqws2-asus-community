<?php
/** Fixed broker admission and privileged package shutdown. No browser paths. */
final class AsusDpiTerminalLifecycle
{
    private string $root;
    public function __construct(?string $root=null,private int $owner=0)
    {$this->root=$root??'/tmp/nfqws2-dpi-terminal';}
    private function prepare(): void
    {
        if($this->root===''||$this->root[0]!=='/'||str_contains($this->root,"\0"))throw new RuntimeException('invalid_state');
        for($p=$this->root;$p!=='/';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');
        $mask=umask(0077);try{if(!is_dir($this->root)&&!@mkdir($this->root,0700))throw new RuntimeException('invalid_state');}finally{umask($mask);}
        clearstatcache(true,$this->root);$s=@lstat($this->root);
        if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700||realpath($this->root)!==$this->root)throw new RuntimeException('invalid_state');
    }
    private function file(string $name,bool $socket=false): ?array
    {
        $path=$this->root.'/'.$name;clearstatcache(true,$path);$s=@lstat($path);if(!$s)return null;
        if(($s['mode']&0170000)!==($socket?0140000:0100000)||$s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']!==0)throw new RuntimeException('invalid_state');
        return $s;
    }
    private function lock(string $name)
    {
        $s=$this->file($name);$mask=umask(0077);try{$f=@fopen($this->root.'/'.$name,$s?'r+b':'x+b');}finally{umask($mask);}
        if(!$f)$f=@fopen($this->root.'/'.$name,'r+b');if(!$f)throw new RuntimeException('invalid_state');
        $s=$this->file($name);$a=fstat($f);if(!$s||$s['ino']!==$a['ino']||$s['dev']!==$a['dev']){fclose($f);throw new RuntimeException('invalid_state');}return $f;
    }
    private function active(): bool
    {
        $f=$this->lock('broker.lock');try{$free=flock($f,LOCK_EX|LOCK_NB);if($free)flock($f,LOCK_UN);return !$free;}finally{fclose($f);}
    }
    private function locked(callable $fn,bool $wait=false): mixed
    {
        $this->prepare();$f=$this->lock('control.lock');$until=hrtime(true)/1e9+3;
        try{while(!flock($f,LOCK_EX|LOCK_NB)){if(!$wait||hrtime(true)/1e9>=$until)throw new RuntimeException('busy');usleep(10000);}return $fn();}
        finally{flock($f,LOCK_UN);fclose($f);}
    }
    /** Caller already owns the Detector store's mutation lease. */
    public function idle(callable $fn): mixed
    {return $this->locked(function()use($fn){if($this->active())throw new RuntimeException('busy');return $fn();});}
    /** Package hooks run as root and may stop the broker of any browser. */
    public function stop(): void
    {
        if(@lstat($this->root)===false)return;
        $this->locked(function(){
            if(!$this->active())return;
            if($this->file('control.sock',true)===null)throw new RuntimeException('invalid_state');
            $f=@stream_socket_client('unix://'.$this->root.'/control.sock',$errno,$error,1,STREAM_CLIENT_CONNECT);
            if(!$f)throw new RuntimeException('terminal_failed');
            try{stream_set_timeout($f,2);if(fwrite($f,"S\n")!==2||!preg_match('/^DPT1 (?:stopped|exited|expired|output_limit|failed) 0 (?:-1|[0-9]{1,3}) 0\n$/D',(string)fgets($f,128)))throw new RuntimeException('terminal_failed');}finally{fclose($f);}
            $until=hrtime(true)/1e9+3;while($this->active()){if(hrtime(true)/1e9>=$until)throw new RuntimeException('busy');usleep(10000);}
        },true);
    }
}

// PHP-CGI -q -f omits SCRIPT_FILENAME; argv[0] still identifies the exact file.
if(realpath($_SERVER['SCRIPT_FILENAME']??($argv[0]??''))===__FILE__){
    if(isset($_SERVER['REQUEST_METHOD'])||!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(1);
    $args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);
    if($args!==['stop'])exit(2);
    try{(new AsusDpiTerminalLifecycle())->stop();}catch(Throwable $e){file_put_contents('php://stderr',"Detector terminal did not stop.\n");exit(1);}
}
