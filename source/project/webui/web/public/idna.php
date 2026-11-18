<?php
namespace Symfony\Polyfill\Intl\Idn {
    // The pinned IDN implementation uses this primitive even without mbstring.
    // Keep its compatibility function namespaced; no global function is added.
    if (!\function_exists('mb_chr') && !\function_exists(__NAMESPACE__.'\\mb_chr')) {
        function mb_chr(int $point, string $encoding='UTF-8'): string
        {
            if (strtoupper($encoding)!=='UTF-8'||$point<0||$point>0x10ffff||($point>=0xd800&&$point<=0xdfff))
                throw new \ValueError('Invalid Unicode scalar');
            if ($point<0x80) return chr($point);
            if ($point<0x800) return chr(0xc0|($point>>6)).chr(0x80|($point&63));
            if ($point<0x10000) return chr(0xe0|($point>>12)).chr(0x80|(($point>>6)&63)).chr(0x80|($point&63));
            return chr(0xf0|($point>>18)).chr(0x80|(($point>>12)&63)).chr(0x80|(($point>>6)&63)).chr(0x80|($point&63));
        }
    }
}
namespace {
    /** One pinned UTS46 path, including on PHP builds without intl/mbstring. */
    final class NfqwsIdna
    {
        public const POLICY='uts46-533d68c-nfc-ebd57cc-std3-bidi-contextj-nontransitional-v1';
        public static function ascii(string $host): ?string
        {
            if($host===''||strlen($host)>1024||preg_match('//u',$host)!==1||str_contains($host,"\0"))return null;
            require_once __DIR__.'/vendor-idna/normalizer/Normalizer.php';
            if(!class_exists('Normalizer',false))require_once __DIR__.'/vendor-idna/normalizer/Resources/stubs/Normalizer.php';
            require_once __DIR__.'/vendor-idna/idn/Resources/unidata/DisallowedRanges.php';
            require_once __DIR__.'/vendor-idna/idn/Resources/unidata/Regex.php';
            require_once __DIR__.'/vendor-idna/idn/Info.php';
            require_once __DIR__.'/vendor-idna/idn/Idn.php';
            try{
                $idn=\Symfony\Polyfill\Intl\Idn\Idn::class;
                $flags=$idn::IDNA_USE_STD3_RULES|$idn::IDNA_CHECK_BIDI|$idn::IDNA_CHECK_CONTEXTJ;
                $info=[];$ascii=$idn::idn_to_ascii($host,$flags|$idn::IDNA_NONTRANSITIONAL_TO_ASCII,$idn::INTL_IDNA_VARIANT_UTS46,$info);
                if(!is_string($ascii)||($info['errors']??1)!==0)return null;
                $decoded=$idn::idn_to_utf8($ascii,$flags|$idn::IDNA_NONTRANSITIONAL_TO_UNICODE,$idn::INTL_IDNA_VARIANT_UTS46,$info);
                if(!is_string($decoded)||($info['errors']??1)!==0)return null;
                $again=$idn::idn_to_ascii($decoded,$flags|$idn::IDNA_NONTRANSITIONAL_TO_ASCII,$idn::INTL_IDNA_VARIANT_UTS46,$info);
                return $again===$ascii&&($info['errors']??1)===0?strtolower($ascii):null;
            }catch(\Throwable){return null;}
        }
    }
}
