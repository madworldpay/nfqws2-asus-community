import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_TLS_TEST_BINARY')
EXTENSION = os.environ.get('PHP_OPENSSL_TEST_EXTENSION')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):pass
    def do_GET(self):
        self.server.seen.append((self.path, self.headers.get('Authorization'), self.headers.get('If-Match')))
        route = self.path.rsplit('/', 1)[1]
        status, raw, headers = self.server.responses.get(route, (404, b'', {}))
        self.send_response(status)
        for key, value in headers.items():self.send_header(key, value)
        if 'Content-Length' not in headers:self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        if self.server.stall:time.sleep(1)
        try:self.wfile.write(raw)
        except (OSError, ssl.SSLError):pass


@unittest.skipUnless(PHP and EXTENSION, 'matching PHP/OpenSSL test runtime required')
class PackageUpdateTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certs = tempfile.TemporaryDirectory();p = Path(cls.certs.name)
        cls.cert = p/'cert.pem';cls.key = p/'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1',
                        '-keyout', str(cls.key), '-out', str(cls.cert)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls):cls.certs.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler);self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.cert, self.key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.server.seen = [];self.server.stall = False
        self.body = b'package bytes'
        self.name = 'nfqws2-asus_1.3.1-asus6+b11_aarch64-3.10.ipk'
        self.server.responses = {'manifest.json': (200, b'{"release":"test"}', {}),
                                 'manifest.sig': (200, base64.b64encode(b's'*384), {}),
                                 self.name: (200, self.body, {})}
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.config = self.base/'channel.json'
        self.config.write_text(json.dumps({'origin': f'https://127.0.0.1:{self.server.server_port}', 'token': 'T'*43}));self.config.chmod(0o600)

    def test_default_channel_filename_uses_canonical_opt_directory(self):
        opt=self.base/'opt';folder=opt/'etc/nfqws-asus-web';folder.mkdir(parents=True)
        shutil.copy2(self.config,folder/'update-channel.json');alias=self.base/'opt-alias';alias.symlink_to(opt,target_is_directory=True)
        app=self.base/'app';shutil.copytree(ROOT/'webui/web/public',app)
        p=app/'dpi-store.php';p.write_text(p.read_text().replace("string $alias='/opt'","string $alias="+json.dumps(str(alias))))
        code="require $argv[1].'/update-transport.php';try{new AsusUpdateTransport(null,(int)$argv[2]);echo json_encode(['ready'=>true]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        r=subprocess.run([PHP,'-n','-r',code,str(app),str(os.getuid())],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),{'ready':True});self.assertEqual(self.server.seen,[])

    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def call(self, action='manifest', package=None, ca=None):
        script = '''if(!is_file($argv[1])){echo json_encode(['error'=>'missing_transport']);exit;}
        require $argv[1];$p=json_decode(stream_get_contents(STDIN),true);
        try{$t=new AsusUpdateTransport($argv[2],(int)$argv[3],$argv[4],['metadata'=>0.4,'download'=>0.4]);
        if($p['action']==='manifest')$v=$t->manifest();else{$t->download($p['package'],$argv[5]);$v='downloaded';}
        echo json_encode(['value'=>$v]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        package = package or {'filename': self.name, 'size': len(self.body), 'sha256': hashlib.sha256(self.body).hexdigest()}
        r = subprocess.run([PHP, '-n', '-d', 'extension='+EXTENSION, '-r', script,
                            str(ROOT/'webui/web/public/update-transport.php'), str(self.config), str(os.getuid()),
                            str(ca or self.cert), str(self.base/'download.ipk')],
                           input=json.dumps({'action': action, 'package': package}), capture_output=True, text=True, timeout=5)
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr);self.assertEqual(r.stderr, '')
        return json.loads(r.stdout)

    def test_manifest_uses_private_header_and_binds_signature_revision(self):
        result = self.call()
        self.assertEqual(result['value']['json'], '{"release":"test"}')
        self.assertEqual(result['value']['signature'], base64.b64encode(b's'*384).decode())
        self.assertEqual(self.server.seen[0][1], 'Bearer '+'T'*43)
        revision = hashlib.sha256(b'{"release":"test"}').hexdigest()
        self.assertEqual(self.server.seen[1][2], '"'+revision+'"')
        self.assertNotIn('T'*43, json.dumps(result))

    def test_stream_download_checks_exact_bytes_and_hash(self):
        self.assertEqual(self.call('download'), {'value': 'downloaded'})
        target = self.base/'download.ipk'
        self.assertEqual(target.read_bytes(), self.body);self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_short_long_or_wrong_hash_download_is_removed(self):
        for body in [b'short', self.body+b'long', b'X'*len(self.body)]:
            self.server.responses[self.name] = (200, body, {})
            self.assertIn(self.call('download')['error'], ['download_size', 'download_hash'])
            self.assertFalse((self.base/'download.ipk').exists())

    def test_existing_destination_and_symlink_are_never_deleted(self):
        target = self.base/'download.ipk';target.write_text('KEEP')
        self.assertEqual(self.call('download'), {'error': 'invalid_state'});self.assertEqual(target.read_text(), 'KEEP')
        target.unlink();outside = self.base/'outside';outside.write_text('KEEP');target.symlink_to(outside)
        self.assertEqual(self.call('download'), {'error': 'invalid_state'});self.assertTrue(target.is_symlink());self.assertEqual(outside.read_text(), 'KEEP')

    def test_redirect_auth_error_and_untrusted_ca_never_leak_token(self):
        for code in [302, 403]:
            self.server.responses['manifest.json'] = (code, b'TOKEN_CANARY', {'Location': 'https://other.invalid/'})
            result = self.call();self.assertIn('error', result);self.assertNotIn('T'*43, json.dumps(result));self.assertNotIn('TOKEN_CANARY', json.dumps(result))
        self.assertIn('error', self.call(ca='/nonexistent/ca.pem'))

    def test_missing_or_unsafe_config_never_makes_a_request(self):
        self.config.chmod(0o644)
        self.assertEqual(self.call(), {'error': 'invalid_channel'});self.assertEqual(self.server.seen, [])
        self.config.unlink()
        self.assertEqual(self.call(), {'error': 'channel_unconfigured'})

    def test_browser_style_url_in_filename_and_origin_injection_are_rejected(self):
        self.assertEqual(self.call('download', {'filename': 'https://other.invalid/file.ipk', 'size': 1, 'sha256': '0'*64}), {'error': 'invalid_manifest'})
        self.assertEqual(self.server.seen, [])
        value=json.loads(self.config.read_text());value['origin']='https://user:pass@127.0.0.1/other';self.config.write_text(json.dumps(value))
        self.assertEqual(self.call(), {'error': 'invalid_channel'});self.assertEqual(self.server.seen, [])

    def test_stalled_response_is_bounded_and_is_not_current(self):
        self.server.stall = True
        started = time.monotonic();result = self.call()
        self.assertIn(result.get('error'), ['timed_out', 'download_failed'])
        self.assertLess(time.monotonic()-started, 1.5)


if __name__ == '__main__':unittest.main()
