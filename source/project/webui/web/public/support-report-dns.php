<?php
require_once __DIR__.'/support-report-platform.php';
require_once __DIR__.'/smartdns-report.php';
/** Passive, fixed-source DNS context. No queries, URLs, account IDs or argv. */
final class AsusReportDns
{
    public function __construct(private AsusReportIO $io,private AsusReportValues $values){}
    private static function flag(?string $value): ?bool{return in_array($value,['0','1'],true)?$value==='1':null;}
    private function resolver(string $ip,string $transport='plain',?int $port=53,string $authentication='none'): ?array
    {
        $n=AsusReportValues::network($ip);if(!$n||str_contains($ip,'/'))return null;
        $canonical=inet_ntop($n['_packed']);$provider='custom';
        foreach(['google'=>['8.8.8.8','8.8.4.4','2001:4860:4860::8888','2001:4860:4860::8844'],
            'cloudflare'=>['1.1.1.1','1.0.0.1','2606:4700:4700::1111','2606:4700:4700::1001'],
            'quad9'=>['9.9.9.9','149.112.112.112','2620:fe::fe','2620:fe::9']] as $name=>$addresses)if(in_array($canonical,$addresses,true))$provider=$name;
        return ['id'=>$this->values->alias('DNS',bin2hex($n['_packed'])),'provider'=>$provider,'family'=>$n['family'],
            'address_class'=>$n['address_class'],'transport'=>$transport,'port'=>$port,'authentication'=>$authentication];
    }
    private function servers(string $raw): array
    {
        $out=[];foreach(array_slice(preg_split('/\s+/',trim($raw),-1,PREG_SPLIT_NO_EMPTY),0,16) as $ip){$r=$this->resolver($ip);if($r!==null)$out[]=$r;}return $out;
    }
    public function collect(): array
    {
        $keys=['dnspriv_enable','dnspriv_profile','dnspriv_rulelist','dhcp_dns1_x','dhcp_dns2_x','dhcp_dns_router','dnsfilter_enable_x','dnsfilter_mode'];
        foreach([0,1] as $unit)foreach(['dnsenable_x','dns1_x','dns2_x','dns'] as $key)$keys[]='wan'.$unit.'_'.$key;
        $nv=[];$nvr=$this->io->streamCommand('nvram',function($line)use(&$nv,$keys){$pair=explode('=',$line,2);if(count($pair)===2&&in_array($pair[0],$keys,true))$nv[$pair[0]]=array_key_exists($pair[0],$nv)?null:$pair[1];},1.5);
        $wan=[];foreach([0,1] as $unit)$wan[]=['unit'=>$unit,'automatic'=>self::flag($nv['wan'.$unit.'_dnsenable_x']??null),
            'configured'=>$this->servers(($nv['wan'.$unit.'_dns1_x']??'').' '.($nv['wan'.$unit.'_dns2_x']??'')),'learned'=>$this->servers($nv['wan'.$unit.'_dns']??'')];
        $configured=[];$invalid=0;$rules=$nv['dnspriv_rulelist']??'';
        if(strlen($rules)>65536){$invalid=1;$rules='';}
        $rows=array_filter(explode('<',$rules),static fn($v)=>$v!=='');if(count($rows)>32)$invalid+=count($rows)-32;
        foreach(array_slice($rows,0,32) as $row) {
            $fields=explode('>',$row);if(count($fields)!==4){$invalid++;continue;}
            [$ip,$port,$host,$pin]=$fields;$p=$port===''?853:(preg_match('/^[0-9]{1,5}$/D',$port)&&(int)$port>0&&(int)$port<=65535?(int)$port:null);
            $r=$this->resolver($ip,'dot',$p,$host!==''?($pin!==''?'name_and_pin':'name'):($pin!==''?'pin':'none'));
            if($r===null||$p===null){$invalid++;continue;}$configured[]=$r;
        }
        $stubby=$this->io->read('dns_stubby',65536);$transports=[];$upstreams=[];$inside=false;
        if($stubby['state']==='available')foreach(explode("\n",$stubby['value']) as $line) {
            if(preg_match('/^\s*-\s*GETDNS_TRANSPORT_(TLS|UDP|TCP)\s*(?:#.*)?$/D',$line,$m))$transports[]=strtolower($m[1]);
            if(preg_match('/^upstream_recursive_servers:\s*(?:#.*)?$/D',$line)){$inside=true;continue;}
            if($inside&&preg_match('/^\S/',$line))$inside=false;
            if($inside&&count($upstreams)<32&&preg_match('/^\s*-\s*address_data:\s*["\']?([0-9a-fA-F:.]+)["\']?\s*(?:#.*)?$/D',$line,$m)){$r=$this->resolver($m[1],'dot',null,'unknown');if($r!==null)$upstreams[]=$r;}
        }
        $forward=$this->io->read('dns_forwarders',16384);if($forward['state']==='missing')$forward=$this->io->read('dns_resolv',16384);$forwarders=[];
        if($forward['state']==='available')foreach(explode("\n",$forward['value']) as $line)if(count($forwarders)<16&&preg_match('/^\s*nameserver\s+([0-9a-fA-F:.]+)\s*(?:#.*)?$/D',$line,$m)){$r=$this->resolver($m[1],'unknown',53);if($r!==null)$forwarders[]=$r;}
        $processes=$this->io->dnsProcesses();$observed=$processes['names'];$configs=[];$configStates=[];
        foreach(['dnscrypt_a','dnscrypt_b','dnscrypt_c'] as $id) {
            $r=$this->io->read($id,65536);$configStates[]=$r['state'];if($r['state']!=='available')continue;$flags=[];
            foreach(explode("\n",$r['value']) as $line)if(preg_match('/^\s*(doh_servers|dnscrypt_servers)\s*=\s*(true|false)\s*(?:#.*)?$/D',$line,$m))$flags[$m[1]]=array_key_exists($m[1],$flags)?null:$m[2]==='true';
            $configs[]=['source'=>$id,'doh_allowed'=>$flags['doh_servers']??null,'dnscrypt_allowed'=>$flags['dnscrypt_servers']??null];
        }
        $dohNames=array_values(array_filter($observed,static fn($name)=>$name!=='stubby'));
        $dotEnabled=self::flag($nv['dnspriv_enable']??null);$profile=($nv['dnspriv_profile']??null)==='1'?'strict':(($nv['dnspriv_profile']??null)==='0'?'opportunistic':'unknown');
        $data=['wan'=>$wan,'lan'=>['advertise_router'=>self::flag($nv['dhcp_dns_router']??null),'configured'=>$this->servers(($nv['dhcp_dns1_x']??'').' '.($nv['dhcp_dns2_x']??''))],
            'system_forwarders'=>$forwarders,'dot'=>['enabled'=>$dotEnabled,'profile'=>$profile,'configured'=>$configured,'invalid_entries'=>$invalid,'generated_transports'=>array_values(array_unique($transports)),
                'generated_upstreams'=>$upstreams,'process_observed'=>in_array('stubby',$observed,true)?true:($processes['state']==='available'?false:null)],
            'doh'=>['observed_components'=>$dohNames,'configs'=>$configs,'state'=>$configs?'configuration_observed':($dohNames?'component_observed':($processes['state']==='available'?'not_observed':'unknown'))],
            'director'=>['enabled'=>self::flag($nv['dnsfilter_enable_x']??null),'global_mode'=>isset($nv['dnsfilter_mode'])&&preg_match('/^[0-9]{1,2}$/D',$nv['dnsfilter_mode'])?(int)$nv['dnsfilter_mode']:null],
            'connectivity_tested'=>false,'client_overrides_observed'=>false,'sources'=>['nvram'=>$nvr['state'],'forwarders'=>$forward['state'],'stubby'=>$stubby['state'],'processes'=>$processes['state'],'dnscrypt'=>$configStates]];
        $opt=dirname($this->io->path('config'),3);$opt=realpath($opt)?:$opt;
        $data['managed_smartdns']=(new AsusSmartDnsReport(new AsusSmartDnsStore($opt.'/etc/nfqws-asus-web/smartdns'),fn()=>(new AsusSmartDnsInstaller($opt.'/lib/nfqws2-asus/smartdns-engine'))->installed()))->collect();
        $known=$nvr['state']==='available'&&($dotEnabled!==null||$wan[0]['automatic']!==null||$wan[1]['automatic']!==null)&&$invalid===0;
        return AsusReportPlatform::section($data,$known?'available':'partial',$known?null:($nvr['state']==='available'?'unsupported':$nvr['state']));
    }
}
