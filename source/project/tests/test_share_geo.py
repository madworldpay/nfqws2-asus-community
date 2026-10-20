import io,json,os,tempfile,time,unittest
from unittest.mock import Mock,patch
from pathlib import Path
from types import SimpleNamespace
from test_support_relay_smtp import config
from nfqws_support.geo import GeoLookup,_reader
from nfqws_support.app import create_app

class Reader:
    def __init__(self,epoch,value):self.epoch=epoch;self.value=value;self.calls=[];self.closed=False
    def metadata(self):return SimpleNamespace(build_epoch=self.epoch)
    def get(self,ip):self.calls.append(ip);return self.value
    def close(self):self.closed=True
VALUE={'country':{'iso_code':'DE','names':{'en':'Germany'}},'subdivisions':[{'names':{'en':'Berlin','ru':'Берлин'}}],'city':{'names':{'en':'Berlin','ru':'Берлин'}},'location':{'latitude':52.5,'longitude':13.4},'traits':{'isp':'PRIVATE_PROVIDER'}}

class ShareGeoTests(unittest.TestCase):
    def test_reader_uses_pinned_maxminddb_3_api_mmap_constant(self):
        module=SimpleNamespace(MODE_MMAP=2,open_database=Mock(return_value='reader'))
        with patch.dict('sys.modules',{'maxminddb':module}):
            self.assertEqual(_reader(Path('/fixed/database.mmdb')),'reader')
        module.open_database.assert_called_once_with('/fixed/database.mmdb',mode=2)
    def test_coarse_offline_projection_and_hashed_cache(self):
        now=1792100000
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'city.mmdb';p.write_bytes(b'fixture');p.chmod(0o600);reader=Reader(now-3*86400,VALUE)
            geo=GeoLookup(p,reader_factory=lambda path:reader,clock=lambda:now,owner=os.getuid())
            a=geo.lookup('8.8.8.8');self.assertEqual(a,{'available':True,'country':'DE','region':'Берлин','city':'Берлин','database_age_days':3})
            self.assertEqual(geo.lookup('8.8.8.8'),a);self.assertEqual(reader.calls,['8.8.8.8'])
            self.assertNotIn('8.8.8.8',repr(geo._cache));self.assertNotIn('PRIVATE_PROVIDER',json.dumps(a));self.assertNotIn('latitude',json.dumps(a))
    def test_missing_stale_future_oversized_links_and_bad_records_allow_manual_input(self):
        now=1792100000
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'city.mmdb';p.write_bytes(b'fixture');p.chmod(0o600)
            for epoch,value in [(now-63*86400,VALUE),(now+2*86400,VALUE),(now,{'city':{'names':{'en':'x'*121}}}),(now,VALUE|{'country':{'iso_code':'BAD'}})]:
                geo=GeoLookup(p,reader_factory=lambda path:Reader(epoch,value),clock=lambda:now,owner=os.getuid())
                self.assertFalse(geo.lookup('8.8.8.8')['available'])
            alias=Path(d)/'alias';alias.symlink_to(p)
            self.assertFalse(GeoLookup(alias,owner=os.getuid()).lookup('8.8.8.8')['available'])
            self.assertFalse(GeoLookup(Path(d)/'missing').lookup('8.8.8.8')['available'])
            p.chmod(0o666);self.assertFalse(GeoLookup(p,owner=os.getuid()).lookup('8.8.8.8')['available'])
            p.chmod(0o600)
            with p.open('wb') as f:f.truncate(192*1024*1024+1)
            self.assertFalse(GeoLookup(p,owner=os.getuid()).lookup('8.8.8.8')['available'])
    def test_private_ips_and_lookup_budget_do_not_retain_ip(self):
        now=1792100000
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'city.mmdb';p.write_bytes(b'fixture');p.chmod(0o600);reader=Reader(now,VALUE)
            geo=GeoLookup(p,reader_factory=lambda path:reader,clock=lambda:now,owner=os.getuid(),lookup_limit=2)
            for ip in ['127.0.0.1','192.168.1.1','::1','198.51.100.1','bad']:
                self.assertFalse(geo.lookup(ip)['available'])
            self.assertEqual(reader.calls,[])
            self.assertTrue(geo.lookup('8.8.8.8')['available']);self.assertTrue(geo.lookup('1.1.1.1')['available'])
            self.assertFalse(geo.lookup('9.9.9.9')['available']);self.assertEqual(len(reader.calls),2)
    def test_fixed_endpoint_uses_trusted_proxy_without_query_body_or_spoof(self):
        class Geo:
            def __init__(self):self.calls=[]
            def lookup(self,ip):self.calls.append(ip);return {'available':False}
        geo=Geo();app=create_app(config(),None,None,geo=geo)
        def request(**extra):
            env={'REQUEST_METHOD':'GET','PATH_INFO':'/nfqws-support/v3/location','REMOTE_ADDR':'127.0.0.1','HTTP_X_REAL_IP':'8.8.8.8','HTTP_X_FORWARDED_FOR':'1.1.1.1','wsgi.input':io.BytesIO()};env.update(extra);out=[]
            raw=b''.join(app(env,lambda s,h:out.append((s,h))));return out,json.loads(raw)
        self.assertEqual(request()[1],{'available':False});self.assertEqual(geo.calls,['8.8.8.8'])
        for extra in [{'QUERY_STRING':'ip=1.1.1.1'},{'CONTENT_LENGTH':'1'},{'REMOTE_ADDR':'8.8.8.8'},{'HTTP_TRANSFER_ENCODING':'chunked'},{'HTTP_X_REAL_IP':'not-ip'},{'REQUEST_METHOD':'POST'}]:
            request(**extra)
        self.assertEqual(geo.calls,['8.8.8.8'])
