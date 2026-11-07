  // Device-profile experiment: authenticated draft, library and native lifecycle.
  if (in_array($_POST['cmd'], ['deviceprofilesstatus','deviceprofilessave','deviceprofilespreview','deviceprofilesruntime','deviceprofilescapture','deviceprofilesimport','deviceprofilesapply'], true)) {
    require_once __DIR__.'/device-profiles-lab.php';
    require_once __DIR__.'/device-profiles-runtime.php';
    require_once __DIR__.'/support-report.php';
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    $deviceLease=null;
    try {
      $draftCommand=in_array($_POST['cmd'],['deviceprofilesstatus','deviceprofilessave','deviceprofilespreview'],true);
      if($draftCommand)NfqwsDeviceProfilesLab::validateRequest($_POST);else NfqwsDeviceProfilesRuntime::validateRequest($_POST);
      if(!hash_equals($_SESSION['csrf_token'],$_POST['csrf_token'])||!asusReportSameOrigin()){
        http_response_code(403);echo json_encode(['error'=>'csrf_failed']);exit();
      }
      session_write_close();
      if(in_array($_POST['cmd'],['deviceprofilessave','deviceprofilescapture','deviceprofilesimport','deviceprofilesapply'],true)){
        require_once __DIR__.'/update-guard.php';$deviceLease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
      }
      if($_POST['cmd']==='deviceprofilesimport')ini_set('memory_limit','64M');
      $runtime=new NfqwsDeviceProfilesRuntime();
      $value=$draftCommand?(new NfqwsDeviceProfilesLab())->dispatch($_POST):$runtime->dispatch($_POST);
      if(in_array($_POST['cmd'],['deviceprofilesstatus','deviceprofilessave'],true)){
        $value['runtime']=$runtime->status();$value['templates']=array_merge($value['templates'],$value['runtime']['templates']);
      }
      $raw=json_encode($value,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);
      if(strlen($raw)>131072)throw new RuntimeException('storage_unavailable');
      echo $raw;
    }catch(Throwable $e){
      $code=in_array($e->getMessage(),['invalid_request','invalid_draft','stale_revision','busy','storage_unavailable','runtime_unavailable','runtime_limit','library_limit','unresolved_profile_resource','strategy_unavailable','profile_import_incomplete','lua_trust','source_changed'],true)?$e->getMessage():'storage_unavailable';
      http_response_code(in_array($code,['stale_revision','busy'],true)?409:($code==='storage_unavailable'?503:400));
      echo json_encode(['error'=>$code]);
    }finally{if(is_resource($deviceLease)){flock($deviceLease,LOCK_UN);fclose($deviceLease);}}
    exit();
  }
