<?php
require __DIR__.'/support_report_fixture.php';
require __DIR__.'/../webui/web/public/support-report.php';
$io=new ReportFixtureIO();
$io->files['config']="NFQUEUE_NUM=300\nNFQWS_BASE_ARGS='--lua-init=@/opt/etc/nfqws2/lua/CANARY_MISSING.lua'\n";
$io->files['baseline']=json_encode(['schema_version'=>1,'engine'=>['sha256'=>[],'version'=>[]],'resources'=>['lua/CANARY.lua'=>['sha256'=>[]]]]);
$io->files['backup']=json_encode(['version'=>1,'restored'=>false,'created'=>['CANARY']]);
$io->inventory['lua']['CANARY.lua']='SECRET_SOURCE';
$r=(new AsusSupportReport($io,new AsusReportValues()))->collect();
reportCheck($r['complete']===false,'malformed sources give partial file');
reportCheck($r['sections']['resources']['data']['missing_references']===1,'missing strategy dependency identified');
$text=AsusSupportReport::encode($r);
foreach(['CANARY','SECRET_SOURCE','/opt/'] as $secret)reportCheck(!str_contains($text,$secret),'raw source not leaked');
$r['sections']['resources']['data']['oversized']=str_repeat('x',1048577);
$bounded=AsusSupportReport::encode($r);reportCheck(strlen($bounded)<=1048576 && json_decode($bounded,true)['complete']===false,'valid bounded partial JSON');
$s=AsusReportValues::literalSettings("f(){\nNFQUEUE_NUM=777\n}\n");
reportCheck(($s['NFQUEUE_NUM']??null)===null,'function body is not a literal global assignment');
echo "PASS malformed sources/privacy/missing resources/size\n";
