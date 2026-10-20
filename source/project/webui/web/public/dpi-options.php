<?php
/** Compile typed settings into the unchanged native CLI. Never accepts a command or path. */
final class AsusDpiOptions
{
    public static function metadata(): array
    {
        static $data;
        if($data===null){$p='/opt/share/nfqws2-asus/dpi-native-defaults.json';if(!is_file($p))$p=dirname(__DIR__,3).'/support/dpi-native-defaults.json';$data=json_decode(file_get_contents($p),true,32,JSON_THROW_ON_ERROR);}
        return $data;
    }
    public static function defaults(): array
    {return ['profile'=>'ru','language'=>'ru','config'=>[],'targets'=>[],'interface'=>null,'proxy'=>null,'fingerprint'=>null,'burst'=>[],'limits'=>['total_seconds'=>600,'group_seconds'=>180]];}
    private static function fail(string $field): never {throw new RuntimeException('invalid_options:'.$field);}
    private static function keys(array $a,array $keys,string $path): void {foreach($a as $k=>$_)if(!in_array($k,$keys,true))self::fail($path.'.'.$k);}
    private static function text(mixed $v,string $p,int $max=2048): string
    {if(!is_string($v)||strlen($v)>$max||preg_match('/[\x00-\x1f\x7f]/',$v))self::fail($p);return $v;}
    private static function number(mixed $v,string $p,float $lo,float $hi,bool $int=false): void
    {if(!is_int($v)&&!is_float($v)||!is_finite((float)$v)||$v<$lo||$v>$hi||($int&&!is_int($v)))self::fail($p);}
    private static function domain(mixed $v,string $p): void
    {self::text($v,$p,253);if(!preg_match('/^(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?$/D',$v)||str_contains($v,'..'))self::fail($p);}
    // The native domain loader strips scheme/path/port before probing (stock x.com entry has a path).
    private static function target(mixed $v,string $p): void
    {
        self::text($v,$p);$host=strtolower(trim($v));
        if(str_contains($host,'://')){[$scheme,$host]=explode('://',$host,2);if(!in_array($scheme,['http','https'],true))self::fail($p);}
        $host=preg_split('~[/?#]~',$host,2)[0];
        if(str_starts_with($host,'[')){if(!preg_match('/^\[([^]]+)\](?::[0-9]+)?$/D',$host,$m))self::fail($p);$host=$m[1];}
        elseif(substr_count($host,':')<2)$host=preg_replace('/:[0-9]+$/D','',$host);
        $host=trim($host,'.');if(@inet_pton($host)!==false)return;self::domain($host,$p);
    }
    private static function listOf(mixed $v,string $p,callable $check,int $max=512): void
    {if(!is_array($v)||!array_is_list($v)||count($v)>$max)self::fail($p);foreach($v as $i=>$item)$check($item,$p.'.'.$i);}
    private static function url(mixed $v,string $p,array $schemes=['http','https']): void
    {self::text($v,$p);$u=parse_url($v);if(!$u||!in_array($u['scheme']??'',$schemes,true)||empty($u['host']))self::fail($p);}
    private static function config(array $c): void
    {
        $m=self::metadata();self::keys($c,$m['config_keys'],'config');
        $positive=['TIMEOUT','POOL_TIMEOUT','STUB_IPS_TIMEOUT','DNS_CHECK_TIMEOUT','DNS_AVAILABILITY_TIMEOUT','FAT_CONNECT_TIMEOUT','FAT_READ_TIMEOUT','FAT_CHUNK_DELAY','TELEGRAM_MEDIA_SIZE_MB','TELEGRAM_UPLOAD_SIZE_MB','TELEGRAM_STALL_TIMEOUT','TELEGRAM_TOTAL_TIMEOUT','TELEGRAM_DC_PING_TIMEOUT'];
        foreach($c as $k=>$v){$p='config.'.$k;
            if($k==='PROXY_URL'){if($v!==null)self::fail($p);continue;}
            if($k==='ASN_CACHE_FILE'){if($v!==null&&$v!=='asn-cache.json')self::fail($p);continue;}
            if($k==='IP_VERSION'){if(!in_array($v,['ipv4','ipv6'],true))self::fail($p);continue;}
            if($k==='TLS_FINGERPRINT'){if(!in_array($v,$m['fingerprints'],true))self::fail($p);continue;}
            if($k==='DEBUG'){if(!is_bool($v))self::fail($p);continue;}
            if($k==='PIN_CACHE_TTL'){self::number($v,$p,0.001,604800);continue;}
            if(in_array($k,$positive,true)){self::number($v,$p,0.001,str_contains($k,'SIZE_MB')?256:1800);continue;}
            if($k==='DNS_TRUTH_FALLBACK'){
                if(!is_array($v))self::fail($p);foreach($v as $d=>$ips){self::domain($d,$p);self::listOf($ips,$p,function($ip,$p){if(!(is_string($ip)&&@inet_pton($ip)!==false))self::fail($p);});}continue;
            }
            if(in_array($k,['DNS_UDP_SERVERS','TELEGRAM_DCS','DNS_AVAILABILITY_SERVERS','BYPASS_TOOLS'],true)){
                self::listOf($v,$p,function($row,$p)use($k){
                    if(!is_array($row)||!array_is_list($row)||count($row)<2||count($row)>4)self::fail($p);
                    self::text($row[0],$p);if($k==='BYPASS_TOOLS'){self::listOf($row[1],$p,[self::class,'text']);return;}
                    self::text($row[1],$p);
                    if($k==='DNS_AVAILABILITY_SERVERS'){
                        if(!in_array($row[2]??null,['udp','doh_wire','doh_json','dot'],true))self::fail($p);
                        if(isset($row[3]))self::number(is_string($row[3])&&preg_match('/^[0-9]+$/D',$row[3])?(int)$row[3]:$row[3],$p,1,65535,true);
                    }else foreach($row as $s)self::text($s,$p);
                });continue;
            }
            $stock=$m['config'][$k]??null;
            if(is_array($stock)){
                if($k==='CONCURRENCY_PRESETS')self::listOf($v,$p,fn($n,$p)=>self::number($n,$p,1,100,true));
                else self::listOf($v,$p,function($s,$p)use($k){
                    if(str_contains($k,'DOMAINS'))self::domain($s,$p);elseif(str_contains($k,'URL')||$k==='CYMRU_DOH_SERVERS')self::url($s,$p,in_array($k,['IP4_LOOKUP_URLS','IP6_LOOKUP_URLS','IP_LOOKUP_URLS'],true)?['http','https']:['https']);else self::text($s,$p);
                });continue;
            }
            if(is_int($stock)||$k==='DNS_STUB_THRESHOLD'){
                $hi=str_contains($k,'PORT')?65535:($k==='DNS_STUB_THRESHOLD'?50:(str_contains($k,'CONCURRENT')||str_contains($k,'CONCURRENCY')?100:($k==='FAT_CHUNK_SIZE'?1048576:100000)));
                self::number($v,$p,1,$hi,true);continue;
            }
            self::text($v,$p);
            if($k==='TELEGRAM_MEDIA_URL')self::url($v,$p);
        }
        if(isset($c['TCP_BLOCK_MIN_KB'],$c['TCP_BLOCK_MAX_KB'])&&$c['TCP_BLOCK_MIN_KB']>$c['TCP_BLOCK_MAX_KB'])self::fail('config.TCP_BLOCK_MAX_KB');
    }
    private static function variant(mixed $text): void
    {
        self::text($text,'burst.variant',512);
        foreach(explode(';',$text) as $part){
            if(in_array($part,['sigalg-swap','+grease','-grease','no-padding','alpn-reverse'],true))continue;
            if(preg_match('/^([+-]ext|[+]group|padding|ext-order|groups|key-shares):(.+)$/D',$part,$m)){
                $values=explode(',',$m[2]);if(in_array($m[1],['+ext','-ext','+group','padding'],true)&&count($values)!==1)self::fail('burst.variant');
                foreach($values as $n){if(!preg_match('/^(?:[0-9]{1,5}|0x[0-9a-fA-F]{1,4})$/D',$n)||intval($n,str_starts_with($n,'0x')?16:10)>65535)self::fail('burst.variant');}continue;
            }
            if(preg_match('/^ext-body:([0-9]{1,5}|0x[0-9a-fA-F]{1,4}):([0-9a-fA-F ]*)$/D',$part,$m)&&intval($m[1],str_starts_with($m[1],'0x')?16:10)<=65535&&strlen(str_replace(' ','',$m[2]))%2===0)continue;
            self::fail('burst.variant');
        }
    }
    public static function normalize(array $input): array
    {
        if(strlen(json_encode($input,JSON_THROW_ON_ERROR))>131072)self::fail('size');
        self::keys($input,array_keys(self::defaults()),'');$o=array_replace(self::defaults(),$input);$m=self::metadata();
        if(!in_array($o['profile'],['ru','ir','cn','global'],true))self::fail('profile');
        if(!in_array($o['language'],['ru','en','zh','fa','auto'],true))self::fail('language');
        foreach(['config','targets','burst','limits'] as $k)if(!is_array($o[$k]))self::fail($k);
        self::config($o['config']);
        if($o['interface']!==null&&$o['interface']!==''){
            self::text($o['interface'],'interface',64);
            if(!(@inet_pton($o['interface'])!==false)&&!preg_match('/^[a-zA-Z0-9_.:-]{1,15}$/D',$o['interface']))self::fail('interface');
        }else $o['interface']=null;
        if($o['proxy']!==null&&$o['proxy']!=='')self::url($o['proxy'],'proxy',['socks5','socks5h','http']);else $o['proxy']=null;
        if($o['fingerprint']!==null&&!in_array($o['fingerprint'],$m['fingerprints'],true))self::fail('fingerprint');
        self::keys($o['targets'],['domains','tcp','sni','burst_domains','quic_unsupported'],'targets');
        foreach($o['targets'] as $k=>$rows){if($rows===null)continue;if($rows===[]){$o['targets'][$k]=null;continue;}
            if($k!=='tcp'){self::listOf($rows,'targets.'.$k,[self::class,$k==='sni'?'domain':'target']);continue;}
            self::listOf($rows,'targets.tcp',function($row,$p){
                if(!is_array($row))self::fail($p);self::keys($row,['id','ip','port','sni','provider','asn'],$p);
                self::text($row['id']??null,$p.'.id',64);if(!(is_string($row['ip']??null)&&@inet_pton($row['ip'])!==false))self::fail($p.'.ip');
                self::number($row['port']??null,$p.'.port',1,65535,true);
                if(isset($row['sni'])&&$row['sni']!=='')self::domain($row['sni'],$p.'.sni');foreach(['provider','asn'] as $k)if(isset($row[$k]))self::text($row[$k],$p.'.'.$k,128);
            });
        }
        $b=$o['burst'];self::keys($b,['connections','timeout','gap','profiles','tls','alpn','variant','trace'],'burst');
        foreach(['connections'=>[1,100],'timeout'=>[1,60],'gap'=>[0,1000]] as $k=>[$lo,$hi])if(isset($b[$k]))self::number($b[$k],'burst.'.$k,$lo,$hi,true);
        if(isset($b['profiles'])){self::text($b['profiles'],'burst.profiles');if($b['profiles']!=='all')foreach(explode(',',$b['profiles']) as $f)if(!in_array($f,$m['fingerprints'],true))self::fail('burst.profiles');}
        if(isset($b['tls'])&&!in_array($b['tls'],['1.2','1.3','1.3+1.2'],true))self::fail('burst.tls');
        if(isset($b['alpn'])&&!in_array($b['alpn'],['h2','http/1.1'],true))self::fail('burst.alpn');
        if(isset($b['trace'])&&!is_bool($b['trace']))self::fail('burst.trace');
        if(isset($b['variant']))self::variant($b['variant']);
        self::keys($o['limits'],['total_seconds','group_seconds'],'limits');$o['limits']=array_replace(self::defaults()['limits'],$o['limits']);
        foreach($o['limits'] as $k=>$v)self::number($v,'limits.'.$k,1,1800,true);
        if($o['limits']['group_seconds']>$o['limits']['total_seconds'])self::fail('limits.group_seconds');
        if(strlen(json_encode($o,JSON_THROW_ON_ERROR))>131072)self::fail('size');
        return $o;
    }
    public static function compile(array $options,int $group,string $binary): array
    {
        if($group<0||$group>6)self::fail('tests');$o=self::normalize($options);$m=self::metadata();
        $a=[$binary,'--json','--tests',(string)$group,'--lang',$o['language'],'--profile',$o['profile']];$files=[];
        if($o['interface']!==null)$a=array_merge($a,['--iface',$o['interface']]);
        if($o['fingerprint']!==null)$a=array_merge($a,['--fingerprint',$o['fingerprint']]);
        $config=$o['config'];if($o['proxy']!==null)$config['PROXY_URL']=$o['proxy'];
        if(isset($config['DNS_TRUTH_FALLBACK']))$config['DNS_TRUTH_FALLBACK']=(object)$config['DNS_TRUTH_FALLBACK'];
        if($config!==[])$files['config.yml']=json_encode(array_replace($m['config'],$config),JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES);
        foreach(['domains'=>'domains.txt','tcp'=>'tcp16.json','sni'=>'whitelist_sni.txt','burst_domains'=>'burst-domains.txt','quic_unsupported'=>'quic_unsupported.txt'] as $k=>$name){
            if(!array_key_exists($k,$o['targets'])||$o['targets'][$k]===null)continue;
            $files[$name]=$k==='tcp'?json_encode($o['targets'][$k],JSON_THROW_ON_ERROR):($o['targets'][$k]===[]?'':implode("\n",$o['targets'][$k])."\n");
            if($k==='domains'&&$group===2||$k==='burst_domains'&&$group===6)$a=array_merge($a,['--domains',$name]);if($k==='tcp')$a=array_merge($a,['--tcp16',$name]);
        }
        if($group===6){foreach(['connections'=>'burst','timeout'=>'burst-timeout','gap'=>'burst-gap','profiles'=>'burst-profiles','tls'=>'burst-tls','alpn'=>'burst-alpn','variant'=>'burst-variant'] as $k=>$flag)if(isset($o['burst'][$k]))$a=array_merge($a,['--'.$flag,(string)$o['burst'][$k]]);if($o['burst']['trace']??false)$a[]='--trace';}
        $lines=fn($s)=>array_values(array_filter(explode("\n",$s),fn($s)=>trim($s)!==''&&!str_starts_with(trim($s),'#')));
        $coverage=[];foreach(['domains'=>'domains.txt','tcp'=>'tcp16.json','sni'=>'whitelist_sni.txt','burst_domains'=>'burst-domains.txt','quic_unsupported'=>'quic_unsupported.txt'] as $k=>$name){
            $stock=$k==='tcp'?json_decode($m['files'][$name],true):$lines($m['files'][$name]);
            $coverage[$k]=count($o['targets'][$k]??$stock);
        }
        $coverage['dns']=count($config['DNS_AVAILABILITY_SERVERS']??$m['config']['DNS_AVAILABILITY_SERVERS']);
        $public=$o;unset($public['proxy']);$public['proxy_configured']=$o['proxy']!==null;
        return ['argv'=>$a,'files'=>$files,'coverage'=>$coverage,'public_settings'=>$public];
    }
}
