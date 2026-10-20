"""Selected DNS/domain copies must describe their source and never change DNS."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC

LEGACY='''bind 127.0.0.1:6053
server-tls 8.8.8.8 -host-name dns.google -tls-host-verify dns.google
server-tls 9.9.9.9 -host-name dns.quad9.net -tls-host-verify dns.quad9.net -group posters -exclude-default-group
server-https https://dns.quad9.net/dns-query -host-ip 149.112.112.112 -host-name dns.quad9.net -tls-host-verify dns.quad9.net -group api -exclude-default-group
nameserver /image.tmdb.org/posters
nameserver /-.api.themoviedb.org/api
address /-.image.tmdb.org/203.0.113.8
'''
class ShareDnsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'smartdns.conf';self.path.write_text(LEGACY)
    def tearDown(self):self.temp.cleanup()
    def call(self,action='sources',selection=None,managed=None):
        data={'selection':selection,'managed':managed}
        code='''$path=$argv[1].'/share-dns.php';if(!is_file($path)){echo json_encode(['error'=>'missing_feature']);exit;}
        require $path;$v=json_decode(stream_get_contents(STDIN),true);try{$dns=new AsusShareDns($argv[2],(int)$argv[3],['managed'=>fn()=>$v['managed']??[]]);echo json_encode($argv[4]==='sources'?$dns->sources():$dns->prepare($v['selection']),JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        before=self.path.read_bytes();p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.path),str(os.getuid()),action],input=json.dumps(data),capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');self.assertEqual(before,self.path.read_bytes());return json.loads(p.stdout)
    def legacy(self):
        v=self.call();self.assertNotIn('error',v);return next(x for x in v['sources'] if x['id']=='legacy')
    def test_legacy_preserves_default_dot_doh_site_scope_and_static_override(self):
        s=self.legacy();self.assertTrue(s['complete']);self.assertEqual(s['origin'],'legacy')
        self.assertEqual(len(s['profile']['upstreams']),3)
        posters=next(x for x in s['profile']['upstreams'] if x['address']=='9.9.9.9');self.assertFalse(posters['default']);self.assertEqual(posters['domains'],[{'name':'image.tmdb.org','include_subdomains':True}])
        api=next(x for x in s['profile']['upstreams'] if x['protocol']=='doh');self.assertEqual(api['bootstrap'],['149.112.112.112']);self.assertEqual(api['domains'],[{'name':'api.themoviedb.org','include_subdomains':False}])
        self.assertEqual(s['profile']['records'][0]['addresses'],['203.0.113.8']);self.assertNotIn(str(self.path),json.dumps(s))
    def test_selected_nondefault_dns_card_can_be_shared_without_other_cards(self):
        s=self.legacy();card=next(x for x in s['profile']['upstreams'] if x['address']=='9.9.9.9');card['domains'][0]['name']='edited.example'
        v=self.call('prepare',[{'source_id':s['id'],'source_sha256':s['sha256'],'upstreams':[card],'records':[]}]);self.assertNotIn('error',v)
        self.assertEqual(len(v['sources'][0]['profile']['upstreams']),1);self.assertFalse(v['sources'][0]['profile']['upstreams'][0]['default']);self.assertEqual(v['sources'][0]['profile']['upstreams'][0]['domains'][0]['name'],'edited.example')
        self.assertNotIn('dns.google',json.dumps(v));self.assertNotIn('203.0.113.8',json.dumps(v))
    def test_selected_static_record_can_be_shared_alone(self):
        s=self.legacy();v=self.call('prepare',[{'source_id':'legacy','source_sha256':s['sha256'],'upstreams':[],'records':[{'index':0,'value':s['profile']['records'][0]}]}]);self.assertNotIn('error',v)
        self.assertEqual(v['sources'][0]['profile']['upstreams'],[]);self.assertEqual(len(v['sources'][0]['profile']['records']),1)
    def test_draft_and_active_are_distinct_read_only_sources(self):
        profile=self.legacy()['profile'];v=self.call(managed={'draft':profile,'active':profile})
        self.assertNotIn('error',v);self.assertEqual({s['id'] for s in v['sources']},{'draft','active','legacy'})
    def test_changed_source_is_rejected_after_selection(self):
        s=self.legacy();self.path.write_text(LEGACY+'# changed\n')
        v=self.call('prepare',[{'source_id':'legacy','source_sha256':s['sha256'],'upstreams':[s['profile']['upstreams'][0]],'records':[]}]);self.assertEqual(v['error'],'source_changed')
    def test_unsupported_include_is_not_misreported_as_complete(self):
        self.path.write_text(LEGACY+'conf-file /etc/PRIVATE_CANARY\n')
        s=self.legacy();self.assertFalse(s['complete']);self.assertTrue(s['warnings']);self.assertNotIn('PRIVATE_CANARY',json.dumps(s))
    def test_credential_or_token_url_is_not_silently_returned(self):
        for url in ['https://user:PRIVATE_CANARY@dns.example/dns-query','https://dns.example/dns-query?token=PRIVATE_CANARY']:
            self.path.write_text(LEGACY+'server-https '+url+' -host-ip 1.1.1.1 -host-name dns.example -tls-host-verify dns.example\n')
            s=self.legacy();self.assertFalse(s['complete']);self.assertNotIn('PRIVATE_CANARY',json.dumps(s))

    def test_explicit_dot_port_is_preserved(self):
        self.path.write_text(LEGACY.replace('server-tls 8.8.8.8 ', 'server-tls 8.8.8.8:8853 '))
        s=self.legacy();self.assertTrue(s['complete']);self.assertEqual(next(x for x in s['profile']['upstreams'] if x['address']=='8.8.8.8')['port'],8853)
    def test_subset_does_not_bypass_boolean_default_validation(self):
        s=self.legacy();card=s['profile']['upstreams'][0];card['default']='yes'
        v=self.call('prepare',[{'source_id':'legacy','source_sha256':s['sha256'],'upstreams':[card],'records':[]}]);self.assertEqual(v.get('error'),'invalid_dns_resource')

    def test_unsupported_address_policy_keeps_other_cards_but_marks_partial(self):
        self.path.write_text(LEGACY+'address /blocked.example/#\n')
        v=self.call();self.assertEqual(len(v['sources']),1);s=v['sources'][0];self.assertFalse(s['complete']);self.assertEqual(len(s['profile']['upstreams']),3)

    def test_many_unsupported_lines_have_bounded_explicit_warning(self):
        self.path.write_text(LEGACY+'unsupported ignored\n'*150)
        s=self.legacy();self.assertFalse(s['complete']);self.assertLessEqual(len(s['warnings']),128);self.assertIn('additional_directives_omitted',{x['code'] for x in s['warnings']})

    def test_default_dns_filename_is_appended_after_resolving_opt_directory(self):
        (self.path.parent/'etc/smartdns').mkdir(parents=True,mode=0o755)
        (self.path.parent/'etc').chmod(0o755);(self.path.parent/'etc/smartdns/smartdns.conf').write_text(LEGACY)
        code="require $argv[1].'/share-dns.php';try{$v=new AsusShareDns(null,(int)$argv[3],['opt_alias'=>$argv[2],'managed'=>fn()=>[]]);echo json_encode($v->sources());}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.path.parent),str(os.getuid())],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);v=json.loads(p.stdout);self.assertNotIn('error',v);self.assertEqual(len(v['sources']),1)
