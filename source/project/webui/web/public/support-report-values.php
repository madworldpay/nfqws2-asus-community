<?php
// Report-only parsers. Never source a user configuration or execute its values.
final class AsusReportValues
{
    private array $aliases = [];

    public static function decimal(string $value, string $maximum): ?string
    {
        if (!preg_match('/^[0-9]+$/D', $value)) return null;
        $value = ltrim($value, '0');
        if ($value === '') $value = '0';
        if (strlen($value) > strlen($maximum) ||
            (strlen($value) === strlen($maximum) && strcmp($value, $maximum) > 0)) return null;
        return $value;
    }

    public static function uint32(string $value): int|float|null
    {
        $n = self::decimal($value, '4294967295');
        return $n === null ? null : (PHP_INT_SIZE >= 8 ? (int)$n : (float)$n);
    }

    public static function literalSettings(string $text): array
    {
        $out = []; $unsafeContext = false;
        // Match whole assignments, including quoted newlines; no shell expansion.
        $lines = preg_split('/\n/', $text);
        for ($i = 0; $i < count($lines); $i++) {
            if (!preg_match('/^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=(.*)$/D', $lines[$i], $m)) {
                if (trim($lines[$i]) !== '' && !str_starts_with(ltrim($lines[$i]), '#')) $unsafeContext = true;
                continue;
            }
            $key = $m[1]; $tail = ltrim($m[2]); $value = null;
            if ($tail !== '' && ($tail[0] === "'" || $tail[0] === '"')) {
                $quote = $tail[0]; $body = substr($tail, 1); $end = strpos($body, $quote);
                while ($end === false && $i + 1 < count($lines)) {
                    $body .= "\n" . $lines[++$i]; $end = strpos($body, $quote);
                }
                if ($end !== false && preg_match('/^[ \t]*(?:#.*)?$/D', substr($body, $end + 1))) {
                    $candidate = substr($body, 0, $end);
                    if ($quote === "'" || !preg_match('/[$`\\\\]/', $candidate)) $value = $candidate;
                }
            } elseif (preg_match('/^([^\s\x00-\x20\'"`$\\\\;|&<>(){}]*)(?:[ \t]+#.*)?[ \t]*$/D', $tail, $n)) {
                $value = $n[1];
            }
            $out[$key] = array_key_exists($key, $out) ? null : $value;
        }
        return $unsafeContext ? array_fill_keys(array_keys($out), null) : $out;
    }

    public static function runtimeSettings(string $text): array
    {
        $values = self::literalSettings($text);
        if (trim($text) !== '' && !array_key_exists('NFQUEUE_NUM', $values)) {
            // Same default as S51nfqws2; retain unknown executable contexts.
            $defaults = self::literalSettings("NFQUEUE_NUM=300\n" . $text);
            $values['NFQUEUE_NUM'] = $defaults['NFQUEUE_NUM'];
        }
        return $values;
    }

    /** Resolve only earlier literal references in double quotes, for resource
     * discovery. This is not a shell parser: substitutions, defaults, forward
     * references, duplicate definitions and executable context stay unknown. */
    public static function referenceSettings(string $text): array
    {
        $values=self::literalSettings($text);$records=[];$unsafe=false;
        $lines=explode("\n",$text);
        for($i=0;$i<count($lines);$i++) {
            if(!preg_match('/^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=(.*)$/D',$lines[$i],$m)){
                if(trim($lines[$i])!==''&&!str_starts_with(ltrim($lines[$i]),'#'))$unsafe=true;continue;
            }
            $key=$m[1];$tail=ltrim($m[2]);$candidate=null;
            if($tail!==''&&($tail[0]==="'"||$tail[0]==='"')){
                $quote=$tail[0];$body=substr($tail,1);$end=null;$at=0;
                while(true){
                    for(;$at<strlen($body);$at++){
                        if($quote==='"'&&$body[$at]==='\\'){$at++;continue;}
                        if($body[$at]===$quote){$end=$at;break;}
                    }
                    if($end!==null||$i+1>=count($lines))break;
                    $body.="\n".$lines[++$i];
                }
                if($quote==='"'&&$end!==null&&preg_match('/^[ \t]*(?:#.*)?$/D',substr($body,$end+1)))$candidate=substr($body,0,$end);
            }
            $records[]=[$key,$candidate];
        }
        if($unsafe)return array_fill_keys(array_keys($values),null);
        $counts=array_count_values(array_column($records,0));$defined=[];
        foreach($records as [$key,$body]){
            if(($counts[$key]??0)===1&&$body!==null&&($values[$key]??null)===null){
                $out='';$ok=true;
                for($i=0;$i<strlen($body);$i++){
                    $c=$body[$i];
                    if($c==='\\'&&isset($body[$i+1])&&str_contains('$"\\`',$body[$i+1])){$out.=$body[++$i];continue;}
                    if($c==='`'){$ok=false;break;}
                    if($c==='$'){
                        if(!preg_match('/^\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))/',substr($body,$i),$m)){$ok=false;break;}
                        $name=($m[1]??'')!==''?$m[1]:$m[2];
                        if(!isset($defined[$name])||($counts[$name]??0)!==1||($values[$name]??null)===null){$ok=false;break;}
                        $out.=$values[$name];$i+=strlen($m[0])-1;
                    }else $out.=$c;
                    if(strlen($out)>65536){$ok=false;break;}
                }
                if($ok)$values[$key]=$out;
            }
            $defined[$key]=true;
        }
        return $values;
    }

