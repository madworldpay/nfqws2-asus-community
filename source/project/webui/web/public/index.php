<?php

ini_set('memory_limit', '32M');
require_once __DIR__ . '/asus.php';
require_once __DIR__ . '/ark.php';

define('NFQWS2', true);
define('ROOT_DIR', '/opt');
const SCRIPT_NAME = 'S51nfqws2';
const CONF_DIR = NFQWS2 ? '/etc/nfqws2' : '/etc/nfqws';
const LISTS_DIR = NFQWS2 ? '/etc/nfqws2/lists' : '/etc/nfqws';
const LOGS_DIR = '/var/log';
const LUA_DIR = '/etc/nfqws2/lua';

/** Same writer boundary as JSON imports; errors never expose private paths. */
function asusPanelWrite(callable $fn): mixed
{
  require_once __DIR__.'/import-transaction.php';
  try {$tx=new AsusImportTransaction();return $tx->writer(function()use($tx,$fn){$tx->recover();return $fn();});}
  catch(Throwable $e){$code=in_array($e->getMessage(),['busy','restore_required','source_changed'],true)?$e->getMessage():'invalid_state';header('Content-Type: application/json; charset=utf-8');http_response_code($code==='invalid_state'?503:409);echo json_encode(['error'=>$code]);exit();}
}

function normalizeString(string $s): string
{
  // Convert all line-endings to UNIX format.
  $s = str_replace(array("\r\n", "\r", "\n"), "\n", $s);

  // Don't allow out-of-control blank lines.
  $s = preg_replace("/\n{3,}/", "\n\n", $s);

  $lastChar = substr($s, -1);
  if ($lastChar !== "\n" && !empty($s)) {
    $s .= "\n";
  }

  return $s;
}

function baseFileName(string $filename): string
{
  $filename = basename($filename);
  if (str_ends_with($filename, '.gz')) {
    $filename = substr($filename, 0, -3);
  }
  return $filename;
}

function getFilePath(string $filename): string
{
  $filename = baseFileName($filename);
  if (preg_match('/\.(list|list-opkg|list-old)$/i', $filename)) {
    $path = ROOT_DIR . LISTS_DIR . '/' . basename($filename);
  } else if (preg_match('/\.log$/i', $filename)) {
    $path = ROOT_DIR . LOGS_DIR . '/' . basename($filename);
  } else if (preg_match('/\.lua$/i', $filename)) {
    $path = ROOT_DIR . LUA_DIR . '/' . basename($filename);
  } else {
    $path = ROOT_DIR . CONF_DIR . '/' . basename($filename);
  }
  return $path;
}

function getFiles(?string $type = null): array
{
  function getSortPriority(string $filename): int
  {
    $priority = [
      'nfqws2.conf' => -81,
      'nfqws.conf' => -80,
      'user.list' => -64,
      'exclude.list' => -63,
      'auto.list' => -62,
      'ipset.list' => -61,
      'ipset_exclude.list' => -60,
      'nfqws2.log' => -11,
      'nfqws.log' => -10,
      'nfqws2-debug.log' => -9,
      'nfqws-debug.log' => -8,
    ];

    if (array_key_exists($filename, $priority)) {
      return $priority[$filename];
    }
    if (str_ends_with($filename, '.conf')) {
      return -70;
    }
    if (str_ends_with($filename, '.list')) {
      return -50;
    }
    if (str_ends_with($filename, '.lua')) {
      return -30;
    }
    if (str_ends_with($filename, '.log')) {
      return 0;
    }
    return 10;
  }

  $result = [];

  if (empty($type) || $type == 'conf') {
    // GLOB_BRACE is unsupported in openwrt
    $confs = array_filter(glob(ROOT_DIR . CONF_DIR . '/*'), function ($file) {
      return is_file($file) && preg_match('/\.(conf|conf-opkg|conf-old|apk-new)$/i', $file);
    });
    $baseConfs = array_map(fn($file) => baseFileName($file), $confs);
    $result = array_merge($result, $baseConfs);
  }

  if (empty($type) || $type == 'list') {
    // GLOB_BRACE is unsupported in openwrt
    $lists = array_filter(glob(ROOT_DIR . LISTS_DIR . '/*'), function ($file) {
      return is_file($file) && preg_match('/\.(list|list\.gz|list-opkg|list-old)$/i', $file);
    });
    $baseLists = array_map(fn($file) => baseFileName($file), $lists);
    $result = array_merge($result, $baseLists);
  }

  if (empty($type) || $type == 'log') {
    // GLOB_BRACE is unsupported in openwrt
    $logs = array_filter(glob(ROOT_DIR . LOGS_DIR . '/nfqws*'), function ($file) {
      return is_file($file) && preg_match('/\.log$/i', $file);
    });
    $baseLogs = array_map(fn($file) => baseFileName($file), $logs);
    $result = array_merge($result, $baseLogs);
  }

  if (NFQWS2 && empty($type) || $type == 'lua') {
    // GLOB_BRACE is unsupported in openwrt
    $luas = array_filter(glob(ROOT_DIR . LUA_DIR . '/*'), function ($file) {
      return is_file($file) && preg_match('/\.(lua|lua\.gz)$/i', $file);
    });
    $baseLuas = array_map(fn($file) => baseFileName($file), $luas);
    $result = array_merge($result, $baseLuas);
  }

  usort($result, fn($a, $b) => getSortPriority($a) - getSortPriority($b));

  return $result;
}

