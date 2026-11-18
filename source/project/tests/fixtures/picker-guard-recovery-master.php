<?php
umask(0077);$platform=$argv[1]??'';
if(!in_array($platform,['asus-entware','openwrt'],true))throw new RuntimeException('fixture_platform');
$native=$platform==='openwrt';$web=$native?'/usr/share/nfqws2-web':'/opt/share/nfqws-asus-web';
$library=$native?'/usr/lib/nfqws2':'/opt/lib/nfqws2-asus';
foreach([$web,$library]as $path)if(!is_dir($path))mkdir($path,0755,true);
foreach(new RecursiveIteratorIterator(new RecursiveDirectoryIterator('/fixture-web',FilesystemIterator::SKIP_DOTS),RecursiveIteratorIterator::SELF_FIRST)as $file){
    $dest=$web.'/'.substr($file->getPathname(),strlen('/fixture-web/'));
    if($file->isDir()){if(!is_dir($dest))mkdir($dest,0755);}
    elseif($file->isFile()&&!$file->isLink()){copy($file->getPathname(),$dest);chmod($dest,0644);}
    else throw new RuntimeException('fixture_source_type');
}
copy('/fixtures/config.php',$library.'/config.php');chmod($library.'/config.php',0644);
if($native){file_put_contents($web.'/platform-profile.json',"{\"schema_version\":1,\"platform\":\"openwrt\"}\n");chmod($web.'/platform-profile.json',0644);}
require $web.'/strategy-picker-runtime.php';
$settings=NfqwsPlatform::settings();
foreach([$settings['config'],$settings['web_config']]as $path)if(!is_dir($path))mkdir($path,0755,true);
$id=str_repeat('a',32);$root=$settings['web_config'].'/strategy-picker';$s=new NfqwsStrategyPickerState($root);
$s->write(['id'=>$id,'state'=>'running','phase'=>'discovering','profiles'=>[],'deadline'=>AsusUpdateStore::uptime()+600]);
$prefix=['/usr/bin/php8-cgi','-n','-d','register_argc_argv=1','-d','max_execution_time=0','-d','max_input_time=0','-q','-f'];
$runtime=$web.'/strategy-picker-runtime.php';$work=null;$guard=null;$events=[];
function event($name,$value=[]){global $events;$row=['event'=>$name,'uptime'=>AsusUpdateStore::uptime()]+$value;$events[]=$row;echo json_encode($row)."\n";flush();}
function awaitActor($s,$role,$proc){
    for($i=0;$i<50;$i++){
        $record=$s->read('actor-'.$role.'.json');
        if($record&&NfqwsStrategyPickerRuntime::sameActor($record['identity']??null))return $record;
        if(!proc_get_status($proc)['running'])throw new RuntimeException($role.'_exited_before_ready');
        usleep(100000);
    }throw new RuntimeException($role.'_not_ready');
}
try{
    $work=proc_open([...$prefix,'/fixtures/worker.php','--',$web,$root,$runtime,'--','work',$id],
        [0=>['file','/dev/null','r'],1=>['file','/tmp/worker.log','w'],2=>['file','/tmp/worker.err','w']],$pipes);
    $actor=awaitActor($s,'work',$work);
    $guard=proc_open([...$prefix,$runtime,'--','guard',$id],
        [0=>['file','/dev/null','r'],1=>['file','/tmp/guard.log','w'],2=>['file','/tmp/guard.err','w']],$pipes);
    awaitActor($s,'guard',$guard);event('both_ready',['platform'=>$platform]);
    if(($s->read()['state']??null)!=='running')throw new RuntimeException('initial_state_not_running');
    $before=$s->read();$invalid=$actor;$invalid['identity']['ticks']='0';$s->write($invalid,'actor-work.json');$start=AsusUpdateStore::uptime();
    // This is an unknown LIVE context, not an absent worker. Recovery must
    // preserve it immediately instead of starting an absence/retry window.
    for($i=0;$i<60&&proc_get_status($guard)['running'];$i++)usleep(100000);
    $j=$s->read();$failure=$s->read('failure-guard.json');
    if($j['state']!=='recovery_required'||($j['code']??null)!=='recovery_required'||proc_get_status($guard)['running']||
        !NfqwsStrategyPickerRuntime::sameActor($actor['identity'])||($j['restored']??false)!==false||
        $s->read('actor-work.json')!==$invalid||($failure['code']??null)!=='recovery_required')
        throw new RuntimeException('unknown_live_context_must_be_preserved_without_signals');
    event('unknown_live_context_preserved',['seconds'=>AsusUpdateStore::uptime()-$start,'work_still_alive'=>true,'code'=>$j['code'],'restored'=>false]);
    echo json_encode(['passed'=>true,'platform'=>$platform,'events'=>$events])."\n";
}finally{
    foreach([$guard,$work]as $proc)if(is_resource($proc)){
        if(proc_get_status($proc)['running']){proc_terminate($proc);usleep(100000);if(proc_get_status($proc)['running'])proc_terminate($proc,9);}
        proc_close($proc);
    }
    foreach(['/tmp/worker.err','/tmp/guard.err']as $path)if(is_file($path)&&filesize($path))file_put_contents('php://stderr',basename($path).": ".file_get_contents($path)."\n");
}
