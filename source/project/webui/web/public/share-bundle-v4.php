<?php
require_once __DIR__.'/share-v4.php';
/** V4's extended boundary is separate; the reviewed legacy V3 bytes stay intact. */
final class AsusShareBundle4
{
    private static function manifest(array $files): string
    {
        if(!array_is_list($files)||count($files)<1||count($files)>5)throw new RuntimeException('invalid_share');
        $order=['report'=>0,'dpi'=>1,'strategy'=>2,'resources'=>3,'dns'=>4];
        $limits=['report'=>1048576,'dpi'=>262144,'strategy'=>65536,'resources'=>786432,'dns'=>131072];
        $prefixes=['dpi'=>'DPI','strategy'=>'STRATEGY','resources'=>'RESOURCES','dns'=>'DNS'];$last=-1;$manifest=[];$documents=[];
        foreach($files as $f) {
            if(!is_array($f))throw new RuntimeException('invalid_share');$keys=array_keys($f);sort($keys);$type=$f['type']??null;
            $at=is_string($type)?($order[$type]??-1):-1;
            if($keys!==['byte_length','data_base64','filename','sha256','type']||$at<=$last||!is_int($f['byte_length'])||$f['byte_length']<1||$f['byte_length']>$limits[$type]||
                !is_string($f['filename'])||strlen($f['filename'])>128||!preg_match('/^NFQWS2_[A-Za-z0-9_-]+_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}Z\.json$/D',$f['filename'])||
                !is_string($f['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$f['sha256'])||!is_string($f['data_base64'])||strlen($f['data_base64'])>4*(int)ceil($limits[$type]/3))throw new RuntimeException('invalid_share');
            $raw=base64_decode($f['data_base64'],true);
            if(!is_string($raw)||strlen($raw)!==$f['byte_length']||base64_encode($raw)!==$f['data_base64']||!hash_equals($f['sha256'],hash('sha256',$raw)))throw new RuntimeException('invalid_share');
            if(in_array($type,['strategy','resources','dns'],true))$v=AsusShareV4Payloads::validate($type,$raw);
            else {
                $kind=$type;
                if($type==='dpi'){$content=AsusSupportSchema::decode($raw,262144,'invalid_dpi');$kind=is_object($content)&&($content->type??null)==='nfqws2_dpi_saved'?'dpi_saved':'dpi';}
                $v=AsusSupportSchema::validate($raw,$kind);
            }
            if($type==='report') {
                $expected='NFQWS2_'.$v['model'].'_'.str_replace(['T',':'],['_','-'],substr($v['captured_at'],0,-1)).'Z.json';
                if($expected!==$f['filename'])throw new RuntimeException('invalid_share');
            }elseif(!str_starts_with($f['filename'],'NFQWS2_'.$prefixes[$type].'_'))throw new RuntimeException('invalid_share');
            $documents[$type]=$v;$last=$at;$manifest[]=implode("\0",[$type,$f['filename'],(string)$f['byte_length'],$f['sha256']]);
        }
        AsusShareV4Payloads::bundle($documents);
        return implode("\0",$manifest);
    }
    private static function source(array $files,?array $source): string
    {
        if($source===null)return '';
        AsusSupportSchema::validate(json_encode(['version'=>4,'submission_id'=>'00000000-0000-4000-8000-000000000000','files'=>$files,'source'=>$source],JSON_THROW_ON_ERROR),'share4');
        $sort=function(array $v)use(&$sort):array {ksort($v);foreach($v as &$x)if(is_array($x))$x=$sort($x);return $v;};
        return "\0SOURCE\0".json_encode($sort($source),JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
    }
    public static function prepare(array $files,string $sessionKey,int $now,?array $source=null): array
    {
        if(!preg_match('/^[a-f0-9]{64}$/D',$sessionKey)||$now<1)throw new RuntimeException('invalid_proof');
        $manifest=self::manifest($files).self::source($files,$source);$nonce=bin2hex(random_bytes(16));
        $proof='v4.'.$now.'.'.$nonce.'.'.hash_hmac('sha256',"NFQWS2-SHARE\0v4\0$now\0$nonce\0".$manifest,hex2bin($sessionKey));
        $out=['version'=>4,'files'=>$files,'proof'=>$proof];if($source!==null)$out['source']=$source;
        if(strlen(json_encode($out,JSON_THROW_ON_ERROR))>4194304)throw new RuntimeException('output_limit');
        return $out;
    }
    public static function verify(string $proof,array $files,string $sessionKey,int $now,?array $source=null): bool
    {
        try {
            if(!preg_match('/^[a-f0-9]{64}$/D',$sessionKey)||!preg_match('/^v4\.([1-9][0-9]{0,9})\.([a-f0-9]{32})\.([a-f0-9]{64})$/D',$proof,$m))return false;
            $issued=(int)$m[1];if((string)$issued!==$m[1]||$issued>$now||$now-$issued>600)return false;
            return hash_equals($m[3],hash_hmac('sha256',"NFQWS2-SHARE\0v4\0$issued\0".$m[2]."\0".self::manifest($files).self::source($files,$source),hex2bin($sessionKey)));
        }catch(Throwable $e){return false;}
    }
    public static function envelope(string $raw,string $id): array
    {
        $v=AsusSupportSchema::validate($raw,'share4');
        if($v['submission_id']!==$id)throw new RuntimeException('invalid_share');self::manifest($v['files']);return $v;
    }
}
