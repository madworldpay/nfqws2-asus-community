<?php
require_once __DIR__.'/install-plan.php';
require_once __DIR__.'/install-state.php';
require_once __DIR__.'/../webui/web/public/openwrt-apk-trust.php';
require_once __DIR__.'/../webui/web/public/openwrt-manual-context.php';

/** Signed bootstrap preparation. No native install/configure or service command. */
final class NfqwsOpenWrtInstallPrepare
{
    public function __construct(private string $work,private ?AsusUpdateSource $source=null,private ?string $key=null,private ?string $schema=null){}
    private function directory():void
    {
        AsusUpdateStore::noLinks($this->work);$s=@lstat($this->work);
        if(!$s){$parent=@lstat(dirname($this->work));if(!$parent||!is_dir(dirname($this->work))||$parent['uid']!==0||($parent['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
            $mask=umask(0077);try{if(!mkdir($this->work,0700))throw new RuntimeException('storage_unavailable');}finally{umask($mask);}$s=lstat($this->work);}
        if(!is_dir($this->work)||$s['uid']!==0||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
    }
    private function schema():string
    {
        if($this->schema!==null)return $this->schema;
        if(!defined('NFQWS_NATIVE_INSTALL_SCHEMA'))throw new RuntimeException('invalid_state');
        $path=$this->work.'/native-schema.json';AsusUpdateStore::noLinks($path);$s=@lstat($path);
        if($s){if(!is_file($path)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>16384||file_get_contents($path)!==NFQWS_NATIVE_INSTALL_SCHEMA)throw new RuntimeException('invalid_state');return $path;}
        $mask=umask(0077);try{$f=fopen($path,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(fwrite($f,NFQWS_NATIVE_INSTALL_SCHEMA)!==strlen(NFQWS_NATIVE_INSTALL_SCHEMA)||!fflush($f))throw new RuntimeException('insufficient_space');}finally{fclose($f);}return $path;
    }
    public function run():array
    {
        if(!NfqwsPlatform::native())throw new RuntimeException('unsupported_abi');$this->directory();
        $store=new AsusUpdateStore('/tmp/nfqws2-native-state/updates');$lease=$store->lease('apply.lock',true);
        try{
            $store->reconcile(AsusUpdateStore::boot(),AsusUpdateStore::uptime());
            if($store->status()['active']!==null||NfqwsOpenWrtManualContext::activeManager()!==null)throw new RuntimeException('busy');
            $firmware=NfqwsOpenWrtUpdateEnvironment::firmware((string)file_get_contents('/etc/openwrt_release'));$own=NfqwsOpenWrtInstallState::read($firmware);
            $key=$this->key??(defined('NFQWS_NATIVE_INSTALL_KEY')?NFQWS_NATIVE_INSTALL_KEY:throw new RuntimeException('signature_unavailable'));
            $source=$this->source??new AsusGithubUpdateSource(0,'/etc/ssl/certs/ca-certificates.crt',['metadata'=>15,'download'=>180],'openwrt');
            $raw=$source->manifest();$plan=NfqwsOpenWrtInstallPlan::select($raw['json'],$raw['signature'],$key,(string)file_get_contents('/etc/openwrt_release'),$own,$this->schema());
            if(in_array($plan['action'],['current','repair_required'],true))return $plan+['archive'=>null,'record'=>null,'keys'=>null,'missing'=>[]];
            $package=$plan['candidate']['package'];NfqwsOpenWrtUpdatePackage::space(disk_free_space(is_dir('/overlay')?'/overlay':'/'),disk_free_space($this->work),$package,0,1048576);
            $archive=$this->work.'/'.$package['filename'];$source->download($package,$archive);$keys=null;
            if($firmware['format']==='apk'){$keys=$this->work.'/keys';NfqwsOpenWrtApkTrust::stage($keys,$key);}
            $record=NfqwsOpenWrtUpdatePackage::inspect($archive,$plan['candidate'],$firmware,$keys);
            return $plan+['archive'=>$archive,'record'=>$record,'keys'=>$keys,'missing'=>NfqwsOpenWrtUpdateManager::missing($firmware,$record['depends'],true)];
        }finally{flock($lease,LOCK_UN);fclose($lease);}
    }
}
