"""Behavioral contract for the experimental native per-device runtime."""
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_lab as lab
from test_lab import device, draft, profile

HERE = Path(__file__).resolve().parent
PHP = os.environ.get('PHP_TEST_BINARY', '/usr/bin/php')


class AddressSafety(unittest.TestCase):
    def test_canonical_loopback_unspecified_and_mapped_special_addresses_are_rejected(self):
        fixture = lab.LabTests(); fixture.setUp(); self.addCleanup(fixture.tearDown)
        for address in ['0:0:0:0:0:0:0:1', '0:0:0:0:0:0:0:0',
                        '::ffff:127.0.0.1', '::ffff:224.0.0.1', '::ffff:0.0.0.0']:
            with self.subTest(address=address):
                value = draft(); value['devices'][0]['addresses'] = [address]
                self.assertEqual(fixture.call('normalize', value), {'error': 'invalid_draft'})


class RuntimePlan(unittest.TestCase):
    def invoke(self, value=None, discovery=None, configs=None, operation='compile'):
        config = {'TCP_PORTS': '80,443', 'UDP_PORTS': '443', 'USER': 'nobody',
                  'NFQWS_ARGS': '--filter-tcp=80,443', 'IPV6_ENABLED': '0'}
        request = {'draft': value or draft(), 'discovery': discovery or {'devices': []},
                   'strategies': configs or {'current': config, 'stock': config},
                   'base_queue': 300, 'operation': operation}
        code = '''try {
        $file=$argv[1].'/device-profiles-plan.php';
        if(!is_file($file)){echo json_encode(['error'=>'missing_planner']);exit;}
        require $argv[2].'/platform.php';require $file;$v=json_decode(stream_get_contents(STDIN),true);
        $plan=NfqwsDeviceProfilesPlan::compile($v['draft'],$v['discovery'],$v['strategies'],$v['base_queue']);
        $out=match($v['operation']){'render'=>NfqwsDeviceProfilesPlan::rules($plan),
          'arguments'=>NfqwsDeviceProfilesPlan::arguments($v['strategies']['stock'],41000),default=>$plan};
        echo json_encode($out,JSON_THROW_ON_ERROR);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p = subprocess.run([PHP, '-n', '-r', code, str(HERE), str(lab.PUBLIC)],
                           input=json.dumps(request), capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stderr, '')
        return json.loads(p.stdout)

    def test_common_mode_has_no_extra_instances_or_selectors(self):
        result = self.invoke(draft('common'))
        self.assertNotIn('error', result)
        self.assertEqual(result['instances'], [])
        self.assertEqual(result['selectors'], [])

    def test_ordered_current_card_uses_main_queue_and_stock_is_separate(self):
        value = draft();value['profiles'].insert(0, profile('profile-00000002', strategy='current'))
        result = self.invoke(value)
        self.assertNotIn('error', result)
        self.assertEqual([r['queue'] for r in result['selectors']], [300, 41000])
        self.assertEqual(len(result['instances']), 1)
        self.assertEqual(result['instances'][0]['strategy'], 'stock')

    def test_mac_follows_current_local_observation_and_drops_stale_saved_ip(self):
        value=draft();value['devices'][0]['mac']='02:11:22:33:44:55'
        result=self.invoke(value, {'devices':[{'mac':'02:11:22:33:44:55','addresses':['192.168.50.21']}]})
        self.assertNotIn('error',result)
        self.assertEqual(result['selectors'][0]['addresses4'], ['192.168.50.21'])
        result=self.invoke(value)
        self.assertNotIn('error',result)
        self.assertEqual(result['selectors'][0]['addresses4'], [])
        self.assertIn('unresolved_mac', result['warnings'])

    def test_ambiguous_address_is_never_assigned_to_either_mac(self):
        value=draft();value['devices'][0]['mac']='02:11:22:33:44:55'
        value['devices'].append(device('manual-00000002','192.168.50.21','02:11:22:33:44:66'))
        value['profiles'][0]['device_ids'].append('manual-00000002')
        observed={'devices':[{'mac':d['mac'],'addresses':['192.168.50.99']} for d in value['devices']]}
        result=self.invoke(value,observed)
        self.assertNotIn('error',result)
        self.assertEqual(result['selectors'][0]['addresses4'], [])
        self.assertIn('ambiguous_address',result['warnings'])

    def test_duplicate_strategy_cards_share_an_instance_and_disabled_cards_cost_nothing(self):
        value=draft();value['profiles'].extend([profile('profile-00000002'),profile('profile-00000003',enabled=False)])
        result=self.invoke(value)
        self.assertNotIn('error',result)
        self.assertEqual(len(result['instances']),1)
        self.assertEqual([s['queue'] for s in result['selectors']],[41000,41000])

    def test_resource_limit_rejects_more_than_four_active_distinct_strategies(self):
        value=draft();config={'TCP_PORTS':'443','UDP_PORTS':'443','NFQWS_ARGS':'--filter-tcp=443'}
        configs={'current':config,'stock':config}
        value['profiles']=[]
        for i in range(5):
            ident='saved-'+format(i,'016x');configs[ident]=config
            value['profiles'].append(profile('profile-'+format(i,'08x'),strategy=ident))
        self.assertEqual(self.invoke(value,configs=configs),{'error':'runtime_profile_limit'})

    def test_native_rules_dispatch_with_goto_and_restore_common_fallback_semantics(self):
        value=draft();value['profiles'].insert(0,profile('profile-00000002',strategy='current'))
        rules=self.invoke(value,operation='render')
        self.assertNotIn('error',rules)
        self.assertIn('ct original ip saddr @dp_0_4 goto dp_0_original',rules['original'])
        self.assertIn('ct original ip saddr @dp_0_4 goto dp_0_reply',rules['reply'])
        self.assertLess(rules['original'].index('dp_0_4'),rules['original'].index('dp_1_4'))
        self.assertIn('queue num 41000 bypass',rules['definitions'])
        self.assertIn('tcp sport',rules['definitions'])
        self.assertNotIn('meta mark set',rules['definitions'])

    def test_invalid_port_data_never_reaches_nft_script(self):
        configs={'current':{'TCP_PORTS':'443','UDP_PORTS':'443'},'stock':{'TCP_PORTS':'443; delete table inet fw4','UDP_PORTS':'443'}}
        self.assertEqual(self.invoke(configs=configs),{'error':'invalid_profile_ports'})

    def test_arguments_match_pinned_startup_with_multiple_uplinks_and_internal_blocks(self):
        config={'TCP_PORTS':'80,443','UDP_PORTS':'443','USER':'nobody','NFQUEUE_NUM':'41000',
                'IPV6_ENABLED':'1','ISP_INTERFACE':'wan0 wan1','LOG_LEVEL':'0',
                'NFQWS_BASE_ARGS':'--blob=x:0x1234','NFQWS_ARGS':'--filter-tcp=80,443',
                'NFQWS_ARGS_QUIC':'--filter-udp=443','NFQWS_ARGS_CUSTOM':'--filter-tcp=8443 --new --filter-tcp=8080',
                'NFQWS_ARGS_UDP':'--filter-udp=5000','NFQWS_EXTRA_ARGS':'--hostlist=/etc/nfqws2/lists/auto.list',
                'NFQWS_ARGS_IPSET':'--ipset=/etc/nfqws2/lists/ipset.list'}
        source=(HERE.parents[1]/'core/etc/init.d/common').read_text()
        function=re.search(r'^_startup_args\(\) \{.*?^\}',source,re.M|re.S)[0]
        expected=subprocess.run(['/bin/sh','-c',function+'\n_startup_args'],env=os.environ|config,
                                capture_output=True,text=True,check=True)
        self.assertEqual(expected.stderr,'')
        self.assertEqual(self.invoke(configs={'current':config,'stock':config},operation='arguments'),expected.stdout.split())


if __name__ == '__main__':
    unittest.main()
