import json,os,subprocess,tempfile,time,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
from http.server import BaseHTTPRequestHandler,HTTPServer
import ssl,threading
GUARD_DIR=tempfile.TemporaryDirectory()
GUARD=Path(GUARD_DIR.name)/'location-launch'
subprocess.run(['cc','-Os','-nostdlib','-static','-fno-stack-protector','-fno-pie','-no-pie',str(PUBLIC.parents[2]/'asus/share/location-launch.c'),'-o',str(GUARD)],check=True,capture_output=True)

class ShareLocationDeadlineTests(unittest.TestCase):
    def test_native_stall_is_killed_by_parent_and_worker_output_is_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=root/'config.json';cfg.write_text(json.dumps({'enabled':True,'sharing_v3_enabled':True,'url':'https://relay.invalid/nfqws-support/v1/reports'}));cfg.chmod(0o600)
            # A ready TLS capability is a lower dependency; only the child process
            # is replaced. The deadline/protocol/kill logic under test is real.
            code='''require $argv[1].'/support-mail.php';class ReadyMail extends AsusSupportMail{public function shareAvailability():array{return ['configured'=>true,'code'=>'ready','sharing_v3'=>true];}}
            $m=new ReadyMail($argv[2],'/fixture-ca',(int)$argv[3],json_decode($argv[4],true),0.25,[$argv[5]]);echo json_encode($m->location());'''
            for worker,available in [(['/usr/bin/python3','-c','import time;time.sleep(20)'],False),(['/usr/bin/python3','-c','print("x"*5000)'],False),(['/usr/bin/python3','-c','print(\'{"available":true,"country":"DE","region":"Berlin","city":"Berlin","database_age_days":1}\')'],True)]:
                started=time.monotonic();p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(cfg),str(os.getuid()),json.dumps(worker),str(GUARD)],capture_output=True,text=True,timeout=3)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');v=json.loads(p.stdout)
                self.assertEqual(v['available'],available);self.assertLess(time.monotonic()-started,2)
    def test_http_cannot_invoke_private_location_worker(self):
        code="$_SERVER['REQUEST_METHOD']='GET';include $argv[1].'/share-location-worker.php';"
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],capture_output=True,text=True,timeout=3)
        self.assertEqual(p.stdout,'');self.assertEqual(p.stderr,'')

    def test_matching_cgi_worker_verifies_tls_and_only_reads_fixed_location(self):
        php=os.environ.get('PHP_TLS_TEST_BINARY',PHP)
        cgi=os.environ.get('PHP_TLS_CGI_TEST_BINARY',os.environ.get('PHP_CGI_TEST_BINARY'));ext=os.environ.get('PHP_OPENSSL_TEST_EXTENSION')
        if not cgi or not ext:self.skipTest('matching CGI and OpenSSL required')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);calls=[]
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost',
                '-addext','subjectAltName=DNS:localhost','-keyout',str(root/'key'),'-out',str(root/'cert')],capture_output=True,check=True)
            class Handler(BaseHTTPRequestHandler):
                mode='ok'
                def log_message(self,*args):pass
                def do_GET(self):
                    calls.append((self.path,dict(self.headers)))
                    raw=b'{"available":true,"country":"DE","region":"Berlin","city":"Berlin","database_age_days":1}'
                    self.send_response(302 if self.mode=='redirect' else 200)
                    if self.mode=='redirect':self.send_header('Location','/PRIVATE_CANARY')
                    self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            server=HTTPServer(('127.0.0.1',0),Handler);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(root/'cert',root/'key');server.socket=ctx.wrap_socket(server.socket,server_side=True)
            t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                cfg=root/'config';cfg.chmod(0o600) if cfg.exists() else None
                command=[cgi,'-n','-d','extension='+ext,'-d','register_argc_argv=1','-q','-f',str(PUBLIC/'share-location-worker.php'),'--','location']
                code="require $argv[1].'/support-mail.php';echo json_encode((new AsusSupportMail($argv[2],$argv[3],fileowner($argv[2]),json_decode($argv[4],true),5,[$argv[5]]))->location());"
                def run(host):
                    cfg.write_text(json.dumps({'enabled':True,'sharing_v3_enabled':True,'url':f'https://{host}:{server.server_port}/nfqws-support/v1/reports'}));cfg.chmod(0o600)
                    p=subprocess.run([php,'-n','-d','extension='+ext,'-r',code,str(PUBLIC),str(cfg),str(root/'cert'),json.dumps(command),str(GUARD)],capture_output=True,text=True,timeout=8)
                    self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)
                self.assertTrue(run('localhost')['available']);self.assertEqual(len(calls),1)
                self.assertEqual(calls[0][0],'/nfqws-support/v3/location');self.assertNotIn('Authorization',calls[0][1])
                self.assertFalse(run('127.0.0.1')['available']);self.assertEqual(len(calls),1)
                Handler.mode='redirect';self.assertFalse(run('localhost')['available']);self.assertEqual(len(calls),2)
                self.assertNotIn('PRIVATE_CANARY',str(calls))
            finally:server.shutdown();server.server_close();t.join(timeout=2)
