<?php
require_once __DIR__.'/share-read.php';

/** Bounded dnsmasq data includes. Never evaluates configuration as code. */
final class AsusSmartDnsConfig
{
    private const FILE_LIMIT=262144;
    private const IDENTITY=['dev','ino','mode','uid','gid','nlink','size','mtime','ctime'];

    public static function includePath(string $line): string
    {
        $value=preg_replace('/^[^=]*=[ \t]*/','',$line);
        if (str_contains($value,'\\')) throw new RuntimeException('existing_dns_rules');
        if (str_starts_with($value,'"')) {
            if (!preg_match('/^"([^"]*)"(?:[ \t\r]*|[ \t\r]+#.*)$/D',$value,$m)) throw new RuntimeException('existing_dns_rules');
            $path=$m[1];
        } else {
            $path=preg_replace('/[ \t\r]+#.*/','',$value);$path=rtrim($path," \t\r");
        }
        if (strlen($path)>1024 || !preg_match('~^/[A-Za-z0-9_.+/ -]+$~D',$path) ||
            preg_match('~//|/\.{1,2}(?:/|$)~',$path)) throw new RuntimeException('existing_dns_rules');
        return $path;
    }
    private static function walk(string $text,callable $reader): array
    {
        $files=[];$active=[];$scanned=strlen($text);$visited=0;$output='';
        $append=function(string $value)use(&$output){
            if (strlen($output)+strlen($value)>262144) throw new RuntimeException('existing_dns_rules');
            $output.=$value;
        };
        $visit=function(string $body,int $depth)use(&$visit,&$files,&$active,&$scanned,&$visited,$reader,$append){
            if ($depth>8 || strlen($body)>262144 || str_contains($body,"\0")) throw new RuntimeException('existing_dns_rules');
            foreach (explode("\n",rtrim($body,"\n")) as $raw) {
                $visited+=strlen($raw)+1;
                if ($visited>1048576) throw new RuntimeException('existing_dns_rules');
                $line=trim($raw);
                if (preg_match('/^(conf-dir|conf-script)\s*(?:=|$)/',$line)) throw new RuntimeException('existing_dns_rules');
                if (!preg_match('/^conf-file\s*(?:=|$)/',$line)) {$append($raw."\n");continue;}
                if (!preg_match('/^conf-file\s*=/',$line)) throw new RuntimeException('existing_dns_rules');
                $path=self::includePath($line);
                if (isset($active[$path])) throw new RuntimeException('existing_dns_rules');
                if (!isset($files[$path])) {
                    if (count($files)>=31) throw new RuntimeException('existing_dns_rules');
                    $entry=$reader($path);
                    if (!is_array($entry) || !is_string($entry['value']??null)) throw new RuntimeException('existing_dns_rules');
                    $scanned+=strlen($entry['value']);
                    if ($scanned>1048576) throw new RuntimeException('existing_dns_rules');
                    $files[$path]=$entry;
                }
                $active[$path]=true;$visit($files[$path]['value'],$depth+1);unset($active[$path]);
            }
        };
        $visit($text,1);
        return ['text'=>$output,'files'=>$files];
    }
    public static function expand(string $text,array $files): string
    {
        return self::walk($text,static function($path)use($files){
            if (!is_string($files[$path]??null)) throw new RuntimeException('existing_dns_rules');
            return ['value'=>$files[$path]];
        })['text'];
    }
    private static function target(string $path,int $owner,bool $allowRepair): array
    {
        $canonical=$path;$boundary=null;$alias=null;
        if (str_starts_with($path,'/opt/')) {
            $boundary=realpath('/opt');
            if ($boundary===false) throw new RuntimeException('existing_dns_rules');
            $alias='/opt';$canonical=$boundary.substr($path,4);
        }
        return [$canonical,new AsusShareRead($owner,$boundary,$alias,$allowRepair)];
    }
    private static function metadata(array|false|null $stat): array
    {
        if(!$stat)throw new RuntimeException('stale_baseline');
        return array_intersect_key($stat,array_flip(self::IDENTITY));
    }
    /** Automatic tightening admits only leaf DNS data with no file or script directives. */
    private static function repairableData(string $value,int $mode): bool
    {
        if(($mode&07111)!==0)return false;
        $seen=false;
        foreach(explode("\n",$value)as $raw){
            $line=trim($raw," \t\r");
            if($line===''||str_starts_with($line,'#'))continue;
            $line=preg_replace('/[ \t]+#.*/','',$line);
            if(!preg_match('~^(?:(?:filter-A|filter-AAAA|no-resolv)|(?:server|rev-server|local|address|ipset|nftset)[ \t]*=[ \t]*[a-zA-Z0-9_.:/,@#%+*\[\]!-]+)$~D',$line))
                return false;
            $seen=true;
        }
        return $seen;
    }
    private static function read(string $path,int $owner,bool $allowRepair=false): array
    {
        [$canonical,$reader]=self::target($path,$owner,$allowRepair);
        $stat=$reader->stat($canonical);
        if(!$stat||$stat['uid']!==$owner||(!$allowRepair&&($stat['mode']&0022)!==0))
            throw new RuntimeException('existing_dns_rules');
        try{$value=$reader->bytes($canonical,self::FILE_LIMIT);}
        catch(Throwable $e){throw new RuntimeException('existing_dns_rules',0,$e);}
        $metadata=self::metadata($stat);
        if(self::metadata($reader->stat($canonical))!==$metadata)throw new RuntimeException('stale_baseline');
        if(($metadata['mode']&0022)!==0&&!self::repairableData($value,$metadata['mode']))
            throw new RuntimeException('existing_dns_rules');
        return ['value'=>$value,'fingerprint'=>['sha256'=>hash('sha256',$value),'file'=>$metadata]];
    }
    public static function collect(string $text,int $owner=0,bool $allowRepair=false): array
    {
        $result=self::walk($text,static fn($path)=>self::read($path,$owner,$allowRepair));
        $fingerprints=[];$repairable=[];
        foreach ($result['files'] as $path=>$entry) {
            if(self::read($path,$owner,$allowRepair)!==$entry)throw new RuntimeException('stale_baseline');
            $fingerprint=$entry['fingerprint'];
            if($allowRepair&&self::repairableData($entry['value'],$fingerprint['file']['mode'])){
                if(($fingerprint['file']['mode']&0022)!==0)$repairable[$path]=$entry;
                // Proofs of prepared DNS stay valid across this one mode change.
                $fingerprint['file']['mode']&=~0022;
                unset($fingerprint['file']['ctime']);
            }
            if(!$allowRepair)unset($fingerprint['file']['gid']); // Legacy baseline digest.
            $fingerprints[$path]=$fingerprint;
        }
        ksort($fingerprints);
        $view=['text'=>$result['text'],'fingerprints'=>$fingerprints];
        if($allowRepair){ksort($repairable);$view['repairable']=$repairable;}
        return $view;
    }

