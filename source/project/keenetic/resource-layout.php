<?php
declare(strict_types=1);

// Called by opkg postinst, outside the web root. The vendor IPK archives these
// three directories as 1001:1001. The privileged importer requires root parents.
function layoutStat(string $path): ?array
{
    clearstatcache(true, $path);
    $s = @lstat($path);
    return $s === false ? null : array_intersect_key($s, array_flip(
        ['dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtime', 'ctime']
    ));
}

function layoutRequire(bool $ok, string $path): void
{
    if (!$ok) throw new RuntimeException("Cannot prepare panel resources at $path");
}

function layoutDirectory(string $path): void
{
    $s = layoutStat($path);
    layoutRequire($s !== null && ($s['mode'] & 0170022) === 0040000 && $s['uid'] === 0, $path);
}

function layoutBytes(string $path, array $s): string
{
    layoutRequire(($s['mode'] & 0170000) === 0100000 && $s['nlink'] === 1 && $s['size'] <= 262144, $path);
    $f = @fopen($path, 'rb');
    layoutRequire($f !== false, $path);
    try {
        layoutRequire(array_intersect_key(fstat($f), $s) === $s, $path);
        $bytes = stream_get_contents($f, 262145);
        layoutRequire(is_string($bytes) && strlen($bytes) === $s['size']
            && array_intersect_key(fstat($f), $s) === $s && layoutStat($path) === $s, $path);
        return $bytes;
    } finally { fclose($f); }
}

function layoutWrite(string $path, string $bytes, int $mode): void
{
    $f = @fopen($path, 'xb');
    layoutRequire($f !== false, $path);
    try {
        layoutRequire(fwrite($f, $bytes) === strlen($bytes) && chmod($path, $mode)
            && fflush($f) && fsync($f), $path);
    } finally { fclose($f); }
}

function layoutFactory(string $opt): array
{
    $share = "$opt/share/nfqws2-asus";
    foreach (["$opt/share", $share, "$share/factory", "$share/factory/lua"] as $dir) layoutDirectory($dir);
    $manifest = "$share/report-baseline.json";
    $read = static function(string $path): string {
        $s = layoutStat($path);
        layoutRequire($s !== null && $s['uid'] === 0 && ($s['mode'] & 0022) === 0, $path);
        return layoutBytes($path, $s);
    };
    $baseline = json_decode($read($manifest), true, 32, JSON_THROW_ON_ERROR);
    $copies = [];
    foreach (['zapret-lib.lua', 'zapret-antidpi.lua', 'zapret-auto.lua', 'local-guarded-ts.lua', 'local-tls13-stun.lua'] as $name) {
        $key = "lua/$name";
        $source = "$share/factory/$key";
        $bytes = $read($source);
        $sha = hash('sha256', $bytes);
        $pin = $baseline['resources'][$key] ?? [];
        layoutRequire(($pin['bytes'] ?? null) === strlen($bytes) && ($pin['sha256'] ?? null) === $sha, $source);
        $copies[$sha] = $bytes;
    }
    return $copies;
}

function layoutInstall(string $opt): void
{
    $base = "$opt/etc/nfqws2";
    $private = "$opt/etc/nfqws-asus-web";
    foreach ([$opt, "$opt/etc", $base, $private] as $dir) layoutDirectory($dir);
    $lock = fopen($private, 'rb');
    layoutRequire($lock !== false && flock($lock, LOCK_EX | LOCK_NB), $private);
    try {
        $copies = layoutFactory($opt);
        $changes = [];
        $evidence = [];
        foreach (['lists', 'lua', 'blobs', 'lists/user.list', 'lists/exclude.list'] as $relative) {
            $path = "$base/$relative";
            $s = layoutStat($path);
            $dir = !str_contains($relative, '/');
            if ($s === null && !$dir) continue;
            layoutRequire($s !== null && ($s['mode'] & 0170000) === ($dir ? 0040000 : 0100000), $path);
            if ($dir && $s['uid'] === 0) { layoutDirectory($path); continue; }
            if (!$dir && in_array($s['uid'], [0, 65534], true)) continue;
            $modes = $dir ? [0755] : [0644, 0664, 0666];
            layoutRequire($s['uid'] === 1001 && $s['gid'] === 1001 && in_array($s['mode'] & 07777, $modes, true), $path);
            $changes[$relative] = $s;
            $evidence[$relative] = ['stat'=>$s];
            if (!$dir) $evidence[$relative]['data_base64'] = base64_encode(layoutBytes($path, $s));
        }
        if ($changes) {
            $backup = "$private/resource-owners-".bin2hex(random_bytes(8)).'.json';
            layoutWrite($backup, json_encode($evidence, JSON_THROW_ON_ERROR)."\n", 0600);
            $parent = fopen($private, 'rb');
            try { layoutRequire(fsync($parent), $private); } finally { fclose($parent); }
            foreach ($changes as $relative=>$before) {
                $path = "$base/$relative";
                layoutDirectory(dirname($path));
                layoutRequire(layoutStat($path) === $before && chown($path, 0), $path);
                $after = layoutStat($path);
                $preserved = array_diff_key($before, ['uid'=>true, 'ctime'=>true]);
                layoutRequire($after !== null && $after['uid'] === 0
                    && array_intersect_key($after, $preserved) === $preserved, $path);
            }
        }
        $dir = "$base/lua/imported";
        if (layoutStat($dir) === null) {
            $mask = umask(0022);
            try { layoutRequire(mkdir($dir, 0755), $dir); } finally { umask($mask); }
        }
        layoutDirectory($dir);
        foreach ($copies as $sha=>$bytes) {
            $dest = "$dir/$sha.lua";
            $tmp = "$dir/.$sha.community-install";
            // A previous postinst may have died between link and unlink.
            $pending = layoutStat($tmp);
            $existing = layoutStat($dest);
            if ($pending !== null) {
                layoutRequire($pending['uid'] === 0 && ($pending['mode'] & 0170022) === 0100000, $tmp);
                if ($existing !== null && $existing['ino'] === $pending['ino'] && $existing['dev'] === $pending['dev']) {
                    layoutRequire($pending['nlink'] === 2, $tmp);
                } else {
                    layoutRequire($pending['nlink'] === 1 && str_starts_with($bytes, layoutBytes($tmp, $pending)), $tmp);
                }
                layoutRequire(unlink($tmp), $tmp);
                $existing = layoutStat($dest);
            }
            if ($existing !== null) {
                layoutRequire($existing['uid'] === 0 && ($existing['mode'] & 0022) === 0
                    && layoutBytes($dest, $existing) === $bytes, $dest);
                continue;
            }
            layoutWrite($tmp, $bytes, 0644);
            try { layoutRequire(link($tmp, $dest), $dest); } finally { unlink($tmp); }
        }
    } finally { fclose($lock); }
}

try {
    umask(0077);
    $alias = (getenv('IPKG_INSTROOT') ?: '').'/opt';
    $opt = realpath($alias);
    layoutRequire($opt !== false && (@lstat($alias)['uid'] ?? -1) === 0, $alias);
    layoutInstall($opt);
} catch (Throwable $error) {
    file_put_contents('php://stderr', $error->getMessage()."\n");
    exit(1);
}
