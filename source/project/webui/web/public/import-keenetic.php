<?php
require_once __DIR__.'/import-config.php';
require_once __DIR__.'/import-document.php';
require_once __DIR__.'/resource-paths.php';
/** Convert literal NFQWS2 strategy text into the existing selective-import format. */
final class AsusImportKeenetic
{
    private const FILE_OPTIONS=['--hostlist','--hostlist-exclude','--hostlist-auto','--ipset','--ipset-exclude'];
    private const MARKER='__NFQWS2_IMPORT_VARIABLE_';
    // Reviewed Linux strategy options: zapret2 v1.0.6, nfq2/nfqws.c long_options,
    // commit 221d7dff24bfec0cd5ac0a5070b8acef2008af3d; plus the pinned fastpath patch.
    // 0 = no operand, 1 = required operand, 2 = optional operand (equals form).
    // Process control, arbitrary outputs and input execution modes are excluded.
    private const OPTIONS=[
        '--debug'=>2,
        '--comment'=>2,
        '--ctrack-timeouts'=>1,
        '--ctrack-disable'=>2,
        '--payload-disable'=>2,
        '--server'=>2,
        '--ipcache-lifetime'=>1,
        '--ipcache-hostname'=>2,
        '--fastpath-workaround'=>1,
        '--reasm-disable'=>2,
        '--blob'=>1,
        '--lua-init'=>1,
        '--lua-gc'=>1,
        '--hostlist'=>1,
        '--hostlist-domains'=>1,
        '--hostlist-exclude'=>1,
        '--hostlist-exclude-domains'=>1,
        '--hostlist-auto'=>1,
        '--hostlist-auto-fail-threshold'=>1,
        '--hostlist-auto-fail-time'=>1,
        '--hostlist-auto-retrans-threshold'=>1,
        '--hostlist-auto-retrans-maxseq'=>1,
        '--hostlist-auto-retrans-reset'=>2,
        '--hostlist-auto-incoming-maxseq'=>1,
        '--hostlist-auto-udp-in'=>1,
        '--hostlist-auto-udp-out'=>1,
        '--hostlist-auto-debug'=>1,
        '--new'=>2,
        '--skip'=>0,
        '--name'=>1,
        '--template'=>2,
        '--import'=>1,
        '--cookie'=>1,
        '--filter-l3'=>1,
        '--filter-tcp'=>1,
        '--filter-udp'=>1,
        '--filter-icmp'=>1,
        '--filter-ipp'=>1,
        '--filter-l7'=>1,
        '--filter-ssid'=>1,
        '--filter-ssid-neg'=>2,
        '--filter-mark'=>1,
        '--ipset'=>1,
        '--ipset-ip'=>1,
        '--ipset-exclude'=>1,
        '--ipset-exclude-ip'=>1,
        '--payload'=>1,
        '--in-range'=>1,
        '--out-range'=>1,
        '--lua-desync'=>1,
    ];
    private static function fail(): never {throw new RuntimeException('unsupported_keenetic_strategy');}
    /** Estimate resolved sizes before the shared parser expands any references. */
    private static function configuration(string $text): array
    {
        if(str_contains($text,self::MARKER))self::fail();
        $literal=preg_replace_callback('/\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))/',fn($m)=>self::MARKER.(($m[1]??'')!==''?$m[1]:$m[2]).'__',$text);
        $records=AsusImportConfig::parse($literal);$sizes=[];
        $size=function(string $key,array $seen=[])use(&$size,&$sizes,$records):int{
            if(!isset($records[$key])||isset($seen[$key])||count($seen)>8)self::fail();if(isset($sizes[$key]))return $sizes[$key];$seen[$key]=true;$value=$records[$key];$length=strlen($value);
            preg_match_all('/'.self::MARKER.'([A-Za-z_][A-Za-z0-9_]*)__/', $value,$matches,PREG_SET_ORDER);
            foreach($matches as $m){$length+=$size($m[1],$seen)-strlen($m[0]);if($length>65536)self::fail();}
            if($length>65536)self::fail();return $sizes[$key]=$length;
        };
        foreach(array_keys($records)as $key)$size($key);return AsusImportConfig::parse($text);
    }
    private static function words(string $text): array
    {
        $words=[];$word='';$quote='';$started=false;
        for($i=0;$i<strlen($text);$i++){$char=$text[$i];
            if($quote===''&&!$started&&$char==='#'){while($i<strlen($text)&&$text[$i]!=="\n")$i++;continue;}
            if($quote!=="'"&&$char==='\\'){if(!isset($text[++$i]))self::fail();if($text[$i]!=="\n"){$word.=$text[$i];$started=true;}continue;}
            if(($char==='"'||$char==="'")&&($quote===''||$quote===$char)){$quote=$quote===''?$char:'';$started=true;continue;}
            if($quote===''&&str_contains(" \t\r\n",$char)){if($started){$words[]=$word;$word='';$started=false;}continue;}
            $word.=$char;$started=true;
        }
        if($quote!=='')self::fail();if($started)$words[]=$word;if(count($words)>8192)self::fail();
        foreach($words as $word)if($word===''||preg_match('/\s/u',$word)||preg_match('/[$`;|&()]/',$word))self::fail();return $words;
    }
    private static function path(string $value,string $kind,bool $marker=false): string
    {
        $at=str_starts_with($value,'@');$path=$at?substr($value,1):$value;
        if(preg_match('~^(?:\./)?(?:(lists|lua|blobs)/)?([A-Za-z0-9_.-]{1,128})$~D',$path,$m)&&!in_array($m[2],['.','..'],true)){
            if(($m[1]??'')!==''&&$m[1]!==$kind)self::fail();$path='/opt/etc/nfqws2/'.$kind.'/'.$m[2];
        }elseif(!str_starts_with($path,'/'))self::fail();
        return ($at||$marker?'@':'').$path;
    }
    private static function arguments(string $text,string $profile,bool $raw=false): string
    {
        $words=self::words($text);$filter=false;$meaningful=false;
        for($i=0;$i<count($words);$i++){
            $token=$words[$i];if(!preg_match('/^(--[A-Za-z][A-Za-z0-9_-]*)(?:=(.*))?$/Ds',$token,$m))self::fail();$option=$m[1];$separate=!str_contains($token,'=');$index=$i;$value=$separate?null:($m[2]??'');
            // getopt_long_only accepts abbreviations. The converter must never
            // pass an unchecked alias around the exact operand guards below.
            if(!isset(self::OPTIONS[$option]))self::fail();$arity=self::OPTIONS[$option];
            if($separate&&$arity===1){if(!isset($words[$i+1])||str_starts_with($words[$i+1],'--'))self::fail();$index=++$i;$value=$words[$index];}
            if(($arity===0&&!$separate)||($arity===1&&($value===null||$value==='')))self::fail();
            // '<' is NFQWS2's exclusive packet-range delimiter, not shell syntax
            // here. Permit it only inside a typed range operand; never a path.
            if($value!==null&&strpbrk($value,'<>')!==false&&(!in_array($option,['--out-range','--in-range'],true)||!preg_match('/^(?:[ndspbax](?:[+-]?[0-9]+)?)?<[ndspbax](?:[+-]?[0-9]+)?$/D',$value)))self::fail();
            if((str_starts_with($option,'--filter-')||$option==='--lua-desync')&&($value===null||$value===''))self::fail();
            if($option==='--hostlist-auto-debug'&&($value===null||!preg_match('~^(?:/opt)?/var/log/nfqws2(?:[-.][A-Za-z0-9_-]+)?\.log$~D',$value)))self::fail();
            if(str_starts_with($option,'--filter-')&&$value!==null&&$value!=='')$filter=true;
            if($option==='--lua-desync'&&$value!==null&&$value!=='')$meaningful=true;
            if(in_array($option,self::FILE_OPTIONS,true)){$kind='lists';if($value===null||$value==='')self::fail();$value=self::path($value,$kind);}
            elseif($option==='--lua-init'){
                if($value===null||$value===''||(!str_starts_with($value,'@')&&!preg_match('/\.lua$/D',$value)))self::fail();$value=self::path($value,'lua',true);
            }elseif($option==='--blob'){
                if($value===null||!preg_match('/^([A-Za-z_][A-Za-z0-9_]*):(.+)$/D',$value,$blob))self::fail();
                if(str_starts_with($blob[2],'@'))$value=$blob[1].':'.self::path($blob[2],'blobs',true);
                elseif(!preg_match('/^0x[0-9a-f]+$/Di',$blob[2]))self::fail();
            }elseif($option==='--debug'&&$value!==null&&!preg_match('/^[01]$/D',$value))self::fail();
            if($value!==null){if($separate)$words[$index]=$value;else $words[$index]=$option.'='.$value;}
        }
        if($raw&&(!$filter||!$meaningful))self::fail();return implode(' ',NfqwsResourcePaths::arguments($words,$profile));
    }
    private static function ports(string $value): string
    {
        if($value==='')return $value;
        foreach(explode(',',$value)as $part)if(!preg_match('/^([0-9]{1,5})(?::([0-9]{1,5}))?$/D',$part,$m)||(int)$m[1]<1||(int)$m[1]>65535||(isset($m[2])&&((int)$m[2]<(int)$m[1]||(int)$m[2]>65535)))self::fail();return $value;
    }
    public static function convert(string $text,?string $profile=null): string
    {
        try{
            if($text===''||strlen($text)>65536||preg_match('//u',$text)!==1||preg_match('/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/',$text))self::fail();
            $text=str_replace("\r\n","\n",$text);$text=preg_replace('/^\h*#.*(?:\n|$)/m','',$text);if(str_contains($text,'$(')||str_contains($text,'`')||str_contains($text,'\\$'))self::fail();$text=preg_replace_callback('/(\\\\+)\n/',fn($m)=>strlen($m[1])%2===1?substr($m[1],0,-1):$m[0],$text);$text=trim($text);if($text==='')self::fail();
            $profile??=NfqwsPlatform::current();NfqwsPlatform::settings($profile);
            if(str_starts_with($text,'--'))$values=['NFQWS_ARGS_CUSTOM'=>self::arguments($text,$profile,true)];
            else {$values=self::configuration($text);$hasBlock=false;foreach($values as $key=>&$value){
                if(in_array($key,AsusImportConfig::PORTS,true))$value=self::ports($value);
                else {$value=self::arguments($value,$profile);if(in_array($key,AsusImportConfig::BLOCKS,true)&&$value!=='')$hasBlock=true;}
            }unset($value);if(!$hasBlock)self::fail();}
            $config=ltrim(AsusImportConfig::replace('',$values),"\n");$document=['type'=>'nfqws2_strategy','schema_version'=>2,'versions'=>['core'=>'unknown','web'=>'unknown'],'purpose'=>'Keenetic NFQWS2','operator'=>'Unknown','comment'=>'','mode'=>'config','config'=>$config,'omitted_options'=>0,'dependencies'=>[]];
            $raw=json_encode($document,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);AsusImportDocument::read([$raw]);return $raw;
        }catch(Throwable $e){self::fail();}
    }
}
