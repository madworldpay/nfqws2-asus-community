<?php
require_once __DIR__.'/support-report-network.php';
require_once __DIR__.'/support-report-dns.php';

final class AsusReportLock
{
    private $handle=null;
    public function __construct(private ?string $directory=null, private int $owner=0) {}
    public function acquire(): void
    {
        $dir=$this->directory??'/tmp/nfqws2-support-report';
        if(is_link($dir)) throw new RuntimeException('unavailable');
        if(!is_dir($dir) && !@mkdir($dir,0700)) throw new RuntimeException('unavailable');
        $s=@lstat($dir);
        if(!$s || $s['uid']!==$this->owner || ($s['mode']&0777)!==0700) throw new RuntimeException('unavailable');
        $file=$dir.'/collector.lock';
        if(is_link($file)) throw new RuntimeException('unavailable');
        if(!file_exists($file)) {
            $f=@fopen($file,'x+b');
            if($f) { @chmod($file,0600); fclose($f); }
        }
        $s=@lstat($file);
        if(!$s || ($s['mode']&0170000)!==0100000 || $s['uid']!==$this->owner || ($s['mode']&0777)!==0600) throw new RuntimeException('unavailable');
        $f=@fopen($file,'r+b'); if(!$f) throw new RuntimeException('unavailable');
        $opened=fstat($f);
        if($opened['ino']!==$s['ino'] || $opened['dev']!==$s['dev']) {fclose($f);throw new RuntimeException('unavailable');}
        if(!flock($f,LOCK_EX|LOCK_NB)) {fclose($f);throw new RuntimeException('busy');}
        $this->handle=$f;
    }
    public function release(): void
    {
        if(is_resource($this->handle)) {flock($this->handle,LOCK_UN);fclose($this->handle);}
        $this->handle=null;
        // Keep the empty lock inode: unlinking it creates a concurrent-lock race.
    }
    public function __destruct() { $this->release(); }
}

