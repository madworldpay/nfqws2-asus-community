<?php
require_once __DIR__.'/smartdns-native.php';

/** Bounded configuration sources and fixed firmware data observations. Never executes inputs or runs a resolver. */
class AsusDpiDnsFiles
{
    private array $roots;
    private array $reads=[];
    private array $directories=[];
    private ?array $firmwareAnchor=null;
    private int $bytes=0;
    private float $deadline;
    public function __construct(array $roots=[],private int $owner=0)
    {
        $this->roots=$roots?:['/opt'=>realpath('/opt')?:'/opt','/tmp'=>'/tmp','/etc'=>'/etc','/jffs'=>'/jffs','/usr'=>'/usr'];
        $this->deadline=microtime(true)+8;
    }
    private function budget():void
    {if(microtime(true)>$this->deadline||count($this->reads)>64||count($this->directories)>64||$this->bytes>2097152)throw new RuntimeException('dns_context_unknown');}
    public function path(string $path):string
    {
        if(strlen($path)>1024||!str_starts_with($path,'/')||preg_match('~[\x00-\x1f\\\\]|(?:^|/)\.{1,2}(?:/|$)|//~',$path))throw new RuntimeException('dns_context_unknown');
        if(str_starts_with($path,'/var/')&&(isset($this->roots['/tmp'])&&$this->roots['/tmp']!=='/tmp'||realpath('/var')==='/tmp'))$path='/tmp/'.substr($path,5);
        foreach($this->roots as $alias=>$root)if($path===$alias||str_starts_with($path,$alias.'/')){
            if($alias==='/etc')$root=$this->firmwareEtc()??$root;
            return rtrim($root,'/').substr($path,strlen($alias));
        }
        throw new RuntimeException('dns_context_unknown');
    }
    private function firmwareEtc():?string
    {
        $etc=$this->roots['/etc']??'';$tmp=$this->roots['/tmp']??'';clearstatcache(true,$etc);
        if(!is_link($etc)){if($this->firmwareAnchor!==null)throw new RuntimeException('dns_context_unknown');return null;}
        $target=rtrim($tmp,'/').'/etc';clearstatcache(true,$target);clearstatcache(true,$tmp);
        $link=@lstat($etc);$linkTarget=@readlink($etc);$dir=@lstat($target);$base=@lstat($tmp);
        $parent=rtrim(dirname($etc),'/').'/';$relative=str_starts_with($target,$parent)?substr($target,strlen($parent)):null;
        if(!$link||$link['uid']!==$this->owner||$link['nlink']!==1||!in_array($linkTarget,[$target,$relative],true)||realpath($etc)!==$target||!$dir||is_link($target)||
            ($dir['mode']&0170000)!==0040000||$dir['uid']!==$this->owner||($dir['mode']&0022)!==0||!$base||is_link($tmp)||
            ($base['mode']&0170000)!==0040000||$base['uid']!==$this->owner)throw new RuntimeException('dns_context_unknown');
        $keys=array_flip(['dev','ino','mode','uid']);
        $proof=[array_intersect_key($link,$keys),$linkTarget,array_intersect_key($dir,$keys),array_intersect_key($base,$keys)];
        if($this->firmwareAnchor!==null&&$this->firmwareAnchor!==$proof)throw new RuntimeException('dns_context_unknown');
        $this->firmwareAnchor=$proof;return $target;
    }
    private function secure(string $path):void
    {
        for($p=dirname($path);$p!=='/';$p=dirname($p)){
            clearstatcache(true,$p);$s=@lstat($p);if(!$s)continue;
            $firmwareTmp=$p===($this->roots['/tmp']??null)&&$s['uid']===$this->owner&&($s['mode']&07777)===0777&&$this->firmwareEtc()!==null;
            if(is_link($p)||($s['mode']&0170000)!==0040000||!in_array($s['uid'],[0,$this->owner],true)||
                ($s['mode']&0022)!==0&&!(($s['mode']&01000)!==0&&$s['uid']===0)&&!$firmwareTmp)throw new RuntimeException('dns_context_unknown');
        }
    }
    private function resolved(string $logical,bool $resolver):string
    {
        $path=$this->path($logical);$this->secure($path);clearstatcache(true,$path);
        if(is_link($path)){
            $link=@lstat($path);if(!$resolver||!$link||$link['uid']!==$this->owner||$link['nlink']!==1)throw new RuntimeException('dns_context_unknown');
            $actual=realpath($path);$allowed=false;
            foreach(['/tmp','/etc']as $root){$base=$this->roots[$root]??null;if(is_string($base)&&is_string($actual)&&str_starts_with($actual,rtrim($base,'/').'/'))$allowed=true;}
            $hosts=$logical==='/etc/hosts'&&basename($actual)==='hosts';
            if(!$allowed||!$hosts&&!preg_match('/^resolv(?:\.conf)?(?:\.auto)?$/D',basename($actual)))throw new RuntimeException('dns_context_unknown');
            $this->secure($actual);return $actual;
        }
        return $path;
    }
    /** Writable stock data is an observed identity, not a trust guarantee or an executable include. */
    private function observedFirmwareData(string $logical,string $file,bool $resolver):bool
    {
        if(!$resolver||!in_array($logical,['/etc/resolv.conf','/tmp/resolv.conf','/tmp/resolv.dnsmasq','/etc/hosts','/tmp/etc/hosts'],true))return false;
        $etc=$this->firmwareEtc();if($etc===null)return false;$tmp=rtrim($this->roots['/tmp'],'/');clearstatcache(true,$tmp);$s=@lstat($tmp);
        if(!$s||$s['uid']!==$this->owner||($s['mode']&07777)!==0777)return false;
        $expected=match($logical){
            '/etc/resolv.conf','/tmp/resolv.conf'=>$tmp.'/resolv.conf',
            '/tmp/resolv.dnsmasq'=>$tmp.'/resolv.dnsmasq',
            default=>$etc.'/hosts',
        };
        return $file===$expected;
    }
    public function read(string $path,bool $resolver=false,bool $optional=false):?string
    {
        $this->budget();$file=$this->resolved($path,$resolver);clearstatcache(true,$file);$s=@lstat($file);$raw=null;$proof=null;
        if(!$s){if(!$optional)throw new RuntimeException('dns_context_unknown');}
        else{
            if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||$s['nlink']!==1||$s['size']>262144||
                ($s['mode']&0022)!==0&&!$this->observedFirmwareData($path,$file,$resolver))throw new RuntimeException('dns_context_unknown');
            $f=@fopen($file,'rb');if(!$f)throw new RuntimeException('dns_context_unknown');
            try{$opened=fstat($f);$raw=stream_get_contents($f,262145);$after=fstat($f);}finally{fclose($f);}
            clearstatcache(true,$file);$last=@lstat($file);
            foreach(['dev','ino','mode','uid','nlink','size','mtime','ctime']as $key)if(!$last||$s[$key]!==$opened[$key]||$s[$key]!==$after[$key]||$s[$key]!==$last[$key])throw new RuntimeException('dns_context_unknown');
            if(!is_string($raw)||strlen($raw)!==$s['size']||strlen($raw)>262144||str_contains($raw,"\0"))throw new RuntimeException('dns_context_unknown');
            $this->bytes+=strlen($raw);$proof=[$file,array_intersect_key($s,array_flip(['dev','ino','mode','uid','nlink','size','mtime','ctime'])),hash('sha256',$raw)];
        }
        if(array_key_exists($path,$this->reads)&&$this->reads[$path]['proof']!==$proof)throw new RuntimeException('dns_context_unknown');
        $this->reads[$path]=['resolver'=>$resolver,'optional'=>$optional,'proof'=>$proof];$this->budget();return $raw;
    }
    public function names(string $path,?string $suffix,bool $allFiles=false):array
    {
        $this->budget();$dir=$this->path($path);$this->secure($dir.'/.proof');clearstatcache(true,$dir);$before=@lstat($dir);
        if(!$before||($before['mode']&0170000)!==0040000)throw new RuntimeException('dns_context_unknown');
        $handle=@opendir($dir);
        if(!is_resource($handle))throw new RuntimeException('dns_context_unknown');$out=[];$count=0;
        try{while(($name=readdir($handle))!==false){
            if(++$count>130)throw new RuntimeException('dns_context_unknown');
            if($allFiles?$name!=='.'&&$name!=='..':!str_starts_with($name,'.')&&!str_starts_with($name,'#')&&!str_ends_with($name,'~')&&($suffix===null||str_ends_with($name,$suffix)))$out[]=$name;
        }}finally{closedir($handle);}
        clearstatcache(true,$dir);$after=@lstat($dir);$keys=array_flip(['dev','ino','mode','uid','nlink','size','mtime','ctime']);$proof=array_intersect_key($before,$keys);
        if(!$after||array_intersect_key($after,$keys)!==$proof)throw new RuntimeException('dns_context_unknown');
        sort($out,SORT_STRING);$key=$path.'|'.($suffix??'').'|'.($allFiles?'all':'config');
        $entry=['path'=>$path,'suffix'=>$suffix,'all_files'=>$allFiles,'names'=>$out,'proof'=>$proof];
        if(isset($this->directories[$key])&&$this->directories[$key]!==$entry)throw new RuntimeException('dns_context_unknown');
        $this->directories[$key]=$entry;$this->budget();return $out;
    }
    public function hosts(string $path):array
    {
        $this->budget();$file=$this->path($path);$this->secure($file);clearstatcache(true,$file);$s=@lstat($file);
        if($s&&($s['mode']&0170000)===0040000){
            if($s['uid']!==$this->owner||($s['mode']&0022)!==0)throw new RuntimeException('dns_context_unknown');$out=[];
            foreach($this->names($path,null,true)as $name)$out[]=$this->read($path.'/'.$name);
            return $out;
        }
        return [$this->read($path,$path==='/etc/hosts')];
    }
    public function verify():void
    {
        if($this->firmwareAnchor!==null)$this->firmwareEtc();
        foreach($this->reads as $path=>$v)$this->read($path,$v['resolver'],$v['optional']);
        foreach($this->directories as $v)$this->names($v['path'],$v['suffix'],$v['all_files']);
    }
    private function dnsmasqIdentity(AsusReportIO $io,int $pid):array
    {
        $stat=$io->readProcess($pid,'stat',8192);$exe=$io->readProcess($pid,'exe');$boot=$io->read('boot',64);
        if($stat['state']!=='available'||$exe['state']!=='available'||$boot['state']!=='available'||
            $exe['value']!==(realpath('/usr/sbin/dnsmasq')?:'/usr/sbin/dnsmasq')||!preg_match('/\) (.*)$/s',$stat['value'],$m))throw new RuntimeException('dns_context_unknown');
        $fields=explode(' ',trim($m[1]));$boot=trim($boot['value']);
        if(($fields[0]??'Z')==='Z'||!preg_match('/^[0-9]{1,20}$/D',$fields[19]??'')||!preg_match('/^[a-f0-9-]{36}$/D',$boot))throw new RuntimeException('dns_context_unknown');
        return ['pid'=>$pid,'starttime'=>$fields[19],'exe'=>$exe['value'],'boot_id'=>$boot];
    }
    /** The already selected primary must own every IPv6 loopback/wildcard listener in both transports. */
    public function primaryIPv6(int $pid):array
    {
        $this->budget();if($pid<2)throw new RuntimeException('dns_context_unknown');$proc=$this->roots['/proc']??'/proc';
        if(is_link($proc)||is_link($proc.'/'.$pid)||is_link($proc.'/'.$pid.'/fd'))throw new RuntimeException('dns_context_unknown');
        $io=new AsusReportIO(['proc'=>$proc]);$identity=$this->dnsmasqIdentity($io,$pid);$end=microtime(true)+1;$sockets=[];
        $loop=pack('L',1)==="\x01\x00\x00\x00"?'00000000000000000000000001000000':'00000000000000000000000000000001';
        foreach(['udp6'=>'07','tcp6'=>'0A']as $protocol=>$state){
            $r=$io->read('dns_'.$protocol);if($r['state']!=='available')throw new RuntimeException('dns_context_unknown');$this->bytes+=strlen($r['value']);$this->budget();$inodes=[];
            foreach(explode("\n",$r['value'])as $line){$v=preg_split('/\s+/',trim($line));
                if(!in_array($v[1]??null,[$loop.':0035',str_repeat('0',32).':0035'],true))continue;
                if($protocol==='tcp6'&&($v[3]??null)!==$state)continue;
                if(($v[3]??null)!==$state||!preg_match('/^[1-9][0-9]{0,19}$/D',$v[9]??'')||count($inodes)>=128)throw new RuntimeException('dns_context_unknown');$inodes[]=$v[9];
            }
            if($inodes===[])throw new RuntimeException('dns_context_unknown');$inodes=array_values(array_unique($inodes));sort($inodes);$sockets[$protocol]=$inodes;
        }
        $handle=@opendir($proc.'/'.$pid.'/fd');if(!is_resource($handle))throw new RuntimeException('dns_context_unknown');$owned=[];$count=0;
        try{while(($fd=readdir($handle))!==false){
            if(++$count>4098||microtime(true)>$end)throw new RuntimeException('dns_context_unknown');$this->budget();
            if(!preg_match('/^[0-9]+$/D',$fd))continue;$link=@readlink($proc.'/'.$pid.'/fd/'.$fd);
            if(is_string($link)&&preg_match('/^socket:\[([1-9][0-9]{0,19})\]$/D',$link,$m))$owned[]=$m[1];
        }}finally{closedir($handle);}
        foreach($sockets as $inodes)if(array_diff($inodes,$owned)!==[])throw new RuntimeException('dns_context_unknown');
        if($this->dnsmasqIdentity($io,$pid)!==$identity||microtime(true)>$end)throw new RuntimeException('dns_context_unknown');
        return ['identity'=>$identity,'sockets'=>$sockets];
    }
}

