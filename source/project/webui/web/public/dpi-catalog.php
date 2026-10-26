<?php
require_once __DIR__.'/platform.php';
final class AsusDpiCatalog
{
    public static function load(): array
    {
        $path=NfqwsPlatform::sharedFile('dpi-catalog.json',dirname(__DIR__,3).'/support/dpi-catalog.json');
        $value=json_decode(file_get_contents($path),true,32,JSON_THROW_ON_ERROR);
        if(($value['schema_version']??null)!==1)throw new RuntimeException('invalid_catalog');
        return $value;
    }
    public static function artifact(string $abi): array
    {return self::load()['artifacts'][$abi]??throw new RuntimeException('unsupported_abi');}
    public static function profile(): array {return self::load()['profile'];}
}
