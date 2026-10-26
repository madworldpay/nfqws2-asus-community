<?php
$module=dirname(__DIR__).'/webui/web/public/openwrt-update-payload.php';
function ok($v,$m){if(!$v)throw new RuntimeException($m);}function refused($f){try{$f();}catch(RuntimeException $e){return;}throw new RuntimeException('unsafe payload inventory accepted');}
ok(is_file($module),'native original-payload fingerprint missing');require $module;
$root=$argv[1];$owner=(int)$argv[2];mkdir($root.'/usr/share/nfqws2',0755,true);$p=$root.'/usr/share/nfqws2/fixture';file_put_contents($p,'old bytes');chmod($p,0644);
$paths=['/usr/share/nfqws2/fixture'];$v=NfqwsOpenWrtUpdatePayload::fromPaths($paths,$root,$owner);
ok(NfqwsOpenWrtUpdatePayload::unchanged($v,$root,$owner),'unchanged original payload');
file_put_contents($p,'new bytes');ok(!NfqwsOpenWrtUpdatePayload::unchanged($v,$root,$owner),'partial replacement must not restart old services');file_put_contents($p,'old bytes');
chmod($p,0600);ok(!NfqwsOpenWrtUpdatePayload::unchanged($v,$root,$owner),'mode change is not exact original');chmod($p,0644);
rename($p,$p.'.backup');symlink('fixture.backup',$p);ok(!NfqwsOpenWrtUpdatePayload::unchanged($v,$root,$owner),'symlink must not pass original fingerprint');unlink($p);rename($p.'.backup',$p);
foreach([['/etc/shadow'],['/usr/share/nfqws2/../other'],['/usr/share/nfqws2/fixture','/usr/share/nfqws2/fixture'],[]]as $bad)refused(fn()=>NfqwsOpenWrtUpdatePayload::fromPaths($bad,$root,$owner));
ok(NfqwsOpenWrtUpdatePayload::unchanged($v,$root,$owner),'restored exact bytes/mode');echo "PASS: exact original payload controls failure recovery\n";
