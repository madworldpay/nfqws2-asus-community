<?php
require_once __DIR__.'/strategy-picker-core.php';
require_once __DIR__.'/support-report.php';

function nfqwsStrategyPickerDispatch(array $post,string $csrf):void
{
    $cmd=$post['cmd'];
    if(str_starts_with($cmd,'picker')){
        header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
        try{
            require_once __DIR__.'/strategy-picker-runtime.php';$runtime=new NfqwsStrategyPickerRuntime();
            NfqwsStrategyPickerRuntime::validateRequest($post);
            if(!hash_equals($csrf,$post['csrf_token'])||!asusReportSameOrigin()){
                http_response_code(403);echo json_encode(['error'=>'csrf_failed']);exit();
            }
            session_write_close();echo json_encode($runtime->dispatch($post),JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);
        }catch(Throwable $e){$code=NfqwsStrategyPickerRuntime::error($e);http_response_code(in_array($code,['busy','source_changed','stale_state'],true)?409:400);echo json_encode(['error'=>$code]);}
        exit();
    }
    // Keep ordinary panel file reads available while selection owns all writes.
    // Keep the signed support channel reachable for diagnosis and closure,
    // including recovery_required. Its normal auth/CSRF/invitation checks still
    // run in index.php; it does not replace the NFQWS configuration.
    if(in_array($cmd,['status','login','filenames','filecontent','technicalstart','technicalstatus','technicalstop'],true))return;
    $root=NfqwsPlatform::settings()['web_config'].'/strategy-picker';
    if(!file_exists($root.'/state.json'))return;
    $paths=is_file(__DIR__.'/device-profiles-paths.php')?__DIR__.'/device-profiles-paths.php':dirname(__DIR__,3).'/experimental/device-profiles/device-profiles-paths.php';
    require_once $paths;
    $state=new NfqwsStrategyPickerState($root);
    $current=$state->read()['state']??null;
    if(in_array($current,['preparing','running','restoring','applying','recovery_required'],true)){
        header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');http_response_code(409);echo json_encode(['error'=>$current==='recovery_required'?'recovery_required':'busy']);exit();
    }
}
