<?php
require __DIR__.'/../webui/web/public/support-mail-proof.php';
require __DIR__.'/../webui/web/public/support-mail.php';
function mailCheck($ok,$name) { if(!$ok) throw new RuntimeException($name); }
$raw="{\"schema_version\":1}\n";
$name='NFQWS2_GT-BE19000AI_2026-10-15_12-30-45Z.json';
$key=str_repeat('a',64); $proof=AsusReportProof::issue($raw,$name,$key,1000);
mailCheck(AsusReportProof::verify($proof,$raw,$name,$key,1000),'valid signature');
mailCheck(AsusReportProof::verify($proof,$raw,$name,$key,1600),'TTL boundary');
foreach([
 [$proof,$raw.' ',$name,$key,1000], [$proof,$raw,$name.'x',$key,1000],
 [$proof,$raw,$name,str_repeat('b',64),1000], [$proof,$raw,$name,$key,999],
 [$proof,$raw,$name,$key,1601], ['v1.bad',$raw,$name,$key,1000],
 [str_replace('v1.','v2.',$proof),$raw,$name,$key,1000],
] as $args)mailCheck(!AsusReportProof::verify(...$args),'reject mutation');
mailCheck(!str_contains($proof,$raw)&&!str_contains($proof,$key),'opaque proof');
$dir=sys_get_temp_dir().'/mail-test-'.bin2hex(random_bytes(8));mkdir($dir,0700);
$config=$dir.'/support-relay.json';
try {
 $mail=new AsusSupportMail($config,$dir.'/ca.pem',fileowner(__FILE__));
 mailCheck($mail->availability()===['configured'=>false,'code'=>'not_configured','dpi_attachments'=>false],'missing config');
 file_put_contents($config,'{"enabled":false,"url":""}');chmod($config,0600);
 mailCheck($mail->availability()['code']==='not_configured','disabled config');
 chmod($config,0644);mailCheck($mail->availability()['code']==='invalid_config','unsafe mode');chmod($config,0600);
 foreach(['http://example.invalid/nfqws-support/v1/reports','https://x:y@example.invalid/nfqws-support/v1/reports','https://example.invalid/nfqws-support/v1/reports?secret=PRIVATE_CANARY','https://example.invalid/nfqws-support/v1/reports#PRIVATE_CANARY'] as $url) {
  file_put_contents($config,json_encode(['enabled'=>true,'url'=>$url]));
  mailCheck($mail->availability()['code']==='invalid_config','unsafe URL');
 }
 unlink($config);symlink($dir.'/other',$config);
 mailCheck($mail->availability()['code']==='invalid_config','symlink');unlink($config);
} finally { if(file_exists($config))unlink($config);rmdir($dir); }
echo "PASS report proof and private mail config\n";
