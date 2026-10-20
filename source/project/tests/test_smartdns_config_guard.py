"""Run the actual POSIX guardian with confined fixture paths and real children."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'asus/smartdns/config-worker.sh'
JOB='b'*32


class ConfigGuardTests(unittest.TestCase):
    def wait_for(self, predicate, limit=6):
        end=time.monotonic()+limit
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.03)
        self.fail('bounded guard event not observed')

    def setup_fixture(self, directory, mode):
        self.assertTrue(SCRIPT.is_file(),'missing guarded worker')
        base=Path(directory);state=base/'state';run=state/'smartdns/jobs'/JOB
        run.mkdir(parents=True,mode=0o700);(state/'updates').mkdir()
        (state/'updates/apply.lock').touch();(state/'updates/apply.lock').chmod(0o600)
        lib=base/'lib';lib.mkdir();(lib/'config-worker.php').touch()
        uptime=base/'uptime';uptime.write_text('2000000.25 0\n' if mode=='long_uptime' else '100.0 0\n')
        worker=base/'worker.py'
        worker.write_text(f'''import os,subprocess,time
from pathlib import Path
r=Path({str(run)!r})
assert 'REQUEST_METHOD' not in os.environ
(r/'worker-pid').write_text(str(os.getpid()))
p=subprocess.Popen(['/bin/sleep','60'])
(r/'child-pid').write_text(str(p.pid))
if {mode!r}=='exit':os._exit(3)
time.sleep(60)
''')
        php=base/'php-cgi';php.write_text(f'#!/bin/sh\nexec /usr/bin/python3 "{worker}"\n');php.chmod(0o700)
        text=SCRIPT.read_text().replace('/opt/var/lib/nfqws2-asus/updates',str(state/'updates')).replace('/opt/etc/nfqws-asus-web',str(state)).replace('/opt/lib/nfqws2-asus/smartdns',str(lib)).replace('/opt/bin/php-cgi',str(php)).replace('/proc/uptime',str(uptime))
        script=lib/'config-worker.sh';script.write_text(text);script.chmod(0o700)
        owner=ROOT/'asus/smartdns/session-owner.c'
        self.assertTrue(owner.is_file(),'missing session owner')
        compiled=subprocess.run(['gcc','-Os','-nostdlib','-static','-fno-builtin','-fno-stack-protector','-fno-pie','-no-pie',f'-DCONFIG_WORKER="{script}"',str(owner),'-o',str(lib/'session-owner')],capture_output=True,text=True)
        self.assertEqual(compiled.returncode,0,compiled.stderr)
        return script,state,run,uptime

    @staticmethod
    def live(pid):
        try:
            value=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1]
            return value.split()[0]!='Z'
        except FileNotFoundError:return False

    def exercise(self, mode, action):
        with tempfile.TemporaryDirectory() as directory:
            script,state,run,uptime=self.setup_fixture(directory,mode)
            foreign=subprocess.Popen(['/bin/sleep','60'])
            p=subprocess.Popen(['/bin/sh',str(script),JOB],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={**os.environ,'REQUEST_METHOD':'PRIVATE_CANARY'})
            child=worker=None
            try:
                self.wait_for(lambda:(run/'child-pid').exists())
                child=int((run/'child-pid').read_text());worker=int((run/'worker-pid').read_text())
                if mode=='long_uptime':self.assertRegex((run/'guard').read_text().split()[3],r'^[0-9]+\.[0-9]{3}$')
                if action!='exit':
                    with (state/'updates/apply.lock').open('r+') as lease:
                        with self.assertRaises(BlockingIOError):fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                if action=='deadline':uptime.write_text(str(float(uptime.read_text().split()[0])+151)+' 0\n')
                if action=='owner_loss':p.kill()
                if action=='worker_loss':os.kill(worker,signal.SIGKILL)
                self.wait_for(lambda:not self.live(child))
                p.wait(timeout=6)
                self.assertTrue(self.live(foreign.pid),'unrelated process was affected')
                def released():
                    with (state/'updates/apply.lock').open('r+') as lease:
                        try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);return True
                        except BlockingIOError:return False
                # TERM may stop the engine before the still-live session
                # anchor finishes its bounded one-second cleanup grace.
                self.wait_for(released)
                with (state/'updates/apply.lock').open('r+') as lease:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                if action=='deadline':self.assertEqual((run/'outcome').read_text().strip(),'timed_out')
                if action=='worker_loss':self.assertEqual((run/'outcome').read_text().strip(),'worker_lost')
                self.assertFalse(self.live(worker))
            finally:
                if p.poll() is None:p.kill();p.wait()
                for pid in [child,worker]:
                    if pid and self.live(pid):os.kill(pid,signal.SIGKILL)
                foreign.terminate();foreign.wait()
                if p.stdout:p.stdout.close()
                if p.stderr:p.stderr.close()

    def test_package_update_uses_the_actual_updater_lock_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            script,state,run,uptime=self.setup_fixture(directory,'hang')
            actual=Path(directory)/'actual-updates';actual.mkdir(mode=0o700)
            lock=actual/'apply.lock';lock.touch(mode=0o600)
            script.write_text(script.read_text().replace(str(state/'updates'),str(actual)))
            with lock.open('r+') as f:
                fcntl.flock(f,fcntl.LOCK_EX)
                p=subprocess.Popen(['/bin/sh',str(script),JOB],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                try:
                    try:out,err=p.communicate(timeout=1)
                    except subprocess.TimeoutExpired:
                        self.fail('validation ignored the actual package updater lease')
                    self.assertEqual(p.returncode,3,out+err)
                    self.assertFalse((run/'worker-pid').exists())
                finally:
                    if p.poll() is None:
                        uptime.write_text('1000 0\n')
                        p.communicate(timeout=6)

    def test_worker_loss_cleans_its_candidate_and_releases_lease(self):self.exercise('hang','worker_loss')
    def test_guard_loss_leaves_session_owner_to_clean_its_children(self):self.exercise('hang','owner_loss')
    def test_absolute_deadline_survives_a_blocking_worker(self):self.exercise('hang','deadline')
    def test_exited_worker_cannot_leave_an_orphan(self):self.exercise('exit','exit')
    def test_long_uptime_proof_never_uses_scientific_notation(self):self.exercise('long_uptime','deadline')


if __name__=='__main__':unittest.main()
