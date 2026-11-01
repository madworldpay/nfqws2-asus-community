"""Short journal contention must not strand a read-only update check."""
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from test_dpi_normalize import PHP, PUBLIC


class PackageUpdateCheckRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'state'
        self.call('store')

    def call(self, action):
        code = r'''require $argv[1].'/update-check.php';
        final class LocalPreparation implements NfqwsUpdatePreparation {
            public function environment():array {return ['installed'=>'1.3.2-asus6+b79'];}
            public function cached():?array {return ['state'=>'available','code'=>null,'candidate'=>['build'=>80],'installed_version'=>'1.3.2-asus6+b79'];}
            public function check(bool $force=false):array {throw new RuntimeException('unexpected_network');}
            public function reserveCached(string $revision,string $requestId):array {throw new RuntimeException('unexpected_install');}
            public function completePrepare(string $id,?callable $stage=null):array {throw new RuntimeException('unexpected_install');}
        }
        try {
            $store=new AsusUpdateStore($argv[2],(int)$argv[3]);
            $check=new AsusUpdateCheck($store,new LocalPreparation());
            $out=match($argv[4]) {'status'=>$check->status(),'request'=>$check->request(),'store'=>$store->status()};
            echo json_encode($out);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(self.root),
                                 str(os.getuid()), action], capture_output=True, text=True, timeout=4)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_short_journal_lock_does_not_fail_status_or_cached_check(self):
        for action in ['status', 'request', 'store']:
            with self.subTest(action=action):
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    with (self.root / 'control.lock').open('r+b') as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX)
                        pending = pool.submit(self.call, action)
                        time.sleep(.2)
                    value = pending.result(timeout=3)
                if action == 'store':
                    self.assertEqual(value, {'active': None, 'history': []})
                else:
                    self.assertIn('state', value, value)
                    self.assertEqual(value['state'], 'available', value)
                    self.assertEqual(value['candidate']['build'], 80)

    def test_live_long_lock_remains_busy_without_replacing_the_lock(self):
        path = self.root / 'control.lock'
        before = path.stat().st_ino
        with path.open('r+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            started = time.monotonic()
            value = self.call('status')
            self.assertEqual(value, {'error': 'busy'})
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(path.stat().st_ino, before)
        self.assertEqual(self.call('status')['state'], 'available')

    def test_reboot_interrupts_the_check_and_the_next_cached_read_recovers(self):
        task = {'schema': 1, 'id': 'a' * 32, 'boot_id': 'previous-boot',
                'started_uptime': 1, 'state': 'checking', 'guardian': None,
                'child': None, 'code': None}
        path = self.root / 'check-task.json'
        path.write_text(json.dumps(task)); path.chmod(0o600)
        self.assertEqual(self.call('status')['code'], 'interrupted')
        self.assertEqual(json.loads(path.read_text())['state'], 'failed')
        # A current cache is returned by a new check, with no network or install.
        value = self.call('request')
        self.assertEqual(value['state'], 'available', value)
        self.assertEqual(self.call('status')['state'], 'available')


if __name__ == '__main__':
    unittest.main()
