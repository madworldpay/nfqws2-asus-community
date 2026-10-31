<?php
require_once __DIR__.'/blob-store.php';
require_once __DIR__.'/import-transaction.php';
require_once __DIR__.'/update-guard.php';
/** Uploads share panel serialization and update admission; reads are inert. */
final class AsusBlobApi
{
    private AsusBlobStore $store;
    public function __construct(?AsusBlobStore $store=null,private ?AsusImportTransaction $tx=null,private mixed $lease=null)
    {$this->store=$store??new AsusBlobStore();}
    public static function validate(array $post): void
    {
        $cmd=$post['cmd']??null;if(!in_array($cmd,['blobinventory','blobupload'],true))throw new RuntimeException('invalid_request');
        $want=$cmd==='blobinventory'?['cmd','csrf_token']:['cmd','csrf_token','name','data_base64','sha256'];$keys=array_keys($post);sort($keys);sort($want);if($keys!==$want)throw new RuntimeException('invalid_request');
        foreach($post as $key=>$value){if(!is_string($value))throw new RuntimeException('invalid_request');if(strlen($value)>($key==='data_base64'?349532:512))throw new RuntimeException($key==='data_base64'?'file_too_large':'invalid_request');}
        if($cmd==='blobupload'&&!preg_match('/^[a-f0-9]{64}$/D',$post['sha256']))throw new RuntimeException('invalid_request');
    }
    public function handle(array $post): array
    {
        self::validate($post);if($post['cmd']==='blobinventory')return $this->store->inventory();
        AsusBlobStore::uploadBytes($post['name'],$post['data_base64'],$post['sha256']);
        $lease=$this->lease!==null?($this->lease)():(new AsusUpdateGuard(new AsusUpdateStore()))->mutationLease();
        try{$this->tx??=new AsusImportTransaction();return $this->tx->writer(function()use($post){$this->tx->recover();return ['file'=>$this->store->upload($post['name'],$post['data_base64'],$post['sha256'])];});}
        finally{if(is_resource($lease)){flock($lease,LOCK_UN);fclose($lease);}}
    }
    public static function error(Throwable $e): string
    {
        $code=$e->getMessage();return in_array($code,['invalid_request','invalid_blob','file_too_large','hash_mismatch','source_changed','resource_unavailable','storage_unavailable','insufficient_space','busy','restore_required','invalid_state','output_limit'],true)?$code:'storage_unavailable';
    }
}
