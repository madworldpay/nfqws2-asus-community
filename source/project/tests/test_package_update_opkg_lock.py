"""The preflight and opkg must share one POSIX lock owner across exec."""
import fcntl
import os
import shlex
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'asus/update/opkg-launch.c'


class PackageUpdateOpkgLockTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.is_file(),'POSIX opkg launcher missing')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.state=self.base/'state';self.state.mkdir(mode=0o700);(self.state/'operations').mkdir(mode=0o700)
        self.job='a'*32;self.op=self.state/'operations'/self.job;self.op.mkdir(mode=0o700);(self.op/'runtime').mkdir(mode=0o700)
        self.lock=self.base/'opkg.lock';self.lock.touch(mode=0o600);self.log=self.base/'log'
        self.preflight=self.op/'runtime/check.sh';self.preflight.write_text('#!/bin/sh\nprintf preflight >> "'+str(self.log)+'"\nexit 0\n');self.preflight.chmod(0o700)
        self.opkg=self.base/'opkg';self.opkg.write_text('#!/bin/sh\nprintf "opkg:$*" >> "'+str(self.log)+'"\nexit 0\n');self.opkg.chmod(0o700)
        self.binary=self.base/'launcher'
        r=subprocess.run([os.environ.get('UPDATE_TEST_CC','gcc'),*shlex.split(os.environ.get('UPDATE_TEST_CFLAGS','')),'-Os','-nostdlib','-static','-fno-builtin','-fno-stack-protector','-fno-pie','-no-pie',
                          '-DUPDATE_ROOT="'+str(self.state)+'"','-DOPKG_LOCK="'+str(self.lock)+'"','-DOPKG_BIN="'+str(self.opkg)+'"',
                          '-DUPDATE_OWNER='+str(os.getuid()),str(SOURCE),'-o',str(self.binary)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
    def argv(self,job=None):return [*shlex.split(os.environ.get('UPDATE_TEST_RUNNER','')),str(self.binary),job or self.job]
    def run_launch(self,job=None):return subprocess.run(self.argv(job),capture_output=True,timeout=5)
    def test_one_pid_owns_posix_lock_from_preflight_through_opkg_exec(self):
        self.preflight.write_text('#!/bin/sh\nprintf "$PPID" > "'+str(self.base/'owner')+'"\nprintf preflight >> "'+str(self.log)+'"\nsleep .4\n')
        self.opkg.write_text('#!/bin/sh\nprintf "$$" > "'+str(self.base/'opkg-pid')+'"\nprintf opkg >> "'+str(self.log)+'"\nsleep .4\n')
        p=subprocess.Popen(self.argv(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            for marker in ['owner','opkg-pid']:
                end=time.monotonic()+2
                while not (self.base/marker).exists() and time.monotonic()<end:time.sleep(.005)
                self.assertEqual(int((self.base/marker).read_text()),p.pid)
                with self.lock.open('r+') as lock:
                    with self.assertRaises(BlockingIOError):fcntl.lockf(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            out,err=p.communicate(timeout=3);self.assertEqual(p.returncode,0,err);self.assertEqual(out,b'')
            with self.lock.open('r+') as lock:fcntl.lockf(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:
            if p.poll() is None:p.kill();p.communicate()
    def test_existing_opkg_lock_prevents_preflight_and_install(self):
        with self.lock.open('r+') as lock:
            fcntl.lockf(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);r=self.run_launch()
            self.assertEqual(r.returncode,73);self.assertFalse(self.log.exists())
    def test_failed_preflight_never_executes_opkg(self):
        self.preflight.write_text('#!/bin/sh\nprintf preflight >> "'+str(self.log)+'"\nexit 1\n')
        self.assertEqual(self.run_launch().returncode,74);self.assertEqual(self.log.read_text(),'preflight')
    def test_system_admin_commands_work_in_preflight_and_installer_without_inheriting_path(self):
        # ASUS preinst needs cru from /usr/sbin. Exercise the same executable
        # lookup boundary with a harmless real system utility on the test host.
        hostile=self.base/'hostile';hostile.mkdir()
        (hostile/'sysctl').write_text('#!/bin/sh\necho WRONG\n');(hostile/'sysctl').chmod(0o700)
        for phase in ['preflight','installer']:
            with self.subTest(phase=phase):
                marker=self.base/phase
                script='#!/bin/sh\nsysctl -n kernel.ostype > '+shlex.quote(str(marker))+' || exit 1\n'
                self.preflight.write_text(script if phase=='preflight' else '#!/bin/sh\nexit 0\n')
                self.opkg.write_text(script if phase=='installer' else '#!/bin/sh\nexit 0\n')
                result=subprocess.run(self.argv(),env=os.environ|{'PATH':str(hostile)},capture_output=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(marker.read_text().strip(),'Linux')
    def test_invalid_id_symlink_and_unsafe_lock_refuse_without_writes(self):
        self.assertEqual(self.run_launch('../wrong').returncode,75)
        outside=self.base/'outside';outside.write_text('KEEP');self.lock.unlink();self.lock.symlink_to(outside)
        self.assertEqual(self.run_launch().returncode,75);self.assertEqual(outside.read_text(),'KEEP');self.assertFalse(self.log.exists())
    def test_killed_lock_owner_does_not_leave_stale_lock_or_install(self):
        self.preflight.write_text('#!/bin/sh\nprintf preflight >> "'+str(self.log)+'"\nsleep .3\n')
        p=subprocess.Popen(self.argv(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        end=time.monotonic()+2
        while not self.log.exists() and time.monotonic()<end:time.sleep(.005)
        p.kill();p.communicate(timeout=2);time.sleep(.4)
        self.assertEqual(self.log.read_text(),'preflight')
        with self.lock.open('r+') as lock:fcntl.lockf(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)


if __name__=='__main__':unittest.main()
