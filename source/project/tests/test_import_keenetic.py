"""Keenetic strategy text becomes inert selective-import data with exact dependencies."""
import base64,json,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC

FULL='''# full Keenetic NFQWS2 configuration
USER="nobody"
ISP_INTERFACE="ppp0"
POLICY_NAME="KeeneticPolicy"
NFQUEUE_NUM="200"
TCP_PORTS="80,443"
UDP_PORTS="443,50000:50100"
MODE_LIST="--hostlist=custom.list"
MODE_ALL=""
MODE_AUTO="--hostlist-auto=auto.list"
NFQWS_BASE_ARGS="--lua-init=@zapret-lib.lua --lua-init=@zapret-antidpi.lua --blob=hello:@custom-tls.bin"
NFQWS_EXTRA_ARGS="$MODE_LIST"
NFQWS_ARGS_IPSET="--ipset-exclude=ipset_exclude.list"
NFQWS_ARGS="
# HTTPS
 --filter-tcp=443 \\
 --lua-desync=fake:blob=hello
"
NFQWS_ARGS_QUIC="--filter-udp=443 --lua-desync=fake:blob=fake_default_quic"
NFQWS_ARGS_UDP=""
NFQWS_ARGS_CUSTOM="--filter-tcp=80 --lua-desync=multisplit --new --filter-tcp=8443 --lua-desync=fake:blob=fake_default_tls"
'''
CURRENT='ASUS_CLIENTS4="192.0.2.2"\nISP_INTERFACE="eth9"\nNFQUEUE_NUM=300\nNFQWS_ARGS="--filter-tcp=80"\n'
class KeeneticImportTests(unittest.TestCase):
 def call(self,text=FULL,profile='asus-entware',inventory=None,prepare=False):
  code="""$file=$argv[1].'/import-keenetic.php';if(!is_file($file)){echo json_encode(['error'=>'missing_feature']);exit;}require $file;require $argv[1].'/import-plan.php';try{$v=json_decode(stream_get_contents(STDIN),true);$text=isset($v['text_base64'])?base64_decode($v['text_base64'],true):$v['text'];$raw=AsusImportKeenetic::convert($text,$v['profile']);$doc=AsusImportDocument::read([$raw]);$out=['document'=>$raw,'parsed'=>$doc];
  if($v['prepare']){$sel=['blocks'=>[],'shared'=>[],'ports'=>[],'files'=>[],'dns'=>[],'allow_shared_impact'=>true,'allow_incomplete'=>true,'trusted_lua'=>true];foreach($doc['values']as $key=>$value)$sel[in_array($key,AsusImportConfig::BLOCKS,true)?'blocks':'shared'][]=['key'=>$key,'value'=>$value];foreach($doc['ports']as $key=>$value)$sel['ports'][]=['key'=>$key,'value'=>$value];$out['plan']=AsusImportPlan::prepare($doc,$sel,$v['current'],$v['inventory'],null,$v['profile']);}echo json_encode($out,JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
  p=subprocess.run([PHP,'-n','-d','memory_limit=32M','-r',code,str(PUBLIC)],input=json.dumps({'text':text if isinstance(text,str)else None,**({'text_base64':base64.b64encode(text).decode()}if isinstance(text,bytes)else{}),'profile':profile,'current':CURRENT,'inventory':{'files':inventory or [],'scan_truncated':False},'prepare':prepare}),text=True,capture_output=True,timeout=10);self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
 def inventory(self):
  return [{'id':str(i)*32,'kind':kind,'name':name,'sha256':'a'*64,'state':'available','byte_length':1,**({'bundled_lua':True}if kind=='lua'else{})}for i,(kind,name)in enumerate([('lua','zapret-lib.lua'),('lua','zapret-antidpi.lua'),('blobs','custom-tls.bin'),('lists','custom.list'),('lists','auto.list'),('lists','ipset_exclude.list')],1)]
 def test_full_literal_configuration_retains_all_strategy_groups_and_excludes_router_identity(self):
  v=self.call();self.assertNotIn('error',v);doc=json.loads(v['document']);self.assertEqual(doc['schema_version'],2);self.assertEqual(doc['mode'],'config');self.assertEqual(set(doc['versions']),{'core','web'});self.assertTrue(doc['purpose']);self.assertTrue(doc['operator']);parsed=v['parsed'];self.assertEqual(set(parsed['values']),{'NFQWS_ARGS','NFQWS_ARGS_QUIC','NFQWS_ARGS_UDP','NFQWS_ARGS_CUSTOM','NFQWS_BASE_ARGS','NFQWS_EXTRA_ARGS','NFQWS_ARGS_IPSET','MODE_LIST','MODE_ALL','MODE_AUTO'});self.assertEqual(parsed['ports'],{'TCP_PORTS':'80,443','UDP_PORTS':'443,50000:50100'});self.assertEqual(parsed['values']['NFQWS_ARGS'],'--filter-tcp=443 --lua-desync=fake:blob=hello');self.assertNotIn('HTTPS',doc['config']);self.assertNotIn('KeeneticPolicy',doc['config']);self.assertNotIn('ppp0',doc['config']);self.assertNotIn('NFQUEUE_NUM',doc['config']);self.assertNotIn('USER=',doc['config'])
 def test_raw_multiline_options_are_one_custom_block_and_keep_all_new_profiles(self):
  raw='# HTTPS\n--filter-tcp=443 \\\n --lua-desync=fake:blob=fake_default_tls\n# second\n--new --filter-udp=443 --lua-desync=fake:blob=fake_default_quic'
  v=self.call(raw);self.assertNotIn('error',v);self.assertEqual(v['parsed']['values'],{'NFQWS_ARGS_CUSTOM':'--filter-tcp=443 --lua-desync=fake:blob=fake_default_tls --new --filter-udp=443 --lua-desync=fake:blob=fake_default_quic'});self.assertEqual(v['parsed']['ports'],[])
 def test_known_relative_operands_normalize_only_resource_paths_and_keep_custom_names(self):
  raw='--filter-tcp=443 --hostlist=lists/custom.list --hostlist-exclude excluded.list --lua-init @lua/custom.lua --blob custom:@blobs/my-client.bin --lua-desync=fake:blob=custom --comment=/opt/etc/nfqws2/blobs/not-a-reference.bin'
  for profile,prefix in [('asus-entware','/opt/etc/nfqws2'),('openwrt','/etc/nfqws2')]:
   v=self.call(raw,profile);self.assertNotIn('error',v);value=v['parsed']['values']['NFQWS_ARGS_CUSTOM'];self.assertIn('--hostlist='+prefix+'/lists/custom.list',value);self.assertIn('--hostlist-exclude '+prefix+'/lists/excluded.list',value);self.assertIn('--lua-init @'+prefix+'/lua/custom.lua',value);self.assertIn('--blob custom:@'+prefix+'/blobs/my-client.bin',value);self.assertIn('--comment=/opt/etc/nfqws2/blobs/not-a-reference.bin',value)
 def test_canonical_absolute_paths_adapt_both_directions_without_other_replacements(self):
  text='--filter-tcp=443 --lua-init=@/opt/etc/nfqws2/lua/a.lua --blob=x:@/etc/nfqws2/blobs/x.bin --hostlist=/etc/nfqws2/lists/x.list --lua-desync=fake:blob=x'
  for profile,prefix in [('asus-entware','/opt/etc/nfqws2'),('openwrt','/etc/nfqws2')]:
   v=self.call(text,profile);self.assertNotIn('error',v);value=v['parsed']['values']['NFQWS_ARGS_CUSTOM'];self.assertIn('--lua-init=@'+prefix+'/lua/a.lua',value);self.assertIn('--blob=x:@'+prefix+'/blobs/x.bin',value);self.assertIn('--hostlist='+prefix+'/lists/x.list',value)
 def test_missing_lua_blob_and_list_each_block_existing_preview_without_guessing_replacements(self):
  rows=self.inventory()
  for name in ['zapret-antidpi.lua','custom-tls.bin','custom.list']:
   v=self.call(inventory=[x for x in rows if x['name']!=name],prepare=True);self.assertNotIn('error',v);self.assertFalse(v['plan']['ready']);self.assertIn(name,[x.get('name')for x in v['plan']['problems']if x['code']=='unresolved_file']);self.assertIn('custom-tls.bin',v['document']);self.assertNotIn('fake_default_tls.bin',v['document'])
 def test_available_standard_dependencies_pass_existing_preview_and_leave_local_identity_intact(self):
  for profile in ['asus-entware','openwrt']:
   v=self.call(inventory=self.inventory(),prepare=True,profile=profile);self.assertNotIn('error',v);self.assertTrue(v['plan']['ready'],v['plan']);self.assertIn('ASUS_CLIENTS4="192.0.2.2"',v['plan']['config']);self.assertIn('ISP_INTERFACE="eth9"',v['plan']['config']);self.assertIn('NFQUEUE_NUM=300',v['plan']['config'])
 def test_v1_process_flags_commands_unresolved_variables_and_ambiguous_formats_are_refused(self):
  samples=['','ordinary text','--filter-tcp=443','--lua-desync=fake','NFQWS_ARGS="--dpi-desync=fake"','--filter-tcp=443 --dpi-desync=fake','NFQWS_ARGS="--filter-tcp=443 --lua-desync=fake"\ntouch /tmp/IMPORT_CONVERT_CANARY','NFQWS_ARGS="$(touch /tmp/IMPORT_CONVERT_CANARY)"','NFQWS_ARGS="`id`"','NFQWS_ARGS="$UNKNOWN"','NFQWS_ARGS="--lua-desync=fake"\nUSER="$(id)"','NFQWS_ARGS="--lua-desync=fake"\nNFQWS_ARGS="again"','--filter-tcp=443 --lua-desync=fake ; id','--filter-tcp=443 --lua-desync=fake | sh','--filter-tcp=443 --lua-init=print(1) --lua-desync=fake']
  for flag in ['--qnum=200','--user=nobody','--daemon','--bind-fix4','--pidfile=/tmp/pid','--fwmark=2','--chdir=/tmp']:
   samples.extend(['--filter-tcp=443 --lua-desync=fake '+flag,'NFQWS_ARGS_CUSTOM="--filter-tcp=443 --lua-desync=fake '+flag+'"'])
  for text in samples:
   with self.subTest(text=text):self.assertEqual(self.call(text),{'error':'unsupported_keenetic_strategy'})
 def test_invalid_utf8_controls_length_and_expansion_bombs_are_bounded(self):
  samples=[b'NFQWS_ARGS="\xff"','NFQWS_ARGS="--lua-desync=fake"\x00','x'*65537,'NFQWS_ARGS="--lua-desync=fake\x01"']
  keys=['MODE_LIST','MODE_ALL','MODE_AUTO','NFQWS_EXTRA_ARGS','NFQWS_BASE_ARGS','NFQWS_ARGS'];lines=[keys[0]+'="'+'x'*3000+'"']+[keys[i]+'="$'+keys[i-1]+' $'+keys[i-1]+'"' for i in range(1,len(keys))];samples.append('\n'.join(lines))
  for text in samples:
   with self.subTest(length=len(text)):self.assertEqual(self.call(text),{'error':'unsupported_keenetic_strategy'})

 def test_input_commands_are_never_executed_or_written(self):
  with tempfile.TemporaryDirectory()as directory:
   marker=Path(directory)/'executed'
   for text in ['NFQWS_ARGS="$(touch '+str(marker)+')"','--filter-tcp=443 --lua-desync=fake; touch '+str(marker)]:self.assertEqual(self.call(text),{'error':'unsupported_keenetic_strategy'});self.assertFalse(marker.exists())
 def test_missing_known_option_operands_and_foreign_output_paths_are_refused(self):
  for options in ['--lua-desync','--filter-tcp','--hostlist-auto-debug=/etc/shadow','--skip=1']:
   text='NFQWS_ARGS="--filter-tcp=443 --lua-desync=fake '+options+'"'
   with self.subTest(options=options):self.assertEqual(self.call(text),{'error':'unsupported_keenetic_strategy'})
 def test_literal_escaped_variables_are_refused_instead_of_becoming_other_blocks(self):
  text='NFQWS_ARGS_CUSTOM="--filter-tcp=443 --lua-desync=fake"\nNFQWS_ARGS="\\$NFQWS_ARGS_CUSTOM"\n'
  self.assertEqual(self.call(text),{'error':'unsupported_keenetic_strategy'})
 def test_complete_pinned_core_configuration_converts_and_previews_with_stock_dependencies(self):
  root=PUBLIC.parents[2];text=(root/'core/etc/nfqws2/nfqws2.conf').read_text();stock=[]
  for i,name in enumerate(['zapret-lib.lua','zapret-antidpi.lua','zapret-auto.lua'],1):stock.append({'id':str(i)*32,'kind':'lua','name':name,'sha256':'a'*64,'state':'available','byte_length':1,'bundled_lua':True})
  for kind,names in [('blobs',['tls_clienthello.bin','quic_initial.bin']),('lists',['user.list','exclude.list','auto.list','ipset.list','ipset_exclude.list'])]:
   for name in names:stock.append({'id':f'{len(stock)+1:032x}','kind':kind,'name':name,'sha256':'b'*64,'state':'available','byte_length':1})
  for profile in ['asus-entware','openwrt']:
   with self.subTest(profile=profile):
    v=self.call(text,profile,inventory=stock,prepare=True);self.assertNotIn('error',v);self.assertTrue(v['plan']['ready'],v['plan']);self.assertEqual(v['plan']['warnings'],[]);self.assertIn('--out-range=<n2',v['parsed']['values']['NFQWS_ARGS_UDP']);self.assertNotIn('# HTTPS',v['parsed']['values']['NFQWS_ARGS']);self.assertIn('--lua-desync=hostfakesplit:host=ozon.ru:midhost=host-2:seqovl=sniext+3:seqovl_pattern=tls_clienthello:badsum:tcp_md5:tcp_ts_up:strategy=3',v['parsed']['values']['NFQWS_ARGS']);self.assertIn('--lua-desync=fake:blob=0x00000000:tcp_ack=-66000:tls_mod=rnd,dupsid,sni=www.google.com:repeats=2:strategy=2',v['parsed']['values']['NFQWS_ARGS'])
 def test_literal_packet_ranges_are_preserved_only_in_their_known_operands(self):
  for suffix in ['--out-range=<n2','--in-range=n1<n5','--out-range <n2','--in-range <s100']:
   text='--filter-tcp=443 --lua-desync=fake '+suffix
   with self.subTest(suffix=suffix):
    v=self.call(text);self.assertNotIn('error',v);self.assertTrue(v['parsed']['values']['NFQWS_ARGS_CUSTOM'].endswith(suffix))
 def test_range_lookalikes_and_standalone_shell_redirections_remain_refused(self):
  for suffix in ['< /etc/shadow','> /tmp/output','</etc/shadow','>/tmp/output','--comment=<n2','--lua-desync=fake:pos=<n2','--out-range=</etc/shadow','--out-range=<n2>/tmp/output','--out-range=<<n2','--in-range=bad<n2','--out-range=>n2','--out-range < /etc/shadow']:
   with self.subTest(suffix=suffix):self.assertEqual(self.call('--filter-tcp=443 --lua-desync=fake '+suffix),{'error':'unsupported_keenetic_strategy'})
 def test_getopt_long_only_abbreviations_and_unknown_options_are_rejected(self):
  options=['--lua-ini=io.output[[/tmp/IMPORT_CANARY]]','--debu=@/tmp/IMPORT_CANARY','--hostlist-auto-debu=/tmp/IMPORT_CANARY','--qnu=222','--use=nobody','--pidfil=/tmp/foreign.pid','--totally-unknown=value','--lua-desyn=fake','--writabl=/tmp/foreign','--intercep=0','--fuz=1','--intercept=0','--writable=/tmp/foreign','--fuzz=/tmp/foreign']
  for option in options:
   for text in ['--filter-tcp=443 --lua-desync=fake '+option,'NFQWS_ARGS_CUSTOM="--filter-tcp=443 --lua-desync=fake '+option+'"']:
    with self.subTest(option=option,full=text.startswith('NFQWS')):self.assertEqual(self.call(text),{'error':'unsupported_keenetic_strategy'})
 def test_exact_long_options_remain_available_with_their_existing_operand_guards(self):
  text='--filter-tcp=443 --filter-l7=tls --new=tls-profile --name=tls-profile --lua-gc=60 --ctrack-timeouts=60:300:60:60 --reasm-disable=quic_initial --payload=tls_client_hello --in-range=n1<n5 --out-range=<n2 --hostlist-domains=example.org --hostlist-auto-fail-threshold=3 --debug=0 --hostlist-auto-debug=/opt/var/log/nfqws2.log --lua-init=@zapret-lib.lua --blob=custom:@my.bin --lua-desync=fake:blob=custom'
  v=self.call(text);self.assertNotIn('error',v);self.assertIn('--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua',v['parsed']['values']['NFQWS_ARGS_CUSTOM']);self.assertIn('--debug=0',v['parsed']['values']['NFQWS_ARGS_CUSTOM']);self.assertIn('--lua-desync=fake:blob=custom',v['parsed']['values']['NFQWS_ARGS_CUSTOM'])
