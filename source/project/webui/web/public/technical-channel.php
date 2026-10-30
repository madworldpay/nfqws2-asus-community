<?php
require_once __DIR__.'/technical-channel-invite.php';
require_once __DIR__.'/technical-channel-files.php';
require_once __DIR__.'/technical-channel-process.php';
final class AsusTechnicalApi
{
    public static function validate(array $v): void
    {
        $keys=['cmd','csrf_token'];if(($v['cmd']??null)==='technicalstart')$keys=array_merge($keys,['invitation','consent']);
        $actual=array_keys($v);sort($actual);sort($keys);
        if($keys!==$actual||!is_string($v['csrf_token']??null)||!preg_match('/^[a-f0-9]{64}$/D',$v['csrf_token']))throw new RuntimeException('invalid_request');
        if($v['cmd']==='technicalstart'&&(!is_string($v['invitation'])||strlen($v['invitation'])>16384||$v['consent']!=='temporary_root_access'))throw new RuntimeException('invalid_request');
    }
    public static function error(Throwable $e): string
    {
        $allowed=['invalid_request','auth_required','invalid_invitation','busy','unsupported_runtime','root_required','unsafe_key_file','key_conflict','launch_failed','connection_failed','interrupted','expired','invalid_state'];
        return in_array($e->getMessage(),$allowed,true)?$e->getMessage():'invalid_state';
    }
}
require_once __DIR__.'/technical-channel-runtime.php';
