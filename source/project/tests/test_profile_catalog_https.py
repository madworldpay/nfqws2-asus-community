"""Real local TLS exercises certificate, redirects, size and read deadlines."""
import http.server,json,pathlib,socket,ssl,subprocess,tempfile,threading,time,unittest
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

    def read(self,path='/ok',cap=64,seconds=2,ca=None,url=None,prelude=''):
        # Reflection reaches the real reader only; production origin stays fixed.
        code="""require $argv[1].'/profile-catalog-transport.php';"""+prelude+"""try{$m=new ReflectionMethod(AsusProfileCatalogTransport::class,'https');echo json_encode(['body'=>$m->invoke(null,$argv[2],(int)$argv[3],microtime(true)+(float)$argv[4],$argv[5])]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"""
        url=url or 'https://127.0.0.1:'+str(self.server.server_port)+path
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),url,str(cap),str(seconds),str(self.cert if ca is None else ca)],text=True,capture_output=True,timeout=4)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def test_verified_tls_succeeds_but_untrusted_certificate_is_rejected(self):
        self.assertEqual(self.read(),{'body':'{}'})
        self.assertEqual(self.read(ca='/etc/ssl/certs/ca-certificates.crt'),{'error':'catalog_tls'})

    def test_missing_ca_and_https_runtime_are_distinguished_without_raw_warnings(self):
        self.assertEqual(self.read(ca=str(self.cert)+'.absent'),{'error':'catalog_tls'})
        self.assertEqual(self.read(prelude="stream_wrapper_unregister('https');"),{'error':'catalog_runtime'})

    def test_connection_refused_has_bounded_nonsecret_diagnostic(self):
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1',0))
            url='https://127.0.0.1:'+str(reserved.getsockname()[1])+'/PRIVATE_CANARY'
            self.assertEqual(self.read(url=url),{'error':'catalog_connect'})

    def test_redirect_is_never_followed(self):
        before=len(self.requests);self.assertEqual(self.read('/redirect'),{'error':'catalog_http'});self.assertEqual(self.requests[before:],['/redirect'])

    def test_declared_and_streamed_oversize_and_compression_are_rejected(self):
        for path in ['/length','/large','/compressed']:
            with self.subTest(path=path):self.assertEqual(self.read(path,cap=4),{'error':'catalog_limit'})

    def test_slow_body_is_stopped_at_read_deadline(self):
        start=time.monotonic();self.assertEqual(self.read('/slow',seconds=.15),{'error':'catalog_timeout'});self.assertLess(time.monotonic()-start,1.5)


class ProfileCatalogDiagnosticTests(unittest.TestCase):
    def test_php_connection_warnings_are_projected_to_closed_codes(self):
        # DNS is libc/system-owned; classify recorded PHP warning forms without
        # making the offline suite depend on a working external DNS resolver.
        cases=[
            ('php_network_getaddresses: getaddrinfo failed: Temporary failure in name resolution PRIVATE_CANARY','catalog_dns'),
            ('php_network_getaddresses: getaddrinfo for PRIVATE_CANARY failed: Name or service not known','catalog_dns'),
            ('SSL operation failed with code 1: certificate verify failed PRIVATE_CANARY','catalog_tls'),
            ('Failed to open stream: Connection refused PRIVATE_CANARY','catalog_connect'),
            ('Failed to open stream: Network is unreachable PRIVATE_CANARY','catalog_connect'),
            ('Failed to open stream: Connection timed out PRIVATE_CANARY','catalog_timeout'),
            ('Unable to find the wrapper "https" PRIVATE_CANARY','catalog_runtime'),
            ('PRIVATE_CANARY unknown provider error','catalog_unavailable'),
        ]
        code="""require $argv[1].'/profile-catalog-api.php';$m=new ReflectionMethod(AsusProfileCatalogTransport::class,'connectionError');$out=[];foreach(json_decode(stream_get_contents(STDIN),true) as $case){$code=$m->invoke(null,$case[0]);$out[]=['transport'=>$code,'api'=>AsusProfileCatalogApi::error(new RuntimeException($code))];}echo json_encode($out);"""
        result=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(cases),capture_output=True,text=True,timeout=4)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertEqual(result.stderr,'')
        self.assertEqual(json.loads(result.stdout),[{'transport':expected,'api':expected} for _,expected in cases])
