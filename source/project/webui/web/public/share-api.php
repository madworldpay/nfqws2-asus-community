<?php
require_once __DIR__.'/share-bundle.php';
require_once __DIR__.'/share-source.php';
require_once __DIR__.'/share-strategy.php';
require_once __DIR__.'/share-contributions.php';
require_once __DIR__.'/dpi-saved-store.php';
require_once __DIR__.'/dpi-saved-projector.php';
require_once __DIR__.'/dpi-jobs.php';
require_once __DIR__.'/support-mail.php';
require_once __DIR__.'/support-mail-proof.php';
require_once __DIR__.'/support-channel-setup.php';
/** Fixed commands and saved config path; a draft is data, never a shell command. */
final class AsusShareApi
{
    private const FIELDS=['sharestates'=>[],'sharesavedrefresh'=>[],'sharesavedread'=>['id'],'sharesaveddelete'=>['id'],
        'sharestrategydraft'=>[],'shareinventory'=>[],'sharednssources'=>[],'shareresourceread'=>['id','source_sha256'],'shareanalyze'=>['selection'],'shareprepare'=>['selection'],'sharesend'=>['envelope','proof','consent','submission_id'],'sharelocation'=>[],'sharechannelconnect'=>[]];
    public function __construct(private ?AsusDpiSavedStore $saved=null,private ?AsusDpiStore $legacy=null,private ?AsusSupportMail $mail=null,
        private string $configPath='/opt/etc/nfqws2/nfqws2.conf',private ?array $versions=null,private ?AsusShareSource $source=null,private ?AsusShareResources $resourceStore=null,private ?AsusShareDns $dnsStore=null)
    {$this->configPath=NfqwsPlatform::translate($this->configPath);}
    public static function validate(array $post): void
    {
        $cmd=$post['cmd']??null;if(!is_string($cmd)||!array_key_exists($cmd,self::FIELDS))throw new RuntimeException('invalid_request');
        $keys=array_keys($post);sort($keys);$expected=array_merge(['cmd','csrf_token'],self::FIELDS[$cmd]);sort($expected);
        if($keys!==$expected)throw new RuntimeException('invalid_request');
        foreach($post as $key=>$v)if(!is_string($v)||strlen($v)>(in_array($key,['selection','envelope'],true)?4194304:256))throw new RuntimeException('invalid_request');
        if(isset($post['id'])&&!preg_match('/^[a-f0-9]{32}$/D',$post['id']))throw new RuntimeException('invalid_request');
        if(isset($post['source_sha256'])&&!preg_match('/^[a-f0-9]{64}$/D',$post['source_sha256']))throw new RuntimeException('invalid_request');
        if($cmd==='sharesend'&&($post['consent']!=='send'||!preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/D',$post['submission_id'])))throw new RuntimeException('invalid_request');
    }
    private function resources(): AsusShareResources {return $this->resourceStore??=new AsusShareResources();}
    private function dns(): AsusShareDns {return $this->dnsStore??=new AsusShareDns();}
    private function saved(): AsusDpiSavedStore {return $this->saved??=new AsusDpiSavedStore();}
    private function legacy(): AsusDpiStore {return $this->legacy??=new AsusDpiStore();}
    private function mail(): AsusSupportMail {return $this->mail??=new AsusSupportMail();}
    private function config(): string
    {
        if(NfqwsPlatform::native())NfqwsPlatform::guardFile(dirname($this->configPath),basename($this->configPath));
        $raw=@file_get_contents($this->configPath,false,null,0,262145);
        if(!is_string($raw)||strlen($raw)>262144)throw new RuntimeException('strategy_unavailable');return $raw;
    }
    private function versions(): array
    {
        if($this->versions!==null)return $this->versions;
        $path=NfqwsPlatform::sharedFile('report-baseline.json',__DIR__.'/missing-baseline.json');
        $raw=@file_get_contents($path,false,null,0,131073);$v=is_string($raw)&&strlen($raw)<=131072?json_decode($raw,true):null;
        $out=[];foreach(['package_version'=>'core','web_version'=>'web'] as $key=>$name)$out[$name]=is_array($v)&&is_string($v[$key]??null)&&preg_match('/^[A-Za-z0-9.+_-]{1,64}$/D',$v[$key])?$v[$key]:'unknown';
        return $out;
    }
    private static function keys(array $value,array $allowed,array $required=[]): void
    {if(array_diff(array_keys($value),$allowed)||array_diff($required,array_keys($value)))throw new RuntimeException('invalid_request');}
    public function handle(array $post,string $sessionKey,int $now): array
    {
        self::validate($post);
        switch($post['cmd']) {
            case 'shareinventory':return $this->resources()->inventory();
            case 'sharednssources':return $this->dns()->sources();
            case 'shareresourceread':return $this->resources()->read($post['id'],$post['source_sha256']);
            case 'shareanalyze':
                $a=AsusSupportSchema::decode($post['selection'],4194304,'invalid_request');if(!is_object($a))throw new RuntimeException('invalid_request');
                $a=AsusSupportSchema::toArray($a);
                return (new AsusShareContributions($this->resources(),$this->dns()))->analyze($a,isset($a['strategy'])?$this->config():'');
            case 'sharesend':
                $envelope=AsusShareBundle::envelope($post['envelope'],$post['submission_id']);
                if(!AsusShareBundle::verify($post['proof'],$envelope['files'],$sessionKey,$now,$envelope['source']??null))throw new RuntimeException('invalid_proof');
                return $this->mail()->sendShare($post['envelope'],$post['submission_id']);
            case 'sharelocation':return $this->mail()->location();
            case 'sharechannelconnect':return (new AsusSupportChannelSetup())->connect();
            case 'sharestates':
                return ['mail'=>$this->mail()->shareAvailability()+['public_setup_available'=>(new AsusSupportChannelSetup())->available()],'dpi'=>(new AsusDpiJobs())->status(),'saved'=>$this->saved()->list()];
            case 'sharesavedrefresh':return $this->saved()->refresh();
            case 'sharesavedread':return $this->saved()->read($post['id']);
            case 'sharesaveddelete':$this->saved()->delete($post['id']);return ['deleted'=>true];
            case 'sharestrategydraft':
                $config=$this->config();$draft=AsusShareStrategy::discover($config);$draft['config']=$config;return $draft;
            case 'shareprepare':
                $v=AsusSupportSchema::decode($post['selection'],4194304,'invalid_request');
                if(!is_object($v))throw new RuntimeException('invalid_request');$v=AsusSupportSchema::toArray($v);
                $version=$v['version']??3;if(!in_array($version,[3,4],true))throw new RuntimeException('invalid_request');
                if($version===3){self::keys($v,['report','dpi','strategy','link_installation']);if(strlen($post['selection'])>2097152)throw new RuntimeException('invalid_request');}
                else self::keys($v,['version','report','dpi','strategy','resources','dns','context','analysis_config_sha256','link_installation'],['version']);$files=[];
                if(isset($v['link_installation'])&&!is_bool($v['link_installation']))throw new RuntimeException('invalid_request');
                if(isset($v['report'])) {
                    $r=$v['report'];if(!is_array($r))throw new RuntimeException('invalid_request');self::keys($r,['raw','filename','proof'],['raw','filename','proof']);
                    foreach($r as $s)if(!is_string($s))throw new RuntimeException('invalid_request');
                    if(!AsusReportProof::verify($r['proof'],$r['raw'],$r['filename'],$sessionKey,$now))throw new RuntimeException('invalid_proof');
                    $files[]=AsusShareBundle::file('report',$r['filename'],$r['raw']);
                }
                if(isset($v['dpi'])) {
                    $d=$v['dpi'];if(!is_array($d))throw new RuntimeException('invalid_request');self::keys($d,['kind','id'],['kind','id']);
                    if(!is_string($d['id'])||!preg_match('/^[a-f0-9]{32}$/D',$d['id']))throw new RuntimeException('invalid_request');
                    if($d['kind']==='saved'){$src=$this->saved()->read($d['id']);$raw=json_encode(AsusDpiSavedProjector::project($src['raw'],$src['sha256']),JSON_UNESCAPED_UNICODE|JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR)."\n";}
                    elseif($d['kind']==='legacy')$raw=$this->legacy()->readResult($d['id']);
                    else throw new RuntimeException('invalid_request');
                    $stamp=gmdate('Y-m-d_H-i-s',$now);
                    if($d['kind']==='legacy'){$legacy=AsusSupportSchema::decode($raw,262144,'invalid_dpi');if(!is_object($legacy)||!is_string($legacy->started_at??null)||!preg_match('/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/D',$legacy->started_at))throw new RuntimeException('invalid_dpi');$stamp=str_replace(['T',':'],['_','-'],substr($legacy->started_at,0,-1));}
                    $files[]=AsusShareBundle::file('dpi','NFQWS2_DPI_'.$stamp.'Z.json',$raw);
                }
                if($version===4) {
                    $extra=(new AsusShareContributions($this->resources(),$this->dns()))->prepare($v,isset($v['strategy'])?$this->config():'',$this->versions());
                    foreach($extra as $type=>$raw)$files[]=AsusShareBundle::file($type,'NFQWS2_'.strtoupper($type).'_'.gmdate('Y-m-d_H-i-s',$now).'Z.json',$raw);
                }elseif(isset($v['strategy'])) {
                    $s=$v['strategy'];if(!is_array($s)||!is_string($s['mode']??null)||!is_array($s['context']??null))throw new RuntimeException('invalid_request');
                    if($s['mode']==='blocks') {
                        self::keys($s,['mode','draft','context'],['mode','draft','context']);if(!is_array($s['draft']))throw new RuntimeException('invalid_request');
                        $raw=AsusShareStrategy::prepare($s['draft'],$s['context'],$this->versions());
                    }elseif($s['mode']==='config') {
                        self::keys($s,['mode','config','context'],['mode','config','context']);if(!is_string($s['config']))throw new RuntimeException('invalid_request');
                        $raw=AsusShareStrategy::fullConfig($s['config'],$s['context'],$this->versions());
                    }else throw new RuntimeException('invalid_request');
                    $files[]=AsusShareBundle::file('strategy','NFQWS2_STRATEGY_'.gmdate('Y-m-d_H-i-s',$now).'Z.json',$raw);
                }
                $source=($this->source??=new AsusShareSource())->capture($v['link_installation']??false,$this->versions());
                return AsusShareBundle::prepare($files,$sessionKey,$now,$source,$version);
        }
        throw new RuntimeException('invalid_request');
    }
}
