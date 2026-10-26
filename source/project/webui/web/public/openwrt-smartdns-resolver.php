<?php
require_once __DIR__.'/platform.php';

/** CAS only the volatile generated file; persistent UCI/VPN sources stay intact. */
final class NfqwsOpenWrtDnsmasqOverlay
{
    public function __construct(private int $owner=0){}
    private function path(array $s):string
    {return NfqwsPlatform::guardFile(dirname($s['config']),basename($s['config']),$this->owner);}
    public static function effective(array $s):string
    {
        if(!is_string($s['text']??null)||strlen($s['text'])>262144||str_contains($s['text'],"\0"))throw new RuntimeException('invalid_state');$lines=[];
        foreach(explode("\n",$s['text'])as $line){$v=trim($line);
            if(preg_match('/^(?:conf-file|conf-dir|conf-script|servers-file)\s*(?:=|$)/',$v))throw new RuntimeException('existing_dns_rules');
            if(preg_match('/^(?:resolv-file)\s*=/',$v)||preg_match('/^(?:no-resolv|all-servers|strict-order)\s*$/D',$v))continue;
            if(preg_match('/^server\s*=\s*(.*)$/D',$v,$m)&&(!str_starts_with($m[1],'/')||preg_match('~^/[#.*]+/~',$m[1])))continue;
            $lines[]=$line;
        }
        return "# NFQWS2 managed volatile DNS configuration\n".rtrim(implode("\n",$lines))."\nno-resolv\nserver=127.0.0.1#6054\n";
    }
    private function read(array $s):string
    {
        $file=$this->path($s);$stat=@lstat($file);
        if(!$stat||$stat['uid']!==$this->owner||($stat['mode']&0022)!==0||$stat['size']>524288)throw new RuntimeException('hook_conflict');
        $raw=@file_get_contents($file);if(!is_string($raw)||strlen($raw)!==$stat['size'])throw new RuntimeException('hook_conflict');return $raw;
    }
    public function routing(array $s):string
    {
        try{$raw=$this->read($s);if($raw===self::effective($s))return 'managed';return $raw===$s['original']?'external':'unknown';}catch(Throwable $e){return 'unknown';}
    }
    private function replace(array $s,string $expected,string $next):void
    {
        $file=$this->path($s);if($this->read($s)!==$expected)throw new RuntimeException('hook_conflict');
        $mode=$s['mode']??null;if(!is_int($mode)||($mode&0022)!==0||($mode&~0777)!==0)throw new RuntimeException('hook_conflict');
        $tmp=NfqwsPlatform::guardFile(dirname($file),'.nfqws-dns-'.bin2hex(random_bytes(8)),$this->owner);$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}
        if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(fwrite($f,$next)!==strlen($next)||!fflush($f)||!chmod($tmp,$mode))throw new RuntimeException('storage_unavailable');}
        finally{fclose($f);}
        try{if($this->read($s)!==$expected||!rename($tmp,$file))throw new RuntimeException('hook_conflict');}finally{if(is_file($tmp))unlink($tmp);}
    }
    public function apply(array $s):void{$this->replace($s,$s['original'],self::effective($s));}
}

