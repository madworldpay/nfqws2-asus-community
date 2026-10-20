"""A short updater status read must not abort an accepted background install."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from test_dpi_normalize import PHP, PUBLIC


class SmartDnsUpdateContentionTests(unittest.TestCase):
    def exercise(self, lock_name, release):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / 'updates'
            state.mkdir(mode=0o700)
            source = (PUBLIC / 'smartdns-api.php').read_text()
            source = source.replace("__DIR__.'/smartdns-install.php'", json.dumps(str(PUBLIC / 'smartdns-install.php'), ensure_ascii=False))
            source = source.replace("__DIR__.'/update-guard.php'", json.dumps(str(PUBLIC / 'update-guard.php'), ensure_ascii=False))
            source = source.replace('new AsusUpdateStore()', f'new AsusUpdateStore({json.dumps(str(state))},{os.getuid()})')
            (root / 'api.php').write_text(source)
            code = '''require $argv[1].'/api.php';
            $i=new AsusSmartDnsInstaller($argv[1].'/engine',(int)$argv[2],['version'=>'fixture','sha256'=>str_repeat('a',64)],
                function(){throw new RuntimeException('download_failed');});
            $j=new AsusSmartDnsJobs($i,['available'=>fn()=>['available'=>true,'code'=>'ready'],'launch'=>fn()=>null]);
            $j->start(str_repeat('a',32));$j->work(str_repeat('a',32));
            echo file_get_contents($argv[1].'/engine/job.json');'''
            with (state / lock_name).open('w') as lock:
                os.chmod(lock.name, 0o600)
                fcntl.flock(lock, fcntl.LOCK_EX)
                started = time.monotonic()
                process = subprocess.Popen([PHP, '-n', '-r', code, str(root), str(os.getuid())], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    if release:
                        deadline = time.monotonic() + 3
                        while time.monotonic() < deadline and process.poll() is None:
                            job = root / 'engine/job.json'
                            if job.exists() and json.loads(job.read_text())['state'] != 'queued':
                                break
                            time.sleep(.005)
                        time.sleep(.15)
                        fcntl.flock(lock, fcntl.LOCK_UN)
                    out, err = process.communicate(timeout=4)
                    self.assertEqual(process.returncode, 0, out + err)
                    self.assertEqual(err, '')
                    return json.loads(out), time.monotonic() - started
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                    if process.poll() is None:
                        process.kill()
                        process.communicate()

    def test_short_status_journal_lock_does_not_fail_install(self):
        job, elapsed = self.exercise('control.lock', release=True)
        self.assertEqual(job['code'], 'download_failed')
        self.assertLess(elapsed, 3)

    def test_active_package_apply_remains_blocked_and_wait_is_bounded(self):
        job, elapsed = self.exercise('apply.lock', release=False)
        self.assertEqual(job['code'], 'busy')
        self.assertLess(elapsed, 3)
