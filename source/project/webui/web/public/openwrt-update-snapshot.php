<?php
require_once __DIR__.'/update-store.php';
require_once __DIR__.'/smartdns-profile.php';

/** Last-moment native settings backup; verification never overwrites operator edits. */
final class NfqwsOpenWrtUpdateSnapshot
{
    private static function keys(array $value,array $expected):bool
    {$keys=array_keys($value);sort($keys);sort($expected);return $keys===$expected;}
    /** Validate a protected identity before using its paths or equivalence flags. */
    private static function identity(array $value,int $owner):array
    {
        if(!self::keys($value,['files','bytes'])||!is_array($value['files'])||count($value['files'])>512||!is_int($value['bytes'])||$value['bytes']<0||$value['bytes']>33554432)throw new RuntimeException('invalid_state');
        $files=[];$bytes=0;
        foreach($value['files']as $name=>$r){
            if(!is_string($name)||strlen($name)>4096||!preg_match('~^etc/(?:nfqws2(?:/[A-Za-z0-9_+.-]{1,128})*|config/nfqws2-web|nfqws2-web/(?:auth\.json|support-relay\.json|update-channel\.json|smartdns/(?:draft|resume-intent)\.json))$~D',$name)||array_intersect(explode('/',$name),['.','..'])||!is_array($r)||!in_array($r['type']??null,['file','link'],true))throw new RuntimeException('invalid_state');
            $link=$r['type']==='link';$consent=!$link&&$name==='etc/nfqws2-web/smartdns/resume-intent.json';
            $expected=['type','uid','gid','mode','size','sha256','stock'];if($link)$expected[]='target';if($consent)$expected[]='consent';
            if(!self::keys($r,$expected)||$name==='etc/nfqws2'&&!$link||!is_int($r['uid'])||$r['uid']<0||$r['uid']>4294967295||!is_int($r['gid'])||$r['gid']<0||$r['gid']>4294967295||!is_int($r['mode'])||$r['mode']<0||$r['mode']>0777||!is_int($r['size'])||$r['size']<0||$r['size']>($link?4096:16777216)||!is_string($r['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$r['sha256'])||!is_bool($r['stock']))throw new RuntimeException('invalid_state');
            if($link){
                if(!is_string($r['target'])||$r['target']===''||str_contains($r['target'],"\0")||strlen($r['target'])!==$r['size']||hash('sha256',$r['target'])!==$r['sha256']||$r['stock'])throw new RuntimeException('invalid_state');
                $files[$name]=['type'=>'link','target'=>$r['target'],'uid'=>$r['uid'],'gid'=>$r['gid'],'mode'=>$r['mode'],'size'=>$r['size'],'sha256'=>$r['sha256'],'stock'=>false];
            }else{
                if($r['stock']&&(!preg_match('~^etc/nfqws2/(?:lua|blobs)/[A-Za-z0-9_+.-]{1,128}$~D',$name)||$r['uid']!==$owner||($r['mode']&0022)!==0))throw new RuntimeException('invalid_state');
                $bytes+=$r['size'];if($bytes>33554432)throw new RuntimeException('invalid_state');
                $files[$name]=['type'=>'file','uid'=>$r['uid'],'gid'=>$r['gid'],'mode'=>$r['mode'],'size'=>$r['size'],'sha256'=>$r['sha256'],'stock'=>$r['stock']];
                if($consent){if(!is_string($r['consent'])||!preg_match('/^[a-f0-9]{64}$/D',$r['consent']))throw new RuntimeException('invalid_state');$files[$name]['consent']=$r['consent'];}
            }
        }
        if($bytes!==$value['bytes'])throw new RuntimeException('invalid_state');ksort($files);return ['files'=>$files,'bytes'=>$bytes];
    }
    private static function bounded(array $value,string $code):void
    {
        try{$raw=json_encode($value,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(strlen($raw)>131072)throw new RuntimeException($code);
    }
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
        if($keys!==$expected||$v['schema_version']!==1||!is_array($v['profile'])||!is_string($v['engine_sha'])||!preg_match('/^[a-f0-9]{64}$/D',$v['engine_sha'])||!is_string($v['source_request_id'])||!preg_match('/^[a-f0-9]{32}$/D',$v['source_request_id'])||!is_string($v['profile_hash'])||AsusSmartDnsProfile::hash($v['profile'])!==$v['profile_hash'])throw new RuntimeException('invalid_state');
        return $v['profile_hash'];
    }
    private static function collect(string $root,int $owner):array
    {
        $root=rtrim($root,'/');AsusUpdateStore::noLinks($root===''?'/':$root);$files=[];$bytes=0;$stock=self::stock($root,$owner);
        $scan=function(string $name)use(&$scan,&$files,&$bytes,$root,$stock,$owner){
            $p=$root.'/'.$name;AsusUpdateStore::noLinks(dirname($p));clearstatcache(true,$p);$s=@lstat($p);if(!$s)return;
            if(($s['mode']&0170000)!==0040000&&count($files)>=512)throw new RuntimeException('output_limit');
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
    /** A bounded settings identity, independent of whether backup copies exist. */
    public static function state(string $root='/',int $owner=0):array
    {$value=self::identity(self::collect($root,$owner),$owner);self::bounded($value,'output_limit');return $value;}
    public static function estimate(string $root='/',int $owner=0):int{return self::state($root,$owner)['bytes'];}
    public static function capture(string $destination,string $root='/',int $owner=0):array
    {
        AsusUpdateStore::noLinks($destination);if(file_exists($destination))throw new RuntimeException('invalid_state');$v=self::state($root,$owner);$root=rtrim($root,'/');
        $free=disk_free_space(dirname($destination));if($free===false||$free<$v['bytes']+4194304)throw new RuntimeException('insufficient_space');
        $raw=json_encode($v,JSON_THROW_ON_ERROR);$index=[];
        foreach($v['files']as $name=>$r)if($r['type']==='file')$index[$name]=['mode'=>0600,'size'=>$r['size'],'sha256'=>$r['sha256']];
        $index['native-snapshot.json']=['mode'=>0600,'size'=>strlen($raw),'sha256'=>hash('sha256',$raw)];
        $cleanup=json_encode(['files'=>$index],JSON_THROW_ON_ERROR);
        $planned=$index+['snapshot.json'=>['mode'=>0600,'size'=>strlen($cleanup),'sha256'=>hash('sha256',$cleanup)]];
        $staging=json_encode(['files'=>$planned],JSON_THROW_ON_ERROR);if(strlen($staging)>131072||strlen($cleanup)>131072)throw new RuntimeException('output_limit');
        $mask=umask(0077);try{if(!mkdir($destination,0700))throw new RuntimeException('invalid_state');
            // Publish ownership atomically before the first potentially large
            // copy. A killed copy leaves only these exact reclaimable paths.
            $temporary=$destination.'/.stage-staging.json';$f=@fopen($temporary,'xb');if(!$f)throw new RuntimeException('insufficient_space');
            try{if(!chmod($temporary,0600)||fwrite($f,$staging)!==strlen($staging)||!fflush($f)||!rename($temporary,$destination.'/staging.json'))throw new RuntimeException('insufficient_space');}
            finally{fclose($f);if(file_exists($temporary))unlink($temporary);}
            foreach($v['files']as $name=>$r){if($r['type']!=='file')continue;$out=$destination.'/'.$name;
                if(!is_dir(dirname($out))&&!mkdir(dirname($out),0700,true))throw new RuntimeException('invalid_state');
                if(!copy($root.'/'.$name,$out)||!chmod($out,0600)||filesize($out)!==$r['size']||hash_file('sha256',$out)!==$r['sha256'])throw new RuntimeException('settings_changed');}
            // Pruning uses the backup's actual protected mode, not the user's mode.
            if(file_put_contents($destination.'/native-snapshot.json',$raw)!==strlen($raw)||file_put_contents($destination.'/snapshot.json',$cleanup)!==strlen($cleanup))throw new RuntimeException('insufficient_space');
        }finally{umask($mask);}
        if(self::state($root,$owner)!==$v)throw new RuntimeException('settings_changed');
        if(!unlink($destination.'/staging.json'))throw new RuntimeException('invalid_state');return $v;
    }
    public static function verify(string $destination,string $root='/',int $owner=0):bool
    {
        AsusUpdateStore::noLinks($destination);$file=$destination.'/native-snapshot.json';$s=@lstat($file);
        if(!$s||!is_file($file)||is_link($file)||$s['uid']!==$owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>131072)throw new RuntimeException('invalid_state');
        try{$v=json_decode((string)file_get_contents($file),true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(!is_array($v))throw new RuntimeException('invalid_state');$v=self::identity($v,$owner);
        foreach($v['files']as $name=>$r){
            if($r['type']==='file'){$p=$destination.'/'.$name;AsusUpdateStore::noLinks($p);$b=@lstat($p);if(!$b||!is_file($p)||$b['uid']!==$owner||$b['nlink']!==1||($b['mode']&0777)!==0600||$b['size']!==$r['size']||hash_file('sha256',$p)!==$r['sha256'])throw new RuntimeException('invalid_state');}
        }
        return self::verifyState($v,$root,$owner);
    }
    /** Verify live settings only; incomplete copies cannot weaken this proof. */
    public static function verifyState(array $saved,string $root='/',int $owner=0):bool
    {
        $saved=self::identity($saved,$owner);self::bounded($saved,'invalid_state');$now=self::state($root,$owner);
        foreach($saved['files']as $name=>$r){
            $new=$now['files'][$name]??null;
            if($new===$r)continue;
            if(isset($r['consent'])&&is_array($new)&&($new['consent']??null)===$r['consent']&&$new['uid']===$r['uid']&&$new['gid']===$r['gid']&&$new['mode']===$r['mode'])continue;
            // An untouched old stock resource may become the new proven stock.
            if(($r['stock']??false)&&is_array($new)&&($new['stock']??false)&&$new['uid']===$r['uid']&&$new['gid']===$r['gid']&&$new['mode']===$r['mode'])continue;
            throw new RuntimeException('settings_changed');
        }
        foreach($now['files']as $name=>$r)if(!isset($saved['files'][$name])&&!$r['stock'])throw new RuntimeException('settings_changed');
        return true;
    }
}
