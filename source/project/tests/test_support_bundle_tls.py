from http.server import HTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import hashlib,base64,json,os,ssl,subprocess,tempfile,threading,unittest
from test_support_relay_bundle_validation import bundle_fixture,encode,dpi_fixture
from test_support_relay_validation import fixture
from test_dpi_normalize import PUBLIC

class BundleTlsTests(unittest.TestCase):
    def test_actual_php_v2_opt_in_two_files_big_envelope_and_bad_ca(self):
        php=os.environ['PHP_TLS_TEST_BINARY'];ext=os.environ['PHP_OPENSSL_TEST_EXTENSION'];v=bundle_fixture()
        # Valid JSON may have whitespace up to the declared byte cap.
        for f,raw,limit in zip(v['files'],[fixture(),dpi_fixture()],[1048576,262144]):
            raw+=b' '*(limit-len(raw));f.update(byte_length=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data_base64=base64.b64encode(raw).decode())
        raw=encode(v)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'body').write_bytes(raw);calls=[]
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost','-keyout',str(p/'key'),'-out',str(p/'cert')],check=True,capture_output=True)
            class H(BaseHTTPRequestHandler):
                def log_message(self,*a):pass
                def do_POST(self):
                    body=self.rfile.read(int(self.headers['Content-Length']));calls.append((self.path,body,self.headers.get('X-NFQWS2-Filename')))
                    r=json.dumps({'state':'accepted','submission_id':v['submission_id'],'code':'smtp_accepted'}).encode();self.send_response(200);self.send_header('Content-Length',str(len(r)));self.end_headers();self.wfile.write(r)
            server=HTTPServer(('127.0.0.1',0),H);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(p/'cert',p/'key');server.socket=ctx.wrap_socket(server.socket,server_side=True);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            code="require $argv[1].'/support-mail.php';$m=new AsusSupportMail($argv[2].'/config',$argv[3],fileowner($argv[2]));echo json_encode([$m->availability(),$m->sendBundle(file_get_contents($argv[2].'/body'),$argv[4])]);"
            def run(flag,ca=None):
                (p/'config').write_text(json.dumps({'enabled':True,'url':f'https://localhost:{server.server_port}/nfqws-support/v1/reports',**({'dpi_attachments_enabled':flag} if flag is not None else {})}));(p/'config').chmod(0o600)
                r=subprocess.run([php,'-n','-d','extension='+ext,'-r',code,str(PUBLIC),directory,str(ca or p/'cert'),v['submission_id']],capture_output=True,text=True,timeout=22)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
            try:
                self.assertEqual(run(None)[1]['state'],'failed_safe');self.assertEqual(calls,[])
                status,outcome=run(True);self.assertEqual(outcome['state'],'accepted');self.assertEqual(calls, [('/nfqws-support/v2/reports',raw,None)]);self.assertTrue(status['dpi_attachments'])
                (p/'badca').write_text('bad');self.assertEqual(run(True,p/'badca')[1]['state'],'unknown');self.assertEqual(len(calls),1)
            finally:server.shutdown();server.server_close();t.join(timeout=2)
