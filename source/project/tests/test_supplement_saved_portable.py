"""Internal portable preparation reads saved bytes under the import writer lock."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC
from test_strategy_supplement import BASE, RECIPE, STOCK


class SupplementSavedPortableTests(unittest.TestCase):
    def setUp(self):
        engine = os.environ.get('NFQWS_TEST_ENGINE_DIR')
        self.assertTrue(engine, 'Provide pinned original Lua fixture bytes')
        artifacts = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifacts:
            self.temp = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=artifacts))
        else:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.temp = Path(tmp.name)
        self.root = self.temp/'source'
        self.root.mkdir(mode=0o755)
        for kind in ('lists', 'lua', 'blobs'):
            (self.root/kind).mkdir(mode=0o755)
        for path, expected in list(STOCK.items())[:2]:
            raw = (Path(engine)/'lua'/Path(path).name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            (self.root/'lua'/Path(path).name).write_bytes(raw)
        for name, raw in {'user.list': b'base.example\n', 'auto.list': b'learned.example\n',
                          'exclude.list': b'excluded.example\n'}.items():
            (self.root/'lists'/name).write_bytes(raw)
        self.config = self.root/'nfqws2.conf'
        self.config.write_text(BASE)
        self.store = self.temp/'import'
        self.store.mkdir(mode=0o700)
        self.count = 0

    def call(self, action='portable', fault='', binding=None):
        code = r'''require $argv[1].'/import-transaction.php';
        if(!method_exists('AsusImportTransaction','supplementPortablePreview')){echo json_encode(['missing_api'=>true]);exit;}
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$events=[];
        $store=new AsusImportStore($argv[2].'/import',(int)$argv[3]);
        $dns=new AsusSmartDnsStore($argv[2].'/dns',(int)$argv[3]);
        $deps=['checkpoint'=>function($phase)use(&$events,$argv,$d,$store){
          if($phase!=='supplement_read')return;
          $f=fopen($argv[2].'/import/writer.lock','rb');$rival=flock($f,LOCK_EX|LOCK_NB);
          $events[]=['phase'=>$phase,'rival_acquired'=>$rival];if($rival)flock($f,LOCK_UN);fclose($f);
          if($d['fault']==='AUTO')file_put_contents($argv[2].'/source/lists/auto.list',"FOREIGN_AUTO\n");
          if($d['fault']==='config')file_put_contents($argv[2].'/source/nfqws2.conf',"# FOREIGN_CONFIG\n".file_get_contents($argv[2].'/source/nfqws2.conf'));
          if($d['fault']==='state')$store->save(['schema_version'=>1,'current'=>null,'history'=>[['id'=>str_repeat('b',32),'state'=>'committed','request_digest'=>str_repeat('c',64),'before'=>str_repeat('d',64),'after'=>str_repeat('e',64),'files'=>[]]]]);
        }];
        $tx=new AsusImportTransaction($store,$dns,$argv[2].'/source',$argv[2].'/source/nfqws2.conf',(int)$argv[3],$deps);
        try{if($d['action']==='state')$out=$tx->supplementState();
          else{$binding=$d['binding'];if($binding===null){$view=NfqwsStrategySupplement::inventory(new AsusShareResources($argv[2].'/source',(int)$argv[3]));
            $binding=['config_sha256'=>hash_file('sha256',$argv[2].'/source/nfqws2.conf'),'resources_sha256'=>$view['resources_sha256']];}
            $out=$tx->supplementPortablePreview($d['recipe'],$d['domains'],$binding);}
          $result=['result'=>$out];
        }catch(Throwable $e){$result=['error'=>$e->getMessage()];}
        echo json_encode($result+['events'=>$events],JSON_THROW_ON_ERROR);'''
        # NfqwsStrategySupplement is loaded by the actual transaction method;
        # the harness also needs it to obtain a controlled initial UI binding.
        code = code.replace("$d=json_decode", "require_once $argv[1].'/strategy-supplement.php';\n        $d=json_decode", 1)
        request = json.dumps({'action': action, 'fault': fault, 'binding': binding,
                              'recipe': RECIPE, 'domains': ['target.example']})
        self.count += 1
        prefix = self.temp/str(self.count)
        prefix.with_suffix('.php').write_text(code)
        prefix.with_suffix('.request.json').write_text(request)
        run = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(self.temp), str(os.getuid())],
                             input=request, text=True, capture_output=True, timeout=25)
        prefix.with_suffix('.stdout').write_text(run.stdout)
        prefix.with_suffix('.stderr').write_text(run.stderr)
        self.assertEqual((run.returncode, run.stderr), (0, ''), run.stdout+run.stderr)
        out = json.loads(run.stdout)
        self.assertNotIn('missing_api', out, 'missing saved portable transaction method')
        return out

    def good(self, **kwargs):
        out = self.call(**kwargs)
        self.assertNotIn('error', out, out)
        return out

    def unlocked(self):
        with (self.store/'writer.lock').open('rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_saved_source_portable_and_comparison_hashes_share_one_actual_mutex(self):
        out = self.good()
        result = out['result']; proposal = result['proposal']; portable = result['portable']
        binding = result['comparison_binding']
        self.assertEqual(result['mode'], 'supplement-saved-portable-preview-v1')
        self.assertTrue(result['saved_config_bound'])
        self.assertEqual(binding['original_config_sha256'], hashlib.sha256(self.config.read_bytes()).hexdigest())
        self.assertEqual(binding['combined_config_sha256'], proposal['preview']['candidate_sha256'])
        self.assertEqual(binding['resources_sha256'], result['binding']['resources_sha256'])
        self.assertEqual(binding['resource_kit_sha256'], proposal['resource_kit_sha256'])
        self.assertEqual(binding['proposal_sha256'], proposal['proposal_sha256'])
        self.assertEqual(binding['domains'], ['target.example'])
        self.assertEqual(portable['base_sha256'], binding['original_config_sha256'])
        self.assertEqual(portable['proposal_sha256'], binding['proposal_sha256'])
        self.assertEqual(out['events'], [{'phase': 'supplement_read', 'rival_acquired': False}])
        self.unlocked()

    def test_AUTO_changed_after_serialization_refuses_and_preserves_it(self):
        out = self.call(fault='AUTO')
        self.assertIn(out.get('error'), ('source_changed', 'supplement_incompatible'), out)
        self.assertEqual((self.root/'lists/auto.list').read_bytes(), b'FOREIGN_AUTO\n')
        self.assertNotIn('result', out)
        self.unlocked()

    def test_saved_config_changed_after_serialization_refuses_without_restoring_it(self):
        out = self.call(fault='config')
        self.assertEqual(out.get('error'), 'source_changed', out)
        self.assertEqual(self.config.read_text(), '# FOREIGN_CONFIG\n'+BASE)
        self.unlocked()

    def test_transaction_state_changed_after_serialization_refuses_without_recovery(self):
        out = self.call(fault='state')
        self.assertEqual(out.get('error'), 'source_changed', out)
        self.assertEqual(json.loads((self.store/'state.json').read_text())['history'][0]['state'], 'committed')
        self.assertEqual(self.config.read_text(), BASE)
        self.unlocked()

    def test_stale_original_or_resource_binding_is_not_replaced_with_a_fresh_one(self):
        for kind in ('config', 'resources'):
            with self.subTest(kind=kind):
                binding = self.good(action='state')['result']['binding']
                if kind == 'config':
                    self.config.write_text(self.config.read_text()+'# OWNER_EDIT\n')
                else:
                    (self.root/'lists/auto.list').write_bytes(b'OWNER_AUTO\n')
                out = self.call(binding=binding)
                self.assertIn('error', out)
                self.assertNotIn('result', out)
                self.unlocked()

    def test_rival_writer_prevents_any_serialization_callback(self):
        lock = self.store/'writer.lock'; lock.write_bytes(b''); lock.chmod(0o600)
        with lock.open('rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB)
            out = self.call()
        self.assertEqual(out.get('error'), 'busy', out)
        self.assertEqual(out['events'], [])
        self.assertEqual(self.config.read_text(), BASE)
        self.assertFalse((self.store/'state.json').exists())
        self.unlocked()

    def test_pending_journal_blocks_internal_portable_preparation_without_recovery(self):
        path = self.store/'state.json'
        path.write_text(json.dumps({'schema_version': 1, 'current': {'id': 'b'*32,
            'state': 'prepared', 'request_digest': 'c'*64, 'before': 'd'*64,
            'after': 'e'*64, 'files': []}, 'history': []}))
        path.chmod(0o600); before = path.read_bytes()
        out = self.call()
        self.assertEqual(out.get('error'), 'busy', out)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(out['events'], [])
        self.unlocked()

    def test_actual_full_kit_is_readonly_and_grants_no_backup_apply_export_or_native_authority(self):
        def pins():
            return {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), tuple(getattr(p.stat(), k) for k in (
                'st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns')))
                for p in self.root.rglob('*') if p.is_file()}
        before = pins(); result = self.good()['result']
        self.assertEqual(pins(), before)
        self.assertFalse((self.store/'state.json').exists())
        self.assertFalse((self.temp/'dns').exists())
        self.assertEqual(sorted(p.name for p in self.store.iterdir()), ['writer.lock'])
        for key in ('can_apply', 'can_export', 'combined_verified', 'actual_device_calls', 'backup_ready'):
            self.assertIs(result[key], False)
        self.assertFalse(result['portable']['config_source_proved'])
        self.assertFalse(result['proposal']['config_source_proved'])
        wire = json.loads(result['portable']['raw'])
        resources = json.loads(base64.b64decode(wire['files'][1]['data_base64']))
        kit = {f['id']: f for f in result['proposal']['resource_kit']['files']}
        self.assertEqual(len(kit), 5)
        self.assertEqual(resources['package_files'], [])
        for file in resources['files']:
            raw = base64.b64decode(file['data_base64'])
            self.assertEqual(raw, base64.b64decode(kit[file['id']]['data_base64']))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), file['sha256'])
        self.unlocked()


if __name__ == '__main__':
    unittest.main()
