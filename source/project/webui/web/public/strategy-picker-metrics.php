<?php

/** Cheap, whole-device telemetry. No actuator, process scan, cache or configuration I/O. */
final class NfqwsStrategyPickerMetrics
{
    // Doubles preserve these integer counters on both 32-bit and 64-bit PHP.
    private static function number(string $value):?float
    {
        if(!preg_match('/^[0-9]{1,16}$/D',$value))return null;
        $n=(float)$value;return $n<=9007199254740991.0?$n:null;
    }
    private static function read(string $path,int $limit):string
    {return (string)@file_get_contents($path,false,null,0,$limit);}

    public static function decode(string $stat,string $meminfo,string $uptime,string $boot,array $sensors):array
    {
        $cpu=null;
        if(preg_match('/^cpu[ \t]+([^\r\n]+)(?:\r?\n|$)/D',$stat,$match)){
            $parts=preg_split('/[ \t]+/',trim($match[1]));$values=[];
            if(count($parts)>=4){
                foreach(array_slice($parts,0,8)as $part){$n=self::number($part);if($n===null){$values=[];break;}$values[]=$n;}
                if(count($values)>=4)$cpu=array_pad($values,8,0.0);
            }
        }
        $memory=null;$mem=[];
        foreach(['MemTotal','MemAvailable','MemFree','Buffers','Cached']as $key){
            $count=preg_match_all('/^'.$key.':[ \t]*([0-9]+)[ \t]+kB[ \t]*$/m',$meminfo,$matches);
            if($count===1)$mem[$key]=self::number($matches[1][0]);
        }
        $total=$mem['MemTotal']??null;$available=$mem['MemAvailable']??null;$estimated=false;
        // Only use the legacy estimate if the kernel does not expose the field.
        // A malformed or duplicated MemAvailable is not a license to replace it.
        if(!preg_match('/^MemAvailable:/m',$meminfo)&&isset($mem['MemFree'],$mem['Buffers'],$mem['Cached'])){
            $available=$mem['MemFree']+$mem['Buffers']+$mem['Cached'];$estimated=true;
        }
        if($total!==null&&$total>0&&$available!==null&&$available>=0&&$available<=$total)
            $memory=['total_kib'=>$total,'available_kib'=>$available,'used_kib'=>$total-$available,'estimated'=>$estimated];

        $up=null;if(preg_match('/^([0-9]{1,12}(?:\.[0-9]{1,6})?)(?:[ \t]|$)/D',trim($uptime),$match))$up=(float)$match[1];
        $boot=trim($boot);$epoch=preg_match('/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/Di',$boot)?hash('sha256',strtolower($boot)):null;
        $temperatures=[];
        foreach(array_slice($sensors,0,16)as $s){
            if(!is_array($s)||!is_string($s['type']??null)||!is_string($s['temp']??null))continue;
            $type=strtolower(trim($s['type']));$kind=null;
            if(in_array($type,['cpu','cpu-thermal','cpu_thermal','x86_pkg_temp'],true))$kind='cpu';
            elseif(in_array($type,['soc','soc-thermal','soc_thermal'],true))$kind='soc';
            $temp=trim($s['temp']);
            if($kind===null||!preg_match('/^-?[0-9]{1,6}$/D',$temp))continue;
            $c=(float)$temp/1000;if($c< -20||$c>150)continue;
            $temperatures[]=['sensor'=>$type,'kind'=>$kind,'celsius'=>$c];
        }
        return ['boot'=>$epoch,'uptime_seconds'=>$up,'cpu_counters'=>$cpu,'memory'=>$memory,'temperatures'=>$temperatures];
    }

    public static function sample():array
    {
        $sensors=[];
        // Thermal zones are kernel-owned; never accept a path from HTTP.
        foreach(array_slice(glob('/sys/class/thermal/thermal_zone[0-9]*')?:[],0,16)as $path){
            if(!preg_match('~/thermal_zone[0-9]+$~D',$path))continue;
            $sensors[]=['type'=>self::read($path.'/type',96),'temp'=>self::read($path.'/temp',32)];
        }
        return self::decode(self::read('/proc/stat',4096),self::read('/proc/meminfo',16384),
            self::read('/proc/uptime',128),self::read('/proc/sys/kernel/random/boot_id',128),$sensors);
    }
}
