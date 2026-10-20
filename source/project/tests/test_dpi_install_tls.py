from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from test_dpi_normalize import PUBLIC


class DpiDownloadTlsTests(unittest.TestCase):
    def test_verified_bounded_download_redirects_and_length_hash(self):
        php=os.environ['PHP_TLS_TEST_BINARY'];extension=os.environ['PHP_OPENSSL_TEST_EXTENSION']
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);data=b'trusted binary fixture';calls=[]
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost','-keyout',str(p/'key'),' -out'.strip(),str(p/'ca')],capture_output=True,check=True)
            class Handler(BaseHTTPRequestHandler):
                mode='ok'
                def log_message(self,*args):pass
                def do_GET(self):
                    calls.append(self.path)
                    if self.mode=='redirect':
                        self.send_response(302);self.send_header('Location','https://127.0.0.1:'+str(self.server.server_port)+'/NEVER');body=b''
                    elif self.mode=='loop':
                        self.send_response(302);self.send_header('Location','https://localhost:'+str(self.server.server_port)+'/asset');body=b''
                    else:self.send_response(200);body=data+(b'x' if self.mode=='long' else b'')
                    self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            server=HTTPServer(('127.0.0.1',0),Handler);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(p/'ca',p/'key');server.socket=ctx.wrap_socket(server.socket,server_side=True)
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            code='''require $argv[1].'/dpi-install.php';try{$d=new AsusDpiDownload($argv[2],['localhost'],(int)$argv[3]);$d->fetch(['url'=>$argv[4],'size'=>(int)$argv[6],'sha256'=>$argv[7]],$argv[5],microtime(true)+5);echo 'ok';}catch(Throwable $e){echo $e->getMessage();}'''
            def run(host='localhost',ca=None,sha=None):
                dest=p/'download';dest.unlink(missing_ok=True)
                r=subprocess.run([php,'-n','-d','extension='+extension,'-r',code,str(PUBLIC),str(ca or p/'ca'),str(server.server_port),f'https://{host}:{server.server_port}/asset',str(dest),str(len(data)),sha or hashlib.sha256(data).hexdigest()],capture_output=True,text=True,timeout=8)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return r.stdout,dest
            try:
                result,dest=run();self.assertEqual(result,'ok');self.assertEqual(dest.read_bytes(),data)
                before=len(calls);self.assertEqual(run('127.0.0.1')[0],'untrusted_download');self.assertEqual(len(calls),before)
                (p/'badca').write_text('invalid');self.assertEqual(run(ca=p/'badca')[0],'download_failed');self.assertEqual(len(calls),before)
                Handler.mode='redirect';self.assertEqual(run()[0],'untrusted_download');self.assertEqual(len(calls),before+1)
                Handler.mode='loop';before=len(calls);self.assertEqual(run()[0],'download_redirect');self.assertEqual(len(calls),before+4)
                Handler.mode='long';self.assertEqual(run()[0],'download_size')
                Handler.mode='ok';self.assertEqual(run(sha='0'*64)[0],'download_hash')
            finally:server.shutdown();server.server_close();t.join(timeout=2)
