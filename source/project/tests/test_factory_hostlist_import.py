"""Package hostlists enter the active configuration only through normal import."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC, ROOT
from test_import_document import CTX, STRATEGY
from test_import_plan import CURRENT, selection


class FactoryHostlistImportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.opt = Path(temp.name) / 'opt'
        self.root = self.opt / 'etc/nfqws2'
        self.lists = self.root / 'lists'
        self.lists.mkdir(parents=True)
        (self.root / 'nfqws2.conf').write_text(CURRENT)
        share = self.opt / 'share/nfqws2-asus'
        self.factory = share / 'factory/lists'
        self.factory.mkdir(parents=True)
        for directory in (self.opt, *self.opt.rglob('*')):
            if directory.is_dir():
                directory.chmod(0o755)
        self.pins = {}
        self.assets = []
        for i, path in enumerate(sorted((ROOT / 'asus/zapret2-pack-lists').glob('*.list.gz')), 1):
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            self.assertEqual(path.name, f'z2-pack-{sha}.list.gz')
            (self.factory / path.name).write_bytes(raw)
            (self.factory / path.name).chmod(0o644)
            self.pins['lists/' + path.name] = {'bytes': len(raw), 'sha256': sha}
            self.assets.append({'id': sha[:32], 'kind': 'lists', 'name': path.name,
                                'byte_length': len(raw), 'sha256': sha, 'aliases': [f'RESOURCE_{i}']})
        self.baseline = share / 'report-baseline.json'
        self.baseline.write_text(json.dumps({'resources': {}, 'package_lists': self.pins}))
        self.baseline.chmod(0o644)

    def transaction(self, action, count=1):
        assets = self.assets[:count]
        aliases = [f['aliases'][0] for f in assets]
        blocks = [{'key': 'NFQWS_ARGS', 'value': '--filter-tcp=443 ' +
                   ' '.join('--hostlist=' + alias for alias in aliases)}]
        docs = [{**STRATEGY, 'blocks': blocks, 'shared': {},
                 'dependencies': [{'id': a, 'kind': 'file', 'included': True} for a in aliases]},
                {'type': 'nfqws2_resources', 'schema_version': 2, 'context': CTX,
                 'files': [], 'package_files': assets, 'audit': {'scope': 'static_explicit_references',
                 'references': [{'id': f'dependency_{i}', 'aliases': f['aliases'],
                                 'resource_id': f['id'], 'state': 'included'} for i, f in enumerate(assets, 1)],
                 'unresolved': [], 'missing_reason': '', 'complete': True}}]
        data = {'documents': list(map(json.dumps, docs)),
                'selection': selection(blocks=blocks, shared=[], files=[], trusted_lua=False)}
        script = """require $argv[1].'/import-transaction.php';
        [$unused,$public,$opt,$uid,$action]=$argv;$uid=(int)$uid;
        $root=$opt.'/etc/nfqws2';$factory=$opt.'/share/nfqws2-asus/factory/lists';
        $resources=new AsusShareResources($root,$uid,AsusShareResources::packageLua($opt,$uid),null,$factory);
        $tx=new AsusImportTransaction(new AsusImportStore($opt.'/journal',$uid),new AsusSmartDnsStore($opt.'/dns',$uid),
            $root,null,$uid,['resources'=>$resources]);
        $id=str_repeat('c',32);$in=json_decode(stream_get_contents(STDIN),true);
        try {
            if($action==='undo'){$out=$tx->undo($id);}else{
                $p=$tx->prepare($in['documents'],$in['selection']);
                if($action==='change_factory')file_put_contents($factory.'/'.$p['files'][0]['name'],'changed');
                if($action==='race')file_put_contents($root.'/lists/'.$p['files'][0]['name'],'owner');
                $out=$action==='preview'?$p:$tx->apply($p,$id);
            }
        }catch(Throwable $e){$out=['error'=>$e->getMessage()];}
        echo json_encode($out,JSON_THROW_ON_ERROR);"""
        result = subprocess.run([PHP, '-n', '-r', script, str(PUBLIC), str(self.opt),
                                 str(os.getuid()), action], input=json.dumps(data), text=True,
                                capture_output=True, check=True, timeout=15)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_preview_apply_and_undo_all_five_without_embedding_the_factory_bytes(self):
        self.assertEqual(len(self.assets), 5)
        self.assertGreater(sum(row['byte_length'] for row in self.assets), 524288)
        preview = self.transaction('preview', 5)
        self.assertTrue(preview.get('ready'), preview)
        self.assertEqual(len(preview['files']), 5)
        self.assertTrue(all('data_base64' not in row for row in preview['files']))
        self.assertEqual(list(self.lists.iterdir()), [])
        self.assertEqual(self.transaction('apply', 5)['state'], 'committed')
        for asset in self.assets:
            self.assertEqual((self.lists / asset['name']).read_bytes(), (self.factory / asset['name']).read_bytes())
        self.assertEqual(self.transaction('undo')['state'], 'undone')
        self.assertEqual(list(self.lists.iterdir()), [])
        self.assertEqual((self.root / 'nfqws2.conf').read_text(), CURRENT)

    def test_preserves_edited_existing_list_and_checks_the_factory_again_on_apply(self):
        name = self.assets[0]['name']
        active = self.lists / name
        active.write_bytes(b'owner')
        self.assertFalse(self.transaction('preview')['ready'])
        self.assertEqual(active.read_bytes(), b'owner')
        active.unlink()
        self.assertEqual(self.transaction('race'), {'error': 'source_changed'})
        self.assertEqual(active.read_bytes(), b'owner')
        active.unlink()
        self.assertEqual(self.transaction('change_factory'), {'error': 'source_changed'})
        self.assertFalse(active.exists())
        self.assertEqual((self.root / 'nfqws2.conf').read_text(), CURRENT)

    def test_reuses_old_active_resource_and_rejects_unpinned_or_unsafe_factory(self):
        name = self.assets[0]['name']
        file = self.factory / name
        shutil.copyfile(file, self.lists / name)
        self.baseline.write_text(json.dumps({'resources': self.pins}))
        preview = self.transaction('preview')
        self.assertTrue(preview.get('ready'), preview)
        self.assertEqual(preview['files'], [])
        (self.lists / name).unlink()
        file.chmod(0o666)
        self.assertFalse(self.transaction('preview')['ready'])
        file.chmod(0o644)
        self.baseline.write_text(json.dumps({'resources': {}, 'package_lists': {}}))
        self.assertFalse(self.transaction('preview')['ready'])
