<?php
require_once __DIR__.'/dpi-store.php';
require_once __DIR__.'/dpi-terminal-lifecycle.php';

/** Independent control observations. No native report or service is modified. */
final class AsusDpiSiteCheck
{
    public const TARGETS=[
        'facebook-main'=>'www.facebook.com','facebook-mobile'=>'m.facebook.com','facebook-cdn'=>'static.xx.fbcdn.net',
        'youtube-main'=>'www.youtube.com','youtube-images'=>'i.ytimg.com','youtube-static'=>'www.gstatic.com',
        'discord-main'=>'discord.com','discord-cdn'=>'cdn.discordapp.com','discord-gateway'=>'gateway.discord.gg',
    ];
    /** Overrides belong to trusted local fixtures, never POST or environment. */
    public function __construct(private ?AsusDpiStore $store=null,private ?AsusDpiTerminalLifecycle $terminal=null,private array $deps=[]) {}
    public static function validate(array $post): void
    {
        $keys=array_keys($post);sort($keys);
        if($keys!==['cmd','csrf_token','target']||($post['cmd']??null)!=='dpisitecheck'||
            !is_string($post['csrf_token'])||strlen($post['csrf_token'])>256||
            !is_string($post['target'])||!isset(self::TARGETS[$post['target']]))throw new RuntimeException('invalid_request');
    }
    public static function response(string $outcome,string|null $error=null): array
    {
        return ['outcome'=>$outcome,'http_status'=>null,'bytes_read'=>0,'body_limited'=>false,
            'redirect'=>null,'elapsed_ms'=>null,'error_code'=>$error];
    }
    public function check(string $target): array
    {
        if(!isset(self::TARGETS[$target]))throw new RuntimeException('invalid_request');
        $store=$this->store??new AsusDpiStore();$terminal=$this->terminal??new AsusDpiTerminalLifecycle();
        return $store->mutation(function()use($target,$store,$terminal){
            return $terminal->idle(function()use($target,$store){
                require_once __DIR__.'/dpi-jobs.php';
                if((new AsusDpiJobs($store))->active()!==null)throw new RuntimeException('busy');
                $before=$this->context();$started=time();$clock=self::now();
                $response=$this->boundedProbe($target,$clock);
                $response['elapsed_ms']=(int)max(0,round((self::now()-$clock)*1000));
                $finished=time();$after=$this->context();$changed=null;$complete=true;
                foreach(['nfqws','mode','config_sha256'] as $key){
                    $known=$before[$key]!==null&&$after[$key]!==null&&$before[$key]!=='unknown'&&$after[$key]!=='unknown';
                    if(!$known)$complete=false;elseif($before[$key]!==$after[$key])$changed=true;
                }
                if($changed!==true&&$complete)$changed=false;
                return ['type'=>'nfqws2_dpi_site_check','schema_version'=>1,'target'=>$target,'url'=>'https://'.self::TARGETS[$target].'/',
                    'started_at'=>$started,'finished_at'=>$finished,'context'=>['before'=>$before,'after'=>$after,'changed'=>$changed],
                    'response'=>$response,'full_service_verified'=>false,'dns_scope'=>'system_resolver'];
            });
        });
    }
    private static function now(): float {$t=hrtime();return $t[0]+$t[1]/1e9;}
    private function boundedProbe(string $target,float $started): array
    {
        if(!function_exists('proc_open')||!function_exists('proc_terminate'))return self::response('unavailable','unsupported_runtime');
        $seconds=min(10.0,max(0.01,(float)($this->deps['deadline_seconds']??10)));$deadline=$started+$seconds;
        $argv=isset($this->deps['worker_argv'])?($this->deps['worker_argv'])($target):
            [NfqwsPlatform::translate('/opt/bin/php-cgi'),'-q','-d','register_argc_argv=1','-f',__FILE__,'--','--worker',$target];
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
            if(!self::validResponse($value))return self::response('unavailable','invalid_probe_result');
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
        if(str_contains($raw,"\0"))return 'unknown';$lines=explode("\n",$raw);$seen=[];$mode='unknown';
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
        }
        return $mode;
    }
}

