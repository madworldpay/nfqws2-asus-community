"""Packet-local clone output is not an external file or a global blob alias."""
import copy
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import unittest
from test_dpi_normalize import PHP, PUBLIC

CLONE = '--lua-desync=tls_client_hello_clone:blob=live:fallback=base'
FAKE = '--lua-desync=fake:blob=live'
CONFIG = '''NFQWS_BASE_ARGS="--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua --blob=base:0x00"
NFQWS_ARGS="--filter-tcp=443"
'''
STOCK = [
    ('zapret-lib.lua', 93714, '6bf528fef1f0fc3c65e189216fc8a06bb873f6e25d1c29d2bfa4695a09b73440'),
    ('zapret-antidpi.lua', 51866, '6d1fa9168e5de1682fef91fd174f68b58c50f6739ef00f42ca7db2b940b6246d'),
]


class DynamicBlobTests(unittest.TestCase):
    def inventory(self):
        return [{'id': hashlib.sha256(('lua\0' + name).encode()).hexdigest()[:32],
                 'kind': 'lua', 'name': name, 'bundled_name': name, 'byte_length': size,
                 'sha256': sha, 'state': 'available', 'bundled_lua': True}
                for name, size, sha in STOCK]

    def analyze(self, text, config=CONFIG, inventory=None, blocks=None):
        body = "require $argv[1].'/share-dependencies.php';$p=json_decode(stream_get_contents(STDIN),true);echo json_encode(AsusShareDependencies::analyze($p['selection'],$p['config'],$p['inventory']));"
        payload = {'selection': {'mode': 'blocks', 'draft': {'blocks': blocks or [
            {'key': 'NFQWS_ARGS', 'value': text}]}}, 'config': config,
            'inventory': {'files': self.inventory() if inventory is None else inventory}}
        p = subprocess.run([PHP, '-n', '-r', body, str(PUBLIC)],
                           input=json.dumps(payload), text=True, capture_output=True, timeout=8)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(p.stderr, '')
        return json.loads(p.stdout)

    def test_export_edited_stock_clone_uses_sent_bytes_for_final_audit(self):
        from test_portable_strategy_assets import PortableStrategyAssets
        root = Path(__import__('os').environ['PACKAGES_DIR'])
        package = next(root.glob('*.ipk'))
        import io
        with tarfile.open(package) as archive:
            data = archive.extractfile('data.tar.gz').read()
        files = {}
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for name, _, _ in STOCK:
                member = next(m for m in archive.getmembers() if m.name.endswith('/lua/' + name))
                files['lua/' + name] = archive.extractfile(member).read()
        name='zapret-antidpi.lua';raw=files['lua/'+name]
        strategy={'mode':'blocks','context':__import__('test_portable_strategy_assets').CTX,'draft':{'blocks':[{'key':'NFQWS_ARGS','value':'--filter-tcp=443 '+CLONE+' '+FAKE}]}}
        result=PortableStrategyAssets().call(strategy=strategy,files=files,package=files,config=CONFIG.replace('--filter-tcp=443','--filter-tcp=443 '+CLONE+' '+FAKE),selected=[{'id':hashlib.sha256(('lua\0'+name).encode()).hexdigest()[:32],'source_sha256':hashlib.sha256(raw).hexdigest(),'text':'function tls_client_hello_clone() end\n'}])
        self.assertNotIn('error',result,result)
        audit=result['documents']['resources']['audit']
        self.assertFalse(audit['complete'],audit)
        self.assertIn('unbound_blob',[x['kind'] for x in audit['unresolved']])

    def test_loaded_stock_clone_produces_blob_for_later_fake_in_same_tcp_profile(self):
        for separator in ['=', ' ']:
            text = '--filter-tcp=443 --payload=tls_client_hello ' + CLONE + ' ' + FAKE
            if separator == ' ':
                text = text.replace('--lua-desync=', '--lua-desync ')
            result = self.analyze(text)
            self.assertTrue(result['complete'], result)
            self.assertNotIn('live', result['blob_bindings'])
            self.assertEqual(result['unresolved'], [])

    def test_clone_fallback_remains_a_real_input_dependency(self):
        result = self.analyze('--filter-tcp=443 ' + CLONE.replace('fallback=base', 'fallback=missing') + ' ' + FAKE)
        self.assertFalse(result['complete'])
        self.assertIn('missing', [r.get('name') for r in result['unresolved']])

    def test_clone_cannot_overwrite_runtime_packet_or_instance_fields(self):
        for name in ['arg', 'dis', 'outgoing', 'l7payload', 'track', 'plan']:
            with self.subTest(name=name):
                result = self.analyze('--filter-tcp=443 ' + CLONE.replace('blob=live', 'blob=' + name)
                                      + ' ' + FAKE.replace('blob=live', 'blob=' + name))
                self.assertFalse(result['complete'], result)

    def test_producer_does_not_resolve_earlier_other_profile_or_other_block_uses(self):
        for text in ['--filter-tcp=443 ' + FAKE + ' ' + CLONE,
                     '--filter-tcp=443 ' + CLONE + ' --new --filter-tcp=443 ' + FAKE,
                     '--filter-tcp=443 ' + CLONE + ' --new=second --filter-tcp=443 ' + FAKE]:
            result = self.analyze(text)
            self.assertFalse(result['complete'], result)
            self.assertIn('live', [r.get('name') for r in result['unresolved']])
        result = self.analyze('', blocks=[
            {'key': 'NFQWS_ARGS', 'value': '--filter-tcp=443 ' + CLONE},
            {'key': 'NFQWS_ARGS_CUSTOM', 'value': '--filter-tcp=443 ' + FAKE}])
        self.assertFalse(result['complete'], result)

    def test_untrusted_or_changed_lua_cannot_claim_stock_producer_semantics(self):
        for change in ['missing', 'untrusted', 'changed', 'override']:
            inventory = self.inventory();config = CONFIG
            if change == 'missing':
                inventory.pop()
            elif change == 'untrusted':
                inventory[-1]['bundled_lua'] = False
            elif change == 'changed':
                inventory[-1]['sha256'] = 'a' * 64
            else:
                config = config.replace('--blob=base:', '--lua-init=@/opt/etc/nfqws2/lua/custom.lua --blob=base:')
                inventory.append({'id': 'f' * 32, 'kind': 'lua', 'name': 'custom.lua',
                                  'state': 'available', 'sha256': 'b' * 64, 'byte_length': 1})
            with self.subTest(change=change):
                result = self.analyze('--filter-tcp=443 ' + CLONE + ' ' + FAKE, config, inventory)
                self.assertFalse(result['complete'], result)

    def test_unselected_profile_initializer_can_override_global_lua_functions(self):
        inventory = self.inventory() + [{'id': 'f' * 32, 'kind': 'lua', 'name': 'custom.lua',
                                        'state': 'available', 'sha256': 'b' * 64, 'byte_length': 1}]
        config = CONFIG + 'NFQWS_ARGS_CUSTOM="--filter-tcp=80 --lua-init=@/opt/etc/nfqws2/lua/custom.lua"\n'
        result = self.analyze('--filter-tcp=443 ' + CLONE + ' ' + FAKE, config, inventory)
        self.assertFalse(result['complete'], result)

    def test_conditional_or_unknown_execution_is_not_claimed_complete(self):
        for text in [
            '--filter-udp=443 ' + CLONE + ' ' + FAKE,
            '--filter-udp=443 --filter-tcp=443 ' + CLONE + ' ' + FAKE,
            '--filter-tcp=443 --filter-udp=443 ' + CLONE + ' ' + FAKE,
            '--filter-tcp=443 ' + CLONE + ' ' + FAKE + ' --filter-udp=443',
            '--template=udp --filter-udp=443 --new --filter-tcp=443 --import=udp ' + CLONE + ' ' + FAKE,
            '--filter-tcp=443 ' + CLONE + ' ' + FAKE + ' --import other',
            '--filter-tcp=443 --filter-icmp=8 ' + CLONE + ' ' + FAKE,
            '--filter-tcp=443 ' + CLONE + ':strategy=1 ' + FAKE,
            '--filter-tcp=443 ' + CLONE + ':direction=in ' + FAKE,
            '--filter-tcp=443 ' + CLONE + ' --payload=http_req ' + FAKE,
            '--filter-tcp=443 ' + CLONE + ' --lua-desync=custom_action ' + FAKE,
            '--filter-tcp=443 ' + CLONE + ' --lua-desync=fake:blob=live:direction=in',
            '--filter-tcp=443 ' + CLONE + ' --lua-desync=fake:blob=live:dir=in',
            '--filter-tcp=443 ' + CLONE + ' --lua-desync=fake:blob=live:dir=any',
            '--filter-tcp=443 --lua-desync=condition:iff=custom:instances=2 ' + CLONE + ' ' + FAKE,
        ]:
            with self.subTest(text=text):
                result = self.analyze(text)
                self.assertFalse(result['complete'], result)

    @unittest.skipUnless(os.environ.get('PACKAGES_DIR'), 'Requires real verified package resources')
    def test_stock_resource_attachments_keep_provenance_during_full_import_preview(self):
        package = next(Path(os.environ['PACKAGES_DIR']).glob('*armv7*.ipk'))
        rows = []
        with tarfile.open(package, 'r:*') as outer:
            member = next(m for m in outer.getmembers() if m.name.startswith('data.tar'))
            with tarfile.open(fileobj=outer.extractfile(member), mode='r:*') as data:
                for name, size, sha in STOCK:
                    member = next(m for m in data.getmembers()
                                  if m.name.lstrip('./') == 'opt/etc/nfqws2/lua/' + name)
                    raw = data.extractfile(member).read()
                    self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (size, sha))
                    rows.append({'id': hashlib.sha256(('lua\0' + name).encode()).hexdigest()[:32],
                                 'kind': 'lua', 'name': name, 'encoding': 'utf8', 'aliases': [],
                                 'source_sha256': sha, 'sha256': sha, 'byte_length': len(raw),
                                 'data_base64': base64.b64encode(raw).decode()})
        body = """require $argv[1].'/import-keenetic.php';require $argv[1].'/import-plan.php';
$p=json_decode(stream_get_contents(STDIN),true);$raw=AsusImportKeenetic::convert($p['config']);
$resources=['type'=>'nfqws2_resources','schema_version'=>1,'context'=>['purpose'=>'fixture','operator'=>'fixture','comment'=>''],
 'files'=>$p['files'],'audit'=>['scope'=>'files_only','references'=>[],'unresolved'=>[],'missing_reason'=>'','complete'=>true]];
$doc=AsusImportDocument::read([$raw,json_encode($resources)]);
$sel=['blocks'=>[],'shared'=>[],'ports'=>[],'files'=>[],'dns'=>[],'allow_shared_impact'=>true,'allow_incomplete'=>false,'trusted_lua'=>false];
foreach($doc['values']as $key=>$value)$sel[in_array($key,AsusImportConfig::BLOCKS,true)?'blocks':'shared'][]=['key'=>$key,'value'=>$value];
if(isset($p['picked_ids'])){foreach($p['picked_ids']as $id)$sel['files'][]=['id'=>$id];$sel['trusted_lua']=true;$sel['allow_incomplete']=true;}
elseif($p['select_files'])foreach($doc['resources']as $file)$sel['files'][]=['id'=>$file['id']];
echo json_encode(AsusImportPlan::prepare($doc,$sel,'NFQWS_ARGS="--filter-tcp=80"', ['files'=>$p['inventory']],null));"""
        config = CONFIG.replace('--filter-tcp=443"', '--filter-tcp=443 ' + CLONE + ' ' + FAKE + '"')
        for selected in [False, True]:
            with self.subTest(selected=selected):
                p = subprocess.run([PHP, '-n', '-r', body, str(PUBLIC)],
                    input=json.dumps({'config': config, 'files': rows,
                                      'inventory': self.inventory(), 'select_files': selected}),
                    text=True, capture_output=True, timeout=8)
                self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
                plan = json.loads(p.stdout)
                self.assertTrue(plan['ready'], plan['problems'])
                self.assertEqual(plan['warnings'], [])
        original = next(r for r in rows if r['name'] == 'zapret-antidpi.lua')
        modified = copy.deepcopy(original)
        raw = b'function tls_client_hello_clone() end\n'
        modified.update(id='c' * 32, sha256=hashlib.sha256(raw).hexdigest(),
                        source_sha256=hashlib.sha256(raw).hexdigest(), byte_length=len(raw),
                        data_base64=base64.b64encode(raw).decode())
        library = [r for r in rows if r is not original]
        for order in [[modified, original], [original, modified]]:
            with self.subTest(chosen_modified_first=order[0] is modified):
                p = subprocess.run([PHP, '-n', '-r', body, str(PUBLIC)],
                    input=json.dumps({'config': config, 'files': library + order,
                                      'inventory': self.inventory(), 'select_files': False,
                                      'picked_ids': ['c' * 32]}),
                    text=True, capture_output=True, timeout=8)
                self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
                plan = json.loads(p.stdout)
                self.assertTrue(plan['ready'], plan)
                self.assertIn('/lua/imported/',plan['files'][0]['path'])
                self.assertIn('--lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua',plan['config'])
                self.assertNotIn(plan['files'][0]['path'],plan['config'])
                self.assertFalse(plan['files'][0]['replace'])


if __name__ == '__main__':
    unittest.main()
