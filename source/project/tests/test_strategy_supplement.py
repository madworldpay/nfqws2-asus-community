"""Data-only supplement preview: exact base/CAS, scope and launcher boundary."""
import hashlib,json,os,re,shlex,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC,ROOT

STOCK={
 '/opt/etc/nfqws2/lua/zapret-lib.lua':'6bf528fef1f0fc3c65e189216fc8a06bb873f6e25d1c29d2bfa4695a09b73440',
 '/opt/etc/nfqws2/lua/zapret-antidpi.lua':'6d1fa9168e5de1682fef91fd174f68b58c50f6739ef00f42ca7db2b940b6246d',
 '/opt/etc/nfqws2/lists/user.list':'1'*64,'/opt/etc/nfqws2/lists/auto.list':'2'*64,
 '/opt/etc/nfqws2/lists/exclude.list':'3'*64}
BASE='''# Preserve this router setting and comment.
ISP_INTERFACE="br-test"
USER="nobody"
NFQUEUE_NUM=300
NFQWS_BASE_ARGS="--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua"
NFQWS_ARGS="--filter-tcp=80,443 --lua-desync=multisplit:pos=2"
NFQWS_ARGS_QUIC="--filter-udp=443 --lua-desync=fake:blob=fake_default_quic:repeats=2"
NFQWS_ARGS_UDP=""
NFQWS_ARGS_CUSTOM="--filter-tcp=443 --hostlist-domains=base.example --lua-desync=multidisorder:pos=2"
NFQWS_EXTRA_ARGS="--hostlist=/opt/etc/nfqws2/lists/user.list --hostlist-auto=/opt/etc/nfqws2/lists/auto.list --hostlist-exclude=/opt/etc/nfqws2/lists/exclude.list"
NFQWS_ARGS_IPSET=""
TCP_PORTS="80,443"
UDP_PORTS="443"
'''
RECIPE={'http':{'method':'pass'},'tls':{'method':'multisplit','pos':'2'},'quic':{'method':'fake','repeats':2}}

