<?php
require __DIR__ . '/../webui/web/public/ark.php';
function must($condition, $label) { if (!$condition) throw new RuntimeException($label); }
class FakeArkPlatform extends AsusArkPlatform {
    public array $state;
    public array $writes = [];
    public int $commits = 0;
    public ?string $failKey = null;
    public int $failCommits = 0;
    public function __construct() {
        $this->state = ['model' => 'Another ASUS', 'device' => hash('sha256', 'test-device'), 'ark_loaded' => true, 'flags' => []];
        foreach (ASUS_ARK_KEYS as $key) $this->state['flags'][$key] = ['present' => false, 'value' => ''];
    }
    public int $sequence = 0;
    public function diagnostics(): array { return ['ark'=>['present'=>'present','loaded'=>$this->state['ark_loaded'] === null ? 'unknown' : ($this->state['ark_loaded'] ? 'loaded' : 'unloaded')], 'nfqueue'=>['queue_number'=>300,'state'=>'bound','sequence'=>$this->sequence], 'process_running'=>true]; }
    public function snapshot(): array { return $this->state; }
    public function write(string $key, array $value): bool {
        $this->writes[] = $key;
        if ($this->failKey === $key) { $this->failKey = null; return false; }
        $this->state['flags'][$key] = $value;
        return true;
    }
    public function commit(): bool { $this->commits++; if ($this->failCommits > 0) { $this->failCommits--; return false; } return true; }
}
class FailedDirectorySync extends AsusArkSettings {
    protected function syncDirectory(string $directory): bool { return false; }
}
$dir = sys_get_temp_dir() . '/nfqws-ark-' . bin2hex(random_bytes(6)); mkdir($dir, 0700);
function fixture($suffix): array {
    global $dir;
    $platform = new FakeArkPlatform;
    return [$platform, new AsusArkSettings($platform, "$dir/$suffix.json")];
}
try {
    // Legacy Merlin keeps nvram in /usr/sbin rather than /bin. Exercise the
    // real platform adapter with an isolated executable, never host NVRAM.
    $nativeNvram = "$dir/legacy nvram";
    $receipt = "$dir/native-commands";
    $fixture = <<<'SH'
#!/bin/sh
case "$1" in
show)
 printf '%s\n' 'productid=RT-AC87U' 'lan_hwaddr=02:00:00:00:00:87' 'ark_qoe_enable=0' 'http_passwd=fake-not-for-export'
 ;;
*)
 printf '%s\n' "$*" >> __RECEIPT__
 ;;