/** Effective configuration identity, deliberately smaller than installation/rollback CAS snapshots.
 * Dependencies are trusted local fixtures only; no request field or environment selects a source.
 * Unknown is never evidence of equality: the picker must reject it even when both samples match.
 */
final class AsusDpiDnsContext
{
    private const NV=['dns_local_cache','dnspriv_enable','dnspriv_profile','dnspriv_rulelist','dhcp_dns1_x','dhcp_dns2_x','dhcp_dns_router','dnsfilter_enable_x','dnsfilter_mode','dnssec_enable',
        'wan0_dnsenable_x','wan0_dns1_x','wan0_dns2_x','wan0_dns','wan1_dnsenable_x','wan1_dns1_x','wan1_dns2_x','wan1_dns'];
    private array $active=[];
    private int $visited=0;
    private array $resolvers=[];
    private array $hosts=[];
    private string $stage='snapshot';
    private function __construct(private string $platform,private AsusDpiDnsFiles $files,private array $deps){}
    private static function unknown():array{return ['schema_version'=>1,'state'=>'unknown','sha256'=>null];}
    public static function collect(array $deps=[]):array
    {return self::observe($deps)['context'];}
    /** Diagnostic metadata never enters the context digest or contains observed values. */
    public static function observe(array $deps=[]):array
    {
        $collector=null;
        try{
            $platform=$deps['platform']??NfqwsPlatform::current();if(!in_array($platform,['asus-entware','openwrt'],true))throw new RuntimeException('dns_context_unknown');
            $collector=new self($platform,$deps['files']??new AsusDpiDnsFiles(),$deps);
            return ['context'=>$collector->snapshot(),'failure'=>null];
        }catch(Throwable $e){
            $source='external';$line=0;$file=basename($e->getFile());
            if(dirname($e->getFile())===__DIR__&&preg_match('/^[a-z0-9-]{1,64}\.php$/D',$file)){$source=$file;$line=max(0,min(1000000,$e->getLine()));}
            return ['context'=>self::unknown(),'failure'=>['stage'=>$collector?->stage??'platform','source'=>$source,'line'=>$line]];
        }
    }
    private static function clean(string $raw):string
    {return implode("\n",array_values(array_filter(array_map('trim',explode("\n",$raw)),static fn($line)=>$line!==''&&!str_starts_with($line,'#'))));}
    private function nvram():array
    {
        if($this->platform==='openwrt')return [];
        if(isset($this->deps['nvram']))$r=($this->deps['nvram'])();
        else{$values=[];$r=(new AsusReportIO())->streamCommand('nvram',function($line)use(&$values){$v=explode('=',$line,2);if(count($v)===2&&in_array($v[0],self::NV,true))$values[$v[0]]=array_key_exists($v[0],$values)?null:$v[1];},1.5);$r['values']=$values;}
        if(($r['state']??null)!=='available'||!is_array($r['values']??null))throw new RuntimeException('dns_context_unknown');
        $values=array_intersect_key($r['values'],array_flip(self::NV));if(in_array(null,$values,true)||!in_array($values['dnspriv_enable']??null,['0','1'],true))throw new RuntimeException('dns_context_unknown');
        foreach($values as $v)if(!is_string($v)||strlen($v)>65536)throw new RuntimeException('dns_context_unknown');ksort($values);return $values;
    }
    private function primary():array
    {
        if(isset($this->deps['primary']))$v=($this->deps['primary'])();
        elseif($this->platform==='openwrt'){require_once __DIR__.'/openwrt-smartdns-resolver.php';$v=(new NfqwsOpenWrtDnsmasqResolver())->primary();}
        else{
            $r=NfqwsPlatform::run(['/bin/sh','/opt/lib/nfqws2-asus/smartdns/primary-dns.sh','identity'],3,[],128);
            $text=implode("\n",$r['output']);if($r['status']!==0||!preg_match('/^[1-9][0-9]* [0-9]+$/D',$text))throw new RuntimeException('dns_context_unknown');
            $v=['config'=>'/tmp/etc/dnsmasq.conf','identity'=>$text];
        }
        if(!is_array($v)||!is_string($v['config']??null))throw new RuntimeException('dns_context_unknown');return $v;
    }
    private function native():array
    {
        if(isset($this->deps['native']))return ($this->deps['native'])();
        $store=new AsusSmartDnsStore();$installer=new AsusSmartDnsInstaller();$backend=AsusSmartDnsNativeBackend::create($store,$installer);$state=$backend->state();
        $healthy=$state!==null&&$backend->healthy();$engine=null;
        if($healthy){if($state['runtime_exe']!==$installer->binaryDirectory().'/smartdns')throw new RuntimeException('dns_context_unknown');$engine=$installer->artifact()['sha256'];}
        return ['state'=>$state,'healthy'=>$healthy,'forwarding'=>$backend->forwarding(),'engine_sha256'=>$engine];
    }
    private function processes():array
    {
        $r=isset($this->deps['processes'])?($this->deps['processes'])():(new AsusReportIO())->dnsProcesses();
        if(($r['state']??null)!=='available'){
            // Fixed diagnostic vocabulary only; never copy provider values.
            // The scan, its bounds, and unknown-context rejection are unchanged.
            $state=in_array($r['state']??null,['missing','partial','truncated','timeout','denied'],true)?$r['state']:'invalid';
            $this->stage=($this->stage==='verify'?'verify':'processes').'_scan_'.$state;
            throw new RuntimeException('dns_context_unknown');
        }
        if(!is_array($r['names']??null)||count($r['names'])>32)throw new RuntimeException('dns_context_unknown');
        $names=array_values(array_unique($r['names']));sort($names);foreach($names as $name)if(!in_array($name,['smartdns','stubby'],true))throw new RuntimeException('dns_context_unknown');return $names;
    }
    private function stubbyProof():bool
    {
        if(isset($this->deps['stubby_proof']))return ($this->deps['stubby_proof'])()===true;
        $r=NfqwsPlatform::run(['/bin/busybox','pidof','stubby'],1,[],128);$pid=trim(implode("\n",$r['output']));
        if($r['status']!==0||!preg_match('/^[1-9][0-9]{0,8}$/D',$pid)||(int)$pid<2)return false;
        $before=AsusDpiRuntime::identity((int)$pid);$io=new AsusReportIO();$uid=$io->readProcess((int)$pid,'status',8192);
        if($before===null||$before['exe']!==(realpath('/usr/sbin/stubby')?:'/usr/sbin/stubby')||$uid['state']!=='available'||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',$uid['value']))return false;
        $raw=@file_get_contents('/proc/'.$pid.'/cmdline',false,null,0,8193);if(!is_string($raw)||strlen($raw)>8192)return false;
        $argv=explode("\0",rtrim($raw,"\0"));if(count($argv)>16||basename(array_shift($argv))!=='stubby')return false;$config=[];
        for($i=0;$i<count($argv);$i++){
            if($argv[$i]==='-g')continue;
            if($argv[$i]==='-C'&&isset($argv[$i+1])){$config[]=$argv[++$i];continue;}
            return false;
        }
        return $config===['/etc/stubby/stubby.yml']&&AsusDpiRuntime::identity((int)$pid)===$before;
    }
    private function runtimeArgv(array $state):array
    {
        if(isset($this->deps['runtime_argv']))return ($this->deps['runtime_argv'])($state);
        $pid=$state['runtime_pid']??'';if(!is_string($pid)||!preg_match('/^[1-9][0-9]{0,8}$/D',$pid)||(int)$pid<2)throw new RuntimeException('dns_context_unknown');
        $raw=@file_get_contents('/proc/'.$pid.'/cmdline',false,null,0,8193);if(!is_string($raw)||strlen($raw)>8192)throw new RuntimeException('dns_context_unknown');
        return explode("\0",rtrim($raw,"\0"));
    }
    /** servers-file is reloadable server data, never a recursive configuration source. */
    private function servers(string $path):string
    {
        $out=[];
        foreach(explode("\n",$this->files->read($path,true))as $line){
            $line=trim($line);if($line===''||str_starts_with($line,'#'))continue;
            $line=preg_replace('/[ \t]+#.*$/','',$line);
            // Unsupported quoting/escaping must not hide a local upstream from the ownership checks.
            if(!preg_match('/^(server|rev-server)\s*=\s*(\S+)$/D',$line,$m)||strpbrk($m[2],chr(34).chr(39).chr(92))!==false)throw new RuntimeException('dns_context_unknown');
            $out[]=$line;
        }
        return implode("\n",$out);
    }
    private function config(string $path,int $depth=0):string
    {
        if($depth>8||++$this->visited>64||isset($this->active[$path]))throw new RuntimeException('dns_context_unknown');$this->active[$path]=true;$out=[];
        foreach(explode("\n",$this->files->read($path))as $line){
            $line=trim($line);if($line===''||str_starts_with($line,'#'))continue;
            if(preg_match('/^(conf-script|hostsdir|dhcp-hostsdir)\s*(?:=|$)/',$line))throw new RuntimeException('dns_context_unknown');
            if(preg_match('/^(conf-file|servers-file|addn-hosts|dhcp-hostsfile|resolv-file)\s*=/',$line,$m)){
                $source=AsusSmartDnsConfig::includePath($line);
                if($m[1]==='conf-file'){$out[]=$this->config($source,$depth+1);continue;}
                if($m[1]==='servers-file'){$out[]=$this->servers($source);continue;}
                if($m[1]==='resolv-file')$this->resolvers[]=$source;
                elseif($m[1]==='addn-hosts')foreach($this->files->hosts($source)as $raw)$this->hosts[]=self::clean($raw);
                else $this->hosts[]=self::clean($this->files->read($source,$source==='/etc/hosts'));
            }elseif(preg_match('/^conf-dir\s*=/',$line)){
                if($this->platform!=='openwrt'||!preg_match('~^conf-dir=(/[^\s,]+)(?:,(\*\.conf))?$~D',$line,$m))throw new RuntimeException('dns_context_unknown');
                foreach($this->files->names($m[1],isset($m[2])?'.conf':null)as $name)$out[]=$this->config($m[1].'/'.$name,$depth+1);continue;
            }elseif(preg_match('/^(conf-file|conf-dir|servers-file|addn-hosts|resolv-file)\s*(?:=|$)/',$line))throw new RuntimeException('dns_context_unknown');
            $out[]=$line;
        }
        unset($this->active[$path]);$text=implode("\n",$out);if(strlen($text)>262144)throw new RuntimeException('dns_context_unknown');return $text;
    }
    private static function local(string $address):bool
    {
        $ip=explode('%',trim($address,'[]'),2)[0];$packed=@inet_pton($ip);
        if($packed===false)return str_starts_with($ip,'127.');
        if(strlen($packed)===16&&substr($packed,0,12)===str_repeat("\0",10)."\xff\xff")$packed=substr($packed,12);
        if(strlen($packed)===4)return ord($packed[0])===127||$packed===str_repeat("\0",4);
        return $packed===str_repeat("\0",16)||$packed===str_repeat("\0",15)."\1";
    }
    private function upstream(string $raw,array $allowed,bool $system=false):void
    {
        foreach(explode("\n",$raw)as $line){$value=null;
            if(preg_match('/^nameserver\s+([^\s#]+)/',$line,$m))$value=$m[1].'#53';
            if(preg_match('/^server\s*=\s*(.*)$/D',$line,$m)){$value=$m[1];if(str_starts_with($value,'/'))$value=substr($value,strrpos($value,'/')+1);}
            if(preg_match('/^rev-server\s*=\s*([^,]+)(?:,(.*))?$/D',$line,$m))$value=trim($m[2]??'');
            if($value===null||$value==='')continue;$value=explode('@',$value,2)[0];$parts=explode('#',$value,2);$address=$parts[0];$port=$parts[1]??'53';
            // The platform primary proofs establish the IPv4 listener only.
            if(self::local($address)&&!in_array(trim($address,'[]').'#'.$port,$allowed,true)&&!($system&&$address==='127.0.0.1'&&$port==='53'))throw new RuntimeException('dns_context_unknown');
        }
    }
    private function snapshot():array
    {
        $this->stage='primary';$primary=$this->primary();$this->stage='nvram';$nv=$this->nvram();
        $this->stage='processes';$names=$this->processes();$this->stage='native';$native=$this->native();
        $this->stage='store';
        $storePath=$this->platform==='openwrt'?'/etc/nfqws2-web/smartdns':'/opt/etc/nfqws-asus-web/smartdns';
        $store=new AsusSmartDnsStore($this->files->path($storePath),$this->deps['owner']??0);$view=$store->view();$active=$view['active'];$managed=null;$allowed=[];$runtimeArgs=null;
        if($active!==null){
            $this->stage='managed_profile';
            $profile=AsusSmartDnsProfile::normalize($active['profile']??[]);$state=$native['state']??null;
            if(!hash_equals($active['profile_hash'],AsusSmartDnsProfile::hash($profile))||!is_array($state)||($state['phase']??null)!=='confirmed'||
                ($state['profile_hash']??null)!==$active['profile_hash']||($native['healthy']??null)!==true||($native['forwarding']??null)!=='managed'||
                !preg_match('/^[a-f0-9]{32}$/D',$state['request_id']??'')||!preg_match('/^[a-f0-9]{64}$/D',$native['engine_sha256']??'')||!in_array('smartdns',$names,true))throw new RuntimeException('dns_context_unknown');
            $rendered=AsusSmartDnsProfile::render($profile,6054)['config'];$request=$state['request_id'];
            $runtime=$this->platform==='openwrt'?'/tmp/nfqws2-native-state/smartdns-runtime/runtime.conf':$storePath.'/jobs/'.$request.'/runtime.conf';
            $runtimeArgs=$this->runtimeArgv($state);$expectedArgs=[$state['runtime_exe'],'-f','-c',$runtime,'-p',dirname($runtime).'/runtime.pid'];
            if($this->platform==='asus-entware'&&($runtimeArgs[0]??null)==='./smartdns')$expectedArgs[0]='./smartdns';
            if($runtimeArgs!==$expectedArgs)throw new RuntimeException('dns_context_unknown');
            $expected=$rendered.($this->platform==='openwrt'?'address /nfqws-'.$request.'.example.net/1.0.0.1'."\n":'');
            if($this->files->read($runtime)!==$expected)throw new RuntimeException('dns_context_unknown');
            $ca=$this->files->read($this->platform==='openwrt'?'/etc/ssl/certs/ca-certificates.crt':'/opt/etc/ssl/certs/ca-certificates.crt');
            $managed=['config'=>hash('sha256',$rendered),'engine'=>$native['engine_sha256'],'ca'=>hash('sha256',$ca)];$allowed[]='127.0.0.1#6054';
        }elseif(($native['healthy']??false)===true||in_array('smartdns',$names,true)||!in_array($native['state']['phase']??null,[null,'rolled_back'],true))throw new RuntimeException('dns_context_unknown');
        $stubby=null;
        $this->stage='stubby';
        if(($nv['dnspriv_enable']??'0')==='1'||in_array('stubby',$names,true)){
            if($this->platform!=='asus-entware'||($nv['dnspriv_enable']??null)!=='1'||!in_array('stubby',$names,true)||!$this->stubbyProof())throw new RuntimeException('dns_context_unknown');
            $stubby=$this->files->read('/etc/stubby/stubby.yml');$listening=false;
            foreach(explode("\n",$stubby)as $line){if(preg_match('/^listen_addresses:\s*$/D',$line)){$listening=true;continue;}if($listening&&preg_match('/^\S/',$line))$listening=false;
                if($listening&&preg_match('/^\s*-\s*["\']?((?:127\.[0-9.]+|::1))@([0-9]{1,5})["\']?\s*$/D',$line,$m))$allowed[]=$m[1].'#'.$m[2];}
        }
        $this->stage='system_resolver';$system=self::clean($this->files->read('/etc/resolv.conf',true));$systemAllowed=$allowed;$listenerProof=null;
        if($this->platform==='openwrt'&&preg_match('/^nameserver\s+::1(?:\s|$)/m',$system)){
            if(!is_int($primary['pid']??null))throw new RuntimeException('dns_context_unknown');
            $listenerProof=$this->files->primaryIPv6($primary['pid']);$systemAllowed[]='::1#53';
        }
        $this->upstream($system,$systemAllowed,true);
        $this->stage='config';$config=$this->config($primary['config']);$this->upstream($config,$allowed);
        $this->stage='resolvers';
        $resolverFiles=[];
        if(!preg_match('/(?:^|\n)no-resolv(?:\n|$)/',$config)){
            // dnsmasq chooses among resolver files by mtime; contents alone cannot prove that choice.
            if(count(array_unique($this->resolvers))>1)throw new RuntimeException('dns_context_unknown');
            foreach($this->resolvers?:['/etc/resolv.conf']as $path){$raw=self::clean($this->files->read($path,true));$this->upstream($raw,$allowed);$resolverFiles[]=$raw;}
        }
        $this->stage='hosts';if(!preg_match('/(?:^|\n)no-hosts(?:\n|$)/',$config))$this->hosts[]=self::clean($this->files->read('/etc/hosts',true));
        $facts=['platform'=>$this->platform,'system'=>$system,'dnsmasq'=>$config,'resolvers'=>$resolverFiles,'hosts'=>$this->hosts,'nvram'=>$nv,'components'=>$names,'managed'=>$managed,'stubby'=>$stubby===null?null:self::clean($stubby)];
        // Read twice to reject mixed snapshots; these identities never enter the digest.
        $this->stage='verify';$this->files->verify();if($this->primary()!==$primary||$this->nvram()!==$nv||$this->processes()!==$names||$this->native()!==$native||$store->view()['active']!==$active||
            $runtimeArgs!==null&&$this->runtimeArgv($native['state'])!==$runtimeArgs||
            $listenerProof!==null&&$this->files->primaryIPv6($primary['pid'])!==$listenerProof)throw new RuntimeException('dns_context_unknown');
        return ['schema_version'=>1,'state'=>'known','sha256'=>hash('sha256',json_encode($facts,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR))];
    }
}
