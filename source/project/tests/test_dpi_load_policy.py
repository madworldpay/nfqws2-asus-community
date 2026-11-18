"""Advanced request pools keep typed options, device admission and guard plans aligned."""
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC


class DpiLoadPolicyTests(unittest.TestCase):
    def launch_fixture(self, memory, pool=400, fd=1024):
        import tempfile
        code=r'''require $argv[1].'/dpi-jobs.php';$base=$argv[2];$GLOBALS['launch_base']=$base;$GLOBALS['launch_memory']=(int)$argv[3];$GLOBALS['launch_pool']=(int)$argv[4];$GLOBALS['launch_fd']=(int)$argv[5];
$shim= <<<'PHP'
namespace LoadLaunchFixture;
use \RuntimeException;use \Throwable;
class NfqwsPlatform{static function native(){return false;}static function translate($p){return $p==='/opt/var/lib/nfqws2-asus/dpi-detector'?$GLOBALS['launch_base'].'/state':$p;}}
class AsusDpiStore{function status(){return ['active'=>['id'=>str_repeat('a',32),'kind'=>'run']];}function readOptions($id){return ['config'=>['MAX_CONCURRENT'=>$GLOBALS['launch_pool']],'limits'=>['total_seconds'=>600]];}}
class AsusDpiLoadPolicy{static function runtime($o){return \AsusDpiLoadPolicy::plan($o['config']['MAX_CONCURRENT'],4,$GLOBALS['launch_memory'],$GLOBALS['launch_fd']);}static function plan(...$a){return \AsusDpiLoadPolicy::plan(...$a);}}
function file_get_contents($p,...$a){return $p==='/proc/self/status'?"Uid:\t0\t0\t0\t0\nCapInh:\t00000000\nCapAmb:\t00000000\n":\file_get_contents($p,...$a);}
function is_executable($p){return true;}function is_file($p){return str_ends_with($p,'/guard.sh')||\is_file($p);}
function proc_open(...$a){$GLOBALS['transport_attempted']=true;return false;}
PHP;
$source=str_replace('__DIR__',var_export($argv[1],true),substr(file_get_contents($argv[1].'/dpi-runtime.php'),5));file_put_contents($base.'/fixture.php','<?php '.$shim.$source);require $base.'/fixture.php';mkdir($base.'/state',0700);
try{(new LoadLaunchFixture\AsusDpiRuntime())->launch(str_repeat('a',32),'run');$error=null;}catch(Throwable $e){$error=$e->getMessage();}
$path=$base.'/state/runs/'.str_repeat('a',32).'/load.plan';echo json_encode(['error'=>$error,'transport'=>$GLOBALS['transport_attempted']??false,'plan'=>is_file($path)?file_get_contents($path):null,'mode'=>is_file($path)?fileperms($path)&0777:null]);'''
        with tempfile.TemporaryDirectory()as tmp:
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),tmp,str(memory),str(pool),str(fd)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def test_launch_keeps_reported_low_memory_without_stopping_before_transport(self):
        v=self.launch_fixture(65535)
        self.assertEqual(v,{'error':'launch_failed','transport':True,'plan':'4 0\n','mode':384})

    def test_launch_writes_private_bounded_plan_before_starting_transport(self):
        v=self.launch_fixture(65536)
        self.assertEqual(v,{'error':'launch_failed','transport':True,'plan':'4 0\n','mode':384})

    def call(self, op, payload):
        code = """$p=json_decode(stream_get_contents(STDIN),true);$f=$argv[1].'/dpi-load-policy.php';
        if(!is_file($f)){echo json_encode(['error'=>'not_implemented']);exit;}require $f;
        try{$v=match($p['op']){
          'plan'=>AsusDpiLoadPolicy::plan($p['pool'],$p['cores'],$p['memory']),
          'cores'=>AsusDpiLoadPolicy::cores($p['raw']),
          'memory'=>AsusDpiLoadPolicy::availableMemoryKiB($p['raw']),
          default=>throw new RuntimeException('invalid')};echo json_encode($v);}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
        r = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC)], input=json.dumps({'op': op, **payload}), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(r.stderr, '')
        return json.loads(r.stdout)

    def test_advanced_load_does_not_use_observations_as_capacity_limits(self):
        v = self.call('plan', {'pool': 200, 'cores': 2, 'memory': 65536})
        self.assertEqual(v, {'available': True, 'code': 'ready', 'worker_threads': 4, 'memory_floor_kib': 0})
        for memory in [0, 24576, 65535]:
            with self.subTest(memory=memory):
                self.assertEqual(self.call('plan', {'pool': 101, 'cores': 4, 'memory': memory})['code'], 'ready')
        self.assertEqual(self.call('plan', {'pool': 200, 'cores': 0, 'memory': 98304})['code'], 'ready')
        for cores in [1, 2, 3]:
            with self.subTest(cores=cores):
                self.assertEqual(self.call('plan', {'pool': 200, 'cores': cores, 'memory': 98304})['code'], 'ready')

    def test_legacy_load_keeps_native_default_without_new_live_memory_floor(self):
        for pool in [1, 4, 10, 50, 100]:
            with self.subTest(pool=pool):
                self.assertEqual(self.call('plan', {'pool': pool, 'cores': 2, 'memory': 61440}),
                                 {'available': True, 'code': 'ready', 'worker_threads': None, 'memory_floor_kib': 0})

    def test_pool_is_never_silently_clamped_or_coerced(self):
        for pool in [0, -1, 1000001, 101.5, '128', True, None]:
            with self.subTest(pool=pool):
                self.assertEqual(self.call('plan', {'pool': pool, 'cores': 4, 'memory': 1048576}).get('code'), 'invalid_request')

    def test_core_parser_rejects_unknown_duplicate_and_malformed_rows(self):
        rows = 'cpu  1 2 3 4 5 6 7 8 0 0\n' + ''.join(f'cpu{i} 1 2 3 4 5 6 7 8 0 0\n' for i in range(4))
        self.assertEqual(self.call('cores', {'raw': rows}), 4)
        for raw in ['', 'cpu 1 2 3\n', rows + 'cpu0 1 2 3 4\n', rows + 'cpu4 broken\n']:
            with self.subTest(raw=raw): self.assertEqual(self.call('cores', {'raw': raw}), 0)

    def test_memory_parser_preserves_strict_available_and_old_kernel_fallback(self):
        for raw, expected in [('MemAvailable: 524288 kB\nMemFree: 1 kB\n', 524288), ('MemFree: 61440 kB\n', 61440),
                              ('MemAvailable: broken\nMemFree: 999999 kB\n', 0), ('MemAvailable: 1 kB\nMemAvailable: 2 kB\n', 0),
                              ('MemAvailable: 9999999999 kB\n', 0)]:
            with self.subTest(raw=raw): self.assertEqual(self.call('memory', {'raw': raw}), expected)


if __name__ == '__main__': unittest.main()
