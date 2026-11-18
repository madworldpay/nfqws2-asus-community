"""Saved-config preview uses the existing writer mutex and guarded resource reader."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC
import test_strategy_supplement as data

ENGINE = os.environ.get('NFQWS_TEST_ENGINE_DIR')
ARTIFACTS = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')


@unittest.skipUnless(ENGINE, 'Requires pinned original Lua fixture bytes')
class SupplementSavedPreviewTests(unittest.TestCase):
    def setUp(self):
        if ARTIFACTS:
            self.temp = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=ARTIFACTS))
        else:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.temp = Path(tmp.name)
        self.root = self.temp/'source'
        self.root.mkdir(mode=0o755)
        for name in ('lists', 'lua', 'blobs'):
            (self.root/name).mkdir(mode=0o755)
        for path, expected in list(data.STOCK.items())[:2]:
            raw = (Path(ENGINE)/'lua'/Path(path).name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            (self.root/'lua'/Path(path).name).write_bytes(raw)
        for name, raw in {'user.list': b'base.example\n', 'auto.list': b'learned.example\n',
                          'exclude.list': b'private-excluded.example\n'}.items():
            (self.root/'lists'/name).write_bytes(raw)
        self.config = self.root/'nfqws2.conf'
        self.config.write_text(data.BASE)
        self.store = self.temp/'import'
        self.store.mkdir(mode=0o700)
        self.count = 0

    def call(self, cmd='importsupplementstate', checkpoint='observe', extra=None, **post):
        request = {'cmd': cmd, 'csrf_token': 'fixture-csrf', **post, **(extra or {})}
        code = r'''require $argv[1].'/import-api.php';
        if(!method_exists('AsusImportTransaction','supplementState')||!method_exists('AsusImportTransaction','supplementPreview')){echo json_encode(['missing_api'=>true]);exit;}
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$events=[];
        $store=new AsusImportStore($argv[2].'/import',(int)$argv[3]);
        $dns=new AsusSmartDnsStore($argv[2].'/dns',(int)$argv[3]);
        $deps=['checkpoint'=>function($phase)use(&$events,$argv,$d){
            if($phase!=='supplement_read')return;
            $f=fopen($argv[2].'/import/writer.lock','rb');$rival=flock($f,LOCK_EX|LOCK_NB);
            $events[]=['phase'=>$phase,'rival_acquired'=>$rival];if($rival)flock($f,LOCK_UN);fclose($f);
            if($d['checkpoint']==='change_config')file_put_contents($argv[2].'/source/nfqws2.conf',"# FOREIGN EDIT\n".file_get_contents($argv[2].'/source/nfqws2.conf'));
        }];
        $tx=new AsusImportTransaction($store,$dns,$argv[2].'/source',$argv[2].'/source/nfqws2.conf',(int)$argv[3],$deps);
        $api=new AsusImportApi($tx,static function(){throw new RuntimeException('UNEXPECTED_MUTATION_LEASE');},$dns);
        try{$value=$api->handle($d['post'],str_repeat('a',64),1700000000);$out=['result'=>$value];}
        catch(Throwable $e){$out=['error'=>AsusImportApi::error($e),'raw_error'=>$e->getMessage()];}
        echo json_encode($out+['events'=>$events],JSON_THROW_ON_ERROR);'''
        self.count += 1
        prefix = self.temp/str(self.count)
        payload = json.dumps({'post': request, 'checkpoint': checkpoint})
        prefix.with_suffix('.php').write_text(code)
        prefix.with_suffix('.request.json').write_text(payload)
        run = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(self.temp), str(os.getuid())],
                             input=payload, text=True, capture_output=True, timeout=25)
        prefix.with_suffix('.stdout').write_text(run.stdout)
        prefix.with_suffix('.stderr').write_text(run.stderr)
        self.assertEqual((run.returncode, run.stderr), (0, ''), run.stdout+run.stderr)
        out = json.loads(run.stdout)
        self.assertNotIn('missing_api', out, 'missing saved-config supplement preview API')
        return out

    def good(self, **kwargs):
        out = self.call(**kwargs)
        self.assertNotIn('error', out, out)
        return out

    def preview(self, binding, **kwargs):
        return self.call('importsupplementpreview', recipe=json.dumps(data.RECIPE),
                         domains=json.dumps(['target.example']), **binding, **kwargs)

    def test_state_digest_comes_from_actual_saved_config_and_resources(self):
        out = self.good()
        self.assertEqual(out['result']['binding']['config_sha256'], hashlib.sha256(self.config.read_bytes()).hexdigest())
        resources = {'/opt/etc/nfqws2/'+str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for kind in ('lists', 'lua') for p in sorted((self.root/kind).iterdir())}
        self.assertEqual(out['result']['binding']['resources_sha256'], data.resource_sha(resources))
        self.assertTrue(out['result']['saved_config_bound'])

    def test_preview_is_prepared_from_saved_bytes_under_the_same_actual_mutex(self):
        state = self.good()
        out = self.preview(state['result']['binding'])
        self.assertNotIn('error', out, out)
        result = out['result']
        self.assertEqual(result['binding'], state['result']['binding'])
        self.assertTrue(result['saved_config_bound'])
        self.assertTrue(result['proposal']['resource_inventory_bound'])
        self.assertIn('--hostlist-domains=target.example', result['proposal']['preview']['candidate_config'])
        self.assertEqual(out['events'], [{'phase': 'supplement_read', 'rival_acquired': False}])
        with (self.store/'writer.lock').open('rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_config_drift_between_state_and_preview_refuses_without_rollback(self):
        binding = self.good()['result']['binding']
        self.config.write_text(data.BASE+'# OWNER EDIT\n')
        out = self.preview(binding)
        self.assertIn('error', out)
        self.assertEqual(self.config.read_text(), data.BASE+'# OWNER EDIT\n')

    def test_AUTO_drift_between_state_and_preview_refuses(self):
        binding = self.good()['result']['binding']
        (self.root/'lists/auto.list').write_bytes(b'changed.example\n')
        self.assertIn('error', self.preview(binding))

    def test_config_change_after_resource_IO_refuses_and_preserves_foreign_edit(self):
        binding = self.good()['result']['binding']
        out = self.preview(binding, checkpoint='change_config')
        self.assertEqual(out['error'], 'source_changed')
        self.assertEqual(self.config.read_text(), '# FOREIGN EDIT\n'+data.BASE)
        with (self.store/'writer.lock').open('rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_existing_rival_writer_blocks_read_without_recover_or_mutation(self):
        lock = self.store/'writer.lock'
        lock.write_bytes(b'')
        lock.chmod(0o600)
        with lock.open('rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB)
            out = self.call()
        self.assertEqual(out['error'], 'busy')
        self.assertEqual(out['events'], [])
        self.assertEqual(self.config.read_text(), data.BASE)

    def test_saved_config_symlink_cannot_select_another_source(self):
        target = self.temp/'foreign.conf'
        self.config.rename(target)
        self.config.symlink_to(target)
        self.assertIn('error', self.call())
        self.assertTrue(self.config.is_symlink())
        self.assertEqual(target.read_text(), data.BASE)

    def test_unfinished_transaction_remains_untouched_and_blocks_preview(self):
        journal = {'schema_version': 1, 'current': {'id': 'b'*32, 'state': 'committing',
                   'request_digest': 'c'*64, 'before': 'd'*64, 'after': 'e'*64, 'files': []}, 'history': []}
        path = self.store/'state.json'
        path.write_text(json.dumps(journal))
        path.chmod(0o600)
        before = path.read_bytes()
        out = self.call()
        self.assertEqual(out['error'], 'busy')
        self.assertEqual(path.read_bytes(), before)

    def test_request_cannot_supply_config_resource_paths_kit_or_unknown_fields(self):
        for field in ('current', 'root', 'resources', 'proposal', 'can_apply'):
            with self.subTest(field=field):
                self.assertEqual(self.call(extra={field: 'foreign'})['error'], 'invalid_request')

    def test_success_changes_no_config_resources_DNS_or_transaction_journal(self):
        def pins():
            return {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), tuple(getattr(p.stat(), x) for x in (
                'st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns')))
                for p in self.root.rglob('*') if p.is_file()}
        before = pins()
        binding = self.good()['result']['binding']
        out = self.preview(binding)
        self.assertNotIn('error', out, out)
        self.assertEqual(pins(), before)
        self.assertFalse((self.store/'state.json').exists())
        self.assertFalse((self.temp/'dns').exists())
        self.assertEqual(sorted(p.name for p in self.store.iterdir()), ['writer.lock'])
        for key in ('can_apply', 'can_export', 'combined_verified', 'actual_device_calls'):
            self.assertIs(out['result'][key], False)
        self.assertNotIn('proof', out['result'])


if __name__ == '__main__':
    unittest.main()
