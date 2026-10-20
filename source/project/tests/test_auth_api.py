"""Exercise authorization and password changes across real PHP requests."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_TEST_BINARY') or shutil.which('php')


@unittest.skipUnless(PHP, 'optional PHP CLI interpreter not supplied')
class PasswordApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.auth = self.base / 'auth.json'
        self.sessions = {}
        # Update lease behavior is exercised independently with real processes;
        # these HTTP fixtures substitute only its local admission boundary.
        (self.base/'update-guard.php').write_text('''<?php
        class AsusUpdateStore {}
        class AsusUpdateGuard { function __construct($s){} function mutationLease(){
          if(is_file(__DIR__.'/update-busy'))throw new RuntimeException('busy');
          $f=fopen(__DIR__.'/http-mutation.lock','c+');flock($f,LOCK_SH);return $f;
        }}''')
        for name in ['index.php', 'asus.php', 'ark.php']:
            source = (ROOT / 'webui/web/public' / name).read_text()
            for original, replacement in [('/opt/etc/nfqws-asus-web/auth.json', self.auth),
                                          ('/etc/passwd', self.base / 'passwd'),
                                          ('/etc/shadow', self.base / 'shadow')]:
                source = source.replace(original, str(replacement))
            (self.base / name).write_text(source)
        default = ROOT / 'asus/web-auth.json'
        if default.exists():
            shutil.copyfile(default, self.auth)
        result = subprocess.run([PHP, '-n', '-r',
                                 "echo crypt('router-password', '$6$nfqws-test$');"],
                                text=True, capture_output=True, check=True)
        (self.base / 'passwd').write_text(f'admin:{result.stdout}:0:0::/:/bin/sh\n')

    def request(self, params, session='user-one'):
        script = '''
        ini_set('session.save_path', $argv[1]);
        session_name('nfqws_asus_session');
        session_id($argv[2]);
        session_start();
        session_write_close();
        $_SERVER['REQUEST_METHOD'] = 'POST';
        $_POST = json_decode($argv[3], true);
        register_shutdown_function(function () {
            echo '\\nHTTP_META=' . json_encode(['code' => http_response_code(), 'session' => session_id()]);
        });
        require $argv[1] . '/index.php';
        '''
        result = subprocess.run([PHP, '-n', '-r', script, str(self.base),
                                 self.sessions.get(session, session), json.dumps(params)],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        body, meta = result.stdout.rsplit('\\nHTTP_META=', 1)
        meta = json.loads(meta)
        self.sessions[session] = meta['session'] or session
        return int(meta['code']), json.loads(body) if body else None

    def login(self, session='user-one', password='router-password', user='admin'):
        code, data = self.request({'cmd': 'login', 'user': user,
                                   'password': password}, session)
        self.assertEqual(code, 200)
        self.assertEqual(data['status'], 0)
        return data['csrf_token']

    def change(self, password, token, session='user-one', confirmation=None):
        return self.request({'cmd': 'password', 'password': password,
                             'confirmation': password if confirmation is None else confirmation,
                             'csrf_token': token}, session)

    def test_password_change_requires_login_and_csrf_and_revokes_other_sessions(self):
        self.assertEqual(self.change('new', 'anything')[0], 401)
        token = self.login()
        self.login('user-two')
        before = self.auth.read_bytes()
        self.assertEqual(self.change('new', 'invalid')[0], 403)
        self.assertEqual(self.change('new', token, confirmation='different')[0], 400)
        self.assertEqual(self.auth.read_bytes(), before)
        self.assertEqual(self.change('new', token)[0], 200)
        self.assertEqual(self.request({'cmd': 'filenames'}, 'user-two')[0], 401)
        self.assertEqual(self.request({'cmd': 'filenames'})[0], 200)
        self.assertEqual(self.request({'cmd': 'login', 'user': 'admin',
                                       'password': 'router-password'}, 'fresh')[0], 401)
        self.login('fresh', 'new')

    def test_empty_password_opens_panel_and_can_be_protected_again(self):
        token = self.login()
        self.assertEqual(self.change('', token)[0], 200)
        code, data = self.request({'cmd': 'login'}, 'anonymous')
        self.assertEqual(code, 200)
        self.assertEqual(self.request({'cmd': 'filenames'}, 'visitor')[0], 200)
        self.assertEqual(self.change('back', data['csrf_token'], 'anonymous')[0], 200)
        self.assertEqual(self.request({'cmd': 'filenames'}, 'visitor')[0], 401)
        self.login('new-user', 'back')

    def test_router_preparation_and_restore_require_login_and_csrf(self):
        for command in ['arkprepare', 'arkrestore']:
            params = {'cmd': command, 'revision': 'stale', 'csrf_token': 'wrong'}
            self.assertEqual(self.request(params, 'visitor')[0], 401)
        self.login()
        for command in ['arkprepare', 'arkrestore']:
            self.assertEqual(self.request({'cmd': command, 'revision': 'stale',
                                           'csrf_token': 'wrong'})[0], 403)
            self.assertEqual(self.request({'cmd': command})[0], 400)

    def test_fallback_is_used_only_when_router_credentials_unavailable(self):
        self.assertEqual(self.request({'cmd': 'login', 'user': 'root',
                                       'password': 'asus'})[0], 401)
        (self.base / 'passwd').unlink()
        self.login(user='root', password='asus')

    def test_invalid_password_request_preserves_credentials(self):
        token = self.login()
        before = self.auth.read_bytes()
        for params in [{'password': ['bad']}, {'password': 'a\0b', 'confirmation': 'a\0b'},
                       {'password': 'a' * 73, 'confirmation': 'a' * 73},
                       {'csrf_token': ['bad']}]:
            data = {'cmd': 'password', 'password': 'new', 'confirmation': 'new', 'csrf_token': token}
            data.update(params)
            self.assertEqual(self.request(data)[0], 400)
            self.assertEqual(self.auth.read_bytes(), before)

    def test_corrupt_or_missing_auth_file_never_opens_the_panel(self):
        for content in [None, '{broken', '{"username":"root"}',
                        '{"mode":"password","username":"root","password_hash":null}']:
            if content is None:
                self.auth.unlink(missing_ok=True)
            else:
                self.auth.write_text(content)
            self.assertEqual(self.request({'cmd': 'filenames'})[0], 503)


if __name__ == '__main__':
    unittest.main()
