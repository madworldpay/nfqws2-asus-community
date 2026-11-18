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
require $web.'/strategy-picker-custom-samples.php';$settings=NfqwsPlatform::settings();
foreach([$settings['config'],$settings['web_config'],dirname($settings['service'])]as $path)if(!is_dir($path))mkdir($path,0755,true);
if(!$native){mkdir('/opt/libexec/nfqws2-asus',0755,true);copy('/bin/busybox','/opt/libexec/nfqws2-asus/busybox');chmod('/opt/libexec/nfqws2-asus/busybox',0755);}
$service=<<<'SH'
#!/bin/sh
case "$1" in
stop) rm -f /tmp/fixture-service-on; echo stop >> /tmp/fixture-service-actions;;
start) touch /tmp/fixture-service-on; echo start >> /tmp/fixture-service-actions;;
diagnostics) if [ -f /tmp/fixture-service-on ]; then echo '{"process_running":true,"nfqueue":{"state":"bound"}}'; else echo '{"process_running":false,"nfqueue":{"state":"absent"}}'; fi;;
*) exit 2;;
esac
SH;
file_put_contents($settings['service'],$service);chmod($settings['service'],0755);
if($native){file_put_contents($library.'/control.sh',$service);chmod($library.'/control.sh',0755);}
$canary=NfqwsPlatform::run(NfqwsPlatform::serviceCommand('stop'),8);
if($canary['status']!==0)throw new RuntimeException('fixture_service_canary: '.json_encode($canary));
$root=$settings['web_config'].'/strategy-picker';$s=new NfqwsStrategyPickerState($root);
$s->path('state.json');
$config=$settings['config'].'/nfqws2.conf';file_put_contents($config,"NFQWS_ARGS=\"original\"\n");chmod($config,0640);
$cfg=new NfqwsStrategyPickerConfig($s,$config);$original=$cfg->raw();$originalStat=lstat($config);
$resource=$settings['config'].'/keep.list';file_put_contents($resource,"user-resource\n");chmod($resource,0640);$resourceStat=lstat($resource);
$foreignFile=$s->root.'/custom-'.str_repeat('e',32).'-'.str_repeat('f',32).'.json';file_put_contents($foreignFile,'preserve');
$prefix=['/usr/bin/php8-cgi','-n','-d','register_argc_argv=1','-d','max_execution_time=0','-d','max_input_time=0','-q','-f'];
$runtime=$web.'/strategy-picker-runtime.php';file_put_contents('/tmp/custom-guard-foreign.php','<?php while(true)usleep(100000);');
$foreign=proc_open([...$prefix,'/tmp/custom-guard-foreign.php'],
    [0=>['file','/dev/null','r'],1=>['file','/tmp/foreign.log','w'],2=>['file','/tmp/foreign.err','w']],$pipes,'/tmp');
