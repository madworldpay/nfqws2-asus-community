<?php
require_once __DIR__.'/device-profiles-paths.php';
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
    public function __construct(?string $private=null,?string $resources=null,?string $config=null,private int $owner=0,private ?array $bundledLua=null)
    {
        $s=NfqwsPlatform::settings();$this->private=NfqwsDeviceProfilesPaths::readPath($private??$s['web_config'].'/device-profiles-lab');
        $this->resources=NfqwsDeviceProfilesPaths::readPath($resources??$s['config'].'/device-profiles');$this->config=NfqwsDeviceProfilesPaths::readPath($config??$s['config']);
        $this->reader=NfqwsDeviceProfilesPaths::reader($this->config,$owner);
        $this->bundledLua??=AsusShareResources::packageLua('/opt',$owner);
    }
    private function directory(string $path,int $mode):void
    {
        clearstatcache(true,$path);
        if(@lstat($path)===false){
            $parent=dirname($path);if(!$this->reader->directory(NfqwsDeviceProfilesPaths::readPath($parent)))throw new RuntimeException('storage_unavailable');
            $mask=umask(0077);try{if(!mkdir($path,$mode)||!chmod($path,$mode))throw new RuntimeException('storage_unavailable');}finally{umask($mask);}
        }
        $s=@lstat($path);
        if(!$this->reader->directory(NfqwsDeviceProfilesPaths::readPath($path))||!$s||$s['uid']!==$this->owner||($s['mode']&0777)!==$mode)throw new RuntimeException('storage_unavailable');
    }
    public static function validId(mixed $id):bool
    {return is_string($id)&&preg_match('/^(?:stock|saved-[a-f0-9]{16})$/D',$id)===1;}
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
    public function entry(string $id,?array &$observedPin=null):array
    {
        $observedPin=null;if(!self::validId($id))throw new RuntimeException('invalid_request');
        $dir=$this->library();if($dir===null)throw new RuntimeException('strategy_unavailable');
        $path=NfqwsDeviceProfilesPaths::guard($dir,$id.'.json',$this->owner);$s=$this->reader->stat($path);
        if(!$s||$s['uid']!==$this->owner||($s['mode']&0777)!==0600)throw new RuntimeException('strategy_unavailable');
        $fields=array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']);$pin=array_intersect_key($s,$fields);
        $row=json_decode($this->reader->bytes($path,262144),true,32,JSON_THROW_ON_ERROR);
        if(array_intersect_key($this->reader->stat($path)??[],$fields)!==$pin||!$this->reader->directory($dir))throw new RuntimeException('source_changed');
        if(($row['schema_version']??null)!==1||($row['id']??null)!==$id||!is_string($row['name']??null)||!is_array($row['config']??null)||!is_array($row['files']??null))throw new RuntimeException('strategy_unavailable');
        if(array_key_exists('resource_binding_version',$row)||array_key_exists('resource_bindings',$row)){
            if(($row['resource_binding_version']??null)!==1||!is_array($row['resource_bindings']??null)||
                array_keys($row['resource_bindings'])!==array_keys($row['files'])||!is_array($row['mutable_files']??null)||!array_is_list($row['mutable_files']))throw new RuntimeException('source_changed');
            foreach($row['files']as $name=>$sha){
                $binding=$row['resource_bindings'][$name];$keys=is_array($binding)?array_keys($binding):[];sort($keys);
                if(NfqwsResourcePaths::relative($name)===null||!is_string($sha)||!preg_match('/^[a-f0-9]{64}$/D',$sha)||$keys!==['identity','parent'])throw new RuntimeException('source_changed');
                foreach(['identity'=>['ctime','dev','gid','ino','mode','mtime','nlink','size','uid'],'parent'=>['dev','gid','ino','mode','uid']]as $part=>$wanted){
                    $keys=is_array($binding[$part])?array_keys($binding[$part]):[];sort($keys);if($keys!==$wanted)throw new RuntimeException('source_changed');
                    foreach($binding[$part]as $value)if(!is_int($value)||$value<0)throw new RuntimeException('source_changed');
                }
                $file=$binding['identity'];$owner=in_array($name,$row['mutable_files'],true)&&$this->owner===0?65534:$this->owner;
                if($file['mode']!==0100644||$file['uid']!==$owner||$file['nlink']!==1||$file['size']>262144||
                    $binding['parent']['mode']!==0040755||$binding['parent']['uid']!==$this->owner)throw new RuntimeException('source_changed');
            }
        }
        if(array_key_exists('resource_directories',$row)){
            if(($row['resource_binding_version']??null)!==1||!is_array($row['resource_directories']))throw new RuntimeException('source_changed');
            $wanted=['..','lists','lua','blobs','.'];foreach(array_keys($row['files'])as $name){$parent=dirname($name);if(!in_array($parent,$wanted,true))$wanted[]=$parent;}sort($wanted);$keys=array_keys($row['resource_directories']);sort($keys);
            if($keys!==$wanted)throw new RuntimeException('source_changed');
            foreach($row['resource_directories']as $directory=>$record){$keys=is_array($record)?array_keys($record):[];sort($keys);if($keys!==['dev','gid','ino','mode','uid'])throw new RuntimeException('source_changed');
                foreach($record as $value)if(!is_int($value)||$value<0)throw new RuntimeException('source_changed');if($record['mode']!==0040755||$record['uid']!==$this->owner)throw new RuntimeException('source_changed');}
            foreach($row['resource_bindings']as $name=>$record)if($record['parent']!==$row['resource_directories'][dirname($name)])throw new RuntimeException('source_changed');
        }
        if(array_intersect_key($this->reader->stat($path)??[],$fields)!==$pin)throw new RuntimeException('source_changed');$observedPin=$pin;return $row;
    }
    private function locked(callable $fn):mixed
    {
        $this->library(true);$path=NfqwsDeviceProfilesPaths::guard($this->private,'library.lock',$this->owner);$mask=umask(0077);
        try{$f=fopen($path,'c+b');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');return $fn();}
        finally{flock($f,LOCK_UN);fclose($f);}
    }
    private function current():string
    {
        $path=NfqwsDeviceProfilesPaths::guard($this->config,'nfqws2.conf',$this->owner);
        return $this->reader->bytes($path,262144);
    }
    public function capture(string $name):array
    {return $this->locked(function()use($name){$raw=$this->current();return $this->create($name,$raw,[],null,hash('sha256',$raw));});}
    /** Fresh method-free infrastructure. No stock/catalog/current rules read. */
    public function synthesis(array $domains):array
    {
        $code=is_file(__DIR__.'/strategy-synthesis.php')?__DIR__.'/strategy-synthesis.php':dirname(__DIR__,2).'/webui/web/public/strategy-synthesis.php';require_once $code;
        return $this->locked(function()use($domains){
            if(!array_is_list($domains)||!$domains||count($domains)>256)throw new RuntimeException('invalid_request');
            foreach($domains as $host)if(!is_string($host)||!NfqwsStrategySynthesis::domain($host))throw new RuntimeException('invalid_request');
            $domains=array_values(array_unique($domains));sort($domains);
            $source=AsusShareResources::forPicker($this->config,$this->owner,$this->bundledLua,$this->reader);$inventory=$source->inventory();$lua=[];$exclude='';$payloads=[];$pins=[];
            if($inventory['scan_truncated'])throw new RuntimeException('picker_resource_limit');
            foreach($inventory['files']as $file){
                if(($file['bundled_lua']??false)&&in_array($file['bundled_name']??null,['zapret-lib.lua','zapret-antidpi.lua'],true))$lua[$file['bundled_name']]='/opt/etc/nfqws2/lua/'.$file['name'];
                if(($file['bundled_resource']??false)&&$file['kind']==='blobs')foreach(NfqwsStrategySynthesis::packagedPayloads()as $id=>$name)if(($file['bundled_name']??null)===$name){
                    $path='/opt/etc/nfqws2/blobs/'.$file['name'];$payloads[$id]=$path;$pins[$path]=$file['sha256'];
                }
                if(($file['bundled_lua']??false)&&isset($lua[$file['bundled_name']??'']))$pins[$lua[$file['bundled_name']]]=$file['sha256'];
                if($file['kind']==='lists'&&$file['name']==='exclude.list'&&$file['state']==='available')$exclude=base64_decode($source->read($file['id'],$file['sha256'])['data_base64'],true);
            }
            if(count($lua)!==2)throw new RuntimeException('synthesis_lua_unavailable');
            ksort($payloads);$blobArgs='';foreach($payloads as $id=>$path)$blobArgs.=' --blob=synthesis_'.$id.':@'.$path;
            $values=NfqwsStrategySynthesis::bind(NfqwsStrategySynthesis::blank(),[
                'NFQWS_BASE_ARGS'=>'--fastpath-workaround=auto --lua-init=@'.$lua['zapret-lib.lua'].' --lua-init=@'.$lua['zapret-antidpi.lua'].$blobArgs,
                'NFQWS_EXTRA_ARGS'=>'--hostlist=/opt/etc/nfqws2/lists/synthesis-user.list --hostlist-auto=/opt/etc/nfqws2/lists/synthesis-auto.list --hostlist-exclude=/opt/etc/nfqws2/lists/synthesis-exclude.list',
                'NFQWS_ARGS_IPSET'=>'','TCP_PORTS'=>'80,443','UDP_PORTS'=>'443']);
            $imported=[];
            foreach(['synthesis-user.list'=>implode("\n",$domains)."\n",'synthesis-auto.list'=>'','synthesis-exclude.list'=>$exclude."\nt.me\ntelegram.org\ntelegram.me\ntelesco.pe\n"]as $name=>$bytes)$imported[]=['kind'=>'lists','target_name'=>$name,'data_base64'=>base64_encode($bytes)];
            return $this->create('Синтез · пустая основа',AsusImportConfig::replace('',$values),$imported,null,null,$pins);
        });
    }
    public function stock(?string $trustedTemplate=null,bool $packagedInputs=false):array
    {
        if($packagedInputs&&($trustedTemplate!==null||NfqwsPlatform::current()!=='asus-entware'))
            throw new RuntimeException('invalid_request');
        return $this->locked(function()use($trustedTemplate,$packagedInputs){
            if(file_exists($this->private.'/library/stock.json'))return $this->entry('stock');
            $share=NfqwsPlatform::settings()['share'];$defaults=$share.'/defaults';
            $raw=$trustedTemplate??$this->reader->bytes(NfqwsDeviceProfilesPaths::guard($defaults,'nfqws2.conf',$this->owner),262144);
            $inputs=[];
            if($packagedInputs){
                $manifest=$this->reader->bytes(NfqwsDeviceProfilesPaths::guard($share,'report-baseline.json',$this->owner),131072);
                $pins=json_decode($manifest,true,32,JSON_THROW_ON_ERROR)['stock_strategy']??[];
                self::verifyStockBytes($raw,$pins['nfqws2.conf']??[]);
                foreach(['user.list','auto.list','exclude.list','ipset.list','ipset_exclude.list'] as $name){
                    $path=NfqwsDeviceProfilesPaths::guard($this->config.'/lists',$name.'.notactive',$this->owner);
                    $bytes=$this->reader->bytes($path,262144);self::verifyStockBytes($bytes,$pins['lists/'.$name]??[]);
                    $inputs[]=['kind'=>'lists','target_name'=>$name,'data_base64'=>base64_encode($bytes)];
                }
                foreach(['quic_initial.bin','tls_clienthello.bin'] as $name){
                    $path=NfqwsDeviceProfilesPaths::guard($defaults.'/blobs',$name,$this->owner);
                    $bytes=$this->reader->bytes($path,262144);self::verifyStockBytes($bytes,$this->bundledLua['blob/'.$name]??[]);
                    $inputs[]=['kind'=>'blobs','target_name'=>$name,'data_base64'=>base64_encode($bytes)];
                }
                foreach(['zapret-lib.lua','zapret-antidpi.lua','zapret-auto.lua'] as $name){
                    $path=NfqwsDeviceProfilesPaths::guard($share.'/factory/lua',$name,$this->owner);
                    $bytes=$this->reader->bytes($path,262144);self::verifyStockBytes($bytes,$this->bundledLua['lua/'.$name]??[]);
                    $inputs[]=['kind'=>'lua','target_name'=>$name,'data_base64'=>base64_encode($bytes)];
                }
            }
            $this->create('Стоковая стратегия',$raw,$inputs,'stock');return $this->entry('stock');
        });
    }
    private static function verifyStockBytes(string $bytes,array $pin):void
    {
        if(($pin['bytes']??null)!==strlen($bytes)||($pin['sha256']??null)!==hash('sha256',$bytes))
            throw new RuntimeException('source_changed');
    }
    public function import(string $name,string $document,bool $trustedLua):array
    {
        return $this->locked(function()use($name,$document,$trustedLua){
            $doc=AsusImportDocument::read([$document]);
            if(!array_intersect(array_keys($doc['values']),AsusImportConfig::BLOCKS))throw new RuntimeException('strategy_unavailable');
            $selection=['blocks'=>[],'shared'=>[],'ports'=>[],'files'=>[],'dns'=>[],
                'allow_shared_impact'=>true,'allow_incomplete'=>$trustedLua,'trusted_lua'=>$trustedLua];
            foreach($doc['values']as $key=>$value)$selection[in_array($key,AsusImportConfig::BLOCKS,true)?'blocks':'shared'][]=['key'=>$key,'value'=>$value];
            foreach($doc['ports']as $key=>$value)$selection['ports'][]=['key'=>$key,'value'=>$value];
            foreach($doc['resources']as $file)$selection['files'][]=['id'=>$file['id']];
            $resources=new AsusShareResources($this->config,$this->owner,$this->bundledLua,$this->reader);$inventory=$resources->inventory();
            $plan=AsusImportPlan::prepare($doc,$selection,$this->current(),$inventory,null,NfqwsPlatform::current());
            foreach($plan['warnings']as $warning)if(!$trustedLua||($warning['kind']??null)!=='lua_dependencies_unchecked')throw new RuntimeException('profile_import_incomplete');
            if(!$plan['ready'])throw new RuntimeException(in_array('lua_trust',array_column($plan['problems'],'code'),true)?'lua_trust':'profile_import_incomplete');
            return $this->create($name,$plan['config'],$plan['files'],null,$plan['fingerprints']['config'],$plan['fingerprints']['files']);
        });
    }
    private function create(string $name,string $raw,array $imported,?string $fixedId=null,?string $expectedSource=null,?array $expectedResources=null):array
    {
        if(strlen($name)>256||!preg_match('/^[^\x00-\x1f\x7f]{1,64}$/uD',trim($name)))throw new RuntimeException('invalid_request');
        $displayName=trim($name);
        if($fixedId===null&&count($this->listing())>=8)throw new RuntimeException('library_limit');
        $expectedSource??=hash('sha256',$this->current());
        $config=NfqwsNativeConfig::parse($raw);$source=AsusShareResources::forPicker($this->config,$this->owner,null,$this->reader);
        $inventory=$source->inventory();$files=[];$total=0;
        if($inventory['scan_truncated'])throw new RuntimeException('picker_resource_limit');
        foreach($inventory['files']as $row)if($row['state']==='available'){
            $file=$source->read($row['id'],$row['sha256']);$files[$row['kind'].'/'.$row['name']]=base64_decode($file['data_base64'],true);
        }
        foreach($expectedResources??[] as $path=>$sha){
            if(NfqwsResourcePaths::canonical($path)!==$path)throw new RuntimeException('invalid_state');
            $relative=substr($path,strlen('/opt/etc/nfqws2/'));$actual=isset($files[$relative])?hash('sha256',$files[$relative]):null;
            if($actual!==$sha)throw new RuntimeException('source_changed');
        }
        foreach($imported as $file)$files[$file['kind'].'/'.$file['target_name']]=base64_decode($file['data_base64'],true);
        foreach($files as $bytes)if(($total+=strlen($bytes))>2097152)throw new RuntimeException('runtime_limit');
        $id=$fixedId??'saved-'.bin2hex(random_bytes(8));if(!self::validId($id))throw new RuntimeException('invalid_request');
        $dir=$this->resources.'/'.$id;$mapping=[];$mutable=[];
        foreach($files as $name=>$bytes){
            $mapping['/etc/nfqws2/'.$name]=$dir.'/'.$name;$mapping['/opt/etc/nfqws2/'.$name]=$dir.'/'.$name;
        }
        foreach($config as $key=>&$value)if(str_starts_with($key,'NFQWS_')){
            // Only known input-file operands are rebound. An unsupported external
            // absolute file can never be read by a newly created strategy.
            $tokens=NfqwsResourcePaths::arguments(preg_split('/\s+/',trim($value),-1,PREG_SPLIT_NO_EMPTY),'openwrt');
            $kept=[];
            for($i=0;$i<count($tokens);$i++){
                $word=$tokens[$i];$option=explode('=',$word,2)[0];
                if(in_array($option,['--debug','--hostlist-auto-debug'],true)){
                    if(!str_contains($word,'=')&&isset($tokens[$i+1])&&!str_starts_with($tokens[$i+1],'--'))$i++;
                    continue;
                }
                if($option==='--hostlist-auto'){
                    $path=str_contains($word,'=')?substr($word,strpos($word,'=')+1):($tokens[$i+1]??'');
                    if(!preg_match('~^/etc/nfqws2/(lists/([A-Za-z0-9_.-]{1,128}))$~D',$path,$m)||in_array($m[2],['.','..'],true))throw new RuntimeException('unresolved_profile_resource');
                    $relative=$m[1];$mutable[$relative]=true;
                    if(!isset($mapping[$path])){
                        $sourcePath=NfqwsDeviceProfilesPaths::guard($this->config.'/lists',$m[2],$this->owner);
                        if(@lstat($sourcePath)!==false)throw new RuntimeException('unresolved_profile_resource');
                        $files[$relative]='';$mapping[$path]=$dir.'/'.$relative;
                    }
                }
                if(preg_match_all('~(?:^|[=@:])(/[^\s,:]+)~',$word,$paths))foreach($paths[1]as $path){
                    if(!isset($mapping[$path]))throw new RuntimeException('unresolved_profile_resource');
                    $word=str_replace($path,$mapping[$path],$word);
                }
                $kept[]=$word;
            }
            $value=implode(' ',$kept);
        }unset($value);
        if(count($files)>256)throw new RuntimeException('runtime_limit');
        $config['USER']='nobody';$config['LOG_LEVEL']='0';
        $this->directory($this->resources,0755);$this->directory($dir,0755);$created=[];$temporary=null;$temporaryPin=null;$published=false;$bindings=[];
        $fields=array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']);$parentFields=array_flip(['dev','ino','mode','uid','gid']);
        try{
            foreach(['lists','lua','blobs']as $kind)$this->directory($dir.'/'.$kind,0755);
            $hashes=[];
            foreach($files as $name=>$bytes){
                $identity=NfqwsResourcePaths::relative($name);if($identity===null)throw new RuntimeException('unresolved_profile_resource');
                if(str_starts_with($identity['name'],'imported/'))$this->directory($dir.'/'.$identity['kind'].'/imported',0755);
                $path=NfqwsDeviceProfilesPaths::guard(dirname($dir.'/'.$name),basename($name),$this->owner);
                clearstatcache(true,dirname($path));$parent=array_intersect_key(lstat(dirname($path)),$parentFields);
                $mask=umask(0077);try{$f=fopen($path,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('storage_unavailable');
                $initial=array_intersect_key(fstat($f),$fields);$created[$path]=['pin'=>$initial,'raw'=>$bytes];
                try{
                    if(fwrite($f,$bytes)!==strlen($bytes)||!fflush($f))throw new RuntimeException('insufficient_space');
                    $written=array_intersect_key(fstat($f),$fields);$expected=$initial;
                    foreach(['size','mtime','ctime']as $key)$expected[$key]=$written[$key];
                    if($written!==$expected||$written['size']!==strlen($bytes)||array_intersect_key($this->reader->stat($path)??[],$fields)!==$written||
                        $this->reader->bytes($path,262144)!==$bytes)throw new RuntimeException('source_changed');
                    $created[$path]['pin']=$written;
                    if(!chmod($path,0644))throw new RuntimeException('storage_unavailable');
                    if(isset($mutable[$name])&&$this->owner===0&&!chown($path,65534))throw new RuntimeException('storage_unavailable');
                    if(!fsync($f))throw new RuntimeException('storage_unavailable');$pin=array_intersect_key(fstat($f),$fields);$expected=$written;
                    $expected['mode']=0100644;$expected['uid']=isset($mutable[$name])&&$this->owner===0?65534:$this->owner;$expected['ctime']=$pin['ctime'];
                    if($pin!==$expected||array_intersect_key($this->reader->stat($path)??[],$fields)!==$pin||$this->reader->bytes($path,262144)!==$bytes)throw new RuntimeException('source_changed');
                    $created[$path]['pin']=$pin;
                    if(!$this->reader->directory(dirname($path)))throw new RuntimeException('source_changed');clearstatcache(true,dirname($path));$ds=lstat(dirname($path));
                    if(array_intersect_key($ds,$parentFields)!==$parent)throw new RuntimeException('source_changed');$df=fopen(dirname($path),'r');
                    try{if(!$df||array_intersect_key(fstat($df),$fields)!==array_intersect_key($ds,$fields)||!fsync($df))throw new RuntimeException('storage_unavailable');
                        clearstatcache(true,dirname($path));if(array_intersect_key(lstat(dirname($path)),$fields)!==array_intersect_key($ds,$fields))throw new RuntimeException('source_changed');
                    }finally{if(is_resource($df))fclose($df);}
                    if(array_intersect_key(fstat($f),$fields)!==$pin||array_intersect_key($this->reader->stat($path)??[],$fields)!==$pin)throw new RuntimeException('source_changed');
                    $bindings[$name]=['identity'=>$pin,'parent'=>$parent];
                }finally{fclose($f);}
                $hashes[$name]=hash('sha256',$bytes);
            }
            if(hash('sha256',$this->current())!==$expectedSource)throw new RuntimeException('source_changed');
            $directories=['..'=>$this->resources,'.'=>$dir,'lists'=>$dir.'/lists','lua'=>$dir.'/lua','blobs'=>$dir.'/blobs'];
            foreach(array_keys($files)as $name){$parent=dirname($name);$directories[$parent]=$dir.'/'.$parent;}
            foreach($directories as $relative=>&$record){if(!$this->reader->directory($record))throw new RuntimeException('source_changed');clearstatcache(true,$record);$record=array_intersect_key(lstat($record),$parentFields);}unset($record);
            foreach($bindings as $name=>$binding)if($binding['parent']!==$directories[dirname($name)])throw new RuntimeException('source_changed');
            $meta=['schema_version'=>1,'id'=>$id,'name'=>$displayName,'config'=>$config,'files'=>$hashes,'mutable_files'=>array_keys($mutable),
                'resource_binding_version'=>1,'resource_bindings'=>$bindings,'resource_directories'=>$directories];
            $encoded=json_encode($meta,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);
            if(strlen($encoded)>262144)throw new RuntimeException('runtime_limit');
            $temporary=$this->private.'/library/.stage-'.bin2hex(random_bytes(8));$mask=umask(0077);
            try{$f=fopen($temporary,'xb');}finally{umask($mask);}
            if(!$f)throw new RuntimeException('storage_unavailable');
            try{if(fwrite($f,$encoded)!==strlen($encoded)||!fflush($f)||!fsync($f))throw new RuntimeException('insufficient_space');
                $temporaryPin=array_intersect_key(fstat($f),$fields);
                if(array_intersect_key($this->reader->stat($temporary)??[],$fields)!==$temporaryPin||$this->reader->bytes($temporary,262144)!==$encoded)throw new RuntimeException('source_changed');
            }finally{fclose($f);}
            foreach($created as $path=>$owned)if(array_intersect_key($this->reader->stat($path)??[],$fields)!==$owned['pin']||$this->reader->bytes($path,262144)!==$owned['raw'])throw new RuntimeException('source_changed');
            $target=NfqwsDeviceProfilesPaths::guard($this->private.'/library',$id.'.json',$this->owner);
            if(!link($temporary,$target))throw new RuntimeException('storage_unavailable');$published=true;
            if(!unlink($temporary))throw new RuntimeException('storage_unavailable');$temporary=null;
            $df=fopen($this->private.'/library','r');try{if(!$df||!fsync($df))throw new RuntimeException('storage_unavailable');}finally{if(is_resource($df))fclose($df);}
            $row=$this->entry($id,$actualPin);$expected=$temporaryPin;$expected['ctime']=$actualPin['ctime'];
            if($row!==$meta||$actualPin!==$expected)throw new RuntimeException('source_changed');
            return ['id'=>$id,'name'=>$meta['name']];
        }catch(Throwable $e){
            // A possibly published entry or partial/swapped object is evidence.
            // Only exact entire buffers on our observed created inode may go.
            if(!$published){
                foreach($created as $path=>$owned){try{
                    if(array_intersect_key($this->reader->stat($path)??[],$fields)===$owned['pin']&&$this->reader->bytes($path,262144)===$owned['raw']&&
                        array_intersect_key($this->reader->stat($path)??[],$fields)===$owned['pin'])@unlink($path);
                }catch(Throwable $ignored){/* Preserve unknown bytes or names. */}}
                foreach(['lua','blobs']as $kind)@rmdir($dir.'/'.$kind.'/imported');
                foreach(['lists','lua','blobs']as $kind)@rmdir($dir.'/'.$kind);@rmdir($dir);
            }throw $e;
        }finally{if(!$published&&$temporary!==null&&$temporaryPin!==null){try{
            if(array_intersect_key($this->reader->stat($temporary)??[],$fields)===$temporaryPin&&$this->reader->bytes($temporary,262144)===$encoded)@unlink($temporary);
        }catch(Throwable $ignored){/* Preserve an unknown metadata stage. */}}}
    }
}
