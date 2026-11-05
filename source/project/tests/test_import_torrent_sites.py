"""Optional website rules are assembled by the server and remain preview-bound."""
import copy
import hashlib
import json
import subprocess
import unittest
from test_import_document import PHP, PUBLIC, STRATEGY
from test_import_plan import selection

SITES = 'nnmclub.to,rutracker.org,rutor.info,tapochek.net'
RULE = ('--comment=nfqws2-community-torrent-sites-v1 --filter-tcp=443 '
        '--hostlist-domains=' + SITES + ' --payload=tls_client_hello '
        '--lua-desync=fake:blob=tls_clienthello:tls_mod=rnd,dupsid,sni=www.google.com:repeats=6:tcp_md5 '
        '--lua-desync=multidisorder:pos=1,midsld')
BASE = ('--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua '
        '--lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua '
        '--blob=tls_clienthello:@/opt/etc/nfqws2/blobs/tls_clienthello.bin')
ORIGINAL = '--filter-tcp=80,443 --filter-l7=http,tls --lua-desync=multisplit:pos=1,midsld'
CUSTOM = '--filter-tcp=443 --hostlist-domains=manual.example --lua-desync=multisplit:pos=2'
CURRENT = ('# owner\nISP_INTERFACE="eth9"\nASUS_CLIENTS4="192.0.2.4"\nTCP_PORTS="80,443"\n'
           'NFQWS_BASE_ARGS="' + BASE + '"\nNFQWS_ARGS="--filter-tcp=443"\n'
           'NFQWS_ARGS_CUSTOM="' + CUSTOM + '"\n')


def fixture():
    strategy = copy.deepcopy(STRATEGY)
    strategy['blocks'] = [{'key': 'NFQWS_ARGS', 'value': ORIGINAL}]
    strategy['shared'] = {'NFQWS_BASE_ARGS': BASE}
    raw = json.dumps(strategy)
    sha = hashlib.sha256(raw.encode()).hexdigest()
    scope = {'id': 'general', 'sha256': sha, 'category': 'global'}
    option = {'catalog_id': 'general', 'sha256': sha}
    selected = selection(blocks=strategy['blocks'], shared=[{'key': 'NFQWS_BASE_ARGS', 'value': BASE}], files=[], trusted_lua=False)
    inventory = {'files': [
        {'id': 'a'*32, 'kind': 'lua', 'name': 'zapret-lib.lua', 'state': 'available', 'sha256': '1'*64, 'byte_length': 1, 'bundled_lua': True},
        {'id': 'b'*32, 'kind': 'lua', 'name': 'zapret-antidpi.lua', 'state': 'available', 'sha256': '2'*64, 'byte_length': 1, 'bundled_lua': True},
        {'id': 'c'*32, 'kind': 'blobs', 'name': 'tls_clienthello.bin', 'state': 'available', 'sha256': '936c2bee4cfb80aa3c426b2dcbcc834b3fbcd1adb17172959dc569c73a14275c', 'byte_length': 681}], 'scan_truncated': False}
    return raw, selected, inventory, scope, option