$foreignProof=null;
for($i=0;$i<50;$i++){$foreignProof=NfqwsStrategyPickerRuntime::identity(proc_get_status($foreign)['pid']);if($foreignProof&&in_array('/tmp/custom-guard-foreign.php',$foreignProof['argv'],true))break;usleep(10000);}
if(!$foreignProof)throw new RuntimeException('fixture_foreign_not_ready');
file_put_contents('/tmp/custom-guard-foreign-proof.json',json_encode($foreignProof));
function waitActor($store,$role,$proc,$id){
    for($i=0;$i<100;$i++){
        $p=$store->read('actor-'.$role.'.json');
        if(($p['id']??null)===$id&&NfqwsStrategyPickerRuntime::sameActor($p['identity']??null))return $p['identity'];
        if(!proc_get_status($proc)['running'])throw new RuntimeException($role.'_exited_before_ready');
        usleep(100000);
    }throw new RuntimeException($role.'_not_ready');
}
$rows=[];$work=null;$guard=null;$ownChild=null;
try{
    foreach(['empty','full','child','foreign']as $index=>$stage){
        $id=str_repeat(dechex($index+10),32);$j=$cfg->snapshot(false);$j['id']=$id;$j['state']='running';$j['phase']='measuring_1';
        $j['deadline']=AsusUpdateStore::uptime()+600;$j['custom_hosts']=['example.com'];
        $j['custom_manifest']=['schema_version'=>1,'hosts'=>['example.com'],'dns_context'=>str_repeat('c',64),
            'pins'=>[['host'=>'example.com','answer'=>['8.8.8.8'],'address'=>'8.8.8.8']],
            'policy'=>NfqwsIdna::POLICY,'fingerprint'=>AsusDpiSiteCheckProbe::PINNED_FINGERPRINT];
        $j['custom_manifest_sha256']=hash('sha256',json_encode($j['custom_manifest'],JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR));
        $s->write($j);$cfg->replace("NFQWS_ARGS=\"temporary\"\n");file_put_contents('/tmp/fixture-service-on','on');
        $work=proc_open([...$prefix,'/fixtures/custom-worker.php','--',$web,$root,$id,$stage,$runtime,'--','work',$id],
            [0=>['file','/dev/null','r'],1=>['file','/tmp/work-'.$stage.'.log','w'],2=>['file','/tmp/work-'.$stage.'.err','w']],$pipes);
        $workProof=waitActor($s,'work',$work,$id);
        $guard=proc_open([...$prefix,$runtime,'--','guard',$id],
            [0=>['file','/dev/null','r'],1=>['file','/tmp/guard-'.$stage.'.log','w'],2=>['file','/tmp/guard-'.$stage.'.err','w']],$pipes);
        $guardProof=waitActor($s,'guard',$guard,$id);
        $ready='/tmp/custom-guard-ready-'.$id;
        for($i=0;$i<150&&!is_file($ready);$i++){if(!proc_get_status($work)['running'])throw new RuntimeException('worker_early_exit_'.$stage.': '.substr(file_get_contents('/tmp/work-'.$stage.'.log'),0,3000));usleep(100000);}
        if(!is_file($ready))throw new RuntimeException('fixture_boundary_not_reached_'.$stage);
        $before=$s->read();$beforeConfig=$cfg->raw();clearstatcache(true,$config);$beforeConfigStat=lstat($config);$ownChild=$stage==='child'?($before['actuator']??null):null;
        if($stage==='child'&&!NfqwsStrategyPickerRuntime::sameActor($ownChild))throw new RuntimeException('fixture_child_not_live');
        if(!NfqwsStrategyPickerRuntime::sameActor($workProof))throw new RuntimeException('fixture_parent_not_live');
        proc_terminate($work,9);proc_close($work);$work=null;
        for($i=0;$i<250&&proc_get_status($guard)['running'];$i++)usleep(100000);
        if(proc_get_status($guard)['running'])throw new RuntimeException('fixture_guard_did_not_finish_'.$stage);
        proc_close($guard);$guard=null;$after=$s->read();clearstatcache();
        $meta=lstat($config);$keep=lstat($resource);$foreignAlive=NfqwsStrategyPickerRuntime::sameActor($foreignProof);
        $row=['stage'=>$stage,'state'=>$after['state'],'code'=>$after['code']??null,'restored'=>$after['restored']??null,
            'config_original'=>$cfg->raw()===$original,'config_metadata'=>array_intersect_key($meta,array_flip(['uid','gid','mode']))===array_intersect_key($originalStat,array_flip(['uid','gid','mode'])),
            'resource_unchanged'=>file_get_contents($resource)==="user-resource\n"&&array_intersect_key($keep,array_flip(['uid','gid','mode','ino']))===array_intersect_key($resourceStat,array_flip(['uid','gid','mode','ino'])),
            'config_preserved'=>$cfg->raw()===$beforeConfig&&array_intersect_key($meta,array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']))===array_intersect_key($beforeConfigStat,array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime'])),
            'service_off'=>!is_file('/tmp/fixture-service-on'),'pending'=>$after['custom_sample_pending']??null,
            'descriptor'=>$after['custom_worker']??null,'actuator'=>$after['actuator']??null,
            'sample_files'=>count(glob($s->root.'/custom-'.$id.'-*.json')),'foreign_file_kept'=>file_get_contents($foreignFile)==='preserve',
            'foreign_actor_alive'=>$foreignAlive,'child_terminated'=>$ownChild===null||!NfqwsStrategyPickerRuntime::sameActor($ownChild),
            'work_terminated'=>!NfqwsStrategyPickerRuntime::sameActor($workProof),'guard_terminated'=>!NfqwsStrategyPickerRuntime::sameActor($guardProof)];
        $pass=$row['resource_unchanged']&&$row['foreign_file_kept']&&$row['foreign_actor_alive']&&$row['work_terminated']&&$row['guard_terminated'];
        if($stage==='foreign')$pass=$pass&&$row['state']==='recovery_required'&&$row['restored']===false&&$row['config_preserved']&&!$row['service_off']&&$row['descriptor']===$before['custom_worker']&&$row['actuator']===$before['actuator'];
        else $pass=$pass&&$row['restored']===true&&$row['config_original']&&$row['config_metadata']&&$row['service_off']&&$row['state']==='failed'&&$row['code']==='interrupted'&&$row['pending']===null&&$row['descriptor']===null&&$row['actuator']===null&&$row['sample_files']===0&&$row['child_terminated'];
        $row['passed']=$pass;$rows[]=$row;echo json_encode($row)."\n";flush();
        // Only fixture-owned direct resources are signalled; never broad kill.
        if($ownChild!==null&&NfqwsStrategyPickerRuntime::sameActor($ownChild))posix_kill($ownChild['pid'],9);
        $ownChild=null;
    }
    $passed=!in_array(false,array_column($rows,'passed'),true);
    echo json_encode(['passed'=>$passed,'platform'=>$platform,'cases'=>count($rows)])."\n";$status=$passed?0:1;
}finally{
    foreach([$guard,$work,$foreign]as $proc)if(is_resource($proc)){
        if(proc_get_status($proc)['running']){proc_terminate($proc,9);}proc_close($proc);
    }
    if($ownChild!==null&&NfqwsStrategyPickerRuntime::sameActor($ownChild))posix_kill($ownChild['pid'],9);
    foreach(glob('/tmp/*.err')as $path)if(filesize($path))file_put_contents('php://stderr',basename($path).': '.file_get_contents($path)."\n");
}
exit($status);
