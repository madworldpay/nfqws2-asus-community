<?php
if (isset($_SERVER['REQUEST_METHOD']) || !in_array(PHP_SAPI,['cli','cgi-fcgi'],true)) exit(1);
$id = end($argv);
if (!is_string($id) || !preg_match('/^[a-f0-9]{32}$/D',$id)) exit(1);
umask(0077);
require_once '/opt/share/nfqws-asus-web/mtproto-install-api.php';
try {
    (new AsusMtprotoInstall())->work($id);
} catch (Throwable $e) {
    exit(1);
}
