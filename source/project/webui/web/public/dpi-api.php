<?php
require_once __DIR__.'/dpi-jobs.php';
require_once __DIR__.'/dpi-options.php';
require_once __DIR__.'/support-json-schema.php';
final class AsusDpiApi
{
    private const FIELDS=['dpistatus'=>[],'dpiinstall'=>['request_id','consent'],'dpistart'=>['request_id','tests','heavy_consent'],'dpistop'=>['job_id'],'dpiresult'=>['job_id'],'dpidelete'=>['job_id'],'dpimetadata'=>[],'dpinative'=>['job_id'],'dpipreferences'=>['action','options']];
    public static function validate(array $post): void
    {
        $cmd=$post['cmd']??null;
        if(!is_string($cmd)||!isset(self::FIELDS[$cmd]))throw new RuntimeException('invalid_request');
        $keys=array_keys($post);sort($keys);$expected=array_merge(['cmd','csrf_token'],self::FIELDS[$cmd]);if($cmd==='dpistart'&&isset($post['options']))$expected[]='options';sort($expected);
        if($keys!==$expected)throw new RuntimeException('invalid_request');
        foreach($post as $key=>$value)if(!is_string($value)||strlen($value)>($key==='options'?131072:128))throw new RuntimeException('invalid_request');
        if(isset($post['request_id'])&&!preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/D',$post['request_id']))throw new RuntimeException('invalid_request');
        if(isset($post['job_id'])&&!preg_match('/^[a-f0-9]{32}$/D',$post['job_id']))throw new RuntimeException('invalid_request');
        if($cmd==='dpiinstall'&&$post['consent']!=='install')throw new RuntimeException('invalid_request');
        if(isset($post['options']))self::options($post['options']);
        if($cmd==='dpipreferences'&&!in_array($post['action'],['read','save','reset'],true))throw new RuntimeException('invalid_request');
        if($cmd==='dpistart') {
            if(!preg_match('/^[0-6]{1,7}$/D',$post['tests'])||!preg_match('/^[56]{0,2}$/D',$post['heavy_consent']))throw new RuntimeException('invalid_request');
            foreach(['tests','heavy_consent'] as $key){$chars=str_split($post[$key]);$sorted=$chars;sort($sorted);if($sorted!==$chars||array_values(array_unique($chars))!==$chars)throw new RuntimeException('invalid_request');}
        }
    }
    public static function dispatch(array $post): array|string
    {
        self::validate($post);
        if($post['cmd']==='dpistart')throw new RuntimeException('workflow_changed');
        $jobs=new AsusDpiJobs();
        return match($post['cmd']) {
            'dpistatus'=>$jobs->status(),
            'dpiinstall'=>$jobs->startInstall($post['request_id'],true),
            'dpistart'=>$jobs->startRun($post['request_id'],array_map('intval',str_split($post['tests'])),array_map('intval',str_split($post['heavy_consent'])),self::options($post['options']??'{}')),
            'dpistop'=>$jobs->stop($post['job_id']),
            'dpiresult'=>$jobs->result($post['job_id']),
            'dpinative'=>$jobs->native($post['job_id']),
            'dpimetadata'=>self::metadata(),
            'dpipreferences'=>self::preferences($post),
            'dpidelete'=>self::delete($jobs,$post['job_id'])
        };
    }
    private static function options(string $raw): array
    {$v=AsusSupportSchema::decode($raw,131072,'invalid_request');if(!is_object($v))throw new RuntimeException('invalid_request');return json_decode($raw,true,32,JSON_THROW_ON_ERROR);}
    private static function metadata(): array
    {$m=AsusDpiOptions::metadata();$m['interfaces']=array_map('basename',glob('/sys/class/net/*')?:[]);return $m;}
    private static function preferences(array $post): array
    {$s=new AsusDpiStore();if($post['action']!=='read')$s->writePreferences($post['action']==='reset'?[]:self::options($post['options']));return $s->readPreferences();}
    private static function delete(AsusDpiJobs $jobs,string $id): array{$jobs->deleteResult($id);return ['deleted'=>true];}
}
