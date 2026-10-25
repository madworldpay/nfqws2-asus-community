<?php
require_once __DIR__.'/openwrt-web.php';
require_once __DIR__.'/support-report.php';
require_once __DIR__.'/dpi-runtime.php';
/** Read-only native facts; never export raw ubus, UCI, hostnames, addresses or logs. */
final class NfqwsOpenWrtReport
{
    private static function token(mixed $v,string $pattern):?string
    {return is_string($v)&&preg_match($pattern,$v)?$v:null;}
    public static function platform():array
    {
        $board=NfqwsOpenWrtWeb::board();
        $raw=(string)@file_get_contents('/etc/openwrt_release',false,null,0,4096);
        preg_match("/^DISTRIB_ARCH='([A-Za-z0-9_.-]{1,64})'$/m",$raw,$arch);
        preg_match("/^DISTRIB_RELEASE='([0-9]{2}\\.[0-9]{2}\\.[0-9]{1,3})'$/m",$raw,$release);
        preg_match('/^([0-9]+(?:\.[0-9]+)?) /',(string)@file_get_contents('/proc/uptime'),$up);
        return ['model'=>'OpenWrt','platform'=>'openwrt','release'=>$release[1]??null,
            'target'=>self::token($board['release']['target']??null,'~^[A-Za-z0-9_-]{1,48}/[A-Za-z0-9_-]{1,48}$~D'),
            'package_arch'=>$arch[1]??null,'kernel'=>self::token(trim((string)@file_get_contents('/proc/sys/kernel/osrelease')),'/^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,4}$/D'),
            'uptime_seconds'=>isset($up[1])?(float)$up[1]:null];
    }
    private static function config(string $directory,string $name):string
    {
        if(!is_dir($directory))return '';
        try{$path=NfqwsPlatform::guardFile($directory,$name);$raw=@file_get_contents($path,false,null,0,262145);
            return is_string($raw)&&strlen($raw)<=262144?$raw:'';}catch(Throwable $e){return '';}
    }
    private static function identity(array $facts):array
    {
        $pid=$facts['pid']??null;$running=$facts['process_running']??null;
        $id=is_int($pid)?AsusDpiRuntime::identity($pid):null;
        $out=['boot'=>trim((string)@file_get_contents('/proc/sys/kernel/random/boot_id')),'pid'=>$id['pid']??null,
            'start_ticks'=>$id['starttime']??null,'exe'=>$id['exe']??null,'running'=>is_bool($running)?$running:null,'uid'=>null,'process_state'=>null];
        if($id){$status=(string)@file_get_contents('/proc/'.$pid.'/status',false,null,0,16384);
            if(preg_match('/^Uid:\s+([0-9]+)\s/m',$status,$m))$out['uid']=(int)$m[1];
            if(preg_match('/^State:\s+([RSDTZI])\s/m',$status,$m))$out['process_state']=$m[1];}
        return $out;
    }
    private static function resources(AsusReportIO $io,array $baseline,string $saved,string $runtime):array
    {
        $refs=[];$unresolved=0;$missing=0;$items=[];$problem=false;$values=new AsusReportValues();
        foreach(['config'=>$saved,'runtime'=>$runtime]as $source=>$text)foreach(AsusReportValues::referenceSettings($text)as $key=>$value){
            if(!str_starts_with($key,'NFQWS_')&&!str_starts_with($key,'MODE_'))continue;
            if($value===null){$unresolved++;continue;}
            preg_match_all('~/(?:opt/)?etc/nfqws2/(lists|lua|blobs)/([A-Za-z0-9_.-]+)~',$value,$matches,PREG_SET_ORDER);
            foreach($matches as $m){if(str_contains($m[2],'..')){$unresolved++;continue;}$kind=['lists'=>'list','lua'=>'lua','blobs'=>'blob'][$m[1]];$refs[$kind][$m[2]][$source]=true;}
            if(preg_match('~@/(?!etc/nfqws2/(?:lists|lua|blobs)/|opt/etc/nfqws2/(?:lists|lua|blobs)/|var/log/nfqws2)~',$value))$unresolved++;
        }
        foreach(['list'=>'LIST','lua'=>'LUA','blob'=>'BLOB']as $kind=>$alias)foreach(array_unique(array_merge(array_keys($refs[$kind]??[]),$io->resources($kind)))as $name){
            if(count($items)>=128){$problem=true;break 2;}
            $r=$io->readResource($kind,$name);$item=['id'=>$values->alias($alias,$name),'kind'=>$kind,'state'=>$r['state'],'referenced_by'=>array_keys($refs[$kind][$name]??[])];
            if($item['referenced_by']&&$r['state']==='missing')$missing++;
            if($r['state']==='available'){$item['bytes']=strlen($r['value']);
                if($kind==='list')$item['lines']=substr_count($r['value'],"\n")+($r['value']!==''&&!str_ends_with($r['value'],"\n")?1:0);
                else{$hash=$baseline['resources'][$kind.'/'.$name]['sha256']??null;$item['baseline_match']=is_string($hash)&&preg_match('/^[a-f0-9]{64}$/D',$hash)?hash_equals($hash,hash('sha256',$r['value'])):null;}
            }else $problem=true;
            $items[]=$item;
        }
        return AsusReportPlatform::section(['items'=>$items,'count'=>count($items),'missing_references'=>$missing,'unresolved_reference_groups'=>$unresolved],
            $problem||$missing||$unresolved?'partial':'available',$problem?'truncated':($missing?'missing':'unsupported'));
    }
    public function collect():array
    {
        $io=new AsusReportIO(['opt'=>'/']);$shared=new AsusSupportReport($io,new AsusReportValues());$begin=$io->now();
        $before=self::config('/etc/nfqws2','nfqws2.conf');$runtime=self::config('/tmp/run/nfqws2-native','config.env');
        $saved=AsusReportValues::runtimeSettings($before);$active=AsusReportValues::runtimeSettings($runtime);
        $q=AsusReportValues::decimal($active['NFQUEUE_NUM']??$saved['NFQUEUE_NUM']??'','65535');$q=$q!==null?(int)$q:null;
        $facts=NfqwsOpenWrtWeb::diagnostics();$id=self::identity($facts);$first=$shared->queueSample($q,$id);
        $sections=[];$section=static fn($data,$state='available',$reason=null)=>AsusReportPlatform::section($data,$state,$reason);
        $sections['platform']=$section(self::platform());
        $baselinePath=NfqwsPlatform::sharedFile('report-baseline.json',__DIR__.'/missing-baseline.json');
        $baseline=json_decode((string)@file_get_contents($baselinePath,false,null,0,131073),true);
        $engine=$io->engine();$known=($engine['state']??'')==='available'&&($baseline['engine']['sha256']??null)===($engine['sha256']??null);
        $data=['present'=>($engine['state']??'')==='missing'?false:(($engine['state']??'')==='available'?true:null),'baseline_match'=>$known,
            'version'=>$known?self::token($baseline['engine']['version']??null,'/^[0-9]+(?:\.[0-9]+){1,4}$/D'):null,'provider'=>$known?'nfqws2-keenetic':null];
        $sections['engine']=$section($data+array_intersect_key($engine,array_flip(['sha256','elf_class','elf_machine'])),($engine['state']??'')==='available'?'available':'unavailable',$engine['state']==='available'?null:$engine['state']);
        $free=@disk_free_space('/etc/nfqws2');$memory=(string)@file_get_contents('/proc/meminfo');$mem=[];
        foreach(['MemTotal','MemAvailable','MemFree']as $key)if(preg_match('/^'.$key.':\s+([0-9]{1,12}) kB$/m',$memory,$m))$mem[$key.'_kib']=$m[1];
        $sections['package']=$section(['platform'=>'openwrt','version'=>NfqwsOpenWrtWeb::version()?:null,'php_version'=>PHP_MAJOR_VERSION.'.'.PHP_MINOR_VERSION.'.'.PHP_RELEASE_VERSION,
            'php_integer_bits'=>PHP_INT_SIZE*8,'storage_free_bytes'=>$free===false?null:sprintf('%.0f',$free),'memory'=>$mem]);
        $loaded=is_dir('/sys/module/ark');$flags=[];foreach(AsusReportPlatform::ARK_KEYS as $key)$flags[$key]=['presence'=>'absent','value'=>null];
        $sections['ark']=$section(['present'=>$loaded?'present':'absent','loaded'=>$loaded?'loaded':'unloaded','nvram_state'=>'unsupported','component_state'=>'available','flags'=>$flags,
            'backup'=>['present'=>false,'valid'=>false,'created'=>null,'restored'=>null]]);
        $sections['process']=$section(['running'=>$id['running'],'uid'=>$id['uid'],'state'=>$id['process_state'],'age_seconds'=>null],$id['running']===null?'unavailable':'available');
        // Existing network projection aliases interfaces/clients and removes raw IPs.
        $sections+= (new AsusReportNetwork($io,new AsusReportValues()))->collect($saved,$active);
        $sections['rules']=$section(['platform'=>'openwrt','capture'=>in_array($facts['capture']??null,['ready','waiting_uplink'],true)?$facts['capture']:'unknown',
            'acceleration'=>in_array($facts['acceleration']??null,['none','system','managed'],true)?$facts['acceleration']:'unknown'],$facts!==[]?'available':'partial',$facts!==[]?null:'unsupported');
        $sections['resources']=self::resources($io,is_array($baseline)?$baseline:[],$before,$runtime);
        $sections['errors']=$section(['observed_prerequisite_failures'=>$before===''?['configuration_missing']:[],'historical_startup_error'=>'unknown']);
        $sections['dns']=$section([], 'unavailable','unsupported');
        $io->pause(max(0,10-($io->now()-$first['_time'])));
        $last=$shared->queueSample($q,self::identity(NfqwsOpenWrtWeb::diagnostics()));$comparison=$shared->compareQueue($first,$last);
        if($before!==self::config('/etc/nfqws2','nfqws2.conf')||$runtime!==self::config('/tmp/run/nfqws2-native','config.env'))$comparison=['result'=>'changed_during_collection','delta'=>null,'interval_ms'=>$comparison['interval_ms']];
        $view=static function($v){foreach(array_keys($v)as $k)if(str_starts_with($k,'_'))unset($v[$k]);return $v;};
        $sections['nfqueue']=$section(['samples'=>[$view($first),$view($last)],'comparison'=>$comparison],in_array($comparison['result'],['increased','unchanged','unbound'],true)?'available':'partial','unsupported');
        $failures=[];foreach($sections as $name=>$v)if($v['state']!=='available')$failures[]=['section'=>$name,'code'=>$v['reason']??'unsupported'];
        return ['schema_version'=>1,'collector_version'=>'1.1.0','model'=>'OpenWrt','captured_at'=>gmdate('Y-m-d\TH:i:s\Z'),
            'duration_ms'=>(int)round(($io->now()-$begin)*1000),'complete'=>$failures===[],'sections'=>$sections,'failures'=>$failures];
    }
}
