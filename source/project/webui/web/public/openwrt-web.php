<?php
require_once __DIR__.'/platform.php';
/** Native read-only facts. No NVRAM emulation and no firmware configuration writes. */
final class NfqwsOpenWrtWeb
{
    private static function json(array $command):array
    {
        $r=NfqwsPlatform::run($command,3);if($r['status']!==0)return [];
        $v=json_decode(implode("\n",$r['output']),true);return is_array($v)?$v:[];
    }
    public static function board():array{return self::json(['/bin/ubus','call','system','board']);}
    public static function diagnostics():array{return self::json(NfqwsPlatform::serviceCommand('diagnostics','openwrt'));}
    public static function wan():array{return self::wanFromDump(self::json(['/bin/ubus','call','network.interface','dump']));}
    public static function wanFromDump(array $dump):array
    {
        $out=[];$seen=[];
        foreach(array_slice($dump['interface']??[],0,128)as $v){
            if(!is_array($v)||($v['up']??null)!==true||in_array($v['proto']??'', ['wireguard','openvpn','ipsec','xfrm','gre','gretap','vxlan'],true))continue;
            $dev=$v['l3_device']??'';if(!is_string($dev)||!preg_match('/^[A-Za-z0-9_.-]{1,32}$/D',$dev))continue;
            $default=false;foreach($v['route']??[]as $route)if(in_array($route['target']??null,['0.0.0.0','::'],true)&&(int)($route['mask']??-1)===0)$default=true;
            if(!$default)continue;
            foreach($v['ipv4-address']??[]as $row){$ip=$row['address']??'';
                if(!is_string($ip)||!preg_match('/^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/D',$ip)||max(array_map('intval',explode('.',$ip)))>255||isset($seen[$dev.'|'.$ip]))continue;
                $seen[$dev.'|'.$ip]=true;$out[]=['interface'=>$dev,'address'=>$ip];
            }
        }
        return ['schema_version'=>1,'state'=>$out?'available':'unavailable','addresses'=>array_slice($out,0,16)];
    }
    public static function version():string
    {
        $p='/usr/share/nfqws2/platform.json';$s=@lstat($p);
        if(!$s||is_link($p)||$s['uid']!==0||($s['mode']&0022)!==0||$s['size']>4096)return '';
        $v=json_decode((string)file_get_contents($p),true);$version=$v['version']??'';
        return is_string($version)&&preg_match('/^[0-9][0-9a-zA-Z.+_-]{1,63}$/D',$version)?$version:'';
    }
    public static function arkStatus():array
    {
        $d=self::diagnostics();$loaded=is_dir('/sys/module/ark');$q=$d['nfqueue']??['queue_number'=>null,'state'=>'unknown','sequence'=>null];
        return ['status'=>0,'model'=>self::board()['model']??'OpenWrt','flags'=>[],'ark_loaded'=>$loaded,'ready'=>!$loaded,
            'revision'=>hash('sha256',json_encode([$loaded,$d])),'backup'=>null,
            'diagnostics'=>['ark'=>['present'=>$loaded?'present':'absent','loaded'=>$loaded?'loaded':'unloaded'],
                'nfqueue'=>$q,'process_running'=>$d['process_running']??null]];
    }
    public static function checkup():array
    {
        $board=self::board();$d=self::diagnostics();$q=$d['nfqueue']??[];$running=($d['process_running']??false)===true;
        preg_match("/^DISTRIB_ARCH='([A-Za-z0-9_.-]{1,64})'$/m",(string)@file_get_contents('/etc/openwrt_release',false,null,0,4096),$arch);
        $bound=($q['state']??'')==='bound';$loaded=is_dir('/sys/module/ark');
        $item=static fn($id,$state,$facts,$action='none')=>['id'=>$id,'state'=>$state,'facts'=>$facts,'action_code'=>$action];
        $memory=(string)@file_get_contents('/proc/meminfo');$mem=[];
        foreach(['MemTotal','MemAvailable','MemFree','Buffers','Cached']as $key)if(preg_match('/^'.$key.':\s+([0-9]+) kB$/m',$memory,$m))$mem[$key]=(float)$m[1];
        $available=$mem['MemAvailable']??($mem['MemFree']??null);$rss=null;$pid=$d['pid']??null;
        if(is_int($pid)&&$pid>1&&preg_match('/^VmRSS:\s+([0-9]+) kB$/m',(string)@file_get_contents('/proc/'.$pid.'/status'),$m))$rss=(float)$m[1];
        $free=@disk_free_space('/etc/nfqws2');
        $items=[
            $item('platform','info',['platform'=>'openwrt','model'=>$board['model']??'OpenWrt','kernel'=>$board['kernel']??null,
                'firmware'=>$board['release']['version']??null,'target'=>$board['release']['target']??null,'package_arch'=>$arch[1]??null,'package_version'=>self::version()]),
            $item('storage_native','info',['path'=>'/etc/nfqws2','free_bytes'=>$free===false?null:sprintf('%.0f',$free),'readonly'=>!is_writable('/etc/nfqws2'),'write_tested'=>false]),
            $item('memory','info',['total_kib'=>$mem['MemTotal']??null,'available_kib'=>$available,'available_estimated'=>!isset($mem['MemAvailable']),'nfqws2_rss_kib'=>$rss]),
            $item('ark',$loaded?'attention':'ready',['present'=>$loaded,'loaded'=>$loaded]),
            $item('process',$running?'ready':'info',['running'=>$running,'rss_kib'=>$rss],'process_is_not_service_success'),
            $item('nfqueue',$bound?'ready':'info',['number'=>$q['queue_number']??null,'bound'=>$bound,'traffic_tested'=>false],'check_queue_and_full_service_response'),
        ];
        return ['schema_version'=>1,'checked_at'=>gmdate('Y-m-d\TH:i:s\Z'),'items'=>$items,
            'readiness'=>['nfqws2'=>['ready'=>$running&&$bound&&!$loaded,'codes'=>$bound?[]:['queue_not_bound']],
                'smartdns_install'=>['ready'=>false,'codes'=>['unsupported_runtime']], 'smartdns_connect'=>['ready'=>false,'codes'=>['unsupported_runtime']]],
            'limits'=>['read_only','write_access_estimated','dns_not_queried','service_success_not_tested']];
    }
}
