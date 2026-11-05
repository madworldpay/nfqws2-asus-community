"""The real API binds optional rules to a signed global document and preview."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC, ROOT
from test_import_torrent_sites import fixture, CURRENT
import test_profile_catalog as catalog_fixtures


class TorrentSitesApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog_fixtures.ProfileCatalogTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        catalog_fixtures.ProfileCatalogTests.tearDownClass()

    def call(self, ops, category='global', bad_hash=False):
        raw, selected, _, _, option = fixture()
        selected['torrent_sites'] = option
        catalog = catalog_fixtures.ProfileCatalogTests().manifest()
        catalog['profiles'][0].update(id='general', category=category, size=len(raw.encode()), sha256='0'*64 if bad_hash else hashlib.sha256(raw.encode()).hexdigest())
        signed = catalog_fixtures.ProfileCatalogTests().signed(catalog)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'resources').mkdir(mode=0o755)
            for kind in ['lua','blobs','lists']:
                (root/'resources'/kind).mkdir(mode=0o755)
            (root/'resources/nfqws2.conf').write_text(CURRENT)
            manifest = {}
            for name in ['zapret-lib.lua','zapret-antidpi.lua']:
                data = ('-- fixture packaged ' + name + '\n').encode()
                (root/'resources/lua'/name).write_bytes(data)
                manifest['lua/'+name] = {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            (root/'resources/blobs/tls_clienthello.bin').write_bytes((ROOT/'asus/blobs/files/tls_clienthello.bin').read_bytes())
            code = '''require $argv[1].'/import-api.php';require_once $argv[1].'/profile-catalog-transport.php';$v=json_decode(stream_get_contents(STDIN),true);$r=$argv[2];$u=(int)$argv[3];
$tx=new AsusImportTransaction(new AsusImportStore($r.'/journal',$u),new AsusSmartDnsStore($r.'/dns',$u),$r.'/resources',$r.'/resources/nfqws2.conf',$u);
$resources=new ReflectionProperty($tx,'resources');$resources->setValue($tx,new AsusShareResources($r.'/resources',$u,$v['manifest']));
$catalog=new AsusProfileCatalogTransport($v['key'],fn($url,$cap,$deadline)=>$v['catalog'],$r.'/catalog',$u,fn()=>1000,88);
$api=new AsusImportApi($tx,fn()=>null,new AsusSmartDnsStore($r.'/dns',$u),$catalog);$proof=null;$out=[];
foreach($v['ops']as $op){try{
 $sel=$v['selection'];if(($op[1]??true)===false)unset($sel['torrent_sites']);
 if($op[0]==='wrong_module'){copy($r.'/resources/lua/zapret-lib.lua',$r.'/resources/lua/zapret-antidpi.lua');continue;}
 if($op[0]==='change_blob'){file_put_contents($r.'/resources/blobs/tls_clienthello.bin','operator edit');continue;}
 $post=['cmd'=>$op[0]==='prepare'?'importprepare':'importapply','csrf_token'=>'fixture','documents'=>json_encode([$v['document']]),'selection'=>json_encode($sel)];
 if($op[0]!=='prepare')$post+=['proof'=>$proof,'request_id'=>str_repeat('a',32)];
 $value=$api->handle($post,str_repeat('f',64),1000);if($op[0]==='prepare')$proof=$value['proof'];$out[]=$value;
}catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}}
echo json_encode(['results'=>$out,'config'=>file_get_contents($r.'/resources/nfqws2.conf')],JSON_THROW_ON_ERROR);'''
            value = {'document':raw,'selection':selected,'manifest':manifest,'key':catalog_fixtures.ProfileCatalogTests.public,'catalog':signed,'ops':ops}
            result = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],input=json.dumps(value),capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stderr,'')
            return json.loads(result.stdout)

    def test_signed_global_document_prepares_and_applies_exact_visible_rule(self):
        value = self.call([['prepare'],['apply']])
        self.assertTrue(value['results'][0].get('ready'),value)
        self.assertEqual(value['results'][1].get('state'),'committed',value)
        self.assertEqual(value['results'][0]['config'],value['config'])

    def test_provider_or_changed_catalog_hash_cannot_borrow_general_scope(self):
        for options in [{'category':'provider'},{'bad_hash':True}]:
            value = self.call([['prepare']],**options)
            self.assertEqual(value['results'],[{'error':'invalid_torrent_sites_source'}])
            self.assertEqual(value['config'],CURRENT)

    def test_toggling_after_preview_rejects_old_proof_without_any_write(self):
        value = self.call([['prepare'],['apply',False]])
        self.assertEqual(value['results'][1],{'error':'invalid_proof'})
        self.assertEqual(value['config'],CURRENT)

    def test_stock_blob_changed_after_preview_cannot_apply_stale_rule(self):
        value = self.call([['prepare'],['change_blob'],['apply']])
        self.assertEqual(value['results'][-1],{'error':'stale_preview'})
        self.assertEqual(value['config'],CURRENT)

    def test_wrong_packaged_module_copy_cannot_satisfy_required_library_name(self):
        value = self.call([['wrong_module'], ['prepare']])
        plan = value['results'][0]
        self.assertFalse(plan.get('ready'), value)
        self.assertIn('torrent_sites_incompatible', [row['code'] for row in plan['problems']])
        self.assertEqual(value['config'], CURRENT)


if __name__=='__main__':
    unittest.main()
