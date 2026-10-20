"""Catch hidden target truncation and settings that never reach the native CLI."""
import json,subprocess,unittest
from test_dpi_normalize import PHP,PUBLIC,ROOT

class DpiOptionsTests(unittest.TestCase):
    def call(self,options=None,group=3):
        code='''$p=$argv[1].'/dpi-options.php';if(!is_file($p)){echo json_encode(['error'=>'not_implemented']);exit;}
        require $p;try{$o=AsusDpiOptions::normalize(json_decode($argv[2],true));echo json_encode(AsusDpiOptions::compile($o,(int)$argv[3],'/native'));}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),json.dumps(options or {}),str(group)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def test_native_defaults_keep_all_original_targets(self):
        v=self.call();self.assertNotIn('error',v)
        self.assertEqual(v['coverage']['domains'],35);self.assertEqual(v['coverage']['tcp'],110)
        self.assertNotIn('--concurrency',v['argv']);self.assertNotIn('--domains',v['argv'])
        self.assertNotIn('domains.txt',v['files']);self.assertNotIn('config.yml',v['files'])

    def test_stock_edit_button_round_trip_preserves_native_config_and_targets(self):
        m=json.loads((ROOT/'support/dpi-native-defaults.json').read_text())
        names={'domains':'domains.txt','tcp':'tcp16.json','sni':'whitelist_sni.txt','burst_domains':'burst-domains.txt','quic_unsupported':'quic_unsupported.txt'}
        targets={k:json.loads(m['files'][n]) if k=='tcp' else [v for v in m['files'][n].splitlines() if v.strip() and not v.strip().startswith('#')] for k,n in names.items()}
        options={'config':m['config'],'targets':targets,'burst':{'connections':10,'timeout':8,'gap':20,'profiles':'rustls,chrome146,chrome123,chrome116,firefox147,safari260,tor145','tls':'1.3+1.2','alpn':'h2'}}
        v=self.call(options,6);self.assertNotIn('error',v)
        actual=json.loads(v['files']['config.yml'])
        self.assertEqual(actual['PIN_CACHE_TTL'],3600)
        self.assertEqual(actual['IP4_LOOKUP_URLS'],m['config']['IP4_LOOKUP_URLS'])
        self.assertEqual(v['coverage']['domains'],35);self.assertEqual(v['coverage']['tcp'],110)

    def test_explicit_settings_reach_cli_and_isolated_files(self):
        v=self.call({'profile':'global','interface':'br0','proxy':'socks5://user:PRIVATE_CANARY@localhost:1080',
                     'config':{'MAX_CONCURRENT':5,'TIMEOUT':3,'IP_VERSION':'ipv6'},
                     'targets':{'domains':['example.com'],'tcp':[{'id':'own','ip':'127.0.0.1','port':443,'sni':'example.com'}]}})
        self.assertNotIn('error',v);self.assertIn('--iface',v['argv']);self.assertIn('br0',v['argv'])
        self.assertEqual(v['coverage']['domains'],1);self.assertEqual(v['coverage']['tcp'],1)
        self.assertEqual(json.loads(v['files']['config.yml'])['TIMEOUT'],3)
        self.assertEqual(v['files']['domains.txt'],'example.com\n')
        self.assertNotIn('PRIVATE_CANARY',json.dumps(v['public_settings']))
        self.assertEqual(v['public_settings']['proxy_configured'],True)

    def test_empty_custom_list_uses_visible_native_defaults(self):
        v=self.call({'targets':{'domains':[]}});self.assertNotIn('error',v)
        self.assertEqual(v['coverage']['domains'],35);self.assertNotIn('domains.txt',v['files'])

    def test_invalid_settings_are_named_and_never_silently_clamped(self):
        for options in [{'command':'reboot'},{'profile':'unknown'},{'limits':{'group_seconds':1801}},
                        {'config':{'MAX_CONCURRENT':0}},{'config':{'TIMEOUT':-1}},
                        {'config':{'UNKNOWN_KEY':1}},{'config':{'ASN_CACHE_FILE':'/etc/shadow'}},
                        {'interface':'br0\nwhoami'},{'proxy':'https://example.com'},
                        {'targets':{'domains':['example.com;reboot']}},{'burst':{'connections':101}}]:
            with self.subTest(options=options):self.assertTrue(self.call(options).get('error','').startswith('invalid_options'))

    def test_burst_parameters_preserve_user_values(self):
        v=self.call({'burst':{'connections':10,'timeout':8,'gap':20,'profiles':'all','tls':'1.2','alpn':'http/1.1','variant':'no-padding','trace':True}},6)
        self.assertNotIn('error',v)
        for flag,value in [('--burst','10'),('--burst-timeout','8'),('--burst-gap','20'),('--burst-tls','1.2'),('--burst-alpn','http/1.1'),('--burst-variant','no-padding')]:
            self.assertEqual(v['argv'][v['argv'].index(flag)+1],value)
        self.assertIn('--trace',v['argv'])

    def test_empty_selected_targets_use_builtin_sets_as_requested(self):
        for target,group in [('domains',2),('tcp',3),('sni',4),('burst_domains',6),('quic_unsupported',2)]:
            with self.subTest(target=target):
                v=self.call({'targets':{target:[]}},group);self.assertNotIn('error',v);self.assertGreater(v['coverage'][target],0)

    def test_burst_list_and_variant_chain_reach_the_original_cli(self):
        v=self.call({'targets':{'domains':['first.example'],'burst_domains':['burst.example']},'burst':{'variant':'-ext:17513;+grease'}},6)
        self.assertNotIn('error',v);self.assertEqual(v['argv'][v['argv'].index('--domains')+1],'burst-domains.txt')

    def test_profile_does_not_replace_the_native_embedded_domain_list(self):
        self.assertEqual(self.call({'profile':'global'})['coverage']['domains'],35)

if __name__=='__main__':unittest.main()
