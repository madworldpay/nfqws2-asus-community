"""Saved supplement -> exact CUSTOM-only LOCAL import plan, never Apply.

The source package profile is actual source fallback, not a device observation.
"""
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


class SupplementLocalPlanTests(unittest.TestCase):
    def setUp(self):
        artifacts = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifacts:
            self.temp = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=artifacts))
        else:
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            self.temp = Path(temp.name)
        engine = Path(os.environ['NFQWS_TEST_ENGINE_DIR'])
        self.root = self.temp/'source'; self.root.mkdir(mode=0o755)
        for kind in ('lists', 'lua', 'blobs'):
            (self.root/kind).mkdir(mode=0o755)
        for path, sha in list(STOCK.items())[:2]:
            raw = (engine/'lua'/Path(path).name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)
            (self.root/'lua'/Path(path).name).write_bytes(raw)
        for name, raw in {'user.list': b'base.example\n', 'auto.list': b'learned.example\n',
                          'exclude.list': b'excluded.example\n'}.items():
            (self.root/'lists'/name).write_bytes(raw)
        self.config = self.root/'nfqws2.conf'; self.config.write_text(BASE); self.config.chmod(0o640)
        self.journal = self.temp/'journal'; self.journal.mkdir(mode=0o700)

    def source_pins(self):
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid',
                  'st_size', 'st_mtime_ns', 'st_ctime_ns')
        return {str(p.relative_to(self.root)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                    'metadata': {k: getattr(p.stat(), k) for k in fields}}
                for p in self.root.rglob('*') if p.is_file()}

    def call(self, fault='', with_plan=True):
        code = r'''require $argv[1].'/import-transaction.php';require_once $argv[1].'/strategy-supplement.php';
        $method=new ReflectionMethod('AsusImportTransaction','supplementPortablePreview');
        if($method->getNumberOfParameters()<4){echo json_encode(['missing_api'=>true]);exit;}
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$r=$argv[2];$uid=(int)$argv[3];$events=[];
        $store=new AsusImportStore($r.'/journal',$uid);$dns=new AsusSmartDnsStore($r.'/dns',$uid);
        $foreignDNS=['schema_version'=>1,'upstreams'=>[['id'=>'localmodel','label'=>'LOCAL MODEL ONLY','protocol'=>'udp',
          'address'=>'192.0.2.53','port'=>53,'tls_name'=>'','url'=>'','bootstrap'=>[],'default'=>true,'domains'=>[]]],'records'=>[]];
        $deps=['checkpoint'=>function($phase)use($store,$dns,$foreignDNS,$d,&$events){
          if($phase!=='supplement_read')return;
          $f=fopen($store->directory().'/writer.lock','rb');$rival=flock($f,LOCK_EX|LOCK_NB);
          if($rival)flock($f,LOCK_UN);fclose($f);$events[]=['phase'=>$phase,'rival_acquired'=>$rival];
          if($d['fault']==='dns')$dns->replaceDraft($foreignDNS,null);
        }];
        $tx=new AsusImportTransaction($store,$dns,$r.'/source',$r.'/source/nfqws2.conf',$uid,$deps);
        $inventory=NfqwsStrategySupplement::inventory(new AsusShareResources($r.'/source',$uid));
        $binding=['config_sha256'=>hash_file('sha256',$r.'/source/nfqws2.conf'),'resources_sha256'=>$inventory['resources_sha256']];
        try{$result=$tx->supplementPortablePreview($d['recipe'],['target.example'],$binding,$d['with_plan']);$out=['result'=>$result];}
        catch(Throwable $e){$out=['error'=>$e->getMessage()];}
        echo json_encode($out+['events'=>$events,'draft'=>$dns->draft(),'source_profile'=>NfqwsPlatform::current()],JSON_THROW_ON_ERROR);'''
        request = json.dumps({'recipe': RECIPE, 'fault': fault, 'with_plan': with_plan}).encode()
        (self.temp/'php-r.private').write_text(code)
        (self.temp/'request.private.json').write_bytes(request)
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(self.temp), str(os.getuid())],
                                input=request, capture_output=True, timeout=30)
        (self.temp/'stdout.private').write_bytes(result.stdout)
        (self.temp/'stderr.private').write_bytes(result.stderr)
        self.assertEqual((result.returncode, result.stderr), (0, b''), result.stdout.decode()+result.stderr.decode())
        out = json.loads(result.stdout)
        self.assertFalse(out.get('missing_api'), 'missing saved portable LOCAL post-plan compiler input')
        return out

    def success(self):
        before = self.source_pins(); out = self.call(); self.assertNotIn('error', out, out)
        self.assertEqual(self.source_pins(), before)
        result = out['result']; plan = result['local_plan']; binding = result['local_plan_binding']
        self.assertTrue(plan['ready']); self.assertEqual(plan['problems'], [])
        self.assertEqual(plan['files'], []); self.assertEqual(plan['draft'], None)
        self.assertEqual(plan['config'], result['proposal']['preview']['candidate_config'])
        self.assertEqual([c['key'] for c in plan['changes']], ['NFQWS_ARGS_CUSTOM'])
        self.assertEqual(binding['postplan_config_sha256'], hashlib.sha256(plan['config'].encode()).hexdigest())
        self.assertEqual(binding['original_config_sha256'], hashlib.sha256(self.config.read_bytes()).hexdigest())
        self.assertEqual(binding['plan_sha256'], plan['digest'])
        self.assertEqual(binding['plan_input_sha256'], plan['input_sha256'])
        self.assertEqual(binding['resource_kit_sha256'], result['proposal']['resource_kit_sha256'])
        for key in ('backup_ready', 'can_apply', 'can_export', 'combined_verified', 'actual_device_calls'):
            self.assertFalse(result[key])
        self.assertEqual(out['events'], [{'phase': 'supplement_read', 'rival_acquired': False}])
        self.assertFalse((self.journal/'state.json').exists())
        self.assertEqual(sorted(p.name for p in self.journal.iterdir()), ['writer.lock'])
        self.assertFalse((self.temp/'dns').exists())
        with (self.journal/'writer.lock').open('rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB)
        return out

    def test_exact_CUSTOM_only_plan_is_bound_under_the_saved_writer_without_mutation(self):
        out = self.success()
        self.assertEqual(out['result']['local_plan_binding']['resources_sha256'], out['result']['binding']['resources_sha256'])
        self.assertEqual(out['result']['local_plan_binding']['draft_sha256'], None)
        self.assertEqual(out['result']['local_plan']['fingerprints']['config'], out['result']['binding']['config_sha256'])

    def test_owner_flat_blob_and_base_arguments_keep_exact_original_paths(self):
        blob = b'\x00LOCAL_FLAT_BLOB\xff'
        (self.root/'blobs/custom.bin').write_bytes(blob)
        current = BASE.replace(' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua"',
            ' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua --blob=owned:@/opt/etc/nfqws2/blobs/custom.bin"')
        current = current.replace('--lua-desync=multidisorder:pos=2', '--lua-desync=fake:blob=owned')
        self.config.write_text(current)
        out = self.success(); plan = out['result']['local_plan']
        self.assertIn('--blob=owned:@/opt/etc/nfqws2/blobs/custom.bin', plan['config'])
        self.assertNotIn('/blobs/imported/', plan['config'])
        kit = out['result']['proposal']['resource_kit']['files']
        self.assertEqual(len(kit), 6)
        actual = next(f for f in kit if f['path'].endswith('/blobs/custom.bin'))
        self.assertEqual(base64.b64decode(actual['data_base64']), blob)

    def test_existing_imported_blob_path_is_preserved_without_republication(self):
        blob = b'LOCAL_IMPORTED_BLOB'
        folder = self.root/'blobs/imported'; folder.mkdir(mode=0o755)
        name = hashlib.sha256(blob).hexdigest()+'.bin'; (folder/name).write_bytes(blob)
        current = BASE.replace(' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua"',
            ' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua --blob=owned:@/opt/etc/nfqws2/blobs/imported/'+name+'"')
        current = current.replace('--lua-desync=multidisorder:pos=2', '--lua-desync=fake:blob=owned')
        self.config.write_text(current)
        out = self.success()
        self.assertIn('/blobs/imported/'+name, out['result']['local_plan']['config'])

    def test_DNS_draft_changed_after_compilation_refuses_and_preserves_foreign_draft(self):
        before = self.source_pins(); out = self.call(fault='dns')
        self.assertEqual(out.get('error'), 'source_changed', out)
        self.assertNotIn('result', out); self.assertEqual(self.source_pins(), before)
        self.assertEqual(out['draft']['upstreams'][0]['address'], '192.0.2.53')
        self.assertFalse((self.journal/'state.json').exists())

    def test_any_native_operand_rebind_refuses_instead_of_transplanting_source_digest(self):
        self.config.write_text(BASE.replace('/opt/etc/nfqws2/', '/etc/nfqws2/'))
        before = self.source_pins(); out = self.call()
        self.assertIn(out.get('error'), ('supplement_plan_incompatible', 'supplement_incompatible'), out)
        self.assertNotIn('result', out); self.assertEqual(self.source_pins(), before)
        self.assertFalse((self.journal/'state.json').exists())

    def test_rival_writer_refuses_before_local_plan_or_serialization_checkpoint(self):
        lock = self.journal/'writer.lock'; lock.write_bytes(b''); lock.chmod(0o600)
        with lock.open('rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB); out = self.call()
        self.assertEqual(out.get('error'), 'busy', out)
        self.assertEqual(out['events'], []); self.assertNotIn('result', out)
        self.assertFalse((self.journal/'state.json').exists())

    def test_default_internal_portable_method_keeps_its_existing_output_contract(self):
        out = self.call(with_plan=False)
        self.assertNotIn('error', out)
        self.assertNotIn('local_plan', out['result']); self.assertNotIn('local_plan_binding', out['result'])
        self.assertFalse(out['result']['can_apply']); self.assertFalse(out['result']['can_export'])
        self.assertEqual(out['result']['comparison_binding']['combined_config_sha256'],
                         out['result']['proposal']['preview']['candidate_sha256'])


if __name__ == '__main__':
    unittest.main()
