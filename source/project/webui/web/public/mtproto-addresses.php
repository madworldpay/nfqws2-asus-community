<?php
require_once __DIR__.'/platform.php';
/** Fixed local firmware reads only. No scans, remote lookups or write commands. */
final class AsusMtprotoAddresses
{
    public static function validate(array $post): void
    {
        $keys=array_keys($post);sort($keys);
        if($keys!==['cmd','csrf_token']||$post['cmd']!=='mtprotoaddresses'||!is_string($post['csrf_token'])||strlen($post['csrf_token'])>1024)throw new RuntimeException('invalid_request');
    }
    private static function ip(mixed $value): ?string
    {
        if(!is_string($value))return null;$value=trim($value);
        if(!preg_match('/^(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}$/D',$value))return null;
        $parts=array_map('intval',explode('.',$value));
        if(max($parts)>255)return null;
        if(in_array($parts[0],[0,127],true)||$parts[0]>=224||($parts[0]===169&&$parts[1]===254))return null;
        return $value;
    }
    public static function collect(?callable $read=null): array
    {
        $read??=function(string $key): ?string {
            if(NfqwsPlatform::native())return null;
            foreach(['/bin/nvram','/usr/sbin/nvram','/sbin/nvram']as $binary)if(is_executable($binary)){
                $r=NfqwsPlatform::run([$binary,'get',$key],1,[],256);
                return $r['status']===0?implode("\n",$r['output']):null;
            }
            return null;
        };
        return ['router'=>self::ip($read('lan_ipaddr')),'docker'=>self::ip($read('ai_sys_ip_address'))];
    }
}
