"""Extended bundles preserve exact selected bytes while legacy v3 stays valid."""
import base64,copy,hashlib,io,json,os,subprocess,tempfile,unittest,uuid
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
from test_share_bundle_api import STRATEGY,share_files
from test_share_relay import encode
from nfqws_support.share import validate_share,share_subject
from nfqws_support.validation import InvalidReport
from nfqws_support.app import create_app
from nfqws_support.smtp import SendOutcome
from nfqws_support.store import RelayStore
from test_support_relay_smtp import config

CTX={'purpose':'Poster','operator':'Example ISP','comment':''}
RES_ID='1'*32
BINARY=b'\0\xff\x80HELLO\0'

def file(kind,data):
    raw=encode(data);return {'type':kind,'filename':f'NFQWS2_{kind.upper()}_2026-10-19_12-00-00Z.json','byte_length':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'data_base64':base64.b64encode(raw).decode()}
def resource(aliases=None):
    return {'id':RES_ID,'kind':'blobs','name':'hello.bin','encoding':'base64','source_sha256':hashlib.sha256(BINARY).hexdigest(),'byte_length':len(BINARY),'sha256':hashlib.sha256(BINARY).hexdigest(),'data_base64':base64.b64encode(BINARY).decode(),'aliases':aliases or []}
def resources(with_strategy=True):
    aliases=['RESOURCE_1'] if with_strategy else []
    return {'type':'nfqws2_resources','schema_version':1,'context':CTX,'files':[resource(aliases)],'audit':{'scope':'static_explicit_references' if with_strategy else 'files_only','references':[{'id':'dependency_1','aliases':aliases,'resource_id':RES_ID,'state':'included'}] if with_strategy else [],'unresolved':[],'missing_reason':'','complete':True}}
def dns():
    row={'id':'quad9','label':'Quad9','protocol':'dot','address':'9.9.9.9','port':853,'tls_name':'dns.quad9.net','url':'','bootstrap':[],'default':False,'domains':[{'name':'image.tmdb.org','include_subdomains':True}]}
    return {'type':'nfqws2_dns','schema_version':1,'context':CTX,'sources':[{'id':'legacy','origin':'legacy','sha256':'a'*64,'profile':{'schema_version':1,'upstreams':[row],'records':[]},'complete':True,'warnings':[],'scope':'upstreams_and_domain_rules'}]}
def fixture(kinds=('strategy','resources','dns')):
    strategy=copy.deepcopy(STRATEGY);strategy.update(schema_version=2,dependencies=[{'id':'RESOURCE_1','kind':'file','included':True}]);strategy['blocks'][0]['value']='--hostlist=RESOURCE_1'
    payloads={'strategy':strategy,'resources':resources('strategy' in kinds),'dns':dns()}
    return {'version':4,'submission_id':str(uuid.uuid4()),'files':[file(k,payloads[k]) for k in kinds]}

