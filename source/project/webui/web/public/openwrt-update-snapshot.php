<?php
require_once __DIR__.'/update-store.php';
require_once __DIR__.'/smartdns-profile.php';

/** Last-moment native settings backup; verification never overwrites operator edits. */
final class NfqwsOpenWrtUpdateSnapshot
{
    private static function stock(string $root,int $owner):array
    {
        $file=$root.'/usr/share/nfqws2/report-baseline.json';AsusUpdateStore::noLinks($file);$s=@lstat($file);if(!$s)return [];
        if(!is_file($file)||$s['uid']!==$owner||($s['mode']&0022)!==0||$s['size']>1048576)throw new RuntimeException('invalid_state');
        $v=json_decode((string)file_get_contents($file),true,32,JSON_THROW_ON_ERROR);$out=[];
        if(!is_array($v['resources']??null)||count($v['resources'])>512)throw new RuntimeException('invalid_state');
        foreach($v['resources']as $name=>$r){if(!preg_match('~^(lua|blob)/([A-Za-z0-9_.-]{1,128})$~D',$name,$m)||!is_int($r['bytes']??null)||$r['bytes']<0||!preg_match('/^[a-f0-9]{64}$/D',$r['sha256']??''))throw new RuntimeException('invalid_state');
            $out['etc/nfqws2/'.($m[1]==='blob'?'blobs':'lua').'/'.$m[2]]=['size'=>$r['bytes'],'sha256'=>$r['sha256']];}
        return $out;
    }
    private static function consent(string $path):string
    {
        $v=json_decode((string)file_get_contents($path),true,32,JSON_THROW_ON_ERROR);$keys=is_array($v)?array_keys($v):[];sort($keys);$expected=['schema_version','profile','profile_hash','engine_sha','source_request_id'];sort($expected);
        if($keys!==$expected||$v['schema_version']!==1||!is_array($v['profile'])||!preg_match('/^[a-f0-9]{64}$/D',$v['engine_sha'])||!preg_match('/^[a-f0-9]{32}$/D',$v['source_request_id'])||AsusSmartDnsProfile::hash($v['profile'])!==$v['profile_hash'])throw new RuntimeException('invalid_state');
        return $v['profile_hash'];
    }
    private static function collect(string $root,int $owner):array
    {
        $root=rtrim($root,'/');AsusUpdateStore::noLinks($root===''?'/':$root);$files=[];$bytes=0;$stock=self::stock($root,$owner);
        $scan=function(string $name)use(&$scan,&$files,&$bytes,$root,$stock,$owner){
            $p=$root.'/'.$name;clearstatcache(true,$p);$s=@lstat($p);if(!$s)return;
            if(is_link($p)){$target=readlink($p);if(!is_string($target)||strlen($target)>4096)throw new RuntimeException('invalid_state');
                $files[$name]=['type'=>'link','target'=>$target,'uid'=>$s['uid'],'gid'=>$s['gid'],'mode'=>$s['mode']&0777,'size'=>strlen($target),'sha256'=>hash('sha256',$target),'stock'=>false];return;}
            if(is_dir($p)){foreach(scandir($p)as $leaf){if($leaf==='.'||$leaf==='..')continue;if(!preg_match('/^[A-Za-z0-9_+.-]{1,128}$/D',$leaf))throw new RuntimeException('invalid_state');$scan($name.'/'.$leaf);}return;}
            if(!is_file($p)||$s['size']>16777216||count($files)>=511)throw new RuntimeException('output_limit');
            $bytes+=$s['size'];if($bytes>33554432)throw new RuntimeException('output_limit');$hash=hash_file('sha256',$p);if(!is_string($hash))throw new RuntimeException('invalid_state');
            $plain=['size'=>$s['size'],'sha256'=>$hash];$owned=$s['uid']===$owner&&$s['nlink']===1&&($s['mode']&0022)===0;
            $files[$name]=['type'=>'file','uid'=>$s['uid'],'gid'=>$s['gid'],'mode'=>$s['mode']&0777]+$plain+['stock'=>$owned&&($stock[$name]??null)===$plain];
            if($name==='etc/nfqws2-web/smartdns/resume-intent.json')$files[$name]['consent']=self::consent($p);
        };
        $scan('etc/nfqws2');$scan('etc/config/nfqws2-web');
        foreach(['auth.json','support-relay.json','update-channel.json','smartdns/draft.json','smartdns/resume-intent.json']as $name)$scan('etc/nfqws2-web/'.$name);
        ksort($files);return ['files'=>$files,'bytes'=>$bytes];
    }
    public static function estimate(string $root='/',int $owner=0):int{return self::collect($root,$owner)['bytes'];}
    public static function capture(string $destination,string $root='/',int $owner=0):array
    {
        AsusUpdateStore::noLinks($destination);if(file_exists($destination))throw new RuntimeException('invalid_state');$v=self::collect($root,$owner);$root=rtrim($root,'/');
        $free=disk_free_space(dirname($destination));if($free===false||$free<$v['bytes']+4194304)throw new RuntimeException('insufficient_space');
        $mask=umask(0077);try{if(!mkdir($destination,0700))throw new RuntimeException('invalid_state');
            foreach($v['files']as $name=>$r){if($r['type']!=='file')continue;$out=$destination.'/'.$name;
                if(!is_dir(dirname($out))&&!mkdir(dirname($out),0700,true))throw new RuntimeException('invalid_state');
                if(!copy($root.'/'.$name,$out)||!chmod($out,0600)||filesize($out)!==$r['size']||hash_file('sha256',$out)!==$r['sha256'])throw new RuntimeException('settings_changed');}
            // Pruning uses the backup's actual protected mode, not the user's mode.
            $index=[];foreach($v['files']as $name=>$r)if($r['type']==='file')$index[$name]=['mode'=>0600,'size'=>$r['size'],'sha256'=>$r['sha256']];
            $raw=json_encode($v,JSON_THROW_ON_ERROR);if(strlen($raw)>131072||file_put_contents($destination.'/native-snapshot.json',$raw)!==strlen($raw))throw new RuntimeException('output_limit');
            $index['native-snapshot.json']=['mode'=>0600,'size'=>strlen($raw),'sha256'=>hash('sha256',$raw)];
            if(file_put_contents($destination.'/snapshot.json',json_encode(['files'=>$index],JSON_THROW_ON_ERROR))===false)throw new RuntimeException('insufficient_space');
        }finally{umask($mask);}
        if(self::collect($root,$owner)!==$v)throw new RuntimeException('settings_changed');return $v;
    }
    public static function verify(string $destination,string $root='/',int $owner=0):bool
    {
        AsusUpdateStore::noLinks($destination);$file=$destination.'/native-snapshot.json';$s=@lstat($file);
        if(!$s||!is_file($file)||is_link($file)||$s['uid']!==$owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>131072)throw new RuntimeException('invalid_state');
        $v=json_decode((string)file_get_contents($file),true,32,JSON_THROW_ON_ERROR);if(!is_array($v['files']??null)||count($v['files'])>512)throw new RuntimeException('invalid_state');$now=self::collect($root,$owner);
        foreach($v['files']as $name=>$r){if(!is_string($name)||!preg_match('~^etc/(?:nfqws2/|nfqws2-web/|config/nfqws2-web$)[A-Za-z0-9_+./-]*$~D',$name)||in_array('..',explode('/',$name),true)||!is_array($r))throw new RuntimeException('invalid_state');
            $new=$now['files'][$name]??null;
            if($r['type']==='file'){$p=$destination.'/'.$name;AsusUpdateStore::noLinks($p);$b=@lstat($p);if(!$b||!is_file($p)||$b['uid']!==$owner||$b['nlink']!==1||($b['mode']&0777)!==0600||$b['size']!==$r['size']||hash_file('sha256',$p)!==$r['sha256'])throw new RuntimeException('invalid_state');}
            if($new===$r)continue;
            if(isset($r['consent'])&&is_array($new)&&($new['consent']??null)===$r['consent']&&$new['uid']===$r['uid']&&$new['gid']===$r['gid']&&$new['mode']===$r['mode'])continue;
            // An untouched old stock resource may become the new proven stock.
            if(($r['stock']??false)&&is_array($new)&&($new['stock']??false)&&$new['uid']===$r['uid']&&$new['gid']===$r['gid']&&$new['mode']===$r['mode'])continue;
            throw new RuntimeException('settings_changed');
        }
        foreach($now['files']as $name=>$r)if(!isset($v['files'][$name])&&!$r['stock'])throw new RuntimeException('settings_changed');
        return true;
    }
}
