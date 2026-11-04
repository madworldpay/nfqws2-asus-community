<?php
require_once __DIR__.'/update-store.php';

/** Protected per-network-step deadline, observed by an independent guardian. */
final class AsusUpdateDeadline
{
    private ?float $deadline=null;
    public function __construct(private AsusUpdateStore $store,private string $id) {$store->readOperation($id);}
    private function cancelled(): void
    {if($this->store->readFile('operations/'.$this->id.'/cancel.json',1024)!==null)throw new RuntimeException('timed_out');}
    public function begin(int $seconds): void
    {
        if($seconds<1||$seconds>180)throw new RuntimeException('invalid_state');$this->cancelled();$this->deadline=AsusUpdateStore::uptime()+$seconds;
        $this->store->writeFile('operations/'.$this->id.'/network.json',json_encode(['deadline'=>$this->deadline],JSON_THROW_ON_ERROR));
    }
    public function end(): void
    {
        $this->cancelled();if($this->deadline===null||AsusUpdateStore::uptime()>=$this->deadline)throw new RuntimeException('timed_out');
        $this->store->writeFile('operations/'.$this->id.'/network.json',json_encode(['deadline'=>null],JSON_THROW_ON_ERROR));$this->deadline=null;
    }
}

/** Durable rollback creation is bounded by work and measured USB flush latency. */
final class AsusUpdateApplyBudget
{
    public const MAX_SECONDS=1800;
    public static function seconds(int $files,float $flush):int
    {
        if($files<0||$files>4096||!is_finite($flush)||$flush<0)throw new RuntimeException('invalid_state');
        // Two times the observed flush cost plus two minutes for validation,
        // archives and service control. Never alter network/service timeouts.
        return (int)min(self::MAX_SECONDS,max(240,ceil(120+2*$files*$flush)));
    }
    public static function measure(string $directory,int $files,int $owner=0):array
    {
        self::seconds($files,0);AsusUpdateStore::noLinks($directory);$s=@lstat($directory);
        if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $latency=0.0;
        for($i=0;$i<2;$i++){
            $path=$directory.'/.flush-probe-'.bin2hex(random_bytes(12));$f=null;$mask=umask(0077);
            try{
                $f=@fopen($path,'xb');if(!$f||!chmod($path,0600)||fwrite($f,str_repeat('x',1024))!==1024||!fflush($f))throw new RuntimeException('insufficient_space');
                $start=hrtime(true);if(!fsync($f))throw new RuntimeException('insufficient_space');$latency=max($latency,(hrtime(true)-$start)/1e9);
            }finally{umask($mask);if(is_resource($f))fclose($f);if(is_file($path)&&!unlink($path))throw new RuntimeException('invalid_state');}
        }
        return ['seconds'=>self::seconds($files,$latency),'durable_files'=>$files,'fsync_seconds'=>$latency];
    }
}
