<?php
require_once __DIR__.'/support-report-io.php';
require_once __DIR__.'/smartdns-install.php';
require_once __DIR__.'/smartdns-connect.php';

/** Private, read-only CAS inputs. Never put this snapshot in a support report. */
final class AsusSmartDnsBaseline
{
    public function __construct(private AsusReportIO $io,private AsusSmartDnsInstaller $installer,private array $deps=[]) {}
    private function file(string $source): array
    {
        $read=$this->io->read($source);$stat=@lstat($this->io->path($source));$meta=null;
        if ($stat) $meta=['mode'=>$stat['mode']&07777,'uid'=>$stat['uid'],'links'=>$stat['nlink'],'device'=>$stat['dev'],'inode'=>$stat['ino']];
        return ['read'=>$read,'meta'=>['state'=>$read['state'],'sha256'=>$read['state']==='available'?hash('sha256',$read['value']):null,'file'=>$meta]];
    }
    private static function nativeFallback(string $config,array $serverFiles): bool
    {
        $explicit=[];$resolver=[];$noResolve=false;
        foreach (explode("\n",$config) as $line) {
            $line=trim($line);if ($line==='' || str_starts_with($line,'#')) continue;
            if ($line==='no-resolv') {$noResolve=true;continue;}
            if (preg_match('/^server\s*=\s*(.+)$/D',$line,$m)) {$explicit[]=trim($m[1]);continue;}
            if (preg_match('/^(resolv-file|servers-file)\s*=\s*(.+)$/D',$line,$m)) {
                $path=trim($m[2]);
                // Only sources already read from native /tmp by the collector.
                // A file under /opt (or any unknown include) cannot survive USB loss.
                if (!isset($serverFiles[$path]) || !is_string($serverFiles[$path])) return false;
                foreach (explode("\n",$serverFiles[$path]) as $entry) {
                    $entry=trim($entry);if ($entry==='' || str_starts_with($entry,'#')) continue;
                    $pattern=$m[1]==='resolv-file'?'/^nameserver\s+([^\s#]+)(?:\s*(?:#.*)?)$/D':'/^server\s*=\s*([^\s]+)$/D';
                    if (preg_match($pattern,$entry,$part)) {
                        if ($m[1]==='resolv-file') $resolver[]=$part[1];else $explicit[]=$part[1];
                    } elseif (!preg_match('/^(?:search|domain|options)\s+/',$entry)) return false;
                }
            }
        }
        $addresses=$noResolve?$explicit:array_merge($explicit,$resolver);
        if (!$addresses) return false;
        foreach ($addresses as $address) {
            // Loopback may be another USB resolver or a native resolver with
            // an unverified dependency chain. Never guess a replacement DNS.
            $ip=explode('#',$address,2)[0];$packed=@inet_pton($ip);
            if ($packed===false || $ip==='::1' || $ip==='::' || str_starts_with($ip,'127.') || $ip==='0.0.0.0') return false;
        }
        return true;
    }
    public function collect(): array
    {
        $facts=[];$files=[];$conflicts=[];$owner=$this->deps['owner']??0;
        foreach (['dnsmasq_config','dns_forwarders','dns_resolv','dns_stubby','dns_ca','hook_dnsmasq','hook_mount','hook_init','hook_firewall','dns_external_config','dns_external_init'] as $source) {
            $f=$this->file($source);$files[$source]=$f;$facts[$source]=$f['meta'];
            if (!in_array($f['read']['state'],['available','missing'],true)) $conflicts[]='dns_sources_unavailable';
        }
        if ($files['dnsmasq_config']['read']['state']!=='available') throw new RuntimeException('baseline_unavailable');
        $hook=$files['hook_dnsmasq'];
        if ($hook['read']['state']==='available' && ($hook['meta']['file']['uid']!==$owner || $hook['meta']['file']['links']!==1 || ($hook['meta']['file']['mode']&0022)!==0 || ($hook['meta']['file']['mode']&0100)===0)) $conflicts[]='hook_permissions';
        if ($files['dns_external_config']['read']['state']!=='missing' || $files['dns_external_init']['read']['state']!=='missing') $conflicts[]='external_smartdns';
        $serverFiles=[];
        foreach (['dns_forwarders'=>'/tmp/resolv.dnsmasq','dns_resolv'=>'/tmp/resolv.conf'] as $source=>$path) {
            if ($files[$source]['read']['state']==='available') {
                $serverFiles[$path]=$files[$source]['read']['value'];
                $serverFiles[$this->io->path($source)]=$files[$source]['read']['value'];
            }
        }
        try {AsusSmartDnsHook::install($hook['read']['value']);}
        catch (Throwable $e) {$conflicts[]='hook_conflict';}
        try {AsusSmartDnsHook::forwarding($files['dnsmasq_config']['read']['value'],$serverFiles);}
        catch (Throwable $e) {$conflicts[]='existing_dns_rules';}
        if (!self::nativeFallback($files['dnsmasq_config']['read']['value'],$serverFiles)) $conflicts[]='native_fallback_unavailable';
        $keys=['jffs2_scripts','dns_local_cache','dnspriv_enable','dnspriv_profile','dnspriv_rulelist','dhcp_dns1_x','dhcp_dns2_x','dhcp_dns_router','dnsfilter_enable_x','dnsfilter_mode','dnssec_enable'];
        foreach ([0,1] as $unit) foreach (['dnsenable_x','dns1_x','dns2_x','dns'] as $key) $keys[]='wan'.$unit.'_'.$key;
        $nv=[];$nvr=$this->io->streamCommand('nvram',function($line)use(&$nv,$keys) {
            $v=explode('=',$line,2);
            if (count($v)===2 && in_array($v[0],$keys,true)) $nv[$v[0]]=array_key_exists($v[0],$nv)?null:$v[1];
        },1.5);
        if ($nvr['state']!=='available' || in_array(null,$nv,true)) $conflicts[]='dns_settings_unavailable';
        if (($nv['jffs2_scripts']??null)!=='1') $conflicts[]='enable_jffs_scripts';
        ksort($nv);$facts['nvram']=['state'=>$nvr['state'],'values'=>$nv];
        $boot=$this->io->read('boot',128);
        if ($boot['state']!=='available' || !preg_match('/^[a-f0-9-]{36}\n?$/D',$boot['value'])) throw new RuntimeException('baseline_unavailable');
        $facts['boot']=trim($boot['value']);$processes=[];$proc=dirname($this->io->path('boot'),4);
        $managed=isset($this->deps['managed_identity'])?($this->deps['managed_identity'])():null;
        $entries=@scandir($proc);$count=0;$end=$this->io->now()+1;
        if (!is_array($entries)) {$entries=[];$conflicts[]='dns_processes_unavailable';}
        foreach ($entries as $pid) if (preg_match('/^[1-9][0-9]{0,8}$/D',$pid) && (int)$pid>1) {
            if (++$count>1024 || $this->io->now()>=$end) {$conflicts[]='dns_processes_unavailable';break;}
            $name=$this->io->readProcess((int)$pid,'comm',64);
            if ($name['state']!=='available') {if (is_dir($proc.'/'.$pid)) $conflicts[]='dns_processes_unavailable';continue;}
            $name=trim($name['value']);
            if (!in_array($name,['dnsmasq','smartdns','stubby','dnscrypt-proxy','dnscrypt-proxy2','AdGuardHome','https-dns-proxy','nextdns','cloudflared'],true)) continue;
            $stat=$this->io->readProcess((int)$pid,'stat');$exe=$this->io->readProcess((int)$pid,'exe');$ticks=null;
            if ($stat['state']==='available' && preg_match('/\) (.*)$/s',$stat['value'],$m)) {
                $v=explode(' ',trim($m[1]));if (preg_match('/^[0-9]+$/D',$v[19]??'')) $ticks=$v[19];
            }
            if ($ticks===null || $exe['state']!=='available') $conflicts[]='dns_processes_unavailable';
            if ($name==='smartdns' && is_array($managed) && ($managed['pid']??null)===(int)$pid && ($managed['starttime']??null)===$ticks && ($managed['exe']??null)===($exe['value']??null) && ($managed['boot_id']??null)===$facts['boot']) continue;
            if ($name==='smartdns') $conflicts[]='external_smartdns';
            if ($name!=='dnsmasq' && $exe['state']==='available' && preg_match('~^/(?:opt|jffs|tmp/mnt)(?:/|$)~',$exe['value'])) $conflicts[]='native_fallback_unavailable';
            $processes[]=['name'=>$name,'pid'=>(int)$pid,'ticks'=>$ticks,'exe_hash'=>$exe['state']==='available'?hash('sha256',$exe['value']):null];
        }
        usort($processes,fn($a,$b)=>$a['pid']<=>$b['pid']);$facts['processes']=$processes;
        $engine=isset($this->deps['engine'])?($this->deps['engine'])():['sha256'=>hash_file('sha256',$this->installer->binaryDirectory().'/smartdns'),'version'=>$this->installer->installed()['version']];
        if (!is_array($engine) || !is_string($engine['sha256']??null) || !preg_match('/^[a-f0-9]{64}$/D',$engine['sha256']) || !is_string($engine['version']??null)) throw new RuntimeException('baseline_unavailable');
        $facts['engine']=$engine;$conflicts=array_values(array_unique($conflicts));sort($conflicts);
        $snapshot=['hook'=>['state'=>$hook['read']['state'],'value'=>$hook['read']['value'],'mode'=>$hook['meta']['file']['mode']??null],
            'config'=>$files['dnsmasq_config']['read'],'server_files'=>$serverFiles,'fingerprints'=>$facts];
        if (strlen(json_encode($snapshot,JSON_THROW_ON_ERROR))>500000) throw new RuntimeException('output_limit');
        return ['hash'=>hash('sha256',json_encode($facts,JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES)), 'snapshot'=>$snapshot,'conflicts'=>$conflicts];
    }
}
