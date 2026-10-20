"""Package Lua is an immutable dependency, not a user-editable contribution."""
import base64,hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_import_document import PHP,PUBLIC
import test_import_plan as f

class BundledLuaTests(unittest.TestCase):
 def fixture(self,body):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d)/'resources';root.mkdir(mode=0o755);(root/'lua').mkdir(mode=0o755);raw=b'function helper() return 1 end\n';(root/'lua/custom.lua').write_bytes(raw)
   manifest={'lua/custom.lua':{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}}
   code='require $argv[1]."/share-contributions.php";$root=$argv[2];$r=new AsusShareResources($root,(int)$argv[3],json_decode($argv[4],true));'+body
   a=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid()),json.dumps(manifest)],capture_output=True,text=True,timeout=10);self.assertEqual(a.returncode,0,a.stdout+a.stderr);return json.loads(a.stdout)
 def test_package_manifest_uses_pinned_opt_alias_and_rejects_writable_or_linked_manifest(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d)/'storage';base.mkdir(mode=0o755);alias=Path(d)/'opt';alias.symlink_to(base);folder=base/'share/nfqws2-asus';folder.mkdir(parents=True,mode=0o755);(base/'share').chmod(0o755)
   path=folder/'report-baseline.json';value={'resources':{'lua/custom.lua':{'bytes':3,'sha256':'a'*64}}};path.write_text(json.dumps(value));path.chmod(0o644)
   code='require $argv[1]."/share-resources.php";echo json_encode(AsusShareResources::packageLua($argv[2],(int)$argv[3]));'
   def read():
    a=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(alias),str(os.getuid())],capture_output=True,text=True);self.assertEqual(a.returncode,0,a.stdout+a.stderr);return json.loads(a.stdout)
   self.assertEqual(read(),value['resources']);path.chmod(0o666);self.assertEqual(read(),[])
   path.unlink();target=folder/'other';target.write_text(json.dumps(value));path.symlink_to(target);self.assertEqual(read(),[])

 def test_only_exact_package_bytes_are_bundled_including_renamed_copies(self):
  v=self.fixture('$a=$r->inventory();copy($root."/lua/custom.lua",$root."/lua/copy.lua");$b=$r->inventory();file_put_contents($root."/lua/custom.lua","changed");$c=$r->inventory();echo json_encode([$a,$b,$c]);')
  self.assertTrue(v[0]['files'][0].get('bundled_lua'));self.assertTrue(all(x.get('bundled_lua')for x in v[1]['files']));self.assertFalse(next(x for x in v[2]['files']if x['name']=='custom.lua').get('bundled_lua'));self.assertEqual(v[0]['files'][0].get('bundled_name'),'custom.lua')
 def test_strategy_uses_package_lua_without_attaching_unselected_bytes(self):
  v=self.fixture('''$c="NFQWS_BASE_ARGS=\\"--lua-init=@/opt/etc/nfqws2/lua/custom.lua\\"\\nNFQWS_ARGS=\\"--filter-tcp=443\\"\\n";$ctx=['purpose'=>'test','operator'=>'ISP','comment'=>''];$s=['mode'=>'blocks','draft'=>['blocks'=>[['key'=>'NFQWS_ARGS','value'=>'--filter-tcp=443']]],'context'=>$ctx];$x=new AsusShareContributions($r,new AsusShareDns());$a=$x->analyze(['resource_ids'=>[],'strategy'=>$s],$c);try{$p=$x->prepare(['strategy'=>$s,'context'=>$ctx,'analysis_config_sha256'=>hash('sha256',$c),'resources'=>['files'=>[],'missing_reason'=>'']],$c,['core'=>'1','web'=>'1']);echo json_encode(['audit'=>$a,'prepared'=>$p]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage(),'audit'=>$a]);}''')
  self.assertNotIn('error',v,v);self.assertTrue(v['audit']['audit']['complete']);self.assertEqual(set(v['prepared']),{'strategy'});strategy=json.loads(v['prepared']['strategy']);self.assertIn('--lua-init=@/opt/etc/nfqws2/lua/custom.lua',strategy['shared']['NFQWS_BASE_ARGS']);self.assertEqual(strategy['dependencies'],[])
  raw=b'function helper() return 1 end\n';row={'id':'a'*32,'kind':'lua','name':'custom.lua','sha256':hashlib.sha256(raw).hexdigest(),'byte_length':len(raw),'state':'available','bundled_lua':True,'bundled_name':'custom.lua'}
  selection=f.selection(blocks=strategy['blocks'],shared=[{'key':k,'value':v} for k,v in strategy['shared'].items()],files=[],trusted_lua=False,allow_incomplete=False)
  plan=f.ImportPlanTests().call(selection,docs=[json.dumps(strategy)],inventory={'files':[row],'scan_truncated':False})
  self.assertTrue(plan['ready'],plan.get('problems'));self.assertEqual(plan['files'],[])
 def test_matching_local_package_lua_needs_no_import_choice_or_lua_consent(self):
  row={'id':'a'*32,'kind':'lua','name':'custom.lua','sha256':hashlib.sha256(f.LUA).hexdigest(),'byte_length':len(f.LUA),'state':'available','bundled_lua':True,'bundled_name':'custom.lua'}
  p=f.ImportPlanTests().call(f.selection(files=[{'id':'1'*32}],trusted_lua=False,allow_incomplete=False),inventory={'files':[row],'scan_truncated':False});self.assertTrue(p['ready'],p.get('problems'));self.assertIn('--lua-init=@/opt/etc/nfqws2/lua/custom.lua',p['config'])
 def test_changed_or_nonpackage_lua_still_requires_explicit_trust(self):
  row={'id':'a'*32,'kind':'lua','name':'custom.lua','sha256':hashlib.sha256(f.LUA).hexdigest(),'byte_length':len(f.LUA),'state':'available','bundled_lua':False}
  p=f.ImportPlanTests().call(f.selection(files=[{'id':'1'*32}],trusted_lua=False),inventory={'files':[row],'scan_truncated':False});self.assertFalse(p['ready']);self.assertIn('lua_trust',[x['code']for x in p['problems']])
