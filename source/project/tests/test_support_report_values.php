<?php
require __DIR__ . '/../webui/web/public/support-report-values.php';
function check($yes, $name) { if (!$yes) throw new RuntimeException($name); }
$v = new AsusReportValues();
check($v::decimal('18446744073709551615', '18446744073709551615') === '18446744073709551615', 'uint64 remains decimal text');
check($v::decimal('18446744073709551616', '18446744073709551615') === null, 'overflow');
check($v::decimal('-1', '4294967295') === null, 'negative');
check($v::uint32('4294967295') == 4294967295.0, 'uint32 on ARM32');
$s = $v::literalSettings("A='literal\nvalue'\nB=123 # comment\nC=\"$(touch /tmp/REPORT_CANARY)\"\nB=2\nD='one'\"two\"\n");
check($s['A'] === "literal\nvalue", 'multiline literal');
check($s['B'] === null && $s['C'] === null && $s['D'] === null, 'duplicates and dynamic expressions unknown');
check(!file_exists('/tmp/REPORT_CANARY'), 'no shell evaluation');
check(method_exists(AsusReportValues::class,'runtimeSettings'),'runtime defaults parser missing');
check($v::runtimeSettings('NFQWS_ARGS="--filter-tcp=443"')['NFQUEUE_NUM']==='300','omitted queue has package default');
foreach (['NFQUEUE_NUM=""','NFQUEUE_NUM=65536','NFQUEUE_NUM=300'."\n".'NFQUEUE_NUM=301'] as $text)
    check($v::decimal($v::runtimeSettings($text)['NFQUEUE_NUM']??'','65535')===null,'explicit invalid queue is not defaulted');
check(($v::runtimeSettings("f(){\nA=1\n}\n")['NFQUEUE_NUM']??null)===null,'executable context stays unknown');
check($v::runtimeSettings('')===[],'missing configuration stays unknown');
check(method_exists(AsusReportValues::class,'referenceSettings'),'safe reference resolver missing');
$r=$v::referenceSettings('MODE_LIST="--hostlist=/opt/etc/nfqws2/lists/user.list"'."\n".'MODE_ALL="--hostlist=/opt/etc/nfqws2/lists/all.list"'."\n".'MODE_AUTO="$MODE_LIST --hostlist-auto=/opt/etc/nfqws2/lists/auto.list $MODE_ALL"'."\n".'NFQWS_EXTRA_ARGS="${MODE_AUTO}"'."\n".'BAD="$(touch /tmp/REPORT_CANARY)"'."\n");
check(str_contains($r['NFQWS_EXTRA_ARGS']??'','auto.list') && str_contains($r['NFQWS_EXTRA_ARGS']??'','all.list'),'earlier literal references resolved');
check($r['BAD']===null&&!file_exists('/tmp/REPORT_CANARY'),'commands never evaluated');
foreach (['A="$B"'."\n".'B="x"', 'B="x"'."\n".'A="$B"'."\n".'B="y"', 'A="$B"'."\n".'B="$A"'] as $text)check($v::referenceSettings($text)['A']===null,'forward duplicate and cycle remain unknown');
check($v->alias('WAN', 'secret-iface') === $v->alias('WAN', 'secret-iface'), 'stable within report');
check($v->alias('WAN', 'another') === 'WAN_2', 'local aliases');
foreach (['0.0.0.0/0','192.168.1.1/32','::/0','2001:db8::1/128'] as $ip) check($v::network($ip) !== null, 'network parse');
check($v::overlaps($v::network('192.168.0.0/16'), $v::network('192.168.1.1/32')), 'overlap');
check(!$v::overlaps($v::network('192.168.0.0/24'), $v::network('192.168.1.1/32')), 'disjoint');
check($v::network('::/129') === null, 'invalid prefix');
echo "PASS values\n";
