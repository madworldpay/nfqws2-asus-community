<?php
declare(strict_types=1);
require_once '/opt/share/nfqws-asus-web/platform.php';
if (NfqwsPlatform::current() !== 'keenetic-entware') {
    http_response_code(503);
    exit();
}
require '/opt/share/nfqws-asus-web/index.php';
