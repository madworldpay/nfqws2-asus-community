<?php
final class AsusTechnicalProcess
{
    public static function uptime(): float{return (float)explode(' ',(string)file_get_contents('/proc/uptime'))[0];}
    public static function identity(int $pid): ?array
    {
        if($pid<2)return null;$s=@file_get_contents('/proc/'.$pid.'/stat');$exe=@readlink('/proc/'.$pid.'/exe');
        if(!is_string($s)||!is_string($exe)||!preg_match('/\) (.*)$/s',$s,$m))return null;$f=explode(' ',trim($m[1]));
        if(in_array($f[0]??'Z',['Z','X'],true)||!preg_match('/^[0-9]+$/D',$f[19]??''))return null;
        return ['pid'=>$pid,'starttime'=>$f[19],'exe'=>$exe,'boot_id'=>trim(file_get_contents('/proc/sys/kernel/random/boot_id'))];
    }
    public static function active(array $state,int $now,float $uptime): bool
    {
        $i=$state['identity']??null;
        return is_array($i)&&is_int($i['pid']??null)&&self::identity($i['pid'])===$i&&in_array($state['state']??null,['connecting','connected'],true)&&is_int($state['expires_at']??null)&&$state['expires_at']>$now&&is_numeric($state['uptime_deadline']??null)&&$state['uptime_deadline']>$uptime;
    }
    public static function serverPrefix(string $binary): array
    {return basename($binary)==='dropbearmulti'?[$binary,'dropbear']:[$binary];}
    public static function groupIdentity(int $pid): ?array
    {
        $i=self::identity($pid);$stat=@file_get_contents('/proc/'.$pid.'/stat');
        if(!$i||!is_string($stat)||!preg_match('/\) (.*)$/s',$stat,$m))return null;$f=explode(' ',trim($m[1]));
        $group=(int)($f[2]??0);$session=(int)($f[3]??0);
        if($group<2||$session!==$group||($f[19]??null)!==$i['starttime'])return null;
        return $i+['group'=>$group,'session'=>$session];
    }
    public static function killGroup(?array $i): void
    {
        if(!$i||!is_int($i['pid']??null))return;$now=self::identity($i['pid']);
        if(!$now||$now['starttime']!==$i['starttime']||$now['boot_id']!==$i['boot_id'])return;
        $group=self::groupIdentity($i['pid']);if(!$group||($i['group']??$i['pid'])!==$group['group']||($i['session']??$i['pid'])!==$group['session'])return;
        $p=@proc_open(['/bin/kill','-KILL','-'.(string)$group['group']],[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes,'/',['PATH'=>'/usr/bin:/bin']);
        if(is_resource($p))proc_close($p);
    }
    public static function kill(?array $i): void
    {
        if($i===null||!is_int($i['pid']??null)||self::identity($i['pid'])!==$i)return;
        $p=@proc_open(['/bin/kill','-KILL',(string)$i['pid']],[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes,'/',['PATH'=>'/usr/bin:/bin']);
        if(is_resource($p))proc_close($p);
    }
}
