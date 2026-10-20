<?php
require __DIR__.'/support_report_fixture.php';
require __DIR__.'/../webui/web/public/support-report.php';
$io=new ReportFixtureIO(); $report=new AsusSupportReport($io,new AsusReportValues());
$identity=['boot'=>'private-boot','pid'=>345,'start_ticks'=>'999','exe'=>'/opt/usr/bin/nfqws2','running'=>true];
foreach([0,300,65535] as $queue) {
    $io->files['queue']="$queue 345 2 2 65535 0 0 4294967295 1\n";
    $a=$report->queueSample($queue,$identity);
    reportCheck($a['sequence']==4294967295.0 && $a['reserved']==1,'uint32/reserved');
}
$io->files['queue']="300 345 0 2 65535 0 0 10 1\n";$a=$report->queueSample(300,$identity);
$io->files['queue']="300 345 0 2 65535 1 2 15 1\n";$b=$report->queueSample(300,$identity);
reportCheck($report->compareQueue($a,$b)['delta']==5,'growth');
reportCheck($report->compareQueue($a,$a)['result']==='unchanged','no growth');
reportCheck($report->compareQueue($b,$a)['result']==='counter_decreased','reset or wrap unknown');
$c=$b;$c['_identity']['start_ticks']='1000';reportCheck($report->compareQueue($a,$c)['result']==='changed_during_collection','PID reuse');
$c=$b;$c['_binding']='777';reportCheck($report->compareQueue($a,$c)['result']==='changed_during_collection','rebind');
$c=$b;$c['_identity']['boot']='other';reportCheck($report->compareQueue($a,$c)['result']==='changed_during_collection','reboot');
$io->files['queue'].=$io->files['queue']; reportCheck($report->queueSample(300,$identity)['state']==='unknown','duplicate');
$io->files['queue']='';reportCheck($report->queueSample(300,$identity)['state']==='unbound','unbound');
$io->files['queue']="300 malformed\n";reportCheck($report->queueSample(300,$identity)['state']==='unknown','malformed');
$io=new ReportFixtureIO(); $io->files['config']="NFQUEUE_NUM=300\n";$io->files['runtime']=$io->files['config'];
$r=(new AsusSupportReport($io,new AsusReportValues()))->collect();
reportCheck($io->time>=110 && $io->time<=125,'ten second gap bounded');
reportCheck($r['schema_version']===1 && $r['complete']===false,'partial base report');
reportCheck(!str_contains(json_encode($r),'_identity')&&!str_contains(json_encode($r),'_binding'),'private identity excluded');
echo "PASS queue/collector\n";
