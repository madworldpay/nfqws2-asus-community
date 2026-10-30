<?php
/** Private recovery journal stores only public key files, never tunnel credentials. */
final class AsusTechnicalFiles
{
    public static function directory(string $path,int $owner=0): void
    {
        if($path===''||$path[0]!=='/'||str_contains($path,'/../')||str_contains($path,"\0"))throw new RuntimeException('unsafe_key_file');
        clearstatcache(true,$path);
        if(is_link($path))throw new RuntimeException('unsafe_key_file');
        $s=@lstat($path);
        if(!$s){self::directory(dirname($path),$owner);if(!@mkdir($path,0700))throw new RuntimeException('unsafe_key_file');$s=lstat($path);}
        if(($s['mode']&0170000)!==0040000||($s['uid']!==$owner&&$s['uid']!==0)||(($s['mode']&0022)!==0&&!(($s['mode']&01000)!==0&&$s['uid']===0)))throw new RuntimeException('unsafe_key_file');
        if($path!=='/')self::directory(dirname($path),$owner);
    }
    public static function read(string $path,int $owner=0,int $limit=65536): ?array
    {
        self::directory(dirname($path),$owner);clearstatcache(true,$path);$s=@lstat($path);
        if(!$s)return null;
        if(is_link($path)||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>$limit)throw new RuntimeException('unsafe_key_file');
        $raw=@file_get_contents($path);if(!is_string($raw)||strlen($raw)>$limit)throw new RuntimeException('unsafe_key_file');
        return ['raw'=>$raw,'mode'=>$s['mode']&0777];
    }
    public static function write(string $path,string $raw,int $mode=0600,int $owner=0): void
    {
        self::read($path,$owner);$tmp=$path.'.'.bin2hex(random_bytes(8)).'.new';
        $f=@fopen($tmp,'xb');if(!$f)throw new RuntimeException('unsafe_key_file');
        try{if(!chmod($tmp,$mode)||fwrite($f,$raw)!==strlen($raw)||!fflush($f))throw new RuntimeException('unsafe_key_file');if(function_exists('fsync')&&!fsync($f))throw new RuntimeException('unsafe_key_file');}
        finally{fclose($f);}
        if(!rename($tmp,$path)){@unlink($tmp);throw new RuntimeException('unsafe_key_file');}
    }
    public static function json(string $path,int $owner=0): ?array
    {
        $f=self::read($path,$owner,524288);if(!$f)return null;
        try{$v=json_decode($f['raw'],true,32,JSON_THROW_ON_ERROR);if(!is_array($v))throw new RuntimeException();return $v;}
        catch(Throwable $e){throw new RuntimeException('invalid_state');}
    }
}
final class AsusTechnicalJournal
{
    public function __construct(private string $path,private int $owner=0){}
    public function apply(array $changes): void
    {
        if(AsusTechnicalFiles::read($this->path,$this->owner)!==null)throw new RuntimeException('busy');
        $entries=[];$directories=[];
        foreach($changes as $c){
            if(!is_string($c['path']??null)||!is_string($c['line']??null)||$c['line']===''||strpbrk($c['line'],"\r\n\0")!==false)throw new RuntimeException('unsafe_key_file');
            $missing=[];$parent=dirname($c['path']);while(!file_exists($parent)&&!is_link($parent)){$missing[]=$parent;$parent=dirname($parent);}
            $directories=array_values(array_unique(array_merge($directories,array_reverse($missing))));
            $old=AsusTechnicalFiles::read($c['path'],$this->owner);$raw=$old['raw']??'';
            if(str_contains($raw,$c['line']))throw new RuntimeException('key_conflict');
            $after=$raw.($raw!==''&&!str_ends_with($raw,"\n")?"\n":'').$c['line']."\n";
            if(strlen($after)>65536)throw new RuntimeException('unsafe_key_file');
            $entries[]=['path'=>$c['path'],'line'=>$c['line'],'before'=>$old===null?null:base64_encode($raw),'mode'=>$old['mode']??0600,'after'=>base64_encode($after)];
        }
        AsusTechnicalFiles::write($this->path,json_encode(['version'=>1,'entries'=>$entries,'directories'=>$directories],JSON_THROW_ON_ERROR),0600,$this->owner);
        try{foreach($entries as $e)AsusTechnicalFiles::write($e['path'],base64_decode($e['after']),$e['mode'],$this->owner);}
        catch(Throwable $e){$this->restore();throw $e;}
    }
    public function restore(): void
    {
        $v=AsusTechnicalFiles::json($this->path,$this->owner);if(!$v)return;
        if(($v['version']??null)!==1||!is_array($v['entries']??null)||count($v['entries'])>2)throw new RuntimeException('invalid_state');
        foreach(array_reverse($v['entries']) as $e){
            if(!is_array($e)||!is_string($e['path']??null)||!is_string($e['line']??null)||strpbrk($e['line'],"\r\n\0")!==false)throw new RuntimeException('invalid_state');
            $old=$e['before']===null?null:base64_decode($e['before'],true);$after=base64_decode($e['after'],true);
            if(!is_string($after)||($old!==null&&!is_string($old))||!is_int($e['mode'])||($e['mode']&0022)!==0)throw new RuntimeException('invalid_state');
            $current=AsusTechnicalFiles::read($e['path'],$this->owner);if(!$current)continue;
            if($current['raw']===$after){if($old===null){if(!unlink($e['path']))throw new RuntimeException('unsafe_key_file');}else AsusTechnicalFiles::write($e['path'],$old,$e['mode'],$this->owner);}
            else{
                // Remove complete owned lines only, retaining separator LF and unrelated edits.
                $lines=explode("\n",$current['raw']);$removed=false;$kept=[];foreach($lines as $line){if(!$removed&&$line===$e['line']){$removed=true;continue;}$kept[]=$line;}
                AsusTechnicalFiles::write($e['path'],implode("\n",$kept),$current['mode'],$this->owner);
            }
        }
        foreach(array_reverse($v['directories']??[]) as $dir){$st=@lstat($dir);if($st&&!is_link($dir)&&($st['mode']&0170000)===0040000&&$st['uid']===$this->owner)@rmdir($dir);}
        if(!unlink($this->path))throw new RuntimeException('unsafe_key_file');
    }
}
