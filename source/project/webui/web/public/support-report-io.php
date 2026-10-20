<?php
// Fixed read-only sources; overrides are injected by local fixtures, never HTTP.
class AsusReportIO
{
    private array $roots;
    private $clock;
    private $sleep;
    private float $start;
    private array $resourceStates = [];
    private const SOURCES = [
        'config'=>['opt','etc/nfqws2/nfqws2.conf'], 'runtime'=>['tmp','nfqws2-asus/runtime.conf'],
        'wan'=>['tmp','nfqws2-asus/wan'], 'pid'=>['tmp','nfqws2-asus/pid'],
        'baseline'=>['opt','share/nfqws2-asus/report-baseline.json'],
        'backup'=>['opt','etc/nfqws-asus-web/ark-backup.json'],
        'opkg'=>['opt','etc/opkg.conf'], 'modules'=>['proc','modules'],
        'kernel'=>['proc','sys/kernel/osrelease'], 'machine'=>['proc','sys/kernel/arch'],
        'boot'=>['proc','sys/kernel/random/boot_id'], 'uptime'=>['proc','uptime'],
        'memory'=>['proc','meminfo'], 'queue'=>['proc','net/netfilter/nfnetlink_queue'],
        'tables4'=>['proc','net/ip_tables_names'], 'tables6'=>['proc','net/ip6_tables_names'],
        'conntrack'=>['proc','sys/net/netfilter/nf_conntrack_count'],
        'conntrack_max'=>['proc','sys/net/netfilter/nf_conntrack_max'],
        'ark_present'=>['proc','ark/status'], 'package'=>['opt','lib/opkg/info/nfqws2-asus.control'],
        'dns_forwarders'=>['tmp','resolv.dnsmasq'], 'dns_resolv'=>['tmp','resolv.conf'],
        'dns_stubby'=>['etc','stubby/stubby.yml'],
        'dnscrypt_a'=>['opt','etc/dnscrypt-proxy2/dnscrypt-proxy.toml'],
        'dnscrypt_b'=>['opt','etc/dnscrypt-proxy/dnscrypt-proxy.toml'],
        'dnscrypt_c'=>['opt','etc/dnscrypt-proxy.toml'],
        'mounts'=>['proc','mounts'], 'dnsmasq_config'=>['tmp','etc/dnsmasq.conf'],
        'dns_udp'=>['proc','net/udp'], 'dns_tcp'=>['proc','net/tcp'],
        'dns_udp6'=>['proc','net/udp6'], 'dns_tcp6'=>['proc','net/tcp6'],
        'dns_ca'=>['opt','etc/ssl/certs/ca-certificates.crt'],
        'dns_external_config'=>['opt','etc/smartdns/smartdns.conf'],
        'dns_external_init'=>['opt','etc/init.d/S50smartdns'],
        'hook_dnsmasq'=>['jffs','scripts/dnsmasq.postconf'],
        'hook_mount'=>['jffs','scripts/post-mount'],
        'hook_init'=>['jffs','scripts/init-start'],
        'hook_firewall'=>['jffs','scripts/firewall-start'],
    ];

    public function __construct(array $roots = [], ?callable $clock = null, ?callable $sleep = null)
    {
        $this->roots = $roots + ['opt'=>'/opt','proc'=>'/proc','sys'=>'/sys','tmp'=>'/tmp','ark'=>'/usr/ark','etc'=>'/etc','jffs'=>'/jffs'];
        $this->clock = $clock ?? static function() { $t=hrtime(); return $t[0]+$t[1]/1e9; };
        $this->sleep = $sleep ?? static fn($seconds) => usleep((int)min(1000000, max(0, $seconds * 1e6)));
        $this->start = $this->now();
    }
    public function now(): float { return ($this->clock)(); }
    public function remaining(): float { return max(0, 25 - ($this->now() - $this->start)); }
    public function pause(float $seconds): void
    {
        $until = $this->now() + min($seconds, $this->remaining());
        while ($this->now() < $until) ($this->sleep)(min(0.1, $until - $this->now()));
    }
    private function result(string $state, string $value = ''): array { return ['state'=>$state,'value'=>$value]; }

