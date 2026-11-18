"""Hard composite budgets and the actual guard loop with an accelerated clock."""
import json
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


class CustomBudgetTests(unittest.TestCase):
    def php(self, body):
        code="require $argv[1].'/strategy-picker-core.php';"+body
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],capture_output=True,text=True,timeout=8)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)

    def test_composite_deadline_comes_from_full_required_phases_not_observed_means(self):
        r=self.php(r'''
        $out=[];
        foreach([[4,3000000,6480],[2,80000,8760],[1,80000,14220]]as [$cpu,$ram,$expected]){
          $base=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose($cpu,$ram,0),38);
          $custom=NfqwsStrategyPickerBudget::custom($base,5);
          $out[]=['base'=>$base,'custom'=>$custom,'expected'=>$expected];
        }echo json_encode($out);
        ''')
        for row in r:
            base,custom=row['base'],row['custom']
            self.assertEqual(custom['deadline_seconds'],row['expected'])
            for k in ['concurrency','group_seconds','probe_seconds','timeout','max_repeats']:
                self.assertEqual(base[k],custom[k])
            self.assertEqual(custom['custom']['minimum_exploratory_trials'],1)
            self.assertEqual(custom['custom']['max_hosts'],5)
            self.assertEqual(custom['custom']['restore_seconds'],120)
            # 3 control + 2 zero + 1 discovery + 3 final native passes.
            minimum=9*(base['probe_seconds']+30)+1560
            self.assertGreaterEqual(custom['deadline_seconds'],minimum+60)
            self.assertLess(custom['deadline_seconds']-minimum,120)

    def test_current_trial_bound_accounts_warm_prepare_and_all_service_calls(self):
        r=self.php(r'''
        $b=['probe_seconds'=>510];$out=[];
        foreach([[2,true,true],[2,true,false],[2,false,false],[1,false,false]]as [$repeats,$warm,$prepare])
          $out[]=NfqwsStrategyPickerBudget::customTrialSeconds($b,$repeats,$warm,$prepare);
        echo json_encode($out);
        ''')
        self.assertEqual(r,[2070,1980,1440,810])

    def test_invalid_structure_refuses_but_observed_memory_does_not_block_a_series(self):
        r=self.php(r'''
        $base=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(4,3000000,0),38);
        $out=[];
        foreach([[$base,0],[$base,10],[$base,11],[array_replace($base,['available_kib'=>65535]),1],
          [array_replace($base,['probe_seconds'=>1800]),5],[array_replace($base,['probe_seconds'=>510.0]),5]]as [$b,$hosts]){
          try{NfqwsStrategyPickerBudget::custom($b,$hosts);$out[]='accepted';}
          catch(Throwable $e){$out[]=$e->getMessage();}
        }echo json_encode($out);
        ''')
        self.assertEqual(r,['invalid_request','accepted','invalid_request','accepted',
                            'accepted','invalid_request'])

    def guard(self, deadline, free_at=None):
        # Keep the production guard method byte-for-byte. Only its environment,
        # process handles, mutation writer and sleep/uptime are isolated doubles.
        code=r'''
        require $argv[1].'/strategy-picker-core.php';
        $source=file_get_contents(getenv('NFQWS_PICKER_GUARD_METHOD_FILE')?:$argv[1].'/strategy-picker-runtime.php');
        $begin=strpos($source,'    public function guard(string $id):void');
        $end=strpos($source,'    public function recoverBoot():bool',$begin);
        if($begin===false||$end===false)throw new RuntimeException('fixture_source');
        $method=substr($source,$begin,$end-$begin);
        $prefix=<<<'PHP'
        namespace CompositeGuardClock;
        use \RuntimeException;use \Throwable;use \NfqwsStrategyPickerBudget;
        class AsusUpdateStore {public static float $now=0;public static function uptime():float{return self::$now;}}
        function sleep($seconds){if($GLOBALS['unlimited_fixture']??false){if(AsusUpdateStore::$now===0.0)AsusUpdateStore::$now=172800;else{AsusUpdateStore::$now+=$seconds;$GLOBALS['guard_fixture']->store->j['state']='completed';}}else AsusUpdateStore::$now+=$seconds;return 0;}
        class AsusUpdateGuard {public function __construct($store){}public function mutationLease(){return tmpfile();}}
        class AsusImportTransaction {public function writer($callback){return $callback();}}
        class Store {
          public array $j;public array $guard;public function __construct(public ?int $freeAt){}
          public function read($name='state.json',&$pin=null){$pin=['model'=>'stable-'.$name];return $name==='actor-guard.json'?$this->guard:$this->j;}
          public function write($value,$name='state.json'){if($name==='state.json')$this->j=$value;elseif($name==='actor-guard.json')$this->guard=$value;}
          public function path($name){return '/nonexistent/composite-clock-fixture/'.$name;}
          public function lock(){if($this->freeAt===null||AsusUpdateStore::$now<$this->freeAt)throw new RuntimeException('busy');return tmpfile();}
        }
        class Guard {
          private const ACTIVE=['preparing','running','restoring','applying'];
          public bool $alive=true;public int $kills=0;public array $diagnostics=[];
          public static $self;public object $config;
          public function __construct(public Store $store){self::$self=$this;$this->config=new class{public function raw($bound=false){return 'CONFIG_DOUBLE';}};}
          public static function identity($pid){return ['pid'=>$pid];}
          private function actor($name,$id,&$pin=null){if($name==='guard'){$pin=['model'=>'stable-actor-guard.json'];return ['pid'=>getmypid()];}return $this->alive?['pid'=>123]:null;}
          private static function killTree($actor){self::$self->kills++;self::$self->alive=false;}
          private static function sameProcess($actor){return false;}
          private function stopOwnedProbe(){}
          private function customReap($boot=false,$commit=true){return false;}
          private function diagnoseGuard($id,$e){$this->diagnostics[]=$e->getMessage();}
          private function phase($phase,$extra){$this->store->j=array_replace($this->store->j,['phase'=>$phase],$extra);}
          private static function error($e){return $e->getMessage();}
          private function fail($code,$id){$this->phase('complete',['state'=>'failed','code'=>$code,'restored'=>true]);}
        PHP;
        eval($prefix.$method.'}');
        $s=new CompositeGuardClock\Store($argv[3]==='null'?null:(int)$argv[3]);
        $s->j=['id'=>str_repeat('a',32),'state'=>'running','phase'=>'discovering',
          'deadline'=>$argv[2]==='unlimited'?null:(int)$argv[2],'restored'=>false];if($argv[2]==='unlimited'){$s->j['started_uptime']=0;$GLOBALS['unlimited_fixture']=true;}
        $g=new CompositeGuardClock\Guard($s);$GLOBALS['guard_fixture']=$g;$g->guard($s->j['id']);
        echo json_encode(['job'=>$s->j,'now'=>CompositeGuardClock\AsusUpdateStore::$now,
          'kills'=>$g->kills,'diagnostics'=>$g->diagnostics]);
        '''
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(deadline),
                          'null'if free_at is None else str(free_at)],capture_output=True,text=True,timeout=8)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)

    def test_unlimited_guard_survives_two_days_until_own_worker_completes(self):
        r=self.guard('unlimited',0)
        self.assertEqual(r['job']['state'],'completed')
        self.assertIsNone(r['job']['deadline'])
        self.assertEqual(r['kills'],0)
        self.assertEqual(r['diagnostics'],[])
        self.assertGreaterEqual(r['now'],172800)

    def test_guard_keeps_full_fresh_recovery_window_after_legacy_3600_deadline(self):
        r=self.guard(3600)
        self.assertEqual(r['job']['state'],'recovery_required')
        self.assertEqual(r['job']['code'],'busy')
        self.assertGreaterEqual(r['now'],3780)
        self.assertEqual(r['kills'],1)

    def test_guard_outlives_composite_main_deadline_and_restores_after_writer_release(self):
        r=self.guard(6480,6600)
        self.assertEqual(r['job']['state'],'failed')
        self.assertEqual(r['job']['code'],'timed_out')
        self.assertTrue(r['job']['restored'])
        self.assertEqual(r['now'],6600)
        self.assertEqual(r['kills'],1)

    def test_legacy_finite_deadline_keeps_original_recovery_window_without_hidden_iteration_cutoff(self):
        r=self.guard(50000)
        self.assertEqual(r['job']['state'],'recovery_required')
        self.assertFalse(r['job']['restored'])
        self.assertEqual(r['job']['code'],'busy')
        self.assertGreaterEqual(r['now'],50180)


if __name__=='__main__':unittest.main()
