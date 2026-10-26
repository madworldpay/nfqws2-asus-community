<?php
require_once __DIR__.'/platform.php';
/** Portable resource identities, without opening files or interpreting a shell. */
final class NfqwsResourcePaths
{
    private const FILE_OPTIONS=['--hostlist','--hostlist-exclude','--hostlist-auto','--ipset','--ipset-exclude'];
    public static function canonical(string $path):?string
    {
        if(!preg_match('~^(?:/opt)?/etc/nfqws2/((?:lists|lua|blobs)/([A-Za-z0-9_.-]{1,128}))$~D',$path,$m)||in_array($m[2],['.','..'],true))return null;
        return '/opt/etc/nfqws2/'.$m[1];
    }
    public static function forms(string $path):array
    {
        $canonical=self::canonical($path);return $canonical===null?[$path]:[$canonical,substr($canonical,4)];
    }
    private static function operand(string $value,string $profile):string
    {
        $marker=str_starts_with($value,'@')?'@':'';$path=substr($value,strlen($marker));
        $canonical=self::canonical($path);
        return $canonical===null?$value:$marker.NfqwsPlatform::translate($canonical,$profile);
    }
    /** Tokens have already passed the literal parser. Only known file options
     * are rebound; comments, domain names, Lua source and other values stay data. */
    public static function arguments(array $tokens,?string $profile=null):array
    {
        $profile??=NfqwsPlatform::current();NfqwsPlatform::settings($profile);
        for($i=0;$i<count($tokens);$i++){
            $token=$tokens[$i];if(!is_string($token))throw new RuntimeException('invalid_resource');
            $eq=strpos($token,'=');$option=$eq===false?$token:substr($token,0,$eq);
            if(!in_array($option,array_merge(self::FILE_OPTIONS,['--lua-init','--blob','--debug','--hostlist-auto-debug']),true))continue;
            $separate=$eq===false;$index=$separate?$i+1:$i;
            $value=$separate?($tokens[$index]??''):substr($token,$eq+1);
            if(!is_string($value))throw new RuntimeException('invalid_resource');
            if(in_array($option,['--debug','--hostlist-auto-debug'],true)){
                if(preg_match('/^@?RESOURCE_[1-9][0-9]*$/D',$value))$value=($option==='--debug'?'@':'').NfqwsPlatform::translate('/opt/var/log/nfqws2.log',$profile);
                elseif(preg_match('~^(@?)(?:/opt)?(/var/log/nfqws2(?:[-.][A-Za-z0-9_-]+)?\.log)$~D',$value,$m))$value=$m[1].NfqwsPlatform::translate('/opt'.$m[2],$profile);
            }elseif($option==='--blob'){
                if(preg_match('/^([A-Za-z_][A-Za-z0-9_]*):(@.*)$/D',$value,$m))$value=$m[1].':'.self::operand($m[2],$profile);
            }elseif($option!=='--lua-init'||str_starts_with($value,'@'))$value=self::operand($value,$profile);
            if($separate){if(isset($tokens[$index]))$tokens[$index]=$value;$i++;}
            else $tokens[$index]=$option.'='.$value;
        }
        return $tokens;
    }
}