/** Select the real local DNS owner, not the first UCI dnsmasq section. */
final class NfqwsOpenWrtDnsmasqResolver
{
    public function __construct(private int $owner=0){}
    public static function select(array $instances,array $owners,array $parents=[]):array
    {
        $owners=array_values(array_unique($owners));
        if(count($owners)!==1||!is_int($owners[0])||$owners[0]<2)throw new RuntimeException('primary_dns_unverified');$found=[];
        foreach($instances as $name=>$v){
            if(!is_string($name)||!preg_match('/^[A-Za-z0-9_]{1,64}$/D',$name)||!is_array($v)||($v['running']??false)!==true)continue;
            $pid=$owners[0];$seen=[];
            while($pid!==($v['pid']??null)&&count($seen)<8&&!isset($seen[$pid])&&is_int($parents[$pid]??null)&&$parents[$pid]>1){$seen[$pid]=true;$pid=$parents[$pid];}
            if($pid!==($v['pid']??null))continue;
            $argv=$v['command']??null;if(!is_array($argv)||!array_is_list($argv)||($argv[0]??null)!=='/usr/sbin/dnsmasq'||count($argv)>32)continue;
            $paths=[];for($i=1;$i<count($argv);$i++)if($argv[$i]==='-C'&&is_string($argv[$i+1]??null))$paths[]=$argv[++$i];
            if($paths!==['/var/etc/dnsmasq.conf.'.$name]&&$paths!==['/tmp/etc/dnsmasq.conf.'.$name])continue;
            $found[]=['instance'=>$name,'pid'=>$owners[0],'config'=>$paths[0]];
        }
        if(count($found)!==1)throw new RuntimeException('primary_dns_unverified');return $found[0];
    }
    private function owners():array
    {
        $required=[];
        foreach(['udp','tcp']as $protocol){$inodes=[];$raw=@file_get_contents('/proc/net/'.$protocol);if(!is_string($raw))throw new RuntimeException('primary_dns_unverified');
            foreach(explode("\n",$raw)as $line){$v=preg_split('/\s+/',trim($line));if(in_array($v[1]??'', ['00000000:0035',NfqwsPlatform::procNetIPv4('127.0.0.1').':0035'],true)&&($protocol!=='tcp'||($v[3]??'')==='0A'))$inodes[]=$v[9]??'';}
            if(!$inodes)throw new RuntimeException('primary_dns_unverified');$required[$protocol]=$inodes;
        }
        $owners=[];$entries=@scandir('/proc');if(!is_array($entries)||count($entries)>4096)throw new RuntimeException('primary_dns_unverified');$end=microtime(true)+3;
        foreach($entries as $pid){
            if(!preg_match('/^[1-9][0-9]{0,8}$/D',$pid)||(int)$pid<2)continue;if(microtime(true)>$end)throw new RuntimeException('primary_dns_unverified');$owned=[];
            foreach(@scandir('/proc/'.$pid.'/fd')?:[]as $fd){if(!preg_match('/^[0-9]+$/D',$fd))continue;$link=@readlink('/proc/'.$pid.'/fd/'.$fd);if(is_string($link)&&preg_match('/^socket:\[([0-9]+)\]$/D',$link,$m))$owned[]=$m[1];}
            $udp=(bool)array_intersect($owned,$required['udp']);$tcp=(bool)array_intersect($owned,$required['tcp']);
            if($udp!==$tcp)throw new RuntimeException('primary_dns_unverified');if($udp)$owners[]=(int)$pid;
        }return $owners;
    }
    private function read(string $path):string
    {
        $file=NfqwsPlatform::guardFile(dirname($path),basename($path),$this->owner);$s=@lstat($file);
        if(!$s||$s['uid']!==$this->owner||($s['mode']&0022)!==0||$s['size']>262144)throw new RuntimeException('existing_dns_rules');
        $raw=@file_get_contents($file);if(!is_string($raw)||strlen($raw)!==$s['size']||str_contains($raw,"\0"))throw new RuntimeException('existing_dns_rules');return $raw;
    }
    public function primary():array
    {
        $r=NfqwsPlatform::run(['/bin/ubus','call','service','list','{"name":"dnsmasq"}'],3);
        try{$services=json_decode(implode("\n",$r['output']),true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('primary_dns_unverified');}
        $owners=$this->owners();$parents=[];
        foreach($owners as $pid)for($n=0;$n<8&&!isset($parents[$pid]);$n++){
            $status=(string)@file_get_contents('/proc/'.$pid.'/status');
            if(!preg_match('/^PPid:\s+([0-9]+)\s*$/m',$status,$m)||(int)$m[1]<2)break;
            $parents[$pid]=(int)$m[1];$pid=(int)$m[1];
        }
        $instances=$services['dnsmasq']['instances']??[];$selected=self::select($instances,$owners,$parents);$identity=AsusDpiRuntime::identity($selected['pid']);
        $instance=$instances[$selected['instance']];$supervisor=AsusDpiRuntime::identity($instance['pid']);
        $args=explode("\0",rtrim((string)@file_get_contents('/proc/'.$selected['pid'].'/cmdline'),"\0"));
        if($identity===null||$identity['exe']!==(realpath('/usr/sbin/dnsmasq')?:'/usr/sbin/dnsmasq')||$args!==$instance['command']||$supervisor===null||
            $selected['pid']!==$instance['pid']&&$supervisor['exe']!==(realpath('/sbin/ujail')?:'/sbin/ujail'))throw new RuntimeException('primary_dns_unverified');
        return $selected;
    }
    private function names(string $dir,?string $suffix):array
    {
        NfqwsPlatform::guardFile($dir,'.directory-proof',$this->owner);$entries=@scandir($dir);if(!is_array($entries)||count($entries)>130)throw new RuntimeException('output_limit');$out=[];
        foreach($entries as $name)if(!str_starts_with($name,'.')&&!str_starts_with($name,'#')&&!str_ends_with($name,'~')&&($suffix===null||str_ends_with($name,$suffix)))$out[]=$name;return $out;
    }
    public function collect():array
    {
        $selected=$this->primary();$canonical=realpath($selected['config']);
        if(!is_string($canonical)||!str_starts_with($canonical,'/tmp/'))throw new RuntimeException('recovery_unavailable');
        $original=$this->read($selected['config']);if(str_starts_with($original,'# NFQWS2 managed volatile DNS configuration'))throw new RuntimeException('restore_required');
        $fingerprints=[];$directories=[];$seen=[];$expanded='';
        $append=function(string $raw)use(&$expanded){$expanded.=$raw."\n";if(strlen($expanded)>262144)throw new RuntimeException('output_limit');};
        $visit=function(string $file,int $depth=0)use(&$visit,&$directories,&$fingerprints,&$seen,$append){
            if($depth>8||count($seen)>64||isset($seen[$file]))throw new RuntimeException('existing_dns_rules');$seen[$file]=true;$raw=$this->read($file);$fingerprints[$file]=hash('sha256',$raw);
            foreach(explode("\n",$raw)as $line){$v=trim($line);
                if(preg_match('/^conf-script(?:=|$)/',$v))throw new RuntimeException('existing_dns_rules');
                if(preg_match('/^conf-file=(\/[^\s,]+)$/D',$v,$m)){$visit($m[1],$depth+1);continue;}
                if(preg_match('/^conf-dir=(\/[^\s,]+)(?:,(\*\.conf))?$/D',$v,$m)){
                    $suffix=isset($m[2])?'.conf':null;$entries=$this->names($m[1],$suffix);$directories[$m[1]]=['suffix'=>$suffix,'names'=>$entries];foreach($entries as $name)$visit($m[1].'/'.$name,$depth+1);continue;
                }
                if(preg_match('/^servers-file=(\/[^\s,]+)$/D',$v,$m)){$visit($m[1],$depth+1);continue;}
                if(preg_match('/^(?:conf-file|conf-dir|servers-file)\s*(?:=|$)/',$v))throw new RuntimeException('existing_dns_rules');
                if(preg_match('/^resolv-file=(\/[^\s,]+)$/D',$v,$m)&&file_exists($m[1]))$fingerprints[$m[1]]=hash('sha256',$this->read($m[1]));
                $append($line);
            }
        };
        $visit($selected['config']);
        // Another local default resolver must remain an explicit ownership
        // choice; never bypass an existing AdGuard/DNSCrypt/etc chain silently.
        foreach(explode("\n",$expanded)as $line)if(preg_match('~^\s*server\s*=\s*(?:127\.|\[?::1)~',$line))throw new RuntimeException('existing_dns_rules');
        ksort($fingerprints);ksort($directories);$facts=['boot'=>trim(file_get_contents('/proc/sys/kernel/random/boot_id')),'instance'=>$selected['instance'],'config'=>$selected['config'],'files'=>$fingerprints,'directories'=>$directories];
        $snapshot=$facts+['original'=>$original,'mode'=>fileperms($selected['config'])&0777,'text'=>$expanded];
        if(strlen(json_encode($snapshot,JSON_THROW_ON_ERROR))>400000)throw new RuntimeException('output_limit');
        return ['hash'=>hash('sha256',json_encode($facts,JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR)),'snapshot'=>$snapshot,'conflicts'=>[]];
    }
    public function sourcesUnchanged(array $snapshot):bool
    {
        try{foreach($snapshot['files']as $path=>$hash)if($path!==$snapshot['config']&&!hash_equals($hash,hash('sha256',$this->read($path))))return false;
            foreach($snapshot['directories']as $dir=>$v)if($this->names($dir,$v['suffix'])!==$v['names'])return false;return true;
        }catch(Throwable $e){return false;}
    }
    /** Validate only the commit boundary; preserve the complete native payload. */
    public static function validateCommit(array $frame,string $instance,string $config,?string $generation=null):void
    {
        if(($frame['name']??null)!=='dnsmasq'||!is_array($frame['instances']??null)||array_keys($frame['instances'])!==[$instance])throw new RuntimeException('primary_dns_unverified');
        $args=$frame['instances'][$instance]['command']??null;
        if(!is_array($args)||!array_is_list($args)||count($args)>32||($args[0]??null)!=='/usr/sbin/dnsmasq')throw new RuntimeException('primary_dns_unverified');
        foreach($args as $arg)if(!is_string($arg))throw new RuntimeException('primary_dns_unverified');
        $paths=[];for($i=1;$i<count($args);$i++)if($args[$i]==='-C')$paths[]=$args[++$i]??null;
        if($paths!==[$config])throw new RuntimeException('primary_dns_unverified');
        if($generation!==null&&(!preg_match('/^[a-f0-9]{32}:(?:forward|restore):[a-f0-9]{16}$/D',$generation)||($frame['instances'][$instance]['env']['NFQWS2_DNS_GENERATION']??null)!==$generation))throw new RuntimeException('hook_conflict');
    }
    public function transaction(array $snapshot,string $operation,string $id,$lease):void
    {
        $name=$snapshot['instance']??null;
        if(!is_string($name)||!preg_match('/^[A-Za-z0-9_]{1,64}$/D',$name)||!preg_match('/^[a-f0-9]{32}$/D',$id)||!in_array($operation,['forward','restore'],true)||!is_resource($lease))throw new RuntimeException('invalid_state');
        $before=$this->primary();if($before['instance']!==$name||$before['config']!==$snapshot['config'])throw new RuntimeException('primary_dns_unverified');
        $r=NfqwsPlatform::run(['/bin/sh','/usr/lib/nfqws2/smartdns/dnsmasq-transaction.sh',$id,$operation,$name],20,[9=>$lease]);
        if($r['status']!==0){foreach($r['output']as $line)if(preg_match('/^Native SmartDNS: (stale_baseline|hook_conflict|primary_dns_unverified|invalid_state)$/D',$line,$m))throw new RuntimeException($m[1]);throw new RuntimeException('dns_restart_failed');}
        $end=microtime(true)+15;
        do{try{$after=$this->primary();if($after['instance']===$name&&$after['config']===$snapshot['config']&&$after['pid']!==$before['pid'])return;}catch(Throwable $e){}usleep(100000);}while(microtime(true)<$end);
        throw new RuntimeException('dns_restart_failed');
    }
}
