<?php
declare(strict_types=1);
require_once __DIR__.'/update-dispatch.php';
require_once __DIR__.'/entware-package.php';
require_once __DIR__.'/keenetic-update-release.php';

/** The operator stages a signed release outside the document root. */
final class NfqwsKeeneticUpdate
{
    private const PACKAGE = 'nfqws2-keenetic-community';
    private const MAX_PACKAGE = 33554432;
    private const INBOX = 'keenetic-release/';
    private const ENTWARE_PATH = '/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin';

    public function __construct(private AsusUpdateStore $store) {}

    private function installed(): array
    {
        $installed = NfqwsEntwarePackage::installed(self::PACKAGE);
        if ($installed === null) throw new RuntimeException('unsupported_version');
        return $installed;
    }

    private function archive(string $name, string $digest, ?int $length = null): string
    {
        $path = $this->store->path($name);
        clearstatcache(true, $path);
        $stat = @lstat($path);
        if (!$stat || ($stat['mode'] & 0170777) !== 0100600 || $stat['uid'] !== 0
            || $stat['nlink'] !== 1 || $stat['size'] < 1 || $stat['size'] > self::MAX_PACKAGE
            || ($length !== null && $stat['size'] !== $length)) {
            throw new RuntimeException('invalid_package');
        }
        $actual = hash_file('sha256', $path);
        if (!is_string($actual) || !hash_equals($digest, $actual)) {
            throw new RuntimeException('download_hash');
        }
        return $path;
    }

    public function check(): array
    {
        $installed = $this->installed();
        $result = [
            'state' => 'unconfigured', 'candidate' => null, 'code' => null,
            'installed_version' => $installed['version'],
        ];
        $sums = $this->store->readFile(self::INBOX.'SHA256SUMS-keenetic.txt', 1024);
        if ($sums === null) return $result;
        $signature = $this->store->readFile(self::INBOX.'SHA256SUMS-keenetic.txt.sig', 384);
        $key = AsusUpdateStore::installed('share/nfqws2-asus/update-release-key.pem');
        AsusUpdateStore::noLinks($key);
        $publicKey = @file_get_contents($key, false, null, 0, 8193);
        if ($signature === null || !is_string($publicKey) || strlen($publicKey) > 8192) {
            throw new RuntimeException('signature_unavailable');
        }
        $candidate = NfqwsKeeneticUpdateRelease::candidate(
            $sums, $signature, $publicKey, $installed['architecture'], $installed['version']
        );
        if ($candidate === null) return array_replace($result, ['state' => 'current']);
        $package = $candidate['package'];
        $path = $this->archive(self::INBOX.$package['sha256'].'.ipk', $package['sha256']);
        $candidate['package']['size'] = filesize($path);
        $candidate += ['core_version' => '1.3.3', 'web_version' => '0.1.4', 'notes' => ''];
        return array_replace($result, ['state' => 'available', 'candidate' => $candidate]);
    }

    private function guard(): AsusUpdateGuard
    {
        return new AsusUpdateGuard($this->store);
    }

