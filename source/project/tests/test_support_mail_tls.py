from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]


class PhpTlsTests(unittest.TestCase):
    def test_real_php_verifies_ca_and_hostname_and_never_follows_redirects(self):
        php=os.environ.get('PHP_TLS_TEST_BINARY',os.environ.get('PHP_TEST_BINARY'))
        extension=os.environ.get('PHP_OPENSSL_TEST_EXTENSION')
        if not php or not extension: self.skipTest('matching PHP TLS runtime required')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); calls=[]
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                            '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost',
                            '-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem')],capture_output=True,check=True)
            sid=str(uuid.uuid4()); raw=b'{"schema_version":1}\n'
            filename='NFQWS2_GT-BE19000AI_2026-10-15_12-30-45Z.json'
            class Handler(BaseHTTPRequestHandler):
                mode='ok'
                def log_message(self,*args): pass
                def do_POST(self):
                    body=self.rfile.read(int(self.headers['Content-Length']))
                    calls.append((self.path,body,dict(self.headers)))
                    response=json.dumps({'state':'accepted','submission_id':sid,'code':'smtp_accepted'}).encode()
                    if self.mode=='redirect':
                        self.send_response(302);self.send_header('Location','/PRIVATE_CANARY')
                    else: self.send_response(200)
                    if self.mode=='oversize': response=b'PRIVATE_CANARY'*500
                    self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(response)))
                    self.end_headers();self.wfile.write(response)
            server=HTTPServer(('127.0.0.1',0),Handler)
            ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(root/'cert.pem',root/'key.pem')
            server.socket=ctx.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                cfg=root/'config.json'
                code='''require $argv[1];$m=new AsusSupportMail($argv[2],$argv[3],fileowner($argv[2]));echo json_encode([$m->availability(),$m->send("{\\"schema_version\\":1}\\n",$argv[4],$argv[5])]);'''
                def run(host='localhost',ca=None):
                    cfg.write_text(json.dumps({'enabled':True,'url':f'https://{host}:{server.server_port}/nfqws-support/v1/reports'}));cfg.chmod(0o600)
                    p=subprocess.run([php,'-n','-d','extension='+extension,'-r',code,
                                      str(ROOT/'webui/web/public/support-mail.php'),str(cfg),str(ca or root/'cert.pem'),filename,sid],capture_output=True,text=True,timeout=22)
                    self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
                    self.assertNotIn('PRIVATE_CANARY',p.stdout)
                    return json.loads(p.stdout)
                status,result=run()
                self.assertEqual(status,{'configured':True,'code':'ready','dpi_attachments':False})
                self.assertEqual(result['state'],'accepted')
                self.assertEqual(calls[0][1],raw)
                self.assertEqual(calls[0][2]['X-NFQWS2-Filename'],filename)
                before=len(calls)
                self.assertEqual(run('127.0.0.1')[1]['state'],'unknown')
                self.assertEqual(len(calls),before,'hostname failure must not deliver HTTP body')
                (root/'bad-ca.pem').write_text('invalid CA')
                self.assertEqual(run(ca=root/'bad-ca.pem')[1]['state'],'unknown')
                self.assertEqual(len(calls),before)
                Handler.mode='redirect'
                self.assertEqual(run()[1]['state'],'unknown');self.assertEqual(len(calls),before+1)
                self.assertEqual(calls[-1][0],'/nfqws-support/v1/reports')
                Handler.mode='oversize'
                self.assertEqual(run()[1]['state'],'unknown')
            finally:
                server.shutdown();server.server_close();thread.join(timeout=2)
