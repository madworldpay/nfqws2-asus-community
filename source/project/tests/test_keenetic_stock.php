<?php
declare(strict_types=1);
require_once dirname(__DIR__) . '/webui/web/public/entware-package.php';
require_once dirname(__DIR__) . '/webui/web/public/platform.php';
require_once dirname(__DIR__) . '/keenetic/stock.php';

function same(mixed $actual, mixed $want): void
{
    if ($actual !== $want) throw new RuntimeException('Unexpected Keenetic platform record');
}

$core = ['Package: nfqws2-keenetic', 'Version: 1.3.3', 'Status: install user installed', 'Architecture: aarch64-3.10'];
$web = ['Package: nfqws-keenetic-web', 'Version: 3.0.24', 'Status: install ok installed', 'Architecture: all'];
$available = ['Package: nfqws2-keenetic', 'Version: 1.4', 'Status: unknown ok not-installed', 'Architecture: all'];
$rows = [...$available, '', ...$core, '', ...$web];
same(NfqwsEntwarePackage::parseInstalled($rows, 'nfqws2-keenetic'), ['version'=>'1.3.3', 'architecture'=>'aarch64-3.10']);
same(NfqwsEntwarePackage::parseInstalled($rows, 'nfqws-keenetic-web'), ['version'=>'3.0.24', 'architecture'=>'all']);
same(NfqwsEntwarePackage::parseInstalled($available, 'nfqws2-keenetic'), null);
same(NfqwsEntwarePackage::parseInstalled([...$core, '', ...$core], 'nfqws2-keenetic'), null);
same(NfqwsEntwarePackage::parseInstalled([...$core, 'Version: 2.0'], 'nfqws2-keenetic'), null);
same(NfqwsKeeneticStock::boardRecord([' hw_id: NC-1812',' arch: aarch64',' release: 5.02.A.9.0-0',' serial: private']),
    ['model'=>'NC-1812','machine'=>'aarch64','firmware'=>'5.02.A.9.0-0']);
same(NfqwsKeeneticStock::boardRecord([' model: Keenetic-3765']),
    ['model'=>null, 'machine'=>null, 'firmware'=>null]);
same(NfqwsKeeneticStock::boardRecord(['hw_id: KN-1234','hw_id: NC-1812','arch: mips'])['model'], null);
same(NfqwsKeeneticStock::brand('KN-1711'), 'Keenetic');
same(NfqwsKeeneticStock::brand('NC-1812'), 'Netcraze');
same(NfqwsKeeneticStock::brand(null), 'Keenetic / Netcraze');
same(NfqwsKeeneticStock::brand('KN-1711.example'), 'Keenetic / Netcraze');
same(NfqwsPlatform::serviceCommand('diagnostics', 'keenetic-entware'), ['/opt/lib/nfqws2-asus/keenetic-diagnostics.sh']);
same(NfqwsPlatform::busybox('keenetic-entware'), '/opt/bin/busybox');
same(NfqwsPlatform::busybox('asus-entware'), '/opt/libexec/nfqws2-asus/busybox');
same(NfqwsPlatform::busybox('openwrt'), '/bin/busybox');
foreach (['status', 'start', 'stop', 'restart'] as $action) {
    same(NfqwsPlatform::serviceCommand($action, 'keenetic-entware'), ['/opt/etc/init.d/S51nfqws2', $action]);
}
same(NfqwsPlatform::serviceCommand('diagnostics', 'asus-entware'), ['/opt/etc/init.d/S51nfqws2', 'diagnostics']);
same(NfqwsPlatform::serviceCommand('diagnostics', 'openwrt'), ['/usr/lib/nfqws2/control.sh', 'diagnostics']);
echo "KeeneticOS board and installed package records verified\n";
