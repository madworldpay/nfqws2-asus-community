<?php
require_once __DIR__.'/support-json-schema.php';
/** One immutable, ordered snapshot; old report contracts remain separate. */
final class AsusShareBundle
{
    public static function file(string $type,string $filename,string $raw): array
    {return ['type'=>$type,'filename'=>$filename,'byte_length'=>strlen($raw),'sha256'=>hash('sha256',$raw),'data_base64'=>base64_encode($raw)];}
    private static function manifest(array $files): string
    {
        if(!array_is_list($files)||count($files)<1||count($files)>3)throw new RuntimeException('invalid_share');
        $order=['report'=>0,'dpi'=>1,'strategy'=>2];$limits=[1048576,262144,65536];$last=-1;$manifest=[];
        foreach($files as $f) {
            if(!is_array($f))throw new RuntimeException('invalid_share');$keys=array_keys($f);sort($keys);
            $type=$f['type']??null;$at=is_string($type)?($order[$type]??-1):-1;
            if($keys!==['byte_length','data_base64','filename','sha256','type']||$at<=$last||!is_int($f['byte_length'])||$f['byte_length']<1||$f['byte_length']>$limits[$at]||
                !is_string($f['filename'])||strlen($f['filename'])>128||!preg_match('/^NFQWS2_[A-Za-z0-9_-]+_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}Z\.json$/D',$f['filename'])||
                !is_string($f['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$f['sha256'])||!is_string($f['data_base64'])||strlen($f['data_base64'])>4*(int)ceil($limits[$at]/3))throw new RuntimeException('invalid_share');
            $raw=base64_decode($f['data_base64'],true);
            if(!is_string($raw)||strlen($raw)!==$f['byte_length']||base64_encode($raw)!==$f['data_base64']||!hash_equals($f['sha256'],hash('sha256',$raw)))throw new RuntimeException('invalid_share');
            $kind=$type;
            if($type==='dpi'){$value=AsusSupportSchema::decode($raw,262144,'invalid_dpi');$kind=is_object($value)&&($value->type??null)==='nfqws2_dpi_saved'?'dpi_saved':'dpi';}
            $value=AsusSupportSchema::validate($raw,$kind);
            if($type==='report') {
                $expected='NFQWS2_'.$value['model'].'_'.str_replace(['T',':'],['_','-'],substr($value['captured_at'],0,-1)).'Z.json';
                if($f['filename']!==$expected)throw new RuntimeException('invalid_share');
            }elseif(!str_starts_with($f['filename'],$type==='dpi'?'NFQWS2_DPI_':'NFQWS2_STRATEGY_'))throw new RuntimeException('invalid_share');
            $last=$at;$manifest[]=implode("\0",[$type,$f['filename'],(string)$f['byte_length'],$f['sha256']]);
        }
        return implode("\0",$manifest);
    }
    private static function sourceManifest(array $files,?array $source): string
    {
        if($source===null)return '';
        AsusSupportSchema::validate(json_encode(['version'=>3,'submission_id'=>'00000000-0000-4000-8000-000000000000','files'=>$files,'source'=>$source],JSON_THROW_ON_ERROR),'share');
        $sort=function(array $v)use(&$sort):array {ksort($v);foreach($v as &$x)if(is_array($x))$x=$sort($x);return $v;};
        return "\0SOURCE\0".json_encode($sort($source),JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
    }
    public static function prepare(array $files,string $sessionKey,int $now,?array $source=null,int $version=3): array
    {
        if($version===4){require_once __DIR__.'/share-bundle-v4.php';return AsusShareBundle4::prepare($files,$sessionKey,$now,$source);}
        if($version!==3)throw new RuntimeException('invalid_share');
        if(!preg_match('/^[a-f0-9]{64}$/D',$sessionKey)||$now<1)throw new RuntimeException('invalid_proof');
        $manifest=self::manifest($files).self::sourceManifest($files,$source);$nonce=bin2hex(random_bytes(16));
        $proof='v3.'.$now.'.'.$nonce.'.'.hash_hmac('sha256',"NFQWS2-SHARE\0v3\0$now\0$nonce\0".$manifest,hex2bin($sessionKey));
        $out=['files'=>$files,'proof'=>$proof];if($source!==null)$out['source']=$source;
        if(strlen(json_encode($out,JSON_THROW_ON_ERROR))>2097152)throw new RuntimeException('output_limit');
        return $out;
    }
    public static function verify(string $proof,array $files,string $sessionKey,int $now,?array $source=null): bool
    {
        if(str_starts_with($proof,'v4.')){require_once __DIR__.'/share-bundle-v4.php';return AsusShareBundle4::verify($proof,$files,$sessionKey,$now,$source);}
        try {
            if(!preg_match('/^[a-f0-9]{64}$/D',$sessionKey)||!preg_match('/^v3\.([1-9][0-9]{0,9})\.([a-f0-9]{32})\.([a-f0-9]{64})$/D',$proof,$m))return false;
            $issued=(int)$m[1];if((string)$issued!==$m[1]||$issued>$now||$now-$issued>600)return false;
            return hash_equals($m[3],hash_hmac('sha256',"NFQWS2-SHARE\0v3\0$issued\0".$m[2]."\0".self::manifest($files).self::sourceManifest($files,$source),hex2bin($sessionKey)));
        }catch(Throwable $e){return false;}
    }
    public static function envelope(string $raw,string $submissionId): array
    {
        $kind=AsusSupportSchema::decode($raw,4194304,'invalid_share');
        if(is_object($kind)&&($kind->version??null)===4){unset($kind);require_once __DIR__.'/share-bundle-v4.php';return AsusShareBundle4::envelope($raw,$submissionId);}
        unset($kind);
        $v=AsusSupportSchema::validate($raw,'share');
        if($v['submission_id']!==$submissionId)throw new RuntimeException('invalid_share');self::manifest($v['files']);return $v;
    }
}
