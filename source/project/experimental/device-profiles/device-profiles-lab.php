<?php
require_once __DIR__.'/device-profiles-paths.php';
/** Isolated draft experiment. No operation here changes traffic or services. */
if (!class_exists('NfqwsPlatform', false)) require_once __DIR__.'/platform.php';

final class NfqwsDeviceProfilesLab
{
    private string $root;
    private int $owner;
    private $sources;
    public function __construct(?string $root=null, ?callable $sources=null, ?int $owner=null)
    {
        $this->root=$root??NfqwsPlatform::settings()['web_config'].'/device-profiles-lab';
        $this->owner=$owner??0;
        $this->sources=$sources??fn()=>$this->localSources();
    }
    private static function keys(array $v,array $keys,string $error='invalid_draft'):void
    {
        $actual=array_keys($v);sort($actual);sort($keys);
        if($actual!==$keys)throw new RuntimeException($error);
    }
    private static function name(mixed $v):string
    {
        if(!is_string($v)||!preg_match('/^[^\x00-\x1f\x7f]{1,64}$/uD',$v)||trim($v)==='')throw new RuntimeException('invalid_draft');
        return trim($v);
    }
    public static function address(mixed $v):string
    {
        if(!is_string($v)||strlen($v)>45||str_contains($v,'%'))throw new RuntimeException('invalid_draft');
        $packed=@inet_pton($v);
        if($packed===false||$packed===str_repeat("\0",16)||$packed===str_repeat("\0",15)."\1"||
            (strlen($packed)===4&&(ord($packed[0])===0||ord($packed[0])===127||ord($packed[0])>=224))||
            (strlen($packed)===16&&(ord($packed[0])===255||substr($packed,0,12)===str_repeat("\0",10)."\xff\xff")))throw new RuntimeException('invalid_draft');
        return strtolower(inet_ntop($packed));
    }
    private static function mac(mixed $v):string
    {
        if(!is_string($v))throw new RuntimeException('invalid_draft');
        if($v==='')return '';
        $v=strtolower($v);
        if(!preg_match('/^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$/D',$v)||$v==='00:00:00:00:00:00'||(hexdec(substr($v,0,2))&1))throw new RuntimeException('invalid_draft');
        return $v;
    }
    public static function normalize(array $v):array
    {
        self::keys($v,['schema_version','mode','devices','profiles']);
        if($v['schema_version']!==1||!in_array($v['mode'],['common','split'],true)||
            !is_array($v['devices'])||!array_is_list($v['devices'])||count($v['devices'])>128||
            !is_array($v['profiles'])||!array_is_list($v['profiles'])||count($v['profiles'])>16)throw new RuntimeException('invalid_draft');
        $devices=[];$ids=[];$identities=[];
        foreach($v['devices'] as $d){
            if(!is_array($d))throw new RuntimeException('invalid_draft');
            self::keys($d,['id','name','mac','addresses']);
            if(!is_string($d['id'])||!preg_match('/^(?:manual-[a-f0-9]{8}|mac-[a-f0-9]{12}|ip-[a-f0-9-]{3,80})$/D',$d['id'])||isset($ids[$d['id']])||
                !is_array($d['addresses'])||!array_is_list($d['addresses'])||count($d['addresses'])>16)throw new RuntimeException('invalid_draft');
            $id=$d['id'];$ids[$id]=true;$mac=self::mac($d['mac']);$addresses=[];
            if(str_starts_with($id,'mac-')&&$id!=='mac-'.str_replace(':','',$mac))throw new RuntimeException('invalid_draft');
            foreach($d['addresses'] as $ip)$addresses[]=self::address($ip);
            if($mac===''&&!$addresses)throw new RuntimeException('invalid_draft');
            if(count(array_unique($addresses))!==count($addresses))throw new RuntimeException('invalid_draft');
            foreach(array_merge($mac!==''?['mac:'.$mac]:[],array_map(fn($ip)=>'ip:'.$ip,$addresses)) as $key){
                if(isset($identities[$key]))throw new RuntimeException('invalid_draft');$identities[$key]=true;
            }
            $devices[]=['id'=>$id,'name'=>self::name($d['name']),'mac'=>$mac,'addresses'=>$addresses];
        }
        $profiles=[];$pids=[];
        foreach($v['profiles'] as $p){
            if(!is_array($p))throw new RuntimeException('invalid_draft');
            self::keys($p,['id','name','enabled','strategy','device_ids']);
            if(!is_string($p['id'])||!preg_match('/^profile-[a-f0-9]{8}$/D',$p['id'])||isset($pids[$p['id']])||!is_bool($p['enabled'])||
                !is_string($p['strategy'])||!preg_match('/^(?:current|stock|saved-[a-f0-9]{16})$/D',$p['strategy'])||!is_array($p['device_ids'])||!array_is_list($p['device_ids'])||count($p['device_ids'])>128)throw new RuntimeException('invalid_draft');
            $seen=[];foreach($p['device_ids'] as $id){if(!is_string($id)||!isset($ids[$id])||isset($seen[$id]))throw new RuntimeException('invalid_draft');$seen[$id]=true;}
            $pids[$p['id']]=true;$profiles[]=['id'=>$p['id'],'name'=>self::name($p['name']),'enabled'=>$p['enabled'],'strategy'=>$p['strategy'],'device_ids'=>$p['device_ids']];
        }
        $result=['schema_version'=>1,'mode'=>$v['mode'],'devices'=>$devices,'profiles'=>$profiles];
        if(strlen(self::encode($result))>65536)throw new RuntimeException('invalid_draft');
        return $result;
    }
    private static function encode(array $v):string{return json_encode($v,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);}
    private function directory(bool $create=false):bool
    {
        clearstatcache(true,$this->root);$s=@lstat($this->root);
        if($s===false&&!$create)return false;
        if($s===false){
            $parent=dirname($this->root);
            try{NfqwsDeviceProfilesPaths::guard($parent,basename($this->root),$this->owner);}catch(Throwable $e){throw new RuntimeException('storage_unavailable');}
            $mask=umask(0077);try{if(!@mkdir($this->root,0700))throw new RuntimeException('storage_unavailable');}finally{umask($mask);}
        }
        try{NfqwsDeviceProfilesPaths::guard($this->root,'draft.json',$this->owner);}catch(Throwable $e){throw new RuntimeException('storage_unavailable');}
        return true;
    }
    private function safeFile(string $name):string
    {
        try{return NfqwsDeviceProfilesPaths::guard($this->root,$name,$this->owner);}catch(Throwable $e){throw new RuntimeException('storage_unavailable');}
    }
    private function read():array
    {
        $default=['schema_version'=>1,'mode'=>'common','devices'=>[],'profiles'=>[]];
        if(!$this->directory())return $default;
        $path=$this->safeFile('draft.json');if(!file_exists($path))return $default;
        $raw=@file_get_contents($path,false,null,0,65537);
        if(!is_string($raw)||strlen($raw)>65536)throw new RuntimeException('storage_unavailable');
        try{$v=json_decode($raw,true,16,JSON_THROW_ON_ERROR);if(!is_array($v))throw new RuntimeException();return self::normalize($v);}
        catch(Throwable $e){throw new RuntimeException('storage_unavailable');}
    }
    public function status():array
    {
        $draft=$this->read();return ['schema_version'=>1,'experimental'=>true,'applied'=>false,'revision'=>hash('sha256',self::encode($draft)),
            'draft'=>$draft,'discovery'=>$this->discovery(),'templates'=>[['id'=>'current','name'=>'Текущая стратегия'],['id'=>'stock','name'=>'Стоковая стратегия']]];
    }
    public function save(array $draft,string $revision):array
    {
        $draft=self::normalize($draft);
        if(!preg_match('/^[a-f0-9]{64}$/D',$revision))throw new RuntimeException('invalid_request');
        $this->directory(true);$mask=umask(0077);$lock=null;$temp=null;
        try{
            $lock=@fopen($this->safeFile('write.lock'),'c+');
            if(!$lock)throw new RuntimeException('storage_unavailable');
            if(!flock($lock,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');
            if(!hash_equals(hash('sha256',self::encode($this->read())),$revision))throw new RuntimeException('stale_revision');
            $temp=$this->safeFile('draft-'.bin2hex(random_bytes(8)).'.tmp');$f=@fopen($temp,'x');
            if(!$f)throw new RuntimeException('storage_unavailable');
            try{$raw=self::encode($draft);if(fwrite($f,$raw)!==strlen($raw)||!fflush($f)||(function_exists('fsync')&&!fsync($f)))throw new RuntimeException('storage_unavailable');}finally{fclose($f);}
            if(!@rename($temp,$this->safeFile('draft.json')))throw new RuntimeException('storage_unavailable');$temp=null;
        }finally{if($temp!==null)@unlink($temp);if(is_resource($lock)){flock($lock,LOCK_UN);fclose($lock);}umask($mask);}
        return $this->status();
    }
    public function preview(array $draft):array
    {
        $draft=self::normalize($draft);$profiles=[];$warnings=[];$assignments=[];$discovered=$this->discovery();
        $resolved=[];foreach($discovered['devices'] as $d)if($d['mac']!==''&&$d['addresses'])$resolved[$d['mac']]=true;
        foreach($draft['profiles'] as $i=>$p){$profiles[]=$p+['priority'=>$i+1];if($p['enabled']&&!$p['device_ids'])$warnings[]='empty_profile';}
        if($draft['mode']==='split'&&!$profiles)$warnings[]='no_profiles';
        foreach($draft['devices'] as $d){
            $matches=[];if($draft['mode']==='split')foreach($profiles as $p)if($p['enabled']&&in_array($d['id'],$p['device_ids'],true))$matches[]=$p['id'];
            if($d['mac']!==''&&!isset($resolved[$d['mac']]))$warnings[]='unresolved_mac';
            $assignments[]=['device_id'=>$d['id'],'profile_ids'=>$matches,'fallback'=>'current'];
        }
        return ['schema_version'=>1,'mode'=>$draft['mode'],'applied'=>false,'profiles'=>$profiles,'assignments'=>$assignments,'warnings'=>array_values(array_unique($warnings))];
    }
    private static function inSubnet(string $ip,string $subnet):bool
    {
        $parts=explode('/',$subnet,2);$a=@inet_pton($ip);$b=@inet_pton($parts[0]);
        if($a===false||$b===false||strlen($a)!==strlen($b)||!isset($parts[1])||!preg_match('/^[0-9]+$/D',$parts[1]))return false;
        $prefix=(int)$parts[1];if($prefix<1||$prefix>strlen($a)*8)return false;
        $whole=intdiv($prefix,8);$bits=$prefix%8;
        return substr($a,0,$whole)===substr($b,0,$whole)&&(!$bits||((ord($a[$whole])^ord($b[$whole]))&(255<<(8-$bits)))===0);
    }
    private function discovery():array
    {
        $out=['state'=>'unavailable','checked_at'=>gmdate('c'),'interfaces'=>[],'devices'=>[]];
        try{$src=($this->sources)();}catch(Throwable $e){return $out;}
        $ifs=[];foreach(array_slice((array)($src['interfaces']??[]),0,32) as $v)if(is_string($v)&&preg_match('/^[A-Za-z0-9_.-]{1,32}$/D',$v))$ifs[$v]=true;
        if(!$ifs)return $out;$out['interfaces']=array_keys($ifs);$map=[];$partial=($src['complete']??false)!==true;
        $add=function(string $ip,string $mac,string $source,string $name='',bool $reachable=false)use(&$map,&$partial){
            try{$ip=self::address($ip);$mac=self::mac($mac);}catch(Throwable $e){return;}
            if($mac==='')return;$id='mac-'.str_replace(':','',$mac);
            if(!isset($map[$id])){if(count($map)>=128){$partial=true;return;}$map[$id]=['id'=>$id,'name'=>'','mac'=>$mac,'addresses'=>[],'sources'=>[],'seen'=>'known'];}
            if(!in_array($ip,$map[$id]['addresses'],true)){if(count($map[$id]['addresses'])<16)$map[$id]['addresses'][]=$ip;else $partial=true;}
            if(!in_array($source,$map[$id]['sources'],true))$map[$id]['sources'][]=$source;
            if($name!==''&&$name!=='*'&&preg_match('/^[^\x00-\x1f\x7f]{1,64}$/uD',$name))$map[$id]['name']=$name;
            if($reachable)$map[$id]['seen']='reachable';
        };
        $leases=(string)($src['leases']??'');$neighbors=(string)($src['neighbors']??'');$arp=(string)($src['arp']??'');
        foreach([$leases,$neighbors,$arp] as $raw)if(strlen($raw)>262144){$partial=true;}
        foreach(explode("\n",substr($leases,0,262144)) as $line){
            $p=preg_split('/\s+/',trim($line));if(count($p)<4||!preg_match('/^[0-9]+$/D',$p[0])||($p[0]!=='0'&&(float)$p[0]<time()))continue;
            $inside=false;foreach((array)($src['subnets']??[]) as $subnet)if(is_string($subnet)&&self::inSubnet($p[2],$subnet))$inside=true;
            if($inside)$add($p[2],$p[1],'dhcp',$p[3]);
        }
        foreach(explode("\n",substr($neighbors,0,262144)) as $line)if(preg_match('/^(\S+)\s+dev\s+(\S+)\s+lladdr\s+(\S+)\s+(.*)$/D',trim($line),$m)&&isset($ifs[$m[2]])&&!preg_match('/\b(?:FAILED|INCOMPLETE)\b/',$m[4]))$add($m[1],$m[3],'neighbor','',preg_match('/\bREACHABLE\b/',$m[4])===1);
        foreach(explode("\n",substr($arp,0,262144)) as $line){$p=preg_split('/\s+/',trim($line));if(count($p)>=6&&isset($ifs[$p[5]])&&$p[2]!=='0x0')$add($p[0],$p[3],'arp');}
        $out['state']=$partial?'partial':'available';$out['devices']=array_values($map);
        // Keep every valid saved draft loadable even with a full neighbor table.
        while(strlen(self::encode($out))>49152){array_pop($out['devices']);$out['state']='partial';}
        return $out;
    }
    public static function observationFile(string $path,int $limit):array
    {
        if($limit<1||$limit>262144)throw new RuntimeException('invalid_request');
        $raw=@file_get_contents($path,false,null,0,$limit+1);
        return ['content'=>is_string($raw)?substr($raw,0,$limit):'',
            'complete'=>is_string($raw)&&strlen($raw)<=$limit];
    }
    private function localSources():array
    {
        $out=['interfaces'=>[],'subnets'=>[],'leases'=>'','neighbors'=>'','arp'=>'','complete'=>true];
        $ip=null;foreach(['/sbin/ip','/usr/sbin/ip','/opt/sbin/ip','/bin/ip','/opt/bin/ip'] as $candidate)if(is_executable($candidate)){$ip=$candidate;break;}
        if($ip===null){$out['complete']=false;return $out;}
        if(NfqwsPlatform::native()){
            $r=NfqwsPlatform::run(['/bin/ubus','call','network.interface','dump'],2,[],65536);
            // OpenWrt commonly installs ubus under /bin; use only this trusted path.
            $data=json_decode(implode("\n",$r['output']),true);if($r['status']!==0||!is_array($data)){$out['complete']=false;return $out;}
            foreach((array)($data['interface']??[]) as $n){
                $name=(string)($n['interface']??'');$dev=(string)($n['l3_device']??'');$default=false;
                foreach((array)($n['route']??[]) as $route)if(in_array($route['target']??null,['0.0.0.0','::'],true)&&(int)($route['mask']??-1)===0)$default=true;
                if(($n['up']??false)!==true||$default||preg_match('/^(?:wan|wwan|loopback)/i',$name)||!preg_match('/^[A-Za-z0-9_.-]{1,32}$/D',$dev)||
                    !($name==='lan'||str_starts_with($dev,'br-')||is_dir('/sys/class/net/'.$dev.'/bridge')))continue;
                $out['interfaces'][]=$dev;
                foreach(array_merge((array)($n['ipv4-address']??[]),(array)($n['ipv6-address']??[])) as $a)if(isset($a['address'],$a['mask']))$out['subnets'][]=$a['address'].'/'.$a['mask'];
            }
        }else{
            $r=NfqwsPlatform::run([$ip,'-o','addr','show'],2,[],65536);
            if($r['status']!==0)$out['complete']=false;
            foreach($r['output'] as $line)if(preg_match('/^\d+: (br[0-9]+)(?:@\S+)?\s+inet6?\s+(\S+)\//',$line,$m)){
                $out['interfaces'][]=$m[1];if(preg_match('/\s+inet6?\s+(\S+\/\d+)/',$line,$a))$out['subnets'][]=$a[1];
            }
        }
        $out['interfaces']=array_values(array_unique($out['interfaces']));
        if(count($out['interfaces'])>32)$out['complete']=false;
        $r=NfqwsPlatform::run([$ip,'neigh','show'],2,[],262144);$out['neighbors']=implode("\n",$r['output']);if($r['status']!==0)$out['complete']=false;
        foreach(['/tmp/dhcp.leases','/var/lib/misc/dnsmasq.leases','/tmp/var/lib/misc/dnsmasq.leases','/opt/var/lib/misc/dnsmasq.leases'] as $path)if(is_file($path)){$read=self::observationFile($path,131072);$out['leases'].=$read['content']."\n";if(!$read['complete'])$out['complete']=false;if(strlen($out['leases'])>262144){$out['complete']=false;break;}}
        $read=self::observationFile('/proc/net/arp',131072);$out['arp']=$read['content'];if(!$read['complete'])$out['complete']=false;
        return $out;
    }
    public static function validateRequest(array $p):void
    {
        $cmd=$p['cmd']??null;$inputs=['deviceprofilesstatus'=>[],'deviceprofilessave'=>['draft','revision'],'deviceprofilespreview'=>['draft']];
        if(!is_string($cmd)||!isset($inputs[$cmd]))throw new RuntimeException('invalid_request');
        self::keys($p,array_merge(['cmd','csrf_token'],$inputs[$cmd]),'invalid_request');
        foreach($p as $v)if(!is_string($v)||strlen($v)>65536)throw new RuntimeException('invalid_request');
        if(strlen($p['csrf_token'])>1024)throw new RuntimeException('invalid_request');
    }
    public function dispatch(array $p):array
    {
        self::validateRequest($p);if($p['cmd']==='deviceprofilesstatus')return $this->status();
        try{$v=json_decode($p['draft'],true,16,JSON_THROW_ON_ERROR);if(!is_array($v))throw new RuntimeException();}catch(Throwable $e){throw new RuntimeException('invalid_draft');}
        return $p['cmd']==='deviceprofilessave'?$this->save($v,$p['revision']):$this->preview($v);
    }
}
