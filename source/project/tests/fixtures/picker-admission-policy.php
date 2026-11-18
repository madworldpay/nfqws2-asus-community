<?php
if(in_array('native-default',$argv??[],true)){
 $package='/tmp/native-admission-package';mkdir($package,0755);
 foreach(['strategy-picker-admission.php','platform.php']as $name){copy(dirname(__DIR__,2).'/webui/web/public/'.$name,$package.'/'.$name);chmod($package.'/'.$name,0644);}
 file_put_contents($package.'/platform-profile.json',json_encode(['schema_version'=>1,'platform'=>'openwrt']));chmod($package.'/platform-profile.json',0644);
 require $package.'/strategy-picker-admission.php';
}else require dirname(__DIR__,2).'/webui/web/public/strategy-picker-admission.php';
function yes($v,$s){if(!$v)throw new RuntimeException($s);}
function denied(callable $fn,string $reason=''){try{$fn();throw new RuntimeException('unexpected_acceptance');}catch(Throwable $e){if($e->getMessage()==='unexpected_acceptance'||$reason!==''&&$e->getMessage()!==$reason)throw $e;}}
$a=new NfqwsStrategyPickerAdmission('/tmp/admission-unit');$scope=bin2hex(random_bytes(16));$sel=str_repeat('a',64);$plan=str_repeat('b',64);$count=0;
function makeReq(){global $a,$scope,$sel,$plan; $id=bin2hex(random_bytes(16));$a->prepare($id,$scope,$sel,$plan);return $id;}
if(in_array('native-default',$argv??[],true)){
 if(!is_dir('/etc/nfqws2-web'))mkdir('/etc/nfqws2-web',0700);$native=new NfqwsStrategyPickerAdmission();$id=bin2hex(random_bytes(16));
 yes(NfqwsPlatform::current()==='openwrt'&&$native->enter($id,$sel,null)===null,'native_default_profile');
 $native->prepare($id,$scope,$sel,$plan);yes(is_file('/etc/nfqws2-web/picker-admission/'.$id.'/record.json'),'native_default_path');
 $lease=$native->enter($id,$sel,$plan);$lease->release();yes($native->revoke($id,$scope)['closed'],'native_default_not_closed');
 echo json_encode(['passed'=>true,'assertions'=>3,'profile'=>'openwrt'])."\n";exit(0);
}
if(in_array('opt-alias',$argv??[],true)){
 require_once dirname(__DIR__,2).'/webui/web/public/platform.php';
 yes(is_link('/opt')&&realpath('/opt')==='/tmp/mnt/admission-fixture/entware','fixture_opt_alias_not_ready');
 $managed=new NfqwsStrategyPickerAdmission();$id=bin2hex(random_bytes(16));
 yes($managed->enter($id,$sel,null)===null,'unmanaged_alias_changed');
 $managed->prepare($id,$scope,$sel,$plan);$lease=$managed->enter($id,$sel,$plan);$lease->release();
 yes($managed->revoke($id,$scope)['closed'],'alias_not_closed');denied(fn()=>$managed->enter($id,$sel,$plan),'admission_closed');
 $root='/tmp/mnt/admission-fixture/entware/etc/nfqws-asus-web/picker-admission';rename($root,$root.'.original');symlink($root.'.original',$root);
 denied(fn()=>(new NfqwsStrategyPickerAdmission())->enter(bin2hex(random_bytes(16)),$sel,null),'invalid_admission');
 echo json_encode(['passed'=>true,'assertions'=>4,'firmware_alias_verified'=>true])."\n";exit(0);
}
if(in_array('pid1',$argv??[],true)){
 yes(getmypid()===1,'fixture_not_PID1');$id=makeReq();$path='/tmp/admission-unit/'.$id.'/record.json';$before=hash_file('sha256',$path);
 denied(fn()=>$a->enter($id,$sel,$plan),'invalid_admission');
 yes(hash_file('sha256',$path)===$before&&!glob('/tmp/admission-unit/'.$id.'/handler-*.json'),'PID1_changed_registry');
 echo json_encode(['passed'=>true,'assertions'=>2,'PID'=>getmypid()])."\n";exit(0);
}
yes($a->enter(bin2hex(random_bytes(16)),$sel,null)===null,'unmanaged_compat');$count++;
$id=makeReq();denied(fn()=>$a->prepare($id,$scope,$sel,$plan),'admission_exists');$count++;
denied(fn()=>$a->enter($id,str_repeat('c',64),$plan),'admission_mismatch');$count++;
denied(fn()=>$a->enter($id,$sel,str_repeat('c',64)),'admission_mismatch');$count++;
denied(fn()=>$a->enter($id,$sel,null),'admission_mismatch');$count++;
denied(fn()=>$a->revoke($id,bin2hex(random_bytes(16))),'admission_mismatch');yes(!is_file('/tmp/admission-unit/'.$id.'/revoked.json'),'foreign_scope_mutated');$count++;
$l=$a->enter($id,$sel,$plan);yes($l!==null,'valid_enter');$count++;$c=$a->candidates($id,$scope);yes(count($c)===1&&$c[0]===NfqwsStrategyPickerAdmission::identity(getmypid()),'full_identity');$count++;
$r=$a->revoke($id,$scope);yes(!$r['closed'],'busy_falsely_closed');$count++;$l->accepted(str_repeat('d',32));$l->release();$r=$a->revoke($id,$scope);yes($r['closed']&&$r['record']['job_id']===str_repeat('d',32),'accepted_job_lost');$count++;
denied(fn()=>$a->enter($id,$sel,$plan),'admission_closed');$count++;
yes($a->revoke($id,$scope)['closed'],'idempotent_close');$count++;
foreach(['unknown','bad_boot','bad_time','bad_type','bad_handler','bad_mode','hardlink','symlink','bad_json']as $case){$id=makeReq();$path='/tmp/admission-unit/'.$id.'/record.json';$v=json_decode(file_get_contents($path),true);
 switch($case){case'unknown':$v['extra']=1;break;case'bad_boot':$v['boot']=str_repeat('f',36);break;case'bad_time':$v['expires']=$v['created']+61;break;case'bad_type':$v['expires']='123';break;case'bad_handler':$v['handler']=['pid'=>1];break;}
 if(in_array($case,['bad_mode','hardlink','symlink','bad_json'],true)){
  if($case==='bad_mode')chmod($path,0644);
  if($case==='hardlink')link($path,$path.'.link');
  if($case==='symlink'){rename($path,$path.'.real');symlink($path.'.real',$path);}
  if($case==='bad_json')file_put_contents($path,'{');
 }else file_put_contents($path,json_encode($v));
 denied(fn()=>$a->enter($id,$sel,$plan));$count++;
}
$id=bin2hex(random_bytes(16));$a->prepare($id,$scope,$sel,$plan,1);usleep(1050000);denied(fn()=>$a->enter($id,$sel,$plan),'admission_closed');$count++;
foreach([0,61,true,'30',30.0,null]as $ttl){denied(fn()=>$a->prepare(bin2hex(random_bytes(16)),$scope,$sel,$plan,$ttl),'invalid_admission');$count++;}
$id=makeReq();$l=$a->enter($id,$sel,$plan);$actor=NfqwsStrategyPickerAdmission::identity(getmypid());$candidate='/tmp/admission-unit/'.$id.'/handler-'.$actor['pid'].'-'.$actor['ticks'].'.json';$foreign='{"unknown":"preserve"}';file_put_contents($candidate,$foreign);denied(fn()=>$l->release(),'invalid_admission');yes(file_get_contents($candidate)===$foreign,'foreign_candidate_deleted');$count++;
echo json_encode(['passed'=>true,'assertions'=>$count])."\n";