function getFileContent(string $filename): string
{
  $path = getFilePath($filename);

  if (file_exists($path)) {
    return file_get_contents($path);
  } else if (file_exists($path . '.gz')) {
    return file_get_contents('compress.zlib://' . $path . '.gz');
  }
  return '';
}

function getLogContent(string $filename): string
{
  $filename = baseFileName($filename);
  $file = file(ROOT_DIR . LOGS_DIR . '/' . $filename);
  $file = array_reverse($file);
  return implode("", $file);
}

function createFile(string $filename): bool
{
  $base = baseFileName($filename);
  $stem = pathinfo($base, PATHINFO_FILENAME);
  if ($base === '' || $base === '.' || $base === '..' || trim($stem) === '') {
    return false;
  }
  if (!preg_match('/^[a-zA-Z0-9_-]+$/', $stem)) {
    return false;
  }
  $path = getFilePath($filename);
  if (file_exists($path)) {
    return false;
  }
  return file_put_contents($path, '') !== false;
}

function saveFile(string $filename, string $content): bool
{
  $path = getFilePath($filename);
  return file_put_contents($path, normalizeString($content)) !== false;
}

function removeFile(string $filename): bool
{
  $path = getFilePath($filename);
  if (file_exists($path)) {
    return unlink($path);
  } else {
    return false;
  }
}

/** Cheap runtime check only; polling status must not dump NVRAM. */
function nfqwsArkLoaded(): ?bool
{
  if (is_dir('/sys/module/ark')) return true;
  if (!is_readable('/sys/module') || !is_executable('/sys/module')) return null;
  $modules = @file_get_contents('/proc/modules', false, null, 0, 262145);
  if ($modules === false || strlen($modules) > 262144) return null;
  return preg_match('/^ark[ \t]/m', $modules) === 1;
}

function nfqwsServiceStatus(): array
{
  $output = null;
  $path = ROOT_DIR . "/etc/init.d/" . SCRIPT_NAME;
  if (!file_exists($path)) {
    return array('service' => false, 'status' => 1);
  }

  exec($path . " status", $output);
  $running = str_contains($output[0] ?? '', 'is running');
  return array('service' => $running, 'status' => 0);
}

function nfqwsServiceAction(string $action): array
{
  $output = null;
  $retval = null;
  exec(ROOT_DIR . "/etc/init.d/" . SCRIPT_NAME . " $action 2>&1", $output, $retval);
  return array('output' => $output, 'status' => $retval);
}

function nfqwsInstalledVersion(): string
{
  $output = [];
  exec("opkg status nfqws2-asus | awk -F': ' '/^Version:/ {print $2}'", $output);
  return $output[0] ?? '';
}

function upgradeAction(): array
{
  return asusUpgradeResponse();
}

