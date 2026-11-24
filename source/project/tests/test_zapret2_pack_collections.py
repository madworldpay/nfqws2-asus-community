"""Supplemental collections retain exact provenance and enter the normal import path."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from test_dpi_normalize import PHP, PUBLIC, ROOT

RAW_SHA = {
    'tcp_alt1': 'fe1f26637c9888b0c083feb0d82cb32f130395db755ac884a22f522bdde51205',
    'tcp_hostfake': '99215abcd31f18c9157f07739a88105b7d33c45daffcfcefeb79b4e2b05b729a',
    'full_combo': 'ad3672d88dab7a187e14360ac0307e951323b61808bd986b971dfd26632108fe',
    'tcp_oob': 'ffac33e50e459f4b197b64b19f707e282925ae9bc37038cdad0f12aaca26f951',
}
BASELINE_SHA = {
    'catalog.json':'ab0c78e7cb1b78c7a4ef7cb61ad3e288ace59a81645f7abf53e30c15ab8e3727',
    'http80.json':'9d4bd22b5936d063f3b3c018d139a108c4e1d4c00e4816620b914c27dece0b28',
    'presets.json':'66af49d57519af93cb64975a2674a394522232674802a25b7ae05e9bf6c000a3',
    'priors.json':'d21f9a3ce272c0e4839e2566fd746b361f10dcca3726556a2c25189817d79906',
    'resources.json':'8b4a1baca4711a0d99dd157866b6f3be40e08fa2bd62e4fd5b0e8f4d13a61626',
    'samples.json':'2f7317fa4cd582449d647c4f1b9acf23538a966e9ea68129f7e047813e4939f8',
    'tcp.json':'2508a96708ea5973e47ea30ff43ce2aa2c3fc120571e1e8a64808f4129302a57',
    'udp.json':'73d6218504fb178180325f75c0da154f6614d765bb146c1be2611ac169083dd3',
    'voice.json':'dbe9e12fd0e1faf791b9546dcd27f754202313ec10696f05758c037d184b9149',
}


class SupplementalPackTests(unittest.TestCase):
    def php(self, body, stdin=None):
        code="require $argv[1].'/zapret2-pack.php';require $argv[1].'/import-document.php';"+body
        result=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=None if stdin is None else json.dumps(stdin),capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout[-1500:]+result.stderr)
        self.assertEqual(result.stderr,'')
        return json.loads(result.stdout)

    def additions(self):
        path=PUBLIC/'zapret2-pack/collections.json'
        self.assertTrue(path.is_file(),'missing supplemental collection')
        return json.loads(path.read_bytes())

    def test_existing_build105_library_bytes_and_documents_remain_unchanged(self):
        for name,want in BASELINE_SHA.items():
            self.assertEqual(hashlib.sha256((PUBLIC/'zapret2-pack'/name).read_bytes()).hexdigest(),want,name)
        for ident,want in [('ba5c701ca2735199e8653598','6771205251738ce1f9c0e12a63b104fe403e9ec576132409032e94dc64dbeecf'),('18cc4afa20db36510afa7c04','95cd09e318c5ee32dee13b909a302f923cf6a58bdae2ca89dee227c560469b4b')]:
            docs=self.php("echo json_encode(AsusZapret2Pack::documents('"+ident+"')); ")
            self.assertEqual(hashlib.sha256('\0'.join(docs).encode()).hexdigest(),want)

    def test_new_collection_has_four_deduplicated_typed_presets_with_original_hashes(self):
        catalog=self.php("echo json_encode(AsusZapret2Pack::catalog());")
        legacy=json.loads((PUBLIC/'zapret2-pack/catalog.json').read_bytes())
        self.assertEqual([{k:v for k,v in r.items() if k!='source_url'} for r in legacy['entries']],catalog['entries'][:len(legacy['entries'])])
        rows=[r for r in catalog['entries'] if r.get('collection')=='avatar']
        self.assertEqual({r['source_id'] for r in rows},set(RAW_SHA))
        for row in rows:
            self.assertEqual(row['group'],'presets');self.assertEqual(row['kind'],'strategy')
            self.assertEqual(row['sha256'],RAW_SHA[row['source_id']])
            self.assertEqual(row['updated_at'],'2026-11-21')
            self.assertEqual(row['attribution'],'avatarDD/zapret-gui')
            self.assertTrue(row['description'].strip())
            self.assertNotIn('source_url',row);self.assertEqual(row['unavailable'],[])
            if row['source_id']=='tcp_oob':self.assertEqual(row['title'],'FakeSplit · HTTP/TLS')
        self.assertEqual(len({r['id'] for r in catalog['entries']}),len(catalog['entries']))

    def test_zemidala_catalog_lists_only_eligible_unique_provider_rules(self):
        catalog = self.php("echo json_encode(AsusZapret2Pack::catalog());")
        rows = [r for r in catalog['entries'] if r.get('collection') == 'zemidala']
        self.assertEqual(len(rows), 67)
        self.assertEqual(len({row['id'] for row in rows}), 67)
        self.assertTrue(all(row['group'] == 'presets' and row['attribution'] == 'Zemidala' for row in rows))
        self.assertFalse(any('source_page' in row or 'steps' in row for row in rows))

    def test_zemidala_transport_rejects_a_changed_or_non_catalog_response(self):
        result = self.php("""
        require $argv[1].'/profile-catalog-transport.php';
        $calls=[];$fixture='{}';
        $transport=new AsusProfileCatalogTransport(read: function($url,$cap,$deadline)use(&$calls,$fixture){
            $calls[]=[$url,$cap];return $fixture;
        });
        $digest=hash('sha256',$fixture);
        $correct=$transport->zemidalaPage('data/AS123.json',strlen($fixture),$digest);
        $errors=[];
        foreach([['data/pending/AS123.json',str_repeat('0',64)],['../README.md',$digest]] as [$path,$sha]){
            try{$transport->zemidalaPage($path,strlen($fixture),$sha);}
            catch(RuntimeException $e){$errors[]=$e->getMessage();}
        }
        echo json_encode([$correct,$calls,$errors]);
        """)
        self.assertEqual(result[0], '{}')
        self.assertEqual([url.split('/data/')[-1] for url, _ in result[1]], ['AS123.json', 'pending/AS123.json'])
        self.assertTrue(all(url.startswith('https://raw.githubusercontent.com/zemidala/nfqws2-strategies/')
                            and cap == 2 for url, cap in result[1]))
        self.assertEqual(result[2], ['resource_unavailable', 'resource_unavailable'])

    def test_private_offline_payload_requires_an_exact_snapshot(self):
        spec = importlib.util.spec_from_file_location('public_payload', ROOT/'webui/public_payload.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        record = {'proto': 'tls', 'steps': ['--lua-desync=pass']}
        ident = hashlib.sha256(b'zemidala\0tls\0--lua-desync=pass').hexdigest()[:24]
        name = 'zapret2-pack/zemidala-offline.json'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public, dist = root/'public', root/'dist'
            metadata = 'zapret2-pack/zemidala-index.json'
            for tree in (public, dist):
                path = tree/metadata
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({'entries': [{'id': ident}]}))
            local = root/'offline.json'
            original = json.dumps({ident: record}).encode()
            local.write_bytes(original)
            with patch.dict(os.environ, {'NFQWS_ZEMIDALA_OFFLINE_INPUT': ''}):
                self.assertNotIn(name, helper.payload(public, dist, {}))
            with patch.dict(os.environ, {'NFQWS_ZEMIDALA_OFFLINE_INPUT': str(local)}):
                self.assertEqual(helper.payload(public, dist, {})[name], (original, 0o644))
                local.write_text(json.dumps({ident: {**record, 'proto': 'http'}}))
                with self.assertRaisesRegex(RuntimeError, 'Zemidala'):
                    helper.payload(public, dist, {})

    def test_raw_sources_license_and_dependency_identity_can_be_rechecked_offline(self):
        data=self.additions();collection=data['collections']['avatar']
        self.assertEqual(collection['commit'],'582e518cddde85187bec0aac9b38dee94f9a4186')
        self.assertEqual(hashlib.sha256(collection['license_text'].encode()).hexdigest(),'7d77b4d431ad88152fab3e33550437729df283dbd9a1dea5ea1776dc8e82b2de')
        for row in data['entries']:
            source=data['sources'][row['source_id']]
            raw=base64.b64decode(source['data_base64'],validate=True)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
            self.assertEqual(json.loads(raw)['id'],row['source_id'])
            self.assertEqual(source['git_blob_sha1'],hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest())
        pool=json.loads((PUBLIC/'zapret2-pack/resources.json').read_bytes())
        archive=ROOT.parent/'sources/zapret2-038c97e5.tar.gz'
        if archive.is_file():
            with tarfile.open(archive)as tar:
                for name in ['zapret-lib.lua','zapret-antidpi.lua']:
                    raw=tar.extractfile(next(n for n in tar.getnames()if n.endswith('/lua/'+name))).read()
                    asset=next(r for r in pool.values()if r['name']==name)
                    self.assertEqual(asset['sha256'],hashlib.sha256(raw).hexdigest())
                    self.assertEqual(asset['byte_length'],len(raw))
        for template in data['templates'].values():
            self.assertEqual({pool[x]['name'] for x in template['resources']},{'zapret-lib.lua','zapret-antidpi.lua'})
            self.assertNotIn('--blob=',template['config'])

    def test_combined_imports_resolve_every_dependency_without_supplying_new_lua_or_blobs(self):
        result=self.php("""
        require $argv[1].'/import-plan.php';$out=[];
        foreach(AsusZapret2Pack::catalog()['entries']as $row){if(($row['collection']??'')!=='avatar')continue;
            $doc=AsusImportDocument::read(AsusZapret2Pack::documents($row['id']));
            $selection=['blocks'=>[],'shared'=>[],'ports'=>[],'files'=>[],'dns'=>[],
                'trusted_lua'=>false,'allow_shared_impact'=>true,'allow_incomplete'=>false];
            foreach($doc['values']as $key=>$value){$area=in_array($key,AsusImportConfig::BLOCKS,true)?'blocks':'shared';$selection[$area][]=compact('key','value');}
            foreach($doc['ports']as $key=>$value)$selection['ports'][]=compact('key','value');
            $local=[];foreach($doc['package_files']as $f)$local[]=$f+['state'=>'available','bundled_resource'=>true,'bundled_name'=>$f['name'],'bundled_lua'=>true];
            $owner='ASUS_CLIENTS4="192.0.2.9"'."\\n".'ISP_INTERFACE="eth9"'."\\n";
            $plan=AsusImportPlan::prepare($doc,$selection,$owner,['files'=>$local,'scan_truncated'=>false],null);
            $bad=$local;$bad[0]['sha256']=str_repeat('0',64);
            $missing=AsusImportPlan::prepare($doc,$selection,$owner,['files'=>$bad,'scan_truncated'=>false],null);
            $out[$row['source_id']]=['doc'=>$doc,'plan'=>$plan,'missing'=>$missing];
        }echo json_encode($out);
        """)
        self.assertEqual(set(result),set(RAW_SHA))
        for ident,item in result.items():
            plan,doc=item['plan'],item['doc']
            self.assertTrue(plan['ready'],(ident,plan));self.assertEqual(plan['warnings'],[])
            self.assertEqual(plan['files'],[]);self.assertEqual(doc['resources'],[])
            self.assertEqual(len(doc['package_files']),2)
            self.assertEqual(plan['draft'],None);self.assertNotIn('RESOURCE_',plan['config'])
            self.assertIn('ASUS_CLIENTS4="192.0.2.9"',plan['config']);self.assertIn('ISP_INTERFACE="eth9"',plan['config'])
            self.assertEqual(doc['ports'],{'TCP_PORTS':'80,443','UDP_PORTS':'' if ident=='tcp_oob' else '443'})
            self.assertTrue(doc['audit']['complete']);self.assertEqual(doc['audit']['unresolved'],[])
            comment=doc['context']['comment']
            self.assertIn('0 runs',comment);self.assertIn('provider, region, mode',comment)
            self.assertIn(RAW_SHA[ident],comment);self.assertNotIn('Magisk v',comment)
            self.assertFalse(item['missing']['ready'])
            self.assertIn('package_resource_unavailable',[p['code']for p in item['missing']['problems']])

    def test_arguments_match_originals_except_documented_single_marker_normalization(self):
        data=self.additions()
        for row in data['entries']:
            original=json.loads(base64.b64decode(data['sources'][row['source_id']]['data_base64']))
            program=data['templates'][row['id']]['config'].split('NFQWS_ARGS_CUSTOM="',1)[1].split('"\n',1)[0]
            expected=' --new '.join(x['args']for x in original['profiles']if x['enabled'])
            if row['source_id']=='tcp_oob':expected=expected.replace('fakedsplit:pos=1,midsld:','fakedsplit:pos=1:')
            self.assertEqual(program,expected)
            self.assertNotIn('--lua-desync=syndata',program)

    def test_supplement_cannot_override_legacy_ids_or_resource_hash_proofs(self):
        data=self.additions();legacy=json.loads((PUBLIC/'zapret2-pack/catalog.json').read_bytes())
        pool=json.loads((PUBLIC/'zapret2-pack/resources.json').read_bytes())
        for collision in ['entry','resource']:
            with self.subTest(collision=collision),tempfile.TemporaryDirectory(prefix='nfqws-pack-conflict-')as tmp:
                root=Path(tmp);(root/'zapret2-pack.php').write_bytes((PUBLIC/'zapret2-pack.php').read_bytes())
                shutil.copytree(PUBLIC/'zapret2-pack',root/'zapret2-pack')
                altered=json.loads(json.dumps(data))
                if collision=='entry':altered['entries'][0]['id']=legacy['entries'][0]['id']
                else:altered['resources'][next(iter(pool))]={'kind':'lua','sha256':'0'*64}
                (root/'zapret2-pack/collections.json').write_text(json.dumps(altered))
                operation='AsusZapret2Pack::catalog()'if collision=='entry'else "AsusZapret2Pack::documents('"+data['entries'][0]['id']+"')"
                code="require $argv[1].'/zapret2-pack.php';try{"+operation+";echo '{}';}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
                result=subprocess.run([PHP,'-n','-r',code,str(root)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(json.loads(result.stdout),{'error':'package_resource_unavailable'})

    def test_equivalent_aliases_and_unverified_sources_are_deferred_without_false_proof(self):
        data=self.additions();deferred={r['source_id']:r for r in data['deferred']}
        for ident in ['tcp_alt2','quic_only','tcp_default','tcp_syndata','0adf38777f40','1c515c0165d9']:
            self.assertIn(ident,deferred)
        self.assertIn('full_combo',deferred['tcp_alt2']['reason'])
        self.assertIn('phase',deferred['tcp_syndata']['reason'])
        for ident in ['0adf38777f40','1c515c0165d9']:
            self.assertIn('permission',deferred[ident]['reason'])
            self.assertNotIn('steps',deferred[ident])
        full=next(r for r in data['entries']if r['source_id']=='full_combo')
        self.assertEqual(full['source_aliases'],['tcp_alt2'])


class PinnedMarkerParserTests(unittest.TestCase):
    def test_pinned_single_marker_parser_keeps_the_numeric_effective_position(self):
        if not shutil.which('gcc'):self.skipTest('requires compiler for pure pinned parser characterization')
        archive=ROOT.parent/'sources/zapret2-038c97e5.tar.gz'
        if not archive.is_file():self.skipTest('requires pinned source archive')
        def function(source,name):
            found=re.search(r'(?m)^[\w *]+\b'+name+r'\([^;]*?\)\s*\{',source);self.assertIsNotNone(found,name)
            start=found.start();at=found.end();depth=1
            while depth:
                depth+=int(source[at]=='{')-int(source[at]=='}');at+=1
            return source[start:at]
        with tarfile.open(archive)as tar:
            read=lambda suffix:tar.extractfile(next(n for n in tar.getnames()if n.endswith('/'+suffix))).read().decode()
            helpers=read('nfq2/helpers.c');protocol=read('nfq2/protocol.c');header=read('nfq2/protocol.h')
            enum=re.search(r'typedef enum \{\s*PM_ABS.*?} t_marker;',header,re.S).group()
            struct=re.search(r'struct proto_pos\s*\{.*?};',header,re.S).group()
            names=re.search(r'static const char \*posmarker_names\[\].*?;',protocol,re.S).group()
            source='#include <stdbool.h>\n#include <stdint.h>\n#include <string.h>\n#include <stdlib.h>\n#include <stdio.h>\n'+enum+struct+names
            source+='\n'+function(helpers,'str_index')+'\n'+function(helpers,'parse_int16')+'\n'+function(protocol,'posmarker_from_name')+'\n'+function(protocol,'posmarker_parse')
            source+='\nint main(void){struct proto_pos a,b,c;int x=posmarker_parse("1,midsld",&a),y=posmarker_parse("1",&b),z=posmarker_parse("method+2",&c);printf("%d %d %d %d %d %d %d %d %d\\n",x,a.marker,a.pos,y,b.marker,b.pos,z,c.marker,c.pos);}\n'
        with tempfile.TemporaryDirectory(prefix='nfqws-marker-parser-')as tmp:
            path=Path(tmp);(path/'probe.c').write_text(source)
            build=subprocess.run(['gcc','-std=c99',str(path/'probe.c'),'-o',str(path/'probe')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.check_output([str(path/'probe')],text=True)
            self.assertEqual(result.strip(),'1 0 1 1 0 1 1 6 2')


if __name__=='__main__':unittest.main()
