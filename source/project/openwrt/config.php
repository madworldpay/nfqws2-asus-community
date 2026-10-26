<?php
if(!class_exists('AsusImportConfig',false))require_once __DIR__.'/import-config.php';

/** The daemon consumes normalized quoted assignments, never sources uploaded shell. */
final class NfqwsNativeConfig
{
    private const DEFAULTS=[
        'ISP_INTERFACE'=>'','NFQUEUE_NUM'=>'300','USER'=>'nobody','IPV6_ENABLED'=>'0',
        'TCP_PORTS'=>'80,443','UDP_PORTS'=>'443','ASUS_CLIENT_MODE'=>'all',
        'ASUS_CLIENTS4'=>'','ASUS_CLIENTS6'=>'','LOG_LEVEL'=>'0',
        'LOG_DEBUG_PATH'=>'@/var/log/nfqws2-debug.log',
        'NFQWS_BASE_ARGS'=>'','NFQWS_EXTRA_ARGS'=>'','NFQWS_ARGS'=>'',
        'NFQWS_ARGS_QUIC'=>'','NFQWS_ARGS_UDP'=>'','NFQWS_ARGS_CUSTOM'=>'',
        'NFQWS_ARGS_IPSET'=>''
    ];
    public static function parse(string $text): array
    {
        $strategies=AsusImportConfig::parse($text);
        $settings=AsusImportConfig::literalValues($text,array_diff(array_keys(self::DEFAULTS),
            array_merge(AsusImportConfig::BLOCKS,AsusImportConfig::SHARED,AsusImportConfig::PORTS)));
        $values=array_replace(self::DEFAULTS,array_intersect_key($strategies,self::DEFAULTS),$settings);
        foreach($values as $key=>$value) {
            if(strlen($value)>65536||preg_match('/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/',$value))throw new RuntimeException('invalid_native_config');
            if(str_starts_with($key,'NFQWS_'))foreach(preg_split('/\s+/',$value,-1,PREG_SPLIT_NO_EMPTY)as$token) {
                if($token[0]==='@'||preg_match('/^-[^-]/',$token))throw new RuntimeException('reserved_engine_option');
                if(!str_starts_with($token,'--'))continue;
                $option=explode('=',substr($token,2),2)[0];
                foreach(['daemon','pidfile','qnum','user','uid','dry-run','version','help','intercept','chdir']as$reserved)
                    if($option===''||str_starts_with($reserved,$option))throw new RuntimeException('reserved_engine_option');
            }
        }
        if(!preg_match('/^[a-z_][a-z0-9_-]{0,31}$/D',$values['USER'])||
           !preg_match('/^[01]$/D',$values['LOG_LEVEL'])||
           !preg_match('/^[01]$/D',$values['IPV6_ENABLED']))throw new RuntimeException('invalid_native_config');
        return $values;
    }
    public static function shell(array $values): string
    {
        if(array_diff(array_keys($values),array_keys(self::DEFAULTS)))throw new RuntimeException('invalid_native_config');
        $out='';foreach($values as $key=>$value){if(!is_string($value))throw new RuntimeException('invalid_native_config');$out.=$key.'='.escapeshellarg($value)."\n";}
        return $out;
    }
}