    /** The callback durably keeps the complete private batch before the first chmod. */
    public static function repair(string $text,callable $backup,int $owner=0,?array $expected=null): void
    {
        $current=self::collect($text,$owner,true);
        if($expected!==null&&$expected!==$current)throw new RuntimeException('stale_baseline');
        $verify=static fn()=>self::collect($text,$owner,true);
        self::repairEntries($current['repairable'],$backup,$owner,static function()use($current,$verify):void{
            if($verify()!==$current)throw new RuntimeException('stale_baseline');
        });
        $current['repairable']=[];
        if($verify()!==$current)throw new RuntimeException('stale_baseline');
    }
    /** Historical includes can be repaired only while their original inode and bytes still match. */
    public static function repairKnown(array $fingerprints,callable $backup,int $owner=0): void
    {
        $verify=static fn()=>self::knownEntries($fingerprints,$owner);
        $current=$verify();
        self::repairEntries($current,$backup,$owner,static function()use($current,$verify):void{
            if($verify()!==$current)throw new RuntimeException('stale_baseline');
        });
        if($verify()!==[])throw new RuntimeException('stale_baseline');
    }
    private static function knownEntries(array $fingerprints,int $owner): array
    {
        if(count($fingerprints)>31)throw new RuntimeException('existing_dns_rules');
        $repairable=[];$total=0;
        foreach($fingerprints as $path=>$expected){
            if(!is_string($path)||self::includePath('conf-file='.$path)!==$path||!is_array($expected)
                ||!is_string($expected['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$expected['sha256'])
                ||!is_array($expected['file']??null))
                throw new RuntimeException('existing_dns_rules');
            // A historical reference is only authority to narrow permissions.
            // Missing or already-protected paths may no longer be in use.
            [$canonical]=self::target($path,$owner,true);
            clearstatcache(true,$canonical);$stat=@lstat($canonical);
            if(!$stat||($stat['mode']&0022)===0)continue;
            $entry=self::read($path,$owner,true);
            $file=$entry['fingerprint']['file'];$proof=$expected['file'];
            $total+=$file['size'];
            if($total>1048576)throw new RuntimeException('existing_dns_rules');
            if(!hash_equals($expected['sha256'],$entry['fingerprint']['sha256']))throw new RuntimeException('stale_baseline');
            foreach(['dev','ino','uid','nlink','size','mtime']as $key)
                if(($proof[$key]??null)!==$file[$key])throw new RuntimeException('stale_baseline');
            if(($proof['mode']??null)!==($file['mode']&~0022)
                ||($proof['gid']??$owner)!==$file['gid']
                ||!self::repairableData($entry['value'],$file['mode']))
                throw new RuntimeException('stale_baseline');
            if(($file['mode']&0022)!==0)$repairable[$path]=$entry;
        }
        ksort($repairable);
        return $repairable;
    }
    private static function checkHandle(array $entry,array $file): void
    {
        $handle=$file['handle'];$path=$file['path'];$reader=$file['reader'];
        if(!$reader->directory(dirname($path))||!rewind($handle)
            ||stream_get_contents($handle,self::FILE_LIMIT+1)!==$entry['value']
            ||self::metadata(fstat($handle))!==$entry['fingerprint']['file']
            ||self::metadata($reader->stat($path))!==$entry['fingerprint']['file'])
            throw new RuntimeException('stale_baseline');
    }
    private static function descriptor(array $metadata): string
    {
        $fds=glob('/proc/self/fd/*');
        if(is_array($fds)&&count($fds)<=1024)foreach($fds as $fd){
            clearstatcache(true,$fd);$stat=@stat($fd);
            if($stat&&self::metadata($stat)===$metadata)return $fd;
        }
        throw new RuntimeException('existing_dns_rules');
    }
    private static function repairEntries(array $entries,callable $backup,int $owner,callable $verify): void
    {
        if($entries===[])return;
        $held=[];
        try{
            foreach($entries as $name=>$entry){
                [$path,$reader]=self::target($name,$owner,true);
                if(!$reader->directory(dirname($path))||self::metadata($reader->stat($path))!==$entry['fingerprint']['file'])
                    throw new RuntimeException('stale_baseline');
                $handle=@fopen($path,'rb');
                if(!$handle)throw new RuntimeException('existing_dns_rules');
                $held[$name]=['handle'=>$handle,'path'=>$path,'reader'=>$reader];
                if(!flock($handle,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');
                self::checkHandle($entry,$held[$name]);
            }
            $backup($entries);
            $verify();
            foreach($entries as $name=>$entry){
                $file=$held[$name];$before=$entry['fingerprint']['file'];
                self::checkHandle($entry,$file);
                // Target the held inode even if a third party replaces the name.
                $mode=$before['mode']&07777&~0022;
                if(!@chmod(self::descriptor($before),$mode))throw new RuntimeException('existing_dns_rules');
                $after=self::metadata(fstat($file['handle']));
                $expected=$before;$expected['mode']=0100000|$mode;$expected['ctime']=$after['ctime'];
                if($after!==$expected)throw new RuntimeException('stale_baseline');
                $entry['fingerprint']['file']=$after;
                self::checkHandle($entry,$file);
            }
        }finally{
            foreach($held as $file)fclose($file['handle']);
        }
    }
}
