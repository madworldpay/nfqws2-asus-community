"""Wrong pool/group generation or option injection changes actual DNS routing."""
import copy
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC


def upstream(id='main', **overrides):
    return dict(id=id, label=id, protocol='dot', address='9.9.9.9', port=853,
                tls_name='dns.quad9.net', url='', bootstrap=[], default=True,
                domains=[]) | overrides


def profile(*servers, records=None):
    return dict(schema_version=1, upstreams=list(servers or [upstream()]), records=records or [])


class SmartDnsProfileTests(unittest.TestCase):
    def call(self, value, action='render', port=16053):
        code = '''$file=$argv[1].'/smartdns-profile.php';
        if(!is_file($file)){echo json_encode(['error'=>'missing_profile']);exit;}
        require $file;$p=json_decode(stream_get_contents(STDIN),true);
        try{$v=AsusSmartDnsProfile::normalize($p);echo json_encode($argv[2]==='render'?AsusSmartDnsProfile::render($v,(int)$argv[3]):['profile'=>$v,'hash'=>AsusSmartDnsProfile::hash($v)]);}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage(),'field'=>$e instanceof AsusSmartDnsProfileError?$e->field:null]);}'''
        p = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), action, str(port)],
                           input=json.dumps(value), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stderr, '')
        return json.loads(p.stdout)

    def test_every_dpi_preset_is_a_valid_editable_profile(self):
        from pathlib import Path
        catalog=json.loads((Path(__file__).resolve().parents[1]/'webui/web/src/api/smartDnsPresets.json').read_text())
        for preset in catalog['presets']:
            with self.subTest(preset=preset['id']):
                server={k:v for k,v in preset.items() if k!='id'}|{'id':'picked','default':True,'domains':[]}
                out=self.call(profile(server));self.assertNotIn('error',out);self.assertIn('bind 127.0.0.1:16053',out['config'])

    def test_specialized_servers_are_not_default(self):
        v = self.call(profile(upstream(), upstream('posters', default=False,
            domains=[dict(name='image.tmdb.org', include_subdomains=False)])))
        self.assertNotIn('error', v)
        lines = [s for s in v['config'].splitlines() if s.startswith('server-tls ')]
        self.assertEqual(len(lines), 2)
        self.assertNotIn('-exclude-default-group', lines[0])
        self.assertIn('-exclude-default-group', lines[1])
        self.assertIn('bind 127.0.0.1:16053', v['config'])
        self.assertIn('bind-tcp 127.0.0.1:16053', v['config'])

    def test_shared_domain_has_one_group(self):
        domain = [dict(name='image.tmdb.org', include_subdomains=True)]
        v = self.call(profile(upstream(), upstream('a', default=False, domains=domain),
                              upstream('b', default=False, domains=domain)))
        self.assertNotIn('error', v)
        self.assertEqual(len(v['groups']), 1)
        self.assertEqual(v['groups'][0]['servers'], ['a', 'b'])
        self.assertEqual(v['groups'][0]['domain'], 'image.tmdb.org')
        self.assertEqual(v['config'].count('nameserver /image.tmdb.org/'), 1)
        self.assertEqual(v['config'].count('-group ' + v['groups'][0]['group']), 2)

    def test_specific_domain_precedence(self):
        v = self.call(profile(upstream(domains=[dict(name='TMDB.ORG.', include_subdomains=True)]),
                              upstream('exact', default=False, domains=[dict(name='image.tmdb.org', include_subdomains=False)])))
        self.assertNotIn('error', v)
        self.assertEqual({(g['domain'], g['include_subdomains']) for g in v['groups']},
                         {('tmdb.org', True), ('image.tmdb.org', False)})
        self.assertIn('nameserver /-.image.tmdb.org/', v['config'])
        self.assertIn('nameserver /tmdb.org/', v['config'])

    def test_static_record_overlap_is_visible(self):
        v = self.call(profile(upstream(domains=[dict(name='example.org', include_subdomains=True)]),
            records=[dict(name='img.example.org', include_subdomains=False,
                          addresses=['192.0.2.10', '2001:db8::10'], checked_at=None)]))
        self.assertNotIn('error', v)
        self.assertEqual(len(v['overlaps']), 1)
        self.assertEqual(v['overlaps'][0]['record'], 'img.example.org')
        self.assertEqual(v['overlaps'][0]['dns_domain'], 'example.org')
        self.assertIn('address /-.img.example.org/192.0.2.10,2001:db8::10', v['config'])

    def test_normalization_is_stable_but_user_edit_changes_hash(self):
        a = self.call(profile(upstream()), 'normalize')
        b = self.call(profile(upstream(label='edited')), 'normalize')
        self.assertNotIn('error', a)
        self.assertEqual(a['hash'], self.call(a['profile'], 'normalize')['hash'])
        self.assertNotEqual(a['hash'], b['hash'])

    def test_doh_pins_connection_without_plain_bootstrap_or_disabled_tls(self):
        v = self.call(profile(upstream(protocol='doh', port=443, url='https://dns.quad9.net/dns-query')))
        self.assertNotIn('error', v)
        self.assertIn('server-https https://dns.quad9.net/dns-query', v['config'])
        self.assertIn('-host-ip 9.9.9.9', v['config'])
        self.assertIn('-tls-host-verify dns.quad9.net', v['config'])
        self.assertNotIn('no-check-certificate', v['config'])
        self.assertNotIn('\nserver ', v['config'])

    def test_invalid_fields_and_injection_are_rejected(self):
        bad = [upstream(port=0), upstream(port=True), upstream(port=65536),
               upstream(address='9.9.9.9\nserver 192.0.2.1'), upstream(id='--group'),
               upstream(tls_name='$(id)'), upstream(tls_name=''),
               upstream(protocol='dot', url='https://dns.example/dns-query'),
               upstream(protocol='doh', port=443, url='http://dns.example/dns-query'),
               upstream(protocol='doh', port=443, url='https://user:pass@dns.example/dns-query'),
               upstream(protocol='doh', port=443, url='https://dns.example/dns-query#fragment'),
               upstream(protocol='doh', port=443, url='https://dns.example/a -no-check-certificate'),
               upstream(address='dns.example', bootstrap=[]),
               upstream(domains=[dict(name='a..example', include_subdomains=True)]),
               upstream(domains=[dict(name='x.example', include_subdomains='yes')]),
               upstream(unknown='value')]
        for server in bad:
            with self.subTest(server=server):
                self.assertEqual(self.call(profile(server)).get('error'), 'invalid_profile')
        for v in [profile(upstream(default=False)), profile(upstream()) | {'command':'id'},
                  profile(upstream(), upstream()), profile(upstream()) | {'schema_version':2}]:
            self.assertEqual(self.call(v).get('error'), 'invalid_profile')

    def test_limits_are_enforced_without_silent_truncation(self):
        values = [profile(*[upstream('s'+str(i)) for i in range(33)]),
                  profile(upstream(label='x'*81)), profile(upstream(bootstrap=['192.0.2.'+str(i) for i in range(1,10)])),
                  profile(upstream(domains=[dict(name='n'+str(i)+'.example', include_subdomains=True) for i in range(257)])),
                  profile(upstream(),records=[dict(name='n'+str(i)+'.example',include_subdomains=False,addresses=['192.0.2.1'],checked_at=None) for i in range(65)]),
                  profile(upstream(),records=[dict(name='x.example',include_subdomains=False,addresses=['192.0.2.'+str(i) for i in range(1,10)],checked_at=None)]),
                  profile(upstream(protocol='doh',port=443,url='https://dns.example/'+('a'*2048)))]
        for value in values:
            with self.subTest(size=len(json.dumps(value))):
                self.assertEqual(self.call(value).get('error'), 'invalid_profile')


if __name__ == '__main__':
    unittest.main()
