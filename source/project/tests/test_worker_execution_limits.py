"""Real Entware CGI CPU timers, restricted to trusted non-HTTP workers."""
import base64
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import ROOT

AUDIT = ROOT / '.work/packaging-audit-20261012'
ABIS = ('armv7-legacy', 'armv7', 'aarch64')
# getrusage measures CPU, not elapsed sleeps. Exceed a shortened real CGI timer.
BURN = '''function cpuSeconds():float{$r=getrusage();return $r['ru_utime.tv_sec']+$r['ru_utime.tv_usec']/1e6+$r['ru_stime.tv_sec']+$r['ru_stime.tv_usec']/1e6;}
$start=cpuSeconds();do{for($i=0;$i<100;$i++)hash('sha256',str_repeat('x',4096));}while(cpuSeconds()-$start<1.2);
echo json_encode(['complete'=>true,'limit'=>(int)ini_get('max_execution_time')]);exit(0);'''


class WorkerExecutionLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.base.chmod(0o700)
        self.root_status = self.base / 'root-status'
        self.root_status.write_text('Uid:\t0\t0\t0\t0\n')

    def run_cgi(self, abi, entry, args=(), http=False):
        root = AUDIT / (abi + '-sysroot')
        runner = AUDIT / ('qemu-aarch64' if abi == 'aarch64' else 'qemu-arm')
        self.assertTrue((root / 'opt/bin/php8-cgi').is_file(), 'actual pinned CGI fixture required')
        env = dict(os.environ)
        for key in ('REQUEST_METHOD', 'QUERY_STRING', 'CONTENT_TYPE', 'CONTENT_LENGTH', 'SCRIPT_FILENAME'):
            env.pop(key, None)
        if http: env.update(REQUEST_METHOD='GET', REDIRECT_STATUS='200', SCRIPT_FILENAME=str(entry))
        return subprocess.run([str(runner), '-L', str(root), '-E', 'LD_LIBRARY_PATH=' + str(root / 'opt/lib'),
            str(root / 'opt/bin/php8-cgi'), '-n', '-d', 'max_execution_time=1', '-d', 'register_argc_argv=1',
            '-q', '-f', str(entry), '--', *args], env=env, capture_output=True, text=True, timeout=8)

    def copied_entry(self, source):
        entry = self.base / 'worker.php'
        entry.write_text(source.read_text().replace('/proc/self/status', str(self.root_status)))
        return entry

    def assert_completes(self, abi, entry, args=()):
        result = self.run_cgi(abi, entry, args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(result.stdout), {'complete': True, 'limit': 0})

    def test_installed_and_staged_updater_entries_outlive_cgi_cpu_default(self):
        app = self.base / 'app'; app.mkdir()
        (app / 'update-worker.php').write_text('<?php ' + BURN)
        for name in ('asus/update/worker.php', 'asus/install-worker.php'):
            entry = self.copied_entry(ROOT / name)
            for abi in ABIS:
                with self.subTest(entry=name, abi=abi): self.assert_completes(abi, entry, ('apply', 'a' * 32))

    def test_bootstrap_main_inherits_limit_only_after_private_work_validation(self):
        data = {'main.php': {'data': base64.b64encode(('<?php ' + BURN).encode()).decode(), 'mode': 0o600}}
        encoded = base64.b64encode(gzip.compress(json.dumps(data).encode())).decode()
        source = (ROOT / 'asus/install-extract.php').read_text()
        source = source.replace('/proc/self/status', str(self.root_status)).replace("['uid']!==0", "['uid']!==" + str(os.getuid()))
        entry = self.base / 'extract.php'
        entry.write_text(source.replace('<?php', '<?php const NFQWS_ASUS_INSTALL_FILES=' + json.dumps(encoded) + ';', 1))
        work = self.base / 'work'; work.mkdir(mode=0o700)
        for abi in ABIS:
            with self.subTest(abi=abi): self.assert_completes(abi, entry, ('check', str(work)))
        work.chmod(0o755)
        result = self.run_cgi('armv7-legacy', entry, ('check', str(work)))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"complete"', result.stdout)

    def test_http_and_nonroot_entry_invocations_never_enter_unlimited_work(self):
        app = self.base / 'app'; app.mkdir()
        (app / 'update-worker.php').write_text('<?php ' + BURN)
        for name in ('asus/update/worker.php', 'asus/install-worker.php'):
            entry = self.copied_entry(ROOT / name)
            result = self.run_cgi('armv7-legacy', entry, ('apply', 'a' * 32), http=True)
            self.assertNotEqual(result.returncode, 0, name + result.stdout + result.stderr)
            self.assertNotIn('Maximum execution time', result.stdout + result.stderr)
            self.assertNotIn('Fatal error', result.stdout + result.stderr)
            self.root_status.write_text('Uid:\t1000\t1000\t1000\t1000\n')
            result = self.run_cgi('armv7-legacy', entry, ('apply', 'a' * 32))
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('Maximum execution time', result.stdout + result.stderr)
            self.root_status.write_text('Uid:\t0\t0\t0\t0\n')

    def test_plain_http_code_retains_cgi_cpu_limit(self):
        entry = self.base / 'http.php'; entry.write_text('<?php ' + BURN)
        result = self.run_cgi('armv7-legacy', entry, http=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Maximum execution time of 1 second exceeded', result.stdout + result.stderr)

    def test_persistent_ip_health_loop_outlives_cumulative_cgi_cpu_limit(self):
        private = self.base / 'private'; private.mkdir(mode=0o700)
        app = self.base / 'app'; app.mkdir()
        (app / 'ip-health-runtime.php').write_text('''<?php
class NfqwsIpHealthStore {}
class NfqwsIpHealthRuntime {
    public function __construct(...$args){}
    public function liveFacts():array{return [];}
    public function writePrivate(...$args):void{}
    public static function startTicks(string $stat):string{return '1';}
    public function tick(int $now):void{''' + BURN + '}}')
        code = (ROOT / 'ip-health/worker.php').read_text().replace('/proc/self/status', str(self.root_status))
        code = code.replace('/opt/share/nfqws-asus-web', str(app)).replace('/tmp/nfqws2-asus/ip-health-private', str(private))
        code = code.replace("$s['uid']!==0", "$s['uid']!==" + str(os.getuid()))
        entry = self.base / 'health.php'; entry.write_text(code)
        for abi in ABIS:
            with self.subTest(abi=abi): self.assert_completes(abi, entry, ('loop',))
        result = self.run_cgi('armv7-legacy', entry, ('loop',), http=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Maximum execution time', result.stdout + result.stderr)
        self.assertNotIn('Fatal error', result.stdout + result.stderr)

    def test_technical_channel_run_and_guard_keep_session_owned_lifetime(self):
        app = self.base / 'app'; app.mkdir()
        (app / 'technical-channel.php').write_text('''<?php
class AsusTechnicalChannel {
    public function run(string $id):void{''' + BURN + '''}
    public function command(string $id):int{''' + BURN + '}}')
        entry = self.copied_entry(ROOT / 'asus/technical-channel/worker.php')
        entry.write_text(entry.read_text().replace('/opt/share/nfqws-asus-web', str(app)))
        for mode in ('run', 'guard'):
            for abi in ABIS:
                with self.subTest(mode=mode, abi=abi): self.assert_completes(abi, entry, (mode, 'a' * 32))
        result = self.run_cgi('armv7-legacy', entry, ('run', 'a' * 32), http=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Fatal error', result.stdout + result.stderr)
        self.root_status.write_text('Uid:\t1000\t1000\t1000\t1000\n')
        result = self.run_cgi('armv7-legacy', entry, ('guard', 'a' * 32))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Maximum execution time', result.stdout + result.stderr)

    def test_technical_signed_expiry_and_uptime_still_fail_closed(self):
        app = self.base / 'app'; app.mkdir()
        process = ROOT / 'webui/web/public/technical-channel-process.php'
        (app / 'technical-channel.php').write_text('<?php require ' + json.dumps(str(process)) + ''';
class AsusTechnicalChannel {
    public function run(string $id):void{
        $now=time();$uptime=AsusTechnicalProcess::uptime();
        $state=['identity'=>AsusTechnicalProcess::identity(getmypid()),'state'=>'connected','expires_at'=>$now+10,'uptime_deadline'=>$uptime+10];
        $active=AsusTechnicalProcess::active($state,$now,$uptime);
        $state['expires_at']=$now;$expired=AsusTechnicalProcess::active($state,$now,$uptime);
        $state['expires_at']=$now+10;$state['uptime_deadline']=$uptime;
        $uptimeExpired=AsusTechnicalProcess::active($state,$now-100,$uptime);
        echo json_encode(['limit'=>(int)ini_get('max_execution_time'),'active'=>$active,'expired'=>$expired,'uptime_expired'=>$uptimeExpired]);
    }
}''')
        entry = self.copied_entry(ROOT / 'asus/technical-channel/worker.php')
        entry.write_text(entry.read_text().replace('/opt/share/nfqws-asus-web', str(app)))
        for abi in ABIS:
            with self.subTest(abi=abi):
                result = self.run_cgi(abi, entry, ('run', 'a' * 32))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout), {'limit': 0, 'active': True, 'expired': False, 'uptime_expired': False})


if __name__ == '__main__': unittest.main()