class TorrentSitesImportTests(unittest.TestCase):
    def plan(self, enabled=True, mutate=None, current=CURRENT, profile='asus-entware'):
        raw, selected, inventory, scope, option = fixture()
        if enabled is not None:
            selected['torrent_sites'] = option if enabled else False
        data = {'documents': [raw], 'selection': selected, 'inventory': inventory,
                'scope': scope, 'current': current, 'profile': profile}
        if mutate:
            mutate(data)
        code = '''require $argv[1].'/import-plan.php';$v=json_decode(stream_get_contents(STDIN),true);try{
echo json_encode(AsusImportPlan::prepare(AsusImportDocument::read($v['documents']),$v['selection'],$v['current'],$v['inventory'],null,$v['profile'],$v['scope']),JSON_THROW_ON_ERROR);
}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC)], input=json.dumps(data), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_unchecked_and_false_are_identical_and_do_not_require_optional_resources(self):
        absent = self.plan(None)
        off = self.plan(False)
        self.assertEqual(off, absent)
        self.assertNotIn('torrent_sites', off)
        self.assertNotIn('nfqws2-community-torrent-sites', off['config'])

    def test_exact_sites_early_rule_preserves_all_original_values_and_settings(self):
        plan = self.plan()
        self.assertTrue(plan.get('ready'), plan)
        changes = {x['key']: x['after'] for x in plan['changes']}
        self.assertEqual(changes['NFQWS_ARGS'], ORIGINAL)
        self.assertEqual(changes['NFQWS_BASE_ARGS'], BASE)
        self.assertEqual(changes['NFQWS_ARGS_CUSTOM'], RULE + ' --new ' + CUSTOM)
        self.assertIn('ISP_INTERFACE="eth9"', plan['config'])
        self.assertIn('ASUS_CLIENTS4="192.0.2.4"', plan['config'])
        self.assertEqual(plan['torrent_sites']['sites'], SITES.split(','))
        self.assertEqual(plan['torrent_sites']['block'], RULE)
        self.assertEqual(plan['files'], [])

    def test_all_imported_groups_keep_author_options_filters_and_non_strategy_settings(self):
        groups = {'NFQWS_ARGS': ORIGINAL,
                  'NFQWS_ARGS_UDP': '--filter-udp=3478-3481 --filter-l7=stun --out-range=<n2 --lua-desync=fake:blob=0x00:repeats=2',
                  'NFQWS_ARGS_QUIC': '--filter-udp=443 --filter-l7=quic --payload=quic_initial --lua-desync=fake:blob=0x00',
                  'NFQWS_ARGS_CUSTOM': CUSTOM + ' --new --filter-tcp=443 --hostlist-exclude-domains=manual-exclude.example --lua-desync=multidisorder:pos=2'}
        def mutate(d):
            strategy=json.loads(d['documents'][0]);strategy['blocks']=[{'key':key,'value':value} for key,value in groups.items()]
            d['documents']=[json.dumps(strategy)];d['selection']['blocks']=strategy['blocks']
            d['current'] += 'MODE_ALL="--hostlist-exclude-domains=owner.example"\nNFQWS_EXTRA_ARGS="--hostlist-exclude-domains=owner.example"\n'
        plan=self.plan(mutate=mutate)
        self.assertTrue(plan.get('ready'), plan)
        changes={row['key']:row['after'] for row in plan['changes']}
        for key,value in groups.items():
            self.assertEqual(changes[key], (RULE+' --new ' if key=='NFQWS_ARGS_CUSTOM' else '')+value)
        self.assertIn('MODE_ALL="--hostlist-exclude-domains=owner.example"',plan['config'])
        self.assertIn('NFQWS_EXTRA_ARGS="--hostlist-exclude-domains=owner.example"',plan['config'])

    def test_repeated_preview_is_idempotent_and_toggle_off_removes_only_generated_addition(self):
        on = self.plan()
        again = self.plan(current=on.get('config', CURRENT))
        self.assertEqual(again.get('config', '').count('nfqws2-community-torrent-sites-v1'), 1)
        off = self.plan(False)
        self.assertIn('NFQWS_ARGS_CUSTOM="' + CUSTOM + '"', off['config'])
        self.assertEqual({r['key']: r['after'] for r in off['changes']}['NFQWS_ARGS'], ORIGINAL)
        self.assertNotEqual(on.get('digest'), off['digest'])

    def test_native_paths_are_preserved_and_stock_resources_are_resolved_canonically(self):
        current = CURRENT.replace('/opt/etc/nfqws2/', '/etc/nfqws2/')
        plan = self.plan(current=current, profile='openwrt')
        self.assertTrue(plan.get('ready'), plan)
        self.assertNotIn('/opt/', plan['config'])
        self.assertIn(RULE, plan['config'])

    def test_missing_changed_or_untrusted_stock_resources_fail_closed(self):
        for mutate in [lambda d: d['inventory']['files'].pop(),
                       lambda d: d['inventory']['files'][-1].update(sha256='0'*64),
                       lambda d: d['inventory']['files'][0].update(bundled_lua=False),
                       lambda d: d['inventory'].update(scan_truncated=True)]:
            plan = self.plan(mutate=mutate)
            self.assertFalse(plan.get('ready'), plan)
            self.assertNotIn('nfqws2-community-torrent-sites', plan.get('config', ''))

    def test_provider_local_forged_or_changed_source_cannot_enable_option(self):
        for mutate in [lambda d: d.update(scope=None),
                       lambda d: d['scope'].update(category='provider'),
                       lambda d: d['scope'].update(sha256='0'*64),
                       lambda d: d['selection']['torrent_sites'].update(extra=True)]:
            plan = self.plan(mutate=mutate)
            self.assertFalse(plan.get('ready'), plan)

    def test_unknown_global_profile_syntax_and_missing_capture_port_are_not_guessed(self):
        cases = ['--dpi-desync=fake', '--template=opaque', '--filter-tcp=443 --lua-desync=unknown_private_function']
        for value in cases:
            plan = self.plan(mutate=lambda d: d['selection']['blocks'][0].update(value=value))
            self.assertFalse(plan.get('ready'), plan)
            self.assertNotIn('nfqws2-community-torrent-sites', plan.get('config', ''))
        plan = self.plan(current=CURRENT.replace('TCP_PORTS="80,443"', 'TCP_PORTS="80"'))
        self.assertFalse(plan.get('ready'), plan)

    def test_manual_lookalike_is_not_removed_and_opaque_managed_marker_is_rejected(self):
        manual = CUSTOM + ' --new ' + RULE.replace('--comment=nfqws2-community-torrent-sites-v1 ', '')
        plan = self.plan(current=CURRENT.replace(CUSTOM, manual))
        self.assertTrue(plan.get('ready'), plan)
        self.assertIn(RULE + ' --new ' + manual, plan['config'])
        plan = self.plan(current=CURRENT.replace(CUSTOM, CUSTOM + ' --comment=nfqws2-community-torrent-sites-v1'))
        self.assertFalse(plan.get('ready'), plan)

    def test_predicates_require_the_exact_loaded_packaged_helper_and_auto_module(self):
        def helper(d):
            base = BASE + ' --lua-init=@/opt/etc/nfqws2/lua/zapret-auto.lua --lua-init=@/opt/etc/nfqws2/lua/local-tls13-stun.lua'
            d['selection']['shared'][0]['value'] = base
            for name, sha in [('zapret-auto.lua', '3'), ('local-tls13-stun.lua', '4')]:
                d['inventory']['files'].append({'id': sha*32, 'kind':'lua', 'name':name, 'state':'available', 'sha256':sha*64, 'byte_length':1, 'bundled_lua':True})
            d['selection']['blocks'][0]['value'] = '--filter-tcp=443 --payload=tls_client_hello --lua-desync=condition:iff=nfqws_local_offers_tls13:instances=2 --lua-desync=multisplit:pos=1 --lua-desync=stopif:iff=nfqws_local_offers_tls13'
        self.assertTrue(self.plan(mutate=helper).get('ready'))
        for change in [lambda d: d['inventory']['files'][-1].update(bundled_lua=False),
                       lambda d: d['selection']['shared'][0].update(value=d['selection']['shared'][0]['value'].replace(' --lua-init=@/opt/etc/nfqws2/lua/local-tls13-stun.lua','')),
                       lambda d: d['selection']['shared'][0].update(value=d['selection']['shared'][0]['value'].replace(' --lua-init=@/opt/etc/nfqws2/lua/zapret-auto.lua','')),
                       lambda d: d['selection']['blocks'][0].update(value=d['selection']['blocks'][0]['value'].replace('iff=nfqws_local_offers_tls13','iff=unknown_function')),
                       lambda d: d['selection']['blocks'][0].update(value=d['selection']['blocks'][0]['value']+':cond_code=dynamic'),
                       lambda d: d['selection']['blocks'][0].update(value='--filter-tcp=443 --lua-desync=nop')]:
            def mutate(d):
                helper(d)
                change(d)
            self.assertFalse(self.plan(mutate=mutate).get('ready'), 'Unproved Lua callbacks must fail closed')

    def test_null_or_scalar_option_is_rejected_instead_of_silently_disabling(self):
        for value in [None, 0, True, 'general']:
            plan = self.plan(mutate=lambda d: d['selection'].update(torrent_sites=value))
            self.assertEqual(plan.get('error'), 'invalid_import_selection', plan)


if __name__ == '__main__':
    unittest.main()
