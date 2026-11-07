<?php
if(!class_exists('AsusShareResources',false))require_once __DIR__.'/share-resources.php';
if(!class_exists('AsusImportPlan',false))require_once __DIR__.'/import-plan.php';
if(!class_exists('NfqwsNativeConfig',false))require_once NfqwsPlatform::settings()['library'].'/config.php';

/** Local, immutable strategy snapshots. Never writes the ordinary router config. */
final class NfqwsDeviceProfilesLibrary
{
    private string $private;
    private string $resources;
    private string $config;
    private AsusShareRead $reader;
    public function __construct(?string $private=null,?string $resources=null,?string $config=null,private int $owner=0)
    {
        $s=NfqwsPlatform::settings();$this->private=$private??$s['web_config'].'/device-profiles-lab';
        $this->resources=$resources??$s['config'].'/device-profiles';$this->config=$config??$s['config'];
        $this->reader=new AsusShareRead($owner,null,null,true);
    }
    private function directory(string $path,int $mode):void
    {
        clearstatcache(true,$path);
        if(@lstat($path)===false){
            $parent=dirname($path);if(!$this->reader->directory($parent))throw new RuntimeException('storage_unavailable');
            $mask=umask(0077);try{if(!mkdir($path,$mode)||!chmod($path,$mode))throw new RuntimeException('storage_unavailable');}finally{umask($mask);}
        }
        $s=@lstat($path);
        if(!$this->reader->directory($path)||!$s||$s['uid']!==$this->owner||($s['mode']&0777)!==$mode)throw new RuntimeException('storage_unavailable');
    }
    private function id(string $id):void
    {if(!preg_match('/^saved-[a-f0-9]{16}$/D',$id))throw new RuntimeException('invalid_request');}
    private function library(bool $create=false):?string
    {
        if(!$create&&!file_exists($this->private.'/library'))return null;
        $this->directory($this->private,0700);$this->directory($this->private.'/library',0700);return $this->private.'/library';
    }
    public function listing():array
    {
        $dir=$this->library();if($dir===null)return [];$files=scandir($dir);if(count($files)>512)throw new RuntimeException('library_limit');$out=[];
        foreach($files as $name)if(preg_match('/^(saved-[a-f0-9]{16})\.json$/D',$name,$m)){
            $row=$this->entry($m[1]);$out[]=['id'=>$m[1],'name'=>$row['name']];
        }
        if(count($out)>8)throw new RuntimeException('library_limit');return $out;
    }
    public function entry(string $id):array
    {
        $this->id($id);$dir=$this->library();if($dir===null)throw new RuntimeException('strategy_unavailable');
        $path=NfqwsPlatform::guardFile($dir,$id.'.json',$this->owner);$s=$this->reader->stat($path);
        if(!$s||$s['uid']!==$this->owner||($s['mode']&0777)!==0600)throw new RuntimeException('strategy_unavailable');
        $row=json_decode($this->reader->bytes($path,262144),true,16,JSON_THROW_ON_ERROR);
        if(($row['schema_version']??null)!==1||($row['id']??null)!==$id||!is_string($row['name']??null)||!is_array($row['config']??null)||!is_array($row['files']??null))throw new RuntimeException('strategy_unavailable');
        return $row;
    }
    private function locked(callable $fn):mixed
    {
        $this->library(true);$path=NfqwsPlatform::guardFile($this->private,'library.lock',$this->owner);$mask=umask(0077);
        try{$f=fopen($path,'c+b');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');return $fn();}
        finally{flock($f,LOCK_UN);fclose($f);}
    }
    private function current():string
    {
        $path=NfqwsPlatform::guardFile($this->config,'nfqws2.conf',$this->owner);
        return $this->reader->bytes($path,262144);
    }
    public function capture(string $name):array
    {return $this->locked(fn()=>$this->create($name,$this->current(),[]));}
    public function import(string $name,string $document,bool $trustedLua):array
    {
        return $this->locked(function()use($name,$document,$trustedLua){
            $doc=AsusImportDocument::read([$document]);
            if(!array_intersect(array_keys($doc['values']),AsusImportConfig::BLOCKS))throw new RuntimeException('strategy_unavailable');
            $selection=['blocks'=>[],'shared'=>[],'ports'=>[],'files'=>[],'dns'=>[],
                'allow_shared_impact'=>true,'allow_incomplete'=>false,'trusted_lua'=>$trustedLua];
            foreach($doc['values']as $key=>$value)$selection[in_array($key,AsusImportConfig::BLOCKS,true)?'blocks':'shared'][]=['key'=>$key,'value'=>$value];
            foreach($doc['ports']as $key=>$value)$selection['ports'][]=['key'=>$key,'value'=>$value];
            foreach($doc['resources']as $file)$selection['files'][]=['id'=>$file['id']];
            $resources=new AsusShareResources($this->config,$this->owner);$inventory=$resources->inventory();
            $plan=AsusImportPlan::prepare($doc,$selection,$this->current(),$inventory,null,'openwrt');
            if(!$plan['ready'])throw new RuntimeException(in_array('lua_trust',array_column($plan['problems'],'code'),true)?'lua_trust':'profile_import_incomplete');
            return $this->create($name,$plan['config'],$plan['files']);
        });
    }
    private function create(string $name,string $raw,array $imported):array
    {
        if(strlen($name)>256||!preg_match('/^[^\x00-\x1f\x7f]{1,64}$/uD',trim($name)))throw new RuntimeException('invalid_request');
        $displayName=trim($name);
        if(count($this->listing())>=8)throw new RuntimeException('library_limit');
        $config=NfqwsNativeConfig::parse($raw);$source=new AsusShareResources($this->config,$this->owner);
        $inventory=$source->inventory();$files=[];$total=0;
        foreach($inventory['files']as $row)if($row['state']==='available'){
            $file=$source->read($row['id'],$row['sha256']);$files[$row['kind'].'/'.$row['name']]=base64_decode($file['data_base64'],true);
        }
        foreach($imported as $file)$files[$file['kind'].'/'.$file['target_name']]=base64_decode($file['data_base64'],true);
        foreach($files as $bytes)if(($total+=strlen($bytes))>2097152)throw new RuntimeException('runtime_limit');
        $id='saved-'.bin2hex(random_bytes(8));$dir=$this->resources.'/'.$id;$mapping=[];
        foreach($files as $name=>$bytes){
            $mapping['/etc/nfqws2/'.$name]=$dir.'/'.$name;$mapping['/opt/etc/nfqws2/'.$name]=$dir.'/'.$name;
        }
        foreach($config as $key=>&$value)if(str_starts_with($key,'NFQWS_')){
            // Only known input-file operands are rebound. An unsupported external
            // absolute file can never be read by a newly created strategy.
            $tokens=NfqwsResourcePaths::arguments(preg_split('/\s+/',trim($value),-1,PREG_SPLIT_NO_EMPTY),'openwrt');
            foreach($tokens as &$word){
                if(preg_match_all('~(?:^|[=@:])(/[^\s,:]+)~',$word,$paths))foreach($paths[1]as $path){
                    if(!isset($mapping[$path]))throw new RuntimeException('unresolved_profile_resource');
                    $word=str_replace($path,$mapping[$path],$word);
                }
            }unset($word);$value=implode(' ',$tokens);
        }unset($value);
        $config['USER']='nobody';$config['LOG_LEVEL']='0';
        $this->directory($this->resources,0755);$this->directory($dir,0755);$created=[];$temporary=null;
        try{
            foreach(['lists','lua','blobs']as $kind)$this->directory($dir.'/'.$kind,0755);
            $hashes=[];
            foreach($files as $name=>$bytes){
                if(!preg_match('~^(lists|lua|blobs)/[A-Za-z0-9_.-]{1,128}$~D',$name))throw new RuntimeException('unresolved_profile_resource');
                $path=NfqwsPlatform::guardFile(dirname($dir.'/'.$name),basename($name),$this->owner);
                $f=fopen($path,'xb');if(!$f)throw new RuntimeException('storage_unavailable');$created[]=$path;
                try{if(fwrite($f,$bytes)!==strlen($bytes)||!fflush($f)||!chmod($path,0644))throw new RuntimeException('insufficient_space');}finally{fclose($f);}
                $hashes[$name]=hash('sha256',$bytes);
            }
            $meta=['schema_version'=>1,'id'=>$id,'name'=>$displayName,'config'=>$config,'files'=>$hashes];
            $encoded=json_encode($meta,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);
            if(strlen($encoded)>262144)throw new RuntimeException('runtime_limit');
            $temporary=$this->private.'/library/.stage-'.bin2hex(random_bytes(8));$mask=umask(0077);
            try{$f=fopen($temporary,'xb');}finally{umask($mask);}
            if(!$f)throw new RuntimeException('storage_unavailable');
            try{if(fwrite($f,$encoded)!==strlen($encoded)||!fflush($f)||(function_exists('fsync')&&!fsync($f)))throw new RuntimeException('insufficient_space');}finally{fclose($f);}
            $target=NfqwsPlatform::guardFile($this->private.'/library',$id.'.json',$this->owner);
            if(!link($temporary,$target))throw new RuntimeException('storage_unavailable');unlink($temporary);$temporary=null;
            return ['id'=>$id,'name'=>$meta['name']];
        }catch(Throwable $e){
            foreach($created as $path)@unlink($path);
            foreach(['lists','lua','blobs']as $kind)@rmdir($dir.'/'.$kind);@rmdir($dir);throw $e;
        }finally{if($temporary!==null)@unlink($temporary);}
    }
}
