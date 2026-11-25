<?php
declare(strict_types=1);
if (!in_array(PHP_SAPI, ['cli', 'cgi-fcgi'], true) || isset($_SERVER['REQUEST_METHOD'])
    || !preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m', (string)file_get_contents('/proc/self/status'))) {
    exit(2);
}
$arguments = array_slice($argv ?? [], 1);
if (($arguments[0] ?? null) === '--') array_shift($arguments);
if (count($arguments) !== 1 || !preg_match('/^[a-f0-9]{32}$/D', $arguments[0])) exit(2);

require_once dirname(__DIR__, 2).'/share/nfqws-asus-web/keenetic-update.php';
if (NfqwsPlatform::current() !== 'keenetic-entware') exit(2);
(new NfqwsKeeneticUpdate(new AsusUpdateStore()))->install($arguments[0]);
