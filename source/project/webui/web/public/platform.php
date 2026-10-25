<?php
/** Trusted package profile. HTTP fields and process environment cannot select it. */
final class NfqwsPlatform
{
    private const PROFILES=[
        'asus-entware'=>['root'=>'/opt','config'=>'/opt/etc/nfqws2','web_config'=>'/opt/etc/nfqws-asus-web',
            'library'=>'/opt/lib/nfqws2-asus','share'=>'/opt/share/nfqws2-asus','service'=>'/opt/etc/init.d/S51nfqws2'],
        'openwrt'=>['root'=>'','config'=>'/etc/nfqws2','web_config'=>'/etc/nfqws2-web',
            'library'=>'/usr/lib/nfqws2','share'=>'/usr/share/nfqws2','service'=>'/etc/init.d/nfqws2-native'],
    ];
    public static function settings(?string $profile=null):array
    {
        $profile??=self::current();
        if(!isset(self::PROFILES[$profile]))throw new RuntimeException('invalid_platform_profile');
        return self::PROFILES[$profile];
    }
    public static function current():string
    {
        static $profile=null;
        if($profile===null){
            $file=__DIR__.'/platform-profile.json';clearstatcache(true,$file);
            $profile=@lstat($file)===false?'asus-entware':self::readProfile($file);
        }
        return $profile;
    }
    public static function native():bool{return self::current()==='openwrt';}
    public static function readProfile(string $file,int $owner=0):string
    {
        clearstatcache(true,$file);$s=@lstat($file);
        if(!$s||is_link($file)||!is_file($file)||$s['uid']!==$owner||($s['mode']&0022)!==0||$s['size']>4096||$s['nlink']!==1)
            throw new RuntimeException('unsafe_platform_profile');
        for($p=dirname($file);$p!=='/';$p=dirname($p)){
            $d=@lstat($p);
            if(!$d||is_link($p)||!is_dir($p)||!in_array($d['uid'],[0,$owner],true))throw new RuntimeException('unsafe_platform_profile');
            // Root-owned sticky /tmp is a valid ancestor of a private fixture.
            if(($d['mode']&0022)!==0&&!(($d['mode']&01000)!==0&&$d['uid']===0))throw new RuntimeException('unsafe_platform_profile');
        }
        $v=json_decode((string)file_get_contents($file),true);
        if(!is_array($v)||array_keys($v)!==['schema_version','platform']||$v['schema_version']!==1||
            !is_string($v['platform'])||!isset(self::PROFILES[$v['platform']]))throw new RuntimeException('invalid_platform_profile');
        return $v['platform'];
    }
    public static function translate(string $path,?string $profile=null):string
    {
        if(str_contains($path,"\0")||preg_match('~(?:^|/)\.\.?(?:/|$)~',$path))throw new RuntimeException('invalid_platform_path');
        $settings=self::settings($profile);
        if($settings['root']==='/opt')return $path;
        $map=[
            '/opt/etc/nfqws2'=>'/etc/nfqws2','/opt/etc/nfqws-asus-web'=>'/etc/nfqws2-web',
            '/opt/share/nfqws2-asus'=>'/usr/share/nfqws2','/opt/lib/nfqws2-asus'=>'/usr/lib/nfqws2',
            '/opt/share/nfqws-asus-web'=>'/usr/share/nfqws2-web','/opt/lib/nfqws-asus-web'=>'/usr/lib/nfqws2-web',
            '/opt/var/lib/nfqws2-asus'=>'/tmp/nfqws2-native-state','/opt/var/log'=>'/var/log',
            '/opt/etc/ssl/certs/ca-certificates.crt'=>'/etc/ssl/certs/ca-certificates.crt',
            '/opt/bin/php-cgi'=>'/usr/bin/php-cgi','/opt/usr/bin/nfqws2'=>'/usr/bin/nfqws2',
        ];
        foreach($map as $from=>$to)if($path===$from||str_starts_with($path,$from.'/'))return $to.substr($path,strlen($from));
        if($path==='/opt'||str_starts_with($path,'/opt/'))throw new RuntimeException('unmapped_platform_path');
        return $path;
    }
    public static function serviceCommand(string $action,?string $profile=null):array
    {
        if(!in_array($action,['start','stop','restart','status','check','diagnostics'],true))throw new RuntimeException('invalid_service_action');
        $settings=self::settings($profile);
        if($settings['root']===''&&in_array($action,['status','check','diagnostics'],true))return ['/usr/lib/nfqws2/control.sh',$action];
        return [$settings['service'],$action];
    }
    public static function reader(int $owner=0,bool $mutable=false):AsusShareRead
    {
        return self::native()?new AsusShareRead($owner,null,null,$mutable):new AsusShareRead($owner,realpath('/opt'),'/opt',$mutable);
    }
    /** Fixed argv selected by trusted callers, bounded output and deadline. */
    public static function run(array $argv,float $timeout=15):array
    {
        $pipes=[];$p=@proc_open($argv,[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes,null,['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin']);
        if(!is_resource($p))return ['status'=>1,'output'=>[]];
        foreach($pipes as $f)stream_set_blocking($f,false);
        $raw='';$until=microtime(true)+$timeout;$status=1;
        try{do{foreach($pipes as $f)$raw.=stream_get_contents($f);$s=proc_get_status($p);
            if(strlen($raw)>65536||microtime(true)>$until){proc_terminate($p,9);break;}
            if(!$s['running']){$status=$s['exitcode'];foreach($pipes as $f)$raw.=stream_get_contents($f);break;}usleep(20000);
        }while(true);}finally{foreach($pipes as $f)fclose($f);proc_close($p);}
        return ['status'=>$status,'output'=>explode("\n",rtrim(substr($raw,0,65536)))];
    }
    public static function guardFile(string $directory,string $name,int $owner=0):string
    {
        if(!preg_match('/^[A-Za-z0-9_.-]{1,128}$/D',$name)||in_array($name,['.','..'],true))throw new RuntimeException('unsafe_panel_file');
        for($p=$directory;$p!=='/'&&$p!=='.';$p=dirname($p)){
            $a=@lstat($p);
            if(!$a||!in_array($a['uid'],[0,$owner],true))throw new RuntimeException('unsafe_panel_file');
            if(is_link($p)&&!($p==='/var'&&$a['uid']===0&&realpath($p)==='/tmp'))throw new RuntimeException('unsafe_panel_file');
            if(!is_link($p)&&($a['mode']&0022)!==0&&!($a['uid']===0&&($a['mode']&01000)!==0))throw new RuntimeException('unsafe_panel_file');
        }
        $base=realpath($directory);$d=$base!==false?@lstat($base):false;
        if(!$d||!is_dir($base)||$d['uid']!==$owner||($d['mode']&0022)!==0)throw new RuntimeException('unsafe_panel_file');
        $path=$base.'/'.$name;clearstatcache(true,$path);$s=@lstat($path);
        if($s!==false&&(is_link($path)||!is_file($path)||$s['nlink']!==1||!in_array($s['uid'],[$owner,65534],true)||($s['mode']&0002)!==0))
            throw new RuntimeException('unsafe_panel_file');
        return $path;
    }
}
