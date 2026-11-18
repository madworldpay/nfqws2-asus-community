<?php
/** Conservative special-use rejection, using bytes on both32- and64-bit PHP. */
final class NfqwsPublicIpv4
{
    public static function test(mixed $ip): bool
    {
        if(!is_string($ip)||!preg_match('/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/D',$ip))return false;
        $packed=@inet_pton($ip);if($packed===false||strlen($packed)!==4||inet_ntop($packed)!==$ip)return false;
        foreach([['0.0.0.0',8],['10.0.0.0',8],['100.64.0.0',10],['127.0.0.0',8],['169.254.0.0',16],['172.16.0.0',12],
            ['192.0.0.0',24],['192.0.2.0',24],['192.31.196.0',24],['192.52.193.0',24],['192.88.99.0',24],['192.168.0.0',16],
            ['192.175.48.0',24],['198.18.0.0',15],['198.51.100.0',24],['203.0.113.0',24],['224.0.0.0',4],['240.0.0.0',4]]as[$network,$bits]){
            $base=inet_pton($network);$whole=intdiv($bits,8);$rest=$bits%8;
            if(substr($packed,0,$whole)===substr($base,0,$whole)&&($rest===0||((ord($packed[$whole])^ord($base[$whole]))>>(8-$rest))===0))return false;
        }
        return true;
    }
}
