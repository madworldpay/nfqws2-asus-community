"""Native CGI CPU timers are disabled only after privileged CLI validation."""
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from test_worker_execution_limits import BURN

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = os.environ.get('NFQWS_TEST_DOCKER')


@unittest.skipUnless(CONTAINER, 'Requires an isolated OpenWrt PHP8 CGI rootfs')
class NativeWorkerExecutionLimits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = json.loads(subprocess.check_output(['docker', 'inspect', CONTAINER]))[0]
        images = {'nfqws-update87-fixture:24', 'nfqws-update87-fixture:25',
                  'nfqws-openwrt-test:24.10.8', 'nfqws-openwrt-test:25.12.6-php'}
        if not CONTAINER.startswith('nfqws-openwrt') or spec['HostConfig']['NetworkMode'] != 'none' or spec['Config']['Image'] not in images:
            raise RuntimeError('Refusing a non-isolated or unrecognized native test container')

    def sh(self, command, data=None):
        result = subprocess.run(['docker', 'exec', '-i', CONTAINER, 'sh', '-c', command],
                                input=data, text=True, capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def setUp(self):
        self.base = '/tmp/native-cpu-limit-' + uuid.uuid4().hex
        self.sh('mkdir -m 755 ' + self.base + '; mkdir -m 755 ' + self.base + '/app')
        self.addCleanup(lambda: self.sh('rm -rf ' + self.base))
        # The first class boundary burns real CPU; the entry validation and
        # set_time_limit call run unchanged in the actual native CGI binary.
        for module in ['openwrt-update-worker.php', 'openwrt-package-quiesce.php']:
            self.sh('cat > ' + self.base + '/app/' + module, '<?php ' + BURN)
        self.entries = {}
        instrument = 'register_shutdown_function(static function(){echo "\\nENTRY_LIMIT=",ini_get("max_execution_time"),"\\n";});\n'
        for source in ['openwrt/update/worker.php', 'openwrt/update/quiesce.php', 'openwrt/install-update.php', 'openwrt/install-main.php']:
            code = (ROOT / source).read_text().replace('/usr/share/nfqws2-web', self.base + '/app')
            if source == 'openwrt/install-main.php':
                code = code.replace('<?php', '<?php class AsusUpdateStore { public function __construct(...$args){' + BURN + '}}', 1)
            code = code.replace('<?php', '<?php ' + instrument, 1)
            entry = self.base + '/' + source.replace('/', '-')
            self.sh('cat > ' + entry, code)
            self.sh('chmod 644 ' + entry)
            self.entries[source] = entry

    def run_cgi(self, entry, args=(), http=False, nonroot=False):
        command = ['docker', 'exec']
        if nonroot:
            command += ['--user', '65534:65534']
        command += [CONTAINER, 'env', '-u', 'REQUEST_METHOD', '-u', 'QUERY_STRING',
                    '-u', 'CONTENT_TYPE', '-u', 'CONTENT_LENGTH', '-u', 'SCRIPT_FILENAME']
        if http:
            command += ['REQUEST_METHOD=GET', 'REDIRECT_STATUS=200', 'SCRIPT_FILENAME=' + entry]
        command += ['/usr/bin/php8-cgi', '-n', '-d', 'max_execution_time=1', '-d',
                    'register_argc_argv=1', '-q', '-f', entry, '--', *args]
        return subprocess.run(command, text=True, capture_output=True, timeout=8)

    def cases(self):
        return [
            ('openwrt/update/worker.php', ('apply', 'a' * 32)),
            ('openwrt/update/quiesce.php', ('upgrade',)),
            ('openwrt/install-update.php', (self.base,)),
            ('openwrt/install-main.php', ('prepare', self.base)),
        ]

    def test_valid_root_cli_entries_outlive_native_cgi_cpu_default(self):
        for source, args in self.cases():
            with self.subTest(entry=source):
                result = self.run_cgi(self.entries[source], args)
                self.assertEqual(result.returncode, 0, source + result.stdout + result.stderr)
                self.assertEqual(result.stderr, '')
                payload, limit = result.stdout.strip().split('\nENTRY_LIMIT=')
                self.assertEqual(json.loads(payload), {'complete': True, 'limit': 0})
                self.assertEqual(limit, '0')

    def assert_denied_with_original_limit(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('"complete"', result.stdout)
        self.assertNotIn('Maximum execution time', result.stdout + result.stderr)
        self.assertNotIn('Fatal error', result.stdout + result.stderr)
        self.assertIn('ENTRY_LIMIT=1', result.stdout, 'rejected callers must never disable the CGI timer')

    def test_http_and_real_nonroot_callers_cannot_disable_the_timer(self):
        for source, args in self.cases():
            for flags in [{'http': True}, {'nonroot': True}]:
                with self.subTest(entry=source, flags=flags):
                    self.assert_denied_with_original_limit(self.run_cgi(self.entries[source], args, **flags))

    def test_invalid_cli_arguments_are_rejected_before_the_limit_optout(self):
        for source, args in [
            ('openwrt/update/worker.php', ('apply', 'bad-id')),
            ('openwrt/update/worker.php', ('unknown', 'a' * 32)),
            ('openwrt/update/quiesce.php', ('unknown',)),
            ('openwrt/install-update.php', ()),
            ('openwrt/install-main.php', ('unknown', self.base)),
        ]:
            with self.subTest(entry=source, args=args):
                self.assert_denied_with_original_limit(self.run_cgi(self.entries[source], args))

    def test_ordinary_http_still_has_native_cgi_cpu_timeout(self):
        entry = self.base + '/ordinary-http.php'
        self.sh('cat > ' + entry, '<?php ' + BURN)
        result = self.run_cgi(entry, http=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"complete"', result.stdout)
        self.assertIn('Maximum execution time of 1 second exceeded', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
