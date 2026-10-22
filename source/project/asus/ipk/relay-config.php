<?php
/** Embedded in both maintainer scripts; never reads or rewrites updater journals. */
final class AsusRelayConffile
{
    private string $opt;
    private string $parent;
    private string $stage;
    private string $active;
    public function __construct(string $opt,private string $version,private string $factoryHash,private int $owner=0)
    {
        $real=realpath($opt);
        if($real===false||!is_dir($real)||!preg_match('/^[A-Za-z0-9.+-]{1,80}$/D',$version)||!preg_match('/^[a-f0-9]{64}$/D',$factoryHash))throw new RuntimeException('relay_config_invalid');
        $this->opt=$real;$this->parent=$real.'/var/lib/nfqws2-asus';$this->stage=$this->parent.'/relay-config-preserve';$this->active=$real.'/etc/nfqws-asus-web/support-relay.json';
    }
    private function noLinks(string $path): void
    {for($p=$path;;$p=dirname($p)){if(is_link($p))throw new RuntimeException('relay_config_invalid');if($p===$this->opt)break;if($p==='/'||!str_starts_with($p,$this->opt.'/'))throw new RuntimeException('relay_config_invalid');}}
    private function directory(string $path,bool $create=false,int $mode=0755): void
    {
        $this->noLinks($path);if($path!==$this->opt)$this->directory(dirname($path),$create);clearstatcache(true,$path);$s=@lstat($path);
        if(!$s&&$create){if(!@mkdir($path,$mode))throw new RuntimeException('relay_config_invalid');$s=lstat($path);}
        if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0022)!==0||($mode===0700&&($s['mode']&0777)!==0700))throw new RuntimeException('relay_config_invalid');
    }
    private function read(string $path,int $mode,int $cap=2048): ?array
    {
        $this->noLinks($path);clearstatcache(true,$path);$s=@lstat($path);if(!$s)return null;$this->directory(dirname($path));
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||($s['mode']&07777)!==$mode||$s['nlink']!==1||$s['size']>$cap)throw new RuntimeException('relay_config_invalid');
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('relay_config_invalid');
        try{$opened=fstat($f);if($opened['ino']!==$s['ino']||$opened['dev']!==$s['dev'])throw new RuntimeException('relay_config_invalid');$raw=stream_get_contents($f,$cap+1);}finally{fclose($f);}
        clearstatcache(true,$path);$after=@lstat($path);
        if(!is_string($raw)||strlen($raw)!==$s['size']||!$after||$after['ino']!==$s['ino']||$after['dev']!==$s['dev']||$after['mode']!==$s['mode']||$after['uid']!==$s['uid']||$after['gid']!==$s['gid']||$after['nlink']!==1||$after['size']!==$s['size']||hash_file('sha256',$path)!==hash('sha256',$raw))throw new RuntimeException('relay_config_changed');
        return ['raw'=>$raw,'meta'=>['mode'=>$mode,'size'=>strlen($raw),'sha256'=>hash('sha256',$raw),'uid'=>$s['uid'],'gid'=>$s['gid']],'ino'=>$s['ino'],'dev'=>$s['dev']];
    }
    private function write(string $path,string $raw,int $gid): void
    {
        $this->noLinks($path);$mask=umask(0077);try{$f=@fopen($path,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('relay_config_invalid');
        try{if(!chmod($path,0600)||(!chgrp($path,$gid)&&lstat($path)['gid']!==$gid)||fwrite($f,$raw)!==strlen($raw)||!fflush($f)||!fsync($f))throw new RuntimeException('relay_config_invalid');}finally{fclose($f);}
    }
    private function locked(callable $fn): void
    {
        $this->directory($this->parent,true);$lock=$this->stage.'.lock';$old=$this->read($lock,0600,0);$mask=umask(0077);
        try{$f=@fopen($lock,$old?'r+be':'x+be');}finally{umask($mask);}if(!$f)throw new RuntimeException('relay_config_busy');
        try{
            $opened=fstat($f);$now=$this->read($lock,0600,0);
            if($now===null||$now['ino']!==$opened['ino']||$now['dev']!==$opened['dev'])throw new RuntimeException('relay_config_invalid');
            if(!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('relay_config_busy');
            $fn();
        }finally{flock($f,LOCK_UN);fclose($f);}
        // Keep the empty lock inode: unlinking could split concurrent callers.
    }
    private function installed(): bool
    {
        $path=$this->opt.'/lib/opkg/status';$this->noLinks($path);$s=@lstat($path);if(!$s)return false;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>2097152)throw new RuntimeException('relay_config_invalid');
        $raw=file_get_contents($path,false,null,0,2097153);if(!is_string($raw)||strlen($raw)>2097152)throw new RuntimeException('relay_config_invalid');
        foreach(preg_split('/\n[ \t]*\n/',trim($raw)) as $section)if(preg_match('/^Package: nfqws2-asus$/m',$section)&&preg_match('/^Status: \S+ \S+ (installed|unpacked|half-configured)$/m',$section))return true;
        return false;
    }
    private function identity(?array $file): ?array
    {return $file===null?null:['ino'=>(string)$file['ino'],'dev'=>(string)$file['dev']];}
    private function savedStage(): array
    {
        $this->directory($this->stage,false,0700);$data=$this->read($this->stage.'/metadata.json',0600,4096);
        try{$m=$data===null?null:json_decode($data['raw'],true,16,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('relay_config_invalid');}
        if(!is_array($m)||array_keys($m)!==['schema','version','factory_sha256','original','original_identity','saved_identity','initialize']||$m['schema']!==1||$m['version']!==$this->version||$m['factory_sha256']!==$this->factoryHash||!is_bool($m['initialize']))throw new RuntimeException('relay_config_invalid');
        $expected=$m['original']===null?['metadata.json']:['file','metadata.json'];$names=array_values(array_diff(scandir($this->stage),['.','..']));sort($names);if($names!==$expected)throw new RuntimeException('relay_config_invalid');
        $saved=$m['original']===null?null:$this->read($this->stage.'/file',0600);
        if(($saved['meta']??null)!==$m['original']||$this->identity($saved)!==$m['saved_identity']||($saved!==null&&$m['initialize']))throw new RuntimeException('relay_config_invalid');
        $identity=$m['original_identity'];
        if($saved===null){if($identity!==null)throw new RuntimeException('relay_config_invalid');}
        elseif(!is_array($identity)||array_keys($identity)!==['ino','dev']||!is_string($identity['ino'])||!is_string($identity['dev'])||!preg_match('/^-?[0-9]{1,20}$/D',$identity['ino'])||!preg_match('/^-?[0-9]{1,20}$/D',$identity['dev']))throw new RuntimeException('relay_config_invalid');
        return [$m,$saved];
    }
    public function prepare(): void
    {
        $this->locked(function(){
            $this->noLinks($this->stage);
            if(file_exists($this->stage)){
                [$m]=$this->savedStage();$active=$this->read($this->active,0600);
                if(($active['meta']??null)!==$m['original']||$this->identity($active)!==$m['original_identity'])throw new RuntimeException('relay_config_changed');
                // A retry before unpack may reuse this exact transaction, without rewriting it.
                return;
            }
            $old=$this->read($this->active,0600);$tmp=$this->parent.'/.relay-preserve-'.bin2hex(random_bytes(12));
            if(!mkdir($tmp,0700))throw new RuntimeException('relay_config_invalid');
            try{
                if($old!==null)$this->write($tmp.'/file',$old['raw'],$old['meta']['gid']);
                $meta=['schema'=>1,'version'=>$this->version,'factory_sha256'=>$this->factoryHash,'original'=>$old['meta']??null,'original_identity'=>$this->identity($old),'saved_identity'=>$this->identity($old===null?null:$this->read($tmp.'/file',0600)),'initialize'=>$old===null&&!$this->installed()];
                $this->write($tmp.'/metadata.json',json_encode($meta,JSON_THROW_ON_ERROR),getmygid());
                if($this->read($this->active,0600)!==$old)throw new RuntimeException('relay_config_changed');
                if(!rename($tmp,$this->stage))throw new RuntimeException('relay_config_invalid');
            }finally{if(is_dir($tmp)){@unlink($tmp.'/file');@unlink($tmp.'/metadata.json');@rmdir($tmp);}}
        });
    }
    public function finish(): void
    {
        $this->locked(function(){
            $this->noLinks($this->stage);if(!file_exists($this->stage))return;
            [$m,$saved]=$this->savedStage();
            $factory=$this->read($this->opt.'/share/nfqws2-asus/support-relay-default.json',0644);
            if($factory===null||$factory['meta']['sha256']!==$this->factoryHash)throw new RuntimeException('relay_config_invalid');
            $active=$this->read($this->active,0600);$factoryMeta=array_replace($factory['meta'],['mode'=>0600]);
            if(($active['meta']??null)!==$m['original']){
                if(($active['meta']??null)!==$factoryMeta)throw new RuntimeException('relay_config_changed');
                if($saved!==null){
                    $tmp=dirname($this->active).'/.relay-config-'.bin2hex(random_bytes(12));
                    try{$this->write($tmp,$saved['raw'],$saved['meta']['gid']);if($this->read($this->active,0600)!==$active)throw new RuntimeException('relay_config_changed');if(!rename($tmp,$this->active))throw new RuntimeException('relay_config_invalid');}finally{if(isset($tmp)&&is_file($tmp)&&!is_link($tmp))@unlink($tmp);}
                }elseif(!$m['initialize']){
                    if($this->read($this->active,0600)!==$active||!unlink($this->active))throw new RuntimeException('relay_config_changed');
                }
            }
            $restored=$this->read($this->active,0600);$wanted=$m['initialize']?$factoryMeta:$m['original'];
            if(($restored['meta']??null)!==$wanted)throw new RuntimeException('relay_config_changed');
            // Only the validated closed set belonging to this install is removed.
            if($saved!==null&&!unlink($this->stage.'/file'))throw new RuntimeException('relay_config_invalid');
            if(!unlink($this->stage.'/metadata.json')||!rmdir($this->stage))throw new RuntimeException('relay_config_invalid');
        });
    }
}
