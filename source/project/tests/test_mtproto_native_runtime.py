"""Execute generated native service fragments without touching /opt or Docker."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'webui/web/src/utils/mtproto-install.sh'


class MtprotoNativeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = SOURCE.read_text()

    def service(self):
        text = self.raw.split('cat > "$work/service" <<\'SH\'\n', 1)[1].split('\nSH\n', 1)[0]
        for before, after in [('/opt/share/nfqws-mtproto', str(self.root)),
                              ('/opt/var/run', str(self.root)),
                              ('/opt/var/log', str(self.root)),
                              ('/opt/bin/python3', sys.executable),
                              ('/opt/libexec/nfqws2-asus/busybox', '/bin/busybox')]:
            text = text.replace(before, after)
        path = self.root / 'service'
        path.write_text(text)
        path.chmod(0o700)
        return path

    def test_runner_is_detached_from_the_launching_session_and_stop_is_owned(self):
        service = self.service()
        (self.root / 'run.py').write_text('import time\ntime.sleep(60)\n')
        launcher = subprocess.Popen(['/bin/sh', '-c', '"$1" start; sleep 60', 'launch', str(service)],
                                    start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pid = None
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    pid = int((self.root / 'nfqws-mtproto.pid').read_text())
                    if b'run.py' in Path(f'/proc/{pid}/cmdline').read_bytes():
                        break
                except (FileNotFoundError, ValueError):
                    pass
                time.sleep(0.02)
            self.assertIsNotNone(pid)
            self.assertNotEqual(os.getsid(pid), os.getsid(launcher.pid),
                                'Service must not stay in the SSH launcher session')
            os.killpg(launcher.pid, signal.SIGHUP)
            launcher.wait(timeout=3)
            self.assertEqual(subprocess.run([str(service), 'status'], capture_output=True).returncode, 0)
            stopped = subprocess.run([str(service), 'stop'], capture_output=True)
            self.assertEqual(stopped.returncode, 0, stopped.stderr)
            self.assertNotEqual(subprocess.run([str(service), 'status'], capture_output=True).returncode, 0)
        finally:
            if launcher.poll() is None:
                os.killpg(launcher.pid, signal.SIGKILL)
                launcher.wait(timeout=3)
            if pid:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_stop_does_not_signal_an_unrelated_pid(self):
        service = self.service()
        other = subprocess.Popen(['sleep', '20'])
        try:
            (self.root / 'nfqws-mtproto.pid').write_text(str(other.pid))
            subprocess.run([str(service), 'stop'], check=True, capture_output=True)
            self.assertIsNone(other.poll())
        finally:
            other.terminate()
            other.wait(timeout=3)

    def test_native_runner_redacts_formatted_keys_and_links_before_upstream_import(self):
        key = '0123456789abcdef0123456789abcdef'
        (self.root / 'config.json').write_text(json.dumps({'port': 18443, 'secret': key}))
        app = self.root / 'app/proxy'
        app.mkdir(parents=True)
        (app / '__init__.py').write_text('')
        (app / 'tg_ws_proxy.py').write_text('''import logging,sys
logging.basicConfig(level=logging.INFO)
def main():
    key=sys.argv[sys.argv.index('--secret')+1]
    logging.info('secret=%s',key)
    logging.info('connect: https://t.me/proxy?secret=dd%s',key)
    logging.info('fields: %s',{'secret':key})
    try:
        raise ValueError('key='+key)
    except ValueError:
        logging.exception('upstream error')
    logging.info('service ready')
''')
        raw = self.raw.split('cat > "$root/run.py" <<\'PY\'\n', 1)[1].split('\nPY\n', 1)[0]
        # Privilege dropping is tested by deployment; this fixture isolates log handling.
        raw = raw.replace("os.setgroups([])", 'pass').replace('os.setgid(user.pw_gid)', 'pass').replace('os.setuid(user.pw_uid)', 'pass')
        prelude = ROOT / 'webui/web/src/utils/mtproto-log-redaction.py'
        if prelude.exists():
            raw = raw.replace('@@MTPROTO_LOG_REDACTION@@', prelude.read_text())
        runner = self.root / 'run.py'
        runner.write_text(raw)
        result = subprocess.run([sys.executable, str(runner)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('service ready', result.stderr)
        self.assertNotIn(key, result.stderr + result.stdout, 'Startup diagnostics must not disclose the proxy key')
        self.assertIn('[redacted]', result.stderr)


if __name__ == '__main__':
    unittest.main()
