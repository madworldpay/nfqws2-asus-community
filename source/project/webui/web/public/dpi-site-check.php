<?php
require_once __DIR__.'/dpi-store.php';
require_once __DIR__.'/dpi-terminal-lifecycle.php';
require_once __DIR__.'/public-ipv4.php';

/** Independent control observations. No native report or service is modified. */
final class AsusDpiSiteCheck
{
    public const TARGETS=[
        'facebook-main'=>'www.facebook.com','facebook-mobile'=>'m.facebook.com','facebook-cdn'=>'static.xx.fbcdn.net',
        'youtube-main'=>'www.youtube.com','youtube-images'=>'i.ytimg.com','youtube-static'=>'www.gstatic.com',
        'discord-main'=>'discord.com','discord-cdn'=>'cdn.discordapp.com','discord-gateway'=>'gateway.discord.gg',
    ];
    /** One custom public target, parsed by the existing typed target rules. */
    public static function customTarget(string $target):?array
    {
        if(strlen($target)>4110||preg_match('/^custom-(https|route):([^\r\n]+)$/Du',$target,$m)!==1)return null;
        require_once __DIR__.'/strategy-picker-targets.php';$parsed=NfqwsStrategyPickerTargets::inspectMixed($m[2]);
        if(!$parsed['valid']||count($parsed['hosts'])!==1)return null;$host=$parsed['hosts'][0];
        return ['operation'=>$m[1],'host'=>$host,'kind'=>NfqwsPublicIpv4::test($host)?'ipv4':'domain'];
    }
    /** Overrides belong to trusted local fixtures, never POST or environment. */
    public function __construct(private ?AsusDpiStore $store=null,private ?AsusDpiTerminalLifecycle $terminal=null,private array $deps=[]) {}
    public static function validate(array $post): void
    {
        $keys=array_keys($post);sort($keys);
        if(!in_array($keys,[['cmd','csrf_token','target'],['cmd','csrf_token','dns_scope','target']],true)||($post['cmd']??null)!=='dpisitecheck'||
            !is_string($post['csrf_token'])||strlen($post['csrf_token'])>256||
            !is_string($post['target'])||(!isset(self::TARGETS[$post['target']])&&self::customTarget($post['target'])===null)||
            array_key_exists('dns_scope',$post)&&!in_array($post['dns_scope'],['system_resolver','local_resolver'],true))throw new RuntimeException('invalid_request');
    }
    public static function response(string $outcome,string|null $error=null): array
    {
        return ['outcome'=>$outcome,'http_status'=>null,'bytes_read'=>0,'body_limited'=>false,
            'redirect'=>null,'elapsed_ms'=>null,'error_code'=>$error];
    }
    public function check(string $target,string $dnsScope='system_resolver'): array
    {
        $custom=self::customTarget($target);
        if((!isset(self::TARGETS[$target])&&$custom===null)||!in_array($dnsScope,['system_resolver','local_resolver'],true))throw new RuntimeException('invalid_request');
        $store=$this->store??new AsusDpiStore();$terminal=$this->terminal??new AsusDpiTerminalLifecycle();
        return $store->mutation(function()use($target,$store,$terminal,$dnsScope,$custom){
            return $terminal->idle(function()use($target,$store,$dnsScope,$custom){
                require_once __DIR__.'/dpi-jobs.php';
                if((new AsusDpiJobs($store))->active()!==null)throw new RuntimeException('busy');
                $before=$this->context();$started=time();$clock=self::now();
                $response=$this->boundedProbe($target,$clock,$dnsScope);$addresses=[];$network=null;$dns=['rcode'=>null,'answers'=>[],'reason'=>'unavailable'];
                if($custom!==null){
                    if(isset($response['response'])){$addresses=$response['addresses'];$dns=$response['dns'];$response=$response['response'];}
                    if($custom['operation']==='route')$network=$this->network($addresses[0]??null,$clock+10);
                }
                $response['elapsed_ms']=(int)max(0,round((self::now()-$clock)*1000));
                $finished=time();$after=$this->context();$changed=null;$complete=true;
                foreach(['nfqws','mode','config_sha256'] as $key){
                    $known=$before[$key]!==null&&$after[$key]!==null&&$before[$key]!=='unknown'&&$after[$key]!=='unknown';
                    if(!$known)$complete=false;elseif($before[$key]!==$after[$key])$changed=true;
                }
                if($changed!==true&&$complete)$changed=false;
                $report=['type'=>'nfqws2_dpi_site_check','schema_version'=>$custom===null?1:2,'target'=>$target,'url'=>'https://'.($custom['host']??self::TARGETS[$target]).'/',
                    'started_at'=>$started,'finished_at'=>$finished,'context'=>['before'=>$before,'after'=>$after,'changed'=>$changed],
                    'response'=>$response,'full_service_verified'=>false,'dns_scope'=>$dnsScope];
                return $custom===null?$report:$report+$custom+['addresses'=>$addresses,'network'=>$network,'dns'=>$dns];
            });
        });
    }
    /** Numeric-only, read-only commands; run() owns each exact child handle. */
    private function network(?string $ip,float $deadline):array
    {
        $out=[];$busybox=NfqwsPlatform::busybox();
        $commands=['ping'=>[$busybox,'ping','-n','-c','3','-W','1','-i','0.2',$ip],
            'route'=>[$busybox,'ip','-4','route','get',$ip],
            'trace'=>[$busybox,'traceroute','-n','-m','12','-q','1','-w','1',$ip]];
        foreach($commands as $kind=>$argv){
            $left=$deadline-self::now();$limit=$kind==='trace'?6144:1536;
            if($ip===null||!NfqwsPublicIpv4::test($ip)||$left<=0){$out[$kind]=['state'=>'not_run','output'=>''];continue;}
            $seconds=min($kind==='ping'?3.0:($kind==='route'?1.0:5.0),$left);
            $r=isset($this->deps['network_run'])?($this->deps['network_run'])($argv,$seconds,$limit):NfqwsPlatform::run($argv,$seconds,[],$limit);
            if(!is_array($r)||!is_int($r['status']??null)||!is_array($r['output']??null)){$out[$kind]=['state'=>'unavailable','output'=>''];continue;}
            $text=substr(preg_replace('/[^\x09\x0a\x0d\x20-\x7e]/','?',implode("\n",$r['output'])),0,$limit);
            $out[$kind]=['state'=>$r['status']===0?'done':($text!==''?'partial':'unavailable'),'output'=>$text];
        }
        return $out;
    }
    private static function now(): float {$t=hrtime();return $t[0]+$t[1]/1e9;}
    private function boundedProbe(string $target,float $started,string $dnsScope): array
    {
        if(!function_exists('proc_open')||!function_exists('proc_terminate'))return self::response('unavailable','unsupported_runtime');
        $seconds=min(10.0,max(0.01,(float)($this->deps['deadline_seconds']??10)));$deadline=$started+$seconds;
        $argv=isset($this->deps['worker_argv'])?($this->deps['worker_argv'])($target,$dnsScope):
            [NfqwsPlatform::translate('/opt/bin/php-cgi'),'-q','-d','register_argc_argv=1','-f',__FILE__,'--','--worker',$target,$dnsScope];
        $proc=null;$pipes=[];$out='';$tooLarge=false;
        try{
            $proc=@proc_open($argv,[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['file','/dev/null','a']],$pipes,'/',
                ['PATH'=>NfqwsPlatform::native()?'/usr/sbin:/usr/bin:/sbin:/bin':'/opt/bin:/usr/bin:/bin','HOME'=>'/','LANG'=>'C'],['bypass_shell'=>true]);
            if(!is_resource($proc))return self::response('unavailable','launch_failed');
            stream_set_blocking($pipes[1],false);
            while(true){
                if(self::now()>=$deadline)return self::response('timeout','deadline');
                $part=@fread($pipes[1],8193-strlen($out));
                if($part===false)return self::response('unavailable','invalid_probe_result');
                $out.=$part;if(strlen($out)>8192){$tooLarge=true;break;}
                $status=proc_get_status($proc);
                if(!$status['running']){
                    // Drain the bounded pipe after exit; never accept a partial JSON prefix.
                    $out.=(string)stream_get_contents($pipes[1],8193-strlen($out));
                    if(strlen($out)>8192)$tooLarge=true;
                    if($status['exitcode']!==0)return self::response('unavailable','probe_failed');
                    break;
                }
                $read=[$pipes[1]];$write=null;$except=null;$wait=min(0.02,max(0,$deadline-self::now()));
                @stream_select($read,$write,$except,0,(int)($wait*1000000));
            }
            if($tooLarge)return self::response('unavailable','output_limit');
            $value=json_decode($out,true,8);
            $custom=self::customTarget($target);
            if($custom!==null){
                if(!is_array($value)||array_keys($value)!==['host','kind','operation','addresses','dns','response']||
                    $value['host']!==$custom['host']||$value['kind']!==$custom['kind']||$value['operation']!==$custom['operation']||
                    !is_array($value['addresses'])||!array_is_list($value['addresses'])||count($value['addresses'])>16||
                    !self::validResponse($value['response'])||!self::validDns($value['dns']))return self::response('unavailable','invalid_probe_result');
                foreach($value['addresses']as $ip)if(!NfqwsPublicIpv4::test($ip))return self::response('unavailable','invalid_probe_result');
                if($custom['kind']==='ipv4'&&$value['addresses']!==[$custom['host']])return self::response('unavailable','invalid_probe_result');
            }elseif(!self::validResponse($value))return self::response('unavailable','invalid_probe_result');
            return $value;
        }catch(Throwable $e){return self::response('unavailable','probe_failed');}
        finally{
            // proc_open owns this exact child. No PID files, process groups or
            // unrelated router/user processes are signalled.
            if(is_resource($proc)){
                if(proc_get_status($proc)['running'])@proc_terminate($proc,9);
                foreach($pipes as $pipe)if(is_resource($pipe))fclose($pipe);
                proc_close($proc);
            }
        }
    }
    private static function validDns(mixed $v):bool
    {
        if(!is_array($v)||array_keys($v)!==['rcode','answers','reason']||
            !($v['rcode']===null||(is_int($v['rcode'])&&$v['rcode']>=0&&$v['rcode']<=15))||
            !is_array($v['answers'])||!array_is_list($v['answers'])||count($v['answers'])>64||
            !in_array($v['reason'],['not_requested','ready','no_address','rcode','timed_out','invalid_response','invalid_arguments','system_answer','system_no_address','answer_limit','unavailable'],true))return false;
        foreach($v['answers']as$ip)if(!is_string($ip)||filter_var($ip,FILTER_VALIDATE_IP,FILTER_FLAG_IPV4)===false)return false;
        return true;
    }
    private static function validResponse(mixed $v): bool
    {
        if(!is_array($v))return false;$keys=array_keys($v);sort($keys);
        if($keys!==['body_limited','bytes_read','elapsed_ms','error_code','http_status','outcome','redirect'])return false;
        return in_array($v['outcome'],['response','timeout','tls_error','connection_error','read_limited','unavailable','blocked_address'],true)&&
            ($v['http_status']===null||(is_int($v['http_status'])&&$v['http_status']>=100&&$v['http_status']<=599))&&
            is_int($v['bytes_read'])&&$v['bytes_read']>=0&&$v['bytes_read']<=262144&&is_bool($v['body_limited'])&&
            ($v['redirect']===null||(is_string($v['redirect'])&&strlen($v['redirect'])<=2048&&!preg_match('/[^\x20-\x7e]/',$v['redirect'])))&&
            ($v['error_code']===null||(is_string($v['error_code'])&&preg_match('/^[a-z][a-z0-9_]{0,63}$/D',$v['error_code'])))&&
            $v['elapsed_ms']===null&&($v['body_limited']===($v['outcome']==='read_limited'))&&
            (!in_array($v['outcome'],['response','read_limited'],true)||$v['http_status']!==null);
    }
    private function context(): array
    {
        $value=['nfqws'=>'unknown','mode'=>'unknown','config_sha256'=>null];
        $proc=$this->deps['proc_root']??'/proc';$entries=@scandir($proc);$readable=true;
        if(is_array($entries)){
            $value['nfqws']='stopped';
            foreach($entries as $entry)if(preg_match('/^[0-9]+$/D',$entry)){
                $name=@file_get_contents($proc.'/'.$entry.'/comm',false,null,0,64);
                if($name===false){if(is_dir($proc.'/'.$entry))$readable=false;continue;}
                if(in_array(trim($name),['nfqws','nfqws2'],true)){$value['nfqws']='running';break;}
            }
            if($value['nfqws']!=='running'&&!$readable)$value['nfqws']='unknown';
        }
        $path=$this->deps['config_path']??NfqwsPlatform::translate('/opt/etc/nfqws2/nfqws2.conf');
        clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||($s['mode']&0170000)!==0100000||$s['size']>262144)return $value;
        $f=@fopen($path,'rb');if(!$f)return $value;
        try{
            $a=fstat($f);if($a['ino']!==$s['ino']||$a['dev']!==$s['dev'])return $value;
            $raw=stream_get_contents($f,262145);if(!is_string($raw)||strlen($raw)>262144)return $value;
            $value['config_sha256']=hash('sha256',$raw);$value['mode']=self::mode($raw);
        }finally{fclose($f);}
        return $value;
    }
    /** A conservative assignment scanner: quoted multiline strategy text is
     * data. Only one literal expanding reference selects a recognized mode. */
    private static function mode(string $raw): string
    {
        if(str_contains($raw,"\0"))return 'unknown';$lines=explode("\n",$raw);$seen=[];$mode='unknown';$literals=[];
        for($i=0;$i<count($lines);$i++){
            $line=$lines[$i];if(trim($line)===''||str_starts_with(ltrim($line),'#'))continue;
            if(!preg_match('/^\h*(?:export\h+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$/D',$line,$m)||isset($seen[$m[1]]))return 'unknown';
            $key=$m[1];$seen[$key]=true;$tail=$m[2];$quote=$tail[0]??'';$body='';
            if($quote==='"'||$quote==="'"){
                $tail=substr($tail,1);$closed=false;$at=0;
                while(true){
                    for(;$at<strlen($tail);$at++){
                        $c=$tail[$at];
                        if($c==='\\'&&$quote==='"'){
                            if(!isset($tail[$at+1]))return 'unknown';$body.=$c.$tail[++$at];continue;
                        }
                        if($c===$quote){$closed=true;$at++;break;}$body.=$c;
                    }
                    if($closed||$i+1>=count($lines))break;$tail.="\n".$lines[++$i];
                }
                if(!$closed||!preg_match('/^\h*(?:#.*)?$/D',substr($tail,$at)))return 'unknown';
            }else{
                if(!preg_match('/^([^\s;|&`]*)(?:\h+#.*)?\h*$/D',$tail,$m))return 'unknown';$body=$m[1];
            }
            if($key==='NFQWS_EXTRA_ARGS'&&$quote!=="'"&&preg_match('/^\$(?:MODE_(AUTO|ALL|LIST)|\{MODE_(AUTO|ALL|LIST)\})$/D',$body,$m))
                $mode=strtolower(($m[1]??'')!==''?$m[1]:$m[2]);
            // Never evaluate shell expansions or escapes to infer a literal mode.
            if($body!==''&&strpbrk($body,'$`\\')===false)$literals[$key]=$body;
        }
        if($mode==='unknown'&&isset($literals['NFQWS_EXTRA_ARGS'])){
            $matches=[];foreach(['AUTO','ALL','LIST']as$name)
                if(isset($literals['MODE_'.$name])&&$literals['MODE_'.$name]===$literals['NFQWS_EXTRA_ARGS'])$matches[]=strtolower($name);
            if(count($matches)===1)$mode=$matches[0];
        }
        return $mode;
    }
}

