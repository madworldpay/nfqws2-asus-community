<?php
/** Bounded JSON reader and validator for our bundled, closed schemas only. */
final class AsusSupportSchema
{
    private static int $budget;
    public static function decode(string $raw,int $max,string $code): mixed
    {
        try {
            if($raw===''||strlen($raw)>$max)throw new RuntimeException();
            $i=0;self::scan($raw,$i,0);self::space($raw,$i);
            if($i!==strlen($raw))throw new RuntimeException();
            $value=json_decode($raw,false,32,JSON_THROW_ON_ERROR);
            self::finite($value);
            return $value;
        } catch(Throwable $e) {throw new RuntimeException($code);}
    }
    private static function space(string $s,int &$i): void
    {while(isset($s[$i])&&str_contains(" \n\r\t",$s[$i]))$i++;}
    private static function quoted(string $s,int &$i): string
    {
        $begin=$i++;
        while(isset($s[$i])) {
            if($s[$i]==='\\'){$i+=2;continue;}
            if($s[$i++]==='"')return json_decode(substr($s,$begin,$i-$begin),true,2,JSON_THROW_ON_ERROR);
        }
        throw new RuntimeException();
    }
    private static function scan(string $s,int &$i,int $depth): void
    {
        self::space($s,$i);$c=$s[$i]??'';
        if($c==='"'){self::quoted($s,$i);return;}
        if($c==='{'||$c==='[') {
            if(++$depth>32)throw new RuntimeException();
            $i++;$end=$c==='{'?'}':']';$seen=[];self::space($s,$i);
            if(($s[$i]??'')===$end){$i++;return;}
            do {
                self::space($s,$i);
                if($c==='{') {
                    if(($s[$i]??'')!=='"')throw new RuntimeException();
                    $key=self::quoted($s,$i);
                    if(array_key_exists($key,$seen))throw new RuntimeException();
                    $seen[$key]=true;self::space($s,$i);
                    if(($s[$i++]??'')!==':')throw new RuntimeException();
                }
                self::scan($s,$i,$depth);self::space($s,$i);$next=$s[$i++]??'';
                if($next===$end)return;
                if($next!==',')throw new RuntimeException();
            } while(isset($s[$i]));
            throw new RuntimeException();
        }
        $start=$i;
        while(isset($s[$i])&&!str_contains(" \n\r\t,]}",$s[$i]))$i++;
        if($start===$i)throw new RuntimeException();
    }
    private static function finite(mixed $v): void
    {
        if(is_float($v)&&!is_finite($v))throw new RuntimeException();
        if(is_array($v)||is_object($v))foreach($v as $x)self::finite($x);
    }
    public static function validate(string $raw,string $kind): array
    {
        $files=['report'=>['report.schema.json',1048576,'invalid_report'],'dpi'=>['dpi-report.schema.json',262144,'invalid_dpi'],
            'envelope'=>['dpi-envelope.schema.json',2097152,'invalid_bundle'],
            'dpi_saved'=>['dpi-saved.schema.json',262144,'invalid_dpi'],
            'strategy'=>['strategy.schema.json',65536,'invalid_strategy'],
            'strategy2'=>['strategy-v2.schema.json',65536,'invalid_strategy'],
            'resources'=>['resources.schema.json',786432,'invalid_resource'],
            'dns_share'=>['dns-share.schema.json',131072,'invalid_dns_resource'],
            'share4'=>['share-v4.schema.json',4194304,'invalid_share'],
            'share'=>['share-envelope.schema.json',2097152,'invalid_share']];
        if(!isset($files[$kind]))throw new RuntimeException('invalid_request');
        [$name,$max,$code]=$files[$kind];$v=self::decode($raw,$max,$code);
        if($kind==='dpi'&&is_object($v)&&($v->schema_version??null)===2)$name='dpi-analysis-v2.schema.json';
        $base=is_file('/opt/share/nfqws2-asus/'.$name)?'/opt/share/nfqws2-asus':dirname(__DIR__,3).'/support';
        $schema=json_decode(file_get_contents($base.'/'.$name),true,128,JSON_THROW_ON_ERROR);
        self::$budget=200000;
        if(!self::match($v,$schema,$schema))throw new RuntimeException($code);
        return self::toArray($v);
    }
    /** Reuse validated strings instead of decoding a second full copy. */
    public static function toArray(mixed $value): mixed
    {
        if(is_object($value))$value=(array)$value;
        if(is_array($value))foreach($value as &$item)$item=self::toArray($item);
        return $value;
    }
    public static function projection(mixed $value,array $schema,array $root): void
    {self::$budget=200000;if(!self::match($value,$schema,$root))throw new RuntimeException('invalid_dpi');}
    private static function match(mixed $v,mixed $s,array $root): bool
    {
        if(--self::$budget<0)throw new RuntimeException('invalid_schema');
        if(is_bool($s))return $s;
        foreach($s as $key=>$_)if(!in_array($key,['$schema','$id','$defs','$ref','title','description','$comment','type','properties','required','additionalProperties','enum','const','pattern','maxLength','minLength','minimum','maximum','maxItems','minItems','items','prefixItems','uniqueItems','anyOf','allOf','if','then'],true))throw new RuntimeException('invalid_schema');
        if(isset($s['$ref'])) {
            if(!preg_match('~^#/\$defs/([A-Za-z0-9_-]+)$~D',$s['$ref'],$m)||!isset($root['$defs'][$m[1]]))throw new RuntimeException('invalid_schema');
            if(!self::match($v,$root['$defs'][$m[1]],$root))return false;
        }
        if(isset($s['type'])) {
            if(is_array($s['type'])) {
                foreach($s['type'] as $type) {$one=$s;$one['type']=$type;if(self::match($v,$one,$root))return true;}
                return false;
            }
            $valid=match($s['type']) {'object'=>is_object($v),'array'=>is_array($v),'string'=>is_string($v),'boolean'=>is_bool($v),'null'=>$v===null,
                'integer'=>(is_int($v)||is_float($v))&&is_finite((float)$v)&&floor($v)==$v,'number'=>(is_int($v)||is_float($v))&&is_finite((float)$v),default=>false};
            if(!$valid)return false;
        }
        if(array_key_exists('const',$s)&&$v!==$s['const']&&!((is_int($v)||is_float($v))&&(is_int($s['const'])||is_float($s['const']))&&$v==$s['const']))return false;
        if(isset($s['enum'])&&!in_array($v,$s['enum'],true))return false;
        if(isset($s['anyOf'])) { $ok=false;foreach($s['anyOf'] as $sub)if(self::match($v,$sub,$root)){$ok=true;break;}if(!$ok)return false; }
        foreach($s['allOf']??[] as $sub)if(!self::match($v,$sub,$root))return false;
        if(isset($s['if'])&&self::match($v,$s['if'],$root)&&isset($s['then'])&&!self::match($v,$s['then'],$root))return false;
        if(is_object($v)) {
            foreach($s['required']??[] as $key)if(!property_exists($v,$key))return false;
            foreach($v as $key=>$item) {
                if(isset($s['properties'][$key])){if(!self::match($item,$s['properties'][$key],$root))return false;}
                elseif(($s['additionalProperties']??true)===false)return false;
                elseif(is_array($s['additionalProperties']??null)&&!self::match($item,$s['additionalProperties'],$root))return false;
            }
        }
        if(is_array($v)) {
            $n=count($v);if($n<($s['minItems']??0)||$n>($s['maxItems']??PHP_INT_MAX))return false;
            if(($s['uniqueItems']??false)&&count(array_unique(array_map('serialize',$v)))!==$n)return false;
            foreach($v as $i=>$item)if(!self::match($item,$s['prefixItems'][$i]??($s['items']??true),$root))return false;
        }
        if(is_string($v)) {
            $len=preg_match_all('/./us',$v);
            if($len===false||$len<($s['minLength']??0)||$len>($s['maxLength']??PHP_INT_MAX))return false;
            if(isset($s['pattern'])) {
                $pattern=$s['pattern'];
                // Fixed-width, disjoint base64 quads never need backtracking. Avoid PCRE JIT's stack cap on a 1 MiB file.
                if($pattern==='^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$')$pattern='^(?:[A-Za-z0-9+/]{4})*+(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$';
                if(preg_match('~'.str_replace('~','\\~',$pattern).'~uD',$v)!==1)return false;
            }
        }
        if((is_int($v)||is_float($v))&&($v<($s['minimum']??-INF)||$v>($s['maximum']??INF)))return false;
        return true;
    }
}
