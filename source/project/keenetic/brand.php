<?php
declare(strict_types=1);

require_once '/opt/share/nfqws-asus-web/platform.php';
require_once '/opt/share/nfqws-asus-web/keenetic-stock.php';
if (NfqwsPlatform::current() !== 'keenetic-entware') {
    http_response_code(404);
    exit;
}
if (!in_array($_SERVER['REQUEST_METHOD'] ?? '', ['GET', 'HEAD'], true)) {
    header('Allow: GET, HEAD');
    http_response_code(405);
    exit;
}
header('Content-Type: application/javascript; charset=utf-8');
header('X-Content-Type-Options: nosniff');
$name = NfqwsKeeneticStock::brand(NfqwsKeeneticStock::board()['model']);
header('Cache-Control: private, max-age=' . ($name === 'Keenetic / Netcraze' ? '60' : '3600'));
if ($_SERVER['REQUEST_METHOD'] === 'HEAD') exit;
?>
(() => {
  const brand = <?= json_encode($name, JSON_THROW_ON_ERROR) ?>;
  document.documentElement.dataset.routerBrand = brand;
  document.title = document.title.replace('Keenetic / Netcraze', brand);
  const manifest = document.querySelector('link[rel="manifest"]');
  if (manifest && (brand === 'Netcraze' || brand === 'Keenetic')) {
    manifest.href = 'manifest-' + brand.toLowerCase() + '.json';
  }
  document.addEventListener('DOMContentLoaded', () => {
    const link = document.querySelector('[data-panel-home]');
    if (link) link.textContent = '← NFQWS2 · ' + brand;
  });
})();
