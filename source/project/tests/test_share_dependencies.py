"""Static references are compared to the actual selection, never executed."""
import hashlib,json,subprocess,unittest
from test_dpi_normalize import PHP,PUBLIC

BASE='''NFQWS_BASE_ARGS="--blob=hello:@/opt/etc/nfqws2/blobs/hello.bin --lua-init=@/opt/etc/nfqws2/lua/custom.lua"
MODE_LIST="--hostlist=/opt/etc/nfqws2/lists/sites.list"
NFQWS_ARGS="--filter-tcp=443 $MODE_LIST --lua-desync=fake:blob=hello"
NFQWS_ARGS_QUIC="--filter-udp=443 --lua-desync=fake:blob=0x0000"
'''

def item(kind,name):return {'id':hashlib.sha256((kind+'\0'+name).encode()).hexdigest()[:32],'kind':kind,'name':name,'state':'available','sha256':'a'*64,'byte_length':10}
class ShareDependenciesTests(unittest.TestCase):
    def analyze(self,text=None,config=BASE,keys=None,selected=None,full=False):
        draft={'blocks':[{'key':k,'value':('--lua-desync=fake:blob=hello $MODE_LIST' if text is None else text)} for k in (keys or ['NFQWS_ARGS'])]}
        selection={'mode':'config','config':config} if full else {'mode':'blocks','draft':draft}
        inventory={'files':[item('lists','sites.list'),item('lua','custom.lua'),item('blobs','hello.bin')],'scan_truncated':False}
        payload={'selection':selection,'config':config,'inventory':inventory,'selected':selected or []}
        code='''$p=$argv[1].'/share-dependencies.php';if(!is_file($p)){echo json_encode(['error'=>'missing_feature']);exit;}
        require $p;$v=json_decode(stream_get_contents(STDIN),true);try{echo json_encode(AsusShareDependencies::analyze($v['selection'],$v['config'],$v['inventory'],$v['selected']),JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(payload),capture_output=True,text=True,timeout=8)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');v=json.loads(p.stdout);self.assertNotIn('error',v);return v
    def test_selected_block_inherits_shared_blob_lua_and_resolved_list(self):
        v=self.analyze();self.assertEqual({x['name'] for x in v['references']},{'hello.bin','custom.lua','sites.list'})
        self.assertEqual(len(v['missing']),3)
        ids=[item(k,n)['id'] for k,n in [('lists','sites.list'),('lua','custom.lua'),('blobs','hello.bin')]]
        v=self.analyze(selected=ids);self.assertEqual(v['missing'],[])
    def test_edited_block_is_analyzed_and_unselected_block_does_not_add_files(self):
        v=self.analyze(text='--filter-tcp=80 --hostlist=/opt/etc/nfqws2/lists/edited.list')
        self.assertIn('edited.list',{x['name'] for x in v['references']});self.assertNotIn('sites.list',{x['name'] for x in v['references']})
        missing=next(x for x in v['references'] if x['name']=='edited.list');self.assertEqual(missing['state'],'missing')
    def test_inline_hex_blob_is_not_a_missing_file(self):
        v=self.analyze(text='--lua-desync=fake:blob=0x0123abcd',config='NFQWS_ARGS="--filter-tcp=443"\n')
        self.assertEqual(v['references'],[]);self.assertEqual(v['missing'],[]);self.assertEqual(v['unresolved'],[])

    def test_engine_builtin_blobs_need_no_file_but_similar_unknown_name_still_fails(self):
        for name in ['fake_default_tls','fake_default_http','fake_default_quic']:
            v=self.analyze(text='--lua-desync=fake:blob='+name,config='NFQWS_ARGS="--filter-tcp=443"\n')
            self.assertTrue(v['complete'],v);self.assertEqual(v['references'],[])
        v=self.analyze(text='--lua-desync=fake:blob=fake_default_other',config='NFQWS_ARGS="--filter-tcp=443"\n')
        self.assertFalse(v['complete']);self.assertIn('unbound_blob',{r['kind'] for r in v['unresolved']})
    def test_quoted_paths_and_separate_option_values_are_tokens_not_commands(self):
        v=self.analyze(text="--hostlist '/opt/etc/nfqws2/lists/sites.list' --lua-init=@/opt/etc/nfqws2/lua/custom.lua",config='NFQWS_ARGS="--filter-tcp=443"\n')
        self.assertEqual({x['name'] for x in v['references']},{'sites.list','custom.lua'})
    def test_outside_directory_and_unbound_blob_or_variable_are_explicit(self):
        v=self.analyze(text='--hostlist=/etc/PRIVATE_CANARY --lua-desync=fake:blob=unknown $PRIVATE_VAR',config='NFQWS_ARGS="--filter-tcp=443"\n')
        self.assertEqual(v['references'][0]['state'],'outside');self.assertTrue(v['unresolved']);self.assertIsNone(v['references'][0]['resource_id'])
    def test_command_substitution_and_malformed_quotes_are_not_executed_or_guessed(self):
        for text in ['--hostlist=$(touch /tmp/NEVER_EXECUTE)','--hostlist="unterminated']:
            v=self.analyze(text=text,config='NFQWS_ARGS="--filter-tcp=443"\n');self.assertTrue(v['unresolved']);self.assertFalse(v['complete'])
    def test_full_config_has_all_resource_branches(self):
        v=self.analyze(full=True);self.assertEqual({x['name'] for x in v['references']},{'hello.bin','custom.lua','sites.list'})

    def test_shared_blob_mapping_contains_resource_id_without_absolute_path(self):
        v=self.analyze();self.assertEqual(v['blob_bindings']['hello'],item('blobs','hello.bin')['id'])
        self.assertNotIn('/opt/',json.dumps(v))

    def test_reference_count_is_bounded_and_warns_instead_of_silent_truncation(self):
        text=' '.join('--hostlist=/opt/etc/nfqws2/lists/site%d.list'%n for n in range(140))
        v=self.analyze(text=text,config='NFQWS_ARGS="--filter-tcp=443"\n')
        self.assertLessEqual(len(v['references']),128);self.assertIn('reference_limit',{x['kind'] for x in v['unresolved']});self.assertFalse(v['complete'])

    def test_separated_lua_desync_operand_cannot_claim_complete_for_unknown_blob(self):
        v=self.analyze(text='--lua-desync fake:blob=not_defined',config='NFQWS_ARGS="--filter-tcp=443"\n')
        self.assertFalse(v['complete']);self.assertIn('unbound_blob',{x['kind'] for x in v['unresolved']})
