<?php
require_once __DIR__.'/platform.php';

/** One explicit local configuration action. No request supplies a URL or report. */
final class AsusSupportChannelSetup
{
    private const TEMPLATE_SHA256='df6c14b241c9d23355fc3acfbf209e97d18f288a80821b1d2298ba0c43214fda';
    public function __construct(private ?string $config=null,private ?string $template=null,private int $owner=0){}
    private function paths(): array
    {
        if(NfqwsPlatform::native())return [$this->config??'/etc/nfqws2-web/support-relay.json',$this->template??'/usr/share/nfqws2/support-relay-default.json'];
        $opt=realpath('/opt');if(($this->config===null||$this->template===null)&&$opt===false)throw new RuntimeException('invalid_state');
        return [$this->config??$opt.'/etc/nfqws-asus-web/support-relay.json',$this->template??$opt.'/share/nfqws2-asus/support-relay-default.json'];
    }
    private static function noLinks(string $path): void
    {for($p=$path;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');}
    private function directory(string $path): void
    {
        $opt=realpath('/opt');$boundary=$opt!==false&&($path===$opt||str_starts_with($path,$opt.'/'))?$opt:$path;
        for($p=$path;;$p=dirname($p)){
            $s=@lstat($p);if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0022)!==0)throw new RuntimeException('invalid_state');
            if($p===$boundary)break;
        }
    }
    private function read(string $path,int $mode): ?array
    {
        self::noLinks($path);$this->directory(dirname($path));clearstatcache(true,$path);$s=@lstat($path);
        if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||($s['mode']&07777)!==$mode||$s['size']>2048)throw new RuntimeException('invalid_state');
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$opened=fstat($f);if($opened['ino']!==$s['ino']||$opened['dev']!==$s['dev'])throw new RuntimeException('source_changed');$raw=stream_get_contents($f,2049);}finally{fclose($f);}
        clearstatcache(true,$path);$after=@lstat($path);
        if(!is_string($raw)||strlen($raw)!==$s['size']||!$after||$after['ino']!==$s['ino']||$after['dev']!==$s['dev']||$after['mode']!==$s['mode']||$after['uid']!==$s['uid']||$after['gid']!==$s['gid']||$after['nlink']!==1||$after['size']!==$s['size']||hash_file('sha256',$path)!==hash('sha256',$raw))throw new RuntimeException('source_changed');
        return ['raw'=>$raw,'ino'=>$s['ino'],'dev'=>$s['dev'],'uid'=>$s['uid'],'gid'=>$s['gid'],'mode'=>$s['mode'],'size'=>$s['size']];
    }
    private static function legacy(?array $file): bool
    {
        if($file===null)return true;$v=json_decode($file['raw'],true);
        if(!is_array($v))return false;$keys=array_keys($v);sort($keys);
        return $keys===['enabled','url']&&$v['enabled']===false&&$v['url']==='';
    }
    private function factory(string $path): array
    {$v=$this->read($path,0644);if($v===null||hash('sha256',$v['raw'])!==self::TEMPLATE_SHA256)throw new RuntimeException('channel_setup_unavailable');return $v;}
    public function available(): bool
    {
        try{[$config,$template]=$this->paths();if(!self::legacy($this->read($config,0600)))return false;$this->factory($template);return true;}
        catch(Throwable $e){return false;}
    }
    public function connect(): array
    {
        [$config,$template]=$this->paths();$lock=dirname($config).'/support-relay-setup.lock';self::noLinks($lock);$this->read($config,0600);
        clearstatcache(true,$lock);$s=@lstat($lock);
        if($s&&(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||($s['mode']&07777)!==0600||$s['nlink']!==1||$s['size']!==0))throw new RuntimeException('invalid_state');
        $mask=umask(0077);try{$f=@fopen($lock,$s?'r+be':'x+be');}finally{umask($mask);}if(!$f)throw new RuntimeException('busy');
        try{
            $opened=fstat($f);clearstatcache(true,$lock);$current=@lstat($lock);
            if(!$current||$current['ino']!==$opened['ino']||$current['dev']!==$opened['dev']||$current['uid']!==$this->owner||$current['nlink']!==1||($current['mode']&07777)!==0600)throw new RuntimeException('invalid_state');
            if(!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');
            $old=$this->read($config,0600);$factory=$this->factory($template);
            if(($old['raw']??null)===$factory['raw'])return ['connected'=>true];
            if(!self::legacy($old))throw new RuntimeException('channel_setup_unavailable');
            $tmp=dirname($config).'/.support-relay-'.bin2hex(random_bytes(12));$mask=umask(0077);
            try{$out=@fopen($tmp,'xb');}finally{umask($mask);}if(!$out)throw new RuntimeException('invalid_state');
            try{
                $gid=$old['gid']??$factory['gid'];
                if(!chmod($tmp,0600)||(!chgrp($tmp,$gid)&&lstat($tmp)['gid']!==$gid)||fwrite($out,$factory['raw'])!==strlen($factory['raw'])||!fflush($out)||!fsync($out))throw new RuntimeException('invalid_state');
                fclose($out);$out=null;
                if($this->read($config,0600)!==$old)throw new RuntimeException('source_changed');
                if(!rename($tmp,$config))throw new RuntimeException('invalid_state');
                return ['connected'=>true];
            }finally{if(is_resource($out))fclose($out);if(is_file($tmp)&&!is_link($tmp))@unlink($tmp);}
        }finally{flock($f,LOCK_UN);fclose($f);}
    }
}
