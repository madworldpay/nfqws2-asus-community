import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from wsgiref.simple_server import make_server, WSGIRequestHandler

from test_support_relay_http import Sender
from test_support_relay_smtp import config
from test_support_relay_validation import fixture, FILENAME
from nfqws_support.app import create_app
from nfqws_support.store import RelayStore

ROOT=Path(__file__).resolve().parents[1]


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args): pass


class NginxTests(unittest.TestCase):
    def test_real_tls_proxy_body_cap_exact_bytes_and_no_body_files(self):
        binary=os.environ.get('NGINX_TEST_BINARY')
        if not binary: self.skipTest('NGINX_TEST_BINARY required for isolated Nginx integration')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                            '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost',
                            '-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem')],check=True,capture_output=True)
            sender=Sender()
            bundle_calls=[]
            def send_bundle(bundle):
                bundle_calls.append(bundle)
                from nfqws_support.smtp import SendOutcome
                return SendOutcome('accepted')
            sender.send_bundle=send_bundle
            server=make_server('127.0.0.1',0,create_app(config(),RelayStore(root/'db',b'x'*32,source_limit=4),sender),handler_class=QuietHandler)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            try:
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
                site=(ROOT/'support-relay/deploy/nginx.conf.example').read_text()
                site=site.replace('listen 443 ssl;',f'listen 127.0.0.1:{port} ssl;').replace('SUPPORT_HOST','localhost')
                site=site.replace('/etc/letsencrypt/live/localhost/fullchain.pem',str(root/'cert.pem')).replace('/etc/letsencrypt/live/localhost/privkey.pem',str(root/'key.pem'))
                site=site.replace('127.0.0.1:8875',f'127.0.0.1:{server.server_port}')
                for name in ['body','proxy','logs','fastcgi','scgi','uwsgi']: (root/name).mkdir()
                cfg=root/'nginx.conf'
                cfg.write_text(f'error_log {root}/error.log error;\npid {root}/nginx.pid;\nevents {{}}\nhttp {{ client_body_temp_path {root}/body; proxy_temp_path {root}/proxy; fastcgi_temp_path {root}/fastcgi; scgi_temp_path {root}/scgi; uwsgi_temp_path {root}/uwsgi; {site} }}\n')
                result=subprocess.run([binary,'-p',tmp+'/', '-t','-c',str(cfg)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                process=subprocess.Popen([binary,'-p',tmp+'/', '-c',str(cfg),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                try:
                    context=ssl.create_default_context(cafile=str(root/'cert.pem'))
                    for attempt in range(50):
                        try:
                            conn=http.client.HTTPSConnection('localhost',port,context=context,timeout=2)
                            conn.request('GET','/health'); response=conn.getresponse()
                            self.assertEqual(response.status,200); response.read(); conn.close(); break
                        except ConnectionRefusedError: time.sleep(.02)
                    else: self.fail('Nginx did not listen')
                    raw=fixture(); raw+=b' '*(1048576-len(raw))
                    conn=http.client.HTTPSConnection('localhost',port,context=context,timeout=5)
                    headers={'Content-Type':'application/json','X-NFQWS2-Filename':FILENAME,
                             'X-NFQWS2-Submission-ID':str(uuid.uuid4()), 'X-Real-IP':'PRIVATE_CANARY'}
                    conn.request('POST','/nfqws-support/v1/reports',raw,headers)
                    response=conn.getresponse(); self.assertEqual(response.status,200,response.read())
                    conn.close()
                    self.assertEqual(sender.calls,[(raw,FILENAME)])
                    # The edge must reject chunked input before proxy normalization
                    # erases Transfer-Encoding and manufactures Content-Length.
                    chunked=fixture()
                    conn=http.client.HTTPSConnection('localhost',port,context=context,timeout=5)
                    conn.request('POST','/nfqws-support/v1/reports',iter([chunked[:100],chunked[100:]]),headers|{'X-NFQWS2-Submission-ID':str(uuid.uuid4())},encode_chunked=True)
                    response=conn.getresponse(); self.assertIn(response.status,(400,422)); response.read(); conn.close()
                    self.assertEqual(sender.calls,[(raw,FILENAME)])
                    conn=http.client.HTTPSConnection('localhost',port,context=context,timeout=5)
                    conn.request('POST','/nfqws-support/v1/reports?PRIVATE_QUERY_CANARY',raw+b' ',headers)
                    response=conn.getresponse(); self.assertEqual(response.status,413); response.read(); conn.close()
                    self.assertEqual(list((root/'body').iterdir()),[])
                    self.assertEqual(list((root/'proxy').iterdir()),[])
                    for path in (root/'logs').iterdir(): self.assertEqual(path.stat().st_size,0)
                    from test_support_relay_bundle_validation import bundle_fixture,encode,dpi_fixture
                    import base64,hashlib
                    v=bundle_fixture()
                    dpi=dpi_fixture();dpi+=b' '*(262144-len(dpi))
                    for f,body in zip(v['files'],[raw,dpi]):f.update(byte_length=len(body),sha256=hashlib.sha256(body).hexdigest(),data_base64=base64.b64encode(body).decode())
                    envelope=encode(v);self.assertGreater(len(envelope),1048576)
                    conn=http.client.HTTPSConnection('localhost',port,context=context,timeout=10)
                    conn.request('POST','/nfqws-support/v2/reports',envelope,{'Content-Type':'application/json','X-NFQWS2-Submission-ID':v['submission_id']})
                    response=conn.getresponse();self.assertEqual(response.status,200,response.read());response.read();conn.close()
                    self.assertEqual([f.raw for f in bundle_calls[0].files],[raw,dpi])
                    self.assertEqual(list((root/'body').iterdir()),[])
                    from test_share_relay import fixture as share_fixture,encode as share_encode
                    submission=share_fixture(('strategy',))
                    conn=http.client.HTTPSConnection('localhost',port,context=context,timeout=10)
                    conn.request('POST','/nfqws-support/v3/reports',share_encode(submission),{'Content-Type':'application/json','X-NFQWS2-Submission-ID':submission['submission_id']})
                    response=conn.getresponse();self.assertEqual(response.status,200,response.read());response.read();conn.close()
                    self.assertEqual(bundle_calls[-1].files[0].type,'strategy')
                    from test_share_v4 import fixture as v4_fixture, BINARY
                    submission4=v4_fixture()
                    conn=http.client.HTTPSConnection('localhost',port,context=context,timeout=10)
                    conn.request('POST','/nfqws-support/v4/reports',share_encode(submission4),{'Content-Type':'application/json','X-NFQWS2-Submission-ID':submission4['submission_id']})
                    response=conn.getresponse();self.assertEqual(response.status,200,response.read());response.read();conn.close()
                    self.assertEqual(bundle_calls[-1].version,4)
                    sent_resources=json.loads(bundle_calls[-1].files[1].raw);self.assertEqual(base64.b64decode(sent_resources['files'][0]['data_base64']),BINARY)
                    self.assertEqual(list((root/'body').iterdir()),[])
                    conn=http.client.HTTPSConnection('localhost',port,context=context,timeout=5)
                    conn.request('GET','/nfqws-support/v3/location')
                    response=conn.getresponse();self.assertEqual(response.status,200);self.assertEqual(json.loads(response.read()),{'available':False});conn.close()
                    conn=http.client.HTTPSConnection('localhost',port,context=context,timeout=10)
                    conn.request('POST','/nfqws-support/v2/reports',b'x'*2097153,{'Content-Type':'application/json'})
                    response=conn.getresponse();self.assertEqual(response.status,413);response.read();conn.close()
                    server.shutdown(); server.server_close(); thread.join(timeout=2)
                    conn=http.client.HTTPSConnection('localhost',port,context=context,timeout=5)
                    conn.request('POST','/nfqws-support/v1/reports?PRIVATE_UPSTREAM_CANARY',fixture(),headers)
                    response=conn.getresponse(); self.assertEqual(response.status,502); response.read(); conn.close()
                    log=(root/'error.log').read_bytes()
                    self.assertNotIn(b'PRIVATE_',log)
                    self.assertNotIn(b'client: 127.0.0.1',log)
                finally:
                    process.terminate(); process.wait(timeout=5)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)
