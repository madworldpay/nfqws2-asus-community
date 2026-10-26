<?php
require_once __DIR__.'/update-store.php';
require_once __DIR__.'/platform.php';

/** Read-only identity of the old package; partial replacement cannot be restarted. */
final class NfqwsOpenWrtUpdatePayload
{
    public static function fromPaths(array $paths,string $root='/',int $owner=0):array
    {
        if(!array_is_list($paths)||count($paths)<1||count($paths)>512)throw new RuntimeException('invalid_state');
        $root=rtrim($root,'/');AsusUpdateStore::noLinks($root===''?'/':$root);$files=[];$bytes=0;
        foreach($paths as $name){
            if(!is_string($name)||strlen($name)>512||!preg_match('~^/(?:usr/bin/nfqws2|usr/(?:lib/nfqws2(?:-web)?|share/nfqws2(?:-web)?|share/licenses/nfqws2-native)/[A-Za-z0-9_+./-]+|lib/upgrade/keep\.d/nfqws2-native|lib/apk/packages/nfqws2-native\.list|lib/apk/commit_hooks\.d/10-nfqws2-native)$~D',$name)||in_array('..',explode('/',$name),true)||in_array('.',explode('/',$name),true)||isset($files[$name]))throw new RuntimeException('invalid_state');
            $path=$root.$name;AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$s=@lstat($path);
            if(!$s||!is_file($path)||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>33554432)throw new RuntimeException('invalid_state');
            $bytes+=$s['size'];if($bytes>134217728)throw new RuntimeException('output_limit');$hash=hash_file('sha256',$path);if(!is_string($hash))throw new RuntimeException('invalid_state');
            $files[$name]=['uid'=>$s['uid'],'gid'=>$s['gid'],'mode'=>$s['mode']&0777,'size'=>$s['size'],'sha256'=>$hash];
        }
        ksort($files);return ['files'=>$files];
    }
    public static function capture(string $format):array
    {
        if($format==='ipk'){
            $r=NfqwsPlatform::run(['/bin/opkg','files','nfqws2-native'],5);if($r['status']!==0)throw new RuntimeException('invalid_state');$paths=$r['output'];
            $header=array_shift($paths);if(!is_string($header)||!preg_match('/^Package nfqws2-native \([^\r\n]+\) is installed on root and has the following files:$/D',$header))throw new RuntimeException('invalid_state');
        }elseif($format==='apk'){
            $file='/lib/apk/packages/nfqws2-native.list';AsusUpdateStore::noLinks($file);$s=@lstat($file);
            if(!$s||!is_file($file)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0022)!==0||$s['size']>65536)throw new RuntimeException('invalid_state');
            $paths=explode("\n",rtrim((string)file_get_contents($file),"\n"));
        }else throw new RuntimeException('unsupported_abi');
        return self::fromPaths($paths);
    }
    public static function unchanged(array $snapshot,string $root='/',int $owner=0):bool
    {
        try{return array_keys($snapshot)===['files']&&is_array($snapshot['files'])&&self::fromPaths(array_keys($snapshot['files']),$root,$owner)===$snapshot;}
        catch(Throwable $e){return false;}
    }
}
