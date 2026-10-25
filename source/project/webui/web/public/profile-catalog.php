<?php
require_once __DIR__.'/support-json-schema.php';
/** Exact signed bytes, a closed index, and immutable content-addressed files. */
final class AsusProfileCatalog
{
    public const ENVELOPE_LIMIT=131072;
    public const DOCUMENT_LIMIT=4194304;
    public static function verify(string $envelope,string $publicKey): array
    {
        try {
            $v=AsusSupportSchema::decode($envelope,self::ENVELOPE_LIMIT,'catalog_invalid');
            if(!is_object($v))throw new RuntimeException();
            $keys=array_keys(get_object_vars($v));sort($keys);
            if($keys!==['manifest','signature']||!is_string($v->manifest)||!is_string($v->signature))throw new RuntimeException();
            $raw=base64_decode($v->manifest,true);$sig=base64_decode($v->signature,true);
            if(!is_string($raw)||strlen($raw)>65536||base64_encode($raw)!==$v->manifest||!is_string($sig)||strlen($sig)!==384||base64_encode($sig)!==$v->signature)throw new RuntimeException();
        }catch(Throwable $e){throw new RuntimeException('catalog_invalid');}
        if(!extension_loaded('openssl')||strlen($publicKey)>2048||!str_starts_with($publicKey,'-----BEGIN PUBLIC KEY-----'))throw new RuntimeException('catalog_signature');
        $key=@openssl_pkey_get_public($publicKey);$details=$key===false?false:openssl_pkey_get_details($key);
        if(!$details||$details['type']!==OPENSSL_KEYTYPE_RSA||$details['bits']!==3072||openssl_verify($raw,$sig,$key,OPENSSL_ALGO_SHA256)!==1)throw new RuntimeException('catalog_signature');
        try {
            $index=AsusSupportSchema::decode($raw,65536,'catalog_invalid');
            $file=NfqwsPlatform::sharedFile('profile-catalog.schema.json',dirname(__DIR__,3).'/support/profile-catalog.schema.json');
            $schema=json_decode(file_get_contents($file),true,32,JSON_THROW_ON_ERROR);
            AsusSupportSchema::projection($index,$schema,$schema);$ids=[];
            foreach($index->profiles as $profile) {
                if(isset($ids[$profile->id])||trim($profile->title)===''||trim($profile->description)==='')throw new RuntimeException();
                $date=DateTimeImmutable::createFromFormat('!Y-m-d\TH:i:s\Z',$profile->updated_at,new DateTimeZone('UTC'));
                if($date===false||$date->format('Y-m-d\TH:i:s\Z')!==$profile->updated_at)throw new RuntimeException();
                $ids[$profile->id]=true;
            }
            return AsusSupportSchema::toArray($index);
        }catch(Throwable $e){throw new RuntimeException('catalog_invalid');}
    }
}
