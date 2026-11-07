<?php
/** A netlink port ID is not a PID, including signed u32 IDs on Linux 2.6. */
final class NfqwsDeviceProfilesQueues
{
    private static function decimal(string $value,string $max):bool
    {return preg_match('/^(?:0|[1-9][0-9]*)$/D',$value)===1&&(strlen($value)<strlen($max)||(strlen($value)===strlen($max)&&strcmp($value,$max)<=0));}
    private static function lines(string $path):array
    {
        $raw=@file_get_contents($path,false,null,0,65537);
        if(!is_string($raw)||strlen($raw)>65536||str_contains($raw,"\0"))throw new RuntimeException('queue_conflict');
        $rows=explode("\n",trim($raw));if(count($rows)>4096)throw new RuntimeException('queue_conflict');return $rows;
    }
    private static function socket(int $queue,string $proc):array
    {
        $port=null;
        foreach(self::lines($proc.'/net/netfilter/nfnetlink_queue')as $line){
            if($line==='')continue;$row=preg_split('/\s+/',trim($line));if(count($row)!==9)throw new RuntimeException('queue_conflict');
            if($row[0]!==strval($queue))continue;
            $value=$row[1];$valid=$value!==''&&$value!=='0'&&$value!=='-0'&&($value[0]==='-'?self::decimal(substr($value,1),'2147483648'):self::decimal($value,'4294967295'));
            if($port!==null||!$valid)throw new RuntimeException('queue_conflict');$port=$value;
        }
        if($port===null)throw new RuntimeException('queue_conflict');
        $rows=self::lines($proc.'/net/netlink');$header=preg_split('/\s+/',trim(array_shift($rows)??''));
        if($header!==['sk','Eth','Pid','Groups','Rmem','Wmem','Dump','Locks','Drops','Inode'])throw new RuntimeException('queue_conflict');
        $inode=null;$seen=[];
        foreach($rows as $line){
            if($line==='')continue;$row=preg_split('/\s+/',trim($line));if(count($row)!==10)throw new RuntimeException('queue_conflict');
            if($row[1]==='12'&&$row[2]===$port){
                if($inode!==null||$row[9]==='0'||!self::decimal($row[9],'18446744073709551615'))throw new RuntimeException('queue_conflict');$inode=$row[9];
            }
            $seen[]=$row[9];
        }
        if($inode===null||count(array_keys($seen,$inode,true))!==1)throw new RuntimeException('queue_conflict');return [$port,$inode];
    }
    public static function owned(int $queue,int $pid,string $proc='/proc'):bool
    {
        if($pid<2)return false;
        try{
            $socket=self::socket($queue,$proc);$dir=$proc.'/'.$pid.'/fd';$handle=@opendir($dir);if(!$handle)return false;$owned=null;$count=0;
            try{while(($fd=readdir($handle))!==false){
                if($fd==='.'||$fd==='..')continue;if(++$count>1024||!self::decimal($fd,'2147483647'))return false;
                if(@readlink($dir.'/'.$fd)==='socket:['.$socket[1].']')$owned=$fd;
            }}finally{closedir($handle);}
            return $owned!==null&&self::socket($queue,$proc)===$socket&&@readlink($dir.'/'.$owned)==='socket:['.$socket[1].']';
        }catch(Throwable $e){return false;}
    }
}
