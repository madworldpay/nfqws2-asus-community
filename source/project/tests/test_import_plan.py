"""Selective import maps exact resource bytes and preserves local router settings."""
import base64,copy,hashlib,json,subprocess,unittest
from test_import_document import PHP,PUBLIC,STRATEGY,CTX

BLOB=b'\0HELLO\xff';LUA=b'function imported() return 1 end\n'
def documents():
 s=copy.deepcopy(STRATEGY);s['blocks'][0]['value']='--filter-tcp=443 --lua-desync=fake:blob=hello';s['shared']={'NFQWS_BASE_ARGS':'--blob=hello:RESOURCE_1 --lua-init=RESOURCE_2'};s['dependencies']=[{'id':a,'kind':k,'included':True}for a,k in [('RESOURCE_1','file'),('RESOURCE_2','file'),('BLOB_3','blob')]]
 rows=[]
 for n,(kind,name,raw,aliases)in enumerate([('blobs','hello.bin',BLOB,['RESOURCE_1','BLOB_3']),('lua','custom.lua',LUA,['RESOURCE_2'])],1):
  sha=hashlib.sha256(raw).hexdigest();rows.append({'id':str(n)*32,'kind':kind,'name':name,'encoding':'base64'if kind=='blobs'else'utf8','source_sha256':sha,'sha256':sha,'byte_length':len(raw),'data_base64':base64.b64encode(raw).decode(),'aliases':aliases})
 r={'type':'nfqws2_resources','schema_version':1,'context':CTX,'files':rows,'audit':{'scope':'static_explicit_references','references':[{'id':f'dependency_{i+1}','aliases':row['aliases'],'resource_id':row['id'],'state':'included'}for i,row in enumerate(rows)],'unresolved':[],'missing_reason':'','complete':True}}
 return [json.dumps(s),json.dumps(r)]
CURRENT='# untouched\nASUS_CLIENTS4="192.0.2.4"\nISP_INTERFACE="eth9"\nNFQUEUE_NUM=300\nNFQWS_BASE_ARGS=""\nNFQWS_ARGS="--filter-tcp=80"\nNFQWS_ARGS_UDP="--filter-udp=443"\nTCP_PORTS=80\n'
def selection(**updates):
 s={'blocks':[{'key':'NFQWS_ARGS','value':'--filter-tcp=443 --lua-desync=fake:blob=hello'}],'shared':[{'key':'NFQWS_BASE_ARGS','value':'--blob=hello:RESOURCE_1 --lua-init=RESOURCE_2'}],'ports':[],'files':[{'id':'1'*32},{'id':'2'*32}],'dns':[],'allow_shared_impact':True,'allow_incomplete':True,'trusted_lua':True};s.update(updates);return s

