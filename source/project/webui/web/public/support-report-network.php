<?php
require_once __DIR__.'/support-report-platform.php';

final class AsusReportNetwork
{
    private array $wanNames=[];
    private bool $partial=false;
    public function __construct(private AsusReportIO $io,private AsusReportValues $values) {}
    private function iface(string $raw): string { return $this->values->alias(in_array($raw,$this->wanNames,true)?'WAN':'IF',$raw); }
    private function names(?string $raw): array
    {
        if($raw===null) return [];
        $names=preg_split('/\s+/',trim($raw),-1,PREG_SPLIT_NO_EMPTY);$out=[];
        foreach(array_slice($names,0,64) as $name) if(strlen($name)<=64 && !preg_match('/[\x00-\x20]/',$name)) $out[]=$name;
        if(count($names)>64) $this->partial=true;
        return array_values(array_unique($out));
    }
    private function settings(array $s): array
    {
        $queue=is_string($s['NFQUEUE_NUM']??null)?AsusReportValues::decimal($s['NFQUEUE_NUM'],'65535'):null;
        $out=['queue_number'=>$queue!==null?(int)$queue:null,'ipv6_enabled'=>in_array($s['IPV6_ENABLED']??null,['0','1'],true)?$s['IPV6_ENABLED']==='1':null,
            'client_mode'=>in_array($s['ASUS_CLIENT_MODE']??null,['all','include','exclude'],true)?$s['ASUS_CLIENT_MODE']:null,
            'wan_auto'=>array_key_exists('ISP_INTERFACE',$s)&&$s['ISP_INTERFACE']==='',
            'wan'=>array_map(fn($n)=>$this->iface($n),$this->names($s['ISP_INTERFACE']??null))];
        foreach(['TCP_PORTS'=>'tcp_ports','UDP_PORTS'=>'udp_ports'] as $key=>$field) {
            $p=$s[$key]??null;$out[$field]=is_string($p)&&strlen($p)<=512&&preg_match('/^(?:[0-9]+(?::[0-9]+)?(?:,[0-9]+(?::[0-9]+)?)*)?$/D',$p)?$p:null;
        }
        foreach([4,6] as $family) {
            $raw=$s['ASUS_CLIENTS'.$family]??null;$ids=[];$invalid=0;
            foreach($this->names($raw) as $client) {
                $n=AsusReportValues::network($client);
                if(!$n||$n['family']!==$family) {++$invalid;continue;}
                $ids[]=$this->values->networkAlias($client);
            }
            $out['clients'.$family]=['state'=>$raw===null?'unknown':'known','ids'=>$ids,'invalid_count'=>$invalid,'processing_selected'=>$out['client_mode']==='all'||($out['client_mode']==='exclude'||count($ids)>0)];
        }
        return $out;
    }
    private function rule(string $line,int $family,string $table,array &$positions,array &$terminals): ?array
    {
        if(!preg_match('/^\[([0-9]+):([0-9]+)\] -A (\S+) (.*)$/D',$line,$m)) return null;
        $chain=$m[3];$body=$m[4];$position=($positions[$chain]??0)+1;$positions[$chain]=$position;
        preg_match('/(?:^| )-j ([^ ]+)/',$body,$jump);$target=$jump[1]??'';
        $own=['nfqa_pre','nfqa_post','nfqa_in','nfqa_out','nfqa_nat'];
        $isOwn=in_array($chain,$own,true);$parent=in_array($chain,['PREROUTING','POSTROUTING','FORWARD','INPUT','OUTPUT'],true)&&in_array($target,$own,true);
        if(!$isOwn&&!$parent) { if(in_array($target,['DROP','REJECT','ACCEPT','RETURN'],true)) $terminals[$chain]=($terminals[$chain]??0)+1;return null; }
        $rule=['family'=>$family,'table'=>$table,'chain'=>$chain,'position'=>$position,
            'packets'=>AsusReportValues::decimal($m[1],'18446744073709551615'), 'bytes'=>AsusReportValues::decimal($m[2],'18446744073709551615'),
            'target'=>in_array($target,array_merge($own,['NFQUEUE','RETURN','ACCEPT','MARK','CONNMARK','MASQUERADE']),true)?$target:null,'selectors'=>[],'incomplete'=>false];
        if($rule['target']===null) $rule['incomplete']=true;
        if($parent) $rule['preceding_terminal_count']=$terminals[$chain]??0;
        $tokens=preg_split('/\s+/',trim($body));
        $negate=false;
        for($i=0;$i<count($tokens);$i++) {
            $option=$tokens[$i];if($option==='!') {$negate=true;continue;}
            if(in_array($option,['--queue-bypass'],true)) { $rule['selectors']['queue_bypass']=true;continue; }
            if($option==='-j') {++$i;continue;}
            if($option==='--tcp-flags') {
                $mask=$tokens[++$i]??'';$flags=$tokens[++$i]??'';
                if(preg_match('/^(?:(?:SYN|ACK|FIN|RST|PSH|URG|ALL|NONE),?)+$/D',$mask)&&preg_match('/^(?:(?:SYN|ACK|FIN|RST|PSH|URG|ALL|NONE),?)+$/D',$flags)) $rule['selectors']['tcp_flags']=[$mask,$flags];else $rule['incomplete']=true;
                continue;
            }
            $value=$tokens[++$i]??'';
            if(in_array($option,['-i','-o'],true)) $rule['selectors'][$option==='-i'?'input':'output']=['id'=>$this->iface($value),'negated'=>$negate];
            elseif(in_array($option,['-s','-d','--ctorigsrc','--ctorigdst'],true)) {
                $n=AsusReportValues::network($value);
                $field=['-s'=>'source','-d'=>'destination','--ctorigsrc'=>'original_source','--ctorigdst'=>'original_destination'][$option];
                if($n) $rule['selectors'][$field]=AsusReportValues::networkView($n)+['id'=>$this->values->networkAlias($value),'negated'=>$negate];else $rule['incomplete']=true;
            } elseif($option==='-p'&&in_array($value,['tcp','udp','icmp','ipv6-icmp','all','6','17'],true)) $rule['selectors']['protocol']=$value;
            elseif($option==='--ctdir'&&in_array($value,['ORIGINAL','REPLY'],true)) $rule['selectors']['ctdir']=$value;
            elseif($option==='--queue-num'&&AsusReportValues::decimal($value,'65535')!==null) $rule['selectors']['queue_number']=(int)$value;
            elseif(in_array($option,['--dport','--sport','--dports','--sports','--connbytes'],true)&&strlen($value)<=512&&preg_match('/^[0-9,:]+$/D',$value)) $rule['selectors'][ltrim($option,'-')]=$value;
            elseif($option==='-m'&&in_array($value,['multiport','connbytes','conntrack','mark','tcp','udp'],true)) $rule['selectors']['matches'][]=$value;
            elseif(in_array($option,['--connbytes-dir','--connbytes-mode','--ctstate'],true)&&in_array($value,['original','reply','both','packets','bytes','avgpkt','NEW','ESTABLISHED','RELATED','ESTABLISHED,RELATED','RELATED,ESTABLISHED'],true)) $rule['selectors'][substr($option,2)]=$value;
            elseif(in_array($option,['--mark','--set-mark'],true)&&preg_match('/^(?:0x[0-9a-f]{1,8}|[0-9]{1,10})(?:\/(?:0x[0-9a-f]{1,8}|[0-9]{1,10}))?$/Di',$value)) $rule['selectors'][substr($option,2)]=$value;
            else $rule['incomplete']=true;
            $negate=false;
        }
        return $rule;
    }
    public function collect(array $savedSettings,array $runtimeSettings): array
    {
        $links=[];$networks=[];$routes=[];$sources=[];$clients=[];$failures=[];
        $sources['links']=$this->io->streamCommand('links',function($line)use(&$links){
            if(count($links)>=64) {$this->partial=true;return;}
            if(preg_match('/^\d+: ([^:]+): <([^>]*)>.*?mtu ([0-9]+)/',$line,$m)) {
                $name=explode('@',$m[1])[0];$links[$name]=['up'=>in_array('UP',explode(',',$m[2]),true),'mtu'=>(int)$m[3]];
            }
        });
        $platform=new AsusReportPlatform($this->io,$this->values);$nv=$platform->readNvram();$discovered=[];
        foreach([0,1] as $unit) if(($nv['values']["wan{$unit}_state_t"]??null)==='2') {
            $proto=$nv['values']["wan{$unit}_proto"]??'';
            $name=$nv['values']["wan{$unit}_".(in_array($proto,['pppoe','pptp','l2tp'],true)?'pppoe_ifname':'ifname')]??'';
            if(!isset($links[$name])) $name=$nv['values']["wan{$unit}_gw_ifname"]??'';
            if(isset($links[$name])) $discovered[]=$name;
        }
        $wanRead=$this->io->read('wan',2048);$runtimeWan=$wanRead['state']==='available'?$this->names($wanRead['value']):[];
        $requested=$this->names($savedSettings['ISP_INTERFACE']??null);
        $this->wanNames=array_values(array_unique(array_merge($discovered,$requested,$runtimeWan,$this->names($runtimeSettings['ISP_INTERFACE']??null))));
        foreach([4,6] as $family) {
            $sources['addr'.$family]=$this->io->streamCommand('addr'.$family,function($line)use(&$networks,$family){
                if(count($networks)>=128) {$this->partial=true;return;}
                if(preg_match('/^\d+: (\S+)\s+inet6? (\S+)/',$line,$m) && ($n=AsusReportValues::network($m[2]))) $networks[]=['iface'=>explode('@',$m[1])[0],'network'=>$n];
            });
            $sources['route'.$family]=$this->io->streamCommand('route'.$family,function($line)use(&$routes,$family){
                if(count($routes)>=128) {$this->partial=true;return;}
                if(!preg_match('/^(\S+).*?\bdev (\S+)/',$line,$m)) return;
                $dest=$m[1]==='default'?($family===4?'0.0.0.0/0':'::/0'):$m[1];$n=AsusReportValues::network($dest);
                if($n) $routes[]=['iface'=>$m[2],'network'=>$n,'default'=>$m[1]==='default'];
            });
        }
        foreach([4,6] as $family) foreach($this->names($savedSettings['ASUS_CLIENTS'.$family]??null) as $client) {
            $n=AsusReportValues::network($client);if(!$n||$n['family']!==$family)continue;
            $match=false;foreach($networks as $link) if(AsusReportValues::overlaps($n,$link['network']))$match=true;
            $routeMatch=[];foreach($routes as $index=>$route)if(AsusReportValues::overlaps($n,$route['network']))$routeMatch[]=$index;
            $clients[]=AsusReportValues::networkView($n)+['id'=>$this->values->networkAlias($client),'interface_overlap'=>$match,'route_overlap_indices'=>$routeMatch];
        }
        $linkView=[];foreach($links as $name=>$info) $linkView[]=['id'=>$this->iface($name)]+$info;
        $addressView=[];foreach($networks as $link) $addressView[]=AsusReportValues::networkView($link['network'])+['interface'=>$this->iface($link['iface'])];
        $routeView=[];foreach($routes as $route) $routeView[]=AsusReportValues::networkView($route['network'])+['interface'=>$this->iface($route['iface']),'default'=>$route['default']];
        $saved=$this->settings($savedSettings);$runtime=$this->settings($runtimeSettings);
        $rules=[];$tableResults=[];
        foreach([4,6] as $family) {
            $available=$this->io->read('tables'.$family,4096);
            foreach(['mangle','nat'] as $table) {
                if($available['state']!=='available') { $tableResults[]=['family'=>$family,'table'=>$table,'state'=>$available['state']];continue; }
                if(!in_array($table,preg_split('/\s+/',trim($available['value'])),true)) { $tableResults[]=['family'=>$family,'table'=>$table,'state'=>'not_loaded'];continue; }
                $positions=[];$terminals=[];
                $result=$this->io->streamCommand("rules$family-$table",function($line)use($family,$table,&$positions,&$terminals,&$rules){
                    if(count($rules)>=256) {$this->partial=true;return;}
                    $rule=$this->rule($line,$family,$table,$positions,$terminals);if($rule) $rules[]=$rule;
                });
                $tableResults[]=['family'=>$family,'table'=>$table,'state'=>$result['state']];
            }
        }
        $networkPartial=$this->partial||$nv['state']!=='available';foreach($sources as $source) if($source['state']!=='available')$networkPartial=true;
        $rulesPartial=$this->partial;foreach($tableResults as $result)if(!in_array($result['state'],['available','not_loaded'],true))$rulesPartial=true;
        foreach($rules as $rule)if($rule['incomplete'])$rulesPartial=true;
        return [
            'settings'=>AsusReportPlatform::section(['saved'=>$saved,'runtime'=>$runtime,'same'=>$savedSettings&&$runtimeSettings?$saved===$runtime:null],$savedSettings&&$runtimeSettings?'available':'partial','missing'),
            'network'=>AsusReportPlatform::section(['wan'=>['auto'=>$saved['wan_auto'],'requested'=>array_map(fn($n)=>$this->iface($n),$requested),'discovered'=>array_map(fn($n)=>$this->iface($n),$discovered),'runtime'=>array_map(fn($n)=>$this->iface($n),$runtimeWan),'runtime_recorded'=>$wanRead['state']==='available','requested_missing_count'=>count(array_diff($requested,array_keys($links))),'runtime_matches_discovered'=>$wanRead['state']==='available'?array_values($runtimeWan)===array_values($discovered):null],
                'interfaces'=>$linkView,'addresses'=>$addressView,'routes'=>$routeView,'clients'=>$clients,'sources'=>array_map(fn($r)=>$r['state'],$sources),'nvram_state'=>$nv['state']],$networkPartial?'partial':'available',$networkPartial?'unsupported':null),
            'rules'=>AsusReportPlatform::section(['tables'=>$tableResults,'items'=>$rules],$rulesPartial?'partial':'available',$rulesPartial?'unsupported':null),
        ];
    }
}
