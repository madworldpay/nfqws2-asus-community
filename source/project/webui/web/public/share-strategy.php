<?php
require_once __DIR__.'/support-json-schema.php';
/** Copies selected data only. No shell expansion or changes to saved settings. */
final class AsusShareStrategy
{
    public const BLOCKS=['NFQWS_ARGS','NFQWS_ARGS_QUIC','NFQWS_ARGS_UDP','NFQWS_ARGS_CUSTOM'];
    private const REFERENCES=['NFQWS_ARGS','NFQWS_ARGS_QUIC','NFQWS_ARGS_UDP','NFQWS_ARGS_CUSTOM','NFQWS_BASE_ARGS','NFQWS_ARGS_IPSET','NFQWS_EXTRA_ARGS','MODE_LIST','MODE_ALL','MODE_AUTO'];
    private const SETTINGS=['ISP_INTERFACE','ASUS_CLIENT_MODE','ASUS_CLIENTS4','ASUS_CLIENTS6','POLICY_NAME','POLICY_EXCLUDE','IPV6_ENABLED','TCP_PORTS','UDP_PORTS','LOG_LEVEL','LOG_DEBUG_PATH','NFQUEUE_NUM','USER','CONFIG_VERSION'];
    private static function assignments(string $config): array
    {
        if(strlen($config)>262144||preg_match('//u',$config)!==1)throw new RuntimeException('invalid_strategy');
        $lines=explode("\n",$config);$out=['__omitted_options'=>0];
        for($i=0;$i<count($lines);$i++) {
            $line=trim($lines[$i]);if($line===''||str_starts_with($line,'#'))continue;
            if(!preg_match('/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$/D',$line,$m))throw new RuntimeException('unsupported_config');
            $key=$m[1];$tail=ltrim($m[2]);$body='';$quote=$tail[0]??'';
            if($quote==='"'||$quote==="'") {
                $tail=substr($tail,1);$at=0;$end=null;
                while(true) {
                    for(;$at<strlen($tail);$at++) {
                        if($quote==='"'&&$tail[$at]==='\\'){$at++;continue;}
                        if($tail[$at]===$quote){$end=$at;break;}
                    }
                    if($end!==null||$i+1>=count($lines))break;
                    $tail.="\n".$lines[++$i];
                }
                if($end===null||!preg_match('/^\s*(?:#.*)?$/D',substr($tail,$end+1)))throw new RuntimeException('unsupported_config');
                $body=substr($tail,0,$end);
            }else {
                if(!preg_match('/^([^\s;|&`]*)(?:\s+#.*)?\s*$/D',$tail,$value))throw new RuntimeException('unsupported_config');
                $body=$value[1];
            }
            if(in_array($key,array_merge(self::REFERENCES,self::SETTINGS),true)) {
                if(array_key_exists($key,$out))throw new RuntimeException('unsupported_config');
                $out[$key]=['value'=>$body,'expand'=>$quote==='"'];
            }else $out['__omitted_options']++;
        }
        return $out;
    }
    private static function resolve(string $key,array $values,array $seen=[]): string
    {
        if(!isset($values[$key])||isset($seen[$key])||count($seen)>=5)return '$'.$key;
        $v=$values[$key];if(!$v['expand'])return $v['value'];$seen[$key]=true;
        return preg_replace_callback('/(?<!\\\\)\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))/u',function($m)use($values,$seen){
            $name=($m[1]??'')!==''?$m[1]:$m[2];return in_array($name,self::REFERENCES,true)?self::resolve($name,$values,$seen):$m[0];
        },$v['value']);
    }
    public static function draft(string $config,array $keys): array
    {
        if(!array_is_list($keys)||count($keys)<1||count($keys)>4||count(array_unique($keys))!==count($keys)||array_diff($keys,self::BLOCKS))throw new RuntimeException('invalid_strategy');
        $values=self::assignments($config);$blocks=[];
        foreach(self::BLOCKS as $key)if(in_array($key,$keys,true)) {
            if(!isset($values[$key]))throw new RuntimeException('strategy_unavailable');
            $blocks[]=['key'=>$key,'value'=>self::resolve($key,$values)];
        }
        return ['blocks'=>$blocks];
    }
    public static function discover(string $config): array
    {
        $values=self::assignments($config);$keys=[];
        foreach(self::BLOCKS as $key)if(isset($values[$key])&&trim($values[$key]['value'])!=='')$keys[]=$key;
        return $keys===[]?['blocks'=>[]]:self::draft($config,$keys);
    }
    private static function text(mixed $value,int $max,bool $required=false): string
    {
        if(!is_string($value)||preg_match('//u',$value)!==1||preg_match('/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/',$value)||preg_match_all('/./us',$value)>$max||($required&&trim($value)===''))throw new RuntimeException('invalid_strategy');
        return trim($value);
    }
    private static function aliaser(array &$deps,?array &$bindings=null): Closure
    {
        $aliases=[];$bindings=[];
        return function(string $kind,string $value)use(&$deps,&$aliases,&$bindings){
            $key=$kind."\0".$value;
            if(!isset($aliases[$key])) {
                if(count($deps)>=128)throw new RuntimeException('invalid_strategy');
                $id=($kind==='file'?'RESOURCE':($kind==='blob'?'BLOB':($kind==='network'?'NETWORK':'VARIABLE'))).'_'.(count($deps)+1);
                $aliases[$key]=$id;$deps[]=['id'=>$id,'kind'=>$kind,'included'=>false];$bindings[$id]=['kind'=>$kind,'value'=>$value];
            }
            return $aliases[$key];
        };
    }
    private static function clean(string $value,Closure $alias,array $preserve=[],bool $keepDestination=false): string
    {
        $value=self::text($value,65536,true);
        if(str_contains($value,'$(')||str_contains($value,'`')||preg_match('~[a-z][a-z0-9+.-]*://[^\s/]+@~i',$value))throw new RuntimeException('unsafe_strategy');
        $value=preg_replace('/^\h*#.*(?:\n|$)/m','',$value);
        // Inspect whole shell-like arguments without executing/expanding them.
        // Keep raw quoting unless replacing a complete private file operand.
        $tokens=[];$raw='';$plain='';$quote='';
        $flush=static function()use(&$tokens,&$raw,&$plain,$alias):void {
            if($raw==='')return;
            if(preg_match('/^--[a-z0-9_-]*(?:password|passwd|secret|token|credential|auth)[a-z0-9_-]*(?:=|$)/i',$plain))throw new RuntimeException('unsafe_strategy');
            if(preg_match('~(?<![A-Za-z0-9:/])@?/.*$~us',$plain,$m,PREG_OFFSET_CAPTURE))
                $raw=substr($plain,0,$m[0][1]).$alias('file',$m[0][0]);
            $tokens[]=$raw;$raw='';$plain='';
        };
        for($i=0;$i<strlen($value);$i++) {
            $c=$value[$i];
            if($quote===''&&str_contains(" \t\r\n",$c)){$flush();continue;}
            $raw.=$c;
            if($c==='\\'&&$quote!=="'") {
                if(++$i>=strlen($value))throw new RuntimeException('unsafe_strategy');
                $raw.=$value[$i];$plain.=$value[$i];continue;
            }
            if(($c==='"'||$c==="'")&&($quote===''||$quote===$c)){$quote=$quote===''?$c:'';continue;}
            $plain.=$c;
        }
        if($quote!=='')throw new RuntimeException('unsafe_strategy');$flush();$value=implode(' ',$tokens);
        // Only an explicit destination filter is reproducible public strategy data.
        // Other address literals retain the legacy identity masking behavior.
        $destinations=[];
        if($keepDestination)$value=preg_replace_callback('~(--ipset-ip(?:=|\s+))([0-9a-f:.,/]+)(?=\s|$)~i',function($m)use(&$destinations,$value){
            foreach(explode(',',$m[2]) as $network){$parts=explode('/',$network);$ip=@inet_pton($parts[0]);if($ip===false||count($parts)>2||(isset($parts[1])&&(!preg_match('/^[0-9]{1,3}$/D',$parts[1])||(int)$parts[1]>strlen($ip)*8)))return $m[0];}
            $key='NFQWSDESTINATION'.count($destinations).'VALUE';while(str_contains($value,$key)||isset($destinations[$key]))$key.='X';
            $destinations[$key]=$m[2];return $m[1].$key;
        },$value);
        $value=preg_replace_callback('/(?<![A-Za-z0-9:])(?:[a-f0-9]{2}:){5}[a-f0-9]{2}(?![A-Za-z0-9:])/i',fn($m)=>$alias('network',$m[0]),$value);
        $value=preg_replace_callback('~(?<![A-Za-z0-9_.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?:/[0-9]{1,2})?(?![A-Za-z0-9_.])~',function($m)use($alias){$ip=explode('/',$m[0],2)[0];return @inet_pton($ip)!==false?$alias('network',$m[0]):$m[0];},$value);
        $value=preg_replace_callback('~(?<![A-Za-z0-9_:])(?:[a-f0-9]{0,4}:){2,}[a-f0-9]{0,4}(?:%[A-Za-z0-9_.-]+)?(?:/[0-9]{1,3})?(?![A-Za-z0-9_:])~i',function($m)use($alias){$ip=preg_split('~[%/]~',$m[0])[0];return @inet_pton($ip)!==false?$alias('network',$m[0]):$m[0];},$value);
        $value=preg_replace_callback('/\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))/',function($m)use($alias,$preserve){
            $name=($m[1]??'')!==''?$m[1]:$m[2];return in_array($name,$preserve,true)?$m[0]:'$'.$alias('variable',$name);
        },$value);
        $remaining=preg_replace('/\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))/','',$value);
        if(str_contains($remaining,'$')||trim($value)==='')throw new RuntimeException('unsafe_strategy');
        preg_match_all('/\b(?:blob|seqovl_pattern)=([A-Za-z][A-Za-z0-9_]*)/',$value,$resources);
        foreach($resources[1] as $resource)$alias('blob',$resource);
        return trim(strtr($value,$destinations));
    }
    private static function finish(array $payload,array $context,array $versions,array $deps,int $schemaVersion=1): string
    {
        if(array_diff(array_keys($context),['purpose','region','operator','comment','share_location'])||
            (array_key_exists('share_location',$context)&&!is_bool($context['share_location'])))throw new RuntimeException('invalid_strategy');
        $out=['type'=>'nfqws2_strategy','schema_version'=>$schemaVersion,'versions'=>$versions]+$payload+[
            'purpose'=>self::text($context['purpose']??'',120,true),'operator'=>self::text($context['operator']??'',120,true),
            'comment'=>self::text($context['comment']??'',2000),'dependencies'=>$deps];
        if(($context['share_location']??false)===true)$out['region']=self::text($context['region']??'',120,true);
        $raw=json_encode($out,JSON_PRETTY_PRINT|JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR)."\n";
        if(strlen($raw)>65536)throw new RuntimeException('output_limit');AsusSupportSchema::validate($raw,$schemaVersion===2?'strategy2':'strategy');return $raw;
    }
    public static function context(array $context): array
    {
        if(array_diff(array_keys($context),['purpose','region','operator','comment','share_location'])||(array_key_exists('share_location',$context)&&!is_bool($context['share_location'])))throw new RuntimeException('invalid_strategy');
        $out=['purpose'=>self::text($context['purpose']??'',120,true),'operator'=>self::text($context['operator']??'',120,true),'comment'=>self::text($context['comment']??'',2000)];
        if(($context['share_location']??false)===true)$out['region']=self::text($context['region']??'',120,true);
        return $out;
    }
    /** V4 selected blocks include the global definitions needed to load their files. */
    public static function extended(array $selection,string $workingConfig,array $versions,?array &$bindings=null): array
    {
        $context=$selection['context']??null;if(!is_array($context))throw new RuntimeException('invalid_strategy');
        if(($selection['mode']??null)==='config') {
            if(!is_string($selection['config']??null))throw new RuntimeException('invalid_strategy');
            $out=json_decode(self::fullConfig($selection['config'],$context,$versions,$bindings,true),true,32,JSON_THROW_ON_ERROR);$out['schema_version']=2;return $out;
        }
        $inputs=self::referenceInputs($selection,$workingConfig);$deps=[];$alias=self::aliaser($deps,$bindings);$blocks=[];$shared=[];
        foreach($inputs as $key=>$value) {
            $clean=trim($value)===''?'':self::clean($value,$alias,[],true);
            if(in_array($key,self::BLOCKS,true))$blocks[]=['key'=>$key,'value'=>$clean];else $shared[$key]=$clean;
        }
        return json_decode(self::finish((['mode'=>'blocks','blocks'=>$blocks]+($shared?['shared'=>$shared]:[])),$context,$versions,$deps,2),true,32,JSON_THROW_ON_ERROR);
    }
    /** Resolve only known NFQWS2 variables as data; never evaluate shell input. */
    public static function referenceInputs(array $selection,string $workingConfig): array
    {
        $full=($selection['mode']??null)==='config';
        if(!$full&&($selection['mode']??null)!=='blocks')throw new RuntimeException('invalid_strategy');
        $config=$full?($selection['config']??null):$workingConfig;
        if(!is_string($config))throw new RuntimeException('invalid_strategy');
        $values=self::assignments($config);$out=[];
        foreach(['NFQWS_BASE_ARGS','NFQWS_EXTRA_ARGS','NFQWS_ARGS_IPSET'] as $key)
            if(isset($values[$key]))$out[$key]=self::resolve($key,$values);
        if($full) {
            foreach(self::REFERENCES as $key)if(isset($values[$key]))$out[$key]=self::resolve($key,$values);
        }else {
            $draft=$selection['draft']??null;
            if(!is_array($draft)||array_keys($draft)!==['blocks']||!is_array($draft['blocks'])||!array_is_list($draft['blocks'])||count($draft['blocks'])<1||count($draft['blocks'])>4)throw new RuntimeException('invalid_strategy');
            $seen=[];
            foreach($draft['blocks'] as $block) {
                if(!is_array($block)||array_diff(array_keys($block),['key','value'])||!in_array($block['key']??null,self::BLOCKS,true)||isset($seen[$block['key']])||!is_string($block['value']??null)||strlen($block['value'])>65536)throw new RuntimeException('invalid_strategy');
                $key=$block['key'];$seen[$key]=true;$local=$values;$local[$key]=['value'=>$block['value'],'expand'=>true];
                $out[$key]=self::resolve($key,$local);
            }
        }
        return $out;
    }
    public static function prepare(array $draft,array $context,array $versions,?array &$bindings=null): string
    {
        if(array_keys($draft)!==['blocks']||!is_array($draft['blocks'])||!array_is_list($draft['blocks'])||count($draft['blocks'])<1||count($draft['blocks'])>4)throw new RuntimeException('invalid_strategy');
        $deps=[];$alias=self::aliaser($deps,$bindings);$seen=[];$blocks=[];
        foreach($draft['blocks'] as $block) {
            if(!is_array($block)||array_diff(array_keys($block),['key','value'])||!in_array($block['key']??null,self::BLOCKS,true)||isset($seen[$block['key']]))throw new RuntimeException('invalid_strategy');
            $seen[$block['key']]=true;
            $blocks[]=['key'=>$block['key'],'value'=>self::clean(self::text($block['value']??null,65536,true),$alias)];
        }
        return self::finish(['mode'=>'blocks','blocks'=>$blocks],$context,$versions,$deps);
    }
    public static function fullConfig(string $config,array $context,array $versions,?array &$bindings=null,bool $keepDestination=false): string
    {
        $values=self::assignments($config);$deps=[];$alias=self::aliaser($deps,$bindings);$lines=[];
        foreach($values as $key=>$record) {
            if($key==='__omitted_options')continue;$value=$record['value'];
            if(in_array($key,self::REFERENCES,true))$value=trim($value)===''?'':self::clean($value,$alias,self::REFERENCES,$keepDestination);
            elseif(in_array($key,['ISP_INTERFACE','ASUS_CLIENTS4','ASUS_CLIENTS6','POLICY_NAME','USER'],true))$value=trim($value)===''?'':'<hidden>';
            elseif($key==='LOG_DEBUG_PATH')$value=trim($value)===''?'':$alias('file',$value);
            elseif($key==='ASUS_CLIENT_MODE'){if(!in_array($value,['all','include','exclude'],true))throw new RuntimeException('unsupported_config');}
            elseif(in_array($key,['TCP_PORTS','UDP_PORTS'],true)) {
                if($value!=='')foreach(explode(',',$value) as $port) {
                    if(!preg_match('/^([0-9]{1,5})(?::([0-9]{1,5}))?$/D',$port,$m)||(int)$m[1]<1||(int)$m[1]>65535||(isset($m[2])&&((int)$m[2]<(int)$m[1]||(int)$m[2]>65535)))throw new RuntimeException('unsupported_config');
                }
            }elseif(in_array($key,['POLICY_EXCLUDE','IPV6_ENABLED'],true)){if(!in_array($value,['0','1'],true))throw new RuntimeException('unsupported_config');}
            elseif($key==='LOG_LEVEL'){if(!in_array($value,['0','1','2'],true))throw new RuntimeException('unsupported_config');}
            elseif(!preg_match('/^[0-9]{1,5}$/D',$value)||($key==='NFQUEUE_NUM'&&(int)$value>65535))throw new RuntimeException('unsupported_config');
            $lines[]=$key.'="'.str_replace(['\\','"'],['\\\\','\\"'],$value).'"';
        }
        if($lines===[])throw new RuntimeException('strategy_unavailable');
        return self::finish(['mode'=>'config','config'=>implode("\n",$lines)."\n",'omitted_options'=>$values['__omitted_options']],$context,$versions,$deps);
    }
}
