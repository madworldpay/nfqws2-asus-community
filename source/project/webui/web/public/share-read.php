<?php
/** Fixed-source readers share the same ownership, fd and path checks. */
final class AsusShareRead
{
    private ?array $anchor=null;
    public function __construct(private int $owner=0,private ?string $boundary=null,private ?string $alias=null,private bool $mutableFiles=false)
    {
        if($boundary!==null){$this->boundary=rtrim($boundary,'/');clearstatcache(true);$s=@lstat($this->boundary);$a=$alias===null?false:@lstat($alias);
            if($s&&$a&&$a['uid']===$owner&&($s['mode']&0170000)===0040000&&$s['uid']===$owner&&($s['mode']&0022)===0&&realpath($alias)===$this->boundary)$this->anchor=$s;
        }
    }
    /** ASUS owns the /opt alias; its USB mount parents can be writable.
     * Pin that one boundary, then require safe directories below it. */
    private function anchored(): bool
    {
        if($this->boundary===null)return true;
        clearstatcache(true);$s=@lstat($this->boundary);$a=$this->alias===null?false:@lstat($this->alias);
        if(!$this->anchor||!$s||!$a||$a['uid']!==$this->owner||realpath($this->alias)!==$this->boundary)return false;
        foreach(['dev','ino','mode','uid','gid'] as $key)if($s[$key]!==$this->anchor[$key])return false;
        return true;
    }
    public function directory(string $path): bool
    {
        if(!$this->anchored()||($this->boundary!==null&&$path!==$this->boundary&&!str_starts_with($path,$this->boundary.'/')))return false;
        for($p=$path;$p!=='/'&&$p!=='.';$p=dirname($p)) {
            clearstatcache(true,$p);$s=@lstat($p);
            if(!$s||($s['mode']&0170000)!==0040000||!in_array($s['uid'],[0,$this->owner],true))return false;
            // Root-owned sticky /tmp is safe for an already-owned child. Other
            // writable ancestors could redirect this privileged reader.
            if(($s['mode']&0022)!==0&&!($s['uid']===0&&($s['mode']&01000)!==0))return false;
            if($p===$this->boundary)break;
        }
        return $path!==''&&$path[0]==='/';
    }
    public function stat(string $path): ?array
    {
        clearstatcache(true,$path);$s=@lstat($path);
        return $s&&($s['mode']&0170000)===0100000&&in_array($s['uid'],[$this->owner,65534],true)&&$s['nlink']===1&&($this->mutableFiles||($s['mode']&0002)===0)?$s:null;
    }
    private static function same(array $a,array $b): bool
    {
        foreach(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime'] as $key)if($a[$key]!==$b[$key])return false;
        return true;
    }
    public function bytes(string $path,int $limit): string
    {
        if(!$this->directory(dirname($path)))throw new RuntimeException('source_changed');
        $before=$this->stat($path);if(!$before)throw new RuntimeException('source_changed');
        if($before['size']>$limit)throw new RuntimeException('file_too_large');
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('resource_unavailable');
        try {
            $opened=fstat($f);if(!$opened||!self::same($before,$opened))throw new RuntimeException('source_changed');
            $raw=stream_get_contents($f,$limit+1);$after=fstat($f);$named=$this->stat($path);
            if(!is_string($raw)||strlen($raw)!==$before['size']||!$after||!$named||!self::same($before,$after)||!self::same($before,$named)||!$this->directory(dirname($path)))throw new RuntimeException('source_changed');
            return $raw;
        } finally {fclose($f);}
    }
}
