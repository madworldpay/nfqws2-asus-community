"""Imported executable dependencies are isolated and recoverable, never stock writes."""
import copy
import hashlib
import json
import os
import base64
import subprocess
from pathlib import Path
import tempfile
import unittest

from test_import_plan import documents, selection, BLOB, LUA, CURRENT
import test_import_plan as plan_fixture
import test_import_transaction as tx_fixture
from test_dpi_normalize import PHP, PUBLIC


def generated(kind, raw):
    return '/opt/etc/nfqws2/' + kind + '/imported/' + hashlib.sha256(raw).hexdigest() + ('.lua' if kind == 'lua' else '.bin')


class PortableAssetImport(unittest.TestCase):
    def setUp(self):
        self.plan = plan_fixture.ImportPlanTests()
        self.tx = tx_fixture.ImportTransactionTests()

    def test_legacy_nonstock_assets_use_generated_paths(self):
        p = self.plan.call()
        self.assertTrue(p['ready'], p)
        self.assertEqual({f['path'] for f in p['files']},
                         {generated('blobs', BLOB), generated('lua', LUA)})
        self.assertTrue(all(not f['replace'] for f in p['files']))

    def test_same_names_different_bytes_coexist(self):
        d = json.loads(documents()[1]); a = d['files'][0]
        b = copy.deepcopy(a); b.update(id='2' * 32, aliases=['RESOURCE_2'])
        raw = b'other'
        b.update(data_base64=base64.b64encode(raw).decode(), byte_length=len(raw),
                 sha256=hashlib.sha256(raw).hexdigest(), source_sha256=hashlib.sha256(raw).hexdigest())
        d.update(files=[a, b]); d['audit'].update(scope='files_only', references=[])
        p = self.plan.call(selection(blocks=[], shared=[]), docs=[json.dumps(d)])
        self.assertTrue(p['ready'], p)
        self.assertEqual({f['path'] for f in p['files']}, {generated('blobs', BLOB), generated('blobs', raw)})

    def package_document(self):
        docs = documents(); r = json.loads(docs[1]); r['schema_version'] = 2
        r['package_files'] = [{k: v for k, v in f.items() if k in
                              ['id', 'kind', 'name', 'byte_length', 'sha256', 'aliases']}
                             for f in r['files']]
        r['files'] = []; docs[1] = json.dumps(r); return docs

    def test_package_reference_needs_actual_verified_receiver_stock(self):
        inventory = {'scan_truncated': False, 'files': [
            {'id': str(i) * 32, 'kind': kind, 'name': name, 'sha256': hashlib.sha256(raw).hexdigest(),
             'byte_length': len(raw), 'state': 'available', 'bundled_resource': True,
             'bundled_lua': kind == 'lua', 'bundled_name': name}
            for i, (kind, name, raw) in enumerate([('blobs', 'hello.bin', BLOB), ('lua', 'custom.lua', LUA)], 1)]}
        sel = selection(files=[], trusted_lua=False, allow_incomplete=False)
        p = self.plan.call(sel, docs=self.package_document(), inventory=inventory)
        self.assertTrue(p['ready'], p); self.assertEqual(p['files'], [])
        self.assertIn('/opt/etc/nfqws2/blobs/hello.bin', p['config'])
        for mutation in ['missing', 'hash', 'trust', 'length']:
            bad = copy.deepcopy(inventory)
            if mutation == 'missing': bad['files'] = []
            elif mutation == 'hash': bad['files'][0]['sha256'] = '0' * 64
            elif mutation == 'trust': bad['files'][0]['bundled_resource'] = False
            else: bad['files'][0]['byte_length'] += 1
            with self.subTest(mutation=mutation):
                p = self.plan.call(sel, docs=self.package_document(), inventory=bad)
                self.assertFalse(p['ready'], p)
                self.assertIn('package_resource_unavailable', [x['code'] for x in p['problems']])

    def test_commit_undo_preserves_original_bytes_inodes_and_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tx.fixture(d); originals = []
            for relative in ['lua/custom.lua', 'blobs/hello.bin']:
                f = root / 'resources' / relative; f.write_bytes(b'ORIGINAL'); f.chmod(0o640)
                originals.append((f, f.read_bytes(), f.stat()))
            result = self.tx.call(root, [self.tx.prep(), ['apply', 'a' * 32]])
            self.assertEqual(result[-1]['value']['state'], 'committed', result)
            for kind, raw in [('lua', LUA), ('blobs', BLOB)]:
                target = root / 'resources' / generated(kind, raw).removeprefix('/opt/etc/nfqws2/')
                self.assertEqual(target.read_bytes(), raw)
            result = self.tx.call(root, [['undo', 'a' * 32]])
            self.assertEqual(result[-1]['value']['state'], 'undone', result)
            for f, raw, stat in originals:
                self.assertEqual(f.read_bytes(), raw)
                self.assertEqual((f.stat().st_ino, f.stat().st_mode, f.stat().st_uid, f.stat().st_gid, f.stat().st_mtime_ns),
                                 (stat.st_ino, stat.st_mode, stat.st_uid, stat.st_gid, stat.st_mtime_ns))
            self.assertFalse(list((root / 'resources').rglob('imported')))

    def test_death_at_new_directory_stage_and_link_recovers(self):
        for phase in ['directory_lua', 'directory_blobs', 'stage_0', 'linked_0', 'file_0', 'config', 'committed']:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as d:
                root = self.tx.fixture(d)
                self.tx.call(root, [self.tx.prep(), ['apply', 'a' * 32]], crash=phase)
                result = self.tx.call(root, [['recover']])
                expected = 'committed' if phase in ['config', 'committed'] else 'rolled_back'
                self.assertEqual(result[-1]['value']['state'], expected, result)
                if expected == 'committed': self.tx.call(root, [['undo', 'a' * 32]])
                self.assertEqual((root / 'resources/nfqws2.conf').read_text(), CURRENT)
                self.assertFalse([p for p in (root / 'resources').rglob('*') if p.is_file() and p.name != 'nfqws2.conf'])

    def test_changed_generated_target_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tx.fixture(d); target = root / 'resources' / generated('blobs', BLOB).removeprefix('/opt/etc/nfqws2/')
            target.parent.mkdir(mode=0o755); target.write_bytes(b'FOREIGN')
            result = self.tx.call(root, [self.tx.prep(), ['apply', 'a' * 32]])
            self.assertIn('error', result[-1]); self.assertEqual(target.read_bytes(), b'FOREIGN')
            self.assertFalse((root / 'journal/state.json').exists())

    def test_export_import_export_retains_exact_bytes_and_dependency_bindings(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tx.fixture(d)
            result = self.tx.call(root, [self.tx.prep(), ['apply', 'a' * 32]])
            self.assertEqual(result[-1]['value']['state'], 'committed', result)
            code = """require $argv[1].'/share-contributions.php';require $argv[1].'/share-v4.php';
            $r=new AsusShareResources($argv[2],(int)$argv[3],[]);$c=file_get_contents($argv[2].'/nfqws2.conf');
            $ctx=['purpose'=>'test','operator'=>'ISP','comment'=>''];
            $s=['mode'=>'blocks','context'=>$ctx,'draft'=>['blocks'=>[['key'=>'NFQWS_ARGS','value'=>'--filter-tcp=443 --lua-desync=fake:blob=hello']]]];
            $docs=(new AsusShareContributions($r,new AsusShareDns()))->prepare(['context'=>$ctx,'strategy'=>$s,'analysis_config_sha256'=>hash('sha256',$c)],$c,['core'=>'1','web'=>'100']);
            $v=[];foreach($docs as $k=>$raw)$v[$k]=AsusShareV4Payloads::validate($k,$raw);AsusShareV4Payloads::bundle($v);echo json_encode($v);"""
            result = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root/'resources'),str(os.getuid())],capture_output=True,text=True,timeout=10)
            self.assertEqual((result.returncode,result.stderr),(0,''),result.stdout)
            docs = json.loads(result.stdout)
            self.assertEqual({f['kind']:base64.b64decode(f['data_base64']) for f in docs['resources']['files']},{'lua':LUA,'blobs':BLOB})
            self.assertTrue(docs['resources']['audit']['complete'])
            self.assertTrue(all(x['included'] for x in docs['strategy']['dependencies']))
            self.assertNotIn('/opt/etc',result.stdout)

    def test_own_directory_creation_gap_requires_attention(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tx.fixture(d)
            self.tx.call(root,[self.tx.prep(),['apply','a'*32]],crash='directory_created_blobs')
            result=self.tx.call(root,[['recover']])
            self.assertEqual(result,[{'error':'restore_required'}])
            self.assertTrue((root/'resources/blobs/imported').is_dir())
            self.assertEqual((root/'resources/nfqws2.conf').read_text(),CURRENT)

    def test_foreign_same_bytes_inode_is_preserved_on_undo(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tx.fixture(d); self.tx.call(root,[self.tx.prep(),['apply','a'*32]])
            target=root/'resources'/generated('blobs',BLOB).removeprefix('/opt/etc/nfqws2/')
            foreign=target.parent/'foreign';foreign.write_bytes(BLOB);os.replace(foreign,target)
            inode=target.stat().st_ino
            result=self.tx.call(root,[['undo','a'*32]])
            self.assertEqual(result,[{'error':'source_changed'}]);self.assertEqual(target.stat().st_ino,inode)
            self.assertEqual(target.read_bytes(),BLOB)

    def test_second_import_reuses_content_and_undo_keeps_first_strategy_asset(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.tx.fixture(d);self.tx.call(root,[self.tx.prep(),['apply','a'*32]])
            target=root/'resources'/generated('blobs',BLOB).removeprefix('/opt/etc/nfqws2/')
            inode=target.stat().st_ino
            result=self.tx.call(root,[self.tx.prep(),['apply','b'*32],['undo','b'*32]])
            self.assertEqual(result[-1]['value']['state'],'undone',result)
            self.assertEqual(target.stat().st_ino,inode);self.assertEqual(target.read_bytes(),BLOB)

    def test_foreign_file_in_created_directory_stops_before_undo_effects(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.tx.fixture(d);self.tx.call(root,[self.tx.prep(),['apply','a'*32]])
            config=(root/'resources/nfqws2.conf').read_bytes()
            foreign=root/'resources/blobs/imported/foreign.bin';foreign.write_bytes(b'KEEP')
            result=self.tx.call(root,[['undo','a'*32]])
            self.assertEqual(result,[{'error':'source_changed'}])
            self.assertEqual((root/'resources/nfqws2.conf').read_bytes(),config)
            self.assertEqual(foreign.read_bytes(),b'KEEP')

    def test_journal_identity_uses_named_fields_and_rejects_wrong_types_or_extras(self):
        for mutation in ['order','bool','extra']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as d:
                root=self.tx.fixture(d);self.tx.call(root,[self.tx.prep(),['apply','a'*32]])
                path=root/'journal/state.json';value=json.loads(path.read_text())
                identity=value['current']['files'][0]['identity']
                if mutation=='order':value['current']['files'][0]['identity']=dict(reversed(list(identity.items())))
                elif mutation=='bool':identity['uid']=True
                else:identity['unknown']=1
                path.write_text(json.dumps(value))
                result=self.tx.call(root,[['undo','a'*32]])
                if mutation=='order':self.assertEqual(result[-1].get('value',{}).get('state'),'undone',result)
                else:self.assertEqual(result,[{'error':'invalid_state'}])

    def checkpoint_call(self, root, phase, mutation, undo=False):
        code = """require $argv[1].'/import-transaction.php';$r=$argv[2];$u=(int)$argv[3];$v=json_decode(stream_get_contents(STDIN),true);
        $t=new AsusImportTransaction(new AsusImportStore($r.'/journal',$u),new AsusSmartDnsStore($r.'/dns',$u),$r.'/resources',$r.'/resources/nfqws2.conf',$u,
        ['checkpoint'=>function($p)use($r){if($p==='%s'){%s}}]);
        try{$out=%s;echo json_encode(['value'=>$out]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}""" % (phase, mutation, "$t->undo(str_repeat('a',32))" if undo else "$t->apply($t->prepare($v[0],$v[1]),str_repeat('a',32))")
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],input=json.dumps([documents(),selection()]),text=True,capture_output=True,timeout=10)
        self.assertEqual((q.returncode,q.stderr),(0,''),q.stdout)
        return json.loads(q.stdout)

    def test_undo_rechecks_same_bytes_foreign_inode_after_config_restore(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.tx.fixture(d);self.tx.call(root,[self.tx.prep(),['apply','a'*32]])
            result=self.checkpoint_call(root,'undo_config',"$p=glob($r.'/resources/blobs/imported/*.bin')[0];copy($p,$r.'/foreign');rename($r.'/foreign',$p);file_put_contents($r.'/foreign-inode',(string)lstat($p)['ino']);",undo=True)
            self.assertIn(result.get('error'),['source_changed','restore_required'],result)
            target=root/'resources'/generated('blobs',BLOB).removeprefix('/opt/etc/nfqws2/')
            self.assertEqual(target.read_bytes(),BLOB)
            self.assertEqual(str(target.stat().st_ino),(root/'foreign-inode').read_text())

    def test_stage_and_directory_substitution_never_commits_or_deletes_foreign_files(self):
        cases=[('stage_0',"$p=glob($r.'/resources/blobs/imported/.import-*')[0];file_put_contents($r.'/foreign','FOREIGN');rename($r.'/foreign',$p);"),
               ('stage_0',"$p=glob($r.'/resources/blobs/imported/.import-*')[0];file_put_contents($r.'/foreign','FOREIGN');unlink($p);symlink($r.'/foreign',$p);"),
               ('directory_blobs',"$p=$r.'/resources/blobs/imported';rename($p,$p.'-owned');mkdir($p,0755);"),
               ('file_1',"$p=glob($r.'/resources/blobs/imported/*.bin')[0];file_put_contents($p,'FOREIGN');"),
               ('config_stage',"$p=glob($r.'/resources/blobs/imported/*.bin')[0];file_put_contents($p,'FOREIGN');")]
        for phase,mutation in cases:
            with self.subTest(phase=phase,mutation=mutation),tempfile.TemporaryDirectory() as d:
                root=self.tx.fixture(d);result=self.checkpoint_call(root,phase,mutation)
                self.assertIn('error',result,result)
                self.assertEqual((root/'resources/nfqws2.conf').read_text(),CURRENT)
                if (root/'foreign').exists():self.assertEqual((root/'foreign').read_text(),'FOREIGN')

    def test_unselected_package_block_does_not_require_its_assets(self):
        docs=self.package_document();s=json.loads(docs[0]);s['shared']={}
        s['blocks']=[{'key':'NFQWS_ARGS','value':'--filter-tcp=443'}, {'key':'NFQWS_ARGS_UDP','value':'--filter-udp=443 --lua-init=RESOURCE_2 --blob=hello:RESOURCE_1 --lua-desync=fake:blob=hello'}]
        docs[0]=json.dumps(s)
        sel=selection(blocks=[s['blocks'][0]],shared=[],files=[],trusted_lua=False,allow_incomplete=False)
        p=self.plan.call(sel,docs=docs)
        self.assertTrue(p['ready'],p)
        self.assertFalse(p['fingerprints']['files'])
        sel['blocks']=[s['blocks'][1]]
        p=self.plan.call(sel,docs=docs)
        self.assertFalse(p['ready'],p)
        self.assertIn('package_resource_unavailable',[x['code'] for x in p['problems']])

    def test_reused_inputs_are_rechecked_before_config_and_never_become_undo_owned(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.tx.fixture(d)
            self.tx.call(root,[self.tx.prep(selection(blocks=[],shared=[])),['apply','b'*32]])
            result=self.checkpoint_call(root,'config_stage',"$p=glob($r.'/resources/blobs/imported/*.bin')[0];file_put_contents($p,'FOREIGN');")
            self.assertIn('error',result,result)
            self.assertEqual((root/'resources/nfqws2.conf').read_text(),CURRENT)
            self.assertEqual(next((root/'resources/blobs/imported').glob('*.bin')).read_bytes(),b'FOREIGN')
            state=json.loads((root/'journal/state.json').read_text())['current']
            self.assertEqual(state['files'],[], 'reused resources are not undo-owned')
