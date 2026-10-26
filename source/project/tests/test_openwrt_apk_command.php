<?php
$module=dirname(__DIR__).'/webui/web/public/openwrt-apk-command.php';
function ok($v,$m){if(!$v)throw new RuntimeException($m);}function rejects(callable $f){try{$f();}catch(RuntimeException $e){return;}throw new RuntimeException('unsafe APK replay accepted');}
ok(is_file($module),'safe APK simulation builder missing');require $module;
$r=NfqwsOpenWrtApkCommand::simulation(['apk','add','--keys-dir','/tmp/keys','--network=no','--cache=no','--repositories-file','/dev/null','/tmp/package.apk']);
ok($r===['/usr/bin/apk','--keys-dir','/tmp/keys','--network=no','--cache=no','--repositories-file','/dev/null','add','--simulate=yes','--pretty-print=no','--progress=no','--','/tmp/package.apk'],'native updater replay');
$r=NfqwsOpenWrtApkCommand::simulation(['/usr/bin/apk','--simulate=no','del','nfqws2-native']);ok(!in_array('--simulate=no',$r,true)&&in_array('--simulate=yes',$r,true),'cannot override forced simulation');
$r=NfqwsOpenWrtApkCommand::simulation(['apk','-qvv','del','--','--simulate=no']);ok(array_slice($r,-2)===['--','--simulate=no'],'literal operands stay after forced options and separator');
$r=NfqwsOpenWrtApkCommand::simulation(['apk','add','--cache-dir','--simulate=no','nfqws2-native']);ok(array_slice($r,1,2)===['--cache-dir','--simulate=no']&&in_array('--simulate=yes',$r,true),'option values never become executable switches');
foreach([['apk','add','--unknown','x'],['apk','--root','/somewhere','del','nfqws2-native'],['apk','add','--keys-dir'],['/bin/sh','add','x'],['apk','add','bad'.chr(0).'name'],['apk','add','--simulate=no','--']]as $bad)rejects(fn()=>NfqwsOpenWrtApkCommand::simulation($bad));
ok(NfqwsOpenWrtApkCommand::affects("(1/2) Upgrading php8 (8.3 -> 8.4)\n(2/2) Upgrading nfqws2-native (1.3.2-r71 -> 1.3.2-r72)\nOK: 10 MiB in 200 packages\n")==='upgrade','detect own upgrade');
ok(NfqwsOpenWrtApkCommand::affects("(1/1) Purging nfqws2-native (1.3.2-r72)\nOK: 1 MiB in 199 packages\n")==='remove','detect own remove');
ok(NfqwsOpenWrtApkCommand::affects("(1/1) Installing unrelated (1)\nOK: 2 MiB in 200 packages\n")===null,'unrelated APK operation stays untouched');
rejects(fn()=>NfqwsOpenWrtApkCommand::affects('(1/1) UNKNOWN nfqws2-native (1)'));
echo "PASS: non-overridable read-only APK simulation and own-change classification\n";