    public function prepare(string $revision, string $requestId): array
    {
        $lease = $this->guard()->mutationLease();
        try {
            $check = $this->check();
            $candidate = $check['candidate'];
            if ($candidate === null || !hash_equals($candidate['revision'], $revision)) {
                throw new RuntimeException('stale_revision');
            }
            $job = $this->store->reserve($revision, $requestId, $candidate + [
                'previous_version' => $check['installed_version'],
            ]);
            $id = $job['id'];
            if (!$this->store->claimPrepare($id)) return $this->store->readOperation($id);
            try {
                $package = $candidate['package'];
                $source = $this->archive(self::INBOX.$package['sha256'].'.ipk', $package['sha256'], $package['size']);
                $path = 'operations/'.$id.'/package.ipk';
                $destination = $this->store->path($path);
                $input = fopen($source, 'rb');
                if (!$input) throw new RuntimeException('download_failed');
                $mask = umask(0077);
                try {
                    $output = fopen($destination, 'xb');
                } finally {
                    umask($mask);
                }
                try {
                    if (!$output || stream_copy_to_stream($input, $output, self::MAX_PACKAGE + 1) !== $package['size']
                        || !fflush($output)) throw new RuntimeException('download_failed');
                } finally {
                    fclose($input);
                    if (is_resource($output)) fclose($output);
                }
                $this->archive($path, $package['sha256'], $package['size']);
                return $this->store->update($id, [
                    'state' => 'prepared', 'phase' => 'validating',
                    'prepared_uptime' => AsusUpdateStore::uptime(),
                    'runtime_digest' => $this->preparedDigest($candidate),
                ]);
            } catch (Throwable $e) {
                return $this->store->update($id, ['state' => 'failed', 'code' => AsusUpdatePrepare::code($e)]);
            }
        } finally {
            flock($lease, LOCK_UN);
            fclose($lease);
        }
    }

    private function preparedDigest(array $candidate): string
    {
        return hash('sha256', $candidate['revision'].$candidate['package']['sha256']);
    }

    public function apply(string $id, string $revision, string $requestId): array
    {
        $lease = $this->guard()->mutationLease();
        try {
            $claim = $this->store->claimApply($id, $revision, $requestId);
        } finally {
            flock($lease, LOCK_UN);
            fclose($lease);
        }
        if (!$claim['launch']) return $claim['operation'];

        $worker = AsusUpdateStore::installed('lib/nfqws2-asus/keenetic-update-worker.php');
        // Scope the lookup to this operation so the panel's PHP process cannot match.
        $lookup = $this->store->path('operations/'.$id.'/unused-guard.pid');
        if (@lstat($lookup) !== false) {
            return $this->store->update($id, ['state' => 'failed', 'code' => 'launch_failed']);
        }
        $process = @proc_open(
            ['/opt/bin/busybox', 'start-stop-daemon', '-S', '-b', '-p', $lookup, '-x', '/opt/bin/php-cgi',
                '--', '-q', '-d', 'register_argc_argv=1', '-f', $worker, '--', $id],
            [0 => ['file', '/dev/null', 'r'], 1 => ['file', '/dev/null', 'a'], 2 => ['file', '/dev/null', 'a']],
            $pipes, '/', ['PATH' => self::ENTWARE_PATH, 'LANG' => 'C', 'HOME' => '/']
        );
        if (!is_resource($process) || proc_close($process) !== 0) {
            return $this->store->update($id, ['state' => 'failed', 'code' => 'launch_failed']);
        }
        return $this->store->readOperation($id);
    }

