<?php
if(PHP_SAPI!=='cgi-fcgi'&&PHP_SAPI!=='cli')exit(1);
$id=end($argv);if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id))exit(1);
umask(0077);require_once '/opt/share/nfqws-asus-web/smartdns-api.php';
try{(new AsusSmartDnsJobs())->work($id);}catch(Throwable $e){exit(1);}
