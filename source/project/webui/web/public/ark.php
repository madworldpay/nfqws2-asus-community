<?php
// Scoped ASUS settings backup. No firmware files, modules or foreign hooks are changed.
const ASUS_ARK_BACKUP = '/opt/etc/nfqws-asus-web/ark-backup.json';
const ASUS_ARK_KEYS = [
    'ark_qoe_enable', 'ark_iam_enable', 'ark_limiter_enable', 'ark_log_enable',
    'ark_hyqos_enable', 'ark_mals_enable', 'ark_adblock_enable', 'ark_tracker_enable', 'ark_ids_enable',
];

class AsusArkPlatform
{
    private ?string $nvramBinary = null;

    public function __construct(private array $nvramCandidates = ['/bin/nvram', '/usr/sbin/nvram', '/sbin/nvram']) {}

    private function nvramCommand(): string
    {
        if ($this->nvramBinary === null) {
            foreach ($this->nvramCandidates as $path) {
                if (is_string($path) && is_file($path) && is_executable($path)) {
                    $this->nvramBinary = $path;
                    break;
                }
            }
        }
        if ($this->nvramBinary === null) throw new RuntimeException('read_failed');
        return escapeshellarg($this->nvramBinary);
    }

    public static function validateDiagnostics(mixed $value): array
    {
        $unknown = ['ark' => ['present' => 'unknown', 'loaded' => 'unknown'],
            'nfqueue' => ['queue_number' => null, 'state' => 'unknown', 'sequence' => null], 'process_running' => null];
        if (!is_array($value) || !is_array($value['ark'] ?? null) || !is_array($value['nfqueue'] ?? null) ||
            !array_key_exists('process_running', $value) || ($value['process_running'] !== null && !is_bool($value['process_running']))) return $unknown;
        $ark = $value['ark']; $queue = $value['nfqueue'];
        if (!in_array($ark['present'] ?? '', ['present', 'absent', 'unknown'], true) ||
            !in_array($ark['loaded'] ?? '', ['loaded', 'unloaded', 'unknown'], true) ||
            !in_array($queue['state'] ?? '', ['bound', 'unbound', 'unknown'], true) ||
            !array_key_exists('queue_number', $queue) || !array_key_exists('sequence', $queue)) return $unknown;
        $number = $queue['queue_number']; $sequence = $queue['sequence'];
        if ($number !== null && (!is_int($number) || $number < 0 || $number > 65535)) return $unknown;
        // json_decode uses a float above PHP_INT_MAX on ARM32; uint32 stays exact.
        if ($sequence !== null && ((!is_int($sequence) && !is_float($sequence)) || !is_finite((float)$sequence) ||
            $sequence < 0 || $sequence > 4294967295.0 || floor((float)$sequence) !== (float)$sequence)) return $unknown;
        if (($queue['state'] === 'bound' && ($number === null || $sequence === null)) ||
            ($queue['state'] !== 'bound' && $sequence !== null)) return $unknown;
        $lifetime = $queue['lifetime'] ?? null;
        if ($lifetime !== null && (!is_string($lifetime) || !preg_match('/^[0-9a-f]{64}$/D', $lifetime))) $lifetime = null;
        return ['ark' => ['present' => $ark['present'], 'loaded' => $ark['loaded']],
            'nfqueue' => ['queue_number' => $number, 'state' => $queue['state'], 'sequence' => $sequence] +
                (array_key_exists('lifetime', $queue) ? ['lifetime' => $queue['state'] === 'bound' && $value['process_running'] === true ? $lifetime : null] : []),
            'process_running' => $value['process_running']];
    }

    public function diagnostics(): array
    {
        $lines = []; $exit = 0;
        exec('/opt/etc/init.d/S51nfqws2 diagnostics 2>/dev/null', $lines, $exit);
        $raw = implode("\n", $lines);
        return self::validateDiagnostics($exit === 0 && strlen($raw) < 8192 ? json_decode($raw, true) : null);
    }

    public function snapshot(): array
    {
        $lines = []; $exit = 0;
        exec($this->nvramCommand() . ' show 2>/dev/null', $lines, $exit);
        if ($exit !== 0) throw new RuntimeException('read_failed');
        // Keep only whitelisted switches and identity, never expose the full NVRAM dump.
        $values = [];
        $wanted = array_merge(ASUS_ARK_KEYS, ['productid', 'odmpid', 'et0macaddr', 'lan_hwaddr']);
        foreach ($lines as $line) {
            $parts = explode('=', $line, 2);
            if (count($parts) === 2 && in_array($parts[0], $wanted, true)) $values[$parts[0]] = $parts[1];
        }
        $flags = [];
        foreach (ASUS_ARK_KEYS as $key) $flags[$key] = ['present' => array_key_exists($key, $values), 'value' => $values[$key] ?? ''];
        $model = ($values['odmpid'] ?? '') ?: ($values['productid'] ?? '');
        $identity = ($values['et0macaddr'] ?? '') ?: ($values['lan_hwaddr'] ?? '');
        if ($model === '' || $identity === '') throw new RuntimeException('read_failed');
        $loaded = $this->diagnostics()['ark']['loaded'];
        return ['model' => $model, 'device' => hash('sha256', $model . "\n" . $identity), 'flags' => $flags,
            'ark_loaded' => $loaded === 'unknown' ? null : $loaded === 'loaded'];
    }