class ImportPlanTests(unittest.TestCase):
 def call(self,sel=None,docs=None,inventory=None,current=CURRENT,draft=None):
  data={'documents':documents()if docs is None else docs,'selection':selection()if sel is None else sel,'current':current,'inventory':{'files':[],'skipped':0,'scan_truncated':False}if inventory is None else inventory,'draft':draft}
  code="""$p=$argv[1].'/import-plan.php';if(!is_file($p)){echo json_encode(['error'=>'missing_feature']);exit;}require $p;try{$v=json_decode(stream_get_contents(STDIN),true);echo json_encode(AsusImportPlan::prepare(AsusImportDocument::read($v['documents']),$v['selection'],$v['current'],$v['inventory'],$v['draft']),JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
  p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(data),capture_output=True,text=True,timeout=10);self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
 def test_exact_file_bindings_and_local_settings_preserved(self):
  p=self.call();self.assertNotIn('error',p);self.assertTrue(p['ready'],p);self.assertIn('ASUS_CLIENTS4="192.0.2.4"',p['config']);self.assertIn('ISP_INTERFACE="eth9"',p['config']);self.assertIn('NFQUEUE_NUM=300',p['config']);self.assertIn('NFQWS_ARGS_UDP="--filter-udp=443"',p['config']);self.assertEqual(len(p['files']),2)
  self.assertIn('--blob=hello:@/opt/etc/nfqws2/blobs/hello.bin',p['config']);self.assertIn('--lua-init=@/opt/etc/nfqws2/lua/custom.lua',p['config']);self.assertNotIn('RESOURCE_',p['config']);self.assertEqual(base64.b64decode(p['files'][0]['data_base64']),BLOB)
 def test_missing_selection_lists_needed_files_and_globals(self):
  p=self.call(selection(shared=[],files=[]));self.assertNotIn('error',p);self.assertFalse(p['ready']);self.assertIn('NFQWS_BASE_ARGS',p['required']['shared']);self.assertEqual(set(p['required']['files']),{'1'*32,'2'*32})
 def test_matching_bytes_reused_and_changed_bytes_replace_same_name(self):
  row={'id':'a'*32,'kind':'blobs','name':'hello.bin','sha256':hashlib.sha256(BLOB).hexdigest(),'state':'available','byte_length':len(BLOB)}
  p=self.call(inventory={'files':[row],'scan_truncated':False,'skipped':0});self.assertTrue(p['ready']);self.assertTrue(p['files'][0]['reuse']);self.assertEqual(p['files'][0]['path'],'/opt/etc/nfqws2/blobs/hello.bin')
  row['sha256']='0'*64;p=self.call(inventory={'files':[row],'scan_truncated':False,'skipped':0});self.assertTrue(p['ready']);self.assertFalse(p['files'][0]['reuse']);self.assertEqual(p['files'][0]['path'],'/opt/etc/nfqws2/blobs/hello.bin');self.assertTrue(p['files'][0]['replace']);self.assertEqual(p['fingerprints']['files'][p['files'][0]['path']],'0'*64)
 def test_shared_change_requires_explicit_cross_block_consent(self):
  p=self.call(selection(allow_shared_impact=False));self.assertFalse(p['ready']);self.assertIn('shared_impact',[v['code']for v in p['problems']]);self.assertIn('NFQWS_ARGS_UDP',p['affected_blocks'])
 def test_lua_choice_requires_trust_and_unbound_blob_never_bypasses(self):
  p=self.call(selection(trusted_lua=False));self.assertFalse(p['ready']);self.assertIn('lua_trust',[v['code']for v in p['problems']])
  sel=selection(allow_incomplete=True);sel['blocks'][0]['value']='--lua-desync=fake:blob=not_defined';p=self.call(sel);self.assertFalse(p['ready']);self.assertIn('unresolved_blob',[v['code']for v in p['problems']])
 def test_resources_only_changes_no_config_and_no_service_action(self):
  p=self.call(selection(blocks=[],shared=[],files=[{'id':'1'*32}]),docs=documents());self.assertTrue(p['ready']);self.assertEqual(p['config'],CURRENT);self.assertIsNone(p['draft']);self.assertEqual(len(p['files']),1);self.assertNotIn('restart',json.dumps(p))
 def test_edited_text_copy_binds_new_hash_and_does_not_reuse_old_source(self):
  sel=selection(files=[{'id':'1'*32},{'id':'2'*32,'text':'return 2\n'}]);p=self.call(sel);self.assertTrue(p['ready']);row=p['files'][1];self.assertEqual(base64.b64decode(row['data_base64']),b'return 2\n');self.assertEqual(row['sha256'],hashlib.sha256(b'return 2\n').hexdigest())
 def test_unknown_fields_duplicate_selection_and_escape_are_rejected(self):
  for change in [{'extra':True},{'files':[{'id':'../'}]},{'blocks':[{'key':'ASUS_CLIENTS4','value':'x'}]},{'files':[{'id':'1'*32}]*2}]:
   self.assertIn('error',self.call(selection(**change)))
  sel=selection();sel['blocks'][0]['value']='--hostlist=/etc/shadow';p=self.call(sel);self.assertFalse(p['ready']);self.assertIn('unresolved_file',[v['code']for v in p['problems']])
 def test_empty_choice_cannot_create_noop_transaction(self):
  p=self.call(selection(blocks=[],shared=[],files=[],dns=[]));self.assertFalse(p['ready']);self.assertIn('empty_selection',[v['code']for v in p['problems']])
 def dns_input(self,default=True,partial=False):
  u={'id':'quad9','label':'Quad9','protocol':'dot','address':'9.9.9.9','port':853,'tls_name':'dns.quad9.net','url':'','bootstrap':[],'default':default,'domains':[{'name':'image.tmdb.org','include_subdomains':True}]}
  source={'id':'legacy','origin':'legacy','sha256':'a'*64,'profile':{'schema_version':1,'upstreams':[u],'records':[]},'complete':not partial,'warnings':[{'line':2,'code':'unsupported_directive'}]if partial else[],'scope':'upstreams_and_domain_rules'}
  d={'type':'nfqws2_dns','schema_version':1,'context':CTX,'sources':[source]}
  choice={'source_id':'legacy','source_sha256':'a'*64,'upstreams':[u],'records':[]}
  return [json.dumps(d)],selection(blocks=[],shared=[],files=[],dns=[choice],allow_incomplete=False)
 def test_dns_selection_creates_draft_only_with_sites_and_no_fake_default(self):
  docs,sel=self.dns_input();p=self.call(sel,docs=docs);self.assertNotIn('error',p);self.assertTrue(p['ready']);self.assertEqual(p['config'],CURRENT);self.assertEqual(p['draft']['upstreams'][0]['domains'][0]['name'],'image.tmdb.org');self.assertEqual(p['fingerprints']['draft'],None)
  docs,sel=self.dns_input(False);p=self.call(sel,docs=docs);self.assertFalse(p['ready']);self.assertIsNone(p['draft']);self.assertIn('invalid_dns_profile',[v['code']for v in p['problems']])
 def test_partial_dns_source_requires_explicit_incomplete_ack(self):
  docs,sel=self.dns_input(partial=True);p=self.call(sel,docs=docs);self.assertFalse(p['ready']);self.assertIn('incomplete_analysis',[v['code']for v in p['problems']]);sel['allow_incomplete']=True;self.assertTrue(self.call(sel,docs=docs)['ready'])
 def test_same_active_and_draft_dns_import_once_with_fixed_answers(self):
  docs,sel=self.dns_input();d=json.loads(docs[0]);source=d['sources'][0];source['id']='active';source['origin']='active';record={'name':'example.org','include_subdomains':True,'addresses':['192.0.2.8'],'checked_at':None};source['profile']['records']=[record]
  other=copy.deepcopy(source);other['id']='draft';other['origin']='draft';d['sources'].append(other)
  sel['dns']=[{'source_id':s['id'],'source_sha256':s['sha256'],'upstreams':s['profile']['upstreams'],'records':[{'index':0,'value':record}]}for s in d['sources']]
  p=self.call(sel,docs=[json.dumps(d)]);self.assertNotIn('error',p);self.assertTrue(p['ready'],p);self.assertEqual(len(p['draft']['upstreams']),1);self.assertEqual(p['draft']['records'],[record])
 def test_duplicate_sources_do_not_double_the_dns_server_limit(self):
  docs,sel=self.dns_input();d=json.loads(docs[0]);source=d['sources'][0];source['id']='active';source['origin']='active';u=source['profile']['upstreams'][0];source['profile']['upstreams']=[dict(u,id='dns'+str(i),address='192.0.2.'+str(i+1))for i in range(32)]
  other=copy.deepcopy(source);other['id']='draft';other['origin']='draft';d['sources'].append(other);sel['dns']=[{'source_id':s['id'],'source_sha256':s['sha256'],'upstreams':s['profile']['upstreams'],'records':[]}for s in d['sources']]
  p=self.call(sel,docs=[json.dumps(d)]);self.assertNotIn('error',p);self.assertTrue(p['ready'],p);self.assertEqual(len(p['draft']['upstreams']),32)
 def test_conflicting_fixed_answers_explain_invalid_dns_profile(self):
  docs,sel=self.dns_input();d=json.loads(docs[0]);source=d['sources'][0];source['id']='active';source['origin']='active';source['profile']['records']=[{'name':'example.org','include_subdomains':True,'addresses':['192.0.2.8'],'checked_at':None}]
  other=copy.deepcopy(source);other['id']='draft';other['origin']='draft';other['profile']['records'][0]['addresses']=['192.0.2.9'];d['sources'].append(other);sel['dns']=[{'source_id':s['id'],'source_sha256':s['sha256'],'upstreams':s['profile']['upstreams'],'records':[{'index':0,'value':s['profile']['records'][0]}]}for s in d['sources']]
  p=self.call(sel,docs=[json.dumps(d)]);self.assertNotIn('error',p);self.assertFalse(p['ready']);self.assertIn('invalid_dns_profile',[v['code']for v in p['problems']]);self.assertIsNone(p['draft'])
 def test_unrelated_legacy_import_name_does_not_change_original_target(self):
  sha=hashlib.sha256(BLOB).hexdigest();row={'id':'a'*32,'kind':'blobs','name':'imp-'+sha+'-hello.bin','sha256':'0'*64,'state':'available','byte_length':1}
  p=self.call(inventory={'files':[row],'scan_truncated':False,'skipped':0});self.assertTrue(p['ready']);self.assertEqual(p['files'][0]['target_name'],'hello.bin')
 def test_replacement_exposes_impact_on_unselected_blocks(self):
  row={'id':'a'*32,'kind':'blobs','name':'hello.bin','sha256':'0'*64,'state':'available','byte_length':1}
  current=CURRENT+'NFQWS_ARGS_CUSTOM="--blob=old:@/opt/etc/nfqws2/blobs/hello.bin"\n'
  p=self.call(selection(blocks=[],shared=[],files=[{'id':'1'*32}],allow_shared_impact=False),inventory={'files':[row]},current=current)
  self.assertFalse(p['ready']);self.assertIn('NFQWS_ARGS_CUSTOM',p['affected_blocks']);self.assertIn('shared_impact',[x['code']for x in p['problems']])
 def test_selected_same_name_with_different_bytes_is_conflict(self):
  v=json.loads(documents()[1]);v['files'][1]={**v['files'][0],'id':'2'*32,'aliases':['RESOURCE_2'],'data_base64':base64.b64encode(b'OTHER').decode(),'sha256':hashlib.sha256(b'OTHER').hexdigest(),'source_sha256':hashlib.sha256(b'OTHER').hexdigest(),'byte_length':5};v['audit']['references']=[];v['audit']['scope']='files_only'
  p=self.call(selection(blocks=[],shared=[]),docs=[json.dumps(v)]);self.assertFalse(p['ready']);self.assertIn('file_conflict',[x['code']for x in p['problems']])
 def test_quoted_and_separate_file_operands_keep_required_at_prefix(self):
  sel=selection();sel['shared'][0]['value']='--blob "hello:RESOURCE_1" --lua-init "RESOURCE_2"';p=self.call(sel);self.assertTrue(p['ready'],p);self.assertIn('--blob hello:@/opt/',p['config']);self.assertIn('--lua-init @/opt/',p['config'])

 def test_exported_at_resource_prefix_is_bound_exactly_once(self):
  docs=documents();v=json.loads(docs[0]);v['shared']['NFQWS_BASE_ARGS']='--blob=hello:@RESOURCE_1 --lua-init=@RESOURCE_2';docs[0]=json.dumps(v)
  sel=selection(shared=[{'key':'NFQWS_BASE_ARGS','value':v['shared']['NFQWS_BASE_ARGS']}])
  inventories=[{'files':[],'scan_truncated':False}, {'files':[{'id':'a'*32,'kind':'blobs','name':'hello.bin','sha256':hashlib.sha256(BLOB).hexdigest(),'state':'available','byte_length':len(BLOB)}],'scan_truncated':False}]
  for inventory in inventories:
   with self.subTest(reused=bool(inventory['files'])):
    p=self.call(sel,docs=docs,inventory=inventory);self.assertTrue(p['ready'],p.get('problems'));self.assertNotIn('@@/opt/',p['config']);self.assertIn('--blob=hello:@/opt/',p['config']);self.assertIn('--lua-init=@/opt/',p['config'])

 def test_unsupported_name_is_rejected_without_silent_rename(self):
  v=json.loads(documents()[1]);v['files'][0]['name']='hello world.bin';p=self.call(selection(blocks=[],shared=[],files=[{'id':'1'*32}]),docs=[json.dumps(v)]);self.assertFalse(p['ready']);self.assertIn('invalid_file_name',[x['code']for x in p['problems']]);self.assertEqual(p['files'],[])

 def test_unused_unsupported_file_name_does_not_block_dns_only_import(self):
  docs,sel=self.dns_input();v=json.loads(documents()[1]);v['files'][0]['name']='мой список.list';p=self.call(sel,docs=docs+[json.dumps(v)]);self.assertTrue(p['ready'],p['problems']);self.assertEqual(p['files'],[]);self.assertIsNotNone(p['draft'])
