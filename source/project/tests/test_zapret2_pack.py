"""Exercise the bundled library through the same document reader used by Import."""
import collections
import json
import subprocess
import unittest

from test_dpi_normalize import PHP, PUBLIC


class Zapret2PackTests(unittest.TestCase):
    def php(self, body):
        code = "require $argv[1].'/zapret2-pack.php';require $argv[1].'/import-document.php';" + body
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC)], capture_output=True, text=True, timeout=100)
        self.assertEqual(result.returncode, 0, result.stdout[-1200:] + result.stderr)
        return json.loads(result.stdout)

    def test_exact_module_and_every_catalog_section_are_visible(self):
        catalog = self.php("echo json_encode(AsusZapret2Pack::catalog());")
        self.assertEqual(catalog['source_sha256'], 'd18cce3864ff72fd19117e85833bd4d8f5b93f19d5cb62006cc44a8522d862ed')
        entries = [row for row in catalog['entries'] if not row.get('collection')]
        self.assertEqual(collections.Counter(row['group'] for row in entries),
                         {'presets': 98, 'http80': 161, 'tcp': 395, 'udp': 58, 'voice': 69})
        self.assertEqual(len({row['id'] for row in entries}), len(entries))

    def test_sources_are_traceable_and_import_shows_plain_credits(self):
        catalog, cited, context = self.php("""
        $catalog=AsusZapret2Pack::catalog();$rows=$catalog['entries'];
        $cited=array_values(array_filter($rows,fn($row)=>$row['title']==='general (alt v4) 1.8.2 / 1.8.4'))[0];
        $doc=AsusImportDocument::read(AsusZapret2Pack::documents($cited['id']));
        echo json_encode([$catalog,$cited,$doc['context']['comment']]);
        """)
        self.assertTrue(all('source_url' not in row for row in catalog['entries'] + catalog['assets']))
        rows = json.loads((PUBLIC/'zapret2-pack/catalog.json').read_bytes())['entries']
        self.assertEqual(catalog['archive_date'], '2026-11-01')
        self.assertEqual(next(r['updated_at'] for r in rows if r['title'] == 'Preset.X1'), '2026-03-01')
        base = 'https://git2.zapret.moe/zapretdiscordyoutube/magisk-zapret2/src/commit/7a05a2267df82dfa765cc7ff68cefd57fb45086a/zapret2/'
        self.assertEqual(len({row['source_url'] for row in rows}), len(rows))
        for row in rows:
            if row['group'] == 'presets':
                self.assertTrue(row['source_url'].startswith(base + 'presets/'))
            else:
                path, line = row['source_url'].split('#L')
                self.assertEqual(path, base + 'strategy-catalogs/' + row['group'] + '.txt')
                self.assertGreater(int(line), 0)
            self.assertTrue(row['attribution'].strip())
            self.assertNotIn('://', row['attribution'])
        self.assertEqual(cited['attribution'], 'Flowseal/zapret-discord-youtube')
        self.assertIn(cited['attribution'], context)
        self.assertNotIn('://', context)
        self.assertNotIn('#L', context)
        self.assertTrue(any(r['attribution'] == 'loop-uh' for r in rows))
        self.assertEqual(next(r['attribution'] for r in rows if r['title']=='ALL TCP & UDP YTDisBystro_3_4_v1'),
                         'zapretdiscordyoutube/magisk-zapret2')

    def test_playback_preset_keeps_the_three_filters_and_all_external_operands(self):
        data = self.php("""
        $rows=AsusZapret2Pack::catalog()['entries'];
        $row=array_values(array_filter($rows,fn($r)=>$r['title']==='ALL TCP & UDP YTDisBystro_3_4_v1'))[0];
        $doc=AsusImportDocument::read(AsusZapret2Pack::documents($row['id']));
        echo json_encode([$row,$doc['values'],$doc['ports'],$doc['resources'],$doc['package_files'],$doc['audit']]);
        """)
        row, values, ports, resources, packaged, audit = data
        self.assertEqual(row['sha256'], '987f48986c03a710137076f1dab68ce9c0d7d87a2ee506bec9f931b29f099d70')
        self.assertEqual(ports, {'TCP_PORTS': '80,443', 'UDP_PORTS': '443:65535'})
        self.assertEqual(values['NFQWS_ARGS_CUSTOM'].split().count('--new'), 2)
        self.assertEqual(sum(r['kind'] == 'lists' for r in resources), 3)
        self.assertTrue(any(r['kind'] == 'blobs' and r['byte_length'] == 228 for r in resources))
        self.assertEqual({r['name'] for r in packaged}, {'zapret-lib.lua','zapret-antidpi.lua','zapret-auto.lua'})
        self.assertTrue(audit['complete'])
        self.assertEqual(audit['unresolved'], [])

    def test_entire_offline_library_resolves_in_the_normal_import_preview(self):
        result = self.php("""
        require $argv[1].'/import-plan.php';
        $catalog=AsusZapret2Pack::catalog();$counts=[];$errors=[];$changedLuaRejected=false;
        $ctx='ASUS_CLIENTS4="192.0.2.9"'."\\n";
        foreach(array_merge($catalog['entries'],$catalog['assets']) as $row){
            if(($row['collection']??null)==='zemidala'||!empty($row['unavailable'])||!empty($row['resident']))continue;
            try {
                $doc=AsusImportDocument::read(AsusZapret2Pack::documents($row['id']));
                $local=[];
                foreach($doc['package_files'] as $f)$local[]=$f+['state'=>'available','bundled_resource'=>true,
                    'bundled_name'=>$f['name'],'bundled_lua'=>$f['kind']==='lua'];
                $selection=['blocks'=>[],'shared'=>[],'ports'=>[],'files'=>[], 'dns'=>[],
                    'trusted_lua'=>false,'allow_shared_impact'=>true,'allow_incomplete'=>true];
                foreach($doc['values'] as $key=>$value){
                    $area=in_array($key,AsusImportConfig::BLOCKS,true)?'blocks':'shared';
                    $selection[$area][]=compact('key','value');
                }
                foreach($doc['ports'] as $key=>$value)$selection['ports'][]=compact('key','value');
                foreach($doc['resources'] as $f)$selection['files'][]=['id'=>$f['id']];
                $inventory=['files'=>$local,'scan_truncated'=>false];
                $plan=AsusImportPlan::prepare($doc,$selection,$ctx,$inventory,null);
                foreach($doc['resources'] as $file){
                    if($changedLuaRejected||$file['kind']!=='lua'||$row['group']!=='presets')continue;
                    $edited=$selection;
                    foreach($edited['files'] as &$pick)if($pick['id']===$file['id']){
                        $pick['text']=base64_decode($file['data_base64'],true)."\n-- edited\n";
                    }
                    unset($pick);
                    $changed=AsusImportPlan::prepare($doc,$edited,$ctx,$inventory,null);
                    $changedLuaRejected=!$changed['ready']&&in_array('lua_trust',array_column($changed['problems'],'code'),true);
                }
                $unexpected=$plan['warnings'];
                if(!$plan['ready']||$unexpected||!str_contains($plan['config'],$ctx)||str_contains($plan['config'],'RESOURCE_'))
                    throw new RuntimeException(json_encode([$plan['problems'],$unexpected]));
                if(empty($row['collection']))$counts[$row['group']]=1+($counts[$row['group']]??0);
            } catch(Throwable $e){$errors[]=[$row['title'],$e->getMessage()];}
        }
        echo json_encode([$counts,$errors,$changedLuaRejected]);
        """)
        counts, errors, changed_lua_rejected = result
        self.assertEqual(errors[:4], [])
        self.assertEqual(counts['presets'], 98)
        self.assertTrue(changed_lua_rejected)
        self.assertGreater(sum(counts[k] for k in ('http80','tcp','udp','voice')), 600)

    def test_new_module_components_reach_a_real_queue_within_the_existing_budget(self):
        result = self.php("""
        require $argv[1].'/strategy-synthesis.php';
        $budget=['max_repeats'=>2];
        $matrix=NfqwsStrategySynthesis::matrix($budget);
        $out=[];
        foreach(NfqwsStrategySynthesis::queue($budget) as $recipe) {
            $out[]=NfqwsStrategySynthesis::compile($recipe);
        }
        echo json_encode([$matrix['module_examples']??null,$matrix['dimensions'],$out]);
        """)
        examples, axes, compiled = result
        self.assertIsInstance(examples, dict)
        for protocol in ('http', 'tls', 'quic'):
            self.assertGreater(examples[protocol], 0)
        self.assertIn('sld+1', axes['split_positions'])
        self.assertIn(211, axes['sequence_overlap'])
        self.assertLessEqual(len(compiled), 24)
        wire = json.dumps(compiled)
        self.assertRegex(wire, r'pos=(?:sld\+1|2,midsld-2|1,host\+2,sld\+2)')
        self.assertNotRegex(wire, r':repeats=[3-9]')
