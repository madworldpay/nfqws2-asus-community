<?php
require_once __DIR__ . '/../webui/web/public/support-report-io.php';
require_once __DIR__ . '/../webui/web/public/support-report-values.php';
function reportCheck($yes, $label) { if (!$yes) throw new RuntimeException($label); }
class ReportFixtureIO extends AsusReportIO
{
    public array $files = [];
    public array $commands = [];
    public array $process = [];
    public array $inventory = [];
    public array $sockets = [];
    public float $time = 100;
    public $onPause = null;
    public function __construct() { parent::__construct([],fn()=>$this->time,function($s){$this->time+=$s; if($this->onPause) ($this->onPause)();}); }
    public function read(string $id, int $limit=262144): array { return isset($this->files[$id]) ? ['state'=>'available','value'=>$this->files[$id]] : ['state'=>'missing','value'=>'']; }
    public function streamCommand(string $id, callable $consume, float $timeout=1): array {
        if (!array_key_exists($id,$this->commands)) return ['state'=>'unsupported','exit_code'=>null];
        foreach (explode("\n",$this->commands[$id]) as $line) $consume($line);
        return ['state'=>'available','exit_code'=>0];
    }
    public function readProcess(int $pid,string $field,int $limit=16384): array { return isset($this->process[$pid][$field]) ? ['state'=>'available','value'=>$this->process[$pid][$field]] : ['state'=>'missing','value'=>'']; }
    public function queueSocket(int $pid,string $port): ?string { return $this->sockets[$pid][$port]??null; }
    public function engine(): array { return ['state'=>'available','sha256'=>str_repeat('a',64),'elf_class'=>2,'elf_machine'=>183]; }
    public function resources(string $kind): array { return array_keys($this->inventory[$kind]??[]); }
    public function readResource(string $kind,string $name,int $limit=262144): array { return isset($this->inventory[$kind][$name]) ? ['state'=>'available','value'=>$this->inventory[$kind][$name]] : ['state'=>'missing','value'=>'']; }
    public function arkComponents(): array { return ['state'=>'available','present'=>false]; }
}
