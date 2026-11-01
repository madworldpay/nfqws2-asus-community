<?php
/** Fixed root-only coordinator. Load action code after the updater lease. */
declare(strict_types=1);
if(!in_array(PHP_SAPI,['cli','cgi-fcgi'],true)||isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))exit(1);
$args=$argv;array_shift($args);if(($args[0]??null)==='--')array_shift($args);$mode=array_shift($args);
if(!in_array($mode,['status','run','preflight'],true)||($mode!=='preflight'&&$args!==[])||$mode==='preflight'&&(count($args)!==2||!preg_match('/^[a-f0-9]{32}$/D',$args[0])||!in_array($args[1],['install','configure'],true)))exit(1);
$shared=null;$exclusive=null;$policy=null;$exit=1;
try{
    if($mode==='run'){
        require_once '/opt/share/nfqws-asus-web/update-guard.php';$updates=new AsusUpdateGuard(new AsusUpdateStore());$t=hrtime();$deadline=(float)$t[0]+$t[1]/1000000000+60;
        do{try{$shared=$updates->mutationLease();break;}catch(Throwable $e){$t=hrtime();if($e->getMessage()!=='busy'||(float)$t[0]+$t[1]/1000000000>=$deadline)throw $e;usleep(100000);}}while(true);
    }
    require_once '/opt/share/nfqws-asus-web/ip-health-sockets.php';$policy=new NfqwsIpHealthSockets();
    if($mode==='status'){$value=$policy->status();$exit=0;}
    elseif($mode==='preflight'){
        // Only the verified fixed native launcher can establish an owned
        // interrupted-unpack boundary. It retains opkg's POSIX lock while this
        // child checks the exact plan and then execs the manager in that PID.
        $status=(string)@file_get_contents('/proc/self/status');if(!preg_match('/^PPid:\s+([0-9]+)/m',$status,$m))throw new RuntimeException('invalid_state');
        $wanted=realpath('/opt/libexec/nfqws2-asus/sockets-launch');$actual=@readlink('/proc/'.$m[1].'/exe');if($wanted===false||$actual!==$wanted)throw new RuntimeException('invalid_state');
        $policy->preflight($args[0],$args[1]);$exit=0;$value=null;
    }else{
        if(!$policy->admitted()){$value=['state'=>'unavailable','code'=>'sockets_not_requested'];$exit=2;}
        else{
            try{$exclusive=$policy->lease();}catch(RuntimeException $e){if($e->getMessage()!=='busy')throw $e;$value=['state'=>'pending','code'=>'busy'];$exit=2;}
            if(is_resource($exclusive)){$prepared=$policy->prepare();$value=$prepared['state']==='ready'?$policy->status():$policy->apply($prepared['id']);$exit=$value['state']==='ready'?0:1;}
        }
    }
}catch(Throwable $e){
    if($mode==='preflight'){$value=null;}
    elseif($policy!==null&&is_resource($exclusive))$value=$policy->failure($e);
    else $value=['state'=>'failed','code'=>$e->getMessage()==='busy'?'busy':'sockets_install_failed'];
}finally{foreach([$exclusive,$shared] as $lease)if(is_resource($lease)){flock($lease,LOCK_UN);fclose($lease);}}
if($value!==null)echo json_encode($value,JSON_THROW_ON_ERROR)."\n";
exit($exit);
