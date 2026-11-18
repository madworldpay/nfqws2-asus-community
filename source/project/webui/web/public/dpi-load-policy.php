<?php
/** Typed requests and observed resources; hardware capacity is not prescribed. */
final class AsusDpiLoadPolicy
{
    public const REQUEST_MAX=1000000;
    // The existing normalized report schema covers at most 1000 TCP rows.
    public const TCP_TARGET_MAX=1000;
    public const FD_RESERVE=32;
    public const STANDARD_MAX=100;
    public static function availableMemoryKiB(string $raw):int
    {
        foreach(['MemAvailable','MemFree']as $key){
            $count=preg_match_all('/^'.$key.':/m',$raw);if($count===0)continue;if($count!==1)return 0;
            if(preg_match_all('/^'.$key.':\s+([0-9]{1,10}) kB\s*$/m',$raw,$m)!==1)return 0;
            $value=(float)$m[1][0];return $value<=2147483647?(int)$value:0;
        }
        return 0;
    }
    public static function cores(string $raw):int
    {
        if(strlen($raw)>1048576)return 0;$seen=[];
        foreach(explode("\n",$raw)as $line){
            if(!str_starts_with($line,'cpu')||preg_match('/^cpu\s/',$line))continue;
            if(!preg_match('/^cpu([0-9]{1,5})\s+[0-9]+(?:\s+[0-9]+){3,11}\s*$/D',$line,$m)||isset($seen[$m[1]]))return 0;
            $seen[$m[1]]=true;
        }
        return count($seen);
    }
    public static function fileDescriptors(string $raw):int
    {
        if(preg_match_all('/^Max open files\b/m',$raw)!==1||
            !preg_match('/^Max open files\s+(unlimited|[0-9]{1,10})\s+(?:unlimited|[0-9]{1,10})\s+files\s*$/m',$raw,$m))return 0;
        if($m[1]==='unlimited')return 2147483647;
        $n=(float)$m[1];return $n<=2147483647?(int)$n:0;
    }
    public static function plan(mixed $pool,int $cores,int $availableKiB,?int $fdSoft=null,bool $largeTcp=false):array
    {
        if(!is_int($pool)||$pool<1||$pool>self::REQUEST_MAX)return ['available'=>false,'code'=>'invalid_request'];
        // Observations describe the device; the requested pool is never reduced
        // or refused using an assumed CPU, RAM or file-descriptor capacity.
        return ['available'=>true,'code'=>'ready','worker_threads'=>($pool>self::STANDARD_MAX||$largeTcp)?4:null,'memory_floor_kib'=>0];
    }
    public static function runtime(array $options):array
    {
        return self::plan($options['config']['MAX_CONCURRENT']??50,
            self::cores((string)@file_get_contents('/proc/stat')),
            self::availableMemoryKiB((string)@file_get_contents('/proc/meminfo')),
            self::fileDescriptors((string)@file_get_contents('/proc/self/limits')),
            count($options['targets']['tcp']??[])>512);
    }
    /** A large report needs more heap than the firmware CGI default. This is
     * request-local, never a change to php.ini or the native process limits. */
    public static function reportMemory(array $options):void
    {
        if(count($options['targets']['tcp']??[])<=512)return;
        $plan=self::runtime($options);
        if(!$plan['available'])throw new RuntimeException($plan['code']);
        $read=static function():float {
            if(!function_exists('ini_get'))return 0;
            $raw=trim((string)ini_get('memory_limit'));
            if($raw==='-1')return INF;
            if(!preg_match('/^([1-9][0-9]{0,12})([KMG]?)$/iD',$raw,$m))return 0;
            return (float)$m[1]*match(strtoupper($m[2])){'K'=>1024,'M'=>1048576,'G'=>1073741824,default=>1};
        };
        $current=$read();
        if($current>=33554432)return;
        if($current<=0||!function_exists('ini_set')||@ini_set('memory_limit','32M')===false||$read()<33554432)
            throw new RuntimeException('unsupported_runtime');
    }
}
