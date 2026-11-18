"""A supplement proposal carries actual guarded resource bytes, without Apply authority."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC
import test_strategy_supplement as preview_data

ENGINE = os.environ.get('NFQWS_TEST_ENGINE_DIR')
ARTIFACTS = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
BLOB = b'\x00\xffsupplement-kit\x00'


@unittest.skipUnless(ENGINE, 'Requires pinned original Lua fixture bytes')
class SupplementResourceKitTests(unittest.TestCase):
    def setUp(self):
        if ARTIFACTS:
            self.temp = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=ARTIFACTS))
        else:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.temp = Path(tmp.name)
        self.root = self.temp/'source'
        self.root.mkdir(mode=0o755)
        for kind in ('lua', 'blobs', 'lists'):
            (self.root/kind).mkdir(mode=0o755)
        for name, expected in list(preview_data.STOCK.items())[:2]:
            raw = (Path(ENGINE)/'lua'/Path(name).name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            (self.root/'lua'/Path(name).name).write_bytes(raw)
        for name, raw in {'lists/user.list': b'base.example\n',
                          'lists/auto.list': b'learned.example\n',
                          'lists/exclude.list': b'private-excluded.example\n',
                          'lists/unrelated.list': b'UNSELECTED_PRIVATE\n',
                          'blobs/custom.bin': BLOB}.items():
            (self.root/name).write_bytes(raw)
        self.current = preview_data.BASE.replace(' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua"',
            ' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua --blob=owned:@/opt/etc/nfqws2/blobs/custom.bin"')
        self.current = self.current.replace('--lua-desync=multidisorder:pos=2', '--lua-desync=fake:blob=owned')
        self.count = 0

    def call(self, action='prepare', **options):
        payload = {'current': self.current, 'recipe': preview_data.RECIPE,
                   'domains': ['target.example'], 'action': action, **options}
        code = r'''$file=$argv[1].'/strategy-supplement.php';
        if(!is_file($file)){echo json_encode(['missing_api'=>true]);exit;}
        require $file;
        if(!class_exists('NfqwsStrategySupplement')){echo json_encode(['missing_api'=>true]);exit;}
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
        try{$store=new AsusShareResources($argv[2],(int)$argv[3],[]);
        $view=NfqwsStrategySupplement::inventory($store);
        $binding=$d['binding']??['config_sha256'=>hash('sha256',$d['current']),'resources_sha256'=>$view['resources_sha256']];
        if($d['action']==='recheck')$out=NfqwsStrategySupplement::recheck($store,$d['current'],$d['proposal']);
        else $out=NfqwsStrategySupplement::prepare($store,$d['current'],$d['recipe'],$d['domains'],$binding);
        echo json_encode(['result'=>$out,'inventory'=>$view],JSON_THROW_ON_ERROR);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        self.count += 1
        prefix = self.temp/str(self.count)
        prefix.with_suffix('.php').write_text(code)
        prefix.with_suffix('.request.json').write_text(json.dumps(payload))
        p = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(self.root), str(os.getuid())],
                           input=json.dumps(payload), text=True, capture_output=True, timeout=25)
        prefix.with_suffix('.stdout').write_text(p.stdout)
        prefix.with_suffix('.stderr').write_text(p.stderr)
        self.assertEqual((p.returncode, p.stderr), (0, ''), p.stdout+p.stderr)
        out = json.loads(p.stdout)
        self.assertNotIn('missing_api', out, 'missing inventory-bound supplement resource-kit API')
        return out

    def good(self, **kwargs):
        out = self.call(**kwargs)
        self.assertNotIn('error', out, out)
        return out

    def test_complete_kit_embeds_actual_lists_Lua_and_binary_blob_only_once(self):
        result = self.good()['result']
        kit = result['resource_kit']
        actual = {f['path']: base64.b64decode(f['data_base64']) for f in kit['files']}
        self.assertEqual(len(kit['files']), 6)
        self.assertEqual(set(actual), {'/opt/etc/nfqws2/'+p for p in (
            'lua/zapret-lib.lua', 'lua/zapret-antidpi.lua', 'blobs/custom.bin',
            'lists/user.list', 'lists/auto.list', 'lists/exclude.list')})
        for name, raw in actual.items():
            self.assertEqual(raw, (self.root/name.removeprefix('/opt/etc/nfqws2/')).read_bytes())
        self.assertEqual(actual['/opt/etc/nfqws2/blobs/custom.bin'], BLOB)
        self.assertNotIn('UNSELECTED_PRIVATE', json.dumps(kit))
        self.assertTrue(kit['complete'])

    def test_proposal_never_grants_apply_export_device_or_combined_traffic_proof(self):
        result = self.good()['result']
        self.assertTrue(result['resource_inventory_bound'])
        self.assertTrue(result['resources_bundled'])
        for key in ('can_apply', 'can_export', 'combined_verified', 'actual_device_calls', 'config_source_proved'):
            self.assertIs(result[key], False, key)
        self.assertEqual(result['preview']['candidate_config'].splitlines()[0], self.current.splitlines()[0])
        self.assertIs(result['preview']['resource_inventory_proved'], False)

    def test_fresh_recheck_reads_files_again_and_rejects_changed_AUTO_bytes(self):
        original = self.good()['result']
        self.assertEqual(self.good(action='recheck', proposal=original)['result'], original)
        (self.root/'lists/auto.list').write_bytes(b'new-learned.example\n')
        self.assertIn('error', self.call(action='recheck', proposal=original))
        self.assertEqual((self.root/'lists/auto.list').read_bytes(), b'new-learned.example\n')

    def test_changed_saved_config_or_forged_inventory_digest_refuses(self):
        original = self.good()['result']
        self.assertIn('error', self.call(action='recheck', proposal=original, current=self.current+'\n'))
        self.assertIn('error', self.call(binding={'config_sha256': hashlib.sha256(self.current.encode()).hexdigest(),
                                                'resources_sha256': 'a'*64}))

    def test_tampered_kit_buffer_path_or_permission_flag_cannot_survive_recheck(self):
        original = self.good()['result']
        for mutate in ('buffer', 'path', 'flag'):
            with self.subTest(mutate=mutate):
                changed = json.loads(json.dumps(original))
                if mutate == 'buffer':
                    changed['resource_kit']['files'][0]['data_base64'] = 'Zm9yZWlnbg=='
                elif mutate == 'path':
                    changed['resource_kit']['files'][0]['path'] = '/tmp/foreign'
                else:
                    changed['can_apply'] = True
                self.assertIn('error', self.call(action='recheck', proposal=changed))

    def test_required_symlink_or_hardlink_is_preserved_and_refused(self):
        path = self.root/'lists/exclude.list'
        target = self.temp/'foreign.list'
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
        self.assertIn('error', self.call())
        self.assertTrue(path.is_symlink())
        path.unlink()
        os.link(target, path)
        self.assertIn('error', self.call())
        self.assertEqual(target.stat().st_nlink, 2)

    def test_changed_stock_Lua_bytes_never_inherit_name_only_trust(self):
        (self.root/'lua/zapret-lib.lua').write_bytes(b'function fake() return true end\n')
        self.assertIn('error', self.call())

    def test_imported_blob_identity_and_OpenWrt_operand_keep_exact_content(self):
        sha = hashlib.sha256(BLOB).hexdigest()
        (self.root/'blobs/imported').mkdir(mode=0o755)
        (self.root/'blobs/custom.bin').rename(self.root/'blobs/imported'/(sha+'.bin'))
        current = self.current.replace('/opt/etc/nfqws2/blobs/custom.bin', '/etc/nfqws2/blobs/imported/'+sha+'.bin')
        result = self.good(current=current)['result']
        file = next(f for f in result['resource_kit']['files'] if f['kind'] == 'blobs')
        self.assertEqual(file['path'], '/opt/etc/nfqws2/blobs/imported/'+sha+'.bin')
        self.assertEqual(base64.b64decode(file['data_base64']), BLOB)
        self.assertIn('/etc/nfqws2/blobs/imported/'+sha+'.bin', result['preview']['candidate_config'])

    def test_total_kit_limit_is_not_relaxed_to_fit_all_dependencies(self):
        (self.root/'lists/user.list').write_bytes(b'a'*210000)
        (self.root/'lists/auto.list').write_bytes(b'b'*210000)
        self.assertIn('error', self.call())

    def test_unbound_blob_or_missing_resource_never_claims_complete_kit(self):
        self.assertIn('error', self.call(current=self.current.replace('fake:blob=owned', 'fake:blob=undefined')))
        (self.root/'blobs/custom.bin').unlink()
        self.assertIn('error', self.call())


if __name__ == '__main__':
    unittest.main()
