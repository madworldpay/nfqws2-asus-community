"""Fixed control requests: exercise real PHP processes and local verified TLS."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import shlex
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

from test_dpi_normalize import PHP, PUBLIC


class DpiSiteCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.config = self.base / 'nfqws2.conf'
        self.config.write_text('MODE_AUTO="auto args"\nNFQWS_EXTRA_ARGS="$MODE_AUTO"\n')
        self.proc = self.base / 'proc'
        (self.proc / '123').mkdir(parents=True)
        (self.proc / '123/comm').write_text('nfqws2\n')
        for name in ['state', 'terminal']:
            (self.base / name).mkdir(mode=0o700)
        self.cert = self.base / 'cert.pem'
        self.key = self.base / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(self.key), '-out', str(self.cert), '-days', '1',
                        '-subj', '/CN=www.facebook.com', '-addext', 'subjectAltName=DNS:www.facebook.com'],
                       capture_output=True, check=True)

    def php(self, code, *args, timeout=15):
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(self.base), *map(str, args)],
                                capture_output=True, text=True, timeout=timeout)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def check(self, target='facebook-main', deadline=None):
        return self.php('''$file=$argv[1].'/dpi-site-check.php';
        if(!is_file($file)){echo json_encode(['error'=>'missing_implementation']);exit;}
        require $file;try {
          $deps=['config_path'=>$argv[2].'/nfqws2.conf','proc_root'=>$argv[2].'/proc',
            'worker_argv'=>fn($target)=>[$argv[3],'-n','-f',$argv[2].'/worker.php','--',$target]];
          if($argv[5]!=='')$deps['deadline_seconds']=(float)$argv[5];
          $s=new AsusDpiStore($argv[2].'/state',getmyuid());
          $g=new AsusDpiTerminalLifecycle($argv[2].'/terminal',getmyuid());
          echo json_encode((new AsusDpiSiteCheck($s,$g,$deps))->check($argv[4]));
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}''', PHP, target,
                        '' if deadline is None else deadline)

    def worker(self, port=None, addresses=None, before='', ca=None):
        # Only this trusted CLI fixture reroutes the pinned public destination
        # to a local TLS server. All validation, TLS options and reads are real.
        source = '''<?php require %s;file_put_contents(%s,(string)getmypid());%s
        $deps=['resolve'=>fn($host)=>%s,'ca'=>%s];
        %s
        echo json_encode((new AsusDpiSiteCheckProbe($deps))->run($argv[1]));'''
        opening = '' if port is None else '''$deps['open']=static function($url,$context){
          file_put_contents(%s,json_encode([$url,stream_context_get_options($context)]));
          return stream_socket_client('tls://127.0.0.1:%d',$errno,$error,3,STREAM_CLIENT_CONNECT,$context);
        };''' % (json.dumps(str(self.base / 'transport.json')), port)
        (self.base / 'worker.php').write_text(source % (
            json.dumps(str(PUBLIC / 'dpi-site-check.php')), json.dumps(str(self.base / 'worker.pid')),
            before, json.dumps(addresses if addresses is not None else ['93.184.216.34']),
            json.dumps(str(ca or self.cert)), opening))

    @contextlib.contextmanager
    def server(self, reply, delay=0, mutate=None):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(4)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert, self.key)
        seen = []
        def serve():
            try:
                conn, _ = listener.accept()
                with conn, context.wrap_socket(conn, server_side=True) as tls:
                    request = b''
                    while b'\r\n\r\n' not in request:
                        part = tls.recv(4096)
                        if not part:
                            return
                        request += part
                    seen.append(request)
                    if mutate:
                        mutate()
                    if delay:
                        time.sleep(delay)
                    tls.sendall(reply)
            except (OSError, ssl.SSLError):
                pass
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            yield listener.getsockname()[1], seen
        finally:
            listener.close()
            thread.join(timeout=.2)

    def test_exact_fields_and_fixed_targets_reject_url_or_execution_input(self):
        base = {'cmd': 'dpisitecheck', 'csrf_token': 'token', 'target': 'facebook-main'}
        for post in [base, base | {'target': 'discord-gateway'}]:
            self.assertEqual(self.validate(post), {'valid': True})
        for field in ['url', 'path', 'command', 'proxy', 'header', 'environment', 'resolver']:
            self.assertEqual(self.validate(base | {field: 'PRIVATE_CANARY'}), {'error': 'invalid_request'})
        for target in ['https://127.0.0.1/', 'facebook-main\n', '', ['facebook-main'], 1]:
            self.assertEqual(self.validate(base | {'target': target}), {'error': 'invalid_request'})
        for post in [base | {'cmd': 'other'}, base | {'csrf_token': []}, {'cmd': 'dpisitecheck'}]:
            self.assertEqual(self.validate(post), {'error': 'invalid_request'})

    def validate(self, post):
        return self.php('''$f=$argv[1].'/dpi-site-check.php';
        if(!is_file($f)){echo json_encode(['error'=>'missing_implementation']);exit;}
        require $f;try{AsusDpiSiteCheck::validate(json_decode($argv[3],true));
        echo json_encode(['valid'=>true]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}''', json.dumps(post))

    def test_http400_is_a_completed_error_response_and_never_full_service_success(self):
        with self.server(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 3\r\nConnection: close\r\n\r\nbad') as (port, seen):
            self.worker(port)
            value = self.check()
        self.assertEqual(value.get('type'), 'nfqws2_dpi_site_check', value)
        self.assertEqual(set(value), {'type', 'schema_version', 'target', 'url', 'started_at', 'finished_at',
                                     'context', 'response', 'full_service_verified', 'dns_scope'})
        self.assertEqual(value['schema_version'], 1)
        self.assertEqual(value['url'], 'https://www.facebook.com/')
        self.assertIs(value['full_service_verified'], False)
        self.assertEqual(value['dns_scope'], 'system_resolver')
        self.assertEqual(value['response'] | {'elapsed_ms': None}, {
            'outcome': 'response', 'http_status': 400, 'bytes_read': 3, 'body_limited': False,
            'redirect': None, 'elapsed_ms': None, 'error_code': None})
        self.assertGreaterEqual(value['response']['elapsed_ms'], 0)
        self.assertIsInstance(value['started_at'], int)
        self.assertGreaterEqual(value['finished_at'], value['started_at'])
        self.assertEqual(len(seen), 1)
        self.assertIn(b'Host: www.facebook.com\r\n', seen[0])
        options = json.loads((self.base / 'transport.json').read_text())
        self.assertEqual(options[0], 'tls://93.184.216.34:443')
        self.assertTrue(options[1]['ssl']['verify_peer'])
        self.assertTrue(options[1]['ssl']['verify_peer_name'])
        self.assertEqual(options[1]['ssl']['peer_name'], 'www.facebook.com')
        self.assertNotIn(b'Cookie:', seen[0])

    def test_redirect_is_bounded_information_and_is_never_followed(self):
        location = 'http://127.0.0.1/private?' + 'x' * 2100
        with self.server(('HTTP/1.1 302 Found\r\nLocation: ' + location + '\r\nContent-Length: 0\r\n\r\n').encode()) as (port, seen):
            self.worker(port)
            value = self.check()
        self.assertEqual(value.get('response', {}).get('http_status'), 302, value)
        self.assertEqual(value['response']['redirect'], location[:2048])
        self.assertEqual(len(seen), 1)

    def test_body_limit_and_chunk_decoding_count_only_body(self):
        for reply, size, outcome, limited in [
            (b'HTTP/1.1 200 OK\r\nContent-Length: 400000\r\n\r\n' + b'x' * 400000, 262144, 'read_limited', True),
            (b'HTTP/1.1 200 OK\r\nContent-Length: 262144\r\n\r\n' + b'x' * 262144, 262144, 'response', False),
            (b'HTTP/1.1 103 Early Hints\r\nLink: </ignored>\r\n\r\nHTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n', 5, 'response', False),
        ]:
            with self.subTest(size=size, outcome=outcome), self.server(reply) as (port, _):
                self.worker(port)
                value = self.check()
                response = value.get('response', {})
                self.assertEqual((response.get('bytes_read'), response.get('outcome'), response.get('body_limited')),
                                 (size, outcome, limited), value)

    def test_truncated_body_is_connection_error_not_completed_response(self):
        with self.server(b'HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nab') as (port, _):
            self.worker(port)
            value = self.check()
        self.assertEqual(value.get('response', {}).get('outcome'), 'connection_error', value)
        self.assertEqual(value['response']['http_status'], 200)
        self.assertEqual(value['response']['bytes_read'], 2)
        self.assertEqual(value['response']['error_code'], 'incomplete_body')

    def test_tls_host_and_trust_errors_are_not_http_responses(self):
        for target, ca in [('discord-main', self.cert), ('facebook-main', self.base / 'missing-ca')]:
            with self.subTest(target=target), self.server(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n') as (port, seen):
                self.worker(port, ca=ca)
                value = self.check(target)
                self.assertEqual(value.get('response', {}).get('outcome'), 'tls_error', value)
                self.assertIsNone(value['response']['http_status'])
                self.assertEqual(seen, [])

    def test_private_or_mixed_dns_answers_never_open_a_connection(self):
        for address in ['0.0.0.0', '10.0.0.1', '100.64.0.1', '127.0.0.1', '169.254.1.1', '172.16.0.1',
                        '192.0.0.1', '192.0.2.1', '192.168.1.1', '198.18.0.1', '198.51.100.1',
                        '203.0.113.1', '224.0.0.1', '240.0.0.1', '255.255.255.255', '::1', '127.1']:
            with self.subTest(address=address):
                self.worker(addresses=['93.184.216.34', address])
                value = self.check()
                self.assertEqual(value.get('response', {}).get('outcome'), 'blocked_address', value)
                self.assertFalse((self.base / 'transport.json').exists())

    def test_empty_dns_and_refused_connection_are_honest_errors(self):
        self.worker(addresses=[])
        value = self.check()
        self.assertEqual(value.get('response', {}).get('outcome'), 'connection_error', value)
        self.assertEqual(value['response']['error_code'], 'dns_failed')
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.close()
        self.worker(port)
        self.assertEqual(self.check().get('response', {}).get('outcome'), 'connection_error')

    def test_context_records_real_before_after_and_hash_without_executing_config(self):
        before = self.config.read_bytes()
        after = b'NFQWS_EXTRA_ARGS="$MODE_LIST"\n# changed\n'
        def change():
            self.config.write_bytes(after)
            (self.proc / '123/comm').write_text('another-service\n')
        with self.server(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n', mutate=change) as (port, _):
            self.worker(port)
            value = self.check()
        self.assertEqual(value.get('context'), {
            'before': {'nfqws': 'running', 'mode': 'auto', 'config_sha256': hashlib.sha256(before).hexdigest()},
            'after': {'nfqws': 'stopped', 'mode': 'list', 'config_sha256': hashlib.sha256(after).hexdigest()},
            'changed': True}, value)
        for text in ['NFQWS_EXTRA_ARGS="$MODE_ALL"\nNFQWS_EXTRA_ARGS="$MODE_AUTO"\n',
                     'NFQWS_ARGS="abc\nNFQWS_EXTRA_ARGS=\\"$MODE_ALL\\"\n"\n',
                     'NFQWS_EXTRA_ARGS="$(touch ' + str(self.base / 'executed') + ')"\n',
                     "NFQWS_EXTRA_ARGS='$MODE_AUTO'\n"]:
            self.config.write_text(text)
            self.worker(addresses=[])
            value = self.check()
            self.assertEqual(value.get('context', {}).get('before', {}).get('mode'), 'unknown', value)
            self.assertIsNone(value['context']['changed'])
            self.assertFalse((self.base / 'executed').exists())

    def test_missing_context_is_unknown_and_equal_known_context_is_stable(self):
        self.worker(addresses=[])
        self.assertIs(self.check().get('context', {}).get('changed'), False)
        self.config.unlink()
        (self.proc / '123/comm').unlink()
        (self.proc / '123').rmdir()
        self.proc.rmdir()
        value = self.check()
        self.assertEqual(value.get('context', {}).get('before'), {'nfqws': 'unknown', 'mode': 'unknown', 'config_sha256': None})
        self.assertIsNone(value['context']['changed'])

    def test_detector_admission_and_terminal_broker_are_busy_without_worker(self):
        for name in ['state/mutation.lock', 'terminal/control.lock', 'terminal/broker.lock']:
            with self.subTest(name=name):
                path = self.base / name
                with path.open('w') as lock:
                    path.chmod(0o600)
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    self.assertEqual(self.check(), {'error': 'busy'})
                    self.assertFalse((self.base / 'worker.pid').exists())
        self.php('''require $argv[1].'/dpi-store.php';
        (new AsusDpiStore($argv[2].'/state',getmyuid()))->reserve('11111111-1111-4111-8111-111111111111','run',[]);
        echo '{}';''')
        self.assertEqual(self.check(), {'error': 'busy'})
        self.assertFalse((self.base / 'worker.pid').exists())

    def test_dns_is_inside_ten_second_wall_deadline_and_only_owned_child_is_reaped(self):
        self.worker(before="$slow=function($host){sleep(20);return ['93.184.216.34'];};",
                    addresses=[])
        path = self.base / 'worker.php'
        path.write_text(path.read_text().replace("'resolve'=>fn($host)=>[]", "'resolve'=>$slow"))
        canary = subprocess.Popen(['sleep', '20'])
        self.addCleanup(lambda: (canary.terminate(), canary.wait()) if canary.poll() is None else None)
        started = time.monotonic()
        value = self.check()
        elapsed = time.monotonic() - started
        self.assertEqual(value.get('response', {}).get('outcome'), 'timeout', value)
        self.assertGreaterEqual(elapsed, 9.5)
        self.assertLess(elapsed, 10.8)
        self.assertIsNone(canary.poll())
        child = int((self.base / 'worker.pid').read_text())
        self.assertFalse(Path(f'/proc/{child}').exists(), 'owned child was not reaped')

    def test_network_wait_is_bounded_and_late_output_cannot_be_used(self):
        with self.server(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n', delay=2) as (port, _):
            self.worker(port)
            started = time.monotonic()
            value = self.check(deadline=.25)
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(value.get('response', {}).get('outcome'), 'timeout', value)
        child = int((self.base / 'worker.pid').read_text())
        self.assertFalse(Path(f'/proc/{child}').exists())

    def test_bad_or_unbounded_child_output_fails_closed(self):
        for body in ["echo '{bad';", "echo str_repeat('x',100000);", "echo json_encode(['outcome'=>'response','http_status'=>999]);"]:
            (self.base / 'worker.php').write_text('<?php ' + body)
            value = self.check()
            self.assertEqual(value.get('response', {}).get('outcome'), 'unavailable', value)
            self.assertIsNone(value['response']['http_status'])

    def test_chunk_truncation_and_ambiguous_http_framing_are_not_complete_responses(self):
        for reply in [b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n',
                      b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 3\r\n\r\nabc',
                      b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n']:
            with self.subTest(reply=reply), self.server(reply) as (port, _):
                self.worker(port)
                value = self.check()
                self.assertEqual(value.get('response', {}).get('outcome'), 'connection_error', value)

    def test_child_inherits_no_proxy_cookie_or_http_activation_environment(self):
        dest = self.base / 'environment.json'
        before = 'file_put_contents(%s,json_encode(getenv()));' % json.dumps(str(dest))
        self.worker(addresses=[], before=before)
        old = os.environ.get('HTTPS_PROXY')
        os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:1/PRIVATE_CANARY'
        try:
            value = self.check()
        finally:
            if old is None:
                os.environ.pop('HTTPS_PROXY', None)
            else:
                os.environ['HTTPS_PROXY'] = old
        self.assertEqual(value.get('response', {}).get('error_code'), 'dns_failed', value)
        environment = json.loads(dest.read_text())
        for key in ['HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy',
                    'REQUEST_METHOD', 'REMOTE_ADDR', 'HTTP_COOKIE', 'QUERY_STRING']:
            self.assertNotIn(key, environment)

    def test_cli_worker_entry_accepts_only_fixed_arguments_and_refuses_http_context(self):
        file = PUBLIC / 'dpi-site-check.php'
        clean = {'PATH': '/usr/bin:/bin', 'HOME': '/', 'LANG': 'C'}
        for extra in [{'REQUEST_METHOD': 'GET'}, {'REMOTE_ADDR': '127.0.0.1'}]:
            result = subprocess.run([PHP, '-n', '-f', str(file), '--', '--worker', 'facebook-main'],
                                    env=clean | extra, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stdout, '')
        result = subprocess.run([PHP, '-n', '-f', str(file), '--', '--worker', 'https://127.0.0.1/'],
                                env=clean, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)

    def test_default_worker_overrides_disabled_cgi_argv(self):
        cgi = os.environ.get('PHP_CGI_TEST_BINARY')
        if not cgi:
            self.skipTest('matching PHP CGI runtime required')
        wrapper = self.base / 'php-cgi'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(cgi) + ' -n -d register_argc_argv=0 "$@"\n')
        wrapper.chmod(0o700)
        public = self.base / 'public'
        public.mkdir()
        for source in PUBLIC.glob('*.php'):
            (public / source.name).write_bytes(source.read_bytes())
        file = public / 'dpi-site-check.php'
        file.write_text(file.read_text().replace("NfqwsPlatform::translate('/opt/bin/php-cgi')", json.dumps(str(wrapper))))
        value = self.php('''require $argv[2].'/public/dpi-site-check.php';
          $store=new AsusDpiStore($argv[2].'/state',getmyuid());
          $terminal=new AsusDpiTerminalLifecycle($argv[2].'/terminal',getmyuid());
          echo json_encode((new AsusDpiSiteCheck($store,$terminal,
            ['config_path'=>$argv[2].'/nfqws2.conf','proc_root'=>$argv[2].'/proc']))->check('facebook-main'));''')
        self.assertEqual(value['response']['outcome'], 'unavailable', value)
        self.assertEqual(value['response']['error_code'], 'https_unavailable', value)

    def test_real_cgi_worker_flags_and_http_refusal(self):
        cgi = os.environ.get('PHP_CGI_TEST_BINARY')
        if not cgi:
            self.skipTest('matching PHP CGI runtime required')
        clean = {'PATH': '/usr/bin:/bin', 'HOME': '/', 'LANG': 'C'}
        file = PUBLIC / 'dpi-site-check.php'
        result = subprocess.run([cgi, '-n', '-q', '-f', str(file), '--', '--worker', 'facebook-main'],
                                env=clean, capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stderr, '')
        self.assertIn(json.loads(result.stdout)['outcome'], ['unavailable', 'tls_error'])
        env = clean | {'REDIRECT_STATUS': '200', 'SCRIPT_FILENAME': str(file),
                       'REQUEST_METHOD': 'GET', 'QUERY_STRING': '--worker+facebook-main',
                       'REMOTE_ADDR': '127.0.0.1'}
        result = subprocess.run([cgi, '-n', '-q', '-f', str(file), '--', '--worker', 'facebook-main'],
                                env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        self.assertNotIn('http_status', result.stdout)


if __name__ == '__main__':
    unittest.main()
