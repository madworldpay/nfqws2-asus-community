<?php
require_once __DIR__.'/platform.php';
/** Fixed operator config; neither status nor construction makes a network call. */
class AsusSupportMail
{
    private string $configPath;
    private string $caPath;
    public function __construct(?string $configPath=null,?string $caPath=null,private int $owner=0,private ?array $locationCommand=null,private float $locationSeconds=5,private ?array $locationGuard=null)
    {
        $this->configPath=$configPath??NfqwsPlatform::translate('/opt/etc/nfqws-asus-web/support-relay.json');
        $this->caPath=$caPath??NfqwsPlatform::translate('/opt/etc/ssl/certs/ca-certificates.crt');
    }
    private function config(): array
    {
        $path=$this->configPath;
        if(is_link($path)||is_link(dirname($path)))return ['code'=>'invalid_config'];
        $s=@lstat($path);
        if(!$s)return ['code'=>'not_configured'];
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['size']>2048)return ['code'=>'invalid_config'];
        $f=@fopen($path,'rb');if(!$f)return ['code'=>'invalid_config'];
        try {
            $opened=fstat($f);
            if($opened['ino']!==$s['ino']||$opened['dev']!==$s['dev'])return ['code'=>'invalid_config'];
            $raw=stream_get_contents($f,2049);
        } finally {fclose($f);}
        $value=is_string($raw)?json_decode($raw,true):null;
        if(!is_array($value)||!in_array(count($value),[2,3,4,5],true)||array_diff(array_keys($value),['enabled','url','dpi_attachments_enabled','sharing_v3_enabled','sharing_v4_enabled'])!==[]||!is_bool($value['enabled']??null)||!is_string($value['url']??null)|| (isset($value['dpi_attachments_enabled'])&&!is_bool($value['dpi_attachments_enabled']))|| (array_key_exists('sharing_v3_enabled',$value)&&!is_bool($value['sharing_v3_enabled']))|| (array_key_exists('sharing_v4_enabled',$value)&&!is_bool($value['sharing_v4_enabled'])))return ['code'=>'invalid_config'];
        if(!$value['enabled'])return ['code'=>'not_configured'];
        $url=$value['url'];$parts=parse_url($url);
        if(strlen($url)>1024||preg_match('/[^\x21-\x7e]/',$url)||!$parts||($parts['scheme']??'')!=='https'||
           !isset($parts['host'])||($parts['path']??'')!=='/nfqws-support/v1/reports')return ['code'=>'invalid_config'];
        foreach(['user','pass','query','fragment'] as $key)if(isset($parts[$key]))return ['code'=>'invalid_config'];
        return ['code'=>'ready','url'=>$url,'dpi_attachments_enabled'=>$value['dpi_attachments_enabled']??false,'sharing_v3_enabled'=>$value['sharing_v3_enabled']??false,'sharing_v4_enabled'=>$value['sharing_v4_enabled']??false];
    }
    public function availability(): array
    {
        $c=$this->config();$code=$c['code'];
        if($code==='ready'&&(!extension_loaded('openssl')||!in_array('https',stream_get_wrappers(),true)||!is_file($this->caPath)||!is_readable($this->caPath)))$code='https_unavailable';
        return ['configured'=>$code==='ready','code'=>$code,'dpi_attachments'=>$code==='ready'&&($c['dpi_attachments_enabled']??false)];
    }
    public function send(string $raw,string $filename,string $submissionId): array
    {
        $result=fn($state,$code)=>['state'=>$state,'submission_id'=>$submissionId,'code'=>$code];
        if(!preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/D',$submissionId)||
           !preg_match('/^NFQWS2_[A-Za-z0-9_-]{1,64}_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}Z\.json$/D',$filename)||
           strlen($raw)===0||strlen($raw)>1048576)return $result('invalid','invalid_request');
        $available=$this->availability();
        if(!$available['configured'])return $result('failed_safe',$available['code']);
        $c=$this->config();if($c['code']!=='ready')return $result('failed_safe','invalid_config');
        return $this->transport($raw,$filename,$submissionId,$c['url']);
    }
    public function sendBundle(string $envelope,string $submissionId): array
    {
        require_once __DIR__.'/support-bundle.php';
        $result=fn($state,$code)=>['state'=>$state,'submission_id'=>$submissionId,'code'=>$code];
        try{AsusSupportBundle::envelope($envelope,$submissionId);}catch(Throwable $e){return $result('invalid','invalid_request');}
        $available=$this->availability();if(!$available['configured']||!$available['dpi_attachments'])return $result('failed_safe','not_configured');
        $c=$this->config();if($c['code']!=='ready'||!($c['dpi_attachments_enabled']??false))return $result('failed_safe','invalid_config');
        $url=substr($c['url'],0,-strlen('/v1/reports')).'/v2/reports';
        return $this->transport($envelope,null,$submissionId,$url);
    }
    public function shareAvailability(): array
    {
        $a=$this->availability();$c=$this->config();$a['sharing_v3']=$a['configured']&&($c['sharing_v3_enabled']??false);$a['sharing_v4']=$a['configured']&&($c['sharing_v4_enabled']??false);return $a;
    }
    public function sendShare(string $envelope,string $submissionId): array
    {
        require_once __DIR__.'/share-bundle.php';
        $result=fn($state,$code)=>['state'=>$state,'submission_id'=>$submissionId,'code'=>$code];
        try{$value=AsusShareBundle::envelope($envelope,$submissionId);}catch(Throwable $e){return $result('invalid','invalid_request');}
        $version=$value['version'];$flag='sharing_v'.$version;
        $a=$this->shareAvailability();if(!($a[$flag]??false))return $result('failed_safe',$a['configured']?'not_configured':$a['code']);
        $c=$this->config();if($c['code']!=='ready'||!($c[$flag.'_enabled']??false))return $result('failed_safe','invalid_config');
        return $this->transport($envelope,null,$submissionId,substr($c['url'],0,-strlen('/v1/reports')).'/v'.$version.'/reports');
    }
    public function location(): array
    {
        $a=$this->shareAvailability();if(!$a['sharing_v3'])return ['available'=>false,'code'=>$a['configured']?'not_configured':$a['code']];
        $c=$this->config();if($c['code']!=='ready'||!($c['sharing_v3_enabled']??false))return ['available'=>false,'code'=>'unavailable'];
        $unavailable=['available'=>false,'code'=>'unavailable'];
        if(!function_exists('proc_open'))return $unavailable;
        // A separate process bounds native DNS/TLS stalls as well as socket I/O.
        // The request has no credentials, report or user-selected network target.
        $worker=$this->locationCommand??[PHP_BINARY,'-d','register_argc_argv=1','-q','-f',__DIR__.'/share-location-worker.php','--','location'];
        $command=array_merge($this->locationGuard??(NfqwsPlatform::native()?[]:['/opt/libexec/nfqws2-asus/location-launch']),$worker);
        $process=@proc_open($command,[0=>['pipe','r'],1=>['pipe','w'],2=>['file','/dev/null','w']],$pipes,'/',
            ['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin:/opt/sbin:/opt/bin','LC_ALL'=>'C'],['bypass_shell'=>true]);
        if(!is_resource($process))return $unavailable;
        $clock=static function():float{$n=hrtime();return $n[0]+$n[1]/1e9;};$until=$clock()+max(0.05,min(5,$this->locationSeconds));$raw='';
        try {
            $input=json_encode(['config'=>$this->configPath,'ca'=>$this->caPath,'owner'=>$this->owner],JSON_THROW_ON_ERROR);
            if(strlen($input)>8192||fwrite($pipes[0],$input)!==strlen($input))return $unavailable;
            fclose($pipes[0]);unset($pipes[0]);stream_set_blocking($pipes[1],false);
            while($clock()<$until) {
                $chunk=fread($pipes[1],4097-strlen($raw));if(!is_string($chunk))return $unavailable;$raw.=$chunk;
                if(strlen($raw)>4096)return $unavailable;
                if(feof($pipes[1]))return self::locationValue($raw);
                $read=[$pipes[1]];$write=$except=[];@stream_select($read,$write,$except,0,20000);
            }
            return $unavailable;
        } finally {
            foreach($pipes as $pipe)if(is_resource($pipe))fclose($pipe);
            if(proc_get_status($process)['running'])proc_terminate($process,9);
            proc_close($process);
        }
    }
    /** Internal worker entry; the HTTP dispatcher only exposes location(). */
    public function locationDirect(): array
    {
        $a=$this->shareAvailability();if(!$a['sharing_v3'])return ['available'=>false,'code'=>$a['configured']?'not_configured':$a['code']];
        $c=$this->config();if($c['code']!=='ready'||!($c['sharing_v3_enabled']??false))return ['available'=>false,'code'=>'unavailable'];
        $url=substr($c['url'],0,-strlen('/v1/reports')).'/v3/location';
        // No report, explicit IP, credentials or query is sent by this GET.
        $context=stream_context_create(['ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false,'cafile'=>$this->caPath],
            'http'=>['method'=>'GET','header'=>"Connection: close\r\n",'timeout'=>5,'ignore_errors'=>true,'follow_location'=>0,'max_redirects'=>0,'protocol_version'=>1.1]]);
        $f=@fopen($url,'rb',false,$context);if(!$f)return ['available'=>false,'code'=>'unavailable'];
        try{$raw=@stream_get_contents($f,4097);$meta=stream_get_meta_data($f);}finally{fclose($f);}
        if(!is_string($raw)||strlen($raw)>4096||($meta['timed_out']??false))return ['available'=>false,'code'=>'unavailable'];
        $status=0;foreach($meta['wrapper_data']??[] as $line)if(preg_match('~^HTTP/\S+ ([0-9]{3})\b~',$line,$m))$status=(int)$m[1];
        if($status!==200)return ['available'=>false,'code'=>'unavailable'];
        return self::locationValue($raw);
    }
    private static function locationValue(string $raw): array
    {
        $v=json_decode($raw,true,8);if(!is_array($v)||($v['available']??null)!==true||array_diff(array_keys($v),['available','country','region','city','database_age_days']))return ['available'=>false,'code'=>'unavailable'];
        if(!is_string($v['country']??null)||!preg_match('/^[A-Z]{2}$/D',$v['country'])||!is_int($v['database_age_days']??null)||$v['database_age_days']<0||$v['database_age_days']>62)return ['available'=>false,'code'=>'unavailable'];
        foreach(['region','city'] as $key)if(!is_string($v[$key]??null)||preg_match('//u',$v[$key])!==1||preg_match('/[\x00-\x1f\x7f]/',$v[$key])||preg_match_all('/./us',$v[$key])>120)return ['available'=>false,'code'=>'unavailable'];
        return $v;
    }
    private function transport(string $raw,?string $filename,string $submissionId,string $url): array
    {
        $result=fn($state,$code)=>['state'=>$state,'submission_id'=>$submissionId,'code'=>$code];
        $context=stream_context_create([
            'ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false,'cafile'=>$this->caPath],
            'http'=>['method'=>'POST','header'=>"Content-Type: application/json\r\nConnection: close\r\nX-NFQWS2-Submission-ID: $submissionId\r\n".($filename===null?'':"X-NFQWS2-Filename: $filename\r\n"),
                'content'=>$raw,'timeout'=>15,'ignore_errors'=>true,'follow_location'=>0,'max_redirects'=>0,'protocol_version'=>1.1]
        ]);
        $started=microtime(true);
        $f=@fopen($url,'rb',false,$context);
        if(!$f)return $result('unknown','delivery_unknown');
        try {
            $headers=stream_get_meta_data($f)['wrapper_data']??[];$status=0;
            foreach($headers as $line)if(preg_match('~^HTTP/\S+ ([0-9]{3})\b~',$line,$m))$status=(int)$m[1];
            $body='';
            while(!feof($f)&&strlen($body)<=4096) {
                $remaining=15-(microtime(true)-$started);
                if($remaining<=0)return $result('unknown','delivery_unknown');
                stream_set_timeout($f,(int)$remaining,(int)(($remaining-(int)$remaining)*1000000));
                $chunk=@fread($f,min(4097-strlen($body),1024));
                if($chunk===false)return $result('unknown','delivery_unknown');
                $body.=$chunk;
                if(stream_get_meta_data($f)['timed_out'])return $result('unknown','delivery_unknown');
            }
        } finally {fclose($f);}
        if(strlen($body)>4096)return $result('unknown','delivery_unknown');
        $value=json_decode($body,true);
        $codes=['smtp_accepted','transport_failed','delivery_unknown','busy','rate_limited','invalid_request','id_conflict','invalid_report'];
        $statuses=['accepted'=>200,'failed_safe'=>503,'unknown'=>503,'busy'=>409,'limited'=>429,'invalid'=>422];
        $state=$value['state']??'';$code=$value['code']??'';
        if(!is_array($value)||($value['submission_id']??null)!==$submissionId||!is_string($state)||!is_string($code)||
           !isset($statuses[$state])||!in_array($code,$codes,true)||($statuses[$state]!==$status&& !($state==='invalid'&&$code==='id_conflict'&&$status===409)))return $result('unknown','delivery_unknown');
        return $result($state,$code);
    }
}
