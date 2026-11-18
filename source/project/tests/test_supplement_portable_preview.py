"""Portable supplement data uses the existing serializer, grammar and importer only."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC
from test_strategy_supplement import BASE, RECIPE, STOCK

BLOB = b'\x00\xffportable-supplement\x00'


class SupplementPortablePreviewTests(unittest.TestCase):
    def setUp(self):
        engine = os.environ.get('NFQWS_TEST_ENGINE_DIR')
        self.assertTrue(engine, 'Provide the pinned original Lua fixture directory')
        artifacts = os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifacts:
            self.temp = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=artifacts))
        else:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.temp = Path(tmp.name)
        self.root, self.dest = self.temp/'source', self.temp/'receiver'
        self.baseline = {}
        for root in (self.root, self.dest):
            root.mkdir(mode=0o755)
            for kind in ('lua', 'blobs', 'lists'):
                (root/kind).mkdir(mode=0o755)
            for path, expected in list(STOCK.items())[:2]:
                name = Path(path).name
                raw = (Path(engine)/'lua'/name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
                (root/'lua'/name).write_bytes(raw)
                self.baseline['lua/'+name] = {'bytes': len(raw), 'sha256': expected}
            for name, raw in {'lists/user.list': b'base.example\n', 'lists/auto.list': b'learned.example\n',
                              'lists/exclude.list': b'excluded.example\n', 'lists/unrelated.list': b'UNSELECTED_PRIVATE\n',
                              'blobs/custom.bin': BLOB}.items():
                (root/name).write_bytes(raw)
        self.current = BASE.replace(' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua"',
            ' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua --blob=owned:@/opt/etc/nfqws2/blobs/custom.bin"')
        self.current = self.current.replace('--lua-desync=multidisorder:pos=2',
            '--lua-desync=fake:blob=owned --comment=custom.bin.target.example')
        self.count = 0

    def call(self, **options):
        data = {'current': self.current, 'recipe': RECIPE, 'domains': ['target.example'],
                'baseline': self.baseline, 'receiver_baseline': self.baseline, 'profile': 'asus-entware', **options}
        code = r'''require $argv[1].'/strategy-supplement.php';
        if(!method_exists('NfqwsStrategySupplement','portablePreview')){echo json_encode(['missing_api'=>true]);exit;}
        require $argv[1].'/import-plan.php';
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
        try{$source=new AsusShareResources($argv[2],(int)$argv[4],$d['baseline']);
        $view=NfqwsStrategySupplement::inventory($source);
        $binding=['config_sha256'=>hash('sha256',$d['current']),'resources_sha256'=>$view['resources_sha256']];
        $p=NfqwsStrategySupplement::prepare($source,$d['current'],$d['recipe'],$d['domains'],$binding);
        if(isset($d['source_change']))file_put_contents($argv[2].'/lists/auto.list',$d['source_change']);
        if(isset($d['tamper'])){
          if($d['tamper']==='buffer')$p['resource_kit']['files'][0]['data_base64']='eA==';
          if($d['tamper']==='flag')$p['can_export']=true;
          if($d['tamper']==='config')$p['preview']['candidate_config'].="\n";
          if($d['tamper']==='scope')$p['preview']['domains']=['other.example'];
        }
        $out=NfqwsStrategySupplement::portablePreview($source,$d['current'],$p);
        $doc=AsusImportDocument::read([$out['raw']]);
        $receiver=new AsusShareResources($argv[3],(int)$argv[4],$d['receiver_baseline']);
        $inventory=$receiver->inventory();$blocks=[];$shared=[];$ports=[];
        foreach($doc['values']as $key=>$value){if(in_array($key,AsusImportConfig::BLOCKS,true))$blocks[]=['key'=>$key,'value'=>$value];else $shared[]=['key'=>$key,'value'=>$value];}
        foreach($doc['ports']as $key=>$value)$ports[]=['key'=>$key,'value'=>$value];
        $selection=['blocks'=>$blocks,'shared'=>$shared,'ports'=>$ports,'files'=>array_map(fn($f)=>['id'=>$f['id']],$doc['resources']),
          'dns'=>[],'allow_shared_impact'=>false,'allow_incomplete'=>false,'trusted_lua'=>false];
        $plan=AsusImportPlan::prepare($doc,$selection,$d['current'],$inventory,null,$d['profile']);
        echo json_encode(['result'=>$out,'proposal'=>$p,'document'=>$doc,'import_plan'=>$plan],JSON_THROW_ON_ERROR);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        self.count += 1
        prefix = self.temp/str(self.count)
        prefix.with_suffix('.php').write_text(code)
        prefix.with_suffix('.request.json').write_text(json.dumps(data))
        p = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(self.root), str(self.dest), str(os.getuid())],
                           input=json.dumps(data), text=True, capture_output=True, timeout=25)
        prefix.with_suffix('.stdout').write_text(p.stdout)
        prefix.with_suffix('.stderr').write_text(p.stderr)
        self.assertEqual((p.returncode, p.stderr), (0, ''), p.stdout+p.stderr)
        out = json.loads(p.stdout)
        self.assertNotIn('missing_api', out, 'missing portable supplement preview API')
        return out

    def good(self, **options):
        out = self.call(**options)
        self.assertNotIn('error', out, out)
        return out

    def test_one_bundle_embeds_every_actual_dependency_including_stock_instead_of_package_references(self):
        out = self.good(); result = out['result']; envelope = json.loads(result['raw'])
        self.assertEqual(envelope['version'], 4)
        self.assertEqual([f['type'] for f in envelope['files']], ['strategy', 'resources'])
        resources = json.loads(base64.b64decode(envelope['files'][1]['data_base64']))
        self.assertEqual(resources.get('package_files', []), [])
        self.assertEqual(len(resources['files']), 6)
        original = {f['id']: f for f in out['proposal']['resource_kit']['files']}
        for f in resources['files']:
            raw = base64.b64decode(f['data_base64'])
            self.assertEqual(raw, base64.b64decode(original[f['id']]['data_base64']))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), f['sha256'])
            self.assertEqual(len(raw), f['byte_length'])
        self.assertTrue(resources['audit']['complete'])
        self.assertNotIn('UNSELECTED_PRIVATE', result['raw'])
        self.assertEqual(hashlib.sha256(result['raw'].encode()).hexdigest(), result['sha256'])

    def test_readonly_data_does_not_grant_export_apply_or_combined_native_proof(self):
        result = self.good()['result']
        for key in ('can_apply', 'can_export', 'combined_verified', 'actual_device_calls', 'config_source_proved'):
            self.assertIs(result[key], False)
        self.assertEqual(result['mode'], 'supplement-portable-preview-v1')
        self.assertEqual(result['base_sha256'], hashlib.sha256(self.current.encode()).hexdigest())
        self.assertFalse((self.root/'nfqws2.conf').exists())

    def test_receiver_blob_name_conflict_uses_hash_path_and_preserves_the_foreign_file(self):
        foreign = b'FOREIGN_BLOB'
        path = self.dest/'blobs/custom.bin'; path.write_bytes(foreign); inode = path.stat().st_ino
        out = self.good(); plan = out['import_plan']; target = '/opt/etc/nfqws2/blobs/imported/'+hashlib.sha256(BLOB).hexdigest()+'.bin'
        self.assertTrue(plan['ready'], plan['problems'])
        values = {r['key']: r['after'] for r in plan['changes']}
        self.assertIn('--blob=owned:@'+target, values['NFQWS_BASE_ARGS'])
        self.assertIn('--lua-desync=fake:blob=owned', values['NFQWS_ARGS_CUSTOM'])
        self.assertIn('--comment=custom.bin.target.example', values['NFQWS_ARGS_CUSTOM'])
        self.assertEqual((path.read_bytes(), path.stat().st_ino), (foreign, inode))
        self.assertFalse((self.dest/'blobs/imported').exists())

    def test_matching_receiver_stock_lua_is_reused_without_trust_prompt_or_overwrite(self):
        plan = self.good()['import_plan']; lua = [f for f in plan['files'] if f['kind']=='lua']
        self.assertTrue(plan['ready'], plan['problems']); self.assertEqual(len(lua), 2)
        self.assertTrue(all(f['reuse'] and not f['replace'] and '/imported/' not in f['path'] for f in lua))

    def test_receiver_changed_stock_lua_demands_explicit_trust_for_an_imported_copy(self):
        path = self.dest/'lua/zapret-lib.lua'; path.write_text('-- FOREIGN LUA\n'); inode = path.stat().st_ino
        plan = self.good()['import_plan']; self.assertFalse(plan['ready'])
        self.assertIn('lua_trust', [p['code'] for p in plan['problems']])
        self.assertTrue(any('/lua/imported/' in f['path'] for f in plan['files']))
        self.assertEqual((path.read_text(), path.stat().st_ino), ('-- FOREIGN LUA\n', inode))

    def test_incoming_names_never_supply_receiver_package_lua_trust(self):
        plan = self.good(receiver_baseline={})['import_plan']; self.assertFalse(plan['ready'])
        self.assertIn('lua_trust', [p['code'] for p in plan['problems']])

    def test_existing_wrong_content_at_imported_hash_target_refuses_and_preserves(self):
        directory = self.dest/'blobs/imported'; directory.mkdir(mode=0o755)
        path = directory/(hashlib.sha256(BLOB).hexdigest()+'.bin'); path.write_bytes(b'FOREIGN_AT_HASH')
        plan = self.good()['import_plan']; self.assertFalse(plan['ready'])
        self.assertIn('file_conflict', [p['code'] for p in plan['problems']]); self.assertEqual(path.read_bytes(), b'FOREIGN_AT_HASH')

    def test_OpenWrt_translates_only_known_file_operands_and_keeps_domain_comment_blob_names(self):
        plan = self.good(profile='openwrt')['import_plan']; self.assertTrue(plan['ready'], plan['problems'])
        values = {r['key']: r['after'] for r in plan['changes']}
        self.assertIn('--lua-init=@/etc/nfqws2/lua/zapret-lib.lua', values['NFQWS_BASE_ARGS'])
        self.assertIn('--blob=owned:@/etc/nfqws2/blobs/imported/', values['NFQWS_BASE_ARGS'])
        self.assertIn('--comment=custom.bin.target.example', values['NFQWS_ARGS_CUSTOM'])
        self.assertIn('--hostlist-domains=target.example', values['NFQWS_ARGS_CUSTOM'])

    def test_changed_AUTO_after_proposal_refuses_before_serialization(self):
        out = self.call(source_change='CHANGED_AUTO\n'); self.assertIn('error', out)
        self.assertEqual((self.root/'lists/auto.list').read_text(), 'CHANGED_AUTO\n')

    def test_tampered_buffer_config_scope_or_permission_flag_never_becomes_a_portable_bundle(self):
        for tamper in ('buffer', 'config', 'scope', 'flag'):
            with self.subTest(tamper=tamper): self.assertIn('error', self.call(tamper=tamper))

    def test_resource_path_or_placeholder_in_literal_comment_refuses_instead_of_broad_rewrite(self):
        for comment in ('/opt/etc/nfqws2/blobs/custom.bin', 'RESOURCE_1'):
            with self.subTest(comment=comment):
                out = self.call(current=self.current.replace('--comment=custom.bin.target.example', '--comment='+comment))
                self.assertIn('error', out)

    def test_list_name_collision_is_an_explicit_readonly_replacement_proposal_not_an_applied_change(self):
        path = self.dest/'lists/user.list'; path.write_bytes(b'FOREIGN_LIST\n'); inode = path.stat().st_ino
        out = self.good(); f = next(f for f in out['import_plan']['files'] if f['kind']=='lists' and f['target_name']=='user.list')
        self.assertTrue(f['replace']); self.assertFalse(f['reuse']); self.assertIs(out['result']['can_apply'], False)
        self.assertEqual((path.read_bytes(), path.stat().st_ino), (b'FOREIGN_LIST\n', inode))


if __name__ == '__main__':
    unittest.main()
