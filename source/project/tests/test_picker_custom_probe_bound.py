"""The production native wait loop has its own bound in a composite trial."""
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC


class CustomProbeBoundTests(unittest.TestCase):
    def observe(self, custom, complete_at, pool=None):
        code=r'''
        require $argv[1].'/strategy-picker-core.php';
        $source=file_get_contents($argv[1].'/strategy-picker-runtime.php');
        $begin=strpos($source,'    private function probe(');
        $end=strpos($source,'    private function stopOwnedProbe():void',$begin);
        if($begin===false||$end===false)throw new RuntimeException('fixture_source');
        $method=substr($source,$begin,$end-$begin);
        $prefix=<<<'PHP'
        namespace CompositeProbeClock;
        use \RuntimeException;use \Throwable;use \NfqwsStrategyPickerBudget;
        class AsusUpdateStore {public static float $now=0;public static function uptime():float{return self::$now;}}
        function sleep($seconds){AsusUpdateStore::$now+=$seconds;return 0;}
        class Store {public array $j;public function read(){return $this->j;}public function write($j){$this->j=$j;}}
        class AsusDpiJobs {
          public static int $completeAt;public static array $options=[];
          public function startRun($request,$groups,$unused,$options){self::$options=$options;return ['id'=>str_repeat('f',32)];}
          public function active(){return AsusUpdateStore::$now<self::$completeAt?['id'=>str_repeat('f',32)]:null;}
          public function native($id){return json_encode(['state'=>'completed']+(isset(self::$options['config'])&&Probe::$manual?
            ['settings'=>['config'=>['MAX_CONCURRENT'=>self::$options['config']['MAX_CONCURRENT']]]]:[]));}
        }
        class Probe {
          public static bool $manual=false;
          public function __construct(public Store $store){}
          private function checkpoint(){if(AsusUpdateStore::uptime()>=$this->store->j['deadline'])throw new RuntimeException('global_deadline');}
          private function customCheckpoint(){$this->checkpoint();}
          private function synthesisCustom($j){return isset($j['custom_hosts']);}
          private function phase($phase,$extra){$this->store->j=array_replace($this->store->j,$extra);}
          public function run(){return $this->probe([2,3]);}
        PHP;
        eval($prefix.$method.'}');
        $s=new CompositeProbeClock\Store();$s->j=['id'=>str_repeat('a',32),'phase'=>'measuring_1','deadline'=>3600,
          'budget'=>['concurrency'=>10,'probe_seconds'=>510,'group_seconds'=>240]];
        if($argv[2]==='yes')$s->j['custom_hosts']=['example.com'];
        if(($argv[4]??'legacy')!=='legacy'){
          $pool=$argv[4];$custom=$argv[2]==='yes';
          $selection=NfqwsStrategyPickerRequest::selection(false,'all',true,$custom?['hosts'=>['example.com'],'only'=>false]:null,$pool);
          $domains=['www.youtube.com'];
          $plan=NfqwsStrategyPickerConcurrency::plan($pool,NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(4,900000,0),1),
            ['cores'=>4,'available_kib'=>900000,'fd_soft'=>2048]);
          $s->j=array_replace($s->j,$selection,['selection_sha256'=>NfqwsStrategyPickerRequest::digest($selection),
            'probe_domains'=>$domains,'concurrency_choice'=>NfqwsStrategyPickerConcurrency::record($plan),
            'budget'=>$custom?NfqwsStrategyPickerBudget::custom($plan['budget'],1):$plan['budget']]);
          CompositeProbeClock\Probe::$manual=true;
        }
        CompositeProbeClock\AsusDpiJobs::$completeAt=(int)$argv[3];$p=new CompositeProbeClock\Probe($s);
        try{$result=$p->run();$error=null;}catch(Throwable $e){$result=null;$error=$e->getMessage();}
        $compiled=null;
        if(CompositeProbeClock\Probe::$manual&&$error===null){
          require $argv[1].'/dpi-options.php';
          $options=AsusDpiOptions::normalize(CompositeProbeClock\AsusDpiJobs::$options);
          $compiled=AsusDpiOptions::compile($options,2,'/trusted/native');
        }
        echo json_encode(['error'=>$error,'native'=>$result,'now'=>CompositeProbeClock\AsusUpdateStore::$now,
          'job'=>$s->j,'options'=>CompositeProbeClock\AsusDpiJobs::$options,'compiled'=>$compiled]);
        '''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),'yes'if custom else'no',str(complete_at),pool or 'legacy'],
                         capture_output=True,text=True,timeout=8)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)

    def test_composite_stalled_native_job_cannot_spend_the_global_generation_deadline(self):
        r=self.observe(True,600)
        self.assertEqual(r['error'],'timed_out')
        self.assertEqual(r['now'],540)
        self.assertEqual(r['job']['dpi_job'],'f'*32)
        self.assertRegex(r['job']['dpi_request'],r'^[a-f0-9-]{36}$')

    def test_composite_normal_completion_keeps_registered_native_options(self):
        r=self.observe(True,30)
        self.assertIsNone(r['error'])
        self.assertEqual(r['native'],{'state':'completed'})
        self.assertEqual(r['options']['limits'],{'total_seconds':510,'group_seconds':240})
        self.assertEqual(r['options']['config']['MAX_CONCURRENT'],10)
        self.assertEqual(r['now'],30)

    def test_fixed_only_native_wait_behavior_is_unchanged(self):
        r=self.observe(False,600)
        self.assertIsNone(r['error'])
        self.assertEqual(r['now'],600)

    def test_selected_pool_reaches_real_normalization_native_config_and_public_settings(self):
        for pool in ['32','992']:
            with self.subTest(pool=pool):
                r=self.observe(True,30,pool)
                self.assertIsNone(r['error'])
                self.assertEqual(r['options']['config']['MAX_CONCURRENT'],int(pool))
                self.assertEqual(json.loads(r['compiled']['files']['config.yml'])['MAX_CONCURRENT'],int(pool))
                self.assertEqual(r['compiled']['public_settings']['config']['MAX_CONCURRENT'],int(pool))
                self.assertEqual(r['job']['concurrency_choice']['effective'],int(pool))


if __name__=='__main__':unittest.main()
