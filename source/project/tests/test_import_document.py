"""Incoming exports stay data; full config never replaces local router identity."""
import base64,copy,hashlib,json,subprocess,unittest,uuid
from test_dpi_normalize import PHP,PUBLIC

CTX={'purpose':'Test','operator':'Example ISP','comment':''}
STRATEGY={'type':'nfqws2_strategy','schema_version':2,'versions':{'core':'1.3.1-asus6+b35','web':'0.1.4'},'mode':'blocks','blocks':[{'key':'NFQWS_ARGS','value':'--filter-tcp=443'}],'shared':{'NFQWS_BASE_ARGS':'--debug=0'},**CTX,'dependencies':[]}

def wire(kind,data):
 raw=json.dumps(data,separators=(',',':')).encode();return {'type':kind,'filename':f'NFQWS2_{kind.upper()}_2026-10-20_00-00-00Z.json','byte_length':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'data_base64':base64.b64encode(raw).decode()}
def envelope(strategy=STRATEGY,version=4):return {'version':version,'submission_id':str(uuid.uuid4()),'files':[wire('strategy',strategy)]}

class ImportDocumentTests(unittest.TestCase):
 def call(self,data,body=None):
  code="""$f=$argv[1].'/import-document.php';if(!is_file($f)){echo json_encode(['error'=>'missing_feature']);exit;}require $f;try{$v=json_decode(stream_get_contents(STDIN),true);"""+(body or "echo json_encode(AsusImportDocument::read($v),JSON_THROW_ON_ERROR);")+"}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
  r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(data),text=True,capture_output=True,timeout=10);self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
 def test_v4_and_separate_strategy_project_blocks_and_shared(self):
  for v in [[json.dumps(envelope())],[json.dumps(STRATEGY)]]:
   out=self.call(v);self.assertNotIn('error',out);self.assertEqual(out['values']['NFQWS_ARGS'],'--filter-tcp=443');self.assertEqual(out['values']['NFQWS_BASE_ARGS'],'--debug=0');self.assertEqual(out['resources'],[])
 def test_legacy_v3_strategy_remains_accepted(self):
  s=copy.deepcopy(STRATEGY);s['schema_version']=1;s.pop('shared');out=self.call([json.dumps(envelope(s,3))]);self.assertNotIn('error',out);self.assertEqual(out['values'],{'NFQWS_ARGS':'--filter-tcp=443'})
 def test_duplicate_keys_categories_bad_hash_and_unsupported_version_rejected(self):
  bad=envelope();bad['files'][0]['sha256']='a'*64
  wrong=envelope();wrong['version']=999
  for docs in [['{"version":4,"version":3}'],[json.dumps(STRATEGY)]*2,[json.dumps(bad)],[json.dumps(wrong)],[]]:
   with self.subTest(docs=str(docs)[:60]):self.assertIn('error',self.call(docs))
 def test_file_and_total_limits_are_explicit(self):
  self.assertIn('error',self.call([' '*4194305]));self.assertIn('error',self.call([json.dumps(STRATEGY)]*6))
 def test_full_config_projects_only_strategy_and_ports(self):
  s=copy.deepcopy(STRATEGY);s.pop('blocks');s.pop('shared');s.update(mode='config',config='ISP_INTERFACE="<hidden>"\nASUS_CLIENTS4="<hidden>"\nUSER="<hidden>"\nNFQUEUE_NUM="300"\nMODE_AUTO="--hostlist-auto=RESOURCE_1"\nNFQWS_EXTRA_ARGS="$MODE_AUTO"\nNFQWS_ARGS="--filter-tcp=443"\nTCP_PORTS="80,443"\n',omitted_options=0)
  out=self.call([json.dumps(s)]);self.assertNotIn('error',out);self.assertEqual(out['values']['NFQWS_EXTRA_ARGS'],'--hostlist-auto=RESOURCE_1');self.assertEqual(out['ports'],{'TCP_PORTS':'80,443'});self.assertNotIn('ASUS_CLIENTS4',out['values']);self.assertNotIn('<hidden>',json.dumps(out['values']))
 def test_static_replacement_preserves_unselected_bytes_and_quotes(self):
  source='# keep\nASUS_CLIENTS4="192.0.2.4"\nNFQWS_ARGS="old\n  second" # old comment\nLOG_LEVEL=0\n'
  body="$a=AsusImportConfig::replace($v['source'],$v['changes']);echo json_encode(['config'=>$a,'parsed'=>AsusImportConfig::parse($a)]);"
  value='--hostlist-domains="example.org" --comment=can\\test'
  out=self.call({'source':source,'changes':{'NFQWS_ARGS':value}},body);self.assertNotIn('error',out);self.assertIn('ASUS_CLIENTS4="192.0.2.4"',out['config']);self.assertIn('LOG_LEVEL=0',out['config']);self.assertEqual(out['parsed']['NFQWS_ARGS'],value)
 def test_shell_expansion_unknown_variable_and_duplicate_assignment_refused(self):
  for text in ['NFQWS_ARGS="$(touch /tmp/IMPORT_CANARY)"\n','NFQWS_ARGS="`id`"\n','NFQWS_ARGS="$UNKNOWN"\n','NFQWS_ARGS="ok"\nNFQWS_ARGS="again"\n']:
   s=copy.deepcopy(STRATEGY);s.pop('blocks');s.pop('shared');s.update(mode='config',config=text,omitted_options=0);self.assertIn('error',self.call([json.dumps(s)]))
 def test_local_fields_cannot_be_written_by_replacer(self):
  out=self.call({'source':'ASUS_CLIENTS4="local"\n','changes':{'ASUS_CLIENTS4':'foreign'}},"echo json_encode(AsusImportConfig::replace($v['source'],$v['changes']));");self.assertIn('error',out)
 def test_separate_report_is_context_and_validated_before_ignored(self):
  from test_support_relay_validation import fixture
  out=self.call([fixture().decode(),json.dumps(STRATEGY)]);self.assertNotIn('error',out);self.assertEqual(out['ignored'],['report'])
  out=self.call(['{"collector_version":"fake"}',json.dumps(STRATEGY)]);self.assertIn('error',out)
