<?php
require_once __DIR__.'/resource-paths.php';
/** A bounded website-only addition. Raw import documents are never rewritten. */
final class AsusImportTorrentSites
{
    public const SITES=['nnmclub.to','rutracker.org','rutor.info','tapochek.net'];
    private const MARKER='nfqws2-community-torrent-sites-v1';
    private const TLS_SHA='936c2bee4cfb80aa3c426b2dcbcc834b3fbcd1adb17172959dc569c73a14275c';
    private const BASE=['--fastpath-workaround','--lua-init','--blob','--debug','--bind-fix4','--bind-fix6','--ipcache-lifetime','--ipcache-hostname'];
    private const PROGRAM=['--new','--comment','--filter-tcp','--filter-udp','--filter-l3','--filter-l7','--payload','--lua-desync','--out-range','--in-range',
        '--hostlist','--hostlist-exclude','--hostlist-auto','--hostlist-domains','--hostlist-exclude-domains',
        '--hostlist-auto-fail-threshold','--hostlist-auto-fail-time','--hostlist-auto-retrans-threshold','--hostlist-auto-debug',
        '--ipset','--ipset-exclude','--ipset-ip','--ipset-exclude-ip'];
    private const FUNCTIONS=['fake','multidisorder','multisplit','hostfakesplit','fakedsplit','fakeddisorder','syndata',
        'http_methodeol','http_hostcase','http_domcase','circular','condition','stopif','drop','pass','send','udplen'];