    public function write(string $key, array $value): bool
    {
        if (!in_array($key, ASUS_ARK_KEYS, true)) return false;
        $argument = $value['present'] ? 'set ' . escapeshellarg($key . '=' . $value['value']) : 'unset ' . escapeshellarg($key);
        exec($this->nvramCommand() . ' ' . $argument . ' 2>/dev/null', $output, $exit);
        return $exit === 0;
    }

    public function commit(): bool
    {
        exec($this->nvramCommand() . ' commit 2>/dev/null', $output, $exit);
        return $exit === 0;
    }
}

class AsusArkSettings
{
    public function __construct(private AsusArkPlatform $platform, private string $path = ASUS_ARK_BACKUP) {}

    private function validateFlags(array $flags): bool
    {
        if (array_keys($flags) !== ASUS_ARK_KEYS) return false;
        foreach ($flags as $flag) {
            if (!is_array($flag) || array_keys($flag) !== ['present', 'value'] || !is_bool($flag['present']) ||
                !is_string($flag['value']) || !preg_match('/^(?:|-?[0-9]{1,10})$/D', $flag['value']) ||
                (!$flag['present'] && $flag['value'] !== '')) return false;
        }
        return true;
    }

    private function snapshot(): array
    {
        $s = $this->platform->snapshot();
        if (!isset($s['flags'], $s['model'], $s['device']) || !array_key_exists('ark_loaded', $s) ||
            ($s['ark_loaded'] !== null && !is_bool($s['ark_loaded'])) || !is_array($s['flags']) ||
            !$this->validateFlags($s['flags']) || !is_string($s['model']) || !is_string($s['device']) ||
            !preg_match('/^[0-9a-f]{64}$/D', $s['device'])) throw new RuntimeException('read_failed');
        return $s;
    }

    private function enabled(array $flag): bool { return $flag['value'] !== '' && (int)$flag['value'] !== 0; }

    private function changed(array $flags): array
    {
        return array_keys(array_filter($flags, fn($flag) => $this->enabled($flag)));
    }

    private function readBackup(): ?array
    {
        if (!file_exists($this->path)) return null;
        $raw = @file_get_contents($this->path);
        $b = $raw !== false && strlen($raw) < 65536 ? json_decode($raw, true) : null;
        if (!is_array($b) || ($b['version'] ?? null) !== 1 || !is_string($b['model'] ?? null) ||
            !is_string($b['device'] ?? null) || !preg_match('/^[0-9a-f]{64}$/D', $b['device']) ||
            !is_string($b['created'] ?? null) || !is_bool($b['restored'] ?? null) ||
            !is_array($b['flags'] ?? null) || !$this->validateFlags($b['flags']) ||
            ($b['changed'] ?? null) !== $this->changed($b['flags']) || !is_string($b['checksum'] ?? null)) {
            throw new RuntimeException('backup_invalid');
        }
        $checksum = $b['checksum']; unset($b['checksum']);
        if (!hash_equals(hash('sha256', json_encode($b, JSON_UNESCAPED_SLASHES)), $checksum)) throw new RuntimeException('backup_invalid');
        return $b;
    }

    private function saveBackup(array $b): void
    {
        $b['checksum'] = hash('sha256', json_encode($b, JSON_UNESCAPED_SLASHES));
        $tmp = @tempnam(dirname($this->path), '.ark-');
        if ($tmp === false) throw new RuntimeException('backup_failed');
        $handle = @fopen($tmp, 'wb');
        $raw = json_encode($b, JSON_UNESCAPED_SLASHES) . "\n";
        $ok = $handle !== false && chmod($tmp, 0600) && fwrite($handle, $raw) === strlen($raw) && fflush($handle);
        if ($ok) $ok = function_exists('fsync') && @fsync($handle);
        if ($handle !== false) fclose($handle);
        $ok = $ok && @rename($tmp, $this->path);
        if (!$ok) { @unlink($tmp); throw new RuntimeException('backup_failed'); }
        // Persist the rename as well as its contents before committing router settings.
        if (!$this->syncDirectory(dirname($this->path))) throw new RuntimeException('backup_failed');
    }

    protected function syncDirectory(string $directory): bool
    {
        $handle = @fopen($directory, 'r');
        if ($handle === false) return false;
        $ok = function_exists('fsync') && @fsync($handle);
        fclose($handle);
        return $ok;
    }

