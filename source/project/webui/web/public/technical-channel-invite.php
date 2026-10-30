<?php
require_once __DIR__.'/support-json-schema.php';
/** An invitation is data signed by our offline administrator, never a downloaded program. */
final class AsusTechnicalInvite
{
    public const PREFIX='https://github.com/madworldpay/nfqws2-asus-community#technical-channel=v1.';
    private static function unb64(string $s): string
    {
        if($s===''||!preg_match('/^[A-Za-z0-9_-]+$/D',$s))throw new RuntimeException('invalid_invitation');
        $raw=base64_decode(strtr($s,'-_','+/'),true);
        if(!is_string($raw)||rtrim(strtr(base64_encode($raw),'+/','-_'),'=')!==$s)throw new RuntimeException('invalid_invitation');
        return $raw;
    }
    public static function key(string $key): string
    {
        if(!preg_match('~^ssh-ed25519 ([A-Za-z0-9+/]{68})$~D',$key,$m))throw new RuntimeException('invalid_invitation');
        $raw=base64_decode($m[1],true);
        if(!is_string($raw)||strlen($raw)!==51||substr($raw,0,19)!==pack('N',11).'ssh-ed25519'.pack('N',32))throw new RuntimeException('invalid_invitation');
        return substr($raw,19);
    }
    private static function publicIpv4(mixed $ip): bool
    {
        // OpenWrt PHP does not necessarily include the optional filter extension.
        if(!is_string($ip)||!preg_match('/^(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}$/D',$ip))return false;
        [$a,$b,$c,$d]=array_map('intval',explode('.',$ip));if(max($a,$b,$c,$d)>255)return false;
        return !($a===0||$a===10||$a===127||$a>=224||($a===100&&$b>=64&&$b<=127)||($a===169&&$b===254)||($a===172&&$b>=16&&$b<=31)||
            ($a===192&&(($b===168)||($b===0&&in_array($c,[0,2],true))))||($a===198&&($b===18||$b===19||($b===51&&$c===100)))||($a===203&&$b===0&&$c===113));
    }
    public static function verify(string $link,string $pem,int $now): array
    {
        try {
            if(strlen($link)>16384||!str_starts_with($link,self::PREFIX))throw new RuntimeException();
            $parts=explode('.',substr($link,strlen(self::PREFIX)));
            if(count($parts)!==2)throw new RuntimeException();
            [$raw,$signature]=array_map([self::class,'unb64'],$parts);
            if(strlen($raw)>8192||strlen($signature)>512||openssl_verify($raw,$signature,$pem,OPENSSL_ALGO_SHA256)!==1)throw new RuntimeException();
            $v=AsusSupportSchema::decode($raw,8192,'invalid_invitation');
            if(!is_object($v))throw new RuntimeException();$v=(array)$v;
            $keys=['schema_version','purpose','session_id','issued_at','expires_at','server','server_port','server_user','remote_port','host_key','operator_key','tunnel_key'];
            $actual=array_keys($v);sort($actual);sort($keys);if($actual!==$keys)throw new RuntimeException();
            if($v['schema_version']!==1||$v['purpose']!=='technical_channel'||!is_string($v['session_id'])||!preg_match('/^[a-f0-9]{32}$/D',$v['session_id']))throw new RuntimeException();
            foreach(['issued_at','expires_at','server_port','remote_port'] as $k)if(!is_int($v[$k]))throw new RuntimeException();
            if($v['issued_at']>$now+60||$v['issued_at']<1577836800||$v['expires_at']<=$now||$v['expires_at']<=$v['issued_at']||$v['expires_at']-$v['issued_at']>86400)throw new RuntimeException();
            if(!self::publicIpv4($v['server']))throw new RuntimeException();
            if($v['server_port']<1||$v['server_port']>65535||$v['remote_port']<1024||$v['remote_port']>65535||!is_string($v['server_user'])||!preg_match('/^nfqs-[a-f0-9]{12}$/D',$v['server_user']))throw new RuntimeException();
            foreach(['host_key','operator_key'] as $k){if(!is_string($v[$k]))throw new RuntimeException();self::key($v[$k]);}
            if(!is_string($v['tunnel_key'])||strlen($v['tunnel_key'])!==112)throw new RuntimeException();
            $secret=base64_decode($v['tunnel_key'],true);
            if(!is_string($secret)||strlen($secret)!==83||substr($secret,0,19)!==pack('N',11).'ssh-ed25519'.pack('N',64)||base64_encode($secret)!==$v['tunnel_key'])throw new RuntimeException();
            return $v;
        }catch(Throwable $e){throw new RuntimeException('invalid_invitation');}
    }
}
