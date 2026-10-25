<?php
/** Read and rewrite literal assignments as data. Never run shell expansion. */
final class AsusImportConfig
{
    public const BLOCKS=['NFQWS_ARGS','NFQWS_ARGS_QUIC','NFQWS_ARGS_UDP','NFQWS_ARGS_CUSTOM'];
    public const SHARED=['NFQWS_BASE_ARGS','NFQWS_EXTRA_ARGS','NFQWS_ARGS_IPSET','MODE_LIST','MODE_ALL','MODE_AUTO'];
    public const PORTS=['TCP_PORTS','UDP_PORTS'];
    private static function scan(string $text): array
    {
        if(strlen($text)>262144||preg_match('//u',$text)!==1||str_contains($text,"\0"))throw new RuntimeException('invalid_import_config');
        $lines=explode("\n",$text);$out=[];
        for($i=0;$i<count($lines);$i++) {
            $line=$lines[$i];$trim=trim($line);if($trim===''||str_starts_with($trim,'#'))continue;
            if(!preg_match('/^\h*(?:export\h+)?([A-Za-z_][A-Za-z0-9_]*)\h*=(.*)$/D',$line,$m))throw new RuntimeException('unsupported_import_config');
            $key=$m[1];if(isset($out[$key]))throw new RuntimeException('unsupported_import_config');$start=$i;$tail=ltrim($m[2]);$quote=$tail[0]??'';$body='';
            if($quote==='"'||$quote==="'") {
                $tail=substr($tail,1);$at=0;$closed=false;
                while(true) {
                    for(;$at<strlen($tail);$at++) {
                        $c=$tail[$at];
                        if($quote==='"'&&$c==='\\') {
                            if(!isset($tail[$at+1]))throw new RuntimeException('unsupported_import_config');$next=$tail[++$at];
                            if($next==="\n")continue;
                            $body.=str_contains('\\"$`',$next)?$next:'\\'.$next;continue;
                        }
                        if($c===$quote){$closed=true;$at++;break;}$body.=$c;
                    }
                    if($closed||$i+1>=count($lines))break;$tail.="\n".$lines[++$i];
                }
                if(!$closed||!preg_match('/^\h*(?:#.*)?$/D',substr($tail,$at)))throw new RuntimeException('unsupported_import_config');
            }else {
                if(!preg_match('/^([^\s;|&`]*)(?:\h+#.*)?\h*$/D',$tail,$v))throw new RuntimeException('unsupported_import_config');$body=$v[1];
            }
            $out[$key]=['value'=>$body,'expand'=>$quote==='"'||$quote==='', 'start'=>$start,'end'=>$i];
        }
        return [$out,$lines];
    }
    public static function parse(string $text): array
    {
        [$records]=self::scan($text);$out=[];
        $resolve=function(string $key,array $seen=[])use(&$resolve,$records):string {
            if(!isset($records[$key])||isset($seen[$key])||count($seen)>8)throw new RuntimeException('unresolved_import_variable');$seen[$key]=true;$v=$records[$key]['value'];
            if(str_contains($v,'$(')||str_contains($v,'`'))throw new RuntimeException('unsafe_import');
            if($records[$key]['expand'])$v=preg_replace_callback('/\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))/',function($m)use(&$resolve,$seen){$name=($m[1]??'')!==''?$m[1]:$m[2];if(!in_array($name,array_merge(self::BLOCKS,self::SHARED),true))throw new RuntimeException('unresolved_import_variable');return $resolve($name,$seen);},$v);
            if(str_contains($v,'$'))throw new RuntimeException('unresolved_import_variable');return $v;
        };
        foreach(array_merge(self::BLOCKS,self::SHARED,self::PORTS) as $key)if(isset($records[$key]))$out[$key]=$resolve($key);
        return $out;
    }
    /** Settings are literal data; unlike strategy blocks they never expand variables. */
    public static function literalValues(string $text,array $keys): array
    {
        [$records]=self::scan($text);$out=[];
        foreach($keys as $key) {
            if(!is_string($key)||!preg_match('/^[A-Z][A-Z0-9_]*$/D',$key))throw new RuntimeException('invalid_config_key');
            if(!isset($records[$key]))continue;$value=$records[$key]['value'];
            if(str_contains($value,'$')||str_contains($value,'`'))throw new RuntimeException('unsafe_import');
            $out[$key]=$value;
        }
        return $out;
    }
    public static function replace(string $text,array $changes): string
    {
        if(array_diff(array_keys($changes),array_merge(self::BLOCKS,self::SHARED,self::PORTS)))throw new RuntimeException('invalid_import_selection');
        [$records,$lines]=self::scan($text);$replacements=[];$added=[];
        foreach($changes as $key=>$value) {
            if(!is_string($value)||strlen($value)>65536||preg_match('//u',$value)!==1||preg_match('/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/',$value)||str_contains($value,'$(')||str_contains($value,'`')||str_contains($value,'$'))throw new RuntimeException('unsafe_import');
            $line=$key.'="'.strtr($value,['\\'=>'\\\\','"'=>'\\"']).'"';
            if(isset($records[$key]))$replacements[$records[$key]['start']]=['end'=>$records[$key]['end'],'line'=>$line];else $added[]=$line;
        }
        $out=[];for($i=0;$i<count($lines);$i++){if(isset($replacements[$i])){$out[]=$replacements[$i]['line'];$i=$replacements[$i]['end'];}else $out[]=$lines[$i];}
        $result=implode("\n",$out);if($added)$result=rtrim($result,"\n")."\n".implode("\n",$added)."\n";
        if(strlen($result)>262144)throw new RuntimeException('output_limit');return $result;
    }
}
