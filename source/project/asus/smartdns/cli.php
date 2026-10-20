<?php
require_once '/opt/share/nfqws-asus-web/smartdns-install.php';
try{echo (new AsusSmartDnsInstaller())->binaryDirectory();}catch(Throwable $e){exit(1);}
