"""Exercise the real POST entrypoint; fixture changes only paths/lock UID."""
import json
import fcntl
import time
import urllib.parse
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import test_auth_api as auth_api

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_TEST_BINARY', str(ROOT / '.work/packaging-audit-20261012/aarch64-cli-wrapper'))
auth_api.PHP = PHP


class SupportReportApiTests(auth_api.PasswordApiTests):
    __unittest_skip__ = False
    def setUp(self):
        super().setUp()
        self.origin = 'http://localhost'
        for source in (ROOT / 'webui/web/public').glob('support-*.php'):
            text = source.read_text().replace('/tmp/nfqws2-support-report', str(self.base / 'report-lock'))
            (self.base / source.name).write_text(text)
        for name in ['smartdns-report.php','smartdns-store.php','smartdns-profile.php','smartdns-install.php','dpi-store.php','dpi-install.php','dpi-runtime.php','dpi-catalog.php','dpi-options.php']:
            (self.base/name).write_text((ROOT/'webui/web/public'/name).read_text())
        index = self.base / 'index.php'
        index.write_text(index.read_text().replace('new AsusReportLock()', 'new AsusReportLock(null, fileowner(__FILE__))'))

    def request(self, params, session='user-one'):
        code = '''ini_set('session.save_path',$argv[1]);
        session_name('nfqws_asus_session');session_id($argv[2]);session_start();session_write_close();
        $_SERVER['REQUEST_METHOD']='POST';$_SERVER['HTTP_HOST']='localhost';
        if($argv[4]!=='MISSING') $_SERVER['HTTP_ORIGIN']=$argv[4];
        $_POST=json_decode($argv[3],true);
        register_shutdown_function(function(){echo '\\nHTTP_META='.json_encode(['code'=>http_response_code(),'session'=>session_id()]);});
        require $argv[1].'/index.php';'''
        run = subprocess.run([PHP, '-n', '-r', code, str(self.base),
                              self.sessions.get(session, session), json.dumps(params), self.origin],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        self.assertEqual(run.stderr, '')
        body, meta = run.stdout.rsplit('\\nHTTP_META=', 1)
        meta = json.loads(meta)
        self.sessions[session] = meta['session'] or session
        return int(meta['code']), json.loads(body) if body else None

    def test_support_report_auth_csrf_origin_and_exact_parameters(self):
        self.assertEqual(self.request({'cmd': 'supportreport', 'csrf_token': 'bad'})[0], 401)
        token = self.login()
        self.assertEqual(self.request({'cmd':'supportreport'})[0], 400)
        self.assertEqual(self.request({'cmd':'supportreport','csrf_token':['bad']})[0], 400)
        self.assertEqual(self.request({'cmd':'supportreport','csrf_token':'wrong'})[0], 403)
        for origin in ['MISSING','https://localhost','http://evil.invalid','null','http://localhost/path']:
            self.origin=origin
            self.assertEqual(self.request({'cmd':'supportreport','csrf_token':token})[0], 403)
        self.origin='http://localhost'
        self.assertEqual(self.request({'cmd':'supportreport','csrf_token':token,'path':'/etc/shadow'})[0],400)
        status, report=self.request({'cmd':'supportreport','csrf_token':token})
        self.assertEqual(status,200)
        self.assertEqual(report['schema_version'],1)
        self.assertFalse(report['complete'])
        self.assertEqual(set(report['sections']), {'platform','package','engine','ark','process','settings','network','rules','nfqueue','resources','errors','dns'})

    def test_support_report_anonymous_mode_with_its_csrf(self):
        token=self.login()
        self.assertEqual(self.change('',token)[0],200)
        token=self.request({'cmd':'login'},'visitor')[1]['csrf_token']
        status,report=self.request({'cmd':'supportreport','csrf_token':token},'visitor')
        self.assertEqual(status,200)
        self.assertEqual(report['schema_version'],1)

    def test_collector_lock_and_session_release(self):
        token = self.login()
        code = """ini_set('session.save_path',$argv[1]);
        session_name('nfqws_asus_session');session_id($argv[2]);
        $_SERVER['REQUEST_METHOD']='POST';$_SERVER['HTTP_HOST']='localhost';
        $_SERVER['HTTP_ORIGIN']='http://localhost';
        $_POST=['cmd'=>'supportreport','csrf_token'=>$argv[3]];
        require $argv[1].'/index.php';"""
        process = subprocess.Popen([PHP,'-n','-r',code,str(self.base),
                                    self.sessions['user-one'],token],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            lock = self.base / 'report-lock/collector.lock'
            until = time.monotonic() + 5
            held = False
            while time.monotonic() < until:
                if lock.exists():
                    with lock.open('rb') as f:
                        try:
                            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        except BlockingIOError:
                            held = True
                            break
                time.sleep(.025)
            self.assertTrue(held,'collector has acquired the global lock')
            before = time.monotonic()
            self.assertEqual(self.request({'cmd':'login'})[0],200)
            self.assertEqual(self.request({'cmd':'supportreport','csrf_token':token})[0],409)
            self.assertLess(time.monotonic()-before,3,'same session is not held for collection')
            stdout,stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode,0,stderr)
            self.assertEqual(stderr,'')
            report = json.loads(stdout)
            self.assertGreaterEqual(report['duration_ms'],9900)
            self.assertLess(report['duration_ms'],25000)
            self.assertEqual(lock.stat().st_size,0,'no report retained in lock')
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_cgi_attachment_headers_and_current_session(self):
        cgi = os.environ.get('PHP_CGI_TEST_BINARY')
        if not cgi:
            self.skipTest('optional matching PHP CGI interpreter not supplied')
        token = self.login()
        data = urllib.parse.urlencode({'cmd':'supportreport','csrf_token':token})
        env = os.environ.copy()
        env.update(REDIRECT_STATUS='200',SCRIPT_FILENAME=str(self.base/'index.php'),
                   REQUEST_METHOD='POST',CONTENT_TYPE='application/x-www-form-urlencoded',
                   CONTENT_LENGTH=str(len(data)),HTTP_HOST='localhost',HTTP_ORIGIN='http://localhost',
                   HTTP_COOKIE='nfqws_asus_session='+self.sessions['user-one'],QUERY_STRING='')
        run = subprocess.run([cgi,'-n','-d','session.save_path='+str(self.base)],
                             input=data,capture_output=True,text=True,env=env,timeout=30)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(run.stderr,'')
        headers,body = run.stdout.split('\n\n',1)
        self.assertIn('Content-Type: application/json; charset=utf-8',headers)
        self.assertIn('Cache-Control: no-store',headers)
        self.assertRegex(headers,r'X-NFQWS2-Report-Proof: v1\.[0-9]{10}\.[a-f0-9]{32}\.[a-f0-9]{64}')
        self.assertRegex(headers,r'Content-Disposition: attachment; filename="NFQWS2_[A-Za-z0-9_-]+Z\.json"')
        self.assertNotIn('Status: 4',headers)
        self.assertEqual(json.loads(body)['schema_version'],1)


if __name__ == '__main__':
    unittest.main()
