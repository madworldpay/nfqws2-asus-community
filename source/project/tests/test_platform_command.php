<?php
require_once __DIR__.'/../webui/web/public/platform.php';
function check(bool $ok,string $why):void{if(!$ok)throw new RuntimeException($why);}
$command=['/bin/sh','-c',"head -c 80000 /dev/zero | tr '\\000' X"];
$default=NfqwsPlatform::run($command,5);check($default['status']!==0&&strlen(implode("\n",$default['output']))<=65536,'default command bound changed');
$metadata=NfqwsPlatform::run($command,5,[],131072);check($metadata['status']===0&&strlen(implode("\n",$metadata['output']))===80000,'bounded native metadata output was truncated');
foreach([0,1048577]as $limit){try{NfqwsPlatform::run($command,5,[],$limit);throw new LogicException('unbounded command accepted');}catch(RuntimeException $e){check($e->getMessage()==='invalid_output_limit','output bound error');}}
echo "Default command limits retained; larger native metadata remains explicitly bounded\n";
