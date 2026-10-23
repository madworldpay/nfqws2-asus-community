"""Real local TLS exercises certificate, redirects, size and read deadlines."""
import http.server,json,pathlib,ssl,subprocess,tempfile,threading,time,unittest
from test_dpi_normalize import PHP,PUBLIC


class ProfileCatalogHttpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();base=pathlib.Path(cls.tmp.name)
        cls.cert=base/'cert.pem';key=base/'key.pem';cls.requests=[]
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1','-days','1','-keyout',str(key),'-out',str(cls.cert)],check=True,capture_output=True)
        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*_):pass
            def do_GET(self):
                cls.requests.append(self.path)
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','/ok');self.send_header('Content-Length','0');self.end_headers();return
                self.send_response(200);self.send_header('Connection','close')
                if self.path=='/length':self.send_header('Content-Length','1000')
                elif self.path=='/compressed':self.send_header('Content-Encoding','gzip')
                self.end_headers()
                try:
                    if self.path=='/slow':self.wfile.write(b'{');self.wfile.flush();time.sleep(.5);self.wfile.write(b'}')
                    else:self.wfile.write(b'0123456789' if self.path=='/large' else b'{}')
                except (BrokenPipeError,ConnectionResetError,ssl.SSLError):pass
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cls.cert,key)
        cls.server.socket=context.wrap_socket(cls.server.socket,server_side=True)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()

    def read(self,path='/ok',cap=64,seconds=2,ca=None):
        # Reflection reaches the real reader only; production origin stays fixed.
        code="""require $argv[1].'/profile-catalog-transport.php';try{$m=new ReflectionMethod(AsusProfileCatalogTransport::class,'https');echo json_encode(['body'=>$m->invoke(null,$argv[2],(int)$argv[3],microtime(true)+(float)$argv[4],$argv[5])]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
        url='https://127.0.0.1:'+str(self.server.server_port)+path
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),url,str(cap),str(seconds),str(self.cert if ca is None else ca)],text=True,capture_output=True,timeout=4)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def test_verified_tls_succeeds_but_untrusted_certificate_is_rejected(self):
        self.assertEqual(self.read(),{'body':'{}'})
        self.assertEqual(self.read(ca='/etc/ssl/certs/ca-certificates.crt'),{'error':'catalog_unavailable'})

    def test_redirect_is_never_followed(self):
        before=len(self.requests);self.assertEqual(self.read('/redirect'),{'error':'catalog_unavailable'});self.assertEqual(self.requests[before:],['/redirect'])

    def test_declared_and_streamed_oversize_and_compression_are_rejected(self):
        for path in ['/length','/large','/compressed']:
            with self.subTest(path=path):self.assertEqual(self.read(path,cap=4),{'error':'catalog_limit'})

    def test_slow_body_is_stopped_at_read_deadline(self):
        start=time.monotonic();self.assertEqual(self.read('/slow',seconds=.15),{'error':'catalog_timeout'});self.assertLess(time.monotonic()-start,1.5)
