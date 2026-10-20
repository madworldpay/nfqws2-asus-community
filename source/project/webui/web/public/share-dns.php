<?php
require_once __DIR__.'/share-read.php';
require_once __DIR__.'/smartdns-store.php';
/** Read-only DNS/card copies. Exporting a subset never applies a DNS profile. */
final class AsusShareDns
{
    private string $legacy;
    private AsusShareRead $reader;
    public function __construct(?string $legacy=null,private int $owner=0,private array $deps=[])
    { $alias=$deps['opt_alias']??'/opt';$this->legacy=$legacy??AsusDpiStore::optPath('/etc/smartdns',$alias).'/smartdns.conf';$this->reader=$legacy===null?new AsusShareRead($owner,realpath($alias),$alias):new AsusShareRead($owner); }
    private static function safeUrl(string $url): bool
    {
        $p=parse_url($url);
        if(!is_array($p)||($p['scheme']??null)!=='https'||isset($p['user'])||isset($p['pass'])||isset($p['fragment']))return false;
        foreach(explode('&',$p['query']??'') as $pair) {
            $key=strtolower(rawurldecode(explode('=',$pair,2)[0]));
            $normalized=preg_replace('/[^a-z0-9]/','',$key);
            if(in_array($normalized,['key','auth','code','sig','signature'],true)||preg_match('/token|secret|password|passwd|credential|apikey|authorization|authentication/',$normalized))return false;
        }
        return true;
    }
    /** Reuse the strict structured validator without imposing installation's
     * default-server/bootstrap requirements on a deliberately partial export. */
    private static function normalizeSubset(array $servers,array $records): array
    {
        $flags=[];$missing=[];
        foreach($servers as $i=>$row) {
            $flags[$i]=$row['default']??null;
            if(!is_bool($flags[$i]))throw new RuntimeException('invalid_dns_resource');
            if(($row['protocol']??null)==='doh'&&(!is_string($row['url']??null)||!self::safeUrl($row['url'])))throw new RuntimeException('private_dns_url');
            if(@inet_pton($row['address']??'')===false&&($row['bootstrap']??null)===[]){$missing[$i]=true;$servers[$i]['bootstrap']=['127.0.0.1'];}
        }
        $dummy=$servers===[];
        if($dummy)$servers=[['id'=>'share_validation_only','label'=>'','protocol'=>'udp','address'=>'127.0.0.1','port'=>53,'tls_name'=>'','url'=>'','bootstrap'=>[],'default'=>true,'domains'=>[]]];
        else $servers[0]['default']=true;
        $p=AsusSmartDnsProfile::normalize(['schema_version'=>1,'upstreams'=>$servers,'records'=>$records]);
        if($dummy)$p['upstreams']=[];
        else foreach($p['upstreams'] as $i=>&$row){$row['default']=$flags[$i];if(isset($missing[$i]))$row['bootstrap']=[];}
        return $p;
    }
    public static function validateExport(array $profile): void
    {
        if(($profile['schema_version']??null)!==1||!is_array($profile['upstreams']??null)||!is_array($profile['records']??null)||(!$profile['upstreams']&&!$profile['records']))throw new RuntimeException('invalid_dns_resource');
        self::normalizeSubset($profile['upstreams'],$profile['records']);
    }
    private static function domain(string $pattern): array
    {
        $exact=str_starts_with($pattern,'-.');$name=$exact?substr($pattern,2):$pattern;
        return ['name'=>AsusSmartDnsProfile::domain($name,'domain'),'include_subdomains'=>!$exact];
    }
    public static function parseLegacy(string $raw): array
    {
        if(strlen($raw)>65536||preg_match('//u',$raw)!==1)throw new RuntimeException('invalid_dns_resource');
        $servers=[];$members=[];$rules=[];$records=[];$warnings=[];
        $ignored=['bind','bind-tcp','resolv-hostname','cache-size','cache-mem-size','cache-persist','cache-file','prefetch-domain','serve-expired','speed-check-mode','response-mode','dualstack-ip-selection','ca-file','log-level','log-file','log-size','log-num','audit-enable','audit-file','audit-size','audit-num','server-name','tcp-idle-time'];
        foreach(explode("\n",$raw) as $number=>$line) {
            $line=trim(preg_split('/\s+#/',$line,2)[0]);if($line===''||str_starts_with($line,'#'))continue;
            $tokens=preg_split('/\s+/',$line);$directive=array_shift($tokens);
            if(in_array($directive,$ignored,true))continue;
            try {
                if(in_array($directive,['server','server-tcp','server-tls','server-https'],true)) {
                    $target=array_shift($tokens);if(!is_string($target))throw new RuntimeException();
                    $protocol=['server'=>'udp','server-tcp'=>'tcp','server-tls'=>'dot','server-https'=>'doh'][$directive];
                    $options=[];$groups=[];$default=true;
                    for($i=0;$i<count($tokens);$i++) {
                        $flag=$tokens[$i];$eq=strpos($flag,'=');$value=null;
                        if($eq!==false){$value=substr($flag,$eq+1);$flag=substr($flag,0,$eq);}
                        if($flag==='-exclude-default-group'){if($value!==null)throw new RuntimeException();$default=false;continue;}
                        if(!in_array($flag,['-host-name','-tls-host-verify','-host-ip','-group'],true))throw new RuntimeException();
                        if($value===null)$value=$tokens[++$i]??null;
                        if(!is_string($value)||$value===''||str_starts_with($value,'-'))throw new RuntimeException();
                        if($flag==='-group')$groups[]=$value;
                        elseif(isset($options[$flag]))throw new RuntimeException();else $options[$flag]=$value;
                    }
                    $url='';$port=$protocol==='dot'?853:53;
                    if($protocol==='doh') {
                        if(!self::safeUrl($target))throw new RuntimeException('private_dns_url');$parts=parse_url($target);$url=$target;$address=trim($parts['host']??'','[]');$port=$parts['port']??443;
                    }elseif(preg_match('/^\[([^]]+)\](?::([0-9]+))?$/D',$target,$m)){$address=$m[1];$port=isset($m[2])?(int)$m[2]:$port;}
                    elseif(substr_count($target,':')===1){[$address,$portText]=explode(':',$target,2);if(!preg_match('/^[0-9]{1,5}$/D',$portText))throw new RuntimeException();$port=(int)$portText;}
                    else $address=$target;
                    $tls=in_array($protocol,['dot','doh'],true)?($options['-tls-host-verify']??$options['-host-name']??($protocol==='doh'?$address:'')):'';
                    sort($groups);$groups=array_values(array_unique($groups));
                    $id='dns_'.substr(hash('sha256',json_encode([$protocol,$address,$port,$tls,$url,$groups,$default],JSON_THROW_ON_ERROR)),0,16);
                    $row=['id'=>$id,'label'=>substr(strtoupper($protocol).' · '.($tls?:$address),0,80),'protocol'=>$protocol,'address'=>$address,'port'=>$port,'tls_name'=>$tls,'url'=>$url,
                        'bootstrap'=>isset($options['-host-ip'])?[trim($options['-host-ip'],'[]')]:[],'default'=>$default,'domains'=>[]];
                    $row=self::normalizeSubset([$row],[])['upstreams'][0];
                    if(isset($servers[$id]))$row['bootstrap']=array_values(array_unique(array_merge($servers[$id]['bootstrap'],$row['bootstrap'])));
                    $servers[$id]=$row;$members[$id]=$groups;
                }elseif(in_array($directive,['nameserver','address'],true)) {
                    if(count($tokens)!==1||!preg_match('~^/([^/]+)/([^/]+)$~D',$tokens[0],$m))throw new RuntimeException();$match=self::domain($m[1]);
                    if($directive==='nameserver')$rules[]=['match'=>$match,'group'=>$m[2],'line'=>$number+1];
                    else {
                        $record=$match+['addresses'=>explode(',',$m[2]),'checked_at'=>null];
                        self::normalizeSubset([],[$record]);$records[]=$record;
                    }
                }else throw new RuntimeException();
            }catch(Throwable $e){$warnings[]=['line'=>$number+1,'code'=>$e->getMessage()==='private_dns_url'?'private_url_omitted':'unsupported_directive'];}
        }
        foreach($rules as $rule) {
            $found=false;
            foreach($members as $id=>$groups)if(in_array($rule['group'],$groups,true)){$servers[$id]['domains'][]=$rule['match'];$found=true;}
            if(!$found)$warnings[]=['line'=>$rule['line'],'code'=>'unresolved_group'];
        }
        try{$profile=self::normalizeSubset(array_values($servers),$records);}
        catch(Throwable $e){throw new RuntimeException('invalid_dns_resource');}
        if(count($warnings)>128)$warnings=array_merge(array_slice($warnings,0,127),[['line'=>0,'code'=>'additional_directives_omitted']]);
        return ['profile'=>$profile,'complete'=>$warnings===[],'warnings'=>$warnings,'scope'=>'upstreams_and_domain_rules'];
    }
    private static function source(string $id,array $profile,string $hash,array $warnings=[]): array
    {return ['id'=>$id,'origin'=>$id,'sha256'=>$hash,'profile'=>$profile,'complete'=>$warnings===[],'warnings'=>$warnings,'scope'=>'upstreams_and_domain_rules'];}
    public function sources(): array
    {
        $sources=[];$warnings=[];
        try {
            $managed=isset($this->deps['managed'])?($this->deps['managed'])():(function(){ $s=new AsusSmartDnsStore();return ['draft'=>$s->draft(),'active'=>$s->active()['profile']??null]; })();
            foreach(['active','draft'] as $kind)if(is_array($managed[$kind]??null)) {
                try {
                    $profile=AsusSmartDnsProfile::normalize($managed[$kind]);$hash=AsusSmartDnsProfile::hash($profile);
                    $profile=self::normalizeSubset($profile['upstreams'],$profile['records']);$sources[]=self::source($kind,$profile,$hash);
                }catch(Throwable $e){$warnings[]=['source'=>$kind,'code'=>'source_unavailable'];}
            }
        }catch(Throwable $e){$warnings[]=['source'=>'managed','code'=>'source_unavailable'];}
        if(file_exists($this->legacy)||is_link($this->legacy)) {
            try {
                $raw=$this->reader->bytes($this->legacy,65536);$parsed=self::parseLegacy($raw);
                $sources[]=self::source('legacy',$parsed['profile'],hash('sha256',$raw),$parsed['warnings']);
            }catch(Throwable $e){$warnings[]=['source'=>'legacy','code'=>'source_unavailable'];}
        }
        return ['sources'=>$sources,'warnings'=>$warnings];
    }
    public function prepare(array $selection): array
    {
        if(!array_is_list($selection)||count($selection)<1||count($selection)>3)throw new RuntimeException('invalid_request');
        $available=[];foreach($this->sources()['sources'] as $source)$available[$source['id']]=$source;
        $out=[];$seen=[];
        foreach($selection as $v) {
            if(!is_array($v)||array_diff(array_keys($v),['source_id','source_sha256','upstreams','records'])||!is_string($v['source_id']??null)||!is_string($v['source_sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$v['source_sha256'])||isset($seen[$v['source_id']]))throw new RuntimeException('invalid_request');
            $seen[$v['source_id']]=true;$source=$available[$v['source_id']]??null;
            if(!$source||!hash_equals($source['sha256'],$v['source_sha256']))throw new RuntimeException('source_changed');
            if(!is_array($v['upstreams']??null)||!array_is_list($v['upstreams'])||!is_array($v['records']??null)||!array_is_list($v['records'])||count($v['upstreams'])>32||count($v['records'])>64||(!$v['upstreams']&&!$v['records']))throw new RuntimeException('invalid_dns_resource');
            $ids=array_column($source['profile']['upstreams'],'id');$used=[];
            foreach($v['upstreams'] as $row)if(!is_array($row)||!in_array($row['id']??null,$ids,true)||isset($used[$row['id']]))throw new RuntimeException('invalid_dns_resource');else $used[$row['id']]=true;
            $records=[];$used=[];
            foreach($v['records'] as $row) {
                if(!is_array($row)||array_diff(array_keys($row),['index','value'])||!is_int($row['index']??null)||!isset($source['profile']['records'][$row['index']])||isset($used[$row['index']])||!is_array($row['value']??null))throw new RuntimeException('invalid_dns_resource');
                $used[$row['index']]=true;$records[]=$row['value'];
            }
            try{$profile=self::normalizeSubset($v['upstreams'],$records);}catch(Throwable $e){throw new RuntimeException('invalid_dns_resource');}
            $out[]=self::source($source['id'],$profile,$source['sha256'],$source['warnings']);
        }
        $result=['sources'=>$out];if(strlen(json_encode($result,JSON_THROW_ON_ERROR))>131072)throw new RuntimeException('output_limit');return $result;
    }
}