esac
SH;
    file_put_contents($nativeNvram, str_replace('__RECEIPT__', escapeshellarg($receipt), $fixture));
    chmod($nativeNvram, 0700);
    $native = new AsusArkPlatform(["$dir/missing-bin-nvram", $nativeNvram]);
    $nativeSnapshot = $native->snapshot();
    must($nativeSnapshot['model'] === 'RT-AC87U', 'legacy native nvram path can read the actual snapshot adapter');
    must($nativeSnapshot['device'] === hash('sha256', "RT-AC87U\n02:00:00:00:00:87"), 'legacy LAN MAC fallback preserves device binding');
    must($nativeSnapshot['flags']['ark_qoe_enable'] === ['present'=>true,'value'=>'0'], 'native snapshot reads only approved flags');
    must(!str_contains(json_encode($nativeSnapshot), 'fake-not-for-export'), 'native snapshot never exports unrelated NVRAM values');
    must($native->write('ark_qoe_enable', ['present'=>true,'value'=>'0']), 'selected native binary handles allowed write');
    must(!$native->write('http_passwd', ['present'=>true,'value'=>'0']), 'unknown NVRAM key is rejected before command execution');
    must($native->commit(), 'selected native binary handles commit');
    must(file($receipt, FILE_IGNORE_NEW_LINES) === ['set ark_qoe_enable=0', 'commit'], 'read/write/commit use one selected executable without extra commands');

    [$p, $s] = fixture('unknown');
    $p->state['ark_loaded'] = null;
    $status = $s->status();
    must($status['status'] === 0 && $status['ark_loaded'] === null, 'unknown runtime remains nullable');
    must($s->action('prepare', $status['revision'])['error'] === 'runtime_unknown' && !$p->writes, 'unknown prepare fails before writes');

    [$p, $s] = fixture('sequence');
    $p->sequence=0; $one=$s->status(); $p->sequence=123; $two=$s->status();
    must($one['revision'] === $two['revision'], 'sequence is not a settings revision');
    must($two['diagnostics']['nfqueue']['sequence'] === 123, 'queue status visible');
    must($s->action('prepare', $one['revision'])['status'] === 0, 'counter changes cannot stale prepare');
    $p->state['ark_loaded']=null;
    must($s->action('restore',$s->status()['revision'])['reboot_required'] === true, 'unknown runtime permits verified restore');

    must(method_exists(AsusArkPlatform::class, 'validateDiagnostics'), 'diagnostic schema validation missing');
    $valid=$p->diagnostics();
    foreach ([0,2147483648.0,4294967295.0] as $seq) { $valid['nfqueue']['sequence']=$seq; must(AsusArkPlatform::validateDiagnostics($valid)['nfqueue']['sequence'] == $seq, 'uint32 survives ARM32 float parsing'); }
    foreach ([-1,4294967296.0,1.5,INF,NAN,'1'] as $seq) { $valid['nfqueue']['sequence']=$seq; must(AsusArkPlatform::validateDiagnostics($valid)['nfqueue']['state'] === 'unknown', 'invalid sequence rejected'); }

    $valid=$p->diagnostics();$valid['nfqueue']['sequence']=20;$valid['nfqueue']['lifetime']=str_repeat('a',64);
    must(AsusArkPlatform::validateDiagnostics($valid)['nfqueue']['lifetime']===str_repeat('a',64),'validated lifetime reaches API');
    foreach(['not-a-token',123,[],str_repeat('A',64)] as $bad) {
        $valid['nfqueue']['lifetime']=$bad;
        $view=AsusArkPlatform::validateDiagnostics($valid);
        must($view['nfqueue']['state']==='bound' && $view['nfqueue']['lifetime']===null,'malformed identity cannot authenticate delivery or hide queue');
    }
    $valid['nfqueue']['lifetime']=str_repeat('a',64);$valid['process_running']=false;
    must(AsusArkPlatform::validateDiagnostics($valid)['nfqueue']['lifetime']===null,'stopped daemon cannot authenticate counter proof');
    [$p, $s] = fixture('all');
    foreach (ASUS_ARK_KEYS as $k) $p->state['flags'][$k] = ['present' => true, 'value' => '1'];
    $original = $p->state;
    $r = $s->action('prepare', $s->status()['revision']);
    must($r['status'] === 0, 'all nine flags can be prepared on another model without a firmware gate');
    must(count($p->writes) === 9, 'all enabled ARK features changed');
    $backup = file_get_contents("$dir/all.json");
    must((fileperms("$dir/all.json") & 0777) === 0600, 'backup private');
    must($s->action('prepare', $s->status()['revision'])['status'] === 0, 'repeated prepare works');
    must(file_get_contents("$dir/all.json") === $backup, 'repeat never overwrites original backup');
    must($s->action('restore', $s->status()['revision'])['status'] === 0, 'restore succeeds');
    must($p->state === $original, 'all nine values roundtrip exactly');

    [$p, $s] = fixture('minimal');
    $p->state['flags'][ASUS_ARK_KEYS[0]] = ['present' => true, 'value' => '1'];
    $p->state['flags'][ASUS_ARK_KEYS[1]] = ['present' => true, 'value' => ''];
    $p->state['flags'][ASUS_ARK_KEYS[2]] = ['present' => true, 'value' => '0'];
    $original = $p->state;
    must($s->action('prepare', $s->status()['revision'])['status'] === 0, 'minimal preparation');
    must($p->writes === [ASUS_ARK_KEYS[0]], 'empty, absent and zero flags not written');
    $p->state['flags'][ASUS_ARK_KEYS[3]] = ['present' => true, 'value' => '1'];
    must($s->action('restore', $s->status()['revision'])['status'] === 0, 'unrelated user changes preserved');
    must($p->state['flags'][ASUS_ARK_KEYS[3]]['value'] === '1', 'restore only touches changed keys');
    unset($p->state['flags'][ASUS_ARK_KEYS[3]]);
    unset($original['flags'][ASUS_ARK_KEYS[3]]);
    must($p->state === $original, 'absent and present-empty keys remain exact');

    [$p, $s] = fixture('stale');
    $revision = $s->status()['revision']; $p->state['flags'][ASUS_ARK_KEYS[0]] = ['present' => true, 'value' => '1'];
    must($s->action('prepare', $revision)['status'] !== 0 && !$p->writes, 'stale preview rejected before writes');

    [$p, $s] = fixture('failed');
    foreach (ASUS_ARK_KEYS as $k) $p->state['flags'][$k] = ['present' => true, 'value' => '1'];
    $original = $p->state; $p->failKey = ASUS_ARK_KEYS[2];
    must($s->action('prepare', $s->status()['revision'])['status'] !== 0, 'partial write failure reported');
    must($p->state === $original && file_exists("$dir/failed.json"), 'failure rolls back with backup retained');
    [$p, $s] = fixture('commit');
    $p->state['flags'][ASUS_ARK_KEYS[0]] = ['present' => true, 'value' => '2']; $original = $p->state; $p->failCommits = 1;
    must($s->action('prepare', $s->status()['revision'])['status'] !== 0 && $p->state === $original, 'failed commit rolls back');

    [$p, $s] = fixture('conflict');
    $p->state['flags'][ASUS_ARK_KEYS[0]] = ['present' => true, 'value' => '1'];
    must($s->action('prepare', $s->status()['revision'])['status'] === 0, 'conflict fixture prepared');
    $p->state['flags'][ASUS_ARK_KEYS[0]]['value'] = '2'; $p->writes = [];
    must($s->action('restore', $s->status()['revision'])['status'] !== 0 && !$p->writes, 'conflicting user change rejected');
    $p->state['device'] = hash('sha256', 'foreign-device');
    must($s->action('restore', $s->status()['revision'])['status'] !== 0 && !$p->writes, 'foreign device backup rejected');

    [$p, $s] = fixture('corrupt'); file_put_contents("$dir/corrupt.json", '{broken');
    must($s->action('prepare', 'anything')['status'] !== 0 && !$p->writes, 'corrupt backup never overwritten');
    [$p, $s] = fixture('missing-dir');
    $s = new AsusArkSettings($p, "$dir/nonexistent/backup.json");
    must($s->action('prepare', 'anything')['status'] !== 0 && !$p->writes, 'backup write failure prevents any NVRAM writes');
    [$p, $s] = fixture('sync');
    $p->state['flags'][ASUS_ARK_KEYS[0]] = ['present' => true, 'value' => '1'];
    $s = new FailedDirectorySync($p, "$dir/sync.json");
    must($s->action('prepare', $s->status()['revision'])['status'] !== 0 && !$p->writes,
        'backup directory must be durable before any NVRAM write');
    echo "PASS: nine flags, minimal changes, exact backup/restore, foreign model, repeat, failure and conflicts\n";
} finally {
    foreach (glob("$dir/*") as $p) unlink($p); rmdir($dir);
}