final class AsusSupportReport
{
    public function __construct(private AsusReportIO $io,private AsusReportValues $values) {}
    public function queueSample(?int $queue,array $identity): array
    {
        $out=['queue_number'=>$queue,'state'=>'unknown','backlog'=>null,'copy_mode'=>null,'copy_range'=>null,'kernel_drops'=>null,'user_drops'=>null,'sequence'=>null,'reserved'=>null,
            '_identity'=>$identity,'_binding'=>null,'_time'=>$this->io->now(),'source_state'=>'available'];
        if($queue===null || $queue<0 || $queue>65535) {$out['source_state']='unsupported';return $out;}
        $read=$this->io->read('queue',262144);$out['source_state']=$read['state'];
        if($read['state']!=='available')return $out;
        $found=[];
        foreach(explode("\n",trim($read['value'])) as $line) {
            $row=preg_split('/\s+/',trim($line));
            if(($row[0]??'')!== (string)$queue)continue;
            if(count($row)!==9) {$out['source_state']='unsupported';return $out;}
            $numbers=[];foreach($row as $value) {$n=AsusReportValues::uint32($value);if($n===null) {$out['source_state']='unsupported';return $out;}$numbers[]=$n;}
            $found[]=$numbers;
        }
        if(count($found)>1) {$out['source_state']='unsupported';return $out;}
        if(!$found) {$out['state']='unbound';return $out;}
        $row=$found[0];$out['state']='bound';$out['_binding']=(string)$row[1];
        foreach(['backlog'=>2,'copy_mode'=>3,'copy_range'=>4,'kernel_drops'=>5,'user_drops'=>6,'sequence'=>7,'reserved'=>8] as $key=>$index)$out[$key]=$row[$index];
        return $out;
    }
    public function compareQueue(array $first,array $second): array
    {
        $out=['result'=>'unavailable','delta'=>null,'interval_ms'=>max(0,(int)round(($second['_time']-$first['_time'])*1000))];
        $stableKeys=array_flip(['boot','pid','start_ticks','exe','uid','running']);
        if($first['queue_number']!==$second['queue_number'] || array_intersect_key($first['_identity'],$stableKeys)!==array_intersect_key($second['_identity'],$stableKeys) || $first['_binding']!==$second['_binding']) {$out['result']='changed_during_collection';return $out;}
        if($first['state']==='unbound'&&$second['state']==='unbound') {$out['result']='unbound';return $out;}
        if($first['state']!=='bound'||$second['state']!=='bound')return $out;
        foreach(['boot','pid','start_ticks','exe'] as $key)if(($first['_identity'][$key]??null)===null)return $out;
        if(($first['_identity']['running']??null)!==true)return $out;
        if($second['sequence']<$first['sequence']) {$out['result']='counter_decreased';return $out;}
        $out['delta']=$second['sequence']-$first['sequence'];$out['result']=$out['delta']>0?'increased':'unchanged';return $out;
    }
    private function queueNumber(array $runtime,array $saved): ?int
    {
        $value=$runtime['NFQUEUE_NUM']??$saved['NFQUEUE_NUM']??null;
        $number=is_string($value)?AsusReportValues::decimal($value,'65535'):null;
        return $number!==null?(int)$number:null;
    }
    public function collect(): array
    {
        $start=$this->io->now();$captured=gmdate('Y-m-d\TH:i:s\Z');
        $configRead=$this->io->read('config');$runtimeRead=$this->io->read('runtime');
        $saved=AsusReportValues::runtimeSettings($configRead['value']);$runtime=AsusReportValues::runtimeSettings($runtimeRead['value']);
        $platform=new AsusReportPlatform($this->io,$this->values);
        $first=$this->queueSample($this->queueNumber($runtime,$saved),$platform->identity());
        $sections=$platform->collect();
        $sections=array_merge($sections,(new AsusReportNetwork($this->io,$this->values))->collect($saved,$runtime));
        $sections['dns']=(new AsusReportDns($this->io,$this->values))->collect();
        $this->io->pause(max(0,10-($this->io->now()-$first['_time'])));
        $runtimeAfter=$this->io->read('runtime');$savedAfter=$this->io->read('config');
        $second=$this->queueSample($this->queueNumber(AsusReportValues::runtimeSettings($runtimeAfter['value']),AsusReportValues::runtimeSettings($savedAfter['value'])),$platform->identity());
        $comparison=$this->compareQueue($first,$second);
        if($savedAfter!==$configRead||$runtimeAfter!==$runtimeRead) {
            $comparison=['result'=>'changed_during_collection','delta'=>null,'interval_ms'=>$comparison['interval_ms']];
            $sections['settings']['state']='partial';$sections['settings']['reason']='changed_during_collection';
        }
        $view=static function($sample){foreach(array_keys($sample) as $key)if(str_starts_with($key,'_'))unset($sample[$key]);return $sample;};
        $sections['nfqueue']=AsusReportPlatform::section(['samples'=>[$view($first),$view($second)],'comparison'=>$comparison],
            in_array($comparison['result'],['increased','unchanged','unbound'],true)?'available':'partial',
            $comparison['result']==='changed_during_collection'?'changed_during_collection':($first['source_state']!=='available'?$first['source_state']:'unsupported'));
        $failures=[];
        foreach($sections as $name=>$section)if($section['state']!=='available')$failures[]=['section'=>$name,'code'=>in_array($section['reason']??'', ['missing','denied','timeout','unsupported','truncated','changed_during_collection'],true)?$section['reason']:'unsupported'];
        if($this->io->remaining()<=0)$failures[]=['section'=>'nfqueue','code'=>'timeout'];
        return ['schema_version'=>1,'collector_version'=>'1.1.0','model'=>$sections['platform']['data']['model'],'captured_at'=>$captured,
            'duration_ms'=>max(0,(int)round(($this->io->now()-$start)*1000)),'complete'=>!$failures,'sections'=>$sections,'failures'=>$failures];
    }
    public static function encode(array $report): string
    {
        $json=json_encode($report,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
        if(strlen($json)+1>1048576) {
            $report['complete']=false;
            foreach($report['sections'] as $key=>$_) $report['sections'][$key]=['state'=>'unavailable','data'=>[],'reason'=>'truncated'];
            $report['failures']=array_map(fn($key)=>['section'=>$key,'code'=>'truncated'],array_keys($report['sections']));
            $json=json_encode($report,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
        }
        return $json."\n";
    }
    public static function filename(array $report): string
    {
        $model=AsusReportPlatform::model($report['model']??null);
        $date=is_string($report['captured_at']??null)&&preg_match('/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/D',$report['captured_at'])?$report['captured_at']:gmdate('Y-m-d\TH:i:s\Z');
        return 'NFQWS2_'.$model.'_'.str_replace(['T',':'],['_','-'],substr($date,0,-1)).'Z.json';
    }
}

function asusReportSameOrigin(): bool
{
    $origin=$_SERVER['HTTP_ORIGIN']??null;$host=$_SERVER['HTTP_HOST']??null;
    if(!is_string($origin)||!is_string($host)||preg_match('/[\x00-\x20]/',$origin.$host))return false;
    $scheme=isset($_SERVER['HTTPS'])&&in_array($_SERVER['HTTPS'],['on','1'],true)?'https':'http';
    $expected=parse_url($scheme.'://'.$host);$actual=parse_url($origin);
    if(!$actual||!$expected||!isset($actual['scheme'],$actual['host']))return false;
    foreach(['user','pass','path','query','fragment'] as $key)if(isset($actual[$key]))return false;
    return $actual['scheme']===$scheme&&strtolower($actual['host'])===strtolower($expected['host']??'')&&
        ($actual['port']??($scheme==='https'?443:80))===($expected['port']??($scheme==='https'?443:80));
}