    /** Runs in the detached, root-owned PHP worker after HTTP authentication and consent. */
    public function install(string $id): void
    {
        $lock = $this->store->lease('apply.lock');
        try {
            $job = $this->store->readOperation($id);
            if ($job['state'] !== 'applying' || $job['boot_id'] !== AsusUpdateStore::boot()) {
                throw new RuntimeException('invalid_state');
            }
            $identity = AsusUpdateLifecycle::identity(getmypid());
            if ($identity === null || $identity['uid'] !== 0) throw new RuntimeException('invalid_state');
            $this->store->update($id, ['identity' => $identity, 'phase' => 'validating']);
            $raw = $this->store->readFile('operations/'.$id.'/candidate.json');
            $candidate = $raw === null ? null : json_decode($raw, true, 16, JSON_THROW_ON_ERROR);
            if (!is_array($candidate) || $candidate['package_version'] !== $job['package_version']
                || !hash_equals($job['runtime_digest'], $this->preparedDigest($candidate))) {
                throw new RuntimeException('stale_revision');
            }
            $installed = $this->installed();
            $package = $candidate['package'];
            if ($installed['version'] !== $candidate['previous_version']
                || $installed['architecture'] !== $package['family']) throw new RuntimeException('stale_revision');
            $archive = $this->archive('operations/'.$id.'/package.ipk', $package['sha256'], $package['size']);
            $config = AsusUpdateStore::installed('etc/nfqws2/nfqws2.conf');
            AsusUpdateStore::noLinks($config);
            $before = hash_file('sha256', $config);
            $service = NfqwsPlatform::serviceStatus('keenetic-entware');
            if (!is_string($before) || $service['status'] !== 0) throw new RuntimeException('invalid_state');

            // Entware opkg needs its package tools on PATH even during a dry run.
            $preflight = NfqwsPlatform::run([
                '/opt/bin/busybox', 'env', 'PATH='.self::ENTWARE_PATH, 'LANG=C', 'HOME=/',
                '/opt/bin/opkg', '--noaction', 'install', $archive,
            ], 15);
            self::verifyPlan($preflight, $installed['version'], $job['package_version']);
            $this->archive('operations/'.$id.'/package.ipk', $package['sha256'], $package['size']);
            $this->store->update($id, ['phase' => 'installing']);
            $logPath = 'operations/'.$id.'/opkg.log';
            $mask = umask(0077);
            try {
                $log = fopen($this->store->path($logPath), 'xb');
            } finally {
                umask($mask);
            }
            if (!$log) throw new RuntimeException('install_failed');
            try {
                $opkg = proc_open(
                    ['/opt/bin/opkg', 'install', $archive],
                    [0 => ['file', '/dev/null', 'r'], 1 => $log, 2 => $log],
                    $pipes, '/', ['PATH' => self::ENTWARE_PATH, 'LANG' => 'C', 'HOME' => '/']
                );
                if (!is_resource($opkg) || proc_close($opkg) !== 0) throw new RuntimeException('install_failed');
            } finally {
                fclose($log);
            }
            $output = $this->store->readFile($logPath);
            $upgrade = 'Upgrading '.self::PACKAGE.' on root from '.$installed['version'].' to '.$job['package_version'].'...';
            $lines = $output === null ? [] : preg_split('/\R/', trim($output));
            $reported = array_values(array_filter($lines, static fn(string $line): bool =>
                !preg_match('~^Removing obsolete file /[^\x00-\x1F]+\.$~D', $line)
            ));
            if ($reported !== [$upgrade, 'Configuring '.self::PACKAGE.'.']) throw new RuntimeException('install_failed');
            $this->store->update($id, ['phase' => 'verifying']);
            $after = $this->installed();
            if ($after['version'] !== $job['package_version'] || $after['architecture'] !== $package['family']) {
                throw new RuntimeException('version_mismatch');
            }
            if (hash_file('sha256', $config) !== $before || NfqwsPlatform::serviceStatus('keenetic-entware') !== $service) {
                throw new RuntimeException('settings_changed');
            }
            $this->store->update($id, [
                'state' => 'succeeded', 'phase' => 'finished', 'installed_version' => $after['version'],
                'core_state' => $service['service'] ? 'running' : 'stopped', 'settings_verified' => true,
            ]);
        } catch (Throwable $e) {
            if ($this->store->readOperation($id)['state'] === 'applying') {
                $this->store->update($id, ['state' => 'failed', 'code' => AsusUpdatePrepare::code($e)]);
            }
        } finally {
            flock($lock, LOCK_UN);
            fclose($lock);
        }
    }

    public static function verifyPlan(array $result, string $from, string $to): void
    {
        $upgrade = 'Upgrading '.self::PACKAGE.' on root from '.$from.' to '.$to.'...';
        $lines = array_values(array_diff($result['output'], ['']));
        if ($result['status'] !== 0 || !in_array($lines, [[$upgrade], [$upgrade, 'Configuring '.self::PACKAGE.'.']], true)) {
            throw new RuntimeException('dependency_change');
        }
    }
}