/** One child performs DNS, TLS and bounded HTTP reads. It starts no children. */
final class AsusDpiSiteCheckProbe
{
    private float $deadline;
    private array $response;
    private int $headerBytes=0;
    public function __construct(private array $deps=[]) {}
    private static function now(): float {$t=hrtime();return $t[0]+$t[1]/1e9;}
    private function remaining(): float
    {$left=$this->deadline-self::now();if($left<=0)throw new RuntimeException('deadline');return $left;}
    /** Reject all special-use IPv4 blocks conservatively, including CGNAT and
     * global exceptions within special registries. Compare bytes for 32-bit PHP. */
    private static function publicAddress(mixed $ip): bool
    {
        if(!is_string($ip)||!preg_match('/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/D',$ip))return false;
        $packed=@inet_pton($ip);if($packed===false||strlen($packed)!==4||inet_ntop($packed)!==$ip)return false;
        foreach([['0.0.0.0',8],['10.0.0.0',8],['100.64.0.0',10],['127.0.0.0',8],['169.254.0.0',16],['172.16.0.0',12],
            ['192.0.0.0',24],['192.0.2.0',24],['192.31.196.0',24],['192.52.193.0',24],['192.88.99.0',24],['192.168.0.0',16],
            ['192.175.48.0',24],['198.18.0.0',15],['198.51.100.0',24],['203.0.113.0',24],['224.0.0.0',4],['240.0.0.0',4]] as [$network,$bits]){
            $base=inet_pton($network);$whole=intdiv($bits,8);$rest=$bits%8;
            if(substr($packed,0,$whole)===substr($base,0,$whole)&&($rest===0||((ord($packed[$whole])^ord($base[$whole]))>>(8-$rest))===0))return false;
        }
        return true;
    }
    public function run(string $target): array
    {
        if(!isset(AsusDpiSiteCheck::TARGETS[$target]))throw new RuntimeException('invalid_request');
        $this->deadline=self::now()+10;$this->response=AsusDpiSiteCheck::response('connection_error','connection_failed');$f=null;
        $host=AsusDpiSiteCheck::TARGETS[$target];$warning='';
        set_error_handler(static function($severity,$message)use(&$warning){$warning=substr($warning.' '.$message,0,4096);return true;});
        try{
            if(!extension_loaded('openssl'))return AsusDpiSiteCheck::response('unavailable','https_unavailable');
            $ca=$this->deps['ca']??NfqwsPlatform::translate('/opt/etc/ssl/certs/ca-certificates.crt');
            if(!is_readable($ca))return AsusDpiSiteCheck::response('tls_error','ca_unavailable');
            $addresses=isset($this->deps['resolve'])?($this->deps['resolve'])($host):gethostbynamel($host);
            $this->remaining();
            if(!is_array($addresses)||$addresses===[])return AsusDpiSiteCheck::response('connection_error','dns_failed');
            // Reject the whole answer, rather than skipping poisoned entries.
            foreach($addresses as $address)if(!self::publicAddress($address))return AsusDpiSiteCheck::response('blocked_address','non_public_address');
            $context=stream_context_create(['ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false,
                'peer_name'=>$host,'SNI_enabled'=>true,'cafile'=>$ca,'disable_compression'=>true]]);
            $endpoint='tls://'.$addresses[0].':443';$errno=0;$error='';
            $f=isset($this->deps['open'])?($this->deps['open'])($endpoint,$context,$this->remaining()):
                stream_socket_client($endpoint,$errno,$error,$this->remaining(),STREAM_CLIENT_CONNECT,$context);
            if(!is_resource($f)){
                $tls=preg_match('/certificate|crypto|SSL operation|TLS (?:alert|handshake)|peer name/i',$warning.' '.$error)===1;
                return AsusDpiSiteCheck::response($tls?'tls_error':'connection_error',$tls?'tls_verification_failed':'connection_failed');
            }
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
    if(count($args)!==2||$args[0]!=='--worker'||!isset(AsusDpiSiteCheck::TARGETS[$args[1]]))exit(2);
    echo json_encode((new AsusDpiSiteCheckProbe())->run($args[1]),JSON_THROW_ON_ERROR);
}
