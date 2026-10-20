<?php
require_once __DIR__.'/support-report-platform.php';

/** Local authenticated UI facts. Never included in the exported diagnostic report. */
final class AsusRouterWan
{
    public function __construct(private AsusReportIO $io) {}
    public function collect(): array
    {
        $empty=['schema_version'=>1,'state'=>'unavailable','addresses'=>[]];
        $nv=(new AsusReportPlatform($this->io,new AsusReportValues()))->readNvram();
        $links=[];$rows=[];
        $linkResult=$this->io->streamCommand('links',function($line)use(&$links){
            if(count($links)>=64)return;
            if(preg_match('/^\d+: ([^:]+): <([^>]*)>/',$line,$m)) {
                $name=explode('@',$m[1])[0];
                if(preg_match('/^[a-zA-Z0-9_.-]{1,32}$/D',$name))$links[$name]=in_array('UP',explode(',',$m[2]),true);
            }
        });
        $addrResult=$this->io->streamCommand('addr4',function($line)use(&$rows){
            if(count($rows)>=128)return;
            if(preg_match('/^\d+: (\S+)\s+inet (\d+\.\d+\.\d+\.\d+)(?:\/\d+)?(?:\s|$)/',$line,$m)) {
                $ip=$m[2];$network=AsusReportValues::network($ip);
                if($network!==null && $network['family']===4 && in_array($network['address_class'],['global','private'],true))
                    $rows[]=['interface'=>explode('@',$m[1])[0],'address'=>$ip];
            }
        });
        // A failed command may have emitted partial data; do not call that a current WAN.
        if($nv['state']!=='available'||$linkResult['state']!=='available'||$addrResult['state']!=='available')return $empty;
        $selected=[];$incomplete=false;$n=$nv['values'];
        foreach([0,1] as $unit)if(($n["wan{$unit}_state_t"]??null)==='2') {
            $protocol=$n["wan{$unit}_proto"]??'';
            $name=$n["wan{$unit}_".(in_array($protocol,['pppoe','pptp','l2tp'],true)?'pppoe_ifname':'ifname')]??'';
            if(($links[$name]??false)!==true)$name=$n["wan{$unit}_gw_ifname"]??'';
            if(($links[$name]??false)===true)$selected[$name]=true;else $incomplete=true;
        }
        $result=[];$seen=[];
        foreach(array_keys($selected) as $name) {
            $found=false;
            foreach($rows as $row)if($row['interface']===$name) {
                $key=$name.'|'.$row['address'];$found=true;
                if(!isset($seen[$key])){$seen[$key]=true;$result[]=$row;}
            }
            if(!$found)$incomplete=true;
        }
        if(!$result)return $empty;
        return ['schema_version'=>1,'state'=>$incomplete?'partial':'available','addresses'=>array_slice($result,0,16)];
    }
}
