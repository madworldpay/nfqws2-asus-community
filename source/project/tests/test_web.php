<?php
$lib = __DIR__ . '/../webui/web/public/asus.php';
if (file_exists($lib)) require $lib;
function verify($value, $label) {
    if (!$value) { fwrite(STDERR, "FAIL: $label\n"); exit(1); }
}
verify(function_exists('asusAuthenticate'), 'ASUS authentication must exist');
$dir = sys_get_temp_dir() . '/nfqws-auth-' . bin2hex(random_bytes(6));
mkdir($dir, 0700);
try {
    $hash = crypt('test-password', '$6$nfqws-test$');
    file_put_contents("$dir/passwd", "admin:x:0:0:admin:/root:/bin/sh\nvisitor:x:1000:1000::/:/bin/false\n");
    file_put_contents("$dir/shadow", "admin:$hash:0:0:0:0:0:0:0\nvisitor:$hash:0:0:0:0:0:0:0\n");
    verify(asusAuthenticate('admin', 'test-password', "$dir/passwd", "$dir/shadow"), 'UID-0 ASUS account can log in');
    verify(!asusAuthenticate('admin', 'wrong', "$dir/passwd", "$dir/shadow"), 'wrong password rejected');
    verify(!asusAuthenticate('visitor', 'test-password', "$dir/passwd", "$dir/shadow"), 'unprivileged account rejected');
    foreach (['', '!', '*', '!!', '!'.$hash] as $locked) {
        file_put_contents("$dir/shadow", "admin:$locked:0:0:0:0:0:0:0\n");
        verify(!asusAuthenticate('admin', '', "$dir/passwd", "$dir/shadow"), 'blank or locked account rejected');
    }
    unlink("$dir/shadow");
    verify(!asusAuthenticate('admin', 'x', "$dir/passwd", "$dir/shadow"), 'missing shadow fails closed');
    file_put_contents("$dir/passwd", "admin:$hash:0:0::/:/bin/sh\n");
    verify(asusAuthenticate('admin', 'test-password', "$dir/passwd", "$dir/shadow"), 'passwd hash supported when shadow absent');
    verify(function_exists('asusWebReadAuth'), 'panel must support a separate password override');
    $path = "$dir/auth.json";
    copy(__DIR__ . '/../asus/web-auth.json', $path);
    $auth = asusWebReadAuth($path, "$dir/passwd", "$dir/shadow");
    verify($auth !== null && $auth['mode'] === 'system', 'fresh install uses the router account');
    verify(asusWebAuthenticate('admin', 'test-password', $auth), 'existing router credentials work');
    verify(!asusWebAuthenticate('root', 'asus', $auth), 'fallback does not bypass available router credentials');
    $fallback = asusWebReadAuth($path, "$dir/absent-passwd", "$dir/absent-shadow");
    verify(asusWebAuthenticate('root', 'asus', $fallback), 'root/asus works only when system credentials unavailable');
    verify(asusWebSavePassword('admin', 'new secret', $path), 'new panel password saved');
    $changed = asusWebReadAuth($path, "$dir/passwd", "$dir/shadow");
    verify(asusWebAuthenticate('admin', 'new secret', $changed), 'custom password persists with the same username');
    verify(!asusWebAuthenticate('admin', 'test-password', $changed), 'old system password no longer logs into panel');
    verify(asusAuthenticate('admin', 'test-password', "$dir/passwd", "$dir/shadow"), 'router account remains unchanged');
    verify($auth['revision'] !== $changed['revision'], 'old sessions can be invalidated');
    verify(!str_contains(file_get_contents($path), 'new secret'), 'password not stored as plaintext');
    verify((fileperms($path) & 0777) === 0600, 'credentials readable only by owner');
    $before = file_get_contents($path);
    verify(!asusWebSavePassword('admin', str_repeat('x', 73), $path), 'oversized bcrypt password rejected');
    verify(file_get_contents($path) === $before, 'failed change preserves existing password');
    verify(!asusWebSavePassword('admin', 'valid', "$dir/missing/auth.json"), 'write failure reported');
    verify(asusWebSavePassword('admin', '', $path), 'empty password saved');
    verify(asusWebReadAuth($path)['password_hash'] === '', 'empty password explicitly disables login');
    verify(asusWebSavePassword('admin', 'restored', $path), 'protection can be enabled again');
    verify(asusWebAuthenticate('admin', 'restored', asusWebReadAuth($path)), 're-enabled password works');
    file_put_contents($path, '{broken');
    verify(asusWebReadAuth($path) === null, 'malformed config fails closed');
    unlink($path);
    verify(asusWebReadAuth($path) === null, 'missing config fails closed');
    verify(asusUpgradeResponse()['status'] !== 0, 'upstream upgrades unavailable');
    echo "PASS: ASUS login, panel password persistence, disabling and update isolation\n";
} finally {
    foreach (glob("$dir/*") as $file) unlink($file);
    rmdir($dir);
}
