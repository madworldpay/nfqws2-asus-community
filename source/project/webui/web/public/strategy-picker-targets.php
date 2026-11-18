<?php
require_once __DIR__.'/idna.php';
require_once __DIR__.'/public-ipv4.php';

/** No DNS/network calls. Failed validation never returns a partial usable set. */
final class NfqwsStrategyPickerTargets
{
    public static function inspect(string $text): array
    {
        return self::inspectText($text,false);
    }
    /** Typed public targets used throughout pin/probe/evidence/assembly.
     * inspect() remains the exact legacy domain-v1 compatibility boundary. */
    public static function inspectMixed(string $text):array
    {
        return self::inspectText($text,true);
    }
    private static function inspectText(string $text,bool $literal):array
    {
        $errors=[];$hosts=[];$seen=[];$nonempty=0;
        if(strlen($text)>4096)return self::result([], [['line'=>0,'code'=>'input_too_long']]);
        foreach(preg_split('/\r\n|\n|\r/',$text)as $index=>$line){
            if(trim($line," \t")==='')continue;
            $number=$index+1;if(++$nonempty>32){$errors[]=['line'=>$number,'code'=>'too_many_lines'];break;}
            $input=trim($line," \t");$code='invalid_hostname';$host=self::host($input,$code,$literal);
            if($host===null){$errors[]=['line'=>$number,'code'=>$code];continue;}
            if(isset($seen[$host]))continue;$seen[$host]=true;
            if(count($hosts)>=10){$errors[]=['line'=>$number,'code'=>'too_many_hosts'];continue;}
            $hosts[]=$host;
        }
        if(!$hosts&&!$errors)$errors[]=['line'=>0,'code'=>'empty'];
        $result=self::result($hosts,$errors);
        if(!$literal||!$result['valid']||!array_filter($hosts,fn($host)=>NfqwsPublicIpv4::test($host)))return $result;
        $typed=static fn($host)=>['kind'=>NfqwsPublicIpv4::test($host)?'ipv4':'domain','host'=>$host];
        $targets=array_map($typed,$hosts);$sorted=$hosts;sort($sorted,SORT_STRING);
        return array_replace($result,['schema_version'=>2,'target_policy_version'=>'custom-public-targets-v2',
            'targets'=>$targets,'sha256'=>hash('sha256',json_encode([2,'custom-public-targets-v2',NfqwsIdna::POLICY,array_map($typed,$sorted)],JSON_THROW_ON_ERROR))]);
    }
    private static function result(array $hosts,array $errors): array
    {
        if($errors)return ['valid'=>false,'hosts'=>[],'errors'=>$errors,'sha256'=>null];
        $sorted=$hosts;sort($sorted,SORT_STRING);
        return ['valid'=>true,'hosts'=>$hosts,'errors'=>[],'sha256'=>hash('sha256',json_encode([NfqwsIdna::POLICY,$sorted],JSON_THROW_ON_ERROR))];
    }
    private static function host(string $input,string &$code,bool $literal=false): ?string
    {
        if(preg_match('//u',$input)!==1||preg_match('/[\x00-\x20\x7f\\\\]/',$input))return null;
        if(str_starts_with($input,'//')){$code='unsupported_scheme';return null;}
        $url=preg_match('~^[a-z][a-z0-9+.-]*://~i',$input)?$input:'https://'.$input;
        try{$parts=parse_url($url);}catch(ValueError){return null;}
        if(!is_array($parts)||!in_array(strtolower($parts['scheme']??''),['http','https'],true)){$code='unsupported_scheme';return null;}
        if(isset($parts['user'])||isset($parts['pass'])){$code='credentials_not_allowed';return null;}
        $afterScheme=substr($url,strpos($url,'://')+3);$authority=substr($afterScheme,0,strcspn($afterScheme,'/?#'));
        // parse_url drops an empty explicit port; inspect the original authority.
        if(isset($parts['port'])||str_contains($authority,':')){$code='port_not_allowed';return null;}
        $host=$parts['host']??'';if(!is_string($host)||strlen($host)>1024)return null;
        if($literal&&preg_match('/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/D',$host)){
            if(!NfqwsPublicIpv4::test($host)){$code='non_public_ipv4';return null;}
            if(!preg_match('~^https?://~i',$input)&&preg_match('~^/[0-9]{1,3}$~D',$parts['path']??'')){$code='cidr_not_allowed';return null;}
            return $host;
        }
        $host=NfqwsIdna::ascii($host);if($host===null)return null;
        if(str_ends_with($host,'.'))$host=substr($host,0,-1);
        if(strlen($host)>253||!str_contains($host,'.')||!preg_match('/^[a-z0-9.-]+$/D',$host))return null;
        $labels=explode('.',$host);
        foreach($labels as $label)if(!preg_match('/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/D',$label))return null;
        // libc/URL parsers can interpret hex and shortened numeric IPv4 forms.
        if(preg_match('/^(?:[0-9]+|0x[0-9a-f]+)$/D',$labels[count($labels)-1]))return null;
        foreach(['local','localhost','localdomain','lan','home','corp','internal','invalid','test','example','onion','arpa']as $suffix)
            if($host===$suffix||str_ends_with($host,'.'.$suffix))return null;
        foreach(['t.me','telegram.org','telegram.me','telesco.pe']as $excluded)
            if($host===$excluded||str_ends_with($host,'.'.$excluded)){$code='telegram_excluded';return null;}
        return $host;
    }
    /** Admit the complete answer or none of it; never filter poisoned entries. */
    public static function addresses(array $answer): array
    {
        if(!$answer)throw new RuntimeException('custom_dns_failed');
        if(count($answer)>16||!array_is_list($answer))throw new RuntimeException('custom_dns_answer_too_large');
        foreach($answer as $ip)if(!NfqwsPublicIpv4::test($ip))throw new RuntimeException('custom_non_public_address');
        $answer=array_values(array_unique($answer));sort($answer,SORT_STRING);return $answer;
    }
}
