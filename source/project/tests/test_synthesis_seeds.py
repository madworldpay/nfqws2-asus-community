import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('synthesis_seeds', PROJECT/'webui/synthesis_seeds.py')
synthesis_seeds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(synthesis_seeds)


class SynthesisSeedsTests(unittest.TestCase):
    def test_complete_chain_keeps_fake_settings_and_split_in_order(self):
        component = synthesis_seeds.component('tls', [
            '--lua-desync=fake:blob=sample:tcp_md5:repeats=2',
            '--lua-desync=multisplit:pos=1,midsld',
        ], {'sample': 'tls_google'})
        self.assertEqual(component, {
            'method': 'multisplit', 'fake': True, 'payload': 'tls_google',
            'fooling': 'md5', 'repeats': 2, 'pos': '1,midsld',
        })

    def test_unrepresented_parameters_repeats_order_and_payload_are_not_projected(self):
        fake = '--lua-desync=fake:blob=fake_default_tls'
        split = '--lua-desync=multisplit:pos=1,midsld'
        for chain, blobs in [
            ([fake+':repeats=7'], {}),
            ([fake+':optional'], {}),
            ([split+':nodrop'], {}),
            ([split, fake], {}),
            ([fake, split, split], {}),
            (['--lua-desync=fake:blob=alias'], {}),
            (['--lua-desync=fake:blob=alias'], {'alias': 'quic_google'}),
            (['--lua-desync=fake:blob=alias:blob=fake_default_tls'], {'alias': 'tls_google'}),
        ]:
            with self.subTest(chain=chain):
                self.assertIsNone(synthesis_seeds.component('tls', chain, blobs))

    def test_unsupported_scope_is_not_discarded(self):
        for scope, extra, ipset in [
            ('--filter-tcp=443 --hostlist-domains=example.org', '', ''),
            ('--filter-tcp=443 --hostlist-exclude=RESOURCE_1', '', ''),
            ('--filter-tcp=443 --filter-l3=ipv6', '', ''),
            ('--filter-tcp=443 --out-range=-d2', '', ''),
            ('--filter-tcp=443', '--hostlist=RESOURCE_1', ''),
            ('--filter-tcp=443', '', '--ipset=RESOURCE_1'),
            ('--filter-tcp=443 --filter-l7=tls --payload=http_req', '', ''),
            ('--filter-udp=443', '', ''),
        ]:
            with self.subTest(scope=scope, extra=extra, ipset=ipset):
                values = {'NFQWS_ARGS': scope+' --lua-desync=multisplit:pos=1,midsld',
                          'NFQWS_EXTRA_ARGS': extra, 'NFQWS_ARGS_IPSET': ipset}
                self.assertEqual(list(synthesis_seeds.rule_components(values, {}, {}, {}, 'magisk')), [])
        first = '--filter-tcp=443 --lua-desync=fake:blob=fake_default_tls'
        phase = first.replace(' --lua-desync=', ' --filter-l7=tls --lua-desync=')+' --payload=tls_client_hello --lua-desync=multisplit:pos=1,midsld'
        self.assertEqual(list(synthesis_seeds.rule_components({
            'NFQWS_ARGS_CUSTOM': phase,
        }, {}, {}, {}, 'avatar')), [])
        self.assertEqual(list(synthesis_seeds.rule_components({
            'NFQWS_ARGS_CUSTOM': first, 'TCP_PORTS': '80,8000:8080',
        }, {}, {}, {}, 'magisk')), [])

    def test_unverified_lua_or_mismatched_blob_does_not_produce_a_seed(self):
        first = '--filter-tcp=443 --lua-desync=fake:blob=example'
        init = '--lua-init=@RESOURCE_1 --lua-init=@RESOURCE_2'
        resources = {'RESOURCE_1': ('lua', 'zapret-lib.lua', 'library-hash'),
                     'RESOURCE_2': ('lua', 'zapret-antidpi.lua', 'implementation-hash'),
                     'RESOURCE_3': ('blobs', 'tls_clienthello.bin', 'blob-hash')}
        values = {'NFQWS_ARGS_CUSTOM': first, 'NFQWS_BASE_ARGS': init+' --blob=example:@RESOURCE_3'}
        libraries = {'zapret-lib.lua': 'library-hash', 'zapret-antidpi.lua': 'implementation-hash'}
        self.assertEqual(list(synthesis_seeds.rule_components(values, resources, libraries, {}, 'magisk')), [])
        payloads = {'blob-hash': 'tls_google'}
        self.assertEqual(list(synthesis_seeds.rule_components(values, resources, {}, payloads, 'magisk')), [])
        self.assertEqual(list(synthesis_seeds.rule_components(values, resources, libraries, payloads, 'magisk')),
                         [('tls', {'method': 'fake', 'payload': 'tls_google', 'repeats': 1})])

    def test_builtin_blob_name_cannot_be_rebound(self):
        rule = '--filter-tcp=443 --lua-desync=fake:blob=fake_default_tls'
        source = '--blob=fake_default_tls:@RESOURCE_1'
        assets = {'RESOURCE_1': ('blobs', 'different.bin', 'different-bytes')}
        for key in ('NFQWS_BASE_ARGS', 'NFQWS_EXTRA_ARGS', 'NFQWS_ARGS'):
            with self.subTest(key=key):
                self.assertEqual(list(synthesis_seeds.rule_components({
                    'NFQWS_ARGS_CUSTOM': rule, key: source,
                }, assets, {}, {}, 'magisk')), [])

    def test_identical_actions_retain_each_source_in_deterministic_order(self):
        asset = lambda data: (json.dumps(data).encode(), 0o644)
        record = {'id': '7a'*12, 'attribution': 'Example A', 'group': 'tcp'}
        blocks = {'config': 'NFQWS_ARGS_CUSTOM="--filter-tcp=443 --lua-desync=multisplit:pos=1,midsld"',
                  'resources': []}
        zemidala = {'id': '6b'*12, 'attribution': 'Zemidala', 'group': 'presets'}
        files = {
            'catalog.json': asset({'entries': [record]}),
            'collections.json': asset({'entries': [], 'templates': {}, 'resources': {}}),
            'resources.json': asset({}), 'samples.json': asset({}),
            'tcp.json': asset({record['id']: blocks}),
            'zemidala-index.json': asset({'entries': [zemidala]}),
            'zemidala-offline.json': asset({zemidala['id']: {'proto': 'tls', 'steps': [
                '--lua-desync=multisplit:pos=1,midsld',
            ]}}),
        }
        result = synthesis_seeds.compile_seeds(files, {}, {}, {})
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual(result['http'], [])
        self.assertEqual(result['quic'], [])
        self.assertEqual(result['tls'], [{
            'component': {'method': 'multisplit', 'pos': '1,midsld'},
            'sources': [
                {'id': record['id'], 'collection': 'magisk', 'attribution': 'Example A'},
                {'id': zemidala['id'], 'collection': 'zemidala', 'attribution': 'Zemidala'},
            ],
        }])

    def test_verified_snapshot_still_requires_independent_scope(self):
        prefix = 'profile-catalog/v1/'
        card = {'id': 'example-cloud', 'attribution': 'Example cloud contributor', 'min_build': 101}
        rule = ('--filter-udp=443 --filter-l7=quic --payload=quic_initial '
                '--lua-desync=fake:blob=fake_default_quic:repeats=2')
        for key, expected in [('NFQWS_ARGS_CUSTOM', True), ('NFQWS_ARGS_QUIC', False)]:
            with self.subTest(group=key):
                strategy = json.dumps({'mode': 'blocks', 'shared': {'NFQWS_EXTRA_ARGS': '--hostlist=RESOURCE_1'},
                                       'blocks': [{'key': key, 'value': rule}]}).encode()
                doc = json.dumps({'files': [{
                    'type': 'strategy', 'sha256': hashlib.sha256(strategy).hexdigest(),
                    'byte_length': len(strategy), 'data_base64': base64.b64encode(strategy).decode(),
                }]}).encode()
                digest = hashlib.sha256(doc).hexdigest()
                manifest = json.dumps({'profiles': [card | {'size': len(doc), 'sha256': digest}]}).encode()
                envelope = json.dumps({'manifest': base64.b64encode(manifest).decode()}).encode()
                snapshot = {prefix+'catalog.json': (envelope, 0o644), prefix+'files/'+digest+'.json': (doc, 0o644)}
                self.assertEqual(list(synthesis_seeds.signed_records(snapshot, 100)), [])
                [source] = synthesis_seeds.signed_records(snapshot, 107)
                collection, row, values, resources = source
                self.assertEqual((collection, row['attribution']), ('cloud', card['attribution']))
                components = list(synthesis_seeds.rule_components(values, resources, {}, {}, collection))
                self.assertEqual(components, [('quic', {'method': 'fake', 'repeats': 2})] if expected else [])


if __name__ == '__main__':
    unittest.main()
