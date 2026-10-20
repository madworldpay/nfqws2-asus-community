<?php
require_once __DIR__.'/update-store.php';

/** Immutable execution closure, prepared before any installed file is replaced. */
final class AsusUpdateRuntime
{
    private const CAP=33554432;
    private static function number(string $data,int $at,int $bytes): int
    {
        if($at<0||$at+$bytes>strlen($data))throw new RuntimeException('unsupported_runtime');$n=0;
        for($i=$bytes-1;$i>=0;$i--){$n=$n*256+ord($data[$at+$i]);if($n>2147483647)throw new RuntimeException('unsupported_runtime');}return $n;
    }
    /** Only inspect ELF headers and string tables, without executing ldd/the file. */
    private static function elf(string $data): array
    {
        if(strlen($data)<64||substr($data,0,4)!=="\x7fELF"||!in_array(ord($data[4]),[1,2],true)||ord($data[5])!==1)throw new RuntimeException('unsupported_runtime');
        $wide=ord($data[4])===2;$word=$wide?8:4;$machine=self::number($data,18,2);
        if(!in_array(self::number($data,16,2),[2,3],true)||$machine!==($wide?183:40))throw new RuntimeException('unsupported_runtime');
        $offset=self::number($data,$wide?32:28,$word);$size=self::number($data,$wide?54:42,2);$count=self::number($data,$wide?56:44,2);
        if($size!==($wide?56:32)||$count>64||$offset+$size*$count>strlen($data))throw new RuntimeException('unsupported_runtime');
        $loads=[];$dynamic=null;$interpreter=null;
        for($i=0;$i<$count;$i++){$p=$offset+$size*$i;$type=self::number($data,$p,4);if(!in_array($type,[1,2,3],true))continue;
            $file=self::number($data,$p+($wide?8:4),$word);$address=self::number($data,$p+($wide?16:8),$word);$bytes=self::number($data,$p+($wide?32:16),$word);
            if($file+$bytes>strlen($data))throw new RuntimeException('unsupported_runtime');
            if($type===1)$loads[]=[$address,$file,$bytes];elseif($type===2){if($bytes>131072)throw new RuntimeException('unsupported_runtime');$dynamic=[$file,$bytes];}
            else{$interpreter=rtrim(substr($data,$file,$bytes),"\0");if(!preg_match('~^/(?:opt/)?lib/[a-zA-Z0-9_.-]{1,100}$~D',$interpreter))throw new RuntimeException('unsupported_runtime');}
        }
        $needed=[];$table=null;$tableSize=null;$indexes=[];
        if($dynamic!==null)for($p=$dynamic[0];$p+$word*2<=$dynamic[0]+$dynamic[1];$p+=$word*2){$tag=self::number($data,$p,$word);if($tag===0)break;if(!in_array($tag,[1,5,10],true))continue;$value=self::number($data,$p+$word,$word);if($tag===1)$indexes[]=$value;elseif($tag===5)$table=$value;else $tableSize=$value;}
        if(count($indexes)>64)throw new RuntimeException('unsupported_runtime');
        if($indexes!==[]){$start=null;if($table===null||$tableSize===null||$tableSize>1048576)throw new RuntimeException('unsupported_runtime');
            foreach($loads as [$address,$file,$bytes])if($table>=$address&&$table+$tableSize<=$address+$bytes)$start=$file+$table-$address;
            if($start===null)throw new RuntimeException('unsupported_runtime');
            foreach($indexes as $index){if($index>=$tableSize)throw new RuntimeException('unsupported_runtime');$end=strpos($data,"\0",$start+$index);if($end===false||$end>=$start+$tableSize)throw new RuntimeException('unsupported_runtime');$name=substr($data,$start+$index,$end-$start-$index);if(!preg_match('/^[a-zA-Z0-9_+.-]{1,128}$/D',$name))throw new RuntimeException('unsupported_runtime');$needed[]=$name;}
        }
        return ['machine'=>$machine,'interpreter'=>$interpreter,'needed'=>$needed];
    }
    private static function source(string $path,int $owner,?string $boundary=null): array
    {
        if($boundary!==null){$real=realpath($path);$base=realpath($boundary);if($real===false||$base===false||!str_starts_with($real,$base.'/'))throw new RuntimeException('invalid_state');$path=$real;}
        else AsusUpdateStore::noLinks($path);
        $s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>16777216)throw new RuntimeException('invalid_state');
        return ['source'=>$path,'size'=>$s['size'],'sha256'=>hash_file('sha256',$path)];
    }
    public static function stage(string $destination,array $config=[],int $owner=0): array
    {
        $opt=$config['opt']??dirname(AsusDpiStore::optPath('/var'));$opt=rtrim($opt,'/');AsusUpdateStore::noLinks($opt);
        AsusUpdateStore::noLinks($destination);if(file_exists($destination)||is_link($destination))throw new RuntimeException('invalid_state');
        $sources=[];$total=0;
        $add=function(string $name,string $path,int $mode,?string $boundary=null)use(&$sources,&$total,$owner){
            if(!preg_match('~^[a-zA-Z0-9_+.-]+(?:/[a-zA-Z0-9_+.-]+)*$~D',$name)||in_array('..',explode('/',$name),true)||in_array('.',explode('/',$name),true))throw new RuntimeException('invalid_state');
            $s=self::source($path,$owner,$boundary);$s['mode']=$mode;if(isset($sources[$name])){if($sources[$name]!==$s)throw new RuntimeException('invalid_state');return;}$total+=$s['size'];if($total>self::CAP||count($sources)>=256)throw new RuntimeException('runtime_limit');$sources[$name]=$s;
        };
        $binary=$config['binary']??PHP_BINARY;$binaryReal=realpath($binary);if($binaryReal===false||!str_starts_with($binaryReal,$opt.'/bin/'))throw new RuntimeException('unsupported_runtime');
        $add('php',$binaryReal,0700,$opt.'/bin');$meta=self::elf(file_get_contents($binaryReal));$interpreter=$meta['interpreter'];if($interpreter===null||!str_starts_with($interpreter,'/opt/lib/'))throw new RuntimeException('unsupported_runtime');$loader=basename($interpreter);$queue=array_merge([$loader],$meta['needed'],['openssl.so']);
        foreach(['libnss_dns.so.2','libnss_files.so.2','libresolv.so.2'] as $name)if(file_exists($opt.'/lib/'.$name))$queue[]=$name;
        while($queue!==[]){$name=array_shift($queue);if(isset($sources['lib/'.$name]))continue;
            $source=$name==='openssl.so'?$opt.'/lib/php8/openssl.so':$opt.'/lib/'.$name;$add('lib/'.$name,$source,0700,$opt.'/lib');
            $elf=self::elf(file_get_contents($sources['lib/'.$name]['source']));if($elf['machine']!==$meta['machine'])throw new RuntimeException('unsupported_runtime');foreach($elf['needed'] as $needed)$queue[]=$needed;
        }
        $app=$config['application']??$opt.'/share/nfqws-asus-web';AsusUpdateStore::noLinks($app);$php=glob($app.'/*.php')?:[];if(count($php)>128)throw new RuntimeException('runtime_limit');
        foreach($php as $p)$add('app/'.basename($p),$p,0600);
        $add('worker.php',$config['entry']??$opt.'/lib/nfqws2-asus/update/worker.php',0600);
        $add('update-launch',$config['launcher']??$opt.'/libexec/nfqws2-asus/update-launch',0700);
        $resources=$config['resources']??$opt.'/share/nfqws2-asus';$add('resources/package-manifest.schema.json',$resources.'/package-manifest.schema.json',0600);
        $key=$resources.'/update-release-key.pem';if(!is_file($key)&&$resources===dirname(__DIR__,3).'/updates')$key=$resources.'/trusted-release-key.pem';$add('resources/update-release-key.pem',$key,0600);
        $free=$config['free']??disk_free_space(dirname($destination));if($free===false||$free<$total+16777216)throw new RuntimeException('insufficient_space');
        $mask=umask(0077);$files=[];
        try{if(!mkdir($destination,0700))throw new RuntimeException('invalid_state');
            $planned=[];foreach($sources as $name=>$source)$planned[$name]=['mode'=>$source['mode'],'size'=>$source['size'],'sha256'=>$source['sha256']];$scripts=[];
            foreach(['check.sh'=>'preflight','run.sh'=>'guard-apply'] as $name=>$mode){
                $scripts[$name]="#!/bin/sh\n[ \"\$#\" = 1 ] || exit 1\nexec ".implode(' ',array_map('escapeshellarg',self::arguments($destination,$loader,$planned))).' -- '.$mode.' "$1"'."\n";
                $planned[$name]=['mode'=>0700,'size'=>strlen($scripts[$name]),'sha256'=>hash('sha256',$scripts[$name])];
            }
            // Persist ownership before copying any bulk bytes. A killed stage
            // can reclaim only these indexed paths and leave operator files.
            $raw=json_encode(['files'=>$planned],JSON_THROW_ON_ERROR);if(strlen($raw)>131072)throw new RuntimeException('runtime_limit');
            $index=fopen($destination.'/staging.json','xb');if(!$index)throw new RuntimeException('invalid_state');try{if(fwrite($index,$raw)!==strlen($raw)||!fflush($index)||!fsync($index))throw new RuntimeException('insufficient_space');}finally{fclose($index);}
            foreach($sources as $name=>$source){$p=$destination.'/'.$name;if(!is_dir(dirname($p))&&!mkdir(dirname($p),0700,true))throw new RuntimeException('invalid_state');
                $in=@fopen($source['source'],'rb');$out=@fopen($p,'xb');if(!$in||!$out)throw new RuntimeException('invalid_state');
                try{$s=fstat($in);if(($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||stream_copy_to_stream($in,$out,$source['size']+1)!==$source['size']||!fflush($out))throw new RuntimeException('runtime_changed');}finally{fclose($in);fclose($out);}
                if(!chmod($p,$source['mode'])||hash_file('sha256',$p)!==$source['sha256'])throw new RuntimeException('runtime_changed');$files[$name]=['mode'=>$source['mode'],'size'=>$source['size'],'sha256'=>$source['sha256']];
            }
            foreach($scripts as $name=>$script){
                $f=fopen($destination.'/'.$name,'xb');if(!$f)throw new RuntimeException('invalid_state');try{if(fwrite($f,$script)!==strlen($script)||!fflush($f)||!chmod($destination.'/'.$name,0700))throw new RuntimeException('insufficient_space');}finally{fclose($f);}
                $files[$name]=['mode'=>0700,'size'=>strlen($script),'sha256'=>hash('sha256',$script)];$total+=strlen($script);if($total>self::CAP)throw new RuntimeException('runtime_limit');
            }
            ksort($files);$manifest=json_encode(['schema'=>1,'files'=>$files,'loader'=>$loader,'bytes'=>$total],JSON_THROW_ON_ERROR);
            if(strlen($manifest)>131072)throw new RuntimeException('runtime_limit');$f=fopen($destination.'/closure.json','xb');if(!$f)throw new RuntimeException('invalid_state');try{if(fwrite($f,$manifest)!==strlen($manifest)||!fflush($f)||!fsync($f))throw new RuntimeException('insufficient_space');}finally{fclose($f);}
            if(!unlink($destination.'/staging.json'))throw new RuntimeException('invalid_state');
        }finally{umask($mask);}return self::load($destination,$owner);
    }
    public static function load(string $runtime,int $owner=0): array
    {
        AsusUpdateStore::noLinks($runtime);$s=@lstat($runtime);if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $p=$runtime.'/closure.json';$meta=self::source($p,$owner);if($meta['size']>131072)throw new RuntimeException('invalid_state');$s=lstat($p);if(($s['mode']&0777)!==0600)throw new RuntimeException('invalid_state');
        try{$m=json_decode(file_get_contents($p),true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(!is_array($m)||array_keys($m)!==['schema','files','loader','bytes']||$m['schema']!==1||!is_array($m['files'])||count($m['files'])>256||!is_int($m['bytes'])||$m['bytes']>self::CAP||!preg_match('/^ld[a-zA-Z0-9_.-]+$/D',$m['loader']))throw new RuntimeException('invalid_state');$total=0;
        foreach($m['files'] as $file=>$item){if(!is_string($file)||!preg_match('~^(?:php|worker\.php|check\.sh|run\.sh|update-launch|(?:app|lib|resources)/[a-zA-Z0-9_+.-]+)$~D',$file)||!is_array($item)||array_keys($item)!==['mode','size','sha256']||!in_array($item['mode'],[0600,0700],true)||!is_int($item['size'])||$item['size']<0||!preg_match('/^[a-f0-9]{64}$/D',$item['sha256']))throw new RuntimeException('invalid_state');
            $p=$runtime.'/'.$file;AsusUpdateStore::noLinks($p);$s=@lstat($p);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0777)!==$item['mode']||$s['size']!==$item['size']||hash_file('sha256',$p)!==$item['sha256'])throw new RuntimeException('runtime_changed');$total+=$item['size'];
        }
        foreach(['php','worker.php','check.sh','run.sh','update-launch','lib/'.$m['loader'],'lib/openssl.so','app/update-store.php','resources/update-release-key.pem','resources/package-manifest.schema.json'] as $file)if(!isset($m['files'][$file]))throw new RuntimeException('invalid_state');
        if($total!==$m['bytes'])throw new RuntimeException('invalid_state');
        return ['argv'=>self::arguments($runtime,$m['loader'],$m['files']),
            'bytes'=>$total,'digest'=>hash_file('sha256',$runtime.'/closure.json')];
    }
    private static function arguments(string $runtime,string $loader,array $files): array
    {
        $inhibit=['',$runtime.'/php','php'];foreach($files as $name=>$_)if(str_starts_with($name,'lib/')){$inhibit[]=$runtime.'/'.$name;$inhibit[]=basename($name);}
        return [$runtime.'/lib/'.$loader,'--inhibit-cache','--inhibit-rpath',implode(':',$inhibit),'--library-path',$runtime.'/lib',$runtime.'/php','-n','-d','extension='.$runtime.'/lib/openssl.so','-d','register_argc_argv=1','-q','-f',$runtime.'/worker.php'];
    }
}
