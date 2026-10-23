"""Selected strategy data is copied, never executed; location needs consent."""
import json,subprocess,unittest
from test_dpi_normalize import PHP,PUBLIC,ROOT

CONFIG='''ISP_INTERFACE="PRIVATE_CANARY_WAN"
ASUS_CLIENTS4="192.168.99.1"
POLICY_NAME="PRIVATE_CANARY_POLICY"
MODE_LIST="--hostlist=/opt/private/PRIVATE_CANARY.list"
NFQWS_ARGS="--filter-tcp=443 $MODE_LIST --lua-desync=fake:blob=tls_clienthello"
NFQWS_ARGS_QUIC="--filter-udp=443 --filter-l7=quic"
NFQWS_ARGS_UDP="--filter-udp=3478 --out-range=<n2"
NFQWS_ARGS_CUSTOM="--filter-tcp=8443 --dpi-desync=fake"
'''

class ShareStrategyTests(unittest.TestCase):
    def test_export_does_not_invent_file_dependencies_for_engine_builtin_blobs(self):
        v=self.call(edited='--lua-desync=fake:blob=fake_default_tls --lua-desync=multisplit:seqovl_pattern=fake_default_http')
        self.assertNotIn('error',v);self.assertEqual(v['dependencies'],[])
        self.assertIn('blob=fake_default_tls',v['blocks'][0]['value'])
        v=self.call(edited='--lua-desync=fake:blob=custom_blob')
        self.assertEqual(v['dependencies'][0]['kind'],'blob')

    def test_credentials_with_separate_values_and_complete_unusual_paths_are_private(self):
        for text in ['--password PRIVATE_CANARY_SECRET','--auth-token PRIVATE_CANARY_SECRET','--password="PRIVATE_CANARY_SECRET"']:
            self.assertIn('error',self.call(edited=text))
        for path in ['/opt/private@home/PRIVATE_CANARY.list','/opt/личное/PRIVATE_CANARY.list','/opt/path+private/PRIVATE_CANARY.list']:
            v=self.call(edited='--filter-tcp=443 --hostlist='+path)
            self.assertNotIn('error',v);self.assertNotIn('PRIVATE_CANARY',json.dumps(v))
            self.assertEqual(v['blocks'][0]['value'],'--filter-tcp=443 --hostlist=RESOURCE_1')

    def test_network_literals_inside_strategy_are_dependencies_not_identity(self):
        v=self.call(edited='--filter-tcp=443 --filter-ip=192.168.99.1/24 --filter-ip6=2001:db8::7 --filter-mac=aa:bb:cc:dd:ee:ff')
        text=json.dumps(v)
        for canary in ['192.168.99.1','2001:db8::7','aa:bb:cc:dd:ee:ff']:self.assertNotIn(canary,text)
        self.assertEqual({x['kind'] for x in v['dependencies']},{'network'})

    def test_full_config_settings_have_real_numeric_or_port_grammar(self):
        for extra in ['TCP_PORTS="PRIVATE_HOSTNAME"','NFQUEUE_NUM="PRIVATE_NAME"','LOG_LEVEL="verbose-secret"','IPV6_ENABLED="2"','UDP_PORTS="99999"']:
            self.assertIn('error',self.full(CONFIG+extra+'\n'))
        v=self.full(CONFIG+'TCP_PORTS="80,443"\nUDP_PORTS="443,1000:2000"\nLOG_LEVEL=0\nNFQUEUE_NUM=300\nIPV6_ENABLED=0\n')
        self.assertEqual(v['mode'],'config')
    def test_operator_is_required_for_sending_strategy(self):
        for value in ['', '   ']:
            self.assertIn('error',self.call(context={'purpose':'YouTube','operator':value}))
    def full(self, config=CONFIG, discover=False):
        code='''require $argv[1].'/share-strategy.php';$config=stream_get_contents(STDIN);try{echo $argv[2]==='discover'?json_encode(AsusShareStrategy::discover($config)):AsusShareStrategy::fullConfig($config,['purpose'=>'all','operator'=>'Example ISP'],['core'=>'1.3.1-asus6+b16','web'=>'0.1.4']);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),'discover' if discover else 'full'],input=config,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)

    def test_discovery_returns_present_nonempty_blocks_for_checkboxes(self):
        v=self.full(CONFIG+'\n',True)
        self.assertEqual([x['key'] for x in v['blocks']],['NFQWS_ARGS','NFQWS_ARGS_QUIC','NFQWS_ARGS_UDP','NFQWS_ARGS_CUSTOM'])
        v=self.full('NFQWS_ARGS="--filter-tcp=443"\nNFQWS_ARGS_CUSTOM=""',True)
        self.assertEqual([x['key'] for x in v['blocks']],['NFQWS_ARGS'])

    def test_full_config_is_separate_redacted_export_and_preserves_mode_definitions(self):
        v=self.full(CONFIG+'PASSWORD="PRIVATE_CANARY_PASSWORD"\n')
        self.assertEqual(v['mode'],'config');self.assertNotIn('blocks',v)
        self.assertIn('NFQWS_ARGS_QUIC=',v['config']);self.assertIn('MODE_LIST=',v['config'])
        self.assertIn('$MODE_LIST',v['config'])
        self.assertNotIn('PRIVATE_CANARY',json.dumps(v));self.assertNotIn('192.168.99.1',json.dumps(v))
        self.assertNotIn('/opt/private',json.dumps(v));self.assertGreater(v['omitted_options'],0)
        self.assertNotIn('region',v)

    def call(self,config=CONFIG,keys=None,context=None,edited=None):
        data={'config':config,'keys':keys or ['NFQWS_ARGS'],'context':{'operator':'Example ISP',**(context if context is not None else {'purpose':'YouTube'})},'edited':edited}
        code='''require $argv[1].'/share-strategy.php';$v=json_decode(stream_get_contents(STDIN),true);try{$draft=AsusShareStrategy::draft($v['config'],$v['keys']);if($v['edited']!==null)$draft['blocks'][0]['value']=$v['edited'];$raw=AsusShareStrategy::prepare($draft,$v['context'],['core'=>'1.3.1-asus6+b15','web'=>'0.1.4']);echo $raw;}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(data),capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)

    def test_only_selected_blocks_with_resource_aliases_leave_router(self):
        v=self.call()
        self.assertEqual(v['type'],'nfqws2_strategy')
        self.assertEqual([b['key'] for b in v['blocks']],['NFQWS_ARGS'])
        self.assertIn('--filter-tcp=443',v['blocks'][0]['value'])
        self.assertNotIn('PRIVATE_CANARY',json.dumps(v));self.assertNotIn('192.168.99',json.dumps(v))
        self.assertNotIn('/opt/private',json.dumps(v));self.assertTrue(v['dependencies'])
        self.assertFalse(v['dependencies'][0]['included'])

    def test_prefilled_region_is_absent_without_separate_consent(self):
        for ctx in [{'purpose':'YouTube','region':'PRIVATE_LOCATION'},{'purpose':'YouTube','region':'PRIVATE_LOCATION','share_location':False}]:
            v=self.call(context=ctx)
            self.assertNotIn('region',v);self.assertNotIn('PRIVATE_LOCATION',json.dumps(v))

    def test_user_edited_region_sent_only_with_checked_consent(self):
        v=self.call(context={'purpose':'YouTube','region':'Москва, исправлено','share_location':True})
        self.assertEqual(v['region'],'Москва, исправлено')
        self.assertNotIn('share_location',v)
        self.assertIn('error',self.call(context={'purpose':'YouTube','region':'Москва','share_location':'yes'}))

    def test_all_four_blocks_and_explicit_edit_do_not_change_source(self):
        v=self.call(keys=['NFQWS_ARGS','NFQWS_ARGS_QUIC','NFQWS_ARGS_UDP','NFQWS_ARGS_CUSTOM'])
        self.assertEqual(len(v['blocks']),4)
        self.assertIn('--out-range=<n2',v['blocks'][2]['value'])
        edited=self.call(edited='--filter-tcp=80 --dpi-desync=fake')
        self.assertEqual(edited['blocks'][0]['value'],'--filter-tcp=80 --dpi-desync=fake')

    def test_command_substitution_credentials_and_unknown_keys_refused(self):
        for text in ['--filter-tcp=$(touch /tmp/SHOULD_NEVER_EXIST)','--password=SECRET','--filter-tcp=`id`']:
            self.assertIn('error',self.call(edited=text))
        self.assertIn('error',self.call(keys=['ISP_INTERFACE']))
        self.assertIn('error',self.call(context={'purpose':'YouTube','latitude':55}))

    def test_unknown_variable_is_dependency_not_private_value(self):
        v=self.call(config='PRIVATE_VAR="PRIVATE_CANARY"\nNFQWS_ARGS="--filter-tcp=443 $PRIVATE_VAR"')
        self.assertNotIn('PRIVATE_CANARY',json.dumps(v))
        self.assertEqual(v['dependencies'][0]['kind'],'variable')
        self.assertNotIn('PRIVATE_VAR',json.dumps(v))

    def test_required_purpose_field_limits_and_closed_schema(self):
        from jsonschema import Draft202012Validator
        self.assertIn('error',self.call(context={}))
        self.assertIn('error',self.call(context={'purpose':'x'*121}))
        self.assertIn('error',self.call(context={'purpose':'test','comment':'x'*2001}))
        v=self.call(context={'purpose':'x'*120,'comment':'x'*2000})
        schema=json.loads((ROOT/'support/strategy.schema.json').read_text())
        self.assertTrue(Draft202012Validator(schema).is_valid(v))
        v['auth']='PRIVATE_CANARY';self.assertFalse(Draft202012Validator(schema).is_valid(v))