    public function path(string $source): ?string
    {
        if (!isset(self::SOURCES[$source])) return null;
        [$root,$path] = self::SOURCES[$source]; return $this->roots[$root] . '/' . $path;
    }
    private function safePath(string $root, string $relative, bool $proc = false): ?string
    {
        $canonical = realpath($root);
        if ($canonical === false || str_contains($relative, '..')) return null;
        $path = $canonical;
        // Linux exposes /proc/net through self/net. Accept only that in-proc
        // numeric task directory; all other symlinks remain denied.
        if ($proc && str_starts_with($relative, 'net/')) {
            $net = realpath($canonical.'/net');
            if ($net === false || ($net !== $canonical.'/net' &&
                !preg_match('~^'.preg_quote($canonical,'~').'/[1-9][0-9]*/net$~D', $net))) return null;
            $path = $net; $relative = substr($relative, 4);
        }
        if ($proc && $relative === 'mounts' && is_link($canonical.'/mounts')) {
            $mounts = realpath($canonical.'/mounts');
            if ($mounts === false || !preg_match('~^'.preg_quote($canonical,'~').'/[1-9][0-9]*/mounts$~D', $mounts)) return null;
            $path = $mounts; $relative = '';
        }
        foreach (explode('/', $relative) as $part) {
            if ($part === '') continue;
            $path .= '/' . $part;
            if (is_link($path)) return null;
        }
        if (file_exists($path) && !is_file($path)) return null;
        return $path;
    }
    private function boundedFile(?string $path, int $limit): array
    {
        if ($this->remaining() <= 0) return $this->result('timeout');
        if ($path === null) return $this->result('denied');
        if (!file_exists($path)) return $this->result('missing');
        if (!is_readable($path)) return $this->result('denied');
        $f = @fopen($path, 'rb'); if (!$f) return $this->result('denied');
        $stat = fstat($f);
        if (($stat['mode'] & 0170000) !== 0100000) { fclose($f); return $this->result('denied'); }
        $data = stream_get_contents($f, max(1, min(262144, $limit)) + 1); fclose($f);
        if ($data === false) return $this->result('denied');
        return strlen($data) > min(262144, $limit) ? $this->result('truncated') : $this->result('available', $data);
    }
    public function read(string $sourceId, int $limit = 262144): array
    {
        if (!isset(self::SOURCES[$sourceId])) return $this->result('denied');
        [$root,$relative] = self::SOURCES[$sourceId];
        return $this->boundedFile($this->safePath($this->roots[$root], $relative, $root === 'proc'), $limit);
    }
    public function readProcess(int $pid, string $field, int $limit = 16384): array
    {
        if ($pid <= 1 || !in_array($field, ['stat','status','exe','comm'], true)) return $this->result('denied');
        if ($field === 'exe') {
            $exe = @readlink($this->roots['proc'] . '/' . $pid . '/exe');
            return $exe === false ? $this->result('missing') : $this->result('available', $exe);
        }
        return $this->boundedFile($this->safePath($this->roots['proc'], "$pid/$field", true), $limit);
    }
    public function engine(): array
    {
        $path = $this->safePath($this->roots['opt'], 'usr/bin/nfqws2');
        if (!$path || !is_file($path)) return ['state'=>'missing'];
        $f = @fopen($path, 'rb'); if (!$f) return ['state'=>'denied'];
        $header = fread($f, 20); $ctx = hash_init('sha256'); hash_update($ctx, $header); $size = strlen($header);
        while (!feof($f) && $this->remaining() > 0 && $size <= 16777216) { $part = fread($f, 65536); if ($part === false) break; hash_update($ctx, $part); $size += strlen($part); }
        $done = feof($f); fclose($f);
        if (!$done) return ['state'=>$this->remaining() <= 0 ? 'timeout' : 'truncated'];
        return ['state'=>'available','executable'=>is_executable($path),'sha256'=>hash_final($ctx),'elf_class'=>str_starts_with($header,"\x7fELF") ? ord($header[4]) : null,
            'elf_machine'=>strlen($header) >= 20 ? (ord($header[5]) === 1 ? unpack('v',substr($header,18,2))[1] : unpack('n',substr($header,18,2))[1]) : null];
    }
    public function enginePath(): string { return (realpath($this->roots['opt']) ?: $this->roots['opt']) . '/usr/bin/nfqws2'; }
    public function dnsProcesses(bool $withMemory = false): array
    {
        $allowed=['stubby','dnscrypt-proxy','dnscrypt-proxy2','https-dns-proxy','AdGuardHome','smartdns','nextdns','cloudflared'];
        $entries=@scandir($this->roots['proc']);if(!is_array($entries))return $withMemory ? ['state'=>'missing','names'=>[],'rss'=>[]] : ['state'=>'missing','names'=>[]];
        $names=[];$rss=[];$count=0;$state='available';$until=$this->now()+min(0.75,$this->remaining());
        foreach($entries as $pid)if(preg_match('/^[1-9][0-9]{0,8}$/D',$pid)&&(int)$pid>1) {
            if(++$count>1024||$this->now()>=$until){$state='truncated';break;}
            $r=$this->readProcess((int)$pid,'comm',64);
            if($r['state']!=='available'){if(is_dir($this->roots['proc'].'/'.$pid))$state='partial';continue;}
            $name=trim($r['value']);
            if(in_array($name,$allowed,true))$names[]=$name==='dnscrypt-proxy2'?'dnscrypt-proxy':$name;
            if($withMemory && ($name==='dnsmasq' || in_array($name,$allowed,true))) {
                if(count($rss)>=32){$state='truncated';break;}
                $status=$this->readProcess((int)$pid,'status',4096);
                $memory=null;
                if($status['state']==='available' && preg_match('/^VmRSS:\s+([0-9]{1,12}) kB$/m',$status['value'],$m)) $memory=(float)$m[1];
                // A disappearing task or missing VmRSS is unknown, never zero.
                $rss[]=['name'=>$name==='dnscrypt-proxy2'?'dnscrypt-proxy':$name,'rss_kib'=>$memory];
            }
        }
        $out=['state'=>$state,'names'=>array_values(array_unique($names))];
        if($withMemory)$out['rss']=$rss;
        return $out;
    }
    public function arkComponents(): array
    {
        if (is_dir($this->roots['sys'].'/module/ark')) return ['state'=>'available','present'=>true,'loaded'=>true];
        $dir=$this->roots['ark'];
        if (is_dir($dir) && is_readable($dir) && is_executable($dir)) {
            foreach (['ark.ko','ark_service','arkctl'] as $name) if (is_file($dir.'/'.$name)) return ['state'=>'available','present'=>true];
            return ['state'=>'available','present'=>false];
        }
        if (!file_exists($dir) && is_readable(dirname($dir))) return ['state'=>'available','present'=>false];
        return ['state'=>'denied','present'=>null];
    }
    public function runtimeComponents(?string $abi): array
    {
        $paths=['init'=>'etc/init.d/S51nfqws2','platform'=>'lib/nfqws2-asus/platform.sh',
            'lifecycle'=>'lib/nfqws2-asus/lifecycle.sh','args'=>'lib/nfqws2-asus/args.sh',
            'abi'=>'lib/nfqws2-asus/abi.sh','diagnostics'=>'lib/nfqws2-asus/diagnostics.sh',
            'shell'=>'libexec/nfqws2-asus/busybox'];
        if (in_array($abi,['armv7-2.6','armv7-3.2'],true)) $paths['selected_shell']='libexec/nfqws2-asus/'.$abi.'/busybox';
        $out=[];
        foreach ($paths as $label=>$relative) {
            $path=$this->safePath($this->roots['opt'],$relative);
            $read=['state'=>$path===null?'denied':(file_exists($path)?'denied':'missing'),'value'=>''];
            // Only a fixed-size header is needed, even for a native runtime.
            if ($path && is_file($path) && is_readable($path)) {
                $f=@fopen($path,'rb'); $header=$f ? fread($f,20) : false; if($f)fclose($f);
                if($header!==false) $read=['state'=>'available','value'=>$header];
            }
            $item=['state'=>$read['state'],'executable'=>$path && is_file($path) ? is_executable($path) : null];
            $h=$read['value'];
            if(strlen($h)>=20 && str_starts_with($h,"\x7fELF")) {
                $item['elf_class']=ord($h[4]);
                $item['elf_machine']=ord($h[5])===1?unpack('v',substr($h,18,2))[1]:unpack('n',substr($h,18,2))[1];
            }
            $out[$label]=$item;
        }
        return $out;
    }
    public function resources(string $kind): array
    {
        $dirs = ['list'=>'etc/nfqws2/lists','lua'=>'etc/nfqws2/lua','blob'=>'etc/nfqws2/blobs','opkg'=>'etc/opkg'];
        if (!isset($dirs[$kind])) return [];
        $path = $this->safePath($this->roots['opt'], $dirs[$kind]);
        // Directories are checked separately from regular-file reads.
        $root = realpath($this->roots['opt']); $dir = $root ? $root . '/' . $dirs[$kind] : '';
        $this->resourceStates[$kind]='available';
        if (!$root || !is_dir($dir)) { $this->resourceStates[$kind]=!$root||file_exists($dir)?'denied':'missing';return []; }
        $walk = $root;
        foreach (explode('/', $dirs[$kind]) as $part) { $walk .= '/'.$part; if (is_link($walk)) { $this->resourceStates[$kind]='denied';return []; } }
        $out = []; $h = @opendir($dir); if (!$h) { $this->resourceStates[$kind]='denied';return []; }
        while (($name = readdir($h)) !== false) { if ($name !== '.' && $name !== '..') $out[] = $name; if (count($out) >= 129) break; }
        closedir($h); sort($out);if(count($out)>128)$this->resourceStates[$kind]='truncated'; return $out;
    }
    public function resourcesState(string $kind): string { return $this->resourceStates[$kind]??'available'; }
    public function readResource(string $kind, string $basename, int $limit = 262144): array
    {
        $dirs = ['list'=>'etc/nfqws2/lists','lua'=>'etc/nfqws2/lua','blob'=>'etc/nfqws2/blobs','opkg'=>'etc/opkg'];
        if (!isset($dirs[$kind]) || $basename === '' || preg_match('/[\/\\\\\x00-\x1f]/', $basename) || str_contains($basename, '..')) return $this->result('denied');
        $result = $this->boundedFile($this->safePath($this->roots['opt'], $dirs[$kind].'/'.$basename), $limit);
        if ($result['state'] !== 'available' || !str_ends_with($basename, '.gz')) return $result;
        if (!function_exists('gzdecode')) return $this->result('unsupported');
        $raw = @gzdecode($result['value'], min(262144,$limit) + 1);
        if ($raw === false) return $this->result('unsupported');
        return strlen($raw) > $limit ? $this->result('truncated') : $this->result('available',$raw);
    }
    private function command(string $id): ?array
    {
        if (isset($this->roots['commands'])) return $this->roots['commands'][$id] ?? null;
        $commands = ['nvram'=>['nvram','show'], 'links'=>['ip','-o','link','show'],
            'addr4'=>['ip','-o','-4','addr','show'], 'addr6'=>['ip','-o','-6','addr','show'],
            'route4'=>['ip','-o','-4','route','show'], 'route6'=>['ip','-o','-6','route','show'],
            'machine'=>['uname','-m']];
        foreach ([4,6] as $family) foreach (['mangle','nat'] as $table)
            $commands["rules$family-$table"] = [$family === 4 ? 'iptables-save' : 'ip6tables-save','--modprobe','/bin/false','-c','-t',$table];
        if (!isset($commands[$id])) return null;
        $argv = $commands[$id]; $binary = array_shift($argv);
        foreach (['/usr/sbin','/sbin','/usr/bin','/bin','/opt/sbin','/opt/bin'] as $dir)
            if (is_file("$dir/$binary") && is_executable("$dir/$binary")) return ["$dir/$binary", ...$argv];
        return [];
    }
    public function streamCommand(string $commandId, callable $consumeLine, float $timeout = 1.0): array
    {
        $argv = $this->command($commandId);
        if ($argv === null) return ['state'=>'denied','exit_code'=>null];
        if (!$argv || !function_exists('proc_open')) return ['state'=>'unsupported','exit_code'=>null];
        if ($this->remaining() <= 0) return ['state'=>'timeout','exit_code'=>null];
        $end = $this->now() + min($timeout, $this->remaining());
        $process = @proc_open($argv, [0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']], $pipes, '/', ['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin:/opt/sbin:/opt/bin','LC_ALL'=>'C'], ['bypass_shell'=>true]);
        if (!is_resource($process)) return ['state'=>'unsupported','exit_code'=>null];
        foreach ($pipes as $pipe) stream_set_blocking($pipe, false);
        $bytes = 0; $buffer = ''; $state = 'available'; $exit = null;
        try {
            while (true) {
                if ($this->now() >= $end) { $state = 'timeout'; break; }
                foreach ([1,2] as $fd) {
                    $part = fread($pipes[$fd], 8192); if ($part === false) $part = '';
                    $bytes += strlen($part);
                    if ($bytes > 524288) { $state = 'truncated'; break 2; }
                    if ($fd === 1) {
                        $buffer .= $part;
                        while (($newline = strpos($buffer, "\n")) !== false) {
                            if ($newline > 8192) { $state = 'truncated'; break 3; }
                            $line = substr($buffer, 0, $newline); $buffer = substr($buffer, $newline+1); $consumeLine($line);
                        }
                        if (strlen($buffer) > 8192) { $state = 'truncated'; break 2; }
                    }
                }
                $status = proc_get_status($process);
                // Older PHP returns the exit code only once, before inherited pipes may reach EOF.
                if (!$status['running'] && $status['exitcode'] >= 0) $exit = $status['exitcode'];
                if (!$status['running'] && feof($pipes[1]) && feof($pipes[2])) break;
                usleep(1000);
            }
            if ($state === 'available' && $buffer !== '') $consumeLine($buffer);
        } finally {
            $status = proc_get_status($process);
            if ($state !== 'available' || $status['running']) { proc_terminate($process, 9); }
            foreach ($pipes as $pipe) fclose($pipe);
            $closed = proc_close($process); if ($exit === null || $exit < 0) $exit = $closed;
        }
        if ($state === 'available' && $exit !== 0) $state = 'unsupported';
        return ['state'=>$state,'exit_code'=>$exit];
    }
}
