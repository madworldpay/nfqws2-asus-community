"""Signed data-only add-ons extend actual imported host scopes without narrowing ALL."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC
from test_import_document import STRATEGY
from test_import_plan import selection
import test_profile_catalog as catalog_fixtures

ORIGIN = 'https://mad13mansprofy13.asuscomm.com:5443/nfqws-profiles/v1/addons/'
BACKUP = 'https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/source/catalog-addons/v1/'
CURRENT = '# owner\nASUS_CLIENTS4="192.0.2.8"\nISP_INTERFACE="eth9"\nTCP_PORTS="80,443"\nNFQWS_BASE_ARGS=""\nNFQWS_ARGS="--filter-tcp=80"\nNFQWS_EXTRA_ARGS=""\n'
SCOPED = '--filter-tcp=443 --hostlist-domains=base.example.org --lua-desync=multisplit:pos=1'


def addon(ident='riot-web', domains=None):
    return {'type':'nfqws2_import_addon','schema_version':1,'id':ident,'title':'Riot web',
            'description':'Web domains only; gameplay UDP is not tested.', 'kind':'scope_domains_v1',
            'domains':['riotgames.com','riotcdn.net'] if domains is None else domains}


def source(document=None, revision=1):
    document = addon() if document is None else document
    raw = json.dumps(document, separators=(',', ':'))
    entry = {'id':document['id'],'title':document['title'],'description':document['description'],
             'attribution':'Example author','updated_at':'2026-11-06T00:00:00Z','revision':1,
             'min_build':92,'size':len(raw.encode()),'sha256':hashlib.sha256(raw.encode()).hexdigest()}
    return raw, entry, {'entry':entry,'document':document,'catalog_revision':revision}


class ImportAddonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog_fixtures.ProfileCatalogTests.setUpClass()
        cls.signer = catalog_fixtures.ProfileCatalogTests()

    @classmethod
    def tearDownClass(cls):
        catalog_fixtures.ProfileCatalogTests.tearDownClass()

    def php(self, code, value, args=()):
        result = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),*map(str,args)],input=json.dumps(value),text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stderr,'')
        return json.loads(result.stdout)

    def verify(self, envelope, document=None):
        return self.php("$f=$argv[1].'/import-addon-catalog.php';if(!is_file($f)){echo '{\"error\":\"missing_feature\"}';exit;}require $f;$v=json_decode(stream_get_contents(STDIN),true);try{echo json_encode($v['document']===null?AsusImportAddonCatalog::verify($v['envelope'],$v['key']):AsusImportAddonCatalog::document($v['document']),JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}", {'envelope':envelope,'key':catalog_fixtures.ProfileCatalogTests.public,'document':document})

    def manifest(self, entry=None, revision=1):
        return {'schema_version':1,'revision':revision,'addons':[source()[1] if entry is None else entry]}

    def test_signed_catalog_is_independent_closed_and_preserves_attribution(self):
        manifest = self.manifest()
        self.assertEqual(self.verify(self.signer.signed(manifest)),manifest)
        changed = json.loads(self.signer.signed(manifest));changed['manifest']=changed['manifest'][:-4]+'AAAA'
        self.assertIn('error',self.verify(json.dumps(changed)))
        for mutate in [lambda v:v.update(profiles=[]),lambda v:v['addons'][0].update(url='https://evil.invalid'),lambda v:v['addons'].append(v['addons'][0]),lambda v:v['addons'][0].update(size=65537),lambda v:v['addons'][0].update(min_build=91),lambda v:v['addons'][0].update(updated_at='2026-02-30T00:00:00Z')]:
            bad=copy.deepcopy(manifest);mutate(bad)
            self.assertEqual(self.verify(self.signer.signed(bad)),{'error':'catalog_invalid'})

    def test_document_accepts_only_unique_normalized_public_domains_and_no_program(self):
        raw,_,_=source()
        self.assertEqual(self.verify('',raw),addon())
        for domains in [[],['riotgames.com']*2,['RiotGames.com'],['*.riotgames.com'],['https://riotgames.com'],['192.0.2.8'],['local'],['router.local'],['x.home.arpa'],['home.arpa'],['example.test'],['x.com\n--lua-init=@evil'],['x.com']*65]:
            bad=addon(domains=domains)
            self.assertEqual(self.verify('',json.dumps(bad)),{'error':'catalog_invalid'},domains)
        for field,value in [('kind','lua'),('commands',[]),('dns',{}),('url','https://evil.invalid')]:
            bad=addon();bad[field]=value
            self.assertEqual(self.verify('',json.dumps(bad)),{'error':'catalog_invalid'})

    def plan(self, blocks=None, extra='', current=CURRENT, options=None, resolved=None, lists=None, allow=False, omit_shared=False):
        blocks = {'NFQWS_ARGS':SCOPED} if blocks is None else blocks
        strategy=copy.deepcopy(STRATEGY);strategy['blocks']=[{'key':k,'value':v} for k,v in blocks.items()];strategy['shared']={'NFQWS_EXTRA_ARGS':extra,'NFQWS_BASE_ARGS':''}
        if omit_shared:strategy['shared']={}
        selected=selection(blocks=strategy['blocks'],shared=[{'key':k,'value':v} for k,v in strategy['shared'].items()],files=[],trusted_lua=False,allow_incomplete=False,allow_shared_impact=allow)
        raw,entry,src=source()
        selected['addons']=[{'id':entry['id'],'sha256':entry['sha256']}] if options is None else options
        value={'documents':[json.dumps(strategy)],'selection':selected,'current':current,'resolved':[src] if resolved is None else resolved,'lists':{} if lists is None else lists}
        code="""require $argv[1].'/import-plan.php';$v=json_decode(stream_get_contents(STDIN),true);$inventory=['files'=>[],'scan_truncated'=>false];foreach($v['lists']as $name=>$raw)$inventory['files'][]=['id'=>substr(hash('sha256','lists'.chr(0).$name),0,32),'kind'=>'lists','name'=>$name,'state'=>'available','sha256'=>hash('sha256',$raw),'byte_length'=>strlen($raw)];try{$reader=fn($file)=>$v['lists'][$file['name']];echo json_encode(AsusImportPlan::prepare(AsusImportDocument::read($v['documents']),$v['selection'],$v['current'],$inventory,null,null,null,$v['resolved'],$reader),JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
        return self.php(code,value)

    def test_scoped_import_unions_domains_and_preserves_algorithm_ports_clients_and_exclusions(self):
        extra='--hostlist-domains=base.example.org --hostlist-exclude-domains=riotcdn.net'
        result=self.plan(extra=extra)
        self.assertTrue(result.get('ready'),result)
        self.assertEqual(result['addons'][0]['action'],'scope_extended')
        self.assertEqual(result['addons'][0]['domains'],['riotgames.com'])
        changes={r['key']:r['after'] for r in result['changes']}
        self.assertEqual(changes['NFQWS_ARGS'],SCOPED)
        self.assertIn(extra,changes['NFQWS_EXTRA_ARGS'])
        self.assertIn('--hostlist-domains=riotgames.com',changes['NFQWS_EXTRA_ARGS'])
        for literal in ['ASUS_CLIENTS4="192.0.2.8"','ISP_INTERFACE="eth9"','TCP_PORTS="80,443"']:
            self.assertIn(literal,result['config'])
        self.assertIn('exclusion',result['addons'][0]['note'].lower())

    def test_all_and_empty_comment_only_include_are_never_narrowed(self):
        for extra,lists in [('',{}),('--hostlist-exclude-domains=exclude.example.org',{}),('--hostlist-domains=;skip,/skip,#skip',{}),('--hostlist=/opt/etc/nfqws2/lists/empty.list',{'empty.list':'# comment only\n\n'})]:
            result=self.plan(blocks={'NFQWS_ARGS':'--filter-tcp=443 --lua-desync=multisplit:pos=1'},extra=extra,lists=lists)
            self.assertTrue(result.get('ready'),result)
            self.assertEqual(result['addons'][0]['action'],'already_covered')
            self.assertNotIn('riotgames.com',result['config'])

    def test_auto_scopes_preserve_auto_and_exclusion_file_and_pin_list_hash(self):
        extra='--hostlist-auto=/opt/etc/nfqws2/lists/auto.list --hostlist-exclude=/opt/etc/nfqws2/lists/exclude.list'
        result=self.plan(blocks={'NFQWS_ARGS':'--filter-tcp=443 --lua-desync=multisplit:pos=1'},extra=extra,lists={'auto.list':'','exclude.list':'riotcdn.net\n'})
        self.assertTrue(result.get('ready'),result)
        self.assertIn(extra,result['config'])
        self.assertEqual(result['addons'][0]['action'],'scope_extended')
        self.assertEqual(len(result['fingerprints']['files']),2)

    def test_include_exemptions_are_never_bypassed_by_an_added_union(self):
        for extra,lists in [('--hostlist-domains=base.example.org,!account.riotgames.com',{}),('--hostlist-auto=/opt/etc/nfqws2/lists/auto.list',{'auto.list':'base.example.org\n!account.riotgames.com\n'})]:
            result=self.plan(blocks={'NFQWS_ARGS':'--filter-tcp=443'},extra=extra,lists=lists)
            self.assertFalse(result.get('ready'),result)
            self.assertIn('addon_scope_incompatible',[p['code'] for p in result['problems']])
            self.assertNotIn('--hostlist-domains=riotgames.com',result['config'])

    def test_domains_already_present_in_plain_file_do_not_add_redundant_option(self):
        result=self.plan(blocks={'NFQWS_ARGS':'--filter-tcp=443'},extra='--hostlist=/opt/etc/nfqws2/lists/base.list',lists={'base.list':'# public\nriotgames.com\nriotcdn.net\n'})
        self.assertTrue(result.get('ready'),result)
        self.assertEqual(result['addons'][0]['action'],'already_covered')
        self.assertNotIn('--hostlist-domains=',result['config'])

    def test_multiple_addons_deduplicate_and_repeat_preview_does_not_stack_options(self):
        _,first,a=source();_,second,b=source(addon('second',['riotcdn.net','leagueoflegends.com']))
        options=[{'id':e['id'],'sha256':e['sha256']} for e in [first,second]]
        result=self.plan(options=options,resolved=[a,b])
        self.assertTrue(result.get('ready'),result)
        self.assertEqual(result['config'].count('riotcdn.net'),1)
        self.assertIn('--hostlist-domains=riotgames.com,riotcdn.net,leagueoflegends.com',result['config'])
        # A base carrying the composed scope is not expanded a second time.
        extra={r['key']:r['after'] for r in result['changes']}['NFQWS_EXTRA_ARGS']
        repeated=self.plan(options=options,resolved=[a,b],extra=extra,current=result['config'])
        self.assertTrue(repeated.get('ready'),repeated)
        self.assertEqual(repeated['config'],result['config'])
        self.assertTrue(all(r['action']=='already_covered' for r in repeated['addons']))

    def test_mixed_unselected_all_path_never_narrows_and_scoped_local_block_extends_only_itself(self):
        current=CURRENT+'NFQWS_ARGS_QUIC="--filter-udp=443 --lua-desync=multisplit:pos=1"\n'
        result=self.plan(current=current)
        self.assertTrue(result.get('ready'),result)
        changes={r['key']:r['after'] for r in result['changes']}
        self.assertEqual(changes['NFQWS_EXTRA_ARGS'],'')
        self.assertIn('--hostlist-domains=riotgames.com,riotcdn.net',changes['NFQWS_ARGS'])
        self.assertNotIn('NFQWS_ARGS_QUIC',changes)
        self.assertEqual(result['affected_blocks'],[])

    def test_literal_quotes_or_backslashes_in_existing_host_scope_are_not_shell_evaluated(self):
        for extra in ["--hostlist-domains='riotgames.com,riotcdn.net'",r'--hostlist-domains=riotgames.com\,riotcdn.net']:
            current=CURRENT.replace('NFQWS_EXTRA_ARGS=""','NFQWS_EXTRA_ARGS="'+extra.replace('\\','\\\\')+'"')
            result=self.plan(current=current,omit_shared=True)
            self.assertFalse(result.get('ready'),result)
            self.assertIn('addon_scope_incompatible',[p['code'] for p in result['problems']])

    def test_covered_existing_extra_with_omitted_shared_selection_has_no_warning_or_false_impact(self):
        current=CURRENT.replace('NFQWS_EXTRA_ARGS=""','NFQWS_EXTRA_ARGS="--hostlist-domains=riotgames.com,riotcdn.net"')+'NFQWS_ARGS_QUIC="--filter-udp=443 --hostlist-domains=quic.example.org"\n'
        result=self.plan(current=current,omit_shared=True)
        self.assertTrue(result.get('ready'),result)
        self.assertEqual(result['addons'][0]['action'],'already_covered')
        self.assertEqual(result['affected_blocks'],[])
        self.assertNotIn('NFQWS_EXTRA_ARGS',{r['key'] for r in result['changes']})

    def test_already_covered_selected_base_does_not_extend_only_an_unselected_block(self):
        current=CURRENT+'NFQWS_ARGS_QUIC="--filter-udp=443 --hostlist-domains=other.example.org"\n'
        result=self.plan(blocks={'NFQWS_ARGS':'--filter-tcp=443 --hostlist-domains=riotgames.com,riotcdn.net'},current=current)
        self.assertTrue(result.get('ready'),result)
        self.assertEqual(result['addons'][0]['action'],'already_covered')
        self.assertEqual({r['key']:r['after'] for r in result['changes']}['NFQWS_EXTRA_ARGS'],'')
        self.assertEqual(result['affected_blocks'],[])

    def test_shared_extension_exposes_unselected_scoped_block_and_requires_consent(self):
        current=CURRENT+'NFQWS_ARGS_QUIC="--filter-udp=443 --hostlist-domains=quic.example.org"\n'
        result=self.plan(current=current,allow=False)
        self.assertFalse(result.get('ready'),result)
        self.assertIn('NFQWS_ARGS_QUIC',result['affected_blocks'])
        self.assertIn('shared_impact',[p['code'] for p in result['problems']])
        self.assertTrue(self.plan(current=current,allow=True).get('ready'))

    def test_custom_segments_extend_only_the_scoped_segment_at_actual_init_placement(self):
        custom='--filter-tcp=443 --hostlist-domains=custom.example.org --lua-desync=multisplit:pos=1 --new --filter-tcp=80 --lua-desync=multisplit:pos=2'
        result=self.plan(blocks={'NFQWS_ARGS_CUSTOM':custom})
        self.assertTrue(result.get('ready'),result)
        changed={r['key']:r['after'] for r in result['changes']}['NFQWS_ARGS_CUSTOM']
        self.assertIn('--hostlist-domains=riotgames.com,riotcdn.net --new',changed)
        self.assertTrue(changed.endswith('--filter-tcp=80 --lua-desync=multisplit:pos=2'))

    def test_empty_main_profile_is_an_active_unrestricted_extra_consumer(self):
        current=CURRENT.replace('NFQWS_ARGS="--filter-tcp=80"','NFQWS_ARGS=""')
        result=self.plan(blocks={'NFQWS_ARGS_QUIC':'--filter-udp=443 --hostlist-domains=quic.example.org'},current=current)
        self.assertTrue(result.get('ready'),result)
        changes={r['key']:r['after'] for r in result['changes']}
        self.assertEqual(changes['NFQWS_EXTRA_ARGS'],'')
        self.assertIn('--hostlist-domains=riotgames.com,riotcdn.net',changes['NFQWS_ARGS_QUIC'])

    def test_ipset_parallel_profile_is_never_narrowed_by_a_local_extension(self):
        # The imported main is scoped only through EXTRA; the IPSET clone is not.
        current=CURRENT+'NFQWS_ARGS_QUIC="--filter-udp=443"\nNFQWS_ARGS_IPSET="--ipset-ip=192.0.2.0/24"\n'
        result=self.plan(blocks={'NFQWS_ARGS':'--filter-tcp=443 --lua-desync=multisplit:pos=1'},extra='--hostlist-domains=base.example.org',current=current)
        # Both EXTRA consumers are scoped, so shared extension is safe and does
        # not touch the parallel IPSET clone or require any algorithm rewrite.
        self.assertFalse(result.get('ready'),result)
        self.assertIn('shared_impact',[p['code'] for p in result['problems']])
        current=current.replace('--filter-udp=443','--filter-udp=443 --hostlist=/opt/etc/nfqws2/lists/compressed.list')
        result=self.plan(blocks={'NFQWS_ARGS':'--filter-tcp=443 --lua-desync=multisplit:pos=1'},extra='--hostlist-domains=base.example.org',current=current,lists={'compressed.list':'\x1f\x8bcompressed'},allow=True)
        self.assertFalse(result.get('ready'),result)
        changes={r['key']:r['after'] for r in result['changes']}
        self.assertEqual(changes['NFQWS_ARGS'],'--filter-tcp=443 --lua-desync=multisplit:pos=1')
        self.assertIn('addon_scope_incompatible',[p['code'] for p in result['problems']])

    def test_generic_scope_does_not_extend_the_specialized_torrent_rule(self):
        import test_import_torrent_sites as torrent
        raw,selected,inventory,scope,option=torrent.fixture()
        selected['torrent_sites']=option;_,entry,src=source()
        selected['addons']=[{'id':entry['id'],'sha256':entry['sha256']}]
        code="""require $argv[1].'/import-plan.php';$v=json_decode(stream_get_contents(STDIN),true);try{echo json_encode(AsusImportPlan::prepare(AsusImportDocument::read([$v['raw']]),$v['selection'],$v['current'],$v['inventory'],null,null,$v['scope'],[$v['addon']]),JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
        result=self.php(code,{'raw':raw,'selection':selected,'current':torrent.CURRENT,'inventory':inventory,'scope':scope,'addon':src})
        self.assertTrue(result.get('ready'),result)
        self.assertEqual({r['key']:r['after'] for r in result['changes']}['NFQWS_ARGS_CUSTOM'],torrent.RULE+' --new '+torrent.CUSTOM)
        self.assertEqual(result['addons'][0]['action'],'already_covered')

    def test_exported_managed_torrent_segment_stays_specialized_during_generic_import(self):
        import test_import_torrent_sites as torrent
        raw,selected,inventory,scope,_=torrent.fixture();strategy=json.loads(raw)
        custom=torrent.RULE+' --new '+torrent.CUSTOM
        strategy['blocks'].append({'key':'NFQWS_ARGS_CUSTOM','value':custom});selected['blocks']=strategy['blocks']
        _,entry,src=source();selected['addons']=[{'id':entry['id'],'sha256':entry['sha256']}]
        code="""require $argv[1].'/import-plan.php';$v=json_decode(stream_get_contents(STDIN),true);try{echo json_encode(AsusImportPlan::prepare(AsusImportDocument::read([$v['raw']]),$v['selection'],$v['current'],$v['inventory'],null,null,$v['scope'],[$v['addon']]),JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
        result=self.php(code,{'raw':json.dumps(strategy),'selection':selected,'current':torrent.CURRENT,'inventory':inventory,'scope':scope,'addon':src})
        self.assertTrue(result.get('ready'),result)
        custom_after={r['key']:r['after'] for r in result['changes']}['NFQWS_ARGS_CUSTOM']
        specialized,manual=custom_after.split(' --new ')
        self.assertEqual(specialized,torrent.RULE)
        self.assertIn('--hostlist-domains=riotgames.com,riotcdn.net',manual)

    def test_managed_marker_outside_custom_never_becomes_a_shared_generic_target(self):
        marker='--comment=nfqws2-community-torrent-sites-v1'
        for blocks,extra in [({'NFQWS_ARGS':marker+' '+SCOPED},''),({'NFQWS_ARGS':SCOPED},marker)]:
            result=self.plan(blocks=blocks,extra=extra)
            self.assertFalse(result.get('ready'),result)
            self.assertIn('addon_scope_incompatible',[p['code'] for p in result['problems']])
        current=CURRENT.replace('NFQWS_ARGS="--filter-tcp=80"','NFQWS_ARGS="'+marker+' '+SCOPED+'"')
        result=self.plan(blocks={'NFQWS_ARGS_QUIC':'--filter-udp=443 --hostlist-domains=quic.example.org'},current=current)
        self.assertTrue(result.get('ready'),result)
        changes={r['key']:r['after'] for r in result['changes']}
        self.assertEqual(changes['NFQWS_EXTRA_ARGS'],'')
        self.assertIn('--hostlist-domains=riotgames.com,riotcdn.net',changes['NFQWS_ARGS_QUIC'])

    def test_abbreviated_single_dash_and_hidden_structural_options_cannot_narrow_a_profile(self):
        for alias in ['--ne','-new','--templ=hidden','--impo=hidden','-skip','--hostlist-domain=riotgames.com','-hostlist-domains=riotgames.com']:
            value=SCOPED+' '+alias+' --filter-tcp=80'
            result=self.plan(blocks={'NFQWS_ARGS_CUSTOM':value})
            self.assertFalse(result.get('ready'),result)
            self.assertIn('addon_scope_incompatible',[p['code'] for p in result['problems']])
            self.assertNotIn('addons',result)

    def test_forged_duplicate_oversize_or_unresolved_selection_cannot_supply_addon_data(self):
        _,entry,_=source();pick={'id':entry['id'],'sha256':entry['sha256']}
        for options in [None,False,[pick]*2,[dict(pick,url='https://evil.invalid')],[dict(pick,id='../escape')],[pick]*9]:
            if options is None: continue
            result=self.plan(options=options)
            self.assertEqual(result.get('error'),'invalid_import_selection',result)
        self.assertEqual(self.plan(resolved=[])['error'],'invalid_addon_source')

    def test_hostlist_bare_cr_and_overlong_chunked_lines_cannot_forge_a_positive_scope(self):
        for raw in ['\rnot-an-active-entry','#'+'x'*4095+'\n']:
            result=self.plan(blocks={'NFQWS_ARGS':'--filter-tcp=443'},extra='--hostlist=/opt/etc/nfqws2/lists/base.list',lists={'base.list':raw})
            self.assertFalse(result.get('ready'),result)
            self.assertIn('addon_scope_incompatible',[p['code'] for p in result['problems']])
            self.assertNotIn('addons',result)

    def test_unknown_compressed_and_hidden_program_scope_has_concrete_unsupported_preview(self):
        cases=[({'NFQWS_ARGS':SCOPED+' --template=hidden'},'',{}),({'NFQWS_ARGS':SCOPED+' --import=hidden'},'',{}),({'NFQWS_ARGS':SCOPED+' --skip'},'',{}),({'NFQWS_ARGS':'--filter-tcp=443'},'--hostlist=/opt/etc/nfqws2/lists/compressed.list',{'compressed.list':'\x1f\x8bdata'})]
        for blocks,extra,lists in cases:
            result=self.plan(blocks=blocks,extra=extra,lists=lists)
            self.assertFalse(result.get('ready'),result)
            self.assertIn('addon_scope_incompatible',[p['code'] for p in result['problems']])
            self.assertNotIn('addons',result)

    def test_excluded_domains_are_visible_and_never_claimed_as_already_covered(self):
        for block in [SCOPED,'--filter-tcp=443']:
            result=self.plan(blocks={'NFQWS_ARGS':block},extra='--hostlist-exclude-domains=riotgames.com,riotcdn.net')
            self.assertFalse(result.get('ready'),result)
            self.assertIn('addon_scope_incompatible',[p['code'] for p in result['problems']])
            self.assertNotIn('addons',result)
        result=self.plan(extra='--hostlist-exclude=/opt/etc/nfqws2/lists/exclude.list',lists={'exclude.list':'riotcdn.net\n'})
        self.assertTrue(result.get('ready'),result)
        self.assertEqual(result['addons'][0]['domains'],['riotgames.com'])
        self.assertIn('riotcdn.net',result['addons'][0]['note'])

    def test_many_long_exclusions_fit_the_preview_note_contract_without_changing_config(self):
        domains=['d'+str(i)+'.'+('a'*58+'.')*4+'com' for i in range(20)]
        _,entry,src=source(addon(domains=domains));extra='--hostlist-exclude-domains='+','.join(domains[:-1])
        result=self.plan(extra=extra,options=[{'id':entry['id'],'sha256':entry['sha256']}],resolved=[src])
        self.assertTrue(result.get('ready'),result)
        self.assertEqual(result['addons'][0]['domains'],[domains[-1]])
        self.assertLessEqual(len(result['addons'][0]['note']),4096)
        self.assertIn(extra,result['config'])

    def test_source_identity_and_catalog_revision_are_part_of_preview_digest(self):
        first=self.plan();_,_,changed=source(revision=2)
        second=self.plan(resolved=[changed])
        self.assertTrue(first.get('ready'),first);self.assertTrue(second.get('ready'),second)
        self.assertNotEqual(first['digest'],second['digest'])

    def api(self, ops, update=None):
        raw,entry,_=source();manifest=self.manifest(entry);strategy=copy.deepcopy(STRATEGY)
        strategy['blocks']=[{'key':'NFQWS_ARGS','value':SCOPED}];strategy['shared']={}
        selected=selection(blocks=strategy['blocks'],shared=[],files=[],trusted_lua=False,allow_incomplete=False)
        selected['addons']=[{'id':entry['id'],'sha256':entry['sha256']}]
        value={'document':json.dumps(strategy),'selection':selected,'key':catalog_fixtures.ProfileCatalogTests.public,'catalog':self.signer.signed(manifest),'raw':raw,'sha':entry['sha256'],'ops':ops}
        if update:value.update(update)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'resources').mkdir(mode=0o755);(root/'resources/nfqws2.conf').write_text(CURRENT)
            code="""require $argv[1].'/import-api.php';$v=json_decode(stream_get_contents(STDIN),true);$r=$argv[2];$u=(int)$argv[3];if(!class_exists('AsusImportAddonCatalogTransport')){echo '{"error":"missing_feature"}';exit;}$calls=[];$read=function($url,$cap,$deadline)use(&$v,&$calls){$calls[]=$url;if(str_ends_with($url,'/catalog.json'))return $v['catalog'];if(str_ends_with($url,'/files/'.$v['sha'].'.json'))return $v['raw'];throw new RuntimeException('catalog_unavailable');};$t=new AsusImportAddonCatalogTransport($v['key'],$read,$r.'/cache',$u,fn()=>1000,92);$tx=new AsusImportTransaction(new AsusImportStore($r.'/journal',$u),new AsusSmartDnsStore($r.'/dns',$u),$r.'/resources',$r.'/resources/nfqws2.conf',$u);$api=new AsusImportApi($tx,fn()=>null,new AsusSmartDnsStore($r.'/dns',$u),null,$t);$proof=null;$undo=null;$out=[];foreach($v['ops']as $op){try{if($op==='change_bytes'){$v['raw']=str_replace('riotgames.com','riotgames.net',$v['raw']);continue;}if($op==='edit_config'){file_put_contents($r.'/resources/nfqws2.conf',file_get_contents($r.'/resources/nfqws2.conf').'# operator edit'.PHP_EOL);continue;}if($op==='expire_catalog'){touch($r.'/cache/catalog.json',0);$v['catalog']=$v['next'];continue;}$sel=$v['selection'];if($op==='apply_off')unset($sel['addons']);$post=['cmd'=>$op==='catalog'?'importaddoncatalog':($op==='prepare'?'importprepare':($op==='status'?'importstatus':($op==='undo'?'importundo':'importapply'))),'csrf_token'=>'fixture'];if(in_array($op,['prepare','apply','apply_off'],true))$post+=['documents'=>json_encode([$v['document']]),'selection'=>$v['selection_raw']??json_encode($sel)];if(in_array($op,['apply','apply_off'],true))$post+=['proof'=>$proof,'request_id'=>str_repeat('a',32)];if($op==='undo')$post+=['proof'=>$undo,'id'=>str_repeat('a',32)];$value=$api->handle($post,str_repeat('f',64),1000);if($op==='prepare')$proof=$value['proof'];if($op==='status')$undo=$value['undo_proof'];$out[]=$value;}catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}}echo json_encode(['results'=>$out,'config'=>file_get_contents($r.'/resources/nfqws2.conf'),'calls'=>$calls],JSON_THROW_ON_ERROR);"""
            return self.php(code,value,[root,os.getuid()])

    def transport(self, responses, body):
        code="""require $argv[1].'/import-addon-catalog-transport.php';$v=json_decode(stream_get_contents(STDIN),true);$calls=[];$deadlines=[];$starts=[];$read=function($url,$cap,$deadline)use(&$v,&$calls,&$deadlines,&$starts){$calls[]=$url;$deadlines[]=$deadline;$starts[]=microtime(true);if(!isset($v['responses'][$url]))throw new RuntimeException('catalog_unavailable');$response=$v['responses'][$url];if(is_array($response)){if(isset($response['delay_us']))usleep($response['delay_us']);throw new RuntimeException($response['error']);}return $response;};$t=new AsusImportAddonCatalogTransport($v['key'],$read,$argv[2],(int)$argv[3],fn()=>1000,92);try{"""+body+"""}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage(),'calls'=>$calls,'deadlines'=>$deadlines,'starts'=>$starts]);}"""
        with tempfile.TemporaryDirectory() as folder:
            return self.php(code,{'key':catalog_fixtures.ProfileCatalogTests.public,'responses':responses},[folder+'/cache',os.getuid()])

    def test_one_total_deadline_covers_primary_probes_and_all_fallback_documents(self):
        first,a,_=source();second,b,_=source(addon('second',['leagueoflegends.com']))
        manifest=self.manifest(a);manifest['addons'].append(b)
        responses={BACKUP+'catalog.json':self.signer.signed(manifest),BACKUP+'files/'+a['sha256']+'.json':first,BACKUP+'files/'+b['sha256']+'.json':second}
        picks=[{'id':e['id'],'sha256':e['sha256']} for e in [a,b]]
        result=self.transport(responses,"$t->resolve(json_decode('"+json.dumps(picks)+"',true));echo json_encode(['calls'=>$calls,'deadlines'=>$deadlines,'starts'=>$starts]);")
        expected=[ORIGIN+'catalog.json',BACKUP+'catalog.json',ORIGIN+'files/'+a['sha256']+'.json',BACKUP+'files/'+a['sha256']+'.json',ORIGIN+'files/'+b['sha256']+'.json',BACKUP+'files/'+b['sha256']+'.json']
        self.assertEqual(result.get('calls'),expected,result)
        self.assertEqual(len(set(result['deadlines'][1::2])),1)
        overall=result['deadlines'][1]
        self.assertLessEqual(overall-result['starts'][0],20)
        for start,deadline in zip(result['starts'][::2],result['deadlines'][::2]):
            self.assertLessEqual(deadline-start,5)
            self.assertLess(deadline,overall)

    def test_catalog_and_immutable_document_fallback_preserve_exact_fixed_paths(self):
        raw,entry,_=source();signed=self.signer.signed(self.manifest(entry));path='files/'+entry['sha256']+'.json'
        for code in ['catalog_http','catalog_dns','catalog_tls','catalog_connect','catalog_timeout','catalog_unavailable','catalog_runtime']:
            responses={ORIGIN+'catalog.json':{'error':code},BACKUP+'catalog.json':signed,ORIGIN+path:{'error':code},BACKUP+path:raw}
            result=self.transport(responses,"$raw=$t->document('riot-web','"+entry['sha256']+"');echo json_encode(['raw'=>$raw,'calls'=>$calls]);")
            self.assertEqual(result.get('raw'),raw,result)
            self.assertEqual(result['calls'],[ORIGIN+'catalog.json',BACKUP+'catalog.json',ORIGIN+path,BACKUP+path])

    def test_successful_primary_never_queries_the_backup(self):
        raw,entry,_=source();path='files/'+entry['sha256']+'.json'
        responses={ORIGIN+'catalog.json':self.signer.signed(self.manifest(entry)),ORIGIN+path:raw,BACKUP+'catalog.json':'should never read',BACKUP+path:'should never read'}
        result=self.transport(responses,"$raw=$t->document('riot-web','"+entry['sha256']+"');echo json_encode(['raw'=>$raw,'calls'=>$calls]);")
        self.assertEqual(result.get('raw'),raw,result)
        self.assertEqual(result['calls'],[ORIGIN+'catalog.json',ORIGIN+path])

    def test_malformed_signature_schema_hash_and_limits_never_mask_primary_with_backup(self):
        raw,entry,_=source();manifest=self.manifest(entry);signed=self.signer.signed(manifest);path='files/'+entry['sha256']+'.json'
        tampered=json.loads(signed);tampered['signature']='A'*512
        wrong=copy.deepcopy(manifest);wrong['addons'][0]['arbitrary']='hidden'
        for primary,want in [(json.dumps(tampered),'catalog_signature'),('bad json','catalog_invalid'),(self.signer.signed(wrong),'catalog_invalid'),('x'*131073,'catalog_limit'),({'error':'catalog_invalid'},'catalog_invalid'),({'error':'catalog_limit'},'catalog_limit')]:
            result=self.transport({ORIGIN+'catalog.json':primary,BACKUP+'catalog.json':signed},"$t->catalog();")
            self.assertEqual(result.get('error'),want,result)
            self.assertEqual(result['calls'],[ORIGIN+'catalog.json'])
        for primary in [raw.replace('riotgames.com','riotgames.net'),'x'*(len(raw)+1)]:
            result=self.transport({ORIGIN+'catalog.json':signed,ORIGIN+path:primary,BACKUP+path:raw},"$t->document('riot-web','"+entry['sha256']+"');")
            self.assertIn(result.get('error'),['catalog_invalid','catalog_limit'],result)
            self.assertEqual(result['calls'],[ORIGIN+'catalog.json',ORIGIN+path])
        invalid='{}';badentry=copy.deepcopy(entry);badentry.update(sha256=hashlib.sha256(invalid.encode()).hexdigest(),size=len(invalid));badpath='files/'+badentry['sha256']+'.json'
        result=self.transport({ORIGIN+'catalog.json':self.signer.signed(self.manifest(badentry)),ORIGIN+badpath:invalid,BACKUP+badpath:invalid},"$t->document('riot-web','"+badentry['sha256']+"');")
        self.assertEqual(result.get('error'),'catalog_invalid',result)
        self.assertEqual(result['calls'],[ORIGIN+'catalog.json',ORIGIN+badpath])

    def test_expired_overall_budget_never_starts_fallback(self):
        result=self.transport({ORIGIN+'catalog.json':{'error':'catalog_timeout','delay_us':30000},BACKUP+'catalog.json':self.signer.signed(self.manifest())},"$method=new ReflectionMethod($t,'fetch');$method->invoke($t,'catalog.json',131072,microtime(true)+0.01);")
        self.assertEqual(result.get('error'),'catalog_timeout',result)
        self.assertEqual(result['calls'],[ORIGIN+'catalog.json'])

    def test_expired_cache_cannot_rollback_through_the_backup(self):
        old=self.manifest(revision=1);new=self.manifest(revision=2)
        responses={ORIGIN+'catalog.json':self.signer.signed(new),BACKUP+'catalog.json':self.signer.signed(old)}
        body="$t->catalog();touch($argv[2].'/catalog.json',0);$v['responses']['"+ORIGIN+"catalog.json']=['error'=>'catalog_http'];$t->catalog();"
        result=self.transport(responses,body)
        self.assertEqual(result.get('error'),'catalog_changed',result)
        self.assertEqual(result['calls'],[ORIGIN+'catalog.json',ORIGIN+'catalog.json',BACKUP+'catalog.json'])

    def test_addon_transport_rejects_minimum_build_and_cache_links(self):
        raw,entry,_=source();manifest=self.manifest(entry)
        responses={ORIGIN+'catalog.json':self.signer.signed(manifest)}
        result=self.transport(responses,"$t->catalog();unlink($argv[2].'/catalog.json');symlink(__FILE__,$argv[2].'/catalog.json');$t->catalog();")
        self.assertEqual(result.get('error'),'catalog_unavailable',result)
        manifest['addons'][0]['min_build']=93;responses[ORIGIN+'catalog.json']=self.signer.signed(manifest)
        result=self.transport(responses,"$t->document('riot-web','"+entry['sha256']+"');")
        self.assertEqual(result.get('error'),'catalog_version',result)
        self.assertEqual(result['calls'],[ORIGIN+'catalog.json'])

    def test_json_empty_object_cannot_silently_disable_the_addon_array(self):
        selected=selection(blocks=[{'key':'NFQWS_ARGS','value':SCOPED}],shared=[],files=[],trusted_lua=False,allow_incomplete=False)
        selected['addons']={}
        result=self.api(['prepare'],{'selection_raw':json.dumps(selected)})
        self.assertEqual(result['results'],[{'error':'invalid_import_selection'}],result)
        self.assertEqual(result['calls'],[])
        self.assertEqual(result['config'],CURRENT)

    def test_csrf_only_catalog_fetches_only_the_fixed_origin_then_immutable_selected_file(self):
        value=self.api(['catalog','prepare'])
        self.assertEqual(value['results'][0],self.manifest()|{'build':92})
        self.assertTrue(value['results'][1].get('ready'),value)
        self.assertEqual(value['calls'],[ORIGIN+'catalog.json',ORIGIN+'files/'+source()[1]['sha256']+'.json'])
        self.assertEqual(value['config'],CURRENT)

    def test_real_apply_and_undo_restore_exact_original_without_service_side_effects(self):
        value=self.api(['prepare','apply','status','undo'])
        self.assertTrue(value['results'][0].get('ready'),value)
        self.assertEqual(value['results'][1].get('state'),'committed',value)
        self.assertEqual(value['results'][-1].get('state'),'undone',value)
        self.assertEqual(value['config'],CURRENT)

    def test_changed_checkbox_bytes_catalog_or_config_cannot_reuse_preview_proof(self):
        changed=self.manifest(revision=2)
        changed['addons'][0]['attribution']='Updated attribution'
        for ops,want,update in [(['prepare','apply_off'],'invalid_proof',None),(['prepare','change_bytes','apply'],'catalog_invalid',None),(['prepare','expire_catalog','apply'],'stale_preview',{'next':self.signer.signed(changed)}),(['prepare','edit_config','apply'],'stale_preview',None)]:
            value=self.api(ops,update)
            self.assertEqual(value['results'][-1],{'error':want},value)
            self.assertNotIn('riotgames.com',value['config'])


if __name__=='__main__':
    unittest.main()
