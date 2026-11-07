  // Device-profile experiment: draft storage and read-only preview only.
  if (in_array($_POST['cmd'], ['deviceprofilesstatus','deviceprofilessave','deviceprofilespreview'], true)) {
    require_once __DIR__.'/device-profiles-lab.php';
    require_once __DIR__.'/support-report.php';
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    try {
      NfqwsDeviceProfilesLab::validateRequest($_POST);
      if(!hash_equals($_SESSION['csrf_token'],$_POST['csrf_token'])||!asusReportSameOrigin()){
        http_response_code(403);echo json_encode(['error'=>'csrf_failed']);exit();
      }
      session_write_close();
      $value=(new NfqwsDeviceProfilesLab())->dispatch($_POST);
      $raw=json_encode($value,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);
      if(strlen($raw)>131072)throw new RuntimeException('storage_unavailable');
      echo $raw;
    }catch(Throwable $e){
      $code=in_array($e->getMessage(),['invalid_request','invalid_draft','stale_revision','busy','storage_unavailable'],true)?$e->getMessage():'storage_unavailable';
      http_response_code(in_array($code,['stale_revision','busy'],true)?409:($code==='storage_unavailable'?503:400));
      echo json_encode(['error'=>$code]);
    }
    exit();
  }
