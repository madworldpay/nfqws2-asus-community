"""Native source snapshots and original probe callbacks, with LOCAL job files.

The actual probe method body runs in a harness whose admission/guard/context
are explicit doubles. AsusDpiStore/AsusDpiJobs and artifact readers are real.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC


class PickerNativeSourceTests(unittest.TestCase):
    def setUp(self):
        artifacts = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifacts:
            self.temp = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=artifacts))
        else:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.temp = Path(tmp.name)
        self.count = 0

    def call(self, action='snapshot', fault=''):
        runtime = (PUBLIC/'strategy-picker-runtime.php').read_text()
        start = runtime.index('    private function probe(')
        end = runtime.index('    private function stopOwnedProbe()', start)
        method = runtime[start:end]
        boot = r'''require $argv[1].'/dpi-jobs.php';require $argv[1].'/strategy-picker-core.php';
        if(!method_exists('AsusDpiStore','nativeSnapshot')||!method_exists('AsusDpiJobs','nativeSnapshot')){echo json_encode(['missing_api'=>true]);exit;}
        final class NativeSourceGateDouble {public function idle(callable $fn):mixed{return $fn();}}
        final class NativeSourceProbeHarness {
          public array $events=[];
          public function __construct(public $store,public $config,public string $root){}
          private function checkpoint():void {$this->events[]='checkpoint';}
          private function synthesisCustom(array $j):bool{return false;}
          private function phase(string $phase,array $v):void {$this->store->write(array_replace($this->store->read(),$v));}
          private function resourcesFingerprint():string{return hash_file('sha256',$this->root.'/resource');}
          public function run($jobs,callable $sink):array{return $this->probe([2,3],$sink,$jobs);}
        '''+method+r'''}
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$root=$argv[2];$uid=(int)$argv[3];
        $s=new AsusDpiStore($root.'/dpi',$uid);$request='11111111-1111-4111-8111-111111111111';
        $native=" {\"state\":\"completed\",\"value\":\"exact native bytes\"} \n";
        $out=[];
        try{
          if($d['action']==='snapshot'){
            $job=$s->reserve($request,'run',['tests'=>[2,3],'options'=>['fixture'=>'actual saved options']]);
            $s->update($job['id'],['state'=>'running']);
            $state=$d['fault']==='partial'?'partial':'completed';
            $s->update($job['id'],['state'=>$state,'native'=>$native]);
            $path=$root.'/dpi/'.$job['id'].'.native.json';$out['id']=$job['id'];
            if($d['fault']==='request')$request='22222222-2222-4222-8222-222222222222';
            if($d['fault']==='options')file_put_contents($root.'/dpi/'.$job['id'].'.options.json','{"changed":true}');
            if($d['fault']==='symlink'){rename($path,$root.'/foreign.native');symlink($root.'/foreign.native',$path);}
            if($d['fault']==='hardlink')link($path,$root.'/foreign.native');
            if($d['fault']==='overcap')file_put_contents($path,str_repeat('x',1048577));
            if($d['fault']==='deleted')$s->deleteResult($job['id']);
            if($d['fault']==='boot'){
              $db=json_decode(file_get_contents($root.'/dpi/jobs.json'),true);$db['jobs'][$job['id']]['boot_id']='foreign-boot';
              file_put_contents($root.'/dpi/jobs.json',json_encode($db));}
            $jobs=new AsusDpiJobs($s);$out['snapshot']=$jobs->nativeSnapshot($job['id'],$request);
            if($d['fault']==='fresh'){
              file_put_contents($path,$native."\n");$out['fresh']=$jobs->nativeSnapshot($job['id'],$request);}
          }else{
            file_put_contents($root.'/config','original configuration');file_put_contents($root.'/resource','original resource');
            $parent=new NfqwsStrategyPickerState($root.'/picker',$uid);
            $parent->write(['id'=>str_repeat('a',32),'request_id'=>str_repeat('b',32),'state'=>'running','phase'=>'measuring_1',
              'current'=>hash_file('sha256',$root.'/config'),'resources_sha256'=>hash_file('sha256',$root.'/resource'),
              'budget'=>['concurrency'=>2,'probe_seconds'=>30,'group_seconds'=>15]]);
            $config=new NfqwsStrategyPickerConfig($parent,$root.'/config',$uid);
            $h=new NativeSourceProbeHarness($parent,$config,$root);
            $jobs=new AsusDpiJobs($s,['installed'=>fn()=>true,'available'=>fn()=>['available'=>true],
              'terminal_gate'=>new NativeSourceGateDouble(),
              'launch'=>function($id,$kind)use($s,$native,$d){$s->update($id,['state'=>'running']);
                $s->update($id,['state'=>'completed','native'=>$d['fault']==='json'?'BROKEN_NATIVE_JSON':$native]);}]);
            try{$out['native']=$h->run($jobs,function($snapshot)use($root,$d,$parent,&$out){
              // The sink is an actual local fsync/readback double for the
              // existing future ROOT/PC collector, never a live transport.
              $f=fopen($root.'/captured.raw','xb');fwrite($f,$snapshot['native']['raw']);fflush($f);fsync($f);fclose($f);
              if(file_get_contents($root.'/captured.raw')!==$snapshot['native']['raw'])throw new RuntimeException('fixture_capture_failed');
              $out['captured']=$snapshot;
              if($d['fault']==='config')file_put_contents($root.'/config','FOREIGN_CONFIG');
              if($d['fault']==='resource')file_put_contents($root.'/resource','FOREIGN_RESOURCE');
              if($d['fault']==='parent'){$j=$parent->read();$j['dpi_request']='foreign-request';$parent->write($j);}
            });}finally{$out['events']=$h->events;$out['parent']=$parent->read();}
          }
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $out['db']=json_decode(file_get_contents($root.'/dpi/jobs.json'),true);
        echo json_encode($out,JSON_THROW_ON_ERROR);'''
        self.count += 1; root = self.temp/str(self.count); root.mkdir(mode=0o700)
        request = json.dumps({'action': action, 'fault': fault})
        (root/'probe-method.php').write_text(method)
        (root/'executed.php').write_text(boot)
        (root/'request.json').write_text(request)
        run = subprocess.run([PHP, '-n', '-r', boot, str(PUBLIC), str(root), str(os.getuid())],
                             input=request, text=True, capture_output=True, timeout=25)
        (root/'stdout.json').write_text(run.stdout); (root/'stderr').write_text(run.stderr)
        self.assertEqual((run.returncode, run.stderr), (0, ''), run.stdout+run.stderr)
        result = json.loads(run.stdout)
        self.assertNotIn('missing_api', result, 'missing native source snapshot API')
        return result, root

    def test_actual_job_request_options_and_exact_native_buffer_are_one_source_snapshot(self):
        out, root = self.call(); self.assertNotIn('error', out, out.get('error'))
        snap = out['snapshot']; self.assertEqual(snap['mode'], 'dpi-native-source-snapshot-v1')
        self.assertEqual(snap['job']['id'], out['id'])
        self.assertEqual(snap['job']['request_id'], '11111111-1111-4111-8111-111111111111')
        for key, name in [('index', 'jobs.json'), ('options', out['id']+'.options.json'), ('native', out['id']+'.native.json')]:
            artifact = snap[key]; raw = artifact['raw'].encode()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), artifact['sha256'])
            self.assertEqual(len(raw), artifact['bytes'])
            self.assertEqual(len(artifact['metadata']), 9)
            if key != 'index': self.assertEqual(raw, (root/'dpi'/name).read_bytes())
        self.assertEqual(snap['options']['sha256'], snap['job']['params']['options_digest'])
        self.assertEqual(json.loads(snap['index']['raw'])['jobs'][out['id']], snap['job'])

    def test_wrong_request_partial_deleted_or_foreign_boot_never_becomes_a_snapshot(self):
        for fault in ('request', 'partial', 'deleted', 'boot'):
            with self.subTest(fault=fault):
                out, root = self.call(fault=fault)
                self.assertIn('error', out); self.assertNotIn('snapshot', out)
                if fault != 'deleted': self.assertTrue((root/'dpi'/(out['id']+'.native.json')).exists())

    def test_changed_options_digest_refuses_and_keeps_actual_native_bytes(self):
        out, root = self.call(fault='options')
        self.assertIn('error', out); self.assertNotIn('snapshot', out)
        self.assertIn(b'exact native bytes', (root/'dpi'/(out['id']+'.native.json')).read_bytes())

    def test_linked_or_overcap_artifact_is_preserved_and_refused(self):
        for fault in ('symlink', 'hardlink', 'overcap'):
            with self.subTest(fault=fault):
                out, root = self.call(fault=fault)
                self.assertIn('error', out); self.assertNotIn('snapshot', out)
                path = root/'dpi'/(out['id']+'.native.json')
                self.assertTrue(path.exists())
                if fault == 'symlink': self.assertTrue(path.is_symlink())
                if fault == 'hardlink': self.assertEqual(path.stat().st_nlink, 2)
                if fault == 'overcap': self.assertEqual(path.stat().st_size, 1048577)

    def test_second_read_uses_fresh_actual_raw_instead_of_cached_bytes(self):
        out, root = self.call(fault='fresh'); self.assertNotIn('error', out, out.get('error'))
        self.assertEqual(out['fresh']['native']['raw'], out['snapshot']['native']['raw']+'\n')
        self.assertNotEqual(out['fresh']['native']['sha256'], out['snapshot']['native']['sha256'])

    def test_original_probe_callback_preserves_raw_before_JSON_decode_failure(self):
        out, root = self.call(action='probe', fault='json')
        self.assertIn('error', out); self.assertNotIn('native', out)
        self.assertEqual((root/'captured.raw').read_bytes(), b'BROKEN_NATIVE_JSON')
        self.assertEqual(out['captured']['native']['raw'], 'BROKEN_NATIVE_JSON')
        self.assertEqual(len(out['db']['jobs']), 1)

    def test_postcallback_parent_config_or_resource_drift_preserves_capture_without_acceptance_or_retry(self):
        for fault in ('parent', 'config', 'resource'):
            with self.subTest(fault=fault):
                out, root = self.call(action='probe', fault=fault)
                self.assertIn('error', out); self.assertNotIn('native', out)
                self.assertEqual((root/'captured.raw').read_text(), out['captured']['native']['raw'])
                self.assertEqual(len(out['db']['jobs']), 1)

    def test_probe_returns_exact_original_snapshot_bytes_after_capture_and_source_checks(self):
        out, root = self.call(action='probe'); self.assertNotIn('error', out, out.get('error'))
        self.assertEqual(out['native'], json.loads((root/'captured.raw').read_text()))
        self.assertEqual(out['captured']['job']['id'], out['parent']['dpi_job'])
        self.assertEqual(out['captured']['job']['request_id'], out['parent']['dpi_request'])
        self.assertEqual(len(out['db']['jobs']), 1)

    def test_source_read_keeps_the_published_index_inode_it_reports(self):
        out, root = self.call(); self.assertNotIn('error', out, out.get('error'))
        index = out['snapshot']['index']; stat = (root/'dpi/jobs.json').stat()
        self.assertEqual((stat.st_dev, stat.st_ino), (index['metadata']['dev'], index['metadata']['ino']))
        self.assertEqual((root/'dpi/jobs.json').read_text(), index['raw'])


if __name__ == '__main__':
    unittest.main()
