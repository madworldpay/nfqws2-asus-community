<?php
// Fixed CLI target of config-worker.sh. Never a public CGI endpoint.
if (!in_array(PHP_SAPI,['cli','cgi-fcgi'],true) || isset($_SERVER['REQUEST_METHOD']) || function_exists('posix_geteuid') && posix_geteuid()!==0) exit(2);
$id=end($argv);
if (!is_string($id) || !preg_match('/^[a-f0-9]{32}$/D',$id)) exit(2);
umask(0077);
require_once '/opt/share/nfqws-asus-web/smartdns-validation.php';
try { (new AsusSmartDnsValidationJob(new AsusSmartDnsStore()))->work($id); }
catch (Throwable $error) { exit(2); }
