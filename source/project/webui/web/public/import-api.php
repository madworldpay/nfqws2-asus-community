<?php
require_once __DIR__.'/import-transaction.php';
require_once __DIR__.'/update-guard.php';
/** Session proof contains hashes only; input documents never reach disk. */
final class AsusImportProof
{
    public static function issue(string $kind,string $digest,string $payload,string $key,int $now): string
    {
        if(!preg_match('/^[a-f0-9]{64}$/D',$key))throw new RuntimeException('invalid_state');$head='im1.'.$now.'.'.bin2hex(random_bytes(16)).'.'.$digest;
        return $head.'.'.hash_hmac('sha256',"NFQWS2-IMPORT\0".$kind."\0".$payload."\0".$head,hex2bin($key));
    }
    public static function verify(string $proof,string $kind,string $payload,string $key,int $now): ?string
    {
        if(!preg_match('/^[a-f0-9]{64}$/D',$key)||!preg_match('/^im1\.([1-9][0-9]{0,9})\.([a-f0-9]{32})\.([a-f0-9]{64})\.([a-f0-9]{64})$/D',$proof,$m))return null;
        $issued=(int)$m[1];if((string)$issued!==$m[1]||$issued>$now||$now-$issued>600)return null;$head=substr($proof,0,strrpos($proof,'.'));
        return hash_equals(hash_hmac('sha256',"NFQWS2-IMPORT\0".$kind."\0".$payload."\0".$head,hex2bin($key)),$m[4])?$m[3]:null;
    }
}
final class AsusImportApi
{
    private const FIELDS=['importinspect'=>['documents'],'importprepare'=>['documents','selection'],'importapply'=>['documents','selection','proof','request_id'],'importstatus'=>[],'importundo'=>['id','proof']];
    private AsusImportTransaction $tx;
    public function __construct(?AsusImportTransaction $tx=null,private mixed $lease=null,private ?AsusSmartDnsStore $dns=null)
    {$this->tx=$tx??new AsusImportTransaction();$this->dns??=new AsusSmartDnsStore();}
    public static function validate(array $post): void
    {
        $cmd=$post['cmd']??null;if(!is_string($cmd)||!isset(self::FIELDS[$cmd]))throw new RuntimeException('invalid_request');$keys=array_keys($post);sort($keys);$want=array_merge(['cmd','csrf_token'],self::FIELDS[$cmd]);sort($want);if($keys!==$want)throw new RuntimeException('invalid_request');
        foreach($post as $key=>$value)if(!is_string($value)||strlen($value)>(in_array($key,['documents','selection'],true)?8388608:512))throw new RuntimeException('invalid_request');
        foreach(['id','request_id']as $k)if(isset($post[$k])&&!preg_match('/^[a-f0-9]{32}$/D',$post[$k]))throw new RuntimeException('invalid_request');
    }
    private static function decoded(string $raw,bool $list): array
    {
        $v=AsusSupportSchema::decode($raw,8388608,'invalid_import');if($list?!is_array($v):!is_object($v))throw new RuntimeException('invalid_import');return AsusSupportSchema::toArray($v);
    }
    private function mutation(callable $fn): array
    {
        $lease=$this->lease!==null?($this->lease)():(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
        try{return $this->tx->writer(function()use($fn){
            // Active DNS jobs own their draft too. Reading/importing is still allowed.
            if(in_array($this->dns->status()['state'],['validating','applying','awaiting_confirmation','rolling_back','conflict'],true))throw new RuntimeException('busy');
            $this->tx->recover();return $fn();
        });}finally{if(is_resource($lease)){flock($lease,LOCK_UN);fclose($lease);}}
    }
    public function handle(array $post,string $key,int $now): array
    {
        self::validate($post);$cmd=$post['cmd'];
        if($cmd==='importstatus'){$s=$this->tx->status();$s['undo_proof']=$s['can_undo']?AsusImportProof::issue('undo',$this->tx->undoDigest(),hash('sha256',$s['id']),$key,$now):null;return $s;}
        if($cmd==='importundo'){
            $digest=AsusImportProof::verify($post['proof'],'undo',hash('sha256',$post['id']),$key,$now);if($digest===null)throw new RuntimeException('invalid_proof');
            return $this->mutation(function()use($post,$digest){$s=$this->tx->status();if($s['state']==='undone'&&$s['id']===$post['id'])return $s;if(!hash_equals($this->tx->undoDigest(),$digest))throw new RuntimeException('stale_preview');return $this->tx->undo($post['id']);});
        }
        $documents=self::decoded($post['documents'],true);if($cmd==='importinspect')return $this->tx->inspect($documents);
        $selection=self::decoded($post['selection'],false);$payload=hash('sha256',json_encode([$documents,$selection],JSON_THROW_ON_ERROR));
        if($cmd==='importprepare'){$p=$this->tx->prepare($documents,$selection);$p['proof']=$p['ready']?AsusImportProof::issue('apply',$p['digest'],$payload,$key,$now):null;return $p;}
        $digest=AsusImportProof::verify($post['proof'],'apply',$payload,$key,$now);if($digest===null)throw new RuntimeException('invalid_proof');
        return $this->mutation(function()use($post,$documents,$selection,$payload,$digest){
            $old=$this->tx->receipt($post['request_id'],$payload);if($old!==null)return $old;
            $p=$this->tx->prepare($documents,$selection);if(!hash_equals($p['digest'],$digest))throw new RuntimeException('stale_preview');return $this->tx->apply($p,$post['request_id'],$payload);
        });
    }
    public static function error(Throwable $e): string
    {
        $codes=['invalid_request','invalid_proof','invalid_import','invalid_import_selection','invalid_import_ports','unsupported_import_version','unsupported_import_config','unsupported_import_argument','duplicate_import_category','no_importable_data','import_limit','import_not_ready','invalid_strategy','unsafe_strategy','unsupported_config','strategy_unavailable','invalid_share','unsupported_report','source_changed','invalid_state','output_limit','insufficient_space','invalid_resource','invalid_dns_resource','private_dns_url','file_too_large','resource_unavailable','busy','request_conflict','stale_preview','stale_state','stale_draft','restore_required','storage_unavailable'];
        return in_array($e->getMessage(),$codes,true)?$e->getMessage():'invalid_import';
    }
}
