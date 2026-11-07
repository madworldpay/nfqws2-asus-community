"""Behavioral checks for the isolated device-profile draft experiment."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parents[1] / 'webui/web/public'
PHP = os.environ.get('PHP_TEST_BINARY', '/var/tmp/nfqws-tech-autologin91-native/php')


def device(ident='manual-00000001', ip='192.168.50.20', mac=''):
    return {'id': ident, 'name': 'Телевизор', 'mac': mac, 'addresses': [ip] if ip else []}


def profile(ident='profile-00000001', devices=None, enabled=True, strategy='stock'):
    return {'id': ident, 'name': 'Профиль', 'enabled': enabled, 'strategy': strategy,
            'device_ids': devices if devices is not None else ['manual-00000001']}


def draft(mode='split'):
    return {'schema_version': 1, 'mode': mode, 'devices': [device()], 'profiles': [profile()]}


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'private'

    def tearDown(self):
        self.temp.cleanup()

    def call(self, operation, value=None, sources=None, revision=''):
        code = '''require $argv[1].'/platform.php';
        if(!is_file($argv[2])){echo json_encode(['error'=>'missing_module']);exit;}
        require $argv[2];$sources=json_decode(file_get_contents($argv[6]),true);
        try{$lab=new NfqwsDeviceProfilesLab($argv[3],fn()=>$sources,(int)$argv[7]);
        $v=json_decode(file_get_contents($argv[5]),true);$r=match($argv[4]){
          'status'=>$lab->status(),'save'=>$lab->save($v,$argv[8]),
          'preview'=>$lab->preview($v),'normalize'=>NfqwsDeviceProfilesLab::normalize($v)};
        echo json_encode($r,JSON_THROW_ON_ERROR|JSON_UNESCAPED_UNICODE);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        source = sources or {'interfaces': ['br-lan'], 'subnets': ['192.168.50.0/24'],
                             'leases': '', 'neighbors': '', 'arp': '', 'complete': True}
        payload_file=Path(self.temp.name)/'request.json';payload_file.write_text(json.dumps(value,ensure_ascii=False))
        source_file=Path(self.temp.name)/'sources.json';source_file.write_text(json.dumps(source,ensure_ascii=False))
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(HERE/'device-profiles-lab.php'),
                                 str(self.root), operation, str(payload_file), str(source_file),
                                 str(os.getuid()), revision], capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_truncated_observation_file_is_marked_incomplete(self):
        path=Path(self.temp.name)/'large-leases';path.write_bytes(b'x'*131073)
        code="require $argv[1].'/platform.php';require $argv[2];try{echo json_encode(NfqwsDeviceProfilesLab::observationFile($argv[3],131072));}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        result=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(HERE/'device-profiles-lab.php'),str(path)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);value=json.loads(result.stdout)
        self.assertFalse(value.get('complete',True));self.assertEqual(len(value['content']),131072)

    def test_default_is_common_and_does_not_claim_applied(self):
        result = self.call('status')
        self.assertEqual(result.get('draft', {}).get('mode'), 'common')
        self.assertFalse(result['applied'])
        self.assertTrue(result['experimental'])
        self.assertEqual(len(result['revision']), 64)

    def test_discovery_joins_lan_dhcp_and_neighbors_but_never_wan(self):
        sources = {'interfaces': ['br-lan'], 'subnets': ['192.168.50.0/24'], 'complete': True,
          'leases': '2147483647 02:11:22:33:44:55 192.168.50.20 living-room *\n2147483647 02:aa:aa:aa:aa:aa 203.0.113.1 upstream *\n',
          'neighbors': '192.168.50.20 dev br-lan lladdr 02:11:22:33:44:55 REACHABLE\nfe80::123 dev br-lan lladdr 02:11:22:33:44:55 STALE\n203.0.113.2 dev wan lladdr 02:aa:bb:cc:dd:ee REACHABLE\n', 'arp': ''}
        result = self.call('status', sources=sources)['discovery']
        self.assertEqual(len(result['devices']), 1)
        row = result['devices'][0]
        self.assertEqual(row['id'], 'mac-021122334455')
        self.assertEqual(row['name'], 'living-room')
        self.assertEqual(row['seen'], 'reachable')
        self.assertEqual(row['addresses'], ['192.168.50.20', 'fe80::123'])
        self.assertEqual(row['sources'], ['dhcp', 'neighbor'])

    def test_failed_and_stale_neighbors_are_not_called_online(self):
        sources = {'interfaces': ['br-lan'], 'subnets': [], 'leases': '', 'complete': False,
          'neighbors': '192.168.50.20 dev br-lan lladdr 02:11:22:33:44:55 STALE\n192.168.50.21 dev br-lan INCOMPLETE\n', 'arp': ''}
        rows = self.call('status', sources=sources)['discovery']
        self.assertEqual(rows['state'], 'partial')
        self.assertEqual(len(rows['devices']), 1)
        self.assertEqual(rows['devices'][0]['seen'], 'known')

    def test_no_lan_does_not_fall_back_to_wan(self):
        sources = {'interfaces': [], 'subnets': [], 'leases': '', 'arp': '',
                   'neighbors': '192.168.1.1 dev wan lladdr 02:11:22:33:44:55 REACHABLE', 'complete': True}
        result = self.call('status', sources=sources)['discovery']
        self.assertEqual(result['state'], 'unavailable')
        self.assertEqual(result['devices'], [])

    def test_manual_entry_and_order_survive_independent_requests(self):
        d = draft(); d['profiles'].append(profile('profile-00000002', strategy='current'))
        d['profiles'].reverse()
        before = self.call('status')
        saved = self.call('save', d, revision=before['revision'])
        self.assertNotIn('error', saved)
        self.assertEqual(self.call('status')['draft'], d)
        self.assertEqual(self.call('status')['draft']['profiles'][0]['id'], 'profile-00000002')
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root/'draft.json').stat().st_mode & 0o777, 0o600)

    def test_stale_tab_cannot_overwrite_saved_order(self):
        old = self.call('status')['revision']
        self.call('save', draft(), revision=old)
        d = draft('common')
        self.assertEqual(self.call('save', d, revision=old), {'error': 'stale_revision'})
        self.assertEqual(self.call('status')['draft']['mode'], 'split')

    def test_preview_preserves_priority_and_ignores_disabled_or_unassigned(self):
        d = draft();d['profiles'] = [profile('profile-00000003', enabled=False),
          profile('profile-00000002', strategy='current'), profile(), profile('profile-00000004', devices=[])]
        p = self.call('preview', d)
        self.assertEqual(p['assignments'][0]['profile_ids'], ['profile-00000002', 'profile-00000001'])
        self.assertEqual(p['assignments'][0]['fallback'], 'current')
        self.assertFalse(p['applied'])
        self.assertIn('empty_profile', p['warnings'])
        self.assertEqual([x['priority'] for x in p['profiles']], [1,2,3,4])

    def test_common_mode_keeps_draft_but_assigns_current_strategy_only(self):
        d = draft('common');p = self.call('preview', d)
        self.assertEqual(p['assignments'][0]['profile_ids'], [])
        self.assertEqual(p['assignments'][0]['fallback'], 'current')
        self.assertEqual(len(self.call('normalize', d)['profiles']), 1)

    def test_mac_only_manual_device_warns_when_address_unresolved(self):
        d = draft();d['devices'] = [device(ip='', mac='02:11:22:33:44:55')]
        self.assertIn('unresolved_mac', self.call('preview', d)['warnings'])

    def test_invalid_inputs_do_not_write_anything(self):
        variants=[]
        for key,val in [('mode','other'),('schema_version',2),('surprise',True)]:
            d=draft();d[key]=val;variants.append(d)
        d=draft();d['profiles'][0]['device_ids']=['manual-aaaaaaaa'];variants.append(d)
        d=draft();d['devices'][0]['addresses']=['192.168.50.1/24'];variants.append(d)
        d=draft();d['devices'][0]['mac']='ff:ff:ff:ff:ff:ff';variants.append(d)
        d=draft();d['devices'][0]['name']='bad\nname';variants.append(d)
        d=draft();d['devices'].append(device('manual-00000002'));variants.append(d)
        d=draft();d['profiles'][0]['enabled']='true';variants.append(d)
        d=draft();d['profiles'][0]['strategy']='../../command';variants.append(d)
        d=draft();d['profiles']=[profile(f'profile-{i:08x}') for i in range(17)];variants.append(d)
        for value in variants:
            with self.subTest(value=value):
                self.assertEqual(self.call('normalize', value), {'error':'invalid_draft'})
        self.assertFalse(self.root.exists())

    def test_large_valid_draft_remains_loadable_with_maximum_discovery(self):
        d={'schema_version':1,'mode':'common','devices':[],'profiles':[]};lines=[]
        for i in range(128):
            mac=f'02:11:22:00:00:{i:02x}'
            addresses=[f'2001:db8:{i:x}:1234:1234:1234:1234:{j:x}' for j in range(16)]
            d['devices'].append({'id':f'manual-{i:08x}','name':'я'*64,'mac':mac,'addresses':addresses[:5]})
            lines += [f'{a} dev br-lan lladdr {mac} STALE' for a in addresses]
        sources={'interfaces':['br-lan'],'subnets':[],'leases':'','arp':'','neighbors':'\n'.join(lines),'complete':True}
        old=self.call('status',sources=sources)['revision'];saved=self.call('save',d,sources=sources,revision=old)
        self.assertEqual(len(saved['draft']['devices']),128)
        self.assertLessEqual(len(json.dumps(saved,ensure_ascii=False).encode()),131072)
        loaded=self.call('status',sources=sources)
        self.assertEqual(loaded['draft'],d)
        self.assertEqual(loaded['discovery']['state'],'partial')

    def test_private_storage_rejects_symlink_and_corrupt_json(self):
        other=Path(self.temp.name)/'other';other.mkdir();self.root.symlink_to(other)
        self.assertEqual(self.call('status'), {'error':'storage_unavailable'})
        self.root.unlink();self.root.mkdir(mode=0o700);(self.root/'draft.json').write_text('{broken')
        (self.root/'draft.json').chmod(0o600)
        self.assertEqual(self.call('status'), {'error':'storage_unavailable'})


if __name__ == '__main__': unittest.main()
