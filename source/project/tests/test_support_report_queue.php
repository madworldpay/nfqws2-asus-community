<?php
require __DIR__.'/support_report_fixture.php';
require __DIR__.'/../webui/web/public/support-report.php';
$io=new ReportFixtureIO(); $io->sockets[345]['345']='9001'; $report=new AsusSupportReport($io,new AsusReportValues());
$identity=['boot'=>'11111111-2222-3333-4444-555555555555','pid'=>345,'start_ticks'=>'999','exe'=>'/opt/usr/bin/nfqws2','running'=>true];
foreach([0,300,65535] as $queue) {
    $io->files['queue']="$queue 345 2 2 65535 0 0 4294967295 1\n";
    $a=$report->queueSample($queue,$identity);
    reportCheck($a['sequence']==4294967295.0 && $a['reserved']==1,'uint32/reserved');
}
$io->files['queue']="300 345 0 2 65535 0 0 10 1\n";$a=$report->queueSample(300,$identity);
$io->files['queue']="300 345 0 2 65535 1 2 15 1\n";$b=$report->queueSample(300,$identity);
reportCheck($report->compareQueue($a,$b)['delta']==5,'growth');
reportCheck($report->compareQueue($a,$a)['result']==='unchanged','no growth');
$c=$a;$c['_identity']['boot']='';$d=$b;$d['_identity']['boot']='';reportCheck($report->compareQueue($c,$d)['result']==='unavailable','empty boot identity cannot prove stable lifetime');
reportCheck($report->compareQueue($b,$a)['result']==='counter_decreased','reset or wrap unknown');
$wrapBefore=$b;$wrapBefore['sequence']=4294967294.0;$wrapAfter=$a;$wrapAfter['sequence']=3;
reportCheck($report->compareQueue($wrapBefore,$wrapAfter)['result']==='counter_decreased','actual uint32 wrap remains unconfirmed');
$c=$b;$c['_identity']['start_ticks']='1000';reportCheck($report->compareQueue($a,$c)['result']==='changed_during_collection','PID reuse');
$c=$b;$c['_binding']='777';reportCheck($report->compareQueue($a,$c)['result']==='changed_during_collection','rebind');
$c=$b;$c['_identity']['boot']='other';reportCheck($report->compareQueue($a,$c)['result']==='changed_during_collection','reboot');
// Exercise the real proc reader: netlink port 345 is reused by a new socket.
$root=sys_get_temp_dir().'/nfqws-socket-'.bin2hex(random_bytes(6));
mkdir($root.'/net/netfilter',0700,true);mkdir($root.'/345/fd',0700,true);
try {
    $real=new AsusReportIO(['proc'=>$root]);$r=new AsusSupportReport($real,new AsusReportValues());
    file_put_contents($root.'/net/netfilter/nfnetlink_queue',"300 345 0 2 65535 0 0 10 1\n");
    file_put_contents($root.'/net/netlink',"sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\n00000000 12 345 00000000 0 0 0 2 0 9001\n");
    symlink('socket:[9001]',$root.'/345/fd/3');$before=$r->queueSample(300,$identity);
    file_put_contents($root.'/net/netfilter/nfnetlink_queue',"300 345 0 2 65535 0 0 80 1\n");
    file_put_contents($root.'/net/netlink',"sk Eth Pid Groups Rmem Wmem Dump Locks Drops Inode\n00000000 12 345 00000000 0 0 0 2 0 9002\n");
    unlink($root.'/345/fd/3');symlink('socket:[9002]',$root.'/345/fd/3');
    reportCheck($r->compareQueue($before,$r->queueSample(300,$identity))['result']==='changed_during_collection','same port new socket cannot prove growth');
    unlink($root.'/345/fd/3');
    $without=$r->queueSample(300,$identity);
    reportCheck($r->compareQueue($without,$without)['result']==='unavailable','missing socket owner evidence stays unconfirmed');
} finally {
    @unlink($root.'/345/fd/3');unlink($root.'/net/netlink');unlink($root.'/net/netfilter/nfnetlink_queue');
    rmdir($root.'/345/fd');rmdir($root.'/345');rmdir($root.'/net/netfilter');rmdir($root.'/net');rmdir($root);
}
$io->files['queue'].=$io->files['queue']; reportCheck($report->queueSample(300,$identity)['state']==='unknown','duplicate');
$io->files['queue']='';reportCheck($report->queueSample(300,$identity)['state']==='unbound','unbound');
$io->files['queue']="300 malformed\n";reportCheck($report->queueSample(300,$identity)['state']==='unknown','malformed');
$io=new ReportFixtureIO(); $io->files['config']="NFQUEUE_NUM=300\n";$io->files['runtime']=$io->files['config'];
$r=(new AsusSupportReport($io,new AsusReportValues()))->collect();
reportCheck($io->time>=110 && $io->time<=125,'ten second gap bounded');
reportCheck($r['schema_version']===1 && $r['complete']===false,'partial base report');
reportCheck(!str_contains(json_encode($r),'_identity')&&!str_contains(json_encode($r),'_binding'),'private identity excluded');
echo "PASS queue/collector\n";