    public function alias(string $kind, string $raw): string
    {
        if (!in_array($kind, ['WAN','IF','CLIENT4','CLIENT6','LIST','LUA','BLOB','DNS'], true)) throw new InvalidArgumentException('alias_kind');
        if (!isset($this->aliases[$kind][$raw])) $this->aliases[$kind][$raw] = $kind . '_' . (count($this->aliases[$kind] ?? []) + 1);
        return $this->aliases[$kind][$raw];
    }

    public static function network(string $raw): ?array
    {
        $parts = explode('/', $raw);
        if (count($parts) > 2 || !($packed = @inet_pton($parts[0]))) return null;
        $bits = strlen($packed) * 8;
        $prefix = $parts[1] ?? (string)$bits;
        if (self::decimal($prefix, (string)$bits) === null) return null;
        $family = $bits === 32 ? 4 : 6;
        $class = 'global';
        if ($family === 4) {
            $n = array_values(unpack('C*', $packed));
            if ($n[0] === 10 || ($n[0] === 172 && $n[1] >= 16 && $n[1] <= 31) || ($n[0] === 192 && $n[1] === 168)) $class = 'private';
            elseif ($n[0] === 127) $class = 'loopback';
            elseif ($n[0] === 169 && $n[1] === 254) $class = 'link_local';
            elseif ($n[0] === 0) $class = 'unspecified';
            elseif ($n[0] >= 224) $class = 'multicast_or_reserved';
        } else {
            if ($packed === str_repeat("\0", 16)) $class = 'unspecified';
            elseif ($packed === str_repeat("\0", 15) . "\1") $class = 'loopback';
            elseif ((ord($packed[0]) & 254) === 252) $class = 'private';
            elseif (ord($packed[0]) === 254 && (ord($packed[1]) & 192) === 128) $class = 'link_local';
            elseif (ord($packed[0]) === 255) $class = 'multicast_or_reserved';
        }
        return ['family'=>$family, 'prefix_length'=>(int)$prefix, 'address_class'=>$class, '_packed'=>$packed];
    }

    public static function networkView(array $network): array
    {
        return array_intersect_key($network, array_flip(['family','prefix_length','address_class']));
    }

    public function networkAlias(string $raw): string
    {
        $n=self::network($raw);
        if(!$n) throw new InvalidArgumentException('network');
        $bytes=intdiv($n['prefix_length'],8);$rem=$n['prefix_length']%8;
        $packed=substr($n['_packed'],0,$bytes);
        if($rem) $packed.=chr(ord($n['_packed'][$bytes]) & (255 << (8-$rem)));
        $packed=str_pad($packed,strlen($n['_packed']),"\0");
        return $this->alias('CLIENT'.$n['family'],bin2hex($packed).'/'.$n['prefix_length']);
    }

    public static function overlaps(array $left, array $right): bool
    {
        if ($left['family'] !== $right['family']) return false;
        $bits = min($left['prefix_length'], $right['prefix_length']); $bytes = intdiv($bits, 8); $rem = $bits % 8;
        if (substr($left['_packed'], 0, $bytes) !== substr($right['_packed'], 0, $bytes)) return false;
        return !$rem || ((ord($left['_packed'][$bytes]) ^ ord($right['_packed'][$bytes])) & (255 << (8 - $rem))) === 0;
    }
}
