<?php
require_once __DIR__.'/update-dispatch.php';
require_once __DIR__.'/update-check.php';

/** Closed commands; channel credentials, paths and processes never cross HTTP. */
final class AsusUpdateApi
{
    private const FIELDS=[
        'packageupdatecheck'=>['force'],
        'packageupdateprepare'=>['revision','request_id'],
        'packageupdateapply'=>['operation_id','revision','request_id','consent'],
        'packageupdatestatus'=>['operation_id'],
    ];
    public static function validate(array $post): void
    {
        $cmd=$post['cmd']??null;if(!is_string($cmd)||!isset(self::FIELDS[$cmd]))throw new RuntimeException('invalid_request');
        $keys=array_keys($post);sort($keys);$expected=array_merge(['cmd','csrf_token'],self::FIELDS[$cmd]);sort($expected);
        if($keys!==$expected)throw new RuntimeException('invalid_request');foreach($post as $v)if(!is_string($v)||strlen($v)>128)throw new RuntimeException('invalid_request');
        foreach(['revision'=>64,'request_id'=>32,'operation_id'=>32] as $key=>$length)if(isset($post[$key])&&!($key==='operation_id'&&$cmd==='packageupdatestatus'&&$post[$key]==='')&&!preg_match('/^[a-f0-9]{'.$length.'}$/D',$post[$key]))throw new RuntimeException('invalid_request');
        if($cmd==='packageupdatecheck'&&!in_array($post['force'],['0','1'],true))throw new RuntimeException('invalid_request');
        if($cmd==='packageupdateapply'&&$post['consent']!=='install')throw new RuntimeException('consent_required');
    }
    public static function operation(?array $job): ?array
    {
        if($job===null)return null;$out=[];
        foreach(['id','revision','state','phase','package_version','installed_version','core_state','settings_verified'] as $field)if(array_key_exists($field,$job))$out[$field]=$job[$field];
        $out['code']=isset($job['code'])?AsusUpdatePrepare::code(new RuntimeException($job['code'])):null;
        $out['service_intent']=in_array($job['intent']['mode']??null,['running','waiting_for_wan','stopped'],true)?$job['intent']['mode']:null;return $out;
    }
    private static function checkResult(array $value):array
    {
        // Native preparation keeps manager-only metadata internally. Older
        // frontends require this exact shared four-field package projection.
        if(is_array($value['candidate']['package']??null))$value['candidate']['package']=array_intersect_key($value['candidate']['package'],array_flip(['family','filename','size','sha256']));
        return $value;
    }
    public static function dispatch(array $post): array
    {
        self::validate($post);$store=new AsusUpdateStore();$dispatch=new AsusUpdateDispatch($store);
        if($post['cmd']==='packageupdatecheck')return self::checkResult((new AsusUpdateCheck($store))->request($post['force']==='1'));
        if($post['cmd']==='packageupdateprepare')return self::operation($dispatch->prepare($post['revision'],$post['request_id']));
        if($post['cmd']==='packageupdateapply')return self::operation($dispatch->apply($post['operation_id'],$post['revision'],$post['request_id']));
        $job=null;if($post['operation_id']!=='')$job=$dispatch->status($post['operation_id']);else{
            $status=$store->status();$job=$status['active']??($status['history'][0]??null);if($job!==null)$job=$dispatch->status($job['id']);
        }
        return ['check'=>self::checkResult((new AsusUpdateCheck($store))->status()),'operation'=>self::operation($job)];
    }
}
