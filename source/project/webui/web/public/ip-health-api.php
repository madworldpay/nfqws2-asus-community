<?php
declare(strict_types=1);
require_once __DIR__.'/ip-health-store.php';

/** Authentication, same-origin and CSRF are enforced by the existing route. */
final class NfqwsIpHealthApi
{
    private NfqwsIpHealthStore $store;
    private $lease;
    public function __construct(?NfqwsIpHealthStore $store=null,?callable $lease=null){$this->store=$store??new NfqwsIpHealthStore();$this->lease=$lease??function(){require_once __DIR__.'/update-guard.php';return (new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();};}
    public static function validate(array $post):void
    {
        $fields=match($post['cmd']??null){'iphealthstatus'=>['cmd','csrf_token'],'iphealthconfigure'=>['cmd','csrf_token','enabled','revision'],'iphealthremove','iphealthrecheck'=>['cmd','csrf_token','id','revision'],'iphealthclear'=>['cmd','csrf_token','revision'],default=>throw new RuntimeException('invalid_request')};
        $keys=array_keys($post);sort($keys);sort($fields);if($keys!==$fields)throw new RuntimeException('invalid_request');foreach($post as $value)if(!is_string($value))throw new RuntimeException('invalid_request');
        if(isset($post['revision'])&&!preg_match('/^[a-f0-9]{64}$/D',$post['revision']))throw new RuntimeException('invalid_request');
        if(isset($post['enabled'])&&!in_array($post['enabled'],['0','1'],true))throw new RuntimeException('invalid_request');
        if(isset($post['id'])&&!(($post['cmd']==='iphealthrecheck'&&$post['id']==='all')||preg_match('/^[a-f0-9]{32}$/D',$post['id'])))throw new RuntimeException('invalid_request');
    }
    public function handle(array $post):array
    {
        self::validate($post);if($post['cmd']==='iphealthstatus')return $this->store->status();$lease=($this->lease)();
        try{return match($post['cmd']){'iphealthconfigure'=>$this->store->configure($post['enabled']==='1',$post['revision']),'iphealthremove'=>$this->store->remove($post['id'],$post['revision']),'iphealthclear'=>$this->store->clear($post['revision']),'iphealthrecheck'=>$this->store->recheck($post['id'],$post['revision'])};}
        finally{if(is_resource($lease)){flock($lease,LOCK_UN);fclose($lease);}}
    }
    public static function error(Throwable $error):string
    {return in_array($error->getMessage(),['invalid_request','invalid_state','stale_revision','busy','not_found','storage_unavailable','insufficient_space','output_limit','unsupported_runtime'],true)?$error->getMessage():'invalid_state';}
}
