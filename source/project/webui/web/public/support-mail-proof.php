<?php
/** Session-bound proof of the exact collector attachment, never part of it. */
final class AsusReportProof
{
    private static function message(string $raw,string $filename,int $issued,string $nonce): string
    { return "NFQWS2-REPORT\0v1\0$issued\0$nonce\0$filename\0".$raw; }
    public static function issue(string $raw,string $filename,string $key,int $now): string
    {
        if(!preg_match('/^[a-f0-9]{64}$/D',$key))throw new RuntimeException('invalid_key');
        $nonce=bin2hex(random_bytes(16));
        return 'v1.'.$now.'.'.$nonce.'.'.hash_hmac('sha256',self::message($raw,$filename,$now,$nonce),hex2bin($key));
    }
    public static function verify(string $proof,string $raw,string $filename,string $key,int $now): bool
    {
        if(strlen($raw)>1048576||!preg_match('/^[a-f0-9]{64}$/D',$key)||
           !preg_match('/^v1\.([1-9][0-9]{0,9})\.([a-f0-9]{32})\.([a-f0-9]{64})$/D',$proof,$m))return false;
        $issued=(int)$m[1];
        if((string)$issued!==$m[1]||$issued>$now||$now-$issued>600)return false;
        return hash_equals(hash_hmac('sha256',self::message($raw,$filename,$issued,$m[2]),hex2bin($key)),$m[3]);
    }
}
