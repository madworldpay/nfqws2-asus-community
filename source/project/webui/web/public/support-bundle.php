<?php
require_once __DIR__.'/support-mail-proof.php';
require_once __DIR__.'/support-json-schema.php';
require_once __DIR__.'/dpi-store.php';
/** Exact immutable two-file snapshot; never makes a network request. */
final class AsusSupportBundle
{
    public function __construct(private ?AsusDpiStore $store=null){}
    public static function file(string $type,string $filename,string $raw): array
    {return ['type'=>$type,'filename'=>$filename,'byte_length'=>strlen($raw),'sha256'=>hash('sha256',$raw),'data_base64'=>base64_encode($raw)];}
    private static function manifest(array $files): string
    {
        if(!array_is_list($files)||count($files)!==2)throw new RuntimeException('invalid_bundle');$parts=[];
        foreach($files as $i=>$f) {
            $keys=is_array($f)?array_keys($f):[];sort($keys);
            if($keys!==['byte_length','data_base64','filename','sha256','type']||($f['type']??null)!==($i===0?'report':'dpi')||
                !is_int($f['byte_length'])||$f['byte_length']<1||$f['byte_length']>($i===0?1048576:262144)||!is_string($f['filename'])||
                !preg_match($i===0?'/^NFQWS2_[A-Za-z0-9_-]{1,64}_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}Z\.json$/D':'/^NFQWS2_DPI_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}Z\.json$/D',$f['filename'])||
                !is_string($f['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$f['sha256'])||!is_string($f['data_base64'])||strlen($f['data_base64'])>($i===0?1398104:349528))throw new RuntimeException('invalid_bundle');
            $raw=base64_decode($f['data_base64'],true);
            if(!is_string($raw)||base64_encode($raw)!==$f['data_base64']||strlen($raw)!==$f['byte_length']||!hash_equals($f['sha256'],hash('sha256',$raw)))throw new RuntimeException('invalid_bundle');
            $parts[]=implode("\0",[$f['type'],$f['filename'],(string)$f['byte_length'],$f['sha256']]);
        }
        return implode("\0",$parts);
    }
    public static function issue(array $files,string $key,int $now): string
    {
        if(!preg_match('/^[a-f0-9]{64}$/D',$key))throw new RuntimeException('invalid_key');$nonce=bin2hex(random_bytes(16));
        $msg="NFQWS2-BUNDLE\0v2\0$now\0$nonce\0".self::manifest($files);
        return 'v2.'.$now.'.'.$nonce.'.'.hash_hmac('sha256',$msg,hex2bin($key));
    }
    public static function verify(string $proof,array $files,string $sessionKey,int $now): bool
    {
        try {
            if(!preg_match('/^[a-f0-9]{64}$/D',$sessionKey)||!preg_match('/^v2\.([1-9][0-9]{0,9})\.([a-f0-9]{32})\.([a-f0-9]{64})$/D',$proof,$m))return false;
            $issued=(int)$m[1];if((string)$issued!==$m[1]||$issued>$now||$now-$issued>600)return false;
            return hash_equals($m[3],hash_hmac('sha256',"NFQWS2-BUNDLE\0v2\0$issued\0".$m[2]."\0".self::manifest($files),hex2bin($sessionKey)));
        }catch(Throwable $e){return false;}
    }
    public function prepare(string $report,string $filename,string $reportProof,string $jobId,string $sessionKey,int $now): array
    {
        if(!AsusReportProof::verify($reportProof,$report,$filename,$sessionKey,$now))throw new RuntimeException('invalid_proof');
        $main=AsusSupportSchema::validate($report,'report');
        if($filename!=='NFQWS2_'.$main['model'].'_'.str_replace(['T',':'],['_','-'],substr($main['captured_at'],0,-1)).'Z.json')throw new RuntimeException('invalid_bundle');
        $dpi=($this->store??new AsusDpiStore())->readResult($jobId);$value=AsusSupportSchema::validate($dpi,'dpi');
        if($value['groups']===[])throw new RuntimeException('result_unavailable');
        $name='NFQWS2_DPI_'.str_replace(['T',':'],['_','-'],substr($value['started_at'],0,-1)).'Z.json';
        $files=[self::file('report',$filename,$report),self::file('dpi',$name,$dpi)];
        return ['files'=>$files,'proof'=>self::issue($files,$sessionKey,$now)];
    }
    public static function envelope(string $raw,string $submissionId): array
    {
        if(strlen($raw)>2097152)throw new RuntimeException('invalid_bundle');
        $v=AsusSupportSchema::validate($raw,'envelope');if($v['submission_id']!==$submissionId)throw new RuntimeException('invalid_bundle');self::manifest($v['files']);
        foreach($v['files'] as $f)AsusSupportSchema::validate(base64_decode($f['data_base64'],true),$f['type']==='report'?'report':'dpi');
        return $v;
    }
}