    private function view(array $s, ?array $b): array
    {
        $flags = [];
        foreach ($s['flags'] as $key => $flag) $flags[] = ['key' => $key, 'present' => $flag['present'], 'value' => $flag['value'], 'enabled' => $this->enabled($flag)];
        return ['status' => 0, 'model' => $s['model'], 'flags' => $flags, 'ark_loaded' => $s['ark_loaded'],
            'diagnostics' => self::diagnosticsView($this->platform->diagnostics()),
            'ready' => !$this->changed($s['flags']), 'revision' => hash('sha256', json_encode([$s, $b])),
            'backup' => $b === null ? null : ['created' => $b['created'], 'changed' => $b['changed'], 'restored' => $b['restored']]];
    }

    private static function diagnosticsView(array $diagnostics): array
    {
        return AsusArkPlatform::validateDiagnostics($diagnostics);
    }

    private function locked(callable $operation): array
    {
        $lock = @fopen($this->path . '.lock', 'c');
        if ($lock === false) return ['status' => 1, 'error' => 'backup_failed'];
        chmod($this->path . '.lock', 0600);
        if (!flock($lock, LOCK_EX | LOCK_NB)) { fclose($lock); return ['status' => 1, 'error' => 'busy']; }
        try { return $operation(); }
        catch (RuntimeException $e) { return ['status' => 1, 'error' => $e->getMessage()]; }
        finally { flock($lock, LOCK_UN); fclose($lock); }
    }

    public function status(): array
    {
        return $this->locked(fn() => $this->view($this->snapshot(), $this->readBackup()));
    }

    private function sameDevice(array $s, array $b): void
    {
        if ($s['model'] !== $b['model'] || !hash_equals($s['device'], $b['device'])) throw new RuntimeException('backup_foreign');
    }

    private function restoreValues(array $b): bool
    {
        $s = $this->snapshot(); $this->sameDevice($s, $b);
        // Refuse to overwrite a switch changed by the owner after our preparation.
        foreach ($b['changed'] as $key) {
            if ($s['flags'][$key] !== $b['flags'][$key] && $s['flags'][$key] !== ['present' => true, 'value' => '0']) {
                throw new RuntimeException('restore_conflict');
            }
        }
        $ok = true;
        foreach ($b['changed'] as $key) {
            if ($s['flags'][$key] !== $b['flags'][$key]) $ok = $this->platform->write($key, $b['flags'][$key]) && $ok;
        }
        $ok = $this->platform->commit() && $ok;
        $after = $this->snapshot();
        foreach ($b['changed'] as $key) if ($after['flags'][$key] !== $b['flags'][$key]) $ok = false;
        return $ok;
    }

    public function action(string $action, string $revision): array
    {
        return $this->locked(function () use ($action, $revision) {
            if (!in_array($action, ['prepare', 'restore'], true)) throw new RuntimeException('invalid_action');
            $s = $this->snapshot(); $b = $this->readBackup();
            if (!hash_equals($this->view($s, $b)['revision'], $revision)) throw new RuntimeException('stale');
            if ($b !== null && !$b['restored']) $this->sameDevice($s, $b);
            if ($action === 'restore') {
                if ($b === null || $b['restored']) throw new RuntimeException('backup_missing');
                if (!$this->restoreValues($b)) throw new RuntimeException('restore_failed');
                $b['restored'] = true; $this->saveBackup($b);
                return ['status' => 0, 'message' => 'restored', 'reboot_required' => true];
            }
            if ($s['ark_loaded'] === null) throw new RuntimeException('runtime_unknown');
            if ($b !== null && !$b['restored']) {
                if ($this->changed($s['flags'])) throw new RuntimeException('backup_active');
                return ['status' => 0, 'message' => 'already_prepared', 'reboot_required' => $s['ark_loaded']];
            }
            $b = ['version' => 1, 'model' => $s['model'], 'device' => $s['device'], 'created' => gmdate('c'),
                'flags' => $s['flags'], 'changed' => $this->changed($s['flags']), 'restored' => false];
            // Must succeed before the first NVRAM write. Survives reboot and package updates.
            $this->saveBackup($b);
            $ok = true;
            foreach ($b['changed'] as $key) {
                if (!$this->platform->write($key, ['present' => true, 'value' => '0'])) { $ok = false; break; }
            }
            if ($ok && $b['changed']) $ok = $this->platform->commit();
            if ($ok) $ok = !$this->changed($this->snapshot()['flags']);
            if (!$ok) {
                if ($this->restoreValues($b)) { $b['restored'] = true; $this->saveBackup($b); throw new RuntimeException('apply_failed'); }
                throw new RuntimeException('recovery_required');
            }
            return ['status' => 0, 'message' => 'prepared', 'reboot_required' => (bool)$b['changed'] || $s['ark_loaded']];
        });
    }
}
