<?php
require_once __DIR__.'/update-prepare.php';
final class AsusUpdateRollback
{
    private const CAP=67108864;
    private const META=['control','conffiles','preinst','postinst','prerm','postrm','md5sums','sha256sums','busybox-migration-aarch64-3.10','busybox-migration-armv7-2.6','busybox-migration-armv7-3.2'];
    /** Factory bytes pinned to the supported ASUS80/81/82 package closures. */
    private const CONFFILE_SEEDS=[
        'etc/nfqws-asus-web/auth.json'=>['sha256'=>'aed0034928bb1bba0d579a176c237f1bef73887e154a359a8de3b877792d0369','base64'=>'ewogICJtb2RlIjogInN5c3RlbSIsCiAgInVzZXJuYW1lIjogInJvb3QiLAogICJwYXNzd29yZF9oYXNoIjogIiQyeSQxMCRCbFY3R0UuQVZ5NlkvZ25iUkNZR3hPQVJwSHhFZnE2NElRVnd5bGhBSlV2VjBQWWFQMmM3MiIKfQo='],
        'etc/nfqws-asus-web/support-relay.json'=>['sha256'=>'df6c14b241c9d23355fc3acfbf209e97d18f288a80821b1d2298ba0c43214fda','base64'=>'eyJlbmFibGVkIjp0cnVlLCJ1cmwiOiJodHRwczovL21hZDEzbWFuc3Byb2Z5MTMuYXN1c2NvbW0uY29tOjU0NDMvbmZxd3Mtc3VwcG9ydC92MS9yZXBvcnRzIiwiZHBpX2F0dGFjaG1lbnRzX2VuYWJsZWQiOnRydWUsInNoYXJpbmdfdjNfZW5hYmxlZCI6dHJ1ZSwic2hhcmluZ192NF9lbmFibGVkIjp0cnVlfQo='],
    ];
    private const OWNER_FILES=['etc/nfqws-asus-web/ark-backup.json','etc/nfqws-asus-web/smartdns/draft.json','etc/nfqws-asus-web/smartdns/resume-intent.json'];
    private static function tree(string $root,int $owner,bool $migration=false):array
    {
        AsusUpdateStore::noLinks($root);if(@lstat($root)===false)return ['present'=>false,'directories'=>[],'files'=>[]];$dirs=[];$files=[];$total=0;
        $scan=function(string $name)use(&$scan,&$dirs,&$files,&$total,$root,$owner,$migration){$p=$root.($name===''?'':'/'.$name);AsusUpdateStore::noLinks($p);$s=@lstat($p);$mutable=$migration&&preg_match('~^(?:snapshot|stage\.[1-9][0-9]*)/lists/[a-zA-Z0-9_.-]+$~D',$name)===1;if(!$s||!($s['uid']===$owner||$mutable&&$s['uid']===65534)||($s['mode']&07000)!==0||!$mutable&&($s['mode']&0022)!==0)throw new RuntimeException('rollback_unavailable');
            if($migration&&$name!==''&&!preg_match('~^(?:(?:snapshot|stage\.[1-9][0-9]*)/(?:config|auth|ark|presence|manifest(?:\.new)?|(?:lists|blobs)(?:/[a-zA-Z0-9_@+.-]+)*)|(?:snapshot|blob-snapshot|stage\.[1-9][0-9]*|blob-stage\.[1-9][0-9]*)|(?:blob-snapshot|blob-stage\.[1-9][0-9]*)/(?:blobs(?:/[a-zA-Z0-9_@+.-]+)*|presence|manifest(?:\.new)?|restored(?:\.new)?)|data-restored(?:\.new)?|complete|defaults-initialized)$~D',$name))throw new RuntimeException('rollback_unavailable');
            if(($s['mode']&0170000)===0040000){$dirs[$name]=['mode'=>$s['mode']&0777,'uid'=>$s['uid'],'gid'=>$s['gid']];foreach(scandir($p) as $child)if($child!=='.'&&$child!=='..'){if(!preg_match('/^[a-zA-Z0-9_@+.-]{1,128}$/D',$child))throw new RuntimeException('rollback_unavailable');$scan($name===''?$child:$name.'/'.$child);}return;}
            if(count($files)>=512)throw new RuntimeException('rollback_unavailable');$files[$name]=self::file($p,$owner,self::CAP,$mutable);$total+=$files[$name]['size'];if($total>self::CAP)throw new RuntimeException('rollback_unavailable');
        };$scan('');ksort($dirs);ksort($files);return ['present'=>true,'directories'=>$dirs,'files'=>$files];
    }
    private static function history(string $opt,int $owner):array
    {
        $out=[];foreach(glob($opt.'/etc/nfqws2-asus-migration.previous.*')?:[] as $path){if(count($out)>=1000||!preg_match('/^nfqws2-asus-migration\.previous\.([1-9][0-9]{0,2}|1000)$/D',basename($path)))throw new RuntimeException('rollback_unavailable');$tree=self::tree($path,$owner,true);$s=lstat($path);$out[basename($path)]=['ino'=>$s['ino'],'dev'=>$s['dev'],'sha256'=>hash('sha256',json_encode($tree,JSON_THROW_ON_ERROR))];}ksort($out);return $out;
    }
    private static function relayLease(string $opt,int $owner)
    {
        $parent=$opt.'/var/lib/nfqws2-asus';AsusUpdateStore::noLinks($parent);if(!is_dir($parent)&&!mkdir($parent,0755,true))throw new RuntimeException('rollback_unavailable');
        for($dir=$parent;;$dir=dirname($dir)){$s=@lstat($dir);if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$owner||($s['mode']&0022)!==0)throw new RuntimeException('rollback_unavailable');if($dir===$opt)break;if(!str_starts_with($dir,$opt.'/'))throw new RuntimeException('rollback_unavailable');}
        $path=$parent.'/relay-config-preserve.lock';AsusUpdateStore::noLinks($path);$before=@lstat($path);if($before)self::file($path,$owner,0);$mask=umask(0077);try{$f=@fopen($path,$before?'r+b':'x+b');}finally{umask($mask);}if(!$f)throw new RuntimeException('rollback_unavailable');
        $now=@lstat($path);$opened=fstat($f);if(!$now||$now['ino']!==$opened['ino']||$now['dev']!==$opened['dev']||($now['mode']&0777)!==0600||!flock($f,LOCK_EX|LOCK_NB)){fclose($f);throw new RuntimeException('rollback_unavailable');}return $f;
    }
    private static function captureAux(string $opt,string $destination,int $owner,bool $copy=true):array
    {
        $lease=self::relayLease($opt,$owner);try{
            $stage=$opt.'/var/lib/nfqws2-asus/relay-config-preserve';AsusUpdateStore::noLinks($stage);if(@lstat($stage)!==false)throw new RuntimeException('recovery_required');
            $aux=['migration'=>self::tree($opt.'/etc/nfqws2-asus-migration',$owner,true),'history'=>self::history($opt,$owner),'owners'=>[]];
            if(isset($aux['migration']['directories']['snapshot'])&&!isset($aux['migration']['files']['data-restored'])&&!isset($aux['migration']['files']['complete']))throw new RuntimeException('recovery_required');
            foreach($aux['migration']['files'] as $name=>$meta)if($copy)self::copy($opt.'/etc/nfqws2-asus-migration/'.$name,$destination.'/aux/migration/'.$name,$meta,$owner);
            foreach(self::OWNER_FILES as $name){AsusUpdateStore::noLinks($opt.'/'.$name);$meta=@lstat($opt.'/'.$name)===false?null:self::file($opt.'/'.$name,$owner,131072);$aux['owners'][$name]=$meta;if($copy&&$meta!==null)self::copy($opt.'/'.$name,$destination.'/aux/owners/'.$name,$meta,$owner);}
            return $aux;
        }finally{flock($lease,LOCK_UN);fclose($lease);}
    }
    private static function file(string $path,int $owner,int $cap=self::CAP,bool $mutable=false):array
    {
        AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||($s['mode']&0170000)!==0100000||$s['nlink']!==1||!($s['uid']===$owner||$mutable&&$s['uid']===65534)||($s['mode']&07000)!==0||!$mutable&&($s['mode']&0022)!==0||$s['size']>$cap)throw new RuntimeException('rollback_unavailable');
        $hash=hash_file('sha256',$path);if(!is_string($hash))throw new RuntimeException('rollback_unavailable');
        return ['mode'=>$s['mode']&0777,'size'=>$s['size'],'sha256'=>$hash,'uid'=>$s['uid'],'gid'=>$s['gid']];
    }
    private static function relative(string $path,string $opt):string
    {
        if(str_starts_with($path,'/opt/'))$path=substr($path,5);elseif(str_starts_with($path,$opt.'/'))$path=substr($path,strlen($opt)+1);else throw new RuntimeException('rollback_unavailable');
        if(!preg_match('~^[a-zA-Z0-9_@+.-]+(?:/[a-zA-Z0-9_@+.-]+)*$~D',$path)||strlen('opt/'.$path)>255||array_intersect(explode('/',$path),['.','..']))throw new RuntimeException('rollback_unavailable');return $path;
    }
    private static function database(string $status):array
    {
        $own=null;$foreign=[];
        foreach(trim($status)===''?[]:preg_split('/\n[ \t]*\n/',trim($status)) as $section){
            $row=AsusUpdatePackage::fields($section);
            if(($row['Package']??null)==='nfqws2-asus'){
                // Opkg's postinst can run before the new live row is committed.
                // Historical absent versions never identify that in-flight payload.
                if(str_ends_with($row['Status']??'',' not-installed')){AsusUpdatePackage::database($section,true);continue;}
                if($own!==null)throw new RuntimeException('rollback_failed');$own=$row;
            }else $foreign[]=$section;
        }
        $db=$foreign===[]?[]:AsusUpdatePackage::database(implode("\n\n",$foreign));ksort($db);foreach($db as &$row)ksort($row);unset($row);
        return [$own,hash('sha256',json_encode($db,JSON_THROW_ON_ERROR))];
    }
    private static function conffileMap(string $text,string $opt):array
    {
        if(trim($text)==='')return [];$parts=preg_split('/\s+/',trim($text));if(count($parts)>4||count($parts)%2!==0)throw new RuntimeException('rollback_unavailable');$out=[];
        for($i=0;$i<count($parts);$i+=2){$name=self::relative($parts[$i],$opt);$hash=$parts[$i+1];if(!isset(self::CONFFILE_SEEDS[$name])||isset($out[$name])||!hash_equals(self::CONFFILE_SEEDS[$name]['sha256'],$hash))throw new RuntimeException('rollback_unavailable');$out[$name]=$hash;}
        ksort($out);return $out;
    }
    private static function conffiles(array $own,array $metadata,string $opt):array
    {
        $map=self::conffileMap($own['Conffiles']??'',$opt);$declared=[];
        if(isset($metadata['conffiles']))foreach(preg_split('/\s+/',trim((string)file_get_contents($opt.'/lib/opkg/info/nfqws2-asus.conffiles'))) as $path){
            if($path==='')continue;$name=self::relative($path,$opt);if(!isset(self::CONFFILE_SEEDS[$name])||isset($declared[$name]))throw new RuntimeException('rollback_unavailable');$declared[$name]=true;
        }
        ksort($declared);if(array_keys($map)!==array_keys($declared))throw new RuntimeException('rollback_unavailable');return $map;
    }
    private static function conffileSeed(string $name):string
    {
        $seed=self::CONFFILE_SEEDS[$name]??null;$raw=$seed===null?false:base64_decode($seed['base64'],true);
        if(!is_string($raw)||!hash_equals($seed['sha256'],hash('sha256',$raw)))throw new RuntimeException('rollback_unavailable');return $raw;
    }
    private static function copy(string $from,string $to,array $meta,int $owner):void
    {
        if(!is_dir(dirname($to))&&!mkdir(dirname($to),0700,true))throw new RuntimeException('insufficient_space');AsusUpdateStore::noLinks($to);
        $in=@fopen($from,'rb');$out=@fopen($to,'xb');if(!$in||!$out)throw new RuntimeException('insufficient_space');
        try{$s=fstat($in);if($s['uid']!==$meta['uid']||$s['nlink']!==1||($s['mode']&0170000)!==0100000||stream_copy_to_stream($in,$out,$meta['size']+1)!==$meta['size']||!fflush($out)||!fsync($out)||!chmod($to,0600))throw new RuntimeException('rollback_unavailable');}finally{fclose($in);fclose($out);}
        if(hash_file('sha256',$to)!==$meta['sha256']||self::file($from,$owner,self::CAP,true)!==$meta)throw new RuntimeException('settings_changed');
    }
    private static function indexDirectory(string $opt,int $owner):string
    {return self::managerDirectory($opt,$owner,true);}
    private static function managerDirectory(string $opt,int $owner,bool $indexes):string
    {
        return self::dataDirectory($opt,$opt.'/lib/opkg'.($indexes?'/info':''),$owner);
    }
    private static function dataDirectory(string $opt,string $directory,int $owner):string
    {
        AsusUpdateStore::noLinks($directory);
        for($p=$directory;;$p=dirname($p)){
            clearstatcache(true,$p);$s=@lstat($p);
            if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$owner||($s['mode']&07022)!==0)throw new RuntimeException('rollback_unavailable');
            if($p===$opt)break;if(!str_starts_with($p,$opt.'/'))throw new RuntimeException('rollback_unavailable');
        }return $directory;
    }
    /** Only fixed manager data may retain 0666 from a legacy umask. */
    private static function indexFile(string $path,int $owner,int $cap=131072):array
    {
        AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$before=@lstat($path);
        if(!$before||($before['mode']&0170000)!==0100000||$before['uid']!==$owner||$before['nlink']!==1||($before['mode']&07000)!==0||(($before['mode']&0022)!==0&&($before['mode']&0777)!==0666)||$before['size']>$cap)throw new RuntimeException('rollback_unavailable');
        $f=@fopen($path,'rb');if(!$f)throw new RuntimeException('rollback_unavailable');
        $identity=fn($s)=>array_intersect_key($s,array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));
        try{
            $opened=fstat($f);if($identity($opened)!==$identity($before))throw new RuntimeException('rollback_unavailable');
            $raw=stream_get_contents($f,$cap+1);$after=fstat($f);
            AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$current=@lstat($path);
            if(!is_string($raw)||strlen($raw)!==$before['size']||$identity($after)!==$identity($before)||!$current||$identity($current)!==$identity($before))throw new RuntimeException('rollback_unavailable');
            // Manager data can be legacy-writable. Recheck through the same
            // validated handle, with the same cap even if it grows mid-read.
            if(!rewind($f))throw new RuntimeException('rollback_unavailable');
            $again=stream_get_contents($f,$cap+1);$after=fstat($f);
            if(!is_string($again)||$again!==$raw||$identity($after)!==$identity($before))throw new RuntimeException('rollback_unavailable');
            AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$current=@lstat($path);if(!$current||$identity($current)!==$identity($before))throw new RuntimeException('rollback_unavailable');
            return ['raw'=>$raw,'identity'=>$identity($before),'sha256'=>hash('sha256',$raw)];
        }finally{fclose($f);}
    }
    /** A stable snapshot of the fixed status file; semantic checks stay with
     * the caller and this method never repairs permissions or manager state. */
    public static function managerStatus(string $opt,int $owner):string
    {
        $directory=self::managerDirectory($opt,$owner,false);$record=self::indexFile($directory.'/status',$owner,2097152);
        self::managerDirectory($opt,$owner,false);return $record['raw'];
    }
    private static function configPaths(string $opt,int $owner):array
    {
        $etc=self::dataDirectory($opt,$opt.'/etc',$owner);$paths=[];$main=$etc.'/opkg.conf';AsusUpdateStore::noLinks($main);clearstatcache(true,$main);
        if(@lstat($main)!==false)$paths[]=$main;
        $directory=$etc.'/opkg';AsusUpdateStore::noLinks($directory);clearstatcache(true,$directory);
        if(@lstat($directory)!==false){
            self::dataDirectory($opt,$directory,$owner);$names=@scandir($directory);if(!is_array($names))throw new RuntimeException('rollback_unavailable');
            foreach($names as $name){
                if(str_starts_with($name,'.')||!str_ends_with($name,'.conf'))continue;
                if(strlen($name)>255||!preg_match('/^[a-zA-Z0-9][a-zA-Z0-9+_.-]*\.conf$/D',$name)||count($paths)>=129)throw new RuntimeException('rollback_unavailable');
                $paths[]=$directory.'/'.$name;
            }
        }return $paths;
    }
    /** ABI text only: fixed config files are never executed or followed as
     * includes. Keep parser allocation bounded even for legacy-writable data. */
    public static function managerConfig(string $opt,int $owner):string
    {
        $paths=self::configPaths($opt,$owner);$records=[];$text='';
        foreach($paths as $path){
            $record=self::indexFile($path,$owner,65536);$text.=$record['raw']."\n";
            if(strlen($text)>262144||substr_count($text,"\n")>4096)throw new RuntimeException('rollback_unavailable');$records[$path]=$record;
        }
        if(self::configPaths($opt,$owner)!==$paths)throw new RuntimeException('rollback_unavailable');
        foreach($records as $path=>$record)if(self::indexFile($path,$owner,65536)!==$record)throw new RuntimeException('rollback_unavailable');
        if(self::configPaths($opt,$owner)!==$paths)throw new RuntimeException('rollback_unavailable');return $text;
    }
    private static function payloadPath(string $name,bool $directory):bool
    {
        $roots=['lib/nfqws2-asus','lib/nfqws-asus-web','libexec/nfqws2-asus','libexec/nfqws-asus-web','share/nfqws2-asus','share/nfqws-asus-web','share/doc/nfqws2-asus','share/licenses/nfqws2-asus','share/licenses/nfqws-asus-web','etc/nfqws2/lua','etc/nfqws2/lists','etc/nfqws2/blobs'];
        $fixed=['usr/bin/nfqws2','bin/nfqws2-dpi','bin/nfqws2-smartdns','bin/nfqws2-smartdns-control','etc/init.d/S51nfqws2','etc/init.d/S80nfqws2-smartdns','etc/init.d/S81nfqws-asus-web','etc/nfqws2/nfqws2.conf','etc/nfqws2/nfqws2.conf.notactive','etc/nfqws-asus-web/auth.json','etc/nfqws-asus-web/support-relay.json'];
        if(!$directory&&in_array($name,$fixed,true))return true;
        foreach($roots as $root)if(str_starts_with($name,$root.'/')||$directory&&($name===$root||str_starts_with($root,$name.'/')))return true;
        if($directory)foreach($fixed as $file)if(str_starts_with($file,$name.'/'))return true;
        return false;
    }
    private static function indexLines(string $raw):array
    {
        if($raw==='')return [];$lines=explode("\n",rtrim($raw,"\n"));
        foreach($lines as $line)if(strlen($line)>4096||$line===''||$line[0]!=='/'||str_contains($line,'//')||preg_match('/[\x00-\x1f\x7f]/',$line)||array_intersect(explode('/',trim($line,'/')),['.','..','']))throw new RuntimeException('rollback_unavailable');
        return $lines;
    }
    /** Read untrusted manager claims one bounded index at a time. Exhaust this
     * iterator before mutation so the final protected-directory check runs. */
    public static function inventory(string $opt,int $owner):iterable
    {
        $info=self::indexDirectory($opt,$owner);$names=@scandir($info);if(!is_array($names))throw new RuntimeException('rollback_unavailable');$count=0;$total=0;
        foreach($names as $index){
            if(!str_ends_with($index,'.list'))continue;
            if(++$count>2048||!preg_match('/^[a-z0-9][a-z0-9+._-]{0,80}\.list$/D',$index))throw new RuntimeException('rollback_unavailable');
            $record=self::indexFile($info.'/'.$index,$owner);$total+=strlen($record['raw']);if($total>8388608)throw new RuntimeException('rollback_unavailable');
            yield $index=>['lines'=>self::indexLines($record['raw']),'identity'=>$record['identity'],'sha256'=>$record['sha256']];
        }
        self::indexDirectory($opt,$owner);
    }
    private static function listed(string $opt,int $owner,?array &$indexes=null,array $conffiles=[]):array
    {
        $info=self::indexDirectory($opt,$owner);$own=self::indexFile($info.'/nfqws2-asus.list',$owner);$files=[];$indexes=['nfqws2-asus.list'=>[$own['identity'],$own['sha256']]];
        foreach(self::indexLines($own['raw']) as $line){
            $line=rtrim($line,'/');if($line==='/opt'||$line===$opt)continue;
            $name=self::relative($line,$opt);$path=$opt.'/'.$name;AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$s=@lstat($path);if(!$s)throw new RuntimeException('rollback_unavailable');$directory=($s['mode']&0170000)===0040000;
            if(!self::payloadPath($name,$directory))throw new RuntimeException('rollback_unavailable');if($directory)continue;
            if(isset($files[$name])||count($files)>=512)throw new RuntimeException('rollback_unavailable');$files[$name]=self::file($path,$owner,self::CAP,preg_match('~^etc/nfqws2/lists/[a-zA-Z0-9_.-]+$~D',$name)===1);
        }if(!$files)throw new RuntimeException('rollback_unavailable');
        // A failed maintainer hook can make real opkg omit retained conffiles
        // from .list even after configure succeeds. Only the closed factory
        // map plus validated own declarations can supply these ownership claims.
        foreach($conffiles as $name=>$hash){
            if(!isset(self::CONFFILE_SEEDS[$name])||!hash_equals(self::CONFFILE_SEEDS[$name]['sha256'],$hash))throw new RuntimeException('rollback_unavailable');
            if(!isset($files[$name])){if(count($files)>=512)throw new RuntimeException('rollback_unavailable');$files[$name]=self::file($opt.'/'.$name,$owner,self::CAP);}
        }
        $present=array_intersect_key($files,self::CONFFILE_SEEDS);ksort($present);if(array_keys($conffiles)!==array_keys($present))throw new RuntimeException('rollback_unavailable');
        $ownSeen=false;
        foreach(self::inventory($opt,$owner) as $index=>$record){
            $fingerprint=[$record['identity'],$record['sha256']];
            if($index==='nfqws2-asus.list'){if($fingerprint!==$indexes[$index])throw new RuntimeException('rollback_unavailable');$ownSeen=true;continue;}
            $indexes[$index]=$fingerprint;
            foreach($record['lines'] as $line){$line=rtrim($line,'/');$name=str_starts_with($line,'/opt/')?substr($line,5):(str_starts_with($line,$opt.'/')?substr($line,strlen($opt)+1):null);if($name!==null&&isset($files[$name]))throw new RuntimeException('rollback_unavailable');}
        }
        if(!$ownSeen)throw new RuntimeException('rollback_unavailable');ksort($indexes);ksort($files);return $files;
    }
    private static function header(string $name,int $mode,int $size,int $uid,int $gid,string $type='0'):string
    {
        $prefix='';if(strlen($name)>100){$at=strrpos($name,'/');if($at===false||$at>155||strlen($name)-$at-1>100)throw new RuntimeException('rollback_unavailable');$prefix=substr($name,0,$at);$name=substr($name,$at+1);}
        $oct=fn(int $n,int $w)=>str_pad(decoct($n),$w-1,'0',STR_PAD_LEFT)."\0";
        $h=str_pad($name,100,"\0").$oct($mode,8).$oct($uid,8).$oct($gid,8).$oct($size,12).$oct(0,12).'        '.$type.str_repeat("\0",100)."ustar\0".'00'.str_repeat("\0",80).str_pad($prefix,155,"\0").str_repeat("\0",12);
        if(strlen($h)!==512)throw new RuntimeException('rollback_unavailable');$sum=array_sum(unpack('C*',$h));return substr_replace($h,str_pad(decoct($sum),6,'0',STR_PAD_LEFT)."\0 ",148,8);
    }
    private static function tar(string $path,array $entries,int $owner):void
    {
        $out=@gzopen($path,'wb1');if(!$out)throw new RuntimeException('insufficient_space');
        try{foreach($entries as $name=>$entry){$meta=$entry['meta'];$type=$entry['directory']??false?'5':'0';$size=$type==='5'?0:$meta['size'];if(gzwrite($out,self::header($name,$meta['mode'],$size,$meta['uid'],$meta['gid'],$type))!==512)throw new RuntimeException('insufficient_space');
                if(isset($entry['bytes'])){if(!is_string($entry['bytes'])||strlen($entry['bytes'])!==$size||$size>131072||hash('sha256',$entry['bytes'])!==$meta['sha256']||gzwrite($out,$entry['bytes'])!==$size)throw new RuntimeException('rollback_unavailable');}
                elseif($size){$in=@fopen($entry['source'],'rb');if(!$in)throw new RuntimeException('rollback_unavailable');try{$left=$size;while($left){$chunk=fread($in,min(65536,$left));if(!is_string($chunk)||$chunk===''||gzwrite($out,$chunk)!==strlen($chunk))throw new RuntimeException('insufficient_space');$left-=strlen($chunk);}}finally{fclose($in);}}
                $padding=(512-$size%512)%512;if($padding&&gzwrite($out,str_repeat("\0",$padding))!==$padding)throw new RuntimeException('insufficient_space');
            }if(gzwrite($out,str_repeat("\0",1024))!==1024)throw new RuntimeException('insufficient_space');
        }finally{gzclose($out);}chmod($path,0600);$sync=fopen($path,'rb');if(!$sync)throw new RuntimeException('insufficient_space');try{if(!fsync($sync))throw new RuntimeException('insufficient_space');}finally{fclose($sync);}
    }
    private static function write(string $path,string $raw):void
    {$f=@fopen($path,'xb');if(!$f)throw new RuntimeException('insufficient_space');try{if(fwrite($f,$raw)!==strlen($raw)||!fflush($f)||!fsync($f)||!chmod($path,0600))throw new RuntimeException('insufficient_space');}finally{fclose($f);}}
    private static function index(string $directory,int $owner,array $quarantined=[]):void
    {
        $m=json_decode(file_get_contents($directory.'/snapshot.json'),true,32,JSON_THROW_ON_ERROR);
        $names=['snapshot.json','package.ipk','archive/data.tar.gz','archive/control.tar.gz','archive/debian-binary','archive/preinst','archive/postinst','archive/prerm','archive/postrm'];
        foreach(['payload','metadata'] as $group)foreach($m[$group] as $name=>$_)$names[]=$group.'/'.$name;
        foreach($m['aux']['migration']['files'] as $name=>$_)$names[]='aux/migration/'.$name;
        foreach($m['aux']['owners'] as $name=>$meta)if($meta!==null)$names[]='aux/owners/'.$name;
        $files=[];foreach(array_merge($names,$quarantined) as $name){
            self::name($name);if(count($files)>=512)throw new RuntimeException('rollback_failed');$meta=self::file($directory.'/'.$name,$owner,self::CAP,true);
            $files[$name]=['mode'=>$meta['mode'],'size'=>$meta['size'],'sha256'=>$meta['sha256'],'uid'=>$meta['uid']];
        }ksort($files);$raw=json_encode(['files'=>$files],JSON_THROW_ON_ERROR);if(strlen($raw)>131072)throw new RuntimeException('rollback_failed');
        $tmp=$directory.'/.cleanup-'.bin2hex(random_bytes(8));self::write($tmp,$raw);if(!rename($tmp,$directory.'/cleanup-index.json'))throw new RuntimeException('rollback_failed');
    }
    private static function staging(string $directory,array $payload,array $metadata,array $aux,string $postinst):void
    {
        $files=[];$add=function(string $name,int $size,string $hash)use(&$files){$files[$name]=['mode'=>0600,'size'=>$size,'sha256'=>$hash];};
        foreach(['payload'=>$payload,'metadata'=>$metadata] as $group=>$items)foreach($items as $name=>$meta)$add($group.'/'.$name,$meta['size'],$meta['sha256']);
        foreach($aux['migration']['files'] as $name=>$meta)$add('aux/migration/'.$name,$meta['size'],$meta['sha256']);
        foreach($aux['owners'] as $name=>$meta)if($meta!==null)$add('aux/owners/'.$name,$meta['size'],$meta['sha256']);
        foreach(['preinst','postinst','prerm','postrm'] as $name){$raw=$name==='postinst'?$postinst:"#!/bin/sh\nexit 0\n";$add('archive/'.$name,strlen($raw),hash('sha256',$raw));}
        $add('archive/debian-binary',4,hash('sha256',"2.0\n"));
        foreach(['package.ipk','archive/data.tar.gz','archive/control.tar.gz'] as $name)$add($name,self::CAP,str_repeat('0',64));
        $add('snapshot.json',131072,str_repeat('0',64));$raw=json_encode(['files'=>$files],JSON_THROW_ON_ERROR);
        if(count($files)>512||strlen($raw)>131072)throw new RuntimeException('rollback_unavailable');self::write($directory.'/staging.json',$raw);
    }
    private static function defaults(array $defaults,array $settings):array
    {
        if(count($defaults)>512)throw new RuntimeException('rollback_unavailable');$out=[];
        foreach($defaults as $name=>$meta){
            if(!is_string($name)||!preg_match('~^etc/nfqws2/(?:nfqws2\.conf|lists/[a-zA-Z0-9_.-]+|blobs/[a-zA-Z0-9_.-]+\.bin)$~D',$name)||array_intersect(explode('/',$name),['.','..'])||!is_array($meta)||array_keys($meta)!==['mode','size','sha256']||!is_int($meta['mode'])||$meta['mode']<0||$meta['mode']>0777||($meta['mode']&0022)!==0||!is_int($meta['size'])||$meta['size']<0||$meta['size']>16777216||!preg_match('/^[a-f0-9]{64}$/D',$meta['sha256']??''))throw new RuntimeException('rollback_unavailable');
            if(!isset($settings['files'][$name]))$out[$name]=$meta;
        }ksort($out);return $out;
    }
    private static function installed(array $env):array
    {
        $opt=$env['opt'];$owner=$env['owner'];[$own,$foreign]=self::database($env['status']);
        if($env['pending']||!preg_match('/^install (?:ok|user) installed$/D',$own['Status']??'')||($own['Version']??null)!==$env['installed'])throw new RuntimeException('rollback_unavailable');
        $metadata=[];
        foreach(self::META as $name){$p=$opt.'/lib/opkg/info/nfqws2-asus.'.$name;if(file_exists($p)||is_link($p))$metadata[$name]=self::file($p,$owner,str_starts_with($name,'busybox-migration-')?1048576:131072);}
        foreach(glob($opt.'/lib/opkg/info/nfqws2-asus.*')?:[] as $path)if(!in_array(substr(basename($path),12),array_merge(self::META,['list']),true))throw new RuntimeException('rollback_unavailable');
        if(!isset($metadata['control']))throw new RuntimeException('rollback_unavailable');$control=file_get_contents($opt.'/lib/opkg/info/nfqws2-asus.control');$controlFields=AsusUpdatePackage::fields($control);if(isset($controlFields['Status']))throw new RuntimeException('rollback_unavailable');
        foreach(['Package'=>'nfqws2-asus','Version'=>$own['Version'],'Architecture'=>$own['Architecture']??''] as $key=>$value)if(!preg_match('/^'.preg_quote($key,'/').': '.preg_quote($value,'/').'$/m',$control))throw new RuntimeException('rollback_unavailable');
        $conffiles=self::conffiles($own,$metadata,$opt);$files=self::listed($opt,$owner,$indexes,$conffiles);
        return [$own,$foreign,$metadata,$conffiles,$files,$indexes];
    }
    /** Same closed installed collectors as rollback; no alternate status parser. */
    public static function attest(array $env):array
    {
        [$own,$foreign,$metadata,$conffiles,$files,$indexes]=self::installed($env);
        $aux=self::captureAux($env['opt'],'',$env['owner'],false);
        // stop('upgrade') may create this consent-bound runtime intent. Its
        // private file is validated above; owner draft/migration stay bound.
        unset($aux['owners']['etc/nfqws-asus-web/smartdns/resume-intent.json']);
        $proof=['own'=>$own,'foreign'=>$foreign,'metadata'=>$metadata,'conffiles'=>$conffiles,'payload'=>$files,'indexes'=>$indexes,'aux'=>$aux,'settings'=>AsusUpdateSnapshot::stable($env['opt'],$env['owner'])];
        return ['schema'=>1,'version'=>$own['Version'],'architecture'=>$own['Architecture'],'sha256'=>hash('sha256',json_encode($proof,JSON_THROW_ON_ERROR))];
    }
    public static function capture(array $env,string $destination,string $settings,string $postinst): array
    {
        if(!str_starts_with($postinst,"#!/bin/sh\nexec "))throw new RuntimeException('rollback_unavailable');
        $opt=$env['opt'];$owner=$env['owner'];[$own,$foreign,$metadata,$conffiles,$files,$indexes]=self::installed($env);$total=0;
        $aux=self::captureAux($opt,$destination,$owner,false);$auxBytes=0;foreach($aux['migration']['files'] as $meta)$auxBytes+=$meta['size'];foreach($aux['owners'] as $meta)if($meta!==null)$auxBytes+=$meta['size'];foreach($metadata as $meta)$auxBytes+=$meta['size'];
        foreach($files as $meta)$total+=$meta['size'];if($total+$auxBytes>self::CAP||disk_free_space(dirname($destination))<$total*2+$auxBytes+16777216)throw new RuntimeException('insufficient_space');
        AsusUpdateSnapshot::verify($opt,$settings,$owner);$defaults=self::defaults($env['defaults']??[],json_decode(file_get_contents($settings.'/snapshot.json'),true,32,JSON_THROW_ON_ERROR));AsusUpdateStore::noLinks($destination);if(file_exists($destination)||is_link($destination))throw new RuntimeException('rollback_unavailable');
        $mask=umask(0077);try{
            if(!mkdir($destination,0700)||!mkdir($destination.'/payload',0700)||!mkdir($destination.'/metadata',0700)||!mkdir($destination.'/archive',0700))throw new RuntimeException('insufficient_space');
            self::staging($destination,$files,$metadata,$aux,$postinst);
            foreach($files as $name=>$meta)self::copy($opt.'/'.$name,$destination.'/payload/'.$name,$meta,$owner);
            foreach($metadata as $name=>$meta)self::copy($opt.'/lib/opkg/info/nfqws2-asus.'.$name,$destination.'/metadata/'.$name,$meta,$owner);
            $data=[];$directories=[];foreach($files as $name=>$meta){for($p=dirname('opt/'.$name);$p!=='.';$p=dirname($p))$directories[$p]=true;
                if(isset($conffiles[$name])){$raw=self::conffileSeed($name);$data['opt/'.$name]=['bytes'=>$raw,'meta'=>array_replace($meta,['mode'=>0600,'size'=>strlen($raw),'sha256'=>$conffiles[$name]])];}
                else $data['opt/'.$name]=['source'=>$destination.'/payload/'.$name,'meta'=>$meta];
            }
            ksort($directories);$entries=[];foreach($directories as $name=>$_){$p=$opt.substr($name,3);AsusUpdateStore::noLinks($p);$s=@lstat($p);if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$owner||($s['mode']&0022)!==0)throw new RuntimeException('rollback_unavailable');$entries[$name.'/']=['directory'=>true,'meta'=>['mode'=>$s['mode']&0777,'size'=>0,'uid'=>$s['uid'],'gid'=>$s['gid']]];}
            self::tar($destination.'/archive/data.tar.gz',$entries+$data,$owner);
            $controls=[];foreach($metadata as $name=>$meta)if(!in_array($name,['preinst','postinst','prerm','postrm'],true))$controls[$name]=['source'=>$destination.'/metadata/'.$name,'meta'=>$meta];
            foreach(['preinst','prerm','postrm','postinst'] as $name){$raw=$name==='postinst'?$postinst:"#!/bin/sh\nexit 0\n";self::write($destination.'/archive/'.$name,$raw);$controls[$name]=['source'=>$destination.'/archive/'.$name,'meta'=>['mode'=>0755,'size'=>strlen($raw),'uid'=>$owner,'gid'=>getmygid()]];}
            self::tar($destination.'/archive/control.tar.gz',$controls,$owner);self::write($destination.'/archive/debian-binary',"2.0\n");$outer=[];
            foreach(['debian-binary','control.tar.gz','data.tar.gz'] as $name)$outer[$name]=['source'=>$destination.'/archive/'.$name,'meta'=>self::file($destination.'/archive/'.$name,$owner)];
            self::tar($destination.'/package.ipk',$outer,$owner);
            if(self::listed($opt,$owner,$currentIndexes,$conffiles)!==$files||$currentIndexes!==$indexes)throw new RuntimeException('settings_changed');AsusUpdateSnapshot::verify($opt,$settings,$owner);
            if(self::captureAux($opt,$destination,$owner)!==$aux)throw new RuntimeException('settings_changed');
            $manifest=['schema'=>1,'version'=>$own['Version'],'architecture'=>$own['Architecture'],'foreign'=>$foreign,'payload'=>$files,'metadata'=>$metadata,'conffiles'=>$conffiles,'aux'=>$aux,'settings'=>self::file($settings.'/snapshot.json',$owner,131072),'defaults'=>$defaults,'package'=>self::file($destination.'/package.ipk',$owner)];
            self::write($destination.'/snapshot.json',json_encode($manifest,JSON_THROW_ON_ERROR));
        }finally{umask($mask);}self::index($destination,$owner);if(!unlink($destination.'/staging.json'))throw new RuntimeException('rollback_unavailable');return self::load($destination,$owner);
    }
    private static function meta(mixed $m):void
    {
        if(!is_array($m)||array_keys($m)!==['mode','size','sha256','uid','gid']||!is_int($m['mode'])||$m['mode']<0||$m['mode']>0777||!is_int($m['size'])||$m['size']<0||$m['size']>self::CAP||!is_string($m['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$m['sha256'])||!is_int($m['uid'])||$m['uid']<0||!is_int($m['gid'])||$m['gid']<0)throw new RuntimeException('rollback_failed');
    }
    private static function name(mixed $name,bool $empty=false):void
    {if(!is_string($name)||!($empty&&$name==='')&&(!preg_match('~^[a-zA-Z0-9_@+.-]+(?:/[a-zA-Z0-9_@+.-]+)*$~D',$name)||array_intersect(explode('/',$name),['.','..'])))throw new RuntimeException('rollback_failed');}
    public static function load(string $directory,int $owner):array
    {
        try{AsusUpdateStore::noLinks($directory);$s=@lstat($directory);if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$owner||($s['mode']&0777)!==0700)throw new RuntimeException();
            self::file($directory.'/snapshot.json',$owner,131072);$m=json_decode(file_get_contents($directory.'/snapshot.json'),true,32,JSON_THROW_ON_ERROR);
            if(!is_array($m)||array_keys($m)!==['schema','version','architecture','foreign','payload','metadata','conffiles','aux','settings','defaults','package']||($m['schema']??null)!==1||!is_string($m['version'])||!preg_match('/^[0-9]+\.[0-9]+\.[0-9]+-asus[0-9]+\+b[1-9][0-9]*$/D',$m['version'])||!in_array($m['architecture'],['all','aarch64-3.10','armv7-2.6','armv7-3.2'],true)||!is_array($m['payload']??null)||count($m['payload'])>512||!is_array($m['metadata']??null)||!is_array($m['conffiles']??null)||count($m['conffiles'])>2||!preg_match('/^[a-f0-9]{64}$/D',$m['foreign']??''))throw new RuntimeException();
            foreach($m['conffiles'] as $name=>$hash)if(!isset(self::CONFFILE_SEEDS[$name],$m['payload'][$name])||!is_string($hash)||!hash_equals(self::CONFFILE_SEEDS[$name]['sha256'],$hash))throw new RuntimeException();
            $present=array_intersect_key($m['payload'],self::CONFFILE_SEEDS);ksort($present);if(array_keys($present)!==array_keys($m['conffiles']))throw new RuntimeException();
            foreach(['payload','metadata'] as $group)foreach($m[$group] as $name=>$meta){self::meta($meta);if($group==='metadata'&&!in_array($name,self::META,true))throw new RuntimeException();if(!preg_match('~^[a-zA-Z0-9_@+.-]+(?:/[a-zA-Z0-9_@+.-]+)*$~D',$name)||array_intersect(explode('/',$name),['.','..']))throw new RuntimeException();$actual=self::file($directory.'/'.$group.'/'.$name,$owner);if($actual['size']!==$meta['size']||$actual['sha256']!==$meta['sha256']||$actual['mode']!==0600)throw new RuntimeException();}
            if(!is_array($m['aux'])||array_keys($m['aux'])!==['migration','history','owners']||!is_array($m['aux']['migration'])||array_keys($m['aux']['migration'])!==['present','directories','files']||!is_bool($m['aux']['migration']['present'])||!is_array($m['aux']['migration']['directories'])||!is_array($m['aux']['migration']['files'])||count($m['aux']['migration']['files'])>512||!is_array($m['aux']['history'])||count($m['aux']['history'])>1000||!is_array($m['aux']['owners'])||array_keys($m['aux']['owners'])!==self::OWNER_FILES)throw new RuntimeException();
            self::meta($m['settings']);self::meta($m['package']);if(!is_array($m['defaults'])||self::defaults($m['defaults'],['files'=>[]])!==$m['defaults'])throw new RuntimeException();
            foreach($m['aux']['migration']['directories'] as $name=>$meta){self::name($name,true);if(!is_array($meta)||array_keys($meta)!==['mode','uid','gid']||!is_int($meta['mode'])||$meta['mode']<0||$meta['mode']>0777||($meta['mode']&0022)!==0||$meta['uid']!==$owner||!is_int($meta['gid'])||$meta['gid']<0)throw new RuntimeException();}
            foreach($m['aux']['history'] as $name=>$meta){if(!preg_match('/^nfqws2-asus-migration\.previous\.([1-9][0-9]{0,2}|1000)$/D',$name)||!is_array($meta)||array_keys($meta)!==['ino','dev','sha256']||!is_int($meta['ino'])||!is_int($meta['dev'])||!preg_match('/^[a-f0-9]{64}$/D',$meta['sha256']))throw new RuntimeException();}
            foreach($m['aux']['migration']['files'] as $name=>$meta){self::name($name);self::meta($meta);$actual=self::file($directory.'/aux/migration/'.$name,$owner);if($actual['size']!==$meta['size']||$actual['sha256']!==$meta['sha256'])throw new RuntimeException();}
            foreach($m['aux']['owners'] as $name=>$meta)if($meta!==null){self::meta($meta);if(!in_array($name,self::OWNER_FILES,true))throw new RuntimeException();$actual=self::file($directory.'/aux/owners/'.$name,$owner);if($actual['size']!==$meta['size']||$actual['sha256']!==$meta['sha256'])throw new RuntimeException();}
            if(self::file($directory.'/package.ipk',$owner)!==$m['package'])throw new RuntimeException();return $m;
        }catch(Throwable $e){throw new RuntimeException('rollback_failed');}
    }
    public static function assertForeign(array $env,array $manifest):void
    {[$own,$foreign]=self::database($env['status']);if($own!==null&&(!in_array($own['Version']??null,[$manifest['version'],$env['candidate_version']??$manifest['version']],true)||($own['Architecture']??null)!==$manifest['architecture']||!preg_match('/^(?:install|deinstall) (?:ok|user|prefer|reinstreq) (?:installed|unpacked|half-installed|half-configured|not-installed)$/D',$own['Status']??''))||!hash_equals($manifest['foreign'],$foreign))throw new RuntimeException('rollback_failed');}
    private static function restoreFile(string $source,string $target,array $meta,int $owner):void
    {
        AsusUpdateStore::noLinks($target);$s=@lstat($target);if($s&&(($s['mode']&0170000)!==0100000||$s['nlink']!==1||!in_array($s['uid'],[$owner,65534],true)))throw new RuntimeException('rollback_failed');
        $parent=dirname($target);AsusUpdateStore::noLinks($parent);if(!is_dir($parent)&&!mkdir($parent,0755,true))throw new RuntimeException('rollback_failed');
        $tmp=$parent.'/.nfqws-rollback-'.bin2hex(random_bytes(12));$mask=umask(0077);try{$in=fopen($source,'rb');$out=fopen($tmp,'xb');if(!$in||!$out)throw new RuntimeException('rollback_failed');try{if(stream_copy_to_stream($in,$out,$meta['size']+1)!==$meta['size']||!fflush($out)||!fsync($out)||!chmod($tmp,$meta['mode']))throw new RuntimeException('rollback_failed');}finally{fclose($in);fclose($out);}
            if((!chown($tmp,$meta['uid'])&&lstat($tmp)['uid']!==$meta['uid'])||(!chgrp($tmp,$meta['gid'])&&lstat($tmp)['gid']!==$meta['gid'])||hash_file('sha256',$tmp)!==$meta['sha256']||!rename($tmp,$target))throw new RuntimeException('rollback_failed');
        }finally{umask($mask);if(is_file($tmp)&&!is_link($tmp))unlink($tmp);}
    }
    private static function quarantine(string $directory,int $owner):string
    {
        $q=$directory.'/quarantine';AsusUpdateStore::noLinks($q);if(!is_dir($q)&&!mkdir($q,0700))throw new RuntimeException('rollback_failed');$s=lstat($q);
        if(($s['mode']&0170000)!==0040000||$s['uid']!==$owner||($s['mode']&0777)!==0700)throw new RuntimeException('rollback_failed');return $q;
    }
    private static function restoreAux(array $env,string $directory,array $m):array
    {
        $owner=$env['owner'];$opt=$env['opt'];$quarantined=[];$lease=self::relayLease($opt,$owner);try{
            $history=self::history($opt,$owner);foreach($m['aux']['history'] as $name=>$meta)if(($history[$name]??null)!==$meta)throw new RuntimeException('rollback_failed');
            foreach(array_diff_key($history,$m['aux']['history']) as $meta)if($meta['sha256']!==hash('sha256',json_encode($m['aux']['migration'],JSON_THROW_ON_ERROR)))throw new RuntimeException('rollback_failed');
            $q=self::quarantine($directory,$owner);
            foreach(['etc/nfqws2-asus-migration'=>'migration','var/lib/nfqws2-asus/relay-config-preserve'=>'relay'] as $name=>$tag){$tree=self::tree($opt.'/'.$name,$owner,$tag==='migration');if(!$tree['present'])continue;
                if($tag==='relay'&&array_diff(array_keys($tree['files']),['metadata.json','file']))throw new RuntimeException('rollback_failed');
                $leaf=$tag.'-'.bin2hex(random_bytes(8));if(!rename($opt.'/'.$name,$q.'/'.$leaf))throw new RuntimeException('rollback_failed');foreach($tree['files'] as $file=>$_)$quarantined[]='quarantine/'.$leaf.'/'.$file;
            }
            $target=$opt.'/etc/nfqws2-asus-migration';foreach($m['aux']['migration']['directories'] as $name=>$meta){$p=$target.($name===''?'':'/'.$name);if(!is_dir($p)&&!mkdir($p,$meta['mode'],true))throw new RuntimeException('rollback_failed');if(!chmod($p,$meta['mode']))throw new RuntimeException('rollback_failed');}
            if(!is_array($m['aux'])||array_keys($m['aux'])!==['migration','history','owners']||!is_array($m['aux']['migration'])||array_keys($m['aux']['migration'])!==['present','directories','files']||!is_bool($m['aux']['migration']['present'])||!is_array($m['aux']['migration']['directories'])||!is_array($m['aux']['migration']['files'])||count($m['aux']['migration']['files'])>512||!is_array($m['aux']['history'])||count($m['aux']['history'])>1000||!is_array($m['aux']['owners'])||array_keys($m['aux']['owners'])!==self::OWNER_FILES)throw new RuntimeException();
            self::meta($m['settings']);self::meta($m['package']);if(!is_array($m['defaults'])||self::defaults($m['defaults'],['files'=>[]])!==$m['defaults'])throw new RuntimeException();
            foreach($m['aux']['migration']['directories'] as $name=>$meta){self::name($name,true);if(!is_array($meta)||array_keys($meta)!==['mode','uid','gid']||!is_int($meta['mode'])||$meta['mode']<0||$meta['mode']>0777||($meta['mode']&0022)!==0||$meta['uid']!==$owner||!is_int($meta['gid'])||$meta['gid']<0)throw new RuntimeException();}
            foreach($m['aux']['history'] as $name=>$meta){if(!preg_match('/^nfqws2-asus-migration\.previous\.([1-9][0-9]{0,2}|1000)$/D',$name)||!is_array($meta)||array_keys($meta)!==['ino','dev','sha256']||!is_int($meta['ino'])||!is_int($meta['dev'])||!preg_match('/^[a-f0-9]{64}$/D',$meta['sha256']))throw new RuntimeException();}
            foreach($m['aux']['migration']['files'] as $name=>$meta)self::restoreFile($directory.'/aux/migration/'.$name,$target.'/'.$name,$meta,$owner);
            foreach($m['aux']['owners'] as $name=>$meta){
                // stop(upgrade) created a consent-bound resume intent against
                // its converged DNS journal. Never resurrect the old journal.
                if(str_ends_with($name,'/resume-intent.json'))continue;
                $p=$opt.'/'.$name;if($meta!==null)self::restoreFile($directory.'/aux/owners/'.$name,$p,$meta,$owner);
                elseif(@lstat($p)!==false){self::file($p,$owner,131072);$leaf='owner-'.bin2hex(random_bytes(8));if(!rename($p,$q.'/'.$leaf))throw new RuntimeException('rollback_failed');$quarantined[]='quarantine/'.$leaf;}
            }
        }finally{flock($lease,LOCK_UN);fclose($lease);}return $quarantined;
    }
    private static function settings(string $settings,array $m,int $owner):array
    {
        try{
            if(self::file($settings.'/snapshot.json',$owner,131072)!==$m['settings'])throw new RuntimeException();
            $record=json_decode(file_get_contents($settings.'/snapshot.json'),true,32,JSON_THROW_ON_ERROR);
            if(!is_array($record['files']??null)||count($record['files'])>512)throw new RuntimeException();
            foreach($record['files'] as $name=>$meta){
                if(!is_string($name)||!preg_match('~^etc/(?:nfqws2/[a-zA-Z0-9_./-]+|nfqws-asus-web/(?:auth|support-relay|update-channel)\.json)$~D',$name)||array_intersect(explode('/',$name),['.','..']))throw new RuntimeException();
                self::meta($meta);AsusUpdateStore::noLinks($settings.'/'.$name);$s=lstat($settings.'/'.$name);
                if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0777)!==$meta['mode']||$s['size']!==$meta['size']||hash_file('sha256',$settings.'/'.$name)!==$meta['sha256'])throw new RuntimeException();
            }return $record;
        }catch(Throwable $e){throw new RuntimeException('rollback_failed');}
    }
    private static function quarantineDefaults(array $env,string $directory,array $m,array $record):array
    {
        $plan=[];foreach($m['defaults'] as $name=>$meta){
            if(isset($record['files'][$name]))throw new RuntimeException('rollback_failed');$path=$env['opt'].'/'.$name;AsusUpdateStore::noLinks($path);if(@lstat($path)===false)continue;
            $actual=self::file($path,$env['owner'],16777216);foreach(['mode','size','sha256'] as $key)if($actual[$key]!==$meta[$key])throw new RuntimeException('rollback_failed');$plan[$name]=$actual;
        }
        if(!$plan)return [];$q=self::quarantine($directory,$env['owner']);$paths=[];
        foreach($plan as $name=>$meta){$path=$env['opt'].'/'.$name;if(self::file($path,$env['owner'],16777216)!==$meta)throw new RuntimeException('rollback_failed');$leaf='default-'.bin2hex(random_bytes(8));if(!rename($path,$q.'/'.$leaf))throw new RuntimeException('rollback_failed');$paths[]='quarantine/'.$leaf;}
        return $paths;
    }
    public static function finalize(array $env,string $directory,string $settings):array
    {
        $owner=$env['owner'];$m=self::load($directory,$owner);self::assertForeign($env,$m);$record=self::settings($settings,$m,$owner);
        $quarantined=self::quarantineDefaults($env,$directory,$m,$record);$quarantined=array_merge($quarantined,self::restoreAux($env,$directory,$m));
        // Own maintainer metadata only: opkg itself owns and commits status DB.
        foreach($m['metadata'] as $name=>$meta)self::restoreFile($directory.'/metadata/'.$name,$env['opt'].'/lib/opkg/info/nfqws2-asus.'.$name,$meta,$owner);
        foreach(['preinst','postinst','prerm','postrm'] as $name)if(!isset($m['metadata'][$name])){$target=$env['opt'].'/lib/opkg/info/nfqws2-asus.'.$name;$current=self::file($target,$owner,131072);$stub=self::file($directory.'/archive/'.$name,$owner,131072);if($current['size']!==$stub['size']||$current['sha256']!==$stub['sha256']||!unlink($target))throw new RuntimeException('rollback_failed');}
        foreach($record['files'] as $name=>$meta)self::restoreFile($settings.'/'.$name,$env['opt'].'/'.$name,$meta,$owner);
        AsusUpdateSnapshot::verify($env['opt'],$settings,$owner);self::index($directory,$owner,$quarantined);return ['restored'=>true];
    }
    public static function verifyInstalled(array $env,string $directory,string $settings):array
    {
        $m=self::load($directory,$env['owner']);self::assertForeign($env,$m);[$own]=self::database($env['status']);
        if(($own['Version']??null)!==$m['version']||($own['Architecture']??null)!==$m['architecture']||!preg_match('/^install (?:ok|user) installed$/D',$own['Status']??''))throw new RuntimeException('rollback_failed');
        try{if(self::conffileMap($own['Conffiles']??'',$env['opt'])!==$m['conffiles'])throw new RuntimeException();}catch(Throwable $e){throw new RuntimeException('rollback_failed');}
        foreach($m['metadata'] as $name=>$meta)if(self::file($env['opt'].'/lib/opkg/info/nfqws2-asus.'.$name,$env['owner'],str_starts_with($name,'busybox-migration-')?1048576:131072)!==$meta)throw new RuntimeException('rollback_failed');
        try{if(self::conffiles($own,$m['metadata'],$env['opt'])!==$m['conffiles']||self::listed($env['opt'],$env['owner'],$indexes,$m['conffiles'])!==$m['payload'])throw new RuntimeException();}catch(Throwable $e){throw new RuntimeException('rollback_failed');}
        if(self::tree($env['opt'].'/etc/nfqws2-asus-migration',$env['owner'],true)!==$m['aux']['migration'])throw new RuntimeException('rollback_failed');
        $history=self::history($env['opt'],$env['owner']);foreach($m['aux']['history'] as $name=>$item)if(($history[$name]??null)!==$item)throw new RuntimeException('rollback_failed');
        foreach($m['aux']['owners'] as $name=>$item)if(!str_ends_with($name,'/resume-intent.json')){
            $p=$env['opt'].'/'.$name;AsusUpdateStore::noLinks($p);if($item===null?@lstat($p)!==false:self::file($p,$env['owner'],131072)!==$item)throw new RuntimeException('rollback_failed');
        }
        AsusUpdateSnapshot::verify($env['opt'],$settings,$env['owner']);return ['version'=>$m['version'],'verified'=>true];
    }
}
