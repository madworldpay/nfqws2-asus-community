<?php
const ASUS_WEB_AUTH_FILE = '/opt/etc/nfqws-asus-web/auth.json';

// Only usable UID-0 system accounts participate in the default router login.
function asusWebSystemAccounts(string $passwdFile, string $shadowFile): array
{
    if (!is_readable($passwdFile)) return [];
    $accounts = [];
    foreach (file($passwdFile, FILE_IGNORE_NEW_LINES) ?: [] as $line) {
        $fields = explode(':', $line);
        if (count($fields) >= 7 && $fields[2] === '0') {
            $accounts[$fields[0]] = $fields[1];
        }
    }
    if (file_exists($shadowFile)) {
        if (!is_readable($shadowFile)) return [];
        $shadow = [];
        foreach (file($shadowFile, FILE_IGNORE_NEW_LINES) ?: [] as $line) {
            $fields = explode(':', $line);
            if (count($fields) >= 2 && isset($accounts[$fields[0]])) {
                $shadow[$fields[0]] = $fields[1];
            }
        }
        $accounts = $shadow;
    }
    return array_filter($accounts, fn($hash) => strlen($hash) >= 13 &&
        !str_starts_with($hash, '!') && !str_starts_with($hash, '*'));
}

function asusAuthenticate(string $username, string $password, string $passwdFile = '/etc/passwd', string $shadowFile = '/etc/shadow'): bool
{
    $accounts = asusWebSystemAccounts($passwdFile, $shadowFile);
    $hash = $accounts[$username] ?? null;
    if ($hash === null || $password === '') return false;
    $candidate = crypt($password, $hash);
    return strlen($candidate) >= 13 && hash_equals($hash, $candidate);
}

function asusWebReadAuth(string $path = ASUS_WEB_AUTH_FILE, string $passwdFile = '/etc/passwd', string $shadowFile = '/etc/shadow'): ?array
{
    $source = @file_get_contents($path);
    if ($source === false) return null;
    $auth = json_decode($source, true);
    if (!is_array($auth) || !in_array($auth['mode'] ?? null, ['system', 'password'], true) ||
        !is_string($auth['username'] ?? null) || $auth['username'] === '' ||
        !is_string($auth['password_hash'] ?? null)) return null;
    $hash = $auth['password_hash'];
    if ($hash !== '' && password_get_info($hash)['algo'] === null) return null;
    // The packaged system mode always has a protected fallback.
    if ($auth['mode'] === 'system' && $hash === '') return null;
    $accounts = $auth['mode'] === 'system' ? asusWebSystemAccounts($passwdFile, $shadowFile) : [];
    $auth['revision'] = hash('sha256', $source . json_encode($accounts));
    if ($accounts) {
        $auth['accounts'] = $accounts;
        $auth['username'] = array_key_first($accounts);
    } else {
        $auth['mode'] = 'password';
    }
    return $auth;
}

function asusWebAuthenticate(string $username, string $password, array $auth): bool
{
    if ($password === '') return false;
    if ($auth['mode'] === 'system') {
        $hash = $auth['accounts'][$username] ?? null;
        if ($hash === null) return false;
        $candidate = crypt($password, $hash);
        return strlen($candidate) >= 13 && hash_equals($hash, $candidate);
    }
    return $username === $auth['username'] && $auth['password_hash'] !== '' &&
        password_verify($password, $auth['password_hash']);
}

function asusWebSavePassword(string $username, string $password, string $path = ASUS_WEB_AUTH_FILE): bool
{
    // bcrypt accepts at most 72 bytes; never silently truncate a password.
    if ($username === '' || strlen($password) > 72 || str_contains($password, "\0")) return false;
    $auth = ['mode' => 'password', 'username' => $username,
        'password_hash' => $password === '' ? '' : password_hash($password, PASSWORD_BCRYPT, ['cost' => 10])];
    $dir = dirname($path);
    if (!is_dir($dir) || !is_writable($dir)) return false;
    $tmp = @tempnam($dir, '.auth-');
    if ($tmp === false) return false;
    $content = json_encode($auth, JSON_UNESCAPED_SLASHES) . "\n";
    $ok = chmod($tmp, 0600) && file_put_contents($tmp, $content, LOCK_EX) === strlen($content) &&
        rename($tmp, $path);
    if (!$ok) @unlink($tmp);
    return $ok;
}

function asusUpgradeResponse(): array
{
    return [
        'status' => 1,
        'output' => ['Install a matching ASUS package release manually. Upstream Keenetic upgrades are disabled for this port.'],
    ];
}