    public static function requested(array $selection): ?array
    {
        $v=array_key_exists('torrent_sites',$selection)?$selection['torrent_sites']:false;if($v===false)return null;
        if(!is_array($v)||array_is_list($v))throw new RuntimeException('invalid_import_selection');
        $keys=array_keys($v);sort($keys);
        if($keys!==['catalog_id','sha256']||!is_string($v['catalog_id'])||!preg_match('/^[a-z0-9][a-z0-9-]{0,63}$/D',$v['catalog_id'])||
            !is_string($v['sha256'])||!preg_match('/^[a-f0-9]{64}$/D',$v['sha256']))throw new RuntimeException('invalid_import_selection');
        return $v;
    }
    public static function rule(): string
    {
        return '--comment='.self::MARKER.' --filter-tcp=443 --hostlist-domains='.implode(',',self::SITES).
            ' --payload=tls_client_hello --lua-desync=fake:blob=tls_clienthello:tls_mod=rnd,dupsid,sni=www.google.com:repeats=6:tcp_md5'.
            ' --lua-desync=multidisorder:pos=1,midsld';
    }
    private static function incompatible(): never {throw new RuntimeException('torrent_sites_incompatible');}
    private static function pairs(string $text,array $allowed): array
    {
        if(strlen($text)>65536||preg_match('/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\'"`$\\\\]/',$text))self::incompatible();
        $text=preg_replace('/(?:^|\n)\h*#[^\n]*/','',$text);
        $words=preg_split('/\s+/',trim($text),-1,PREG_SPLIT_NO_EMPTY);if(count($words)>8192)self::incompatible();$out=[];
        for($i=0;$i<count($words);$i++){
            $parts=explode('=',$words[$i],2);$key=$parts[0];if(!in_array($key,$allowed,true))self::incompatible();
            if($key==='--new'){if(count($parts)!==1)self::incompatible();$value='';}
            elseif(in_array($key,['--bind-fix4','--bind-fix6'],true))$value=$parts[1]??'';
            else{$value=$parts[1]??($words[++$i]??'');if($value===''||str_starts_with($value,'--'))self::incompatible();}
            if($key==='--lua-desync'&&!in_array(explode(':',$value,2)[0],self::FUNCTIONS,true))self::incompatible();
            $out[]=[$key,$value];
        }
        return $out;
    }
    private static function covers443(string $ports): bool
    {
        $covers=false;
        foreach(explode(',',$ports)as $part){if(!preg_match('/^([1-9][0-9]{0,4})(?:[:-]([1-9][0-9]{0,4}))?$/D',$part,$m))self::incompatible();
            $a=(int)$m[1];$z=(int)($m[2]??$m[1]);if($a>$z||$z>65535)self::incompatible();if($a<=443&&443<=$z)$covers=true;}
        return $covers;
    }
    private static function desync(string $value,array $loaded): void
    {
        $parts=explode(':',$value);$function=array_shift($parts);
        $module=$function==='pass'?'zapret-lib.lua':(in_array($function,['circular','condition','stopif'],true)?'zapret-auto.lua':'zapret-antidpi.lua');
        if(!isset($loaded['lua/'.$module]))self::incompatible();$iff=null;
        foreach($parts as $part){$pair=explode('=',$part,2);$key=$pair[0];
            // These callbacks can execute Lua that static resource inspection cannot prove.
            if(in_array($key,['hostkey','failure_detector','success_detector','cond','cond_code'],true))self::incompatible();
            if($key==='iff'){
                if($iff!==null||($pair[1]??null)!=='nfqws_local_offers_tls13'||!isset($loaded['lua/local-tls13-stun.lua'],$loaded['lua/zapret-auto.lua']))self::incompatible();
                $iff=$pair[1];
            }
        }
        if(in_array($function,['condition','stopif'],true)&&$iff===null)self::incompatible();
    }
    public static function add(array $changes,array $current,array $inventory,array $virtual,array $files,array $option,?array $scope): array
    {
        if($scope===null||($scope['category']??null)!=='global'||($scope['id']??null)!==$option['catalog_id']||
            ($scope['sha256']??null)!==$option['sha256'])throw new RuntimeException('invalid_torrent_sites_source');
        if(($inventory['scan_truncated']??false)===true)self::incompatible();
        $effective=array_replace($current,$changes);
        if(!self::covers443($effective['TCP_PORTS']??''))self::incompatible();
        $stock=[];$available=[];
        foreach($inventory['files']??[]as $row)if(($row['state']??null)==='available'&&($row['bundled_lua']??false)===true&&
            ($row['bundled_name']??$row['name'])===$row['name'])$stock[$row['kind'].'/'.$row['name']]=$row['sha256'];
        foreach($virtual as $row)if(($row['state']??null)==='available')$available[$row['kind'].'/'.$row['name']]=$row;
        foreach($files as $file)if($file['kind']==='lua'&&!$file['reuse'])self::incompatible();
        $loaded=[];$tls=false;
        foreach(self::pairs($effective['NFQWS_BASE_ARGS']??'',self::BASE)as [$key,$value]){
            if($key==='--lua-init'){
                if(!str_starts_with($value,'@'))self::incompatible();$path=NfqwsResourcePaths::canonical(substr($value,1));
                if($path===null||!str_starts_with($path,'/opt/etc/nfqws2/lua/'))self::incompatible();$name='lua/'.basename($path);
                if(!isset($stock[$name],$available[$name])||$available[$name]['sha256']!==$stock[$name])self::incompatible();$loaded[$name]=true;
            }
            if($key==='--blob'&&str_starts_with($value,'tls_clienthello:')){
                if($tls||!str_starts_with($value,'tls_clienthello:@'))self::incompatible();
                $path=NfqwsResourcePaths::canonical(substr($value,strlen('tls_clienthello:@')));
                $row=$available['blobs/tls_clienthello.bin']??null;
                if($path!=='/opt/etc/nfqws2/blobs/tls_clienthello.bin'||!is_array($row)||$row['sha256']!==self::TLS_SHA||($row['byte_length']??null)!==681)self::incompatible();$tls=true;
            }
        }
        if(!$tls||!isset($loaded['lua/zapret-lib.lua'],$loaded['lua/zapret-antidpi.lua']))self::incompatible();
        $tcp=false;
        foreach(['NFQWS_ARGS_CUSTOM','NFQWS_ARGS_UDP','NFQWS_ARGS_QUIC','NFQWS_ARGS','NFQWS_EXTRA_ARGS','NFQWS_ARGS_IPSET']as $key)
            foreach(self::pairs($effective[$key]??'',self::PROGRAM)as [$optionName,$value]){
                if($optionName==='--filter-tcp'&&self::covers443($value))$tcp=true;
                if($optionName==='--lua-desync')self::desync($value,$loaded);
            }
        if(!$tcp)self::incompatible();
        $custom=$effective['NFQWS_ARGS_CUSTOM']??'';$rule=self::rule();
        while($custom===$rule||str_starts_with($custom,$rule.' --new '))$custom=$custom===$rule?'':substr($custom,strlen($rule.' --new '));
        if(str_contains($custom,self::MARKER))self::incompatible();
        $changes['NFQWS_ARGS_CUSTOM']=$rule.(trim($custom)===''?'':' --new '.$custom);
        return ['changes'=>$changes,'preview'=>['sites'=>self::SITES,'block'=>$rule,'key'=>'NFQWS_ARGS_CUSTOM']];
    }
}
