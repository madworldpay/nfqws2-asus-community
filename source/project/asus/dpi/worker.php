<?php
// Installed outside the document root. Only a detached root guardian calls this entry.
if(PHP_SAPI!=='cgi-fcgi'&&PHP_SAPI!=='cli')exit(1);
$job=end($argv);
if(!is_string($job)||!preg_match('/^[a-f0-9]{32}$/D',$job))exit(1);
require_once '/opt/share/nfqws-asus-web/dpi-jobs.php';
try{(new AsusDpiWorker())->run($job);}catch(Throwable $e){exit(1);}