/** One child performs DNS, TLS and bounded HTTP reads. It starts no children. */
final class AsusDpiSiteCheckProbe
{
    public const PINNED_FINGERPRINT='php-openssl-pinned-https-v1';
    public const MIXED_PINNED_FINGERPRINT='php-openssl-pinned-public-targets-v2';
    private float $deadline;
    private array $response;
    private int $headerBytes=0;
    private array $dnsObservation=['rcode'=>null,'answers'=>[],'reason'=>'not_requested'];
    public function __construct(private array $deps=[]) {}
    private static function now(): float {$t=hrtime();return $t[0]+$t[1]/1e9;}
    private function remaining(): float
    {$left=$this->deadline-self::now();if($left<=0)throw new RuntimeException('deadline');return $left;}
    /** Reject all special-use IPv4 blocks conservatively, including CGNAT and
     * global exceptions within special registries. Compare bytes for 32-bit PHP. */
    private static function publicAddress(mixed $ip): bool
    {
        return NfqwsPublicIpv4::test($ip);
    }
    public function run(string $target,string $dnsScope='system_resolver'): array
    {
        if(!in_array($dnsScope,['system_resolver','local_resolver'],true))throw new RuntimeException('invalid_request');
        $custom=AsusDpiSiteCheck::customTarget($target);if($custom!==null)return $this->custom($custom,$dnsScope);
        if(!isset(AsusDpiSiteCheck::TARGETS[$target]))throw new RuntimeException('invalid_request');
        return $this->perform(AsusDpiSiteCheck::TARGETS[$target],$dnsScope,null,'auto',10);
    }
    private function resolve(string $host,string $dnsScope):array|false
    {
        if($dnsScope==='local_resolver'){
            require_once __DIR__.'/openwrt-dns-probe.php';
            $timeout=(int)max(1,min(2500,floor($this->remaining()*1000)));
            $dns=NfqwsOpenWrtDnsProbe::query('127.0.0.1',$this->deps['dns_port']??53,$host,'A','udp',$timeout);
            if(($dns['truncated']??false)===true){
                $timeout=(int)max(1,min(2500,floor($this->remaining()*1000)));
                $dns=NfqwsOpenWrtDnsProbe::query('127.0.0.1',$this->deps['dns_port']??53,$host,'A','tcp',$timeout);
            }
            $this->dnsObservation=['rcode'=>($dns['rcode']??-1)>=0?$dns['rcode']:null,'answers'=>$dns['answers']??[],'reason'=>$dns['reason']??'unavailable'];
            return ($dns['ok']??false)===true?$dns['answers']:[];
        }
        $answer=isset($this->deps['resolve'])?($this->deps['resolve'])($host):gethostbynamel($host);
        $this->dnsObservation=['rcode'=>null,'answers'=>is_array($answer)?array_values($answer):[],'reason'=>$answer?'system_answer':'system_no_address'];
        if(count($this->dnsObservation['answers'])>64){$this->dnsObservation=['rcode'=>null,'answers'=>[],'reason'=>'answer_limit'];return [];}
        return $answer;
    }
    private function custom(array $target,string $dnsScope):array
    {
        $this->deadline=self::now()+10;$addresses=[];$this->dnsObservation=['rcode'=>null,'answers'=>[],'reason'=>'not_requested'];$response=AsusDpiSiteCheck::response('unavailable','not_requested');
        try{
            $answer=$target['kind']==='ipv4'?[$target['host']]:$this->resolve($target['host'],$dnsScope);$this->remaining();
            if(!is_array($answer)||$answer===[])$response=AsusDpiSiteCheck::response('connection_error','dns_failed');
            else{
                $addresses=NfqwsStrategyPickerTargets::addresses($answer);
                if($target['operation']==='https')$response=$this->perform($target['host'],$dnsScope,$addresses,'auto',min(8.0,$this->remaining()),$target['kind']==='ipv4');
            }
        }catch(Throwable $e){
            $code=$e->getMessage();$response=AsusDpiSiteCheck::response($code==='deadline'?'timeout':($code==='custom_non_public_address'?'blocked_address':'unavailable'),
                $code==='deadline'?'deadline':($code==='custom_non_public_address'?'non_public_address':($code==='custom_dns_answer_too_large'?'dns_answer_too_large':'probe_failed')));
        }
        return ['host'=>$target['host'],'kind'=>$target['kind'],'operation'=>$target['operation'],'addresses'=>$addresses,'dns'=>$this->dnsObservation,'response'=>$response];
    }
    /** Separate OpenSSL observation, not a native Rustls/QUIC or service test.
     * The caller supplies one complete, already resolved answer; never re-resolve. */
    public function pinned(string $host,array $answer,string $tlsMode,float $seconds=8): array
    {
        require_once __DIR__.'/strategy-picker-targets.php';
        $target=NfqwsStrategyPickerTargets::inspect($host);
        if(!$target['valid']||$target['hosts']!==[$host]||!in_array($tlsMode,['tls12','tls13'],true)||
            !is_finite($seconds)||$seconds<=0||$seconds>8)throw new RuntimeException('invalid_request');
        $addresses=NfqwsStrategyPickerTargets::addresses($answer);
        return $this->perform($host,'system_resolver',$addresses,$tlsMode,$seconds);
    }
    /** Explicit typed v2 entry point; the v1 domain contract remains closed to IPs. */
    public function pinnedTarget(array $target,array $answer,string $tlsMode,float $seconds=8):array
    {
        require_once __DIR__.'/strategy-picker-targets.php';
        $keys=array_keys($target);sort($keys);
        if($keys!==['host','kind']||!is_string($target['host'])||!in_array($target['kind'],['domain','ipv4'],true)||
            !in_array($tlsMode,['tls12','tls13'],true)||!is_finite($seconds)||$seconds<=0||$seconds>8)
            throw new RuntimeException('invalid_request');
        $host=$target['host'];$literal=$target['kind']==='ipv4';
        if($literal){
            if(!NfqwsPublicIpv4::test($host)||$answer!==[$host])throw new RuntimeException('invalid_request');
        }else{
            $parsed=NfqwsStrategyPickerTargets::inspect($host);
            if(!$parsed['valid']||$parsed['hosts']!==[$host])throw new RuntimeException('invalid_request');
        }
        $addresses=NfqwsStrategyPickerTargets::addresses($answer);
        return $this->perform($host,'system_resolver',$addresses,$tlsMode,$seconds,$literal);
    }
    /** A bounded DER reader for the captured, already chain-verified certificate.
     * OpenSSL's display string cannot distinguish an IP SAN from DNS text that
     * contains ", IP Address:". PHP's generic name check also accepts numeric
     * DNS SANs and legacy CNs, so literal v2 additionally requires tag [7]. */
    private static function derValue(string $der,int &$at,?int $expected=null):array
    {
        $size=strlen($der);
        if($at+2>$size)throw new RuntimeException('invalid_certificate');
        $tag=ord($der[$at++]);$length=ord($der[$at++]);
        if(($tag&31)===31||$expected!==null&&$tag!==$expected)throw new RuntimeException('invalid_certificate');
        if($length&128){
            $bytes=$length&127;
            if($bytes<1||$bytes>3||$at+$bytes>$size||ord($der[$at])===0)throw new RuntimeException('invalid_certificate');
            $length=0;for($i=0;$i<$bytes;$i++)$length=$length*256+ord($der[$at++]);
            if($length<128)throw new RuntimeException('invalid_certificate');
        }
        if($length>$size-$at)throw new RuntimeException('invalid_certificate');
        $value=substr($der,$at,$length);$at+=$length;return [$tag,$value];
    }
    private static function hasIpSan(mixed $certificate,string $host):bool
    {
        try{
            if($certificate===null||!openssl_x509_export($certificate,$pem)||strlen($pem)>262144||
                !preg_match('~\A-----BEGIN CERTIFICATE-----\s+([A-Za-z0-9+/=\r\n]+)-----END CERTIFICATE-----\s*\z~D',$pem,$m))return false;
            $der=base64_decode(str_replace(["\r","\n"],'',$m[1]),true);
            if(!is_string($der)||strlen($der)>131072)return false;
            $at=0;[, $outer]=self::derValue($der,$at,0x30);if($at!==strlen($der))return false;
            $at=0;[, $tbs]=self::derValue($outer,$at,0x30);
            $at=0;if(isset($tbs[0])&&ord($tbs[0])===0xa0)self::derValue($tbs,$at,0xa0);
            foreach([0x02,0x30,0x30,0x30,0x30,0x30]as $tag)self::derValue($tbs,$at,$tag);
            $extensions=null;
            while($at<strlen($tbs)){
                [$tag,$value]=self::derValue($tbs,$at);
                if($tag===0xa3){if($extensions!==null||$at!==strlen($tbs))return false;$extensions=$value;}
                elseif(!in_array($tag,[0x81,0x82],true))return false;
            }
            if($extensions===null)return false;
            $at=0;[, $list]=self::derValue($extensions,$at,0x30);if($at!==strlen($extensions))return false;
            $at=0;$seen=false;$match=false;$packed=pack('C4',...array_map('intval',explode('.',$host)));
            while($at<strlen($list)){
                [, $extension]=self::derValue($list,$at,0x30);$i=0;
                [, $oid]=self::derValue($extension,$i,0x06);
                if(isset($extension[$i])&&ord($extension[$i])===0x01){
                    [, $critical]=self::derValue($extension,$i,0x01);
                    if($critical!=="\x00"&&$critical!=="\xff")return false;
                }
                [, $value]=self::derValue($extension,$i,0x04);if($i!==strlen($extension))return false;
                if($oid!=="\x55\x1d\x11")continue;
                if($seen)return false;$seen=true;
                $i=0;[, $names]=self::derValue($value,$i,0x30);if($i!==strlen($value))return false;
                $i=0;
                while($i<strlen($names)){
                    [$tag,$name]=self::derValue($names,$i);
                    if(!in_array($tag,[0xa0,0x81,0x82,0xa3,0xa4,0xa5,0x86,0x87,0x88],true))return false;
                    if($tag===0x87){
                        if(!in_array(strlen($name),[4,16],true))return false;
                        if($name===$packed)$match=true;
                    }
                }
            }
            return $seen&&$match;
        }catch(Throwable $e){return false;}
    }
    private function perform(string $host,string $dnsScope,?array $pinnedAddresses,string $tlsMode,float $seconds,bool $literal=false): array
    {
        $this->deadline=self::now()+$seconds;$this->headerBytes=0;
        $this->response=AsusDpiSiteCheck::response('connection_error','connection_failed');$f=null;$warning='';
        set_error_handler(static function($severity,$message)use(&$warning){$warning=substr($warning.' '.$message,0,4096);return true;});
        try{
            if(!extension_loaded('openssl'))return AsusDpiSiteCheck::response('unavailable','https_unavailable');
            $ca=$this->deps['ca']??NfqwsPlatform::translate('/opt/etc/ssl/certs/ca-certificates.crt');
            if(!is_readable($ca))return AsusDpiSiteCheck::response('tls_error','ca_unavailable');
            if($pinnedAddresses!==null)$addresses=$pinnedAddresses;
            else $addresses=$this->resolve($host,$dnsScope);
            $this->remaining();
            if(!is_array($addresses)||$addresses===[])return AsusDpiSiteCheck::response('connection_error','dns_failed');
            // Reject the whole answer, rather than skipping poisoned entries.
            foreach($addresses as $address)if(!self::publicAddress($address))return AsusDpiSiteCheck::response('blocked_address','non_public_address');
            $ssl=['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false,
                'peer_name'=>$host,'SNI_enabled'=>!$literal,'cafile'=>$ca,'disable_compression'=>true];
            if($literal)$ssl['capture_peer_cert']=true;
            if($tlsMode!=='auto'){
                $method=$tlsMode==='tls12'?'STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT':'STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT';
                if(!defined($method))return AsusDpiSiteCheck::response('unavailable','tls_version_unavailable');
                $ssl['crypto_method']=constant($method);
            }
            $context=stream_context_create(['ssl'=>$ssl]);
            $endpoint='tls://'.$addresses[0].':443';$errno=0;$error='';
            $f=isset($this->deps['open'])?($this->deps['open'])($endpoint,$context,$this->remaining()):
                stream_socket_client($endpoint,$errno,$error,$this->remaining(),STREAM_CLIENT_CONNECT,$context);
            if(!is_resource($f)){
                $tls=preg_match('/certificate|crypto|SSL operation|TLS (?:alert|handshake)|peer name/i',$warning.' '.$error)===1;
                return AsusDpiSiteCheck::response($tls?'tls_error':'connection_error',$tls?'tls_verification_failed':'connection_failed');
            }
            if($tlsMode!=='auto'&&(stream_get_meta_data($f)['crypto']['protocol']??null)!==($tlsMode==='tls12'?'TLSv1.2':'TLSv1.3'))
                return AsusDpiSiteCheck::response('tls_error','tls_version_mismatch');
            if($literal&&!self::hasIpSan(stream_context_get_options($f)['ssl']['peer_certificate']??null,$host))
                return AsusDpiSiteCheck::response('tls_error','tls_verification_failed');
            $this->timeout($f);
            $request="GET / HTTP/1.1\r\nHost: ".$host."\r\nUser-Agent: NFQWS2-Control/1\r\nAccept: */*\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n";
            for($at=0;$at<strlen($request);){$n=fwrite($f,substr($request,$at));if(!$n)throw new RuntimeException('write_failed');$at+=$n;$this->timeout($f);}
            $headers=[];
            for($interim=0;$interim<6;$interim++){
                $status=$this->line($f);
                if(!preg_match('~^HTTP/1\.[01] ([1-5][0-9]{2})(?: [^\r\n]*)?\r\n$~D',$status,$m))throw new RuntimeException('invalid_http');
                $code=(int)$m[1];$headers=$this->headers($f);
                if($code>=200){$this->response['http_status']=$code;break;}
                if($code===101||$interim===5)throw new RuntimeException('invalid_http');
            }
            if(isset($headers['location']))$this->response['redirect']=substr(preg_replace('/[^\x20-\x7e]/','',$headers['location']),0,2048);
            $chunked=isset($headers['transfer-encoding']);$length=null;
            if($chunked&&strtolower($headers['transfer-encoding'])!=='chunked')throw new RuntimeException('invalid_http');
            if(isset($headers['content-length'])){
                if($chunked||!preg_match('/^[0-9]{1,18}$/D',$headers['content-length']))throw new RuntimeException('invalid_http');
                $length=(int)min(262145,(float)$headers['content-length']);
            }
            if(!in_array($this->response['http_status'],[204,304],true)){
                if($chunked)$this->chunks($f);elseif($length!==null)$this->body($f,$length);else $this->body($f,null);
            }
            if($this->response['body_limited']){$this->response['outcome']='read_limited';$this->response['error_code']='body_limit';}
            else{$this->response['outcome']='response';$this->response['error_code']=null;}
            return $this->response;
        }catch(Throwable $e){
            $code=$e->getMessage();$timeout=$code==='deadline';
            $this->response['outcome']=$timeout?'timeout':'connection_error';$this->response['body_limited']=false;
            $this->response['error_code']=in_array($code,['deadline','write_failed','invalid_http','header_limit','incomplete_body','invalid_chunk','read_failed'],true)?$code:'connection_failed';
            return $this->response;
        }finally{if(is_resource($f))fclose($f);restore_error_handler();}
    }
    private function timeout($f): void
    {$seconds=$this->remaining();stream_set_timeout($f,(int)$seconds,(int)(($seconds-(int)$seconds)*1000000));}
    private function line($f): string
    {
        $this->timeout($f);$line=fgets($f,8193);
        if(stream_get_meta_data($f)['timed_out'])throw new RuntimeException('deadline');
        if(!is_string($line)||!str_ends_with($line,"\r\n"))throw new RuntimeException('invalid_http');
        $this->headerBytes+=strlen($line);if($this->headerBytes>32768)throw new RuntimeException('header_limit');return $line;
    }
    private function headers($f): array
    {
        $headers=[];
        while(($line=$this->line($f))!=="\r\n"){
            if(!preg_match('/^([!#$%&\'*+.^_`|~0-9A-Za-z-]+):[\t ]*([^\r\n]*)\r\n$/D',$line,$m))throw new RuntimeException('invalid_http');
            $name=strtolower($m[1]);
            if(isset($headers[$name])&&in_array($name,['content-length','transfer-encoding','location'],true))throw new RuntimeException('invalid_http');
            $headers[$name]=trim($m[2]);
        }
        return $headers;
    }
    private function read($f,int $count): string
    {
        $this->timeout($f);$raw=fread($f,$count);$meta=stream_get_meta_data($f);
        if($meta['timed_out'])throw new RuntimeException('deadline');
        if($raw===false)throw new RuntimeException('read_failed');return $raw;
    }
    private function body($f,?int $length): void
    {
        $left=$length;
        while($left===null||$left>0){
            $capacity=262144-$this->response['bytes_read'];
            if($capacity===0){$this->response['body_limited']=true;return;}
            $raw=$this->read($f,min(8192,$capacity,$left??8192));
            if($raw===''){
                if($left!==null)throw new RuntimeException('incomplete_body');
                if(feof($f))return;throw new RuntimeException('read_failed');
            }
            $this->response['bytes_read']+=strlen($raw);if($left!==null)$left-=strlen($raw);
        }
    }
    private function chunks($f): void
    {
        while(true){
            if(!preg_match('/^([0-9a-fA-F]{1,12})(?:;[^\r\n]*)?\r\n$/D',$this->line($f),$m))throw new RuntimeException('invalid_chunk');
            $size=(int)min(262145,(float)hexdec($m[1]));
            if($size===0){$this->headers($f);return;}
            $this->body($f,$size);if($this->response['body_limited'])return;
            $ending='';while(strlen($ending)<2){$part=$this->read($f,2-strlen($ending));if($part==='')throw new RuntimeException('incomplete_body');$ending.=$part;}
            if($ending!=="\r\n")throw new RuntimeException('invalid_chunk');
        }
    }
}

// The same packaged file is a CLI-only child entry. Direct HTTP access cannot
// activate it, and neither target nor worker settings come from the environment.
if(realpath($_SERVER['SCRIPT_FILENAME']??($argv[0]??''))===__FILE__){
    if(isset($_SERVER['REQUEST_METHOD'])||isset($_SERVER['REMOTE_ADDR'])||!in_array(PHP_SAPI,['cli','cgi-fcgi'],true))exit(1);
    $args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);
    if(!in_array(count($args),[2,3],true)||$args[0]!=='--worker'||(!isset(AsusDpiSiteCheck::TARGETS[$args[1]])&&AsusDpiSiteCheck::customTarget($args[1])===null)||
        isset($args[2])&&!in_array($args[2],['system_resolver','local_resolver'],true))exit(2);
    echo json_encode((new AsusDpiSiteCheckProbe())->run($args[1],$args[2]??'system_resolver'),JSON_THROW_ON_ERROR);
}