def resource_sha(resources):
 return hashlib.sha256(json.dumps(resources,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

class SupplementTests(unittest.TestCase):
 def preview(self,current=BASE,recipe=None,domains=None,resources=None,binding=None):
  resources=STOCK if resources is None else resources
  binding=binding or {'config_sha256':hashlib.sha256(current.encode()).hexdigest(),'resources_sha256':resource_sha(resources)}
  payload={'current':current,'recipe':RECIPE if recipe is None else recipe,'domains':['target.example']if domains is None else domains,'resources':resources,'binding':binding}
  code="""require $argv[1].'/strategy-synthesis.php';$x=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);if(!method_exists('NfqwsStrategySynthesis','supplementPreview')){echo json_encode(['missing_api'=>true]);exit;}try{$r=NfqwsStrategySynthesis::supplementPreview($x['current'],$x['recipe'],$x['domains'],$x['resources'],$x['binding']);echo json_encode(['result'=>$r,'parsed'=>AsusImportConfig::parse($r['candidate_config'])]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
  p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(payload),capture_output=True,text=True,timeout=25)
  self.assertEqual(p.returncode,0,p.stderr+p.stdout);self.assertEqual(p.stderr,'');out=json.loads(p.stdout)
  self.assertNotIn('missing_api',out,'missing supplement preview API')
  return out
 def good(self,**kw):
  out=self.preview(**kw);self.assertNotIn('error',out,out);return out
 def refused(self,**kw):self.assertIn('error',self.preview(**kw))
 def test_priority_profiles_precede_exact_original_CUSTOM_and_preserve_other_lines(self):
  out=self.good();r=out['result'];old='--filter-tcp=443 --hostlist-domains=base.example --lua-desync=multidisorder:pos=2'
  self.assertEqual(r['changed_keys'],['NFQWS_ARGS_CUSTOM']);self.assertTrue(out['parsed']['NFQWS_ARGS_CUSTOM'].endswith(' --new '+old))
  self.assertEqual(out['parsed']['NFQWS_ARGS'],'--filter-tcp=80,443 --lua-desync=multisplit:pos=2')
  for line in BASE.splitlines():
   if not line.startswith('NFQWS_ARGS_CUSTOM='):self.assertIn(line,r['candidate_config'].splitlines())
 def test_added_rules_have_explicit_domain_IPV4_scope_and_no_AUTO_or_include_union(self):
  r=self.good()['result'];self.assertEqual(len(r['added_profiles']),2)
  for rule in r['added_profiles']:
   self.assertIn('--filter-l3=ipv4',rule);self.assertIn('--hostlist-domains=target.example',rule)
   self.assertIn('--hostlist-exclude=/opt/etc/nfqws2/lists/exclude.list',rule)
   self.assertIn('--hostlist-exclude-domains=t.me,telegram.org,telegram.me,telesco.pe',rule)
   self.assertNotIn('--hostlist-auto=',rule);self.assertNotIn('--hostlist=/opt/etc/nfqws2/lists/user.list',rule)
 def test_changed_original_bytes_or_resource_inventory_invalidates_preview_CAS(self):
  binding={'config_sha256':hashlib.sha256(BASE.encode()).hexdigest(),'resources_sha256':resource_sha(STOCK)}
  self.refused(current=BASE+'\n',binding=binding);files=dict(STOCK);files['/opt/etc/nfqws2/lists/exclude.list']='4'*64;self.refused(resources=files,binding=binding)
 def test_ports_are_never_widened_to_make_candidate_work(self):
  self.refused(current=BASE.replace('TCP_PORTS="80,443"','TCP_PORTS="80"'))
  self.refused(current=BASE.replace('UDP_PORTS="443"','UDP_PORTS="3478"'))
  r=self.good()['parsed'];self.assertEqual(r['TCP_PORTS'],'80,443');self.assertEqual(r['UDP_PORTS'],'443')
 def test_unknown_Lua_templates_or_global_profile_filters_refuse(self):
  mutations=[BASE.replace('--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua','--lua-init=evil()'),BASE.replace('--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua','--lua-init=@/opt/etc/nfqws2/lua/custom.lua'),BASE.replace('--filter-tcp=80,443','--template=site --filter-tcp=80,443'),BASE.replace('--filter-tcp=80,443','--skip --filter-tcp=80,443'),BASE.replace('NFQWS_BASE_ARGS="','NFQWS_BASE_ARGS="--filter-tcp=~443 '),BASE.replace('NFQWS_ARGS_CUSTOM="','NFQWS_ARGS_CUSTOM="--new=3 ')]
  for current in mutations:
   with self.subTest(current=current):self.refused(current=current)
 def test_unknown_or_changed_stock_initializer_digest_refuses_even_if_name_matches(self):
  files=dict(STOCK);files['/opt/etc/nfqws2/lua/zapret-lib.lua']='5'*64;self.refused(resources=files)
  self.refused(current=BASE.replace('--lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua','--lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua'))
 def test_domain_boundary_never_promotes_IP_telegram_or_injected_scope(self):
  for domains in [[],['1.1.1.1'],['t.me'],['api.telegram.org'],['target.example --hostlist-auto=/tmp/x'],[f'n{i}.example'for i in range(6)]]:
   with self.subTest(domains=domains):self.refused(domains=domains)
 def test_shared_filters_or_unbound_paths_cannot_be_silently_bypassed(self):
  self.refused(current=BASE.replace('NFQWS_EXTRA_ARGS="','NFQWS_EXTRA_ARGS="--filter-mark=0x1 '))
  self.refused(current=BASE.replace('/opt/etc/nfqws2/lists/exclude.list','/tmp/unbound.list'))
  files=dict(STOCK);del files['/opt/etc/nfqws2/lists/exclude.list'];self.refused(resources=files)
 def test_generated_override_or_unknown_base_program_is_not_arbitrary_concatenation(self):
  recipe=dict(RECIPE);recipe['overrides']=[{'protocol':'tls','domains':['other.example'],'component':{'method':'pass'}}];self.refused(recipe=recipe)
  self.refused(current=BASE.replace('--lua-desync=multidisorder:pos=2','--lua-desync=condition:luaexec=evil()'))
  self.refused(current=BASE.replace('NFQWS_BASE_ARGS="','NFQWS_BASE_ARGS="--blob=fake_default_tls:@/opt/etc/nfqws2/blobs/custom.bin '))
 def test_all_pass_or_profile_budget_exhaustion_produces_no_candidate(self):
  self.refused(recipe={'http':{'method':'pass'},'tls':{'method':'pass'},'quic':{'method':'pass'}})
  many=' --new '.join(['--filter-tcp=443 --lua-desync=pass']*23)
  current=re.sub(r'^NFQWS_ARGS_CUSTOM=.*$',lambda _: 'NFQWS_ARGS_CUSTOM="'+many+'"',BASE,flags=re.M);self.refused(current=current)
 def test_preview_deterministic_bound_to_scope_and_never_proves_apply_export_or_traffic(self):
  a=self.good(domains=['z.example','a.example'])['result'];b=self.good(domains=['a.example','z.example'],resources=dict(reversed(list(STOCK.items()))))['result'];self.assertEqual(a,b)
  for key in ('can_apply','can_export','combined_verified','resources_bundled','actual_device_calls'):self.assertIs(a[key],False,key)
  self.assertEqual(a['domains'],['a.example','z.example']);self.assertNotEqual(a['preview_sha256'],self.good(domains=['other.example'])['result']['preview_sha256'])
 def test_actual_common_launcher_keeps_new_priority_before_entire_original_suffix(self):
  out=self.good();function=re.search(r'^_startup_args\(\) \{.*?^\}',(ROOT/'core/etc/init.d/common').read_text(),re.M|re.S).group()
  values=out['parsed'];script='\n'.join(k+'='+shlex.quote(v)for k,v in values.items())+'\nUSER=nobody\nNFQUEUE_NUM=300\nISP_INTERFACE=br-test\nLOG_LEVEL=0\n'+function+'\n_startup_args\n'
  p=subprocess.run(['/bin/sh'],input=script,text=True,capture_output=True,timeout=5);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'')
  args=p.stdout.strip();self.assertLess(args.index('--hostlist-domains=target.example'),args.index('--hostlist-domains=base.example'));self.assertIn('--filter-tcp=80,443 --lua-desync=multisplit:pos=2 --hostlist=/opt/etc/nfqws2/lists/user.list --hostlist-auto=/opt/etc/nfqws2/lists/auto.list --hostlist-exclude=/opt/etc/nfqws2/lists/exclude.list',args)

if __name__=='__main__':unittest.main()
