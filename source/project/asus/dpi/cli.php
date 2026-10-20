<?php
// CLI resolver, outside the document root. No network probes or shell input.
if(PHP_SAPI!=='cgi-fcgi'&&PHP_SAPI!=='cli')exit(1);
require_once '/opt/share/nfqws-asus-web/dpi-install.php';
try { echo (new AsusDpiInstaller())->binary(); }
catch(Throwable $e) { exit(1); }