class ShareV4Tests(unittest.TestCase):
    def test_download_artifact_proof_and_fixed_mail_preserve_exact_original_bytes(self):
        from email import policy
        from email.parser import BytesParser
        from nfqws_support.smtp import SmtpSender
        from test_support_relay_smtp import FakeSmtp
        payload=b'\x00\xffexact downloaded bytes\r\n'
        document={'type':'nfqws2_download','schema_version':1,'filename':'diagnostic-original.zip',
                  'media_type':'application/zip','byte_length':len(payload),
                  'sha256':hashlib.sha256(payload).hexdigest(),'data_base64':base64.b64encode(payload).decode()}
        v={'version':4,'submission_id':str(uuid.uuid4()),'files':[{'type':'artifact','filename':document['filename'],'byte_length':len(payload),'sha256':document['sha256'],'data_base64':document['data_base64']}]}
        out=self.php(v,"$p=AsusShareBundle::prepare($v['files'],$key,1000,null,4);echo json_encode(['prepared'=>$p,'valid'=>AsusShareBundle::verify($p['proof'],$p['files'],$key,1001)]);")
        self.assertNotIn('error',out);self.assertTrue(out['valid'])
        bundle=validate_share(encode(v),v['submission_id']);fake=FakeSmtp();read_fd,write_fd=os.pipe()
        try:SmtpSender(config(),factory=lambda **kw:fake)._send(None,None,bundle,write_fd)
        finally:os.close(read_fd);os.close(write_fd)
        msg=BytesParser(policy=policy.default).parsebytes(fake.wire)
        attachments=list(msg.iter_attachments());self.assertEqual(len(attachments),1)
        self.assertEqual(attachments[0].get_filename(),document['filename'])
        self.assertEqual(attachments[0].get_payload(decode=True),payload)
        self.assertEqual(str(msg['To']),'support@example.invalid')
        bad=copy.deepcopy(v);bad['files'][0]['sha256']='0'*64
        self.assertIn('error',self.php(bad,"echo json_encode(AsusShareBundle::envelope(json_encode($v),$v['submission_id']));"))
        with self.assertRaises(InvalidReport):validate_share(encode(bad),bad['submission_id'])

    def php(self,value,body):
        code="require $argv[1].'/share-bundle.php';$v=json_decode(stream_get_contents(STDIN),true);$key=str_repeat('a',64);try{"+body+"}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        cp=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(value),capture_output=True,text=True,timeout=10)
        self.assertEqual(cp.returncode,0,cp.stdout+cp.stderr);self.assertEqual(cp.stderr,'');return json.loads(cp.stdout)
    def test_download_preparation_api_needs_no_current_strategy_or_installation_id(self):
        payload=b'exact installer text\n'
        value={'version':4,'artifact':{'filename':'nfqws-installer.sh','media_type':'text/plain','data_base64':base64.b64encode(payload).decode()}}
        out=self.php(value,"require $argv[1].'/share-api.php';$api=new AsusShareApi(configPath:'/not-existing-download-control/nfqws2.conf',versions:['core'=>'1.0.0','web'=>'1.0.0']);$post=['cmd'=>'shareprepare','csrf_token'=>'fixture','selection'=>json_encode($v)];$p=$api->handle($post,$key,1000);echo json_encode(['prepared'=>$p,'valid'=>AsusShareBundle::verify($p['proof'],$p['files'],$key,1001,$p['source']??null)]);")
        self.assertNotIn('error',out);self.assertTrue(out['valid']);self.assertEqual(len(out['prepared']['files']),1)
        f=out['prepared']['files'][0];self.assertEqual(f['filename'],value['artifact']['filename'])
        self.assertEqual(base64.b64decode(f['data_base64']),payload)
        self.assertNotIn('installation_id',out['prepared']['source'])

    def test_router_v4_review_proof_binds_extended_bytes_and_version(self):
        v=fixture();r=self.php(v,"$p=AsusShareBundle::prepare($v['files'],$key,1000,null,4);echo json_encode(['prepared'=>$p,'valid'=>AsusShareBundle::verify($p['proof'],$p['files'],$key,1001)]);")
        self.assertNotIn('error',r);self.assertTrue(r['valid']);self.assertEqual(r['prepared']['version'],4);self.assertTrue(r['prepared']['proof'].startswith('v4.'))

    def test_optional_message_is_bound_to_files_and_delivered_as_plain_mail_text(self):
        from email import policy
        from email.parser import BytesParser
        from nfqws_support.smtp import SmtpSender
        from test_support_relay_smtp import FakeSmtp
        v=fixture(('dns',))
        bare=validate_share(encode(v),v['submission_id'])
        v['comment']='На телевизоре видны постеры.\nВидео загружается долго.'
        bundle=validate_share(encode(v),v['submission_id'])
        self.assertNotEqual(bundle.sha256,bare.sha256)
        checks=self.php(v,"$p=AsusShareBundle::prepare($v['files'],$key,1000,null,4,$v['comment']);echo json_encode([$p['comment'],AsusShareBundle::verify($p['proof'],$p['files'],$key,1001,null,$v['comment']),AsusShareBundle::verify($p['proof'],$p['files'],$key,1001,null,'other'),AsusShareBundle::verify($p['proof'],$p['files'],$key,1001)]);")
        self.assertEqual(checks,[v['comment'],True,False,False])
        fake=FakeSmtp();read_fd,write_fd=os.pipe()
        try:SmtpSender(config(),factory=lambda **kw:fake)._send(None,None,bundle,write_fd)
        finally:os.close(read_fd);os.close(write_fd)
        mail=BytesParser(policy=policy.default).parsebytes(fake.wire)
        self.assertIn(v['comment'],mail.get_body().get_content().replace('\r\n','\n'))
        self.assertEqual(next(mail.iter_attachments()).get_payload(decode=True),bare.files[0].raw)
        for invalid in ('x'*2001, 'control\0'):
            with self.assertRaises(InvalidReport):validate_share(encode(dict(v,comment=invalid)),v['submission_id'])
    def test_router_and_relay_accept_resources_or_dns_without_strategy(self):
        for kinds in [('resources',),('dns',),('resources','dns')]:
            v=fixture(kinds);b=validate_share(encode(v),v['submission_id']);self.assertEqual([f.type for f in b.files],list(kinds))
            r=self.php(v,"echo json_encode(AsusShareBundle::envelope(json_encode($v),$v['submission_id']));");self.assertNotIn('error',r)
            self.assertEqual(share_subject(b.files),'NFQWS2 community [strategies]')
    def test_inner_blob_hash_and_alias_consistency_are_verified(self):
        v=fixture();self.assertEqual(len(validate_share(encode(v),v['submission_id']).files),3)
        for mutation in ['hash','alias','length','path','encoding']:
            bad=copy.deepcopy(v);data=json.loads(base64.b64decode(bad['files'][1]['data_base64']));r=data['files'][0]
            if mutation=='hash':r['sha256']='0'*64
            if mutation=='alias':r['aliases']=['RESOURCE_9']
            if mutation=='length':r['byte_length']=1
            if mutation=='path':r['name']='../../etc/passwd'
            if mutation=='encoding':r['encoding']='utf8'
            bad['files'][1]=file('resources',data)
            with self.assertRaises(InvalidReport):validate_share(encode(bad),bad['submission_id'])
            self.assertIn('error',self.php(bad,"echo json_encode(AsusShareBundle::envelope(json_encode($v),$v['submission_id']));"))
    def test_missing_dependencies_do_not_require_reason_or_force_upload(self):
        v=fixture(('strategy','resources'));s=json.loads(base64.b64decode(v['files'][0]['data_base64']));s['dependencies'][0]['included']=False
        r=resources();r['files']=[];r['audit']['references'][0].update(resource_id=None,state='not_selected');r['audit']['complete']=False;r['audit']['missing_reason']='Не хочу прикладывать этот файл'
        v['files']=[file('strategy',s),file('resources',r)]
        self.assertEqual(len(validate_share(encode(v),v['submission_id']).files),2)
        r['audit']['missing_reason']='';v['files'][1]=file('resources',r)
        self.assertEqual(len(validate_share(encode(v),v['submission_id']).files),2)
        self.assertNotIn('error',self.php(v,"echo json_encode(AsusShareBundle::envelope(json_encode($v),$v['submission_id']));"))
        v['files']=[file('strategy',s)]
        self.assertEqual(len(validate_share(encode(v),v['submission_id']).files),1)
        self.assertNotIn('error',self.php(v,"echo json_encode(AsusShareBundle::envelope(json_encode($v),$v['submission_id']));"))
    def test_sensitive_doh_url_is_rejected_even_with_correct_outer_hash(self):
        v=fixture(('dns',));d=dns();row=d['sources'][0]['profile']['upstreams'][0];row.update(protocol='doh',port=443,url='https://user:SECRET@dns.quad9.net/dns-query');v['files'][0]=file('dns',d)
        with self.assertRaises(InvalidReport):validate_share(encode(v),v['submission_id'])
    def test_legacy_v3_still_uses_unchanged_file_contract(self):
        v={'version':3,'submission_id':str(uuid.uuid4()),'files':share_files()};self.assertEqual(len(validate_share(encode(v),v['submission_id']).files),3)
        r=self.php(v,"$p=AsusShareBundle::prepare($v['files'],$key,1000);echo json_encode([$p['proof'],AsusShareBundle::verify($p['proof'],$p['files'],$key,1000)]);");self.assertTrue(r[0].startswith('v3.'));self.assertTrue(r[1])
    def test_v4_http_path_accepts_once_and_v3_path_rejects_v4(self):
        class Sender:
            def __init__(self):self.count=0
            def send_bundle(self,b):self.count+=1;return SendOutcome('accepted')
        with tempfile.TemporaryDirectory() as d:
            sender=Sender();app=create_app(config(),RelayStore(Path(d)/'db',b'x'*32),sender);v=fixture()
            def req(path):
                raw=encode(v);env={'REQUEST_METHOD':'POST','PATH_INFO':path,'REMOTE_ADDR':'127.0.0.1','HTTP_X_REAL_IP':'192.0.2.4','HTTP_X_NFQWS2_SUBMISSION_ID':v['submission_id'],'CONTENT_LENGTH':str(len(raw)),'CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(raw)};status=[]
                out=b''.join(app(env,lambda s,h:status.append(s)));return int(status[0][:3]),json.loads(out)
            self.assertEqual(req('/nfqws-support/v3/reports')[0],422)
            self.assertEqual(req('/nfqws-support/v4/reports')[0],200);self.assertEqual(req('/nfqws-support/v4/reports')[0],200);self.assertEqual(sender.count,1)

    def test_encoded_token_query_is_rejected_on_router_and_relay(self):
        v=fixture(('dns',));d=dns();row=d['sources'][0]['profile']['upstreams'][0];row.update(protocol='doh',port=443,url='https://dns.quad9.net/dns-query?to%6ben=SECRET');v['files'][0]=file('dns',d)
        with self.assertRaises(InvalidReport):validate_share(encode(v),v['submission_id'])
        self.assertIn('error',self.php(v,"echo json_encode(AsusShareBundle::envelope(json_encode($v),$v['submission_id']));"))

    def test_common_auth_parameters_and_empty_tokens_are_rejected_on_both_sides(self):
        for query in ['access_token=PRIVATE_CANARY','auth-token=PRIVATE_CANARY','api_token=PRIVATE_CANARY','client_secret=PRIVATE_CANARY','x-api-key=PRIVATE_CANARY','token','token=']:
            with self.subTest(query=query):
                v=fixture(('dns',));d=dns();row=d['sources'][0]['profile']['upstreams'][0];row.update(protocol='doh',port=443,url='https://dns.quad9.net/dns-query?'+query);v['files'][0]=file('dns',d)
                with self.assertRaises(InvalidReport):validate_share(encode(v),v['submission_id'])
                self.assertIn('error',self.php(v,"echo json_encode(AsusShareBundle::envelope(json_encode($v),$v['submission_id']));"))
