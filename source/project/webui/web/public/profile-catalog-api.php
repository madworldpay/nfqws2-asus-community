<?php
require_once __DIR__.'/profile-catalog-transport.php';
final class AsusProfileCatalogApi
{
    public function __construct(private ?AsusProfileCatalogTransport $source=null){}
    public static function validate(array $post): void
    {
        $cmd=$post['cmd']??null;
        $fields=['importcatalog'=>[],'importcatalogload'=>['id','sha256']];
        if(!is_string($cmd)||!isset($fields[$cmd]))throw new RuntimeException('invalid_request');
        $keys=array_keys($post);sort($keys);$expected=array_merge(['cmd','csrf_token'],$fields[$cmd]);
        if(array_key_exists('source',$post)){
            if($post['source']!=='package')throw new RuntimeException('invalid_request');
            $expected[]='source';
        }
        sort($expected);
        if($keys!==$expected)throw new RuntimeException('invalid_request');
        foreach($post as $v)if(!is_string($v)||strlen($v)>128)throw new RuntimeException('invalid_request');
        if($cmd==='importcatalogload'&&(!preg_match('/^[a-z0-9][a-z0-9-]{0,63}$/D',$post['id'])||!preg_match('/^[a-f0-9]{64}$/D',$post['sha256'])))throw new RuntimeException('invalid_request');
    }
    public function handle(array $post): array
    {
        self::validate($post);$source=$this->source??new AsusProfileCatalogTransport();$packaged=isset($post['source']);
        if($post['cmd']==='importcatalog')return $source->catalog($packaged)+['build'=>$source->build()];
        return ['document'=>$source->document($post['id'],$post['sha256'],$packaged)];
    }
    public static function error(Throwable $e): string
    {
        $code=$e->getMessage();return in_array($code,['invalid_request','catalog_invalid','catalog_signature','catalog_unavailable','catalog_runtime','catalog_dns','catalog_tls','catalog_connect','catalog_http','catalog_timeout','catalog_limit','catalog_changed','catalog_version'],true)?$code:'catalog_invalid';
    }
}
