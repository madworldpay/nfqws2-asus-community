import base64,hashlib,io,json,os,tempfile,unittest,uuid,zlib
from email import policy
from email.parser import BytesParser
from pathlib import Path
from test_share_bundle_api import share_files
from test_support_relay_smtp import config,FakeSmtp
from nfqws_support.share import validate_share,share_subject
from nfqws_support.validation import InvalidReport
from nfqws_support.smtp import SmtpSender,SendOutcome
from nfqws_support.store import RelayStore
from nfqws_support.app import create_app

SOURCE={'model':'GT-BE19000AI','firmware':{'firmver':'3006.102','buildno':'9','extendno':'0'},'kernel':'4.19.294','versions':{'core':'1.3.1-asus6+b16','web':'0.1.4'},'installation_id':'a'*32}
def fixture(kinds=('report','dpi','strategy'),sid=None,source=None):
    v={'version':3,'submission_id':sid or str(uuid.uuid4()),'files':share_files(kinds)}
    if source is not None:v['source']=source
    return v
def encode(v):return json.dumps(v,separators=(',',':'),ensure_ascii=False).encode()

class ShareRelayTests(unittest.TestCase):
    def test_all_combinations_and_source_metadata_are_closed_and_immutable(self):
        for kinds in [('report',),('dpi',),('strategy',),('report','dpi'),('report','strategy'),('dpi','strategy'),('report','dpi','strategy')]:
            v=fixture(kinds,source=SOURCE);b=validate_share(encode(v),v['submission_id'])
            self.assertEqual([f.type for f in b.files],list(kinds));self.assertEqual(json.loads(b.source_json),SOURCE)
            self.assertEqual([f.raw for f in b.files],[base64.b64decode(f['data_base64']) for f in v['files']])
            changed=fixture(kinds,sid=v['submission_id'],source=SOURCE|{'kernel':None})
            self.assertNotEqual(validate_share(encode(changed),v['submission_id']).sha256,b.sha256)
        for source in [SOURCE|{'ip':'198.51.100.1'},SOURCE|{'installation_id':'not-an-id'},SOURCE|{'model':'my-home-name'}]:
            v=fixture(source=source)
            with self.assertRaises(InvalidReport):validate_share(encode(v),v['submission_id'])
    def test_malformed_files_private_fields_and_wrong_order_fail(self):
        v=fixture()
        for bad in [v|{'version':2},v|{'files':[]},v|{'files':list(reversed(v['files']))},v|{'files':[v['files'][0]]*2},v|{'extra':'private'}]:
            with self.assertRaises(InvalidReport):validate_share(encode(bad),v['submission_id'])
        for key,value in [('data_base64',v['files'][0]['data_base64']+'\n'),('byte_length',1),('sha256','0'*64),('filename','bad.json')]:
            bad=fixture();bad['files'][0][key]=value
            with self.assertRaises(InvalidReport):validate_share(encode(bad),bad['submission_id'])
        for raw in [b'x'*2097153,b'\xff',encode(v).replace(b'"version":3',b'"version":3,"version":3')]:
            with self.assertRaises(InvalidReport):validate_share(raw,v['submission_id'])
        bad=fixture(('strategy',));f=bad['files'][0];data=json.loads(base64.b64decode(f['data_base64']));data['operator']='   ';raw=encode(data)
        f.update(byte_length=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data_base64=base64.b64encode(raw).decode())
        with self.assertRaises(InvalidReport):validate_share(encode(bad),bad['submission_id'])
    def test_subject_has_two_categories_without_one_label_per_installation(self):
        for kinds,expected in [(('dpi',),'NFQWS2 community [diagnostics]'),(('strategy',),'NFQWS2 community [strategies]'),(('report','strategy'),'NFQWS2 community [diagnostics] [strategies]')]:
            v=fixture(kinds);self.assertEqual(share_subject(validate_share(encode(v),v['submission_id']).files),expected)
    def test_v3_one_send_dedup_and_metadata_conflict_preserve_old_health(self):
        class Sender:
            def __init__(self):self.calls=[]
            def send_bundle(self,b):self.calls.append(b);return SendOutcome('accepted')
        with tempfile.TemporaryDirectory() as d:
            sender=Sender();app=create_app(config(),RelayStore(Path(d)/'db',b'x'*32),sender);v=fixture(source=SOURCE)
            def request(v,**extra):
                raw=encode(v);env={'REQUEST_METHOD':'POST','PATH_INFO':'/nfqws-support/v3/reports','REMOTE_ADDR':'127.0.0.1','HTTP_X_REAL_IP':'192.0.2.4','HTTP_X_NFQWS2_SUBMISSION_ID':v['submission_id'],'CONTENT_LENGTH':str(len(raw)),'CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(raw)};env.update(extra);status=[]
                body=b''.join(app(env,lambda s,h:status.append(s)));return int(status[0][:3]),json.loads(body)
            self.assertEqual(request(v)[0],200);self.assertEqual(request(v)[0],200);self.assertEqual(len(sender.calls),1)
            self.assertEqual(request(v|{'source':SOURCE|{'kernel':None}})[1]['code'],'id_conflict')
            self.assertEqual(request(fixture(),REMOTE_ADDR='198.51.100.8')[0],422)
            self.assertEqual(request(fixture(),HTTP_X_NFQWS2_FILENAME='extra.json')[0],422)
            db=(Path(d)/'db').read_bytes();self.assertNotIn(b'GT-BE19000AI',db);self.assertNotIn(b'a'*32,db)
    def test_one_mixed_mime_contains_exact_json_and_searchable_consented_id(self):
        v=fixture(source=SOURCE);bundle=validate_share(encode(v),v['submission_id']);r,w=os.pipe()
        try:
            fake=FakeSmtp(capture_fd=w);self.assertEqual(SmtpSender(config(),factory=lambda **kw:fake).send_bundle(bundle).state,'accepted');os.close(w);w=None
            record=json.loads(zlib.decompress(os.read(r,262144)))
        finally:
            os.close(r)
            if w is not None:os.close(w)
        msg=BytesParser(policy=policy.default).parsebytes(record['wire'].encode()[:-3]);files=list(msg.iter_attachments())
        self.assertEqual(str(msg['Subject']),'NFQWS2 community [diagnostics] [strategies]');self.assertEqual(len(files),3)
        self.assertEqual([p.get_payload(decode=True) for p in files],[f.raw for f in bundle.files])
        body=msg.get_body(preferencelist=('plain',)).get_content();meta=json.loads(body)
        self.assertEqual(meta['source'],SOURCE);self.assertEqual(meta['submission_id'],v['submission_id'])
        self.assertEqual(str(msg['X-NFQWS2-Submission-ID']),v['submission_id'])
        v=fixture(('strategy',),source={k:v for k,v in SOURCE.items() if k!='installation_id'})
        self.assertNotIn('installation_id',validate_share(encode(v),v['submission_id']).source_json)
