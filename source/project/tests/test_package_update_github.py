import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_TLS_TEST_BINARY')
EXTENSION = os.environ.get('PHP_OPENSSL_TEST_EXTENSION')
METADATA = 'https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/updates/v2/public.json'
NATIVE_METADATA = 'https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/updates/v2/openwrt/public.json'
RELEASES = 'https://github.com/madworldpay/nfqws2-asus-community/releases/download/'
ASSET_HOST = 'release-assets.githubusercontent.com'


class PublicHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):pass
    def do_GET(self):
        self.server.seen.append((self.path, dict(self.headers)))
        status, raw, headers = self.server.responses.get(self.path, (404, b'', {}))
        self.send_response(status)
        for key, value in headers.items():self.send_header(key, value)
        if 'Content-Length' not in headers:self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        try:
            if self.server.stall:time.sleep(1)
            if self.server.drip:
                for byte in raw:
                    self.wfile.write(bytes([byte]));self.wfile.flush();time.sleep(0.08)
            else:self.wfile.write(raw)
        except (OSError, ssl.SSLError):pass


@unittest.skipUnless(PHP and EXTENSION, 'matching PHP/OpenSSL test runtime required')
class GithubUpdateTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certs = tempfile.TemporaryDirectory();p = Path(cls.certs.name)
        cls.cert = p/'cert.pem';cls.key = p/'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1',
                        '-keyout', str(cls.key), '-out', str(cls.cert)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.release_key = p/'release-key.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:3072', '-out', str(cls.release_key)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.release_public = subprocess.check_output(['openssl', 'pkey', '-in', str(cls.release_key), '-pubout']).decode()

    @classmethod
    def tearDownClass(cls):cls.certs.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base = Path(self.tmp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), PublicHandler);self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.cert, self.key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.server.seen = [];self.server.stall = False;self.server.drip = False
        self.origin = f'https://127.0.0.1:{self.server.server_port}'
        self.name = 'nfqws2-asus_1.3.1-asus6+b63_aarch64-3.10.ipk';self.body = b'public package bytes'
        self.release = '/releases/download/build63/'+self.name
        self.asset = '/github-production-release-asset/fixture/package?token=ONLY_IN_URL'
        self.manifest = b'{"release":"test", "exact":"bytes"}\n'
        self.signature = base64.b64encode(b's'*384).decode()
        self.envelope = {'manifest': base64.b64encode(self.manifest).decode(), 'signature': self.signature}
        self.server.responses = {'/updates/public.json': (200, json.dumps(self.envelope).encode(), {}),
                                 self.release: (302, b'', {'Location': self.origin+self.asset, 'Set-Cookie': 'PRIVATE_COOKIE=never_forward'}),
                                 self.asset: (200, self.body, {})}
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start();self.addCleanup(self.stop)
        self.app = self.base/'app';self.app.mkdir()
        for name in ['update-transport.php', 'update-github.php', 'update-manifest.php', 'dpi-store.php', 'dpi-options.php', 'support-json-schema.php', 'platform.php']:
            source = ROOT/'webui/web/public'/name
            if source.exists():shutil.copy2(source, self.app/name)
        (self.base/'resources').mkdir()
        shutil.copy2(ROOT/'updates/package-manifest.schema.json', self.base/'resources/package-manifest.schema.json')
        public = self.app/'update-github.php'
        if public.exists():
            raw = public.read_text().replace(METADATA, self.origin+'/updates/public.json').replace(RELEASES, self.origin+'/releases/download/')
            raw = raw.replace(NATIVE_METADATA,self.origin+'/updates/openwrt/public.json')
            raw = raw.replace("'"+ASSET_HOST+"'", "'127.0.0.1'").replace('private const HTTPS_PORT=443;', f'private const HTTPS_PORT={self.server.server_port};')
            public.write_text(raw)
        opt = self.base/'opt';(opt/'etc/nfqws-asus-web').mkdir(parents=True)
        store = self.app/'dpi-store.php';store.write_text(store.read_text().replace("string $alias='/opt'", 'string $alias='+json.dumps(str(opt))))
        self.config = opt/'etc/nfqws-asus-web/update-channel.json'

    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def call(self, action='manifest', package=None, config='default', ca=None, direct=False, platform='asus-entware'):
        package = package or {'filename': self.name, 'size': len(self.body), 'sha256': hashlib.sha256(self.body).hexdigest()}
        script = '''require $argv[1].'/update-transport.php';$p=json_decode(stream_get_contents(STDIN),true);
        try{$times=['metadata'=>0.4,'download'=>0.4];
        if($p['direct']){if(!class_exists('AsusGithubUpdateSource'))throw new RuntimeException('missing_public_transport');$t=new AsusGithubUpdateSource((int)$argv[2],$argv[3],$times,$p['platform']);}
        else $t=new AsusUpdateTransport($p['config']==='default'?null:$p['config'],(int)$argv[2],$argv[3],$times);
        if($p['action']==='construct')$v='ready';elseif($p['action']==='manifest')$v=$t->manifest();
        elseif($p['action']==='verify'){require $argv[1].'/update-manifest.php';$raw=$t->manifest();
            $verified=AsusPackageManifest::verify($raw['json'],$raw['signature'],$p['key']);
            $v=AsusPackageManifest::candidate($verified,'aarch64-3.10','1.3.1-asus6+b62');}
        else{$t->download($p['package'],$argv[4]);$v='downloaded';}
        echo json_encode(['value'=>$v]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        result = subprocess.run([PHP, '-n', '-d', 'extension='+EXTENSION, '-r', script,
                                 str(self.app), str(os.getuid()), str(ca or self.cert), str(self.base/'download.ipk')],
                                input=json.dumps({'action': action, 'package': package, 'config': config, 'direct': direct, 'key': self.release_public,'platform':platform}),
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr);self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def assert_no_credentials(self):
        for _, headers in self.server.seen:
            lowered = {k.lower(): v for k,v in headers.items()}
            self.assertNotIn('authorization', lowered);self.assertNotIn('cookie', lowered)
            self.assertEqual(lowered.get('accept-encoding'), 'identity')

    def test_missing_default_config_fetches_one_public_envelope_without_credentials(self):
        self.assertEqual(self.call(), {'value': {'json': self.manifest.decode(), 'signature': self.signature}})
        self.assertEqual([p for p, _ in self.server.seen], ['/updates/public.json']);self.assert_no_credentials()

    def test_public_source_implements_the_existing_interface(self):
        self.assertEqual(self.call(direct=True), {'value': {'json': self.manifest.decode(), 'signature': self.signature}})

    def test_native_discovery_uses_separate_public_identity_without_credentials(self):
        self.server.responses['/updates/openwrt/public.json']=(200,json.dumps(self.envelope).encode(),{})
        self.assertEqual(self.call(direct=True,platform='openwrt'),{'value':{'json':self.manifest.decode(),'signature':self.signature}})
        self.assertEqual([p for p,_ in self.server.seen],['/updates/openwrt/public.json']);self.assert_no_credentials()

    def test_native_packages_use_signed_build_tag_and_never_download_entware(self):
        for name in ['nfqws2-native_1.3.2-r72_x86_64.apk','nfqws2-native_1.3.2-72_arm_cortex-a9.ipk']:
            self.server.responses['/releases/download/build72/'+name]=(302,b'',{'Location':self.origin+self.asset})
            package={'filename':name,'size':len(self.body),'sha256':hashlib.sha256(self.body).hexdigest()}
            self.assertEqual(self.call('download',package=package,direct=True,platform='openwrt'),{'value':'downloaded'})
            self.assert_no_credentials();self.server.seen.clear();(self.base/'download.ipk').unlink()
        for name in ['nfqws2-native_1.3.2-r72_x86_64.ipk','nfqws2-native_1.3.2-72_x86_64.apk']:
            package={'filename':name,'size':len(self.body),'sha256':hashlib.sha256(self.body).hexdigest()}
            self.assertEqual(self.call('download',package=package,direct=True,platform='openwrt'),{'error':'invalid_manifest'})
        self.assertEqual(self.call('download',direct=True,platform='openwrt'),{'error':'invalid_manifest'})
        self.assertEqual(self.server.seen,[])

    def test_unknown_platform_cannot_select_a_download_origin(self):
        self.assertEqual(self.call(direct=True,platform='custom'),{'error':'invalid_channel'})
        self.assertEqual(self.server.seen,[])

    def test_public_envelope_still_requires_pinned_manifest_signature_verification(self):
        value = {'schema_version': 1, 'package_version': '1.3.1-asus6+b63', 'core_version': '1.3.1-asus6',
                 'web_version': '0.1.4', 'build': 63, 'notes': 'public transport',
                 'packages': [{'family': 'aarch64-3.10', 'filename': self.name, 'size': len(self.body),
                               'sha256': hashlib.sha256(self.body).hexdigest()}]}
        raw = json.dumps(value).encode()+b'\n'
        signature = subprocess.check_output(['openssl', 'dgst', '-sha256', '-sign', str(self.release_key)], input=raw)
        self.envelope = {'manifest': base64.b64encode(raw).decode(), 'signature': base64.b64encode(signature).decode()}
        self.server.responses['/updates/public.json'] = (200, json.dumps(self.envelope).encode(), {})
        candidate = self.call('verify')['value']
        self.assertEqual(candidate['build'], 63);self.assertEqual(candidate['revision'], hashlib.sha256(raw).hexdigest())
        self.envelope['manifest'] = base64.b64encode(raw+b' ').decode()
        self.server.responses['/updates/public.json'] = (200, json.dumps(self.envelope).encode(), {})
        self.assertEqual(self.call('verify'), {'error': 'invalid_signature'})

    def test_missing_explicit_config_never_uses_public_channel(self):
        self.assertEqual(self.call(config=str(self.config)), {'error': 'channel_unconfigured'});self.assertEqual(self.server.seen, [])

    def test_bad_existing_default_private_configuration_never_falls_back(self):
        self.config.write_text('{"origin":"https://private.invalid","token":"BAD"}');self.config.chmod(0o600)
        self.assertEqual(self.call(), {'error': 'invalid_channel'});self.assertEqual(self.server.seen, [])
        self.config.chmod(0o644)
        self.assertEqual(self.call(), {'error': 'invalid_channel'});self.assertEqual(self.server.seen, [])
        self.config.unlink();self.config.symlink_to(self.base/'missing-channel')
        self.assertEqual(self.call(), {'error': 'invalid_channel'});self.assertEqual(self.server.seen, [])

    def test_existing_private_configuration_retains_private_flow(self):
        self.config.write_text(json.dumps({'origin': self.origin, 'token': 'T'*43}));self.config.chmod(0o600)
        self.server.responses['/nfqws-updates/v1/manifest.json'] = (200, self.manifest, {})
        self.server.responses['/nfqws-updates/v1/manifest.sig'] = (200, self.signature.encode(), {})
        self.assertIn('value', self.call());self.assertEqual(len(self.server.seen), 2)
        for _, headers in self.server.seen:self.assertEqual(headers.get('Authorization'), 'Bearer '+'T'*43)
        self.assertEqual(self.server.seen[1][1].get('If-Match'), '"'+hashlib.sha256(self.manifest).hexdigest()+'"')

    def test_public_download_derives_release_tag_and_streams_verified_bytes(self):
        self.assertEqual(self.call('download'), {'value': 'downloaded'})
        target = self.base/'download.ipk';self.assertEqual(target.read_bytes(), self.body);self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual([p for p, _ in self.server.seen], [self.release, self.asset]);self.assert_no_credentials()

    def test_armv7_package_uses_its_exact_candidate_filename(self):
        name = self.name.replace('aarch64-3.10', 'armv7');path = '/releases/download/build63/'+name
        self.server.responses[path] = (200, self.body, {})
        package = {'filename': name, 'size': len(self.body), 'sha256': hashlib.sha256(self.body).hexdigest()}
        self.assertEqual(self.call('download', package), {'value': 'downloaded'});self.assertEqual(self.server.seen[0][0], path)

    def test_unsafe_filename_and_build_values_fail_before_network_io(self):
        for name in ['https://other.invalid/a.ipk', self.name.replace('+b63', '+b063'), self.name.replace('+b63', '+b2147483648'), self.name.replace('1.3.1', '01.3.1'), self.name.replace('+b63', '+b0'), self.name+'?x=1']:
            with self.subTest(name=name):
                package = {'filename': name, 'size': len(self.body), 'sha256': hashlib.sha256(self.body).hexdigest()}
                self.assertEqual(self.call('download', package), {'error': 'invalid_manifest'})
        self.assertEqual(self.server.seen, [])

    def test_bad_envelopes_are_rejected_without_exposing_body(self):
        variants = [b'not json', b'[]', b'{"manifest":"e30=","manifest":"e30=","signature":"x"}',
                    json.dumps(dict(self.envelope, extra='x')).encode(),
                    json.dumps(dict(self.envelope, manifest=self.envelope['manifest']+'\n')).encode(),
                    json.dumps(dict(self.envelope, manifest=base64.b64encode(b'x'*32769).decode())).encode(),
                    json.dumps(dict(self.envelope, manifest='')).encode(),
                    json.dumps(dict(self.envelope, signature=base64.b64encode(b's'*383).decode())).encode(),
                    json.dumps(dict(self.envelope, signature=self.signature+'\n')).encode()]
        for raw in variants:
            with self.subTest(raw=raw[:60]):
                self.server.responses['/updates/public.json'] = (200, raw, {})
                self.assertIn(self.call().get('error'), ['invalid_manifest', 'invalid_signature', 'download_size'])

    def test_signed_manifest_size_boundary_preserves_exact_bytes(self):
        for size in [1, 32768]:
            self.envelope['manifest'] = base64.b64encode(b'x'*size).decode()
            self.server.responses['/updates/public.json'] = (200, json.dumps(self.envelope).encode(), {})
            self.assertEqual(self.call()['value']['json'], 'x'*size)

    def test_metadata_redirect_and_compressed_response_are_rejected(self):
        self.server.responses['/updates/public.json'] = (302, b'', {'Location': self.origin+self.asset})
        self.assertEqual(self.call(), {'error': 'download_redirect'});self.assertEqual(len(self.server.seen), 1)
        self.server.responses['/updates/public.json'] = (200, json.dumps(self.envelope).encode(), {'Content-Encoding': 'gzip'})
        self.assertEqual(self.call(), {'error': 'download_size'})

    def test_redirects_outside_asset_allowlist_are_rejected_without_request(self):
        invalid = ['https://other.invalid/github-production-release-asset/x',
                   self.origin+'/other/path', self.origin+'/github-production-release-asset/../private',
                   self.origin+'/github-production-release-asset/%2e%2e/private',
                   self.origin+'/github-production-release-asset/x#fragment',
                   self.origin.replace('https://', 'http://')+'/github-production-release-asset/x',
                   self.origin.replace('https://', 'https://user:pass@')+'/github-production-release-asset/x',
                   '//127.0.0.1/github-production-release-asset/x',
                   'https://127.0.0.1:1/github-production-release-asset/x']
        for url in invalid:
            with self.subTest(url=url):
                self.server.seen.clear();self.server.responses[self.release] = (302, b'', {'Location': url})
                self.assertEqual(self.call('download'), {'error': 'download_redirect'})
                self.assertEqual(len(self.server.seen), 1);self.assertFalse((self.base/'download.ipk').exists())

    def test_at_most_three_asset_redirects_are_followed(self):
        a, b, c = ['/github-production-release-asset/fixture/'+n for n in ['a', 'b', 'c']]
        self.server.responses[self.release] = (302, b'', {'Location': self.origin+a})
        self.server.responses[a] = (307, b'', {'Location': self.origin+b})
        self.server.responses[b] = (308, b'', {'Location': self.origin+c})
        self.server.responses[c] = (200, self.body, {})
        self.assertEqual(self.call('download'), {'value': 'downloaded'});self.assertEqual(len(self.server.seen), 4)
        (self.base/'download.ipk').unlink();self.server.seen.clear()
        self.server.responses[c] = (302, b'', {'Location': self.origin+self.asset})
        self.assertEqual(self.call('download'), {'error': 'download_redirect'});self.assertEqual(len(self.server.seen), 4)
        self.assertFalse((self.base/'download.ipk').exists());self.assert_no_credentials()

    def test_short_long_wrong_hash_or_encoded_download_is_removed(self):
        for body, headers in [(b'short', {}), (self.body+b'long', {}), (b'X'*len(self.body), {}), (self.body, {'Content-Encoding': 'gzip'}), (self.body, {'Content-Length': str(len(self.body)+1)})]:
            with self.subTest(body=body, headers=headers):
                self.server.responses[self.asset] = (200, body, headers)
                self.assertIn(self.call('download').get('error'), ['download_size', 'download_hash'])
                self.assertFalse((self.base/'download.ipk').exists())

    def test_existing_or_non_private_destination_is_never_overwritten(self):
        target = self.base/'download.ipk';target.write_bytes(b'KEEP')
        self.assertEqual(self.call('download'), {'error': 'invalid_state'});self.assertEqual(target.read_bytes(), b'KEEP')
        target.unlink();outside = self.base/'outside';outside.write_bytes(b'KEEP');target.symlink_to(outside)
        self.assertEqual(self.call('download'), {'error': 'invalid_state'});self.assertTrue(target.is_symlink());self.assertEqual(outside.read_bytes(), b'KEEP')
        target.unlink();self.base.chmod(0o755)
        self.assertEqual(self.call('download'), {'error': 'invalid_state'});self.assertEqual(self.server.seen, [])

    def test_tls_verification_rejects_missing_ca_and_wrong_hostname(self):
        self.assertEqual(self.call(ca='/nonexistent/ca.pem'), {'error': 'https_unavailable'})
        public = self.app/'update-github.php';public.write_text(public.read_text().replace(self.origin+'/updates/public.json', self.origin.replace('127.0.0.1', 'localhost')+'/updates/public.json'))
        self.assertEqual(self.call(), {'error': 'download_failed'});self.assertEqual(self.server.seen, [])

    def test_stalled_metadata_and_download_deadlines_remove_partial_file(self):
        self.server.stall = True
        for action in ['manifest', 'download']:
            started = time.monotonic();result = self.call(action)
            self.assertIn(result.get('error'), ['timed_out', 'download_failed']);self.assertLess(time.monotonic()-started, 1.5)
            self.assertFalse((self.base/'download.ipk').exists())

    def test_trickled_metadata_honors_total_deadline(self):
        self.server.drip = True;started = time.monotonic()
        self.assertIn(self.call().get('error'), ['timed_out', 'download_failed']);self.assertLess(time.monotonic()-started, 1.5)


if __name__ == '__main__':unittest.main()
