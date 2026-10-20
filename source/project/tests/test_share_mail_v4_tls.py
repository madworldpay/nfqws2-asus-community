"""The operator gate controls the real TLS route, without sending email."""
import json,os,ssl,subprocess,tempfile,threading,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
from test_share_v4 import fixture
from test_share_relay import encode
from test_share_bundle_api import share_files
from test_dpi_normalize import PUBLIC

class ShareMailV4TlsTests(unittest.TestCase):
    def test_separate_v4_gate_and_exact_tls_routing_leave_v3_working(self):
        php=os.environ.get('PHP_TLS_TEST_BINARY');extension=os.environ.get('PHP_OPENSSL_TEST_EXTENSION')
        if not php or not extension:self.skipTest('matching TLS runtime required')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);calls=[]
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem')],check=True,capture_output=True)
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_POST(self):
                    raw=self.rfile.read(int(self.headers['Content-Length']));calls.append((self.path,raw));body=json.dumps({'state':'accepted','code':'smtp_accepted','submission_id':self.headers['X-NFQWS2-Submission-ID']}).encode()
                    self.send_response(200);self.send_header('Content-Length',str(len(body)));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
            server=HTTPServer(('127.0.0.1',0),Handler);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(root/'cert.pem',root/'key.pem');server.socket=ctx.wrap_socket(server.socket,server_side=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                def run(value,flag):
                    cfg=root/'config.json';cfg.write_text(json.dumps({'enabled':True,'url':f'https://localhost:{server.server_port}/nfqws-support/v1/reports','sharing_v3_enabled':True,'sharing_v4_enabled':flag}));cfg.chmod(0o600)
                    code="require $argv[1].'/support-mail.php';$raw=stream_get_contents(STDIN);$v=json_decode($raw,true);$m=new AsusSupportMail($argv[2],$argv[3],fileowner($argv[2]));echo json_encode([$m->shareAvailability(),$m->sendShare($raw,$v['submission_id'])]);"
                    result=subprocess.run([php,'-n','-d','extension='+extension,'-r',code,str(PUBLIC),str(cfg),str(root/'cert.pem')],input=encode(value),capture_output=True,timeout=20)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertEqual(result.stderr,b'');return json.loads(result.stdout)
                v4=fixture();status,result=run(v4,False);self.assertFalse(status['sharing_v4']);self.assertEqual(result['state'],'failed_safe');self.assertEqual(calls,[])
                v3={'version':3,'submission_id':v4['submission_id'],'files':share_files(('strategy',))};self.assertEqual(run(v3,False)[1]['state'],'accepted');self.assertEqual(calls[-1],('/nfqws-support/v3/reports',encode(v3)))
                status,result=run(v4,True);self.assertTrue(status['sharing_v4']);self.assertEqual(result['state'],'accepted');self.assertEqual(calls[-1],('/nfqws-support/v4/reports',encode(v4)))
            finally:server.shutdown();server.server_close();thread.join(timeout=2)
