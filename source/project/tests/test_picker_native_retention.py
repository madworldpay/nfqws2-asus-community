"""Bounded LOCAL raw retention; source callbacks/ROOT admission remain unwired.

Real files, physical zero allocation, fsync, readback, DPI store and pruning.
The engine body and guard are explicit doubles. No success/media validator.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC
from test_strategy_supplement import BASE


class PickerNativeRetentionTests(unittest.TestCase):
    def call(self, fault='', count=1):
        artifacts = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifacts:
            root = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=artifacts))
        else:
            tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); root = Path(tmp.name)
        code = r'''require $argv[1].'/strategy-picker-core.php';require $argv[1].'/dpi-jobs.php';
        require $argv[1].'/update-store.php';
        $file=$argv[1].'/strategy-picker-native-capture.php';
        if(!is_file($file)){echo json_encode(['missing_api'=>true]);exit;}require $file;
        final class RetentionTerminalDouble {public function idle(callable $fn):mixed{return $fn();}}
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
        $root=$argv[2];$uid=(int)$argv[3];$store=new NfqwsStrategyPickerState($root.'/picker',$uid);
        file_put_contents($root.'/config',$d['base']);chmod($root.'/config',0640);
        $config=new NfqwsStrategyPickerConfig($store,$root.'/config',$uid);$j=$config->snapshot(false);
        $j=array_replace($j,['state'=>'running','phase'=>'measuring_1','request_id'=>str_repeat('b',32),
          'resources_sha256'=>str_repeat('e',64),'deadline'=>AsusUpdateStore::uptime()+120]);if($d['fault']==='unlimited'){$j['deadline']=null;$j['started_uptime']=max(0,AsusUpdateStore::uptime()-172800);}$store->write($j);
        $guardCalls=0;$guardFailAt=0;$guard=function()use(&$guardCalls,&$guardFailAt):void{
          ++$guardCalls;if($guardCalls===$guardFailAt)throw new RuntimeException('guard_lost');};
        $retainer=new NfqwsStrategyPickerNativeCapture($store,$guard,$uid);
        $s=new AsusDpiStore($root.'/dpi',$uid);$launches=[];
        $body=$d['fault']==='max_native'?str_repeat('x',1048576):'{malformed native body';
        $jobs=new AsusDpiJobs($s,['installed'=>fn()=>true,'available'=>fn()=>['available'=>true],
          'terminal_gate'=>new RetentionTerminalDouble(),'launch'=>function($id,$kind)use($s,$root,$body,&$launches){
            $before=json_decode(file_get_contents($root.'/dpi/jobs.json'),true);$row=$before['jobs'][$id];
            $launches[]=['id'=>$id,'request'=>$row['request_id']];
            $s->update($id,['state'=>'running']);$s->update($id,['state'=>'completed','native'=>$body]);}]);
        $out=['reserved'=>[],'captures'=>[],'sources'=>[],'before_input'=>[]];
        try{for($i=0;$i<$d['count'];++$i){
          $request=sprintf('12345678-1234-4123-8123-%012d',$i+1);
          $input=['mode'=>'picker-trial-native-input-v1','parent_id'=>$j['id'],'parent_request_id'=>$j['request_id'],
            'parent_boot'=>$j['boot'],'profile_id'=>str_repeat('c',32),'source'=>'current','recipe'=>null,
            'config_sha256'=>$j['current'],'resource_fingerprint_sha256'=>$j['resources_sha256'],
            'resource_binding_scope'=>'existing_fingerprint_excludes_mutable_AUTO','warmup'=>$i%3===0,
            'repeat'=>$i%3===0?null:$i%3];
          $state=$store->read();$state['dpi_request']=$request;$store->write($state);
          if($d['fault']==='expired'){$state['deadline']=AsusUpdateStore::uptime()-1;$store->write($state);}
          if($d['fault']==='guard_after_reserve')$guardFailAt=$guardCalls+2;
          $retainer->reserve($request,$input);$out['reserved'][]=$request;
          if($d['fault']==='reserve_only')break;
          $before=is_file($root.'/dpi/jobs.json')?json_decode(file_get_contents($root.'/dpi/jobs.json'),true):['jobs'=>[]];
          $out['before_input'][]=count($before['jobs']);
          if($d['fault']==='duplicate')$retainer->reserve($request,$input);
          if($d['fault']==='slot_changed')file_put_contents($root.'/picker/native-'.$j['id'].'-'.$request.'.slot','FOREIGN');
          if(in_array($d['fault'],['symlink','hardlink'],true)){
            $p=$root.'/picker/native-'.$j['id'].'-'.$request.'.slot';
            if($d['fault']==='hardlink')link($p,$root.'/foreign-hardlink');
            else{rename($p,$root.'/original-slot');file_put_contents($root.'/foreign','FOREIGN');symlink($root.'/foreign',$p);}}
          $job=$jobs->startRun($request,[2],[],['config'=>['MAX_CONCURRENT'=>2]]);
          $state=$store->read();$state['dpi_job']=$job['id'];$store->write($state);
          $snapshot=$jobs->nativeSnapshot($job['id'],$request);
          file_put_contents($root.'/source-'.$i.'.json',json_encode($snapshot,JSON_THROW_ON_ERROR));
          $out['sources'][]=['file'=>'source-'.$i.'.json','native_sha256'=>$snapshot['native']['sha256']];
          if($d['fault']==='hash')$snapshot['native']['sha256']=str_repeat('0',64);
          if($d['fault']==='input')$input['source']='synthesis';
          if($d['fault']==='guard_after_capture')$guardFailAt=$guardCalls+2;
          $out['captures'][]=$retainer->capture($snapshot,$input);
          if($d['fault']==='capture_twice')$retainer->capture($snapshot,$input);
        }}catch(Throwable $e){$out['error']=$e->getMessage();}
        $db=is_file($root.'/dpi/jobs.json')?json_decode(file_get_contents($root.'/dpi/jobs.json'),true):['jobs'=>[]];
        echo json_encode($out+['launches'=>$launches,'db'=>$db,'parent'=>$store->read(),'guard_calls'=>$guardCalls],JSON_THROW_ON_ERROR);'''
        request = json.dumps({'base': BASE, 'fault': fault, 'count': count}).encode()
        (root/'php-r.private').write_text(code); (root/'request.private.json').write_bytes(request)
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(root), str(os.getuid())],
                                input=request, capture_output=True, timeout=30)
        (root/'stdout.private').write_bytes(result.stdout); (root/'stderr.private').write_bytes(result.stderr)
        self.assertEqual((result.returncode, result.stderr), (0, b''), result.stdout.decode()+result.stderr.decode())
        out = json.loads(result.stdout)
        self.assertFalse(out.get('missing_api'), 'missing bounded native capture reservation/retention')
        return out, root

    def assert_capture(self, out, root):
        for ref, source in zip(out['captures'], out['sources']):
            self.assertEqual(ref['state'], 'captured_unaccepted')
            self.assertFalse(ref['accepted'])
            manifest = root/'picker'/ref['name']
            raw = manifest.read_bytes(); self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['sha256'])
            value = json.loads(raw); slot = root/'picker'/value['slot']['name']; data = slot.read_bytes()
            self.assertEqual(len(data), 1310720)
            self.assertEqual(hashlib.sha256(data).hexdigest(), value['slot']['sha256'])
            snapshot = json.loads((root/source['file']).read_bytes())
            offset = 0
            for kind in ['index', 'options', 'native']:
                artifact = value['artifacts'][kind]; expected = snapshot[kind]['raw'].encode()
                self.assertEqual(artifact['offset'], offset)
                self.assertEqual(data[offset:offset+artifact['bytes']], expected)
                self.assertEqual(artifact['sha256'], hashlib.sha256(expected).hexdigest())
                self.assertEqual(artifact['source_metadata'], snapshot[kind]['metadata'])
                offset += len(expected)
            self.assertEqual(data[offset:], bytes(len(data)-offset))

    def test_six_contemporaneous_sources_survive_actual_DPI_last3(self):
        out, root = self.call(count=6)
        self.assertNotIn('error', out); self.assertEqual(len(out['captures']), 6)
        self.assertEqual(len(out['db']['jobs']), 3)
        self.assertEqual(out['before_input'][:3], [0, 1, 2]); self.assert_capture(out, root)
        self.assertEqual(len(list((root/'picker').glob('*.intent.json'))), 6)
        for ref in out['captures'][:3]:
            self.assertNotIn(json.loads((root/'picker'/ref['name']).read_text())['native_job_id'], out['db']['jobs'])

    def test_full_1MiB_malformed_raw_retained_without_semantic_acceptance(self):
        out, root = self.call('max_native')
        self.assertNotIn('error', out); self.assert_capture(out, root)
        self.assertEqual(len(json.loads((root/'source-0.json').read_text())['native']['raw']), 1048576)

    def test_seventh_reservation_refused_before_seventh_input(self):
        out, root = self.call(count=7)
        self.assertEqual(out.get('error'), 'output_limit'); self.assertEqual(len(out['launches']), 6)
        self.assertEqual(len(out['captures']), 6); self.assert_capture(out, root)

    def test_duplicate_and_recapture_preserve_original_bytes(self):
        for fault, launches, captures in [('duplicate', 0, 0), ('capture_twice', 1, 1)]:
            with self.subTest(fault=fault):
                out, root = self.call(fault)
                self.assertEqual(out.get('error'), 'request_conflict')
                self.assertEqual(len(out['launches']), launches); self.assertEqual(len(out['captures']), captures)
                self.assert_capture(out, root)

    def test_guard_loss_after_physical_reservation_issues_no_input(self):
        out, root = self.call('guard_after_reserve')
        self.assertEqual(out.get('error'), 'guard_lost'); self.assertEqual(out['launches'], [])
        self.assertEqual(len(list((root/'picker').glob('*.slot'))), 1)
        slot = next((root/'picker').glob('*.slot'))
        self.assertEqual(slot.read_bytes(), bytes(1310720))
        self.assertGreaterEqual(slot.stat().st_blocks*512, 1310720)

    def test_capture_metadata_storage_also_allocated_before_possible_input(self):
        out, root = self.call('reserve_only')
        self.assertNotIn('error', out); self.assertEqual(out['launches'], [])
        manifests = list((root/'picker').glob('*.capture.json'))
        self.assertEqual(len(manifests), 1, 'capture metadata space must be reserved too')
        raw = manifests[0].read_bytes(); value = json.loads(raw)
        self.assertEqual(value['state'], 'capture_pending'); self.assertFalse(value['accepted'])
        self.assertEqual(len(raw), 32768); self.assertGreaterEqual(manifests[0].stat().st_blocks*512, 32768)

    def test_postcapture_guard_loss_keeps_unaccepted_original_buffers(self):
        out, root = self.call('guard_after_capture')
        self.assertEqual(out.get('error'), 'guard_lost'); self.assertEqual(out['captures'], [])
        manifests = list((root/'picker').glob('*.capture.json')); self.assertEqual(len(manifests), 1)
        raw = manifests[0].read_bytes()
        ref = {'name': manifests[0].name, 'sha256': hashlib.sha256(raw).hexdigest(),
               'state': 'captured_unaccepted', 'accepted': False}
        out['captures'] = [ref]; self.assert_capture(out, root)

    def test_tampered_binding_hash_slot_and_links_refused_preserving_unknown(self):
        for fault in ['hash', 'input', 'slot_changed', 'symlink', 'hardlink']:
            with self.subTest(fault=fault):
                out, root = self.call(fault)
                self.assertIn(out.get('error'), ['source_changed', 'storage_unavailable', 'unsafe_panel_file'])
                self.assertEqual(out['captures'], []); self.assertEqual(len(out['launches']), 1)
                self.assertEqual([json.loads(p.read_text())['state'] for p in (root/'picker').glob('*.capture.json')], ['capture_pending'])
                if fault == 'symlink': self.assertEqual((root/'foreign').read_bytes(), b'FOREIGN')
                if fault == 'slot_changed': self.assertEqual(next((root/'picker').glob('*.slot')).read_bytes(), b'FOREIGN')
                if fault == 'hardlink': self.assertEqual((root/'foreign-hardlink').stat().st_nlink, 2)

    def test_explicit_unlimited_parent_keeps_original_native_capture_binding(self):
        out, root = self.call('unlimited')
        self.assertNotIn('error',out)
        self.assertEqual(len(out['reserved']),1)
        self.assertEqual(len(out['captures']),1)
        self.assertEqual(len(out['launches']),1)
        self.assertIsNone(out['parent']['deadline'])

    def test_original_deadline_refuses_without_reservation_or_input(self):
        out, root = self.call('expired')
        self.assertEqual(out.get('error'), 'timed_out'); self.assertEqual(out['launches'], [])
        self.assertEqual(list((root/'picker').glob('native-*')), [])


if __name__ == '__main__':
    unittest.main()