function main(): void
{
  if (!isset($_SERVER['REQUEST_METHOD']) || $_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(302);
    header('Location: index.html');
    exit();
  }

  if (!is_string($_POST['cmd'] ?? null)) {
    http_response_code(400);
    exit();
  }

  $auth = asusWebReadAuth();
  if ($auth === null) {
    http_response_code(503);
    exit();
  }
  $authEnabled = $auth['mode'] === 'system' || $auth['password_hash'] !== '';

  ini_set('session.use_strict_mode', '1');
  session_name('nfqws_asus_session');
  session_set_cookie_params(['httponly' => true, 'samesite' => 'Strict']);
  session_start();
  $sessionValid = ($_SESSION['auth'] ?? false) &&
    hash_equals($auth['revision'], $_SESSION['auth_revision'] ?? '');
  if ($authEnabled && !$sessionValid) {
    if ($_POST['cmd'] !== 'login' || !is_string($_POST['user'] ?? null) ||
        !is_string($_POST['password'] ?? null) || !asusWebAuthenticate($_POST['user'], $_POST['password'], $auth)) {
      http_response_code(401);
      exit();
    } else {
      session_regenerate_id(true);
      $_SESSION['auth'] = true;
      $_SESSION['auth_revision'] = $auth['revision'];
      $_SESSION['auth_username'] = $_POST['user'];
    }
  }
  if (!isset($_SESSION['csrf_token'])) $_SESSION['csrf_token'] = bin2hex(random_bytes(32));

  if (in_array($_POST['cmd'], ['packageupdatecheck','packageupdateprepare','packageupdateapply','packageupdatestatus'], true)) {
    header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
    if ($authEnabled && !$sessionValid) {http_response_code(403);echo json_encode(['error'=>'auth_required']);exit();}
    require_once __DIR__.'/update-api.php';require_once __DIR__.'/support-report.php';
    try {
      AsusUpdateApi::validate($_POST);
      if (!hash_equals($_SESSION['csrf_token'], $_POST['csrf_token']) || !asusReportSameOrigin()) {http_response_code(403);echo json_encode(['error'=>'csrf_failed']);exit();}
      session_write_close();$value=AsusUpdateApi::dispatch($_POST);$raw=json_encode($value,JSON_THROW_ON_ERROR);
      if (strlen($raw)>32768) throw new RuntimeException('output_limit');http_response_code(200);echo $raw;
    } catch (Throwable $e) {
      $code=AsusUpdatePrepare::code($e);http_response_code(in_array($code,['invalid_request','consent_required'],true)?400:(in_array($code,['busy','request_conflict','stale_revision'],true)?409:503));echo json_encode(['error'=>$code]);
    }
    exit();
  }

  $requiredParams = array(
    'filecontent' => array('filename'),
    'filecreate' => array('filename'),
    'filesave' => array('filename', 'content'),
    'fileremove' => array('filename'),
    'password' => array('password', 'confirmation', 'csrf_token'),
    'arkprepare' => array('csrf_token', 'revision'),
    'arkrestore' => array('csrf_token', 'revision'),
    'supportreport' => array('csrf_token'),
    'supportmailstatus' => array('csrf_token'),
    'supportsend' => array('csrf_token', 'consent', 'filename', 'report', 'report_proof', 'submission_id'),
  );
  foreach ($requiredParams[$_POST['cmd']] ?? array() as $param) {
    if (!is_string($_POST[$param] ?? null)) {
      http_response_code(400);
      exit();
    }
  }

  $mutationLease = null;
  $updaterMutations = ['filecreate','filesave','fileremove','password','arkprepare','arkrestore','start','stop','restart','upgrade','dpiinstall','dpistart','dpistop','dpidelete','sharesavedrefresh','sharesaveddelete','smartdnsinstall'];
  if (in_array($_POST['cmd'], $updaterMutations, true) || ($_POST['cmd']==='dpipreferences' && ($_POST['action']??null)!=='read')) {
    require_once __DIR__.'/update-guard.php';
    try {$mutationLease=(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();}
    catch (Throwable $e) {
      $code=$e->getMessage()==='busy'?'busy':'invalid_state';header('Content-Type: application/json; charset=utf-8');http_response_code($code==='busy'?409:503);echo json_encode(['error'=>$code]);exit();
    }
  }

  if (in_array($_POST['cmd'], ['importinspect','importprepare','importapply','importstatus','importundo'], true)) {
    require_once __DIR__.'/support-report.php';require_once __DIR__.'/import-api.php';
    header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
    try {
      AsusImportApi::validate($_POST);
      if(!hash_equals($_SESSION['csrf_token'],$_POST['csrf_token'])||!asusReportSameOrigin()){http_response_code(403);echo json_encode(['error'=>'csrf_failed']);exit();}
      if(!isset($_SESSION['import_key']))$_SESSION['import_key']=bin2hex(random_bytes(32));
      $key=$_SESSION['import_key'];session_write_close();$result=(new AsusImportApi())->handle($_POST,$key,time());
      $raw=json_encode($result,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);if(strlen($raw)>4194304)throw new RuntimeException('output_limit');http_response_code(200);echo $raw;
    }catch(Throwable $e){$code=AsusImportApi::error($e);http_response_code($code==='invalid_proof'?403:(in_array($code,['busy','source_changed','stale_preview','stale_state','stale_draft','request_conflict','restore_required'],true)?409:400));echo json_encode(['error'=>$code]);}
    exit();
  }

  if (in_array($_POST['cmd'], ['routercheckup','wanaddresses','smartdnsconfigstatus','smartdnsdraft','smartdnsvalidate','smartdnspreview','smartdnsapply','smartdnsconfirm','smartdnsrollback'], true)) {
    require_once __DIR__.'/support-report.php';require_once __DIR__.'/smartdns-config-api.php';
    header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
    try {
      AsusSmartDnsConfigApi::validate($_POST);
      if(!hash_equals($_SESSION['csrf_token'],$_POST['csrf_token'])||!asusReportSameOrigin()){http_response_code(403);echo json_encode(['error'=>'csrf_failed']);exit();}
      session_write_close();$result=AsusSmartDnsConfigApi::dispatch($_POST);
      $raw=json_encode($result,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);if(strlen($raw)>524288)throw new RuntimeException('output_limit');
      http_response_code(200);echo $raw;
    }catch(Throwable $e){
      $error=AsusSmartDnsConfigApi::error($e);$code=$error['error'];
      http_response_code(in_array($code,['invalid_request','invalid_profile'],true)?400:(in_array($code,['busy','stale_draft','stale_preview','stale_baseline','stale_state','request_conflict','restore_required'],true)?409:503));
      echo json_encode($error);
    }
    exit();
  }

  if (in_array($_POST['cmd'], ['smartdnsstatus','smartdnsinstall'], true)) {
    require_once __DIR__.'/support-report.php';require_once __DIR__.'/smartdns-api.php';
    header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
    try {
      AsusSmartDnsApi::validate($_POST);
      if(!hash_equals($_SESSION['csrf_token'],$_POST['csrf_token'])||!asusReportSameOrigin()){http_response_code(403);echo json_encode(['error'=>'csrf_failed']);exit();}
      session_write_close();$result=AsusSmartDnsApi::dispatch($_POST);http_response_code(200);echo json_encode($result,JSON_THROW_ON_ERROR);
    }catch(Throwable $e){$code=AsusSmartDnsInstaller::code($e->getMessage());http_response_code($code==='busy'?409:(in_array($code,['invalid_request','consent_required'],true)?400:503));echo json_encode(['error'=>$code]);}
    exit();
  }

  if (in_array($_POST['cmd'], ['sharestates','sharesavedrefresh','sharesavedread','sharesaveddelete','sharestrategydraft','shareinventory','sharednssources','shareresourceread','shareanalyze','shareprepare','sharesend','sharelocation'], true)) {
    require_once __DIR__.'/support-report.php';require_once __DIR__.'/share-api.php';
    header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
    try {
      AsusShareApi::validate($_POST);
      if(!hash_equals($_SESSION['csrf_token'],$_POST['csrf_token'])||!asusReportSameOrigin()){http_response_code(403);echo json_encode(['error'=>'csrf_failed']);exit();}
      if(!isset($_SESSION['support_report_key']))$_SESSION['support_report_key']=bin2hex(random_bytes(32));
      $key=$_SESSION['support_report_key'];session_write_close();
      $result=(new AsusShareApi())->handle($_POST,$key,time());
      if($_POST['cmd']==='sharesend'){$statuses=['accepted'=>200,'failed_safe'=>503,'unknown'=>503,'busy'=>409,'limited'=>429,'invalid'=>422];http_response_code(($result['code']??'')==='id_conflict'?409:($statuses[$result['state']]??503));}else http_response_code(200);
      $raw=json_encode($result,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);if(strlen($raw)>($_POST['cmd']==='sharesavedread'?8388608:($_POST['cmd']==='shareprepare'?4194304:2097152)))throw new RuntimeException('output_limit');echo $raw;
    }catch(Throwable $e){
      $code=in_array($e->getMessage(),['invalid_request','invalid_proof','invalid_strategy','unsafe_strategy','unsupported_config','strategy_unavailable','invalid_share','unsupported_report','result_unavailable','source_changed','invalid_state','output_limit','insufficient_space','invalid_resource','invalid_dns_resource','private_dns_url','incomplete_reason_required','file_too_large','resource_unavailable'],true)?$e->getMessage():'unavailable';
      http_response_code($code==='invalid_proof'?403:(in_array($code,['source_changed'],true)?409:(in_array($code,['invalid_request','invalid_strategy','unsafe_strategy','unsupported_config','invalid_share','invalid_resource','invalid_dns_resource','private_dns_url','incomplete_reason_required','file_too_large'],true)?400:503)));echo json_encode(['error'=>$code]);
    }
    exit();
  }

  if (in_array($_POST['cmd'], ['supportbundleprepare','supportbundlesend'], true)) {
    require_once __DIR__.'/support-report.php';require_once __DIR__.'/support-bundle.php';require_once __DIR__.'/support-mail.php';
    header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
    $isSending=$_POST['cmd']==='supportbundlesend';
    $expected=$isSending?['cmd','csrf_token','envelope','proof','submission_id','consent']:['cmd','csrf_token','report','filename','report_proof','job_id'];sort($expected);$keys=array_keys($_POST);sort($keys);
    if($keys!==$expected){http_response_code(400);exit();}
    foreach($_POST as $v)if(!is_string($v)){http_response_code(400);exit();}
    if(!hash_equals($_SESSION['csrf_token'],$_POST['csrf_token'])||!asusReportSameOrigin()){http_response_code(403);exit();}
    $key=$_SESSION['support_report_key']??'';session_write_close();
    try {
      if($isSending){
        if($_POST['consent']!=='send')throw new RuntimeException('invalid_request');
        $envelope=AsusSupportBundle::envelope($_POST['envelope'],$_POST['submission_id']);
        if(!AsusSupportBundle::verify($_POST['proof'],$envelope['files'],$key,time())){http_response_code(403);exit();}
        $result=(new AsusSupportMail())->sendBundle($_POST['envelope'],$_POST['submission_id']);
        $codes=['accepted'=>200,'failed_safe'=>503,'unknown'=>503,'busy'=>409,'limited'=>429,'invalid'=>422];http_response_code($result['code']==='id_conflict'?409:($codes[$result['state']]??503));echo json_encode($result);
      }else{
        $result=(new AsusSupportBundle())->prepare($_POST['report'],$_POST['filename'],$_POST['report_proof'],$_POST['job_id'],$key,time());
        http_response_code(200);echo json_encode($result,JSON_THROW_ON_ERROR);
      }
    }catch(Throwable $e){http_response_code($e->getMessage()==='invalid_proof'?403:400);echo json_encode(['error'=>'invalid_bundle']);}
    exit();
  }

  if (in_array($_POST['cmd'], ['dpistatus','dpiinstall','dpistart','dpistop','dpiresult','dpidelete','dpimetadata','dpinative','dpipreferences'], true)) {
    require_once __DIR__.'/support-report.php';
    require_once __DIR__.'/dpi-api.php';
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    try {
      AsusDpiApi::validate($_POST);
      if (!hash_equals($_SESSION['csrf_token'], $_POST['csrf_token']) || !asusReportSameOrigin()) {http_response_code(403);exit();}
      session_write_close();
      $dpiResponse=AsusDpiApi::dispatch($_POST);
      if (is_string($dpiResponse)) {
        $dpiValue=json_decode($dpiResponse,true,32,JSON_THROW_ON_ERROR);
        $dpiTime=strtotime($dpiValue['started_at']);
        header('Content-Disposition: attachment; filename="'.($_POST['cmd']==='dpinative'?'NFQWS2_DPI_NATIVE_':'NFQWS2_DPI_').gmdate('Y-m-d_H-i-s',$dpiTime).'Z.json"');
        http_response_code(200);echo $dpiResponse;
      } else {
        $dpiJson=json_encode($dpiResponse,JSON_THROW_ON_ERROR);
        if(strlen($dpiJson)>($_POST['cmd']==='dpimetadata'||$_POST['cmd']==='dpipreferences'?131072:16384))throw new RuntimeException('invalid_state');
        http_response_code(200);echo $dpiJson;
      }
    } catch(Throwable $e) {
      $dpiField=null;if(str_starts_with($e->getMessage(),'invalid_options:')){$dpiCode='invalid_options';$field=substr($e->getMessage(),16);$dpiField=preg_match('/^[a-zA-Z0-9_.]{1,100}$/D',$field)?$field:'settings';}else $dpiCode=$e->getMessage()==='workflow_changed'?'workflow_changed':AsusDpiJobs::code($e->getMessage());
      http_response_code($dpiCode==='workflow_changed'?410:(in_array($dpiCode,['invalid_request','consent_required','invalid_options'],true)?400:(in_array($dpiCode,['busy','request_conflict'],true)?409:503)));
      echo json_encode(['error'=>$dpiCode,'field'=>$dpiField]);
    }
    exit();
  }

  switch ($_POST['cmd']) {
    case 'supportmailstatus':
    case 'supportsend':
      require_once __DIR__ . '/support-report.php';
      require_once __DIR__ . '/support-mail-proof.php';
      require_once __DIR__ . '/support-mail.php';
      $keys = array_keys($_POST); sort($keys);
      $mailSending = $_POST['cmd'] === 'supportsend';
      $expected = $mailSending ? ['cmd','consent','csrf_token','filename','report','report_proof','submission_id'] : ['cmd','csrf_token'];
      if ($keys !== $expected) { http_response_code(400); exit(); }
      if (!hash_equals($_SESSION['csrf_token'], $_POST['csrf_token']) || !asusReportSameOrigin()) {
        http_response_code(403); exit();
      }
      if ($mailSending) {
        if ($_POST['consent'] !== 'send' || strlen($_POST['report']) === 0 || strlen($_POST['report']) > 1048576 ||
            !preg_match('/^NFQWS2_[A-Za-z0-9_-]{1,64}_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}Z\.json$/D', $_POST['filename']) ||
            !preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/D', $_POST['submission_id'])) {
          http_response_code(400); exit();
        }
        if (!AsusReportProof::verify($_POST['report_proof'], $_POST['report'], $_POST['filename'], $_SESSION['support_report_key'] ?? '', time())) {
          http_response_code(403); exit();
        }
      }
      session_write_close();
      header('Content-Type: application/json; charset=utf-8');
      header('Cache-Control: no-store');
      if (!$mailSending) {
        http_response_code(200);
        echo json_encode((new AsusSupportMail())->availability());
      } else {
        try {
          $result = (new AsusSupportMail())->send($_POST['report'], $_POST['filename'], $_POST['submission_id']);
        } catch (Throwable $e) {
          $result = ['state'=>'unknown','submission_id'=>$_POST['submission_id'],'code'=>'delivery_unknown'];
        }
        $codes = ['accepted'=>200,'failed_safe'=>503,'unknown'=>503,'busy'=>409,'limited'=>429,'invalid'=>422];
        http_response_code($result['code'] === 'id_conflict' ? 409 : ($codes[$result['state']] ?? 503));
        echo json_encode($result);
      }
      exit();

    case 'supportreport':
      require_once __DIR__ . '/support-report.php';
      require_once __DIR__ . '/support-mail-proof.php';
      $keys = array_keys($_POST); sort($keys);
      if ($keys !== ['cmd', 'csrf_token']) { http_response_code(400); exit(); }
      if (!hash_equals($_SESSION['csrf_token'], $_POST['csrf_token']) || !asusReportSameOrigin()) {
        http_response_code(403); exit();
      }
      if (!isset($_SESSION['support_report_key'])) $_SESSION['support_report_key'] = bin2hex(random_bytes(32));
      $reportKey = $_SESSION['support_report_key'];
      session_write_close();
      $reportLock = new AsusReportLock();
      try {
        $reportLock->acquire();
        $report = (new AsusSupportReport(new AsusReportIO(), new AsusReportValues()))->collect();
        $json = AsusSupportReport::encode($report);
        $reportFilename = AsusSupportReport::filename($report);
        header('Cache-Control: no-store');
        header('Content-Type: application/json; charset=utf-8');
        header('Content-Disposition: attachment; filename="' . $reportFilename . '"');
        header('X-NFQWS2-Report-Proof: ' . AsusReportProof::issue($json, $reportFilename, $reportKey, time()));
        http_response_code(200);
        echo $json;
      } catch (Throwable $e) {
        http_response_code($e->getMessage() === 'busy' ? 409 : 503);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store');
        echo json_encode(['error' => $e->getMessage() === 'busy' ? 'busy' : 'unavailable']);
      } finally {
        $reportLock->release();
      }
      exit();

    case 'arkstatus':
      $response = (new AsusArkSettings(new AsusArkPlatform()))->status();
      break;

    case 'arkprepare':
    case 'arkrestore':
      if (!hash_equals($_SESSION['csrf_token'], $_POST['csrf_token'])) {
        http_response_code(403);
        exit();
      }
      $response = (new AsusArkSettings(new AsusArkPlatform()))->action(
        $_POST['cmd'] === 'arkprepare' ? 'prepare' : 'restore', $_POST['revision']);
      break;

    case 'status':
      $status = nfqwsServiceStatus();
      $response = array('status' => $status['status'], 'service' => $status['service'], 'ark_loaded' => nfqwsArkLoaded(), 'nfqws2' => NFQWS2, 'version' => nfqwsInstalledVersion(), 'anonym' => !$authEnabled, 'authenticated' => $authEnabled && $sessionValid, 'csrf_token' => $_SESSION['csrf_token'], 'username' => $sessionValid ? $_SESSION['auth_username'] : $auth['username']);
      break;

    case 'filenames':
      $files = getFiles($_POST['type'] ?? null);
      $response = array('status' => 0, 'files' => $files);
      break;

    case 'filecontent':
      if (str_ends_with($_POST['filename'], '.log')) {
        $content = getLogContent($_POST['filename']);
      } else {
        $content = getFileContent($_POST['filename']);
      }
      $response = array('status' => 0, 'content' => $content, 'filename' => $_POST['filename']);
      break;

    case 'filecreate':
      $result=asusPanelWrite(fn()=>createFile($_POST['filename']));
      $response = array('status' => $result ? 0 : 1, 'filename' => $_POST['filename']);
      break;

    case 'filesave':
      $result=asusPanelWrite(fn()=>saveFile($_POST['filename'],$_POST['content']));
      $response = array('status' => $result ? 0 : 1, 'filename' => $_POST['filename']);
      break;

    case 'fileremove':
      $result=asusPanelWrite(fn()=>removeFile($_POST['filename']));
      $response = array('status' => $result ? 0 : 1, 'filename' => $_POST['filename']);
      break;

    case 'restart':
    case 'stop':
    case 'start':
      $response = nfqwsServiceAction($_POST['cmd']);
      break;

    case 'upgrade':
      $response = upgradeAction();
      break;

    case 'login':
      $response = array('status' => 0, 'csrf_token' => $_SESSION['csrf_token']);
      break;

    case 'password':
      if (!hash_equals($_SESSION['csrf_token'], $_POST['csrf_token'])) {
        http_response_code(403);
        exit();
      }
      if ($_POST['password'] !== $_POST['confirmation'] || strlen($_POST['password']) > 72 || str_contains($_POST['password'], "\0")) {
        http_response_code(400);
        exit();
      }
      $username = $sessionValid ? $_SESSION['auth_username'] : $auth['username'];
      $saved = asusWebSavePassword($username, $_POST['password']);
      $newAuth = $saved ? asusWebReadAuth() : null;
      if ($newAuth !== null) {
        session_regenerate_id(true);
        $_SESSION['auth'] = true;
        $_SESSION['auth_revision'] = $newAuth['revision'];
        $_SESSION['auth_username'] = $username;
        $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
      }
      $response = array('status' => $newAuth !== null ? 0 : 1);
      break;

    case 'logout':
      $_SESSION['auth'] = false;
      unset($_SESSION['auth_revision'], $_SESSION['auth_username']);
      $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
      $response = array('status' => 0);
      break;

    default:
      http_response_code(405);
      exit();
  }

  header('Content-Type: application/json; charset=utf-8');
  http_response_code(200);
  echo json_encode($response);
  exit();
}

main();
