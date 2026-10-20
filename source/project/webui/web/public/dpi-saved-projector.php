<?php
require_once __DIR__.'/dpi-analysis.php';
/** Reads measured badges/counters only. It never exports arbitrary text cells. */
final class AsusDpiSavedProjector
{
    private const BADGES=['OK'=>'ok','REDIR'=>'redir','BLOCKED'=>'blocked','ISP PAGE'=>'isp_page','LOCAL IP'=>'local_ip',
        'TIMEOUT'=>'timeout','SEND TIMEOUT'=>'send_timeout','POOL TIMEOUT'=>'pool_timeout','DETECTED'=>'detected',
        'TCP RST'=>'tcp_rst','TCP ABORT'=>'tcp_abort','TLS RST'=>'tls_rst','TLS ABORT'=>'tls_abort','TLS DROP'=>'tls_dropped',
        'TLS ALERT'=>'tls_alert','16KB DROP'=>'tcp16_20','TLS BLOCK'=>'tls_block','TLS ERR'=>'tls_err','NO CA BUNDLE'=>'no_ca_bundle',
        'TLS SPOOF'=>'tls_spoof','TLS EOF'=>'tls_eof','NO TLS1.3'=>'no_tls13','SYN DROP'=>'syn_dropped','REFUSED'=>'refused',
        'NET UNREACH'=>'net_unreach','HOST UNREACH'=>'host_unreach','OS ERR'=>'os_err','DNS FAIL'=>'dns_fail','DNS FAKE'=>'dns_fake',
        'NXDOMAIN'=>'nxdomain','CLOSED'=>'quic_closed','VN'=>'quic_vn','SPOOF'=>'quic_spoof','DROP'=>'quic_drop',
        '—'=>'quic_unsupported','-'=>'quic_unsupported','ERR'=>'err','UNKNOWN'=>'unknown','STALL'=>'stalled','SLOW'=>'slow','ERROR'=>'error'];
    private static function cells(string $line): array
    {
        if(!str_contains($line,'│')&&!str_contains($line,'|'))return [];
        $parts=preg_split('/[│|]/u',$line);array_shift($parts);array_pop($parts);return array_map('trim',$parts);
    }
    private static function metric(array &$groups,int $group,string $name,int|float $value): void
    {
        $groups[$group]??=['group'=>$group,'metrics'=>[],'rows'=>[]];$groups[$group]['metrics'][$name]=$value;
    }
    private static function row(array &$groups,int $group,array $row): void
    {
        $groups[$group]??=['group'=>$group,'metrics'=>[],'rows'=>[]];
        if(count($groups[$group]['rows'])>=512)throw new RuntimeException('output_limit');
        $groups[$group]['rows'][]=$row;
    }
    public static function project(string $raw,string $sourceSha256): array
    {
        if($raw===''||strlen($raw)>1048576||preg_match('//u',$raw)!==1||!preg_match('/^[a-f0-9]{64}$/D',$sourceSha256)||!hash_equals(hash('sha256',$raw),$sourceSha256))throw new RuntimeException('unsupported_report');
        $meta=AsusDpiOptions::metadata();$known=[];
        foreach(explode("\n",$meta['files']['domains.txt']) as $d){$d=trim($d);if($d!==''&&!str_starts_with($d,'#'))$known[]=explode('/',preg_replace('~^https?://~','',$d))[0];}
        $tcp=array_column(json_decode($meta['files']['tcp16.json'],true,32,JSON_THROW_ON_ERROR),'id');
        $dcs=array_column($meta['config']['TELEGRAM_DCS'],1);
        $language=preg_match('/Информация о сети|Результаты проверки доменов|DNS доступность|Проверка TCP|Скачивание/u',$raw)?'ru':'en';
        $clean=preg_replace('/\x1b\[[0-?]*[ -\/]*[@-~]/','',$raw);
        $groups=[];$omitted=0;$section=null;$burstColumns=0;
        foreach(explode("\n",str_replace("\r",'',$clean)) as $line) {
            $line=trim($line);if($line===''||preg_match('/^[\s┌┐└┘├┤┬┴┼─═╔╗╚╝╠╣╦╩╬+\-=]+$/u',$line))continue;
            $handled=false;
            if(str_contains($line,'TLS / SNI Domain Inspection Results:')||str_contains($line,'Результаты проверки доменов (TLS / SNI):')){$section=2;continue;}
            if(str_contains($line,'TCP 16–20 KB Block Check')||str_contains($line,'Проверка TCP 16-20KB блокировки')){$section=3;continue;}
            if(str_contains($line,'Telegram Availability Check')||str_contains($line,'Проверка доступности Telegram')){$section=5;continue;}
            if(preg_match('/IPv([46]):.*?TTLB:?\s*([0-9]{1,9})\s*(?:ms|мс)/u',$line,$m)){self::metric($groups,0,'ipv'.$m[1].'_latency_ms',(int)$m[2]);$handled=true;}
            if(str_contains($line,'DNS availability')||str_contains($line,'DNS доступность')) {
                foreach(['DoH'=>'doh','DoT'=>'dot','UDP'=>'udp'] as $label=>$key)if(preg_match('/(?<![0-9])([0-9]{1,6})\/([0-9]{1,6})\s+'.$label.'\b/u',$line,$m)&&$m[1]<=$m[2]){
                    self::metric($groups,1,$key.'_ok',(int)$m[1]);self::metric($groups,1,$key.'_total',(int)$m[2]);$handled=true;
                }
            }
            if(preg_match('/(?:Found white SNI: in|Найдено белых SNI: у)\s+([0-9]{1,6})\s+(?:of|из)\s+([0-9]{1,6})/u',$line,$m)&&$m[1]<=$m[2]) {
                self::metric($groups,4,'found_as',(int)$m[1]);self::metric($groups,4,'detected_as',(int)$m[2]);$handled=true;
            }elseif(preg_match('/(?:No white SNI found for any of|Белые SNI не найдены ни для одной из)\s+([0-9]{1,6})/u',$line,$m)) {
                self::metric($groups,4,'found_as',0);self::metric($groups,4,'detected_as',(int)$m[1]);$handled=true;
            }elseif(str_contains($line,'No AS is blocked')||str_contains($line,'Ни одна AS не заблокирована')){self::metric($groups,4,'found_as',0);self::metric($groups,4,'detected_as',0);$handled=true;}
            $cells=self::cells($line);
            if(($cells[0]??null)==='Fingerprint'){$section=6;$burstColumns=max(0,count($cells)-2);continue;}
            if($section===2&&count($cells)>=5&&in_array($cells[0],$known,true)) {
                $values=[];
                foreach(['http','tls12','tls13','quic'] as $i=>$key){$badge=self::BADGES[$cells[$i+1]]??null;if($badge===null){$values=[];break;}$values[$key]=['status'=>$key==='quic'&&$badge==='ok'?'quic_ok':$badge,'detail'=>['code'=>'unclassified']];}
                if($values!==[]){self::row($groups,2,['target'=>'domain-'.(array_search($cells[0],$known,true)+1),'metrics'=>(object)[],'values'=>$values]);$handled=true;}
            }
            if($section===3&&count($cells)>=4&&in_array($cells[0],$tcp,true)&&isset(self::BADGES[$cells[3]])){
                self::row($groups,3,['target'=>'tcp-'.(array_search($cells[0],$tcp,true)+1),'metrics'=>(object)[],'status'=>self::BADGES[$cells[3]],'detail'=>['code'=>'unclassified']]);$handled=true;
            }
            if($section===5&&count($cells)>=5&&in_array($cells[0],$dcs,true)&&in_array($cells[3],['OK','unavailable','недоступен'],true)) {
                self::metric($groups,5,'dc_total',($groups[5]['metrics']['dc_total']??0)+1);
                self::metric($groups,5,'dc_reachable',($groups[5]['metrics']['dc_reachable']??0)+($cells[3]==='OK'?1:0));$handled=true;
            }
            if($section===5&&preg_match('/^(Download|Upload|Скачивание|Загрузка)[ \t]*:\s*(OK|STALL|SLOW|BLOCKED|ERROR)\b/u',$line,$m)) {
                $download=in_array($m[1],['Download','Скачивание'],true);$metrics=[];
                if(preg_match('~/\s*([0-9]{1,6})s\)~',$line,$seconds))$metrics['duration_ms']=(int)$seconds[1]*1000;
                self::row($groups,5,['target'=>$download?'transfer-1':'transfer-2','direction'=>$download?'download':'upload','status'=>self::BADGES[$m[2]],'metrics'=>(object)$metrics]);$handled=true;
            }
            if($section===6&&$burstColumns>0&&count($cells)>$burstColumns){
                $fp=strtolower(preg_replace('/[^a-zA-Z0-9]/','',$cells[0]));
                if(in_array($fp,$meta['fingerprints'],true))foreach(array_slice($cells,1,$burstColumns) as $i=>$cell){
                    if(preg_match('/^([0-9]{1,4})\/([0-9]{1,4})$/D',$cell,$m)&&$m[1]<=$m[2]){self::row($groups,6,['target'=>'burst-'.($i+1),'profile'=>$fp,'metrics'=>['answered'=>(int)$m[1],'attempts'=>(int)$m[2]]]);$handled=true;}
                }
            }
            if(!$handled)$omitted++;
        }
        if($groups===[])throw new RuntimeException('unsupported_report');ksort($groups);
        foreach($groups as &$group)$group['metrics']=(object)$group['metrics'];unset($group);
        $out=['type'=>'nfqws2_dpi_saved','schema_version'=>1,'detector_version'=>$meta['version'],'format'=>'upstream_txt','language'=>$language,'source_sha256'=>$sourceSha256,
            'groups'=>array_values($groups),'coverage'=>['partial'=>true,'recognized_groups'=>array_keys($groups),'omitted_lines'=>$omitted]];
        $json=json_encode($out,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
        if(strlen($json)>262144)throw new RuntimeException('output_limit');AsusSupportSchema::validate($json,'dpi_saved');return $out;
    }
}
