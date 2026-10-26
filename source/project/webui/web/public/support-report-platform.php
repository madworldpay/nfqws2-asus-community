<?php
require_once __DIR__.'/support-report-io.php';
require_once __DIR__.'/support-report-values.php';

final class AsusReportPlatform
{
    public const ARK_KEYS = ['ark_qoe_enable','ark_iam_enable','ark_limiter_enable','ark_log_enable','ark_hyqos_enable','ark_mals_enable','ark_adblock_enable','ark_tracker_enable','ark_ids_enable'];
    private array $nvram = [];
    private string $nvramState = 'missing';
    public function __construct(private AsusReportIO $io, private AsusReportValues $values) {}
    public static function section(array $data, string $state='available', ?string $reason=null): array
    {
        $s=['state'=>$state,'data'=>$data]; if($reason!==null) $s['reason']=$reason; return $s;
    }
    public function readNvram(): array
    {
        $keys=array_merge(self::ARK_KEYS,['productid','odmpid','firmver','buildno','extendno','sw_mode','jffs2_scripts']);
        foreach ([0,1] as $unit) foreach (['state_t','proto','pppoe_ifname','ifname','gw_ifname'] as $key) $keys[]="wan{$unit}_$key";
        $this->nvram=[];
        $result=$this->io->streamCommand('nvram',function($line)use($keys){
            $pair=explode('=',$line,2);
            if(count($pair)===2 && in_array($pair[0],$keys,true)) $this->nvram[$pair[0]]=array_key_exists($pair[0],$this->nvram) ? null : $pair[1];
        },1.5);
        $this->nvramState=$result['state'];
        return ['state'=>$this->nvramState,'values'=>$this->nvram];
    }
    public static function model(?string $s): string
    {
        if($s==='OpenWrt')return $s;
        return is_string($s) && preg_match('/^(?:(?:GT|RT|TUF|DSL|4G)-(?:AC|AXE?|BE)[0-9]{2,6}(?:U|G|Go|Pro|AI|S|P|V[0-9]){0,2}|(?:RT-)?BE[0-9]{2,4}|ZenWiFi_(?:XT|ET|BT)[0-9]{1,3})$/D',$s) ? $s : 'ASUS-unknown';
    }
    public function identity(): array
    {
        $boot=$this->io->read('boot',128); $pid=$this->io->read('pid',32);
        $raw=trim($pid['value']); $p=AsusReportValues::decimal($raw,'2147483647');
        $out=['boot'=>$boot['state']==='available' ? trim($boot['value']) : null,'pid'=>null,'start_ticks'=>null,'exe'=>null,'running'=>null,'uid'=>null,'process_state'=>null];
        if($pid['state']==='missing') { $out['running']=false; return $out; }
        if($pid['state']!=='available' || $p===null || (int)$p<=1) return $out;
        $p=(int)$p; $out['pid']=$p;
        $exe=$this->io->readProcess($p,'exe'); $stat=$this->io->readProcess($p,'stat'); $status=$this->io->readProcess($p,'status');
        if($exe['state']==='missing' && $stat['state']==='missing') { $out['running']=false; return $out; }
        if($exe['state']!=='available' || $stat['state']!=='available' || $status['state']!=='available') return $out;
        $out['exe']=$exe['value']; $expected=$this->io->enginePath();
        if(!in_array($exe['value'],[$expected,$expected.' (deleted)'],true)) { $out['running']=false; return $out; }
        if(!preg_match('/^\d+ \(.*\) ([A-Z]) (.*)$/sD',trim($stat['value']),$m)) return $out;
        $tail=preg_split('/\s+/',$m[2]); $start=AsusReportValues::decimal($tail[18]??'','18446744073709551615');
        if($start===null || !preg_match('/^Uid:\s+([0-9]+)/m',$status['value'],$uid)) return $out;
        $uid=AsusReportValues::decimal($uid[1],'2147483647'); if($uid===null) return $out;
        $out['start_ticks']=$start; $out['uid']=(int)$uid; $out['process_state']=in_array($m[1],['R','S','D','T','Z','I'],true)?$m[1]:null;
        $out['running']=$m[1]!=='Z'; return $out;
    }
    private static function opkgWord(string &$tail, bool $last): string
    {
        $tail=ltrim($tail);
        if(str_starts_with($tail,'"')) {
            $end=strpos($tail,'"',1);
            $after=$end!==false?substr($tail,$end+1,1):'';
            if($end!==false && (!$last || $after==='' || preg_match('/\s/',$after))) {
                $value=substr($tail,1,$end-1);$tail=substr($tail,$end+1);return $value;
            }
        }
        preg_match('/^\S*/',$tail,$m);$tail=substr($tail,strlen($m[0]));return $m[0];
    }
    public static function abi(string $text): ?string
    {
        $seen=[];$highest=null;$primary=null;$tie=false;
        foreach(explode("\n",$text) as $tail) {
            $kind=self::opkgWord($tail,false);$name=self::opkgWord($tail,false);$priority=self::opkgWord($tail,true);
            $tail=ltrim($tail);$tail=preg_replace('/^\S*/','',$tail);
            if(trim($tail)!=='' || $kind!=='arch' || isset($seen[$name])) continue;
            $seen[$name]=true;if($name==='all')continue;
            preg_match('/^[ \t]*([+-]?[0-9]+)/',$priority,$n);$number=$n[1]??'0';
            $limit=str_starts_with($number,'-')?'2147483648':'2147483647';
            if(AsusReportValues::decimal(ltrim($number,'+-'),$limit)===null)return null;
            $number=(float)$number;
            if($highest===null || $number>$highest){$highest=$number;$primary=$name;$tie=false;}
            elseif($number===$highest)$tie=true;
        }
        return !$tie && $highest>0 && in_array($primary,['armv7-2.6','armv7-3.2','aarch64-3.10'],true)?$primary:null;
    }
    public function collect(): array
    {
        $nv=$this->readNvram(); $n=$nv['values']; $model=self::model(($n['odmpid']??'') ?: ($n['productid']??''));
        $kernel=$this->io->read('kernel',128); $k=trim($kernel['value']);
        if(!preg_match('/^[0-9]{1,3}\.[0-9]{1,3}(?:\.[0-9]{1,4})?(?:[-_](?:merlin|asus|gnuton|[0-9_.]+))?$/Di',$k)) $k=null;
        $machine=[];$mr=$this->io->streamCommand('machine',function($line)use(&$machine){ if(in_array(trim($line),['aarch64','armv7l','armv8l'],true)) $machine[]=trim($line); },0.5);
        $uptime=$this->io->read('uptime',128);preg_match('/^([0-9]+)(?:\.[0-9]+)? /',$uptime['value'],$up);
        $firmware=[];
        foreach(['firmver','buildno','extendno'] as $key) $firmware[$key]=isset($n[$key]) && preg_match('/^[0-9]{1,8}(?:[._-][0-9]{1,8})*(?:[_-]gnuton[0-9._-]*)?$/Di',$n[$key]) ? $n[$key] : null;
        $platform=['model'=>$model,'kernel'=>$k,'architecture'=>count($machine)===1?$machine[0]:null,'firmware'=>$firmware,'router_mode'=>isset($n['sw_mode']) && in_array($n['sw_mode'],['1','2','3','4','5'],true)?(int)$n['sw_mode']:null,'uptime_seconds'=>isset($up[1]) ? (float)$up[1] : null];
        $baselineRead=$this->io->read('baseline'); $baseline=json_decode($baselineRead['value'],true);
        if(!is_array($baseline) || ($baseline['schema_version']??null)!==1) $baseline=[];
        if(!is_array($baseline['engine']??null)) $baseline['engine']=[];
        if(!is_array($baseline['resources']??null)) $baseline['resources']=[];
        $package=$this->io->read('package',16384);preg_match('/^Version: ([0-9]+\.[0-9]+\.[0-9]+-asus[0-9]+\+b[1-9][0-9]*)$/m',$package['value'],$version);
        $bversion=$baseline['package_version']??null;
        if(!is_string($bversion) || !preg_match('/^[0-9]+\.[0-9]+\.[0-9]+-asus[0-9]+\+b[1-9][0-9]*$/D',$bversion)) $bversion=null;
        $opkg=$this->io->read('opkg');$abiText=$opkg['value'];
        $abiComplete=in_array($opkg['state'],['available','missing'],true);
        $dropins=$this->io->resources('opkg');
        if(count($dropins)>128 || !in_array($this->io->resourcesState('opkg'),['available','missing'],true))$abiComplete=false;
        foreach($dropins as $file) if(str_ends_with($file,'.conf')) {
            $r=$this->io->readResource('opkg',$file);
            if($r['state']!=='available')$abiComplete=false;
            if(strlen($abiText)+strlen($r['value'])>262144){$abiComplete=false;break;}
            $abiText.="\n".$r['value'];
        }
        $abi=$abiComplete?self::abi($abiText):null;
        $runtimeComponents=$this->io->runtimeComponents($abi);
        $engine=$this->io->engine();$known=$engine['state']==='available' && ($baseline['engine']['sha256']??null)===($engine['sha256']??null);
        $engineData=['present'=>$engine['state']==='missing'?false:($engine['state']==='available'?true:null),'baseline_match'=>$known,'version'=>$known && is_string($baseline['engine']['version']??null) && preg_match('/^[0-9]+(?:\.[0-9]+){1,4}$/D',$baseline['engine']['version'])?$baseline['engine']['version']:null,
            'provider'=>$known && ($baseline['engine']['provider']??null)==='nfqws2-keenetic'?'nfqws2-keenetic':null];
        if($engine['state']==='available') $engineData+=array_intersect_key($engine,array_flip(['sha256','elf_class','elf_machine']));
        $modules=$this->io->read('modules');$loaded=$modules['state']==='available'?(preg_match('/^ark\s/m',$modules['value'])?'loaded':'unloaded'):'unknown';
        $component=$this->io->arkComponents();if(($component['loaded']??false)===true)$loaded='loaded';$present=$loaded==='loaded'?'present':($component['present']===null?'unknown':($component['present']?'present':'absent'));
        $flags=[];$flagProblem=false;
        foreach(self::ARK_KEYS as $key) {
            $has=array_key_exists($key,$n); $val=$has?$n[$key]:null;
            $valid=$val==='' || (is_string($val) && AsusReportValues::decimal($val,'2147483647')!==null);
            $flags[$key]=['presence'=>$has?'present':($this->nvramState==='available'?'absent':'unknown'),'value'=>$valid?$val:null];
            if(($has&&!$valid)||(!$has&&$this->nvramState!=='available')) $flagProblem=true;
        }
        $backup=$this->io->read('backup',65536);$backupData=json_decode($backup['value'],true);
        $backupView=['present'=>$backup['state']==='available'?true:($backup['state']==='missing'?false:null),'valid'=>false,'created'=>null,'restored'=>null];
        if(is_array($backupData) && ($backupData['version']??null)===1 && is_bool($backupData['restored']??null) && is_string($backupData['created']??null) && preg_match('/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)$/D',$backupData['created'])) {
            $checksum=$backupData['checksum']??null;unset($backupData['checksum']);
            if(is_string($checksum) && hash_equals(hash('sha256',json_encode($backupData,JSON_UNESCAPED_SLASHES)),$checksum)) $backupView=['present'=>true,'valid'=>true,'created'=>$backupData['created'],'restored'=>$backupData['restored']];
        }
        $identity=$this->identity();$resources=[];$resourceProblem=false;$total=0;$references=[];$unresolved=0;$missing=0;
        foreach(['config','runtime'] as $source) {
            $read=$this->io->read($source);$settings=AsusReportValues::referenceSettings($read['value']);
            foreach($settings as $key=>$value) {
                if(!str_starts_with($key,'NFQWS_')&&!str_starts_with($key,'MODE_'))continue;
                if($value===null) {++$unresolved;continue;}
                preg_match_all('~/opt/etc/nfqws2/(lists|lua|blobs)/([A-Za-z0-9_.-]+)~',$value,$matches,PREG_SET_ORDER);
                foreach($matches as $match) {
                    $kind=['lists'=>'list','lua'=>'lua','blobs'=>'blob'][$match[1]];
                    if(str_contains($match[2],'..')) {++$unresolved;continue;}
                    $references[$kind][$match[2]][$source]=true;
                }
                if(preg_match('~@/(?!opt/etc/nfqws2/(?:lists|lua|blobs)/)~',$value))++$unresolved;
            }
        }
        if($unresolved) $resourceProblem=true;
        foreach(['list'=>'LIST','lua'=>'LUA','blob'=>'BLOB'] as $kind=>$aliasKind) foreach(array_unique(array_merge(array_keys($references[$kind]??[]),$this->io->resources($kind))) as $name) {
            if(++$total>128) {$resourceProblem=true;break 2;}
            $r=$this->io->readResource($kind,$name);$item=['id'=>$this->values->alias($aliasKind,$name),'kind'=>$kind,'state'=>$r['state'],'referenced_by'=>array_keys($references[$kind][$name]??[])];
            if($item['referenced_by']&&$r['state']==='missing')++$missing;
            if($r['state']==='available') {
                $item['bytes']=strlen($r['value']);
                if($kind==='list') $item['lines']=substr_count($r['value'],"\n")+($r['value']!==''&&!str_ends_with($r['value'],"\n")?1:0);
                if($kind!=='list') $item['baseline_match']=is_string($baseline['resources']["$kind/$name"]['sha256']??null)&&preg_match('/^[a-f0-9]{64}$/D',$baseline['resources']["$kind/$name"]['sha256']) ? hash_equals($baseline['resources']["$kind/$name"]['sha256'],hash('sha256',$r['value'])) : null;
            } else $resourceProblem=true;
            $resources[]=$item;
        }
        $memory=$this->io->read('memory',16384);$mem=[];
        foreach(['MemTotal','MemAvailable','MemFree','SwapTotal','SwapFree'] as $key) if(preg_match('/^'.$key.':\s+([0-9]+) kB$/m',$memory['value'],$m)) $mem[$key.'_kib']=$m[1];
        $opt=$this->io->path('config');$free=$opt ? @disk_free_space(dirname($opt)) : false;
        $ct=[];foreach(['conntrack','conntrack_max'] as $key) { $r=$this->io->read($key,64);$ct[$key]=AsusReportValues::decimal(trim($r['value']),'4294967295'); }
        $failures=[];
        $configRead=$this->io->read('config');$config=AsusReportValues::runtimeSettings($configRead['value']);
        if($configRead['state']==='missing')$failures[]='configuration_missing';
        elseif($configRead['state']!=='available')$failures[]='configuration_unreadable';
        elseif(in_array(null,$config,true))$failures[]='configuration_not_literal';
        if($abi===null)$failures[]='abi_unknown';
        if($engine['state']==='missing')$failures[]='engine_missing';
        elseif($engine['state']!=='available')$failures[]='engine_unreadable';
        elseif(($engine['executable']??true)!==true)$failures[]='engine_not_executable';
        foreach($runtimeComponents as $label=>$item) {
            if($item['state']!=='available' || (in_array($label,['init','shell','selected_shell'],true)&&$item['executable']!==true))$failures[]='runtime_unavailable';
            if(in_array($label,['shell','selected_shell'],true) && isset($item['elf_machine']) && $abi!==null && $item['elf_machine']!==($abi==='aarch64-3.10'?183:40))$failures[]='runtime_elf_mismatch';
        }
        if($abi!==null && $engine['state']==='available' && ($engine['elf_machine']??null)!==($abi==='aarch64-3.10'?183:40))$failures[]='engine_elf_mismatch';
        if($configRead['state']==='available') {
            if(!is_string($config['NFQUEUE_NUM']??null)||AsusReportValues::decimal($config['NFQUEUE_NUM'],'65535')===null)$failures[]='queue_number_invalid';
            if(!in_array($config['ASUS_CLIENT_MODE']??null,['all','include','exclude'],true))$failures[]='client_mode_invalid';
        }
        return [
            'platform'=>self::section($platform,$model!=='ASUS-unknown'&&$k!==null?'available':'partial','unsupported'),
            'package'=>self::section(['version'=>$version[1]??$bversion,'entware_abi'=>$abi,'runtime_components'=>$runtimeComponents,'php_version'=>PHP_MAJOR_VERSION.'.'.PHP_MINOR_VERSION.'.'.PHP_RELEASE_VERSION,'php_integer_bits'=>PHP_INT_SIZE*8,'opt_free_bytes'=>$free===false?null:sprintf('%.0f',$free),'memory'=>$mem,'conntrack'=>$ct],$abi!==null&&$bversion!==null?'available':'partial','missing'),
            'engine'=>self::section($engineData,$engine['state']==='available'?'available':'unavailable',$engine['state']==='available'?null:$engine['state']),
            'ark'=>self::section(['present'=>$present,'loaded'=>$loaded,'nvram_state'=>$this->nvramState,'component_state'=>$component['state'],'flags'=>$flags,'backup'=>$backupView],$loaded!=='unknown'&&$present!=='unknown'&&!$flagProblem?'available':'partial',$this->nvramState!=='available'?$this->nvramState:'unsupported'),
            'process'=>self::section(['running'=>$identity['running'],'uid'=>$identity['uid'],'state'=>$identity['process_state'],'age_seconds'=>null],$identity['running']!==null?'available':'unavailable','missing'),
            'resources'=>self::section(['items'=>$resources,'count'=>count($resources),'missing_references'=>$missing,'unresolved_reference_groups'=>$unresolved],$resourceProblem?'partial':'available',$total>128?'truncated':($missing?'missing':'unsupported')),
            'errors'=>self::section(['observed_prerequisite_failures'=>array_values(array_unique($failures)),'historical_startup_error'=>'unknown']),
        ];
    }
}
