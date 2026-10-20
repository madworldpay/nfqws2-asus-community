<?php
require_once __DIR__.'/dpi-store.php';
require_once __DIR__.'/share-read.php';
/** Explicit copies from NFQWS2's resource directories. No execution or writes. */
final class AsusShareResources
{
    public const FILE_LIMIT=262144;
    public const TOTAL_LIMIT=524288;
    public const COUNT_LIMIT=128;
    private const KINDS=['lists','lua','blobs'];
    private string $root;
    private AsusShareRead $reader;
    public function __construct(?string $root=null,private int $owner=0,private ?array $bundledLua=null)
    {
        $this->root=$root??AsusDpiStore::optPath('/etc/nfqws2');$this->reader=$root===null?new AsusShareRead($owner,realpath('/opt'),'/opt',true):new AsusShareRead($owner,null,null,true);
        if($this->bundledLua===null)$this->bundledLua=$root===null?self::packageLua('/opt',$owner):[];
    }
    /** A pinned firmware-owned /opt alias may resolve to USB or internal storage. */
    public static function packageLua(string $alias='/opt',int $owner=0): array
    {
        try {
            $base=realpath($alias);if($base===false)return [];
            $reader=new AsusShareRead($owner,$base,$alias);
            $path=rtrim($base,'/').'/share/nfqws2-asus/report-baseline.json';
            $stat=$reader->stat($path);
            if(!$stat || $stat['uid']!==$owner || ($stat['mode']&0022)!==0)return [];
            $v=json_decode($reader->bytes($path,131072),true,32,JSON_THROW_ON_ERROR);
            return is_array($v['resources']??null)?$v['resources']:[];
        } catch(Throwable $e) {return [];}
    }
    private function directory(string $path): bool { return $this->reader->directory($path); }
    private static function name(string $name): bool
    {return $name!==''&&$name!=='.'&&$name!=='..'&&strlen($name)<=128&&preg_match('//u',$name)===1&&!preg_match('~[/\\\\\x00-\x1f\x7f]~',$name);}
    private function stat(string $path): ?array { return $this->reader->stat($path); }
    private function bytes(string $path): string { return $this->reader->bytes($path,self::FILE_LIMIT); }
    private function entries(): array
    {
        if(!$this->directory($this->root))throw new RuntimeException('resource_unavailable');
        $files=[];$skipped=0;$truncated=false;
        foreach(self::KINDS as $kind) {
            $dir=$this->root.'/'.$kind;
            if(!is_dir($dir)&&!is_link($dir))continue;
            if(!$this->directory($dir)){$skipped++;continue;}
            $handle=@opendir($dir);if(!$handle){$skipped++;continue;}$count=0;
            try {
                while(($name=readdir($handle))!==false) {
                    if($name==='.'||$name==='..')continue;
                    if(++$count>512){$truncated=true;break;}
                    if(!self::name($name)||str_contains($name,'.notactive')||str_contains($name,'-opkg')||str_contains($name,'.opkg-')){$skipped++;continue;}
                    $path=$dir.'/'.$name;$s=$this->stat($path);if(!$s){$skipped++;continue;}
                    if(count($files)>=self::COUNT_LIMIT){$truncated=true;break;}
                    $files[]=['id'=>substr(hash('sha256',$kind."\0".$name),0,32),'kind'=>$kind,'name'=>$name,'byte_length'=>$s['size'],'path'=>$path];
                }
            } finally {closedir($handle);}
        }
        usort($files,fn($a,$b)=>strcmp($a['kind'].'/'.$a['name'],$b['kind'].'/'.$b['name']));
        return ['files'=>$files,'skipped'=>$skipped,'scan_truncated'=>$truncated];
    }
    public function inventory(): array
    {
        $out=$this->entries();$remaining=2097152;
        foreach($out['files'] as &$row) {
            $path=$row['path'];unset($row['path']);$row['sha256']=null;$row['bundled_lua']=false;
            if($row['byte_length']>self::FILE_LIMIT){$row['state']='too_large';continue;}
            if($row['byte_length']>$remaining){$row['state']='unavailable';$out['scan_truncated']=true;continue;}
            try{$raw=$this->bytes($path);$row['sha256']=hash('sha256',$raw);$row['state']='available';$remaining-=strlen($raw);}
            catch(RuntimeException $e){$row['state']='unavailable';}
            if($row['kind']==='lua'&&$row['state']==='available')foreach($this->bundledLua as $name=>$baseline)if(str_starts_with($name,'lua/')&&preg_match('~^lua/[A-Za-z0-9_.-]+$~D',$name)&&is_array($baseline)&&($baseline['bytes']??null)===$row['byte_length']&&($baseline['sha256']??null)===$row['sha256']){$row['bundled_lua']=true;$row['bundled_name']=substr($name,4);break;}
        }
        return $out;
    }
    public function read(string $id,string $sourceSha): array
    {
        if(!preg_match('/^[a-f0-9]{32}$/D',$id)||!preg_match('/^[a-f0-9]{64}$/D',$sourceSha))throw new RuntimeException('invalid_request');
        foreach($this->entries()['files'] as $row)if($row['id']===$id) {
            if(!$this->directory(dirname($row['path'])))throw new RuntimeException('source_changed');
            $raw=$this->bytes($row['path']);$hash=hash('sha256',$raw);
            if(!hash_equals($sourceSha,$hash))throw new RuntimeException('source_changed');
            unset($row['path']);$utf8=$row['kind']!=='blobs'&&preg_match('//u',$raw)===1&&!str_contains($raw,"\0");
            $row+=['sha256'=>$hash,'encoding'=>$utf8?'utf8':'base64','data_base64'=>base64_encode($raw)];
            if($utf8)$row['text']=$raw;
            return $row;
        }
        throw new RuntimeException('source_changed');
    }
    public function prepare(array $selections): array
    {
        if(!array_is_list($selections)||count($selections)>self::COUNT_LIMIT)throw new RuntimeException('invalid_request');
        $out=[];$seen=[];$total=0;
        foreach($selections as $v) {
            if(!is_array($v)||array_diff(array_keys($v),['id','source_sha256','text'])||!is_string($v['id']??null)||!is_string($v['source_sha256']??null)||isset($seen[$v['id']]))throw new RuntimeException('invalid_request');
            $seen[$v['id']]=true;$row=$this->read($v['id'],$v['source_sha256']);$raw=base64_decode($row['data_base64'],true);
            if(array_key_exists('text',$v)) {
                if($row['encoding']!=='utf8'||!is_string($v['text'])||strlen($v['text'])>self::FILE_LIMIT||preg_match('//u',$v['text'])!==1||str_contains($v['text'],"\0"))throw new RuntimeException('invalid_resource');
                $raw=$v['text'];
            }
            $total+=strlen($raw);if($total>self::TOTAL_LIMIT)throw new RuntimeException('output_limit');
            $out[]=['id'=>$row['id'],'kind'=>$row['kind'],'name'=>$row['name'],'encoding'=>$row['encoding'],
                'source_sha256'=>$row['sha256'],'byte_length'=>strlen($raw),'sha256'=>hash('sha256',$raw),'data_base64'=>base64_encode($raw)];
        }
        return $out;
    }
}
