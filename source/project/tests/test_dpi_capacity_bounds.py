"""Bounded larger workloads keep real descriptors, complete reports and device admission aligned."""
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC


class CapacityBoundsTests(unittest.TestCase):
    def php(self, code, value=None):
        r=subprocess.run([PHP,'-n','-r',"require $argv[1].'/dpi-jobs.php';$x=json_decode(stream_get_contents(STDIN),true);try{"+code+"}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}",str(PUBLIC)],input=json.dumps(value),capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def test_larger_pool_is_not_blocked_by_assumed_descriptor_headroom(self):
        for pool,fd,ready in [(800,1024,True),(992,1024,True),(993,1024,True),(1024,1056,True),(800,None,True),(800,0,True),(100000,4096,True),(1000000,4096,True)]:
            with self.subTest(pool=pool,fd=fd):
                v=self.php("echo json_encode(AsusDpiLoadPolicy::plan($x[0],4,524288,$x[1]));",[pool,fd])
                self.assertEqual(v.get('available'),ready)
                self.assertEqual(v.get('code'),'ready'if ready else'unsupported_runtime')
        self.assertEqual(self.php("echo json_encode(AsusDpiLoadPolicy::plan(1000001,4,524288,4096));")['code'],'invalid_request')

    def test_fd_limit_parser_refuses_duplicate_unknown_and_malformed_counters(self):
        for raw,want in [('Max open files            1024                 4096                 files\n',1024),
                         ('Max open files unlimited unlimited files\n',2147483647),('',0),
                         ('Max open files 1024 4096 files\nMax open files 1024 4096 files\n',0),
                         ('Max open files -1 4096 files\n',0),('Max open files 1024 4096 bytes\n',0)]:
            with self.subTest(raw=raw):self.assertEqual(self.php("echo json_encode(AsusDpiLoadPolicy::fileDescriptors($x));",raw),want)

    def test_large_workload_keeps_worker_hint_without_an_assumed_memory_floor(self):
        for cores,memory,ready in [(4,524288,True),(2,1048576,True),(4,524287,True)]:
            with self.subTest(cores=cores,memory=memory):
                v=self.php("echo json_encode(AsusDpiLoadPolicy::plan(10,$x[0],$x[1],1024,true));",[cores,memory])
                self.assertEqual(v['available'],ready)
                if ready:self.assertEqual([v['worker_threads'],v['memory_floor_kib']],[4,0])
        v=self.php("echo json_encode(AsusDpiInstaller::memoryAvailability(524287,['tests'=>[3],'options'=>['config'=>['MAX_CONCURRENT'=>10],'targets'=>['tcp'=>array_fill(0,513,[])]]],null));")
        self.assertEqual(v['code'],'ready')

    def test_normalized_thousand_tcp_targets_reach_native_files_without_widening_other_lists(self):
        code="$t=[];for($i=0;$i<$x;++$i)$t[]=['id'=>'fixture-'.$i,'ip'=>'203.0.113.1','port'=>443,'sni'=>'example.test'];$o=AsusDpiOptions::normalize(['config'=>['MAX_CONCURRENT'=>800],'targets'=>['tcp'=>$t]]);$c=AsusDpiOptions::compile($o,3,'/native');echo json_encode(['pool'=>$c['public_settings']['config']['MAX_CONCURRENT'],'coverage'=>$c['coverage']['tcp'],'native_rows'=>count(json_decode($c['files']['tcp16.json'],true)),'config_pool'=>json_decode($c['files']['config.yml'],true)['MAX_CONCURRENT'],'argv'=>$c['argv']]);"
        v=self.php(code,1000);self.assertNotIn('error',v);self.assertEqual([v['pool'],v['coverage'],v['native_rows']],[800,1000,1000]);self.assertEqual(v['config_pool'],800);self.assertIn('--tcp16',v['argv'])
        self.assertTrue(self.php(code,1001)['error'].startswith('invalid_options'))
        for options in [{'targets':{'domains':['example.test']*513}},{'config':{'DNS_EGRESS_CONCURRENCY':101}},{'burst':{'connections':101}}]:
            self.assertTrue(self.php("AsusDpiOptions::normalize($x);echo '{}';",options)['error'].startswith('invalid_options'))

    def test_runtime_binds_workload_cardinality_and_descriptor_snapshot(self):
        code=r'''$src=substr(file_get_contents($argv[1].'/dpi-load-policy.php'),5);$shim='namespace CapacityResources; function file_get_contents($p){return $GLOBALS["resource_fixture"][$p]??"";}';eval($shim.$src);$GLOBALS['resource_fixture']=['/proc/stat'=>"cpu 1 2 3 4\ncpu0 1 2 3 4\ncpu1 1 2 3 4\ncpu2 1 2 3 4\ncpu3 1 2 3 4\n",'/proc/meminfo'=>"MemAvailable: 524288 kB\n",'/proc/self/limits'=>"Max open files 831 4096 files\n"];
$a=CapacityResources\AsusDpiLoadPolicy::runtime(['config'=>['MAX_CONCURRENT'=>800]]);$b=CapacityResources\AsusDpiLoadPolicy::runtime(['config'=>['MAX_CONCURRENT'=>10],'targets'=>['tcp'=>array_fill(0,513,[])]]);echo json_encode([$a,$b]);'''
        v=self.php(code);self.assertEqual(v[0]['code'],'ready');self.assertEqual(v[1]['memory_floor_kib'],0)

    def test_launch_reports_real_transport_failure_instead_of_a_descriptor_prediction(self):
        from test_dpi_load_policy import DpiLoadPolicyTests
        v=DpiLoadPolicyTests.launch_fixture(self,524288,pool=800,fd=831)
        self.assertEqual(v,{'error':'launch_failed','transport':True,'plan':'4 0\n','mode':384})

    def report(self, count):
        code=r'''$rows=[];for($i=0;$i<$x;++$i)$rows[]=['id'=>'PRIVATE_NATIVE_ID','ip'=>'198.51.100.12','port'=>443,'status'=>'ok','detail'=>'elapsed_1234ms','duration_ms'=>12,'received_kb'=>16];$g=AsusDpiNative::group(json_encode(['schema_version'=>1,'results'=>['tcp16'=>$rows]]),3);$ctx=['nfqws'=>'running','ark'=>'absent','tun_observed'=>false];$n=AsusDpiNative::document(['started_at'=>1760000000,'finished_at'=>1760000001,'state'=>'completed','tests'=>[3]],[$g],['before'=>$ctx,'after'=>$ctx,'changed'=>false],['config'=>['MAX_CONCURRENT'=>800]],['tcp'=>$x],[]);$r=AsusDpiAnalysis::report(json_decode($n,true));$v=json_decode($r,true);echo json_encode(['rows'=>count($v['groups'][0]['rows']),'last'=>$v['groups'][0]['rows'][$x-1]['target'],'bytes'=>strlen($r),'pretty'=>str_contains($r,"\n    "),'coverage'=>$v['coverage']['tcp'],'leak'=>str_contains($r,'PRIVATE_NATIVE_ID')||str_contains($r,'198.51.100.12')]);'''
        return self.php(code,count)

    def test_large_analysis_keeps_all_rows_and_original_schema_quota(self):
        v=self.report(1000);self.assertNotIn('error',v);self.assertEqual([v['rows'],v['last'],v['coverage']],[1000,'tcp-1000',1000]);self.assertLessEqual(v['bytes'],262144);self.assertFalse(v['leak']);self.assertFalse(v['pretty'])

    def test_existing_small_analysis_stays_readable_and_oversize_coverage_still_refused(self):
        v=self.report(1);self.assertNotIn('error',v);self.assertTrue(v['pretty']);self.assertIn('error',self.report(1001))


if __name__=='__main__':unittest.main()
