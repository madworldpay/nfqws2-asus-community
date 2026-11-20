<?php
declare(strict_types=1);

// The installer can run this through either Entware PHP binary before changing any files.
if (!in_array(PHP_SAPI, ['cli', 'cgi-fcgi'], true) || isset($_SERVER['REQUEST_METHOD'])) {
    http_response_code(404);
    exit(1);
}
require_once dirname(__DIR__) . '/webui/web/public/platform.php';
require_once dirname(__DIR__) . '/webui/web/public/entware-package.php';
require_once __DIR__ . '/stock.php';

$facts = NfqwsKeeneticStock::inspect();
echo json_encode($facts, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES), "\n";
exit(in_array(null, $facts, true) ? 1 : 0);
