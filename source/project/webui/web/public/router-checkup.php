<?php
require_once __DIR__.'/support-report-dns.php';
require_once __DIR__.'/smartdns-install.php';

/** Passive facts only. Readiness never starts services or probes the network. */
final class AsusRouterCheckup
{
    public function __construct(private AsusReportIO $io, private array $deps=[]) {}
    private static function item(string $id, string $state, array $facts, string $action='none'): array
    { return ['id'=>$id, 'state'=>$state, 'facts'=>$facts, 'action_code'=>$action]; }
    private function storage(string $area, string $path, array $mounts): array
    {
        $real = realpath($path); $mount = null;
        foreach ($mounts as $m) {
            if ($real !== false && ($real === $m['path'] || str_starts_with($real, rtrim($m['path'],'/').'/')) && ($mount === null || strlen($m['path']) > strlen($mount['path']))) $mount = $m;
        }
        $free = $real === false ? false : @disk_free_space($real);
        $ro = $mount !== null && in_array('ro', $mount['options'], true);
        $writable = $real !== false && is_dir($real) && is_writable($real) && !$ro;
        $kind = $mount === null ? 'unknown' : (str_contains($mount['type'],'jffs') ? 'jffs' : (in_array($mount['type'],['tmpfs','ramfs'],true) ? 'memory' : (str_starts_with($mount['device'],'/dev/sd') ? 'usb' : 'other')));
        $facts = ['present'=>$real !== false, 'mount_type'=>$mount['type']??null, 'storage_kind'=>$kind, 'readonly'=>$ro,
            'writable_estimate'=>$writable, 'write_tested'=>false, 'free_bytes'=>$free === false ? null : sprintf('%.0f',$free),
            'installer_reserve_bytes'=>$area === 'opt' ? 50331648 : null];
        return self::item('storage_'.$area, $writable ? 'info' : 'attention', $facts, $writable ? 'write_not_tested' : ($ro ? 'opt_readonly' : 'storage_unavailable'));
    }
    public function collect(): array
    {
        $values = new AsusReportValues(); $platform = new AsusReportPlatform($this->io, $values);
        $nv = $platform->readNvram(); $n = $nv['values']; $items = [];
        $kernel = trim($this->io->read('kernel',128)['value']);
        if (!preg_match('/^[0-9][0-9a-zA-Z._-]{1,95}$/D', $kernel)) $kernel = null;
        $opkg = $this->io->read('opkg'); $abiText = $opkg['value']; $complete = in_array($opkg['state'],['available','missing'],true);
        foreach ($this->io->resources('opkg') as $file) if (str_ends_with($file,'.conf')) {
            $r = $this->io->readResource('opkg',$file);
            if ($r['state'] !== 'available' || strlen($abiText)+strlen($r['value']) > 262144) { $complete = false; break; }
            $abiText .= "\n".$r['value'];
        }
        if (!in_array($this->io->resourcesState('opkg'),['available','missing'],true)) $complete = false;
        $abi = $complete ? AsusReportPlatform::abi($abiText) : null;
        $firmware = [];
        foreach (['firmver','buildno','extendno'] as $key) $firmware[$key] = isset($n[$key]) && preg_match('/^[0-9a-zA-Z._-]{1,64}$/D',$n[$key]) ? $n[$key] : null;
        $package = $this->io->read('package',16384);
        preg_match('/^Version: ([0-9]+\.[0-9]+\.[0-9]+-asus[0-9]+\+b[0-9]+)$/m',$package['value'],$version);
        $items[] = self::item('platform', $abi !== null ? 'ready' : 'info', ['model'=>AsusReportPlatform::model(($n['odmpid']??'') ?: ($n['productid']??'')), 'firmware'=>$firmware, 'kernel'=>$kernel, 'entware_abi'=>$abi, 'package_version'=>$version[1]??null]);
        $mountRead = $this->io->read('mounts'); $mounts = [];
        foreach (explode("\n", $mountRead['value']) as $line) {
            $parts = preg_split('/\s+/',trim($line));
            if (count($parts) < 4) continue;
            $decode = static fn($v) => preg_replace_callback('/\\\\(040|011|012|134)/', static fn($m) => chr(octdec($m[1])), $v);
            $mounts[] = ['device'=>$decode($parts[0]), 'path'=>$decode($parts[1]), 'type'=>$parts[2], 'options'=>explode(',',$parts[3])];
        }
        $opt = dirname($this->io->path('config'),3); $jffs = dirname($this->io->path('hook_dnsmasq'),2);
        $optItem = $this->storage('opt',$opt,$mounts); $jffsItem = $this->storage('jffs',$jffs,$mounts);
        $items[] = $optItem; $items[] = $jffsItem;
        $memRead = $this->io->read('memory',16384); $mem = [];
        foreach (['MemTotal','MemAvailable','MemFree','Buffers','Cached'] as $key) if (preg_match('/^'.$key.':\s+([0-9]{1,12}) kB$/m',$memRead['value'],$m)) $mem[$key] = (float)$m[1];
        $available = isset($mem['MemAvailable']) ? $mem['MemAvailable'] : (isset($mem['MemFree']) ? (float)AsusDpiInstaller::availableMemoryKiB($memRead['value']) : null);
        $identity = $platform->identity(); $rss = null;
        if ($identity['running'] === true && $identity['pid'] !== null) {
            $p = $this->io->readProcess($identity['pid'],'status',16384);
            if (preg_match('/^VmRSS:\s+([0-9]+) kB$/m',$p['value'],$m)) $rss = (float)$m[1];
        }
        $processes = $this->io->dnsProcesses(true);
        $items[] = self::item('memory', $available !== null && $available < 65536 ? 'attention' : 'info', ['total_kib'=>$mem['MemTotal']??null, 'available_kib'=>$available, 'available_estimated'=>!isset($mem['MemAvailable']), 'nfqws2_rss_kib'=>$rss, 'dns_process_rss'=>$processes['rss'], 'dns_process_read_state'=>$processes['state'], 'rss_includes_shared_pages'=>true, 'installer_reserve_kib'=>65536, 'router_minimum_memory_claimed'=>false], 'installer_reserve_not_router_minimum');
        $modules = $this->io->read('modules'); $component = $this->io->arkComponents();
        $loaded = ($component['loaded']??false) || ($modules['state']==='available' && preg_match('/^ark\s/m',$modules['value']));
        $arkKnown = $modules['state']==='available' || ($component['loaded']??false);
        $items[] = self::item('ark', $loaded ? 'attention' : ($arkKnown ? 'ready' : 'info'), ['loaded'=>$arkKnown ? (bool)$loaded : null], $loaded ? 'review_ark_preparation' : 'none');
        $flags = []; $unknown = false; $enabled = false;
        foreach (AsusReportPlatform::ARK_KEYS as $key) {
            $raw = $n[$key]??null; $value = is_string($raw) && preg_match('/^[0-9]{1,10}$/D',$raw) ? $raw !== '0' : null;
            $flags[$key] = $value; $unknown = $unknown || $value === null; $enabled = $enabled || $value === true;
        }
        $items[] = self::item('ark_flags', $enabled ? 'attention' : ($unknown ? 'info' : 'ready'), $flags, $unknown ? 'unknown_flag_is_not_failure' : 'none');
        $config = AsusReportValues::runtimeSettings($this->io->read('config')['value']);
        $number = isset($config['NFQUEUE_NUM']) && is_string($config['NFQUEUE_NUM']) ? AsusReportValues::decimal($config['NFQUEUE_NUM'],'65535') : null;
        $queue = $this->io->read('queue',16384); $bound = false;
        foreach (explode("\n",$queue['value']) as $line) {
            $parts = preg_split('/\s+/',trim($line));
            if ($number !== null && count($parts) >= 9 && preg_match('/^[0-9]+$/D',$parts[0]) && ltrim($parts[0],'0') === ltrim($number,'0') && preg_match('/^[0-9]+$/D',$parts[1]) && (float)$parts[1] > 0) $bound = true;
        }
        $backend = $modules['state']==='available' ? (bool)preg_match('/^nfnetlink_queue\s/m',$modules['value']) : null;
        $items[] = self::item('process', $identity['running'] === true ? 'ready' : 'info', ['running'=>$identity['running'], 'rss_kib'=>$rss], 'process_is_not_service_success');
        $items[] = self::item('nfqueue', $bound ? 'ready' : 'info', ['number'=>$number===null?null:(int)$number, 'bound'=>$bound, 'backend_loaded'=>$backend, 'traffic_tested'=>false], 'check_queue_and_full_service_response');
        $dns = (new AsusReportDns($this->io,$values))->collect();
        $externalRead = $this->io->read('dns_external_config',65536); $externalInit = $this->io->read('dns_external_init',16384);
        $managed = isset($this->deps['managed_identity']) && ($this->deps['managed_identity'])() === true;
        $external = $externalRead['state'] !== 'missing' || $externalInit['state'] !== 'missing' || (in_array('smartdns',$processes['names'],true) && !$managed);
        $items[] = self::item('dns_runtime', $external ? 'attention' : 'info', ['external_smartdns'=>$external, 'managed_runtime'=>$managed, 'process_names'=>$processes['names'], 'dns_context'=>$dns, 'connectivity_tested'=>false], $external ? 'external_smartdns' : 'run_explicit_dns_validation');
        $ports = [];
        foreach (['dns_udp'=>'udp','dns_udp6'=>'udp6','dns_tcp'=>'tcp','dns_tcp6'=>'tcp6'] as $source=>$protocol) {
            $r = $this->io->read($source,65536);
            foreach (explode("\n",$r['value']) as $line) if (preg_match('/^\s*\d+: [0-9A-Fa-f]+:([0-9A-Fa-f]{4}) /',$line,$m)) {
                $port = hexdec($m[1]); if (in_array($port,[53,6053,6054],true)) $ports[$protocol.':'.$port] = ['protocol'=>$protocol, 'port'=>$port];
            }
        }
        $items[] = self::item('ports','info',['listeners'=>array_values($ports)],'port_is_not_process_ownership');
        $hooks = []; $hookConflict = false;
        foreach (['hook_dnsmasq'=>['dnsmasq_postconf','dns_forwarding'],'hook_mount'=>['post_mount','opt_ready_start'],'hook_init'=>['init_start','opt_storage_bootstrap_if_needed'],'hook_firewall'=>['firewall_start','firewall_reapply_if_used']] as $source=>[$id,$purpose]) {
            $r = $this->io->read($source,65536); $present = $r['state'] === 'available';
            $own = $present && str_contains($r['value'],'# BEGIN NFQWS2 SMARTDNS MANAGED');
            $earlyExit = $present && !$own && (bool)preg_match('/^\s*(?:exit|exec)\b/m',$r['value']);
            if ($id === 'dnsmasq_postconf' && ($earlyExit || !in_array($r['state'],['available','missing'],true))) $hookConflict = true;
            $hooks[] = ['id'=>$id, 'purpose'=>$purpose, 'present'=>$present, 'read_state'=>$r['state'], 'owned_block'=>$own, 'early_exit'=>$earlyExit, 'executable'=>$present?is_executable($this->io->path($source)):null];
        }
        $scripts = isset($n['jffs2_scripts']) && in_array($n['jffs2_scripts'],['0','1'],true) ? $n['jffs2_scripts']==='1' : null;
        $items[] = self::item('hooks', $hookConflict || $scripts === false ? 'attention' : 'info', [
            'custom_scripts_enabled'=>$scripts, 'items'=>$hooks,
            'smartdns_itself_requires_hook'=>false,
            'selected_forwarding_method'=>'merlin_dnsmasq_postconf',
            'selected_method_requires_postconf'=>true,
            'local_forwarding_requires_firewall_hook'=>false,
            'opt_readiness_required'=>true,
            'dns_scope'=>'primary_lan', 'guest_sdn_vpn_tested'=>false, 'boot_tested'=>false,
        ], $hookConflict ? 'check_hook_conflicts' : 'hooks_depend_on_selected_feature');
        $now = isset($this->deps['now']) ? ($this->deps['now'])() : time(); $ca = is_readable($this->io->path('dns_ca'));
        $items[] = self::item('tls', $now < 1704067200 || !$ca ? 'attention' : 'info', ['clock_plausible'=>$now>=1704067200, 'ca_present'=>$ca, 'certificate_tested'=>false], 'certificate_requires_network_validation');
        try { $install = isset($this->deps['installer_availability']) ? ($this->deps['installer_availability'])() : (new AsusSmartDnsInstaller())->availability(); }
        catch (Throwable $e) { $install = ['available'=>false, 'code'=>'unsupported_runtime']; }
        $codes = [];
        if (!$install['available']) $codes[] = AsusSmartDnsInstaller::code($install['code']);
        if ($abi === null) $codes[] = 'unsupported_abi';
        if (!$optItem['facts']['writable_estimate']) $codes[] = $optItem['facts']['readonly'] ? 'opt_readonly' : 'storage_unavailable';
        if ($available !== null && $available < 65536) $codes[] = 'insufficient_memory';
        if ($optItem['facts']['free_bytes'] !== null && (float)$optItem['facts']['free_bytes'] < 50331648) $codes[] = 'insufficient_space';
        // Installation reserves cover extraction/backups, not a permanent RAM
        // minimum for an already installed runtime. Apply has its own real probe.
        try { $installed = isset($this->deps['installed']) ? ($this->deps['installed'])() : (new AsusSmartDnsInstaller())->installed()['installed']; }
        catch (Throwable $e) { $installed = false; }
        $items[] = self::item('smartdns_engine', $installed ? 'ready' : 'info', ['installed'=>$installed], $installed ? 'configure_and_validate' : 'install_optional_engine');
        $connect = [];
        if (!$installed) $connect[] = 'not_installed';
        if ($abi === null) $connect[] = 'unsupported_abi';
        if (!$optItem['facts']['writable_estimate']) $connect[] = $optItem['facts']['readonly'] ? 'opt_readonly' : 'storage_unavailable';
        if ($now < 1704067200) $connect[] = 'invalid_clock';
        if (!$ca) $connect[] = 'https_unavailable';
        if ($external) $connect[] = 'external_smartdns';
        if ($hookConflict) $connect[] = 'check_hook_conflicts';
        if (!$jffsItem['facts']['writable_estimate']) $connect[] = 'jffs_unavailable';
        if ($scripts !== true) $connect[] = $scripts===false ? 'jffs_scripts_disabled' : 'jffs_scripts_unknown';
        return ['schema_version'=>1, 'checked_at'=>gmdate('Y-m-d\TH:i:s\Z',(int)$now), 'items'=>$items,
            'readiness'=>['nfqws2'=>['ready'=>$identity['running']===true && $bound && !$loaded, 'codes'=>$bound?[]:['queue_not_bound']],
            'smartdns_install'=>['ready'=>!$codes,'codes'=>array_values(array_unique($codes))], 'smartdns_connect'=>['ready'=>!$connect,'codes'=>array_values(array_unique($connect))]],
            'limits'=>['read_only','write_access_estimated','dns_not_queried','service_success_not_tested','modules_not_loaded']];
    }
}
