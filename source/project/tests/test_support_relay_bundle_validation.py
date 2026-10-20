import base64,hashlib,json,sys,unittest,uuid
from pathlib import Path
from test_support_relay_validation import fixture,FILENAME
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'support-relay/src'))
from nfqws_support.bundle import validate_bundle
from nfqws_support.validation import InvalidReport

ROOT=Path(__file__).resolve().parents[1]
DPI_FILENAME='NFQWS2_DPI_2026-10-15_12-00-00Z.json'
def dpi_fixture():
    c=json.loads((ROOT/'support/dpi-catalog.json').read_text());group=json.loads((ROOT/'tests/fixtures/dpi/group2.json').read_text())['expected'];ctx={'nfqws':'running','ark':'absent','tun_observed':False}
    return json.dumps({'type':'nfqws2_dpi','schema_version':1,'detector_version':c['version'],'profile_sha256':c['profile_sha256'],'origin':'router','started_at':'2026-10-15T12:00:00Z','finished_at':'2026-10-15T12:01:00Z','ip_family':'ipv4','state':'partial','selected_tests':[1,2],'groups':[group],'context':{'before':ctx,'after':ctx,'changed':False},'coverage':{'limited':True,'dns':9,'domains':6,'tcp':8,'sni':16}},separators=(',',':')).encode()
def bundle_fixture(sid=None):
    files=[]
    for kind,name,raw in [('report',FILENAME,fixture()),('dpi',DPI_FILENAME,dpi_fixture())]:files.append({'type':kind,'filename':name,'byte_length':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'data_base64':base64.b64encode(raw).decode()})
    return {'version':2,'submission_id':sid or str(uuid.uuid4()),'files':files}
def encode(v):return json.dumps(v,separators=(',',':')).encode()

class BundleValidationTests(unittest.TestCase):
    def test_cleaned_v2_is_accepted_but_native_and_free_identifiers_are_rejected(self):
        from nfqws_support.dpi_validation import validate_dpi_report
        old=json.loads(dpi_fixture());ctx=old['context']
        value={k:old[k] for k in ['type','detector_version','origin','started_at','finished_at','state','selected_tests']}
        value.update(schema_version=2,context=ctx,coverage={'domains':35},settings={'profile':'ru','proxy_configured':False,'interface_selected':False,'metrics':{}},groups=[{'group':2,'metrics':{},'rows':[{'target':'domain-1','metrics':{},'values':{'http':{'status':'ok','detail':{'code':'http','http_status':200}}}}]}])
        self.assertFalse(validate_dpi_report(encode(value),DPI_FILENAME).complete)
        for bad in [value|{'type':'nfqws2_dpi_native'},value|{'ip':'192.0.2.1'},value|{'groups':[{'group':2,'metrics':{},'rows':[{'target':'PRIVATE_DOMAIN','metrics':{}}]}]}]:
            with self.assertRaises(InvalidReport):validate_dpi_report(encode(bad),DPI_FILENAME)
    def test_exact_files_and_closed_input(self):
        v=bundle_fixture();b=validate_bundle(encode(v),v['submission_id']);self.assertEqual([f.raw for f in b.files],[fixture(),dpi_fixture()]);self.assertEqual(len(b.sha256),64)
        for key,value in [('version',1),('PRIVATE_CANARY',1),('submission_id',str(uuid.uuid4()))]:
            bad=v|{key:value}
            with self.assertRaises(InvalidReport):validate_bundle(encode(bad),v['submission_id'])
        for key,value in [('type','report'),('byte_length',1),('sha256','0'*64),('data_base64',v['files'][1]['data_base64']+'\n'),('filename','PRIVATE_CANARY.json')]:
            bad=bundle_fixture(v['submission_id']);bad['files'][1][key]=value
            with self.assertRaises(InvalidReport):validate_bundle(encode(bad),v['submission_id'])
    def test_size_depth_duplicate_utf8_and_private_fields_rejected(self):
        v=bundle_fixture()
        for raw in [b'x'*2097153,b'\xff',b'['*33+b'0'+b']'*33,encode(v).replace(b'"version":2',b'"version":2,"version":2')]:
            with self.assertRaises(InvalidReport):validate_bundle(raw,v['submission_id'])
        raw=dpi_fixture().replace(b'"origin":"router"',b'"origin":"router","PRIVATE_CANARY":"192.0.2.1"');v['files'][1].update(byte_length=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data_base64=base64.b64encode(raw).decode())
        with self.assertRaises(InvalidReport):validate_bundle(encode(v),v['submission_id'])
