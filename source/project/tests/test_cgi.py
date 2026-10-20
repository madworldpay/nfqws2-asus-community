"""Exercise the PHP wrapper with a real CGI interpreter when available."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PHP_CGI = os.environ.get('PHP_CGI_TEST_BINARY') or shutil.which('php-cgi')
PHP_CLI = os.environ.get('PHP_TEST_BINARY') or shutil.which('php')


@unittest.skipUnless(PHP_CLI, 'optional PHP CLI interpreter not supplied')
class ApiCommandTests(unittest.TestCase):
    def test_scoped_ark_backup_restore(self):
        result = subprocess.run([PHP_CLI, '-n', str(ROOT / 'tests/test_ark.php')],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('PASS: nine flags', result.stdout)

    def test_removed_domain_check_returns_unknown_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = Path(tmp) / 'index.php'
            api.write_text((ROOT / 'webui/web/public/index.php').read_text())
            (Path(tmp) / 'asus.php').write_text(
                (ROOT / 'webui/web/public/asus.php').read_text().replace(
                    '/opt/etc/nfqws-asus-web/auth.json', str(Path(tmp) / 'auth.json')))
            shutil.copyfile(ROOT / 'webui/web/public/ark.php', Path(tmp) / 'ark.php')
            (Path(tmp) / 'auth.json').write_text(
                '{"mode":"password","username":"root","password_hash":""}')
            script = '''
            ini_set('session.save_path', $argv[1]);
            session_name('nfqws_asus_session');
            session_id('nfqws-test-domain-removal');
            session_start();
            $_SESSION['auth'] = true;
            session_write_close();
            $_SERVER['REQUEST_METHOD'] = 'POST';
            $_POST = ['cmd' => 'check'];
            register_shutdown_function(function () {
                echo 'HTTP_STATUS=' . http_response_code();
            });
            require $argv[2];
            '''
            r = subprocess.run([PHP_CLI, '-n', '-d', 'error_reporting=E_ALL&~E_DEPRECATED',
                                '-r', script, tmp, str(api)],
                               text=True, capture_output=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, 'HTTP_STATUS=405')


@unittest.skipUnless(PHP_CGI, 'optional PHP CGI interpreter not supplied')
class CgiTests(unittest.TestCase):
    def test_script_filename_from_lighttpd_is_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'index.php'
            script.write_text('<?php echo "CGI_SCRIPT_OK";')
            # Entware's shared php.ini points doc_root at another application.
            wrapper = (ROOT / 'asus/php-cgi.sh').read_text().replace(
                '/opt/bin/php-cgi', shlex.quote(PHP_CGI) + ' -n -d doc_root=/opt/share/www')
            wrapper = wrapper.replace('/opt/share/nfqws-asus-web', tmp)
            env = {**os.environ, 'SCRIPT_FILENAME': str(script),
                   'SCRIPT_NAME': '/index.php', 'REQUEST_METHOD': 'POST',
                   'CONTENT_LENGTH': '0', 'REDIRECT_STATUS': '200',
                   'SERVER_PROTOCOL': 'HTTP/1.1', 'GATEWAY_INTERFACE': 'CGI/1.1',
                   'DOCUMENT_ROOT': tmp}
            env.pop('PATH_TRANSLATED', None)
            r = subprocess.run(['sh', '-c', wrapper], input='', text=True,
                               capture_output=True, env=env, timeout=10)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('CGI_SCRIPT_OK', r.stdout)
            self.assertNotIn('Status: 404', r.stdout)


if __name__ == '__main__':
    unittest.main()
