"""A strategy carries its required custom bytes, not unrelated user files."""
import base64
import copy
import hashlib
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

from test_dpi_normalize import PHP, PUBLIC
from nfqws_support.share import validate_share
from nfqws_support.validation import InvalidReport
from test_share_v4 import file as envelope_file

LUA = b'function custom() return 1 end\n'
BLOB = b'\x00\xffportable\x00'
CTX = {'purpose': 'youtube', 'operator': 'Example ISP', 'comment': ''}
CONFIG = ('NFQWS_BASE_ARGS="--lua-init=@/opt/etc/nfqws2/lua/custom.lua '
          '--blob=hello:@/opt/etc/nfqws2/blobs/hello.bin"\n'
          'NFQWS_ARGS="--filter-tcp=443 --lua-desync=fake:blob=hello"\n')
STRATEGY = {'mode': 'blocks', 'context': CTX,
            'draft': {'blocks': [{'key': 'NFQWS_ARGS',
                      'value': '--filter-tcp=443 --lua-desync=fake:blob=hello'}]}}


class PortableStrategyAssets(unittest.TestCase):
    def call(self, files=None, package=None, selected=None, config=CONFIG, strategy=None):
        files = files if files is not None else {
            'lua/custom.lua': LUA, 'blobs/hello.bin': BLOB,
            'lua/unrelated.lua': b'private_unselected()',
            'lists/sites.list': b'PRIVATE_UNSELECTED_HOST\n',
        }
        baseline = {name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                    for name, raw in (package or {}).items()}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'nfqws2'
            root.mkdir(mode=0o755)
            for kind in ('lua', 'blobs', 'lists'):
                (root / kind).mkdir(mode=0o755)
            for name, raw in files.items():
                (root / name).write_bytes(raw)
            request = {'context': CTX, 'strategy': strategy or STRATEGY,
                       'resources': {'files': selected or [], 'missing_reason': ''},
                       'analysis_config_sha256': hashlib.sha256(config.encode()).hexdigest()}
            code = '''require $argv[1].'/share-contributions.php';
            require $argv[1].'/share-v4.php';
            try{$d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
            $r=new AsusShareResources($argv[2],(int)$argv[3],$d['baseline']);
            $x=new AsusShareContributions($r,new AsusShareDns());
            $out=$x->prepare($d['selection'],$d['config'],['core'=>'1','web'=>'100']);
            foreach($out as $kind=>$raw)AsusShareV4Payloads::validate($kind,$raw);
            echo json_encode(['documents'=>array_map(fn($v)=>json_decode($v,true),$out),
                'inventory'=>$r->inventory()],JSON_THROW_ON_ERROR);
            }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
            result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(root),
                                     str(os.getuid())], input=json.dumps({
                                         'selection': request, 'config': config,
                                         'baseline': baseline}), capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr, '')
            return json.loads(result.stdout)

    def resources(self, result):
        self.assertNotIn('error', result, result)
        self.assertIn('resources', result['documents'])
        value = result['documents']['resources']
        self.assertEqual(value['schema_version'], 2)
        return value

    def test_required_custom_lua_and_blob_are_embedded_automatically(self):
        result = self.call()
        value = self.resources(result)
        self.assertEqual(value['package_files'], [])
        self.assertEqual({f['kind']: base64.b64decode(f['data_base64'])
                          for f in value['files']}, {'lua': LUA, 'blobs': BLOB})
        self.assertTrue(value['audit']['complete'])
        self.assertTrue(all(d['included'] for d in result['documents']['strategy']['dependencies']))
        self.assertNotIn('PRIVATE_UNSELECTED', json.dumps(result['documents']))
        self.assertNotIn('private_unselected', json.dumps(result['documents']))

    def test_exact_package_lua_and_blob_are_hash_bound_references(self):
        value = self.resources(self.call(package={'lua/custom.lua': LUA,
                                                  'blobs/hello.bin': BLOB}))
        self.assertEqual(value['files'], [])
        self.assertEqual({(f['kind'], f['name'], f['sha256'])
                          for f in value['package_files']}, {
                              ('lua', 'custom.lua', hashlib.sha256(LUA).hexdigest()),
                              ('blobs', 'hello.bin', hashlib.sha256(BLOB).hexdigest())})
        self.assertTrue(value['audit']['complete'])
        self.assertTrue(all('data_base64' not in f for f in value['package_files']))

    def test_same_name_changed_package_file_is_embedded(self):
        value = self.resources(self.call(package={'lua/custom.lua': b'old Lua',
                                                  'blobs/hello.bin': b'old blob'}))
        self.assertEqual(value['package_files'], [])
        self.assertEqual({f['sha256'] for f in value['files']},
                         {hashlib.sha256(LUA).hexdigest(), hashlib.sha256(BLOB).hexdigest()})

    def test_identical_renamed_package_bytes_use_canonical_package_name(self):
        value = self.resources(self.call(package={'lua/official.lua': LUA,
                                                  'blobs/official.bin': BLOB}))
        self.assertEqual(value['files'], [])
        self.assertEqual({f['name'] for f in value['package_files']},
                         {'official.lua', 'official.bin'})

    def test_custom_source_edit_is_not_mislabeled_package(self):
        resource_id = hashlib.sha256(b'lua\0custom.lua').hexdigest()[:32]
        value = self.resources(self.call(package={'lua/custom.lua': LUA}, selected=[{
            'id': resource_id, 'source_sha256': hashlib.sha256(LUA).hexdigest(),
            'text': 'function custom() return 2 end\n'}]))
        self.assertFalse(any(f['kind'] == 'lua' for f in value['package_files']))
        self.assertEqual(base64.b64decode(next(f for f in value['files'] if f['kind'] == 'lua')['data_base64']),
                         b'function custom() return 2 end\n')

    def test_unreadable_required_bytes_do_not_claim_complete_portability(self):
        result = self.call(files={'lua/custom.lua': LUA})
        self.assertIn('error', result)

    def test_automatic_collection_respects_per_file_limit(self):
        result = self.call(files={'lua/custom.lua': LUA,
                                 'blobs/hello.bin': b'x' * 262145})
        self.assertIn('error', result)

    def envelope(self, value):
        if not hasattr(self, '_wire_strategy'):
            self._wire_strategy = self.call()['documents']['strategy']
        return {'version': 4, 'submission_id': str(uuid.uuid4()),
                'files': [envelope_file('strategy', self._wire_strategy),
                          envelope_file('resources', value)]}

    def php_envelope(self, value):
        code = """require $argv[1].'/share-bundle.php';
        $v=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
        try{AsusShareBundle::envelope(json_encode($v),$v['submission_id']);echo 'ok';}
        catch(Throwable $e){echo 'reject';}"""
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC)],
                                input=json.dumps(value), text=True,
                                capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        return result.stdout

    def test_resources2_uses_actual_router_and_relay_envelope_validators(self):
        for package in [{}, {'lua/custom.lua': LUA, 'blobs/hello.bin': BLOB}]:
            env = self.envelope(self.resources(self.call(package=package)))
            self.assertEqual(self.php_envelope(env), 'ok')
            self.assertEqual(len(validate_share(json.dumps(env).encode(), env['submission_id']).files), 2)

    def test_packaged_list_references_bind_name_length_and_digest_on_both_receivers(self):
        raw = gzip.compress(b'example.test\n', mtime=0)
        digest = hashlib.sha256(raw).hexdigest()
        name = f'z2-pack-{digest}.list.gz'
        path = 'lists/' + name
        args = '--filter-tcp=443 --hostlist=/opt/etc/nfqws2/' + path
        strategy = {'mode': 'blocks', 'context': CTX, 'draft': {
            'blocks': [{'key': 'NFQWS_ARGS', 'value': args}]}}
        resource_id = hashlib.sha256(b'lists\0' + name.encode()).hexdigest()[:32]
        documents = self.call(files={path: raw}, package={path: raw}, strategy=strategy,
                              config=f'NFQWS_ARGS="{args}"\n',
                              selected=[{'id': resource_id, 'source_sha256': digest}])['documents']
        resources = documents['resources']
        self.assertEqual([f['name'] for f in resources['package_files']], [name])
        for field, replacement in [(None, None), ('sha256', '0' * 64), ('byte_length', 0)]:
            with self.subTest(field=field):
                value = copy.deepcopy(resources)
                if field:
                    value['package_files'][0][field] = replacement
                env = {'version': 4, 'submission_id': str(uuid.uuid4()),
                       'files': [envelope_file('strategy', documents['strategy']),
                                 envelope_file('resources', value)]}
                if field:
                    self.assertEqual(self.php_envelope(env), 'reject')
                    with self.assertRaises(InvalidReport):
                        validate_share(json.dumps(env).encode(), env['submission_id'])
                else:
                    self.assertEqual(self.php_envelope(env), 'ok')
                    self.assertEqual(len(validate_share(json.dumps(env).encode(), env['submission_id']).files), 2)

    def test_closed_package_metadata_and_types_reject_on_both_receivers(self):
        original = self.resources(self.call(package={'lua/custom.lua': LUA}))
        def change(field, value):
            changed = copy.deepcopy(original)
            changed['package_files'][0][field] = value
            return changed
        cases = [change('data_base64', 'eA=='), change('name', '../custom.lua'),
                 change('byte_length', True), change('byte_length', 1.0),
                 change('sha256', 'A' * 64), change('aliases', ['RESOURCE_999']),
                 change('kind', 'lists')]
        for field, value in [('schema_version', True), ('schema_version', 2.0),
                             ('package_files', {}), ('unknown', 1)]:
            changed = copy.deepcopy(original); changed[field] = value; cases.append(changed)
        changed = copy.deepcopy(original)
        changed['package_files'][0]['id'] = changed['files'][0]['id']; cases.append(changed)
        changed = copy.deepcopy(original)
        changed['package_files'][0]['aliases'] = changed['files'][0]['aliases']; cases.append(changed)
        changed = copy.deepcopy(original)
        changed['files'][0]['data_base64'] += '\n'; cases.append(changed)
        for index, value in enumerate(cases):
            with self.subTest(index=index):
                env = self.envelope(value)
                self.assertEqual(self.php_envelope(env), 'reject')
                with self.assertRaises(InvalidReport):
                    validate_share(json.dumps(env).encode(), env['submission_id'])

    def test_trusted_build_baseline_blob_key_is_recognized(self):
        value = self.resources(self.call(package={'blob/hello.bin': BLOB}))
        self.assertEqual([f['kind'] for f in value['package_files']], ['blobs'])

    def test_unselected_global_lua_requires_complete_export_scope(self):
        result = self.call(config=CONFIG + 'NFQWS_ARGS_UDP="--filter-udp=443 --lua-init=@/opt/etc/nfqws2/lua/unrelated.lua"\n')
        self.assertEqual(result.get('error'), 'strategy_scope_incomplete')


if __name__ == '__main__':
    unittest.main()
