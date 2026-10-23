"""Run the actual static serving rules, including methods and rate limiting."""
import concurrent.futures,http.client,os,pathlib,shutil,socket,subprocess,tempfile,time,unittest
from test_dpi_normalize import ROOT


class ProfileCatalogNginxTests(unittest.TestCase):
    def setUp(self):
        self.binary=os.environ.get('NFQWS_NGINX_BINARY') or shutil.which('nginx')
        if not self.binary:self.skipTest('local nginx binary required')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=pathlib.Path(self.tmp.name)
        self.root=self.base/'public';(self.root/'files').mkdir(parents=True)
        (self.root/'catalog.json').write_text('{"signed":"fixture"}')
        self.sha='a'*64;(self.root/'files'/(self.sha+'.json')).write_text('{"profile":"fixture"}')
        (self.base/'private-key.pem').write_text('PRIVATE_CANARY')
        settings=ROOT/'profile-catalog'
        self.assertTrue((settings/'nginx.conf.example').is_file(),'cloud server locations are implemented')
        self.assertTrue((settings/'nginx-http.conf.example').is_file(),'rate zones belong in the http context')
        locations=(settings/'nginx.conf.example').read_text().replace('/srv/nfqws-profiles/v1',str(self.root))
        zones=(settings/'nginx-http.conf.example').read_text()
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        temporary=''.join(f'{kind}_temp_path {self.base}/{kind};' for kind in ['client_body','proxy','fastcgi','uwsgi','scgi'])
        conf=f'pid {self.base}/nginx.pid;error_log {self.base}/error.log;events {{worker_connections 64;}}http {{access_log off;{temporary}{zones}server {{listen 127.0.0.1:{self.port};{locations}location / {{return 404;}}}}}}'
        self.conf=self.base/'nginx.conf';self.conf.write_text(conf)
        check=subprocess.run([self.binary,'-p',str(self.base),'-c',str(self.conf),'-t'],capture_output=True,text=True)
        self.assertEqual(check.returncode,0,check.stdout+check.stderr)
        self.process=subprocess.Popen([self.binary,'-p',str(self.base),'-c',str(self.conf),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop)
        for _ in range(50):
            try:
                with socket.create_connection(('127.0.0.1',self.port),timeout=.1):return
            except OSError:time.sleep(.02)
        self.fail('nginx did not start')

    def stop(self):
        if self.process.poll() is None:self.process.terminate();self.process.wait(timeout=3)

    def request(self,path,method='GET'):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        try:
            connection.request(method,path);r=connection.getresponse();return r.status,dict(r.getheaders()),r.read()
        finally:connection.close()

    def test_only_exact_catalog_and_hash_files_are_readable(self):
        self.assertEqual(self.request('/nfqws-profiles/v1/catalog.json')[2],b'{"signed":"fixture"}')
        status,headers,body=self.request('/nfqws-profiles/v1/files/'+self.sha+'.json');self.assertEqual(status,200);self.assertEqual(body,b'{"profile":"fixture"}');self.assertIn('immutable',headers['Cache-Control'])
        self.assertEqual(self.request('/nfqws-profiles/v1/catalog.json','HEAD')[2],b'')
        self.assertEqual(self.request('/nfqws-profiles/v1/catalog.json','POST')[0],405)
        for path in ['/nfqws-profiles/','/nfqws-profiles/v1/files/','/nfqws-profiles/v1/files/../private-key.pem','/nfqws-profiles/v1/files/%2e%2e/%2e%2e/private-key.pem','/nfqws-profiles/v1/files/UNKNOWN.json']:
            with self.subTest(path=path):
                status,_,body=self.request(path);self.assertNotEqual(status,200);self.assertNotIn(b'PRIVATE_CANARY',body)

    def test_request_burst_is_limited_with_retry_after(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            results=list(ex.map(lambda _:self.request('/nfqws-profiles/v1/catalog.json'),range(40)))
        limited=[r for r in results if r[0]==429];self.assertTrue(limited,'burst must be limited');self.assertTrue(all(r[1].get('Retry-After') for r in limited))

    def test_symlinked_file_is_not_served(self):
        path=self.root/'files'/(self.sha+'.json');path.unlink();path.symlink_to(self.base/'private-key.pem')
        status,_,body=self.request('/nfqws-profiles/v1/files/'+self.sha+'.json');self.assertNotEqual(status,200);self.assertNotIn(b'PRIVATE_CANARY',body)
