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
