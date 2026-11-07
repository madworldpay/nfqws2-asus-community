<?php
require_once __DIR__.'/device-profiles-lab.php';

/** Bounded native plan. Names, addresses and ports are data, never shell/nft code. */
final class NfqwsDeviceProfilesPlan
{
    public static function ports(string $value):string
    {
        if(strlen($value)>2048)throw new RuntimeException('invalid_profile_ports');
        if($value==='')return '';
        $rows=explode(',',$value);if(count($rows)>128)throw new RuntimeException('invalid_profile_ports');$ranges=[];
        foreach($rows as $row){
            if(!preg_match('/^([0-9]{1,5})(?::([0-9]{1,5}))?$/D',$row,$m))throw new RuntimeException('invalid_profile_ports');
            $a=(int)$m[1];$b=(int)($m[2]??$m[1]);
            if($a<1||$b<$a||$b>65535)throw new RuntimeException('invalid_profile_ports');$ranges[]=[$a,$b];
        }
        return self::mergePorts($ranges);
    }
    private static function mergePorts(array $ranges):string
    {
        sort($ranges);$out=[];
        foreach($ranges as [$a,$b]){
            $i=count($out)-1;if($i>=0&&$a<=$out[$i][1]+1)$out[$i][1]=max($b,$out[$i][1]);else $out[]=[$a,$b];
        }
        return implode(',',array_map(fn($r)=>$r[0]=== $r[1]?(string)$r[0]:$r[0].':'.$r[1],$out));
    }
    private static function unionPorts(array $values):string
    {
        $ranges=[];foreach($values as $value)foreach(explode(',',self::ports($value)) as $row)if($row!==''){
            $p=explode(':',$row);$ranges[]=[(int)$p[0],(int)($p[1]??$p[0])];
        }
        return self::mergePorts($ranges);
    }
    public static function compile(array $draft,array $discovery,array $strategies,int $baseQueue):array
    {
        $draft=NfqwsDeviceProfilesLab::normalize($draft);
        if($baseQueue<0||$baseQueue>65535||($baseQueue>=41000&&$baseQueue<=41003))throw new RuntimeException('queue_conflict');
        if(!is_array($strategies['current']??null))throw new RuntimeException('strategy_unavailable');
        $base=$strategies['current'];$tcp=[self::ports($base['TCP_PORTS']??'80,443')];$udp=[self::ports($base['UDP_PORTS']??'443')];
        $out=['mode'=>$draft['mode'],'instances'=>[],'selectors'=>[],'warnings'=>[],
              'flow_tcp'=>$tcp[0],'flow_udp'=>$udp[0]];
        if($draft['mode']==='common')return $out;
        $observed=[];
        foreach(array_slice((array)($discovery['devices']??[]),0,128) as $row){
            if(!is_array($row)||!is_string($row['mac']??null)||!is_array($row['addresses']??null))continue;
            foreach(array_slice($row['addresses'],0,16)as $address){
                try{$ip=NfqwsDeviceProfilesLab::address($address);}catch(Throwable $e){continue;}
                $observed[strtolower($row['mac'])][$ip]=true;
            }
        }
        $addresses=[];$owners=[];
        foreach($draft['devices']as $device){
            $ips=$device['mac']===''?$device['addresses']:array_keys($observed[$device['mac']]??[]);
            if($device['mac']!==''&&!$ips)$out['warnings'][]='unresolved_mac';
            $addresses[$device['id']]=$ips;
            foreach($ips as $ip)$owners[$ip][$device['id']]=true;
        }
        $queues=['current'=>$baseQueue];
        foreach($draft['profiles']as $profile){
            if(!$profile['enabled']||!$profile['device_ids'])continue;
            $id=$profile['strategy'];$config=$strategies[$id]??null;
            if(!is_array($config))throw new RuntimeException('strategy_unavailable');
            $pTcp=self::ports($config['TCP_PORTS']??'80,443');$pUdp=self::ports($config['UDP_PORTS']??'443');
            if(!isset($queues[$id])){
                $slot=count($out['instances']);if($slot>=4)throw new RuntimeException('runtime_profile_limit');
                $queues[$id]=41000+$slot;
                $out['instances'][]=['strategy'=>$id,'slot'=>$slot,'queue'=>$queues[$id],'config'=>$config];
            }
            $a4=[];$a6=[];
            foreach($profile['device_ids']as $deviceId)foreach($addresses[$deviceId]as $ip){
                if(count($owners[$ip])!==1){$out['warnings'][]='ambiguous_address';continue;}
                if(str_contains($ip,':'))$a6[$ip]=true;else $a4[$ip]=true;
            }
            $out['selectors'][]=['profile_id'=>$profile['id'],'queue'=>$queues[$id],
                'addresses4'=>array_keys($a4),'addresses6'=>array_keys($a6),'tcp'=>$pTcp,'udp'=>$pUdp];
            $tcp[]=$pTcp;$udp[]=$pUdp;
        }
        $out['flow_tcp']=self::unionPorts($tcp);$out['flow_udp']=self::unionPorts($udp);
        $out['warnings']=array_values(array_unique($out['warnings']));
        if(strlen(json_encode($out,JSON_THROW_ON_ERROR))>262144)throw new RuntimeException('runtime_limit');
        return $out;
    }
    public static function arguments(array $config,int $queue):array
    {
        // Same token ordering as the pinned core _startup_args, with user/queue
        // selected by the native supervisor rather than the imported profile.
        $args=['--user=nobody','--qnum='.$queue];$base=$config['NFQWS_BASE_ARGS']??'';
        if(!str_contains($base,'--fastpath-workaround='))$args[]='--fastpath-workaround=auto';
        $append=static function(string $value)use(&$args):void{
            $value=implode("\n",array_filter(explode("\n",$value),fn($line)=>!str_starts_with(ltrim($line),'#')));
            foreach(preg_split('/\s+/',trim($value),-1,PREG_SPLIT_NO_EMPTY)as $word)$args[]=$word;
        };
        $append($base);
        if(count(preg_split('/\s+/',trim($config['ISP_INTERFACE']??''),-1,PREG_SPLIT_NO_EMPTY))>1){
            $args[]='--bind-fix4';if(($config['IPV6_ENABLED']??'0')!=='0')$args[]='--bind-fix6';
        }
        $ipset=$config['NFQWS_ARGS_IPSET']??'';$extra=$config['NFQWS_EXTRA_ARGS']??'';
        foreach(['NFQWS_ARGS_CUSTOM','NFQWS_ARGS_UDP']as $key)if(trim($config[$key]??'')!==''){$append($config[$key]);$args[]='--new';}
        foreach(['NFQWS_ARGS_QUIC','NFQWS_ARGS']as $key){
            $text=$config[$key]??'';if($key==='NFQWS_ARGS_QUIC'&&trim($text)==='')continue;
            if(trim($ipset)!==''){$append($text.' '.$ipset.' --ipset-ip=0.0.0.0');$args[]='--new';}
            $append($text.' '.$extra);if($key==='NFQWS_ARGS_QUIC')$args[]='--new';
        }
        if(count($args)>8192||strlen(implode(' ',$args))>131072)throw new RuntimeException('runtime_limit');
        return $args;
    }
    public static function rules(array $plan):array
    {
        $out=['definitions'=>'','original'=>'','reply'=>''];
        foreach($plan['selectors']as $i=>$p){
            foreach([4,6]as $family){
                $name='dp_'.$i.'_'.$family;$ips=$p['addresses'.$family];
                $out['definitions'].=' set '.$name.' { type ipv'.$family.'_addr;'.($ips?' elements = { '.implode(', ',$ips).' };':'')." }\n";
                if($ips)foreach(['original','reply']as $direction)$out[$direction].='  ct original '.($family===4?'ip':'ip6').' saddr @'.$name.' goto dp_'.$i.'_'.$direction."\n";
            }
            foreach(['original','reply']as $direction){
                $port=$direction==='original'?'dport':'sport';$out['definitions'].=' chain dp_'.$i.'_'.$direction." {\n";
                foreach(['tcp','udp']as $protocol)if($p[$protocol]!==''){
                    $ports=str_replace(':','-',$p[$protocol]);$queue=$p['queue'];
                    $out['definitions'].='  '.$protocol.' '.$port.' { '.$ports.' } ct '.$direction.' packets 1-15 counter queue num '.$queue." bypass\n";
                    if($protocol==='tcp'){
                        $out['definitions'].='  tcp '.$port.' { '.$ports.' } tcp flags & (fin | rst) != 0 counter queue num '.$queue." bypass\n";
                        if($direction==='reply')$out['definitions'].='  tcp sport { '.$ports.' } tcp flags & (syn | ack) == (syn | ack) counter queue num '.$queue." bypass\n";
                    }
                }
                $out['definitions'].="  return\n }\n";
            }
        }
        return $out;
    }
}
