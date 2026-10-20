"""Shell callers keep the shared update lease for the entire mutation."""
import fcntl
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]


class PackageUpdateShellTests(unittest.TestCase):
    def setUp(self):
        source=ROOT/'asus/update/lifecycle.sh';self.assertTrue(source.is_file(),'shell update guard missing')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.opt=self.base/'opt'
        for name in ['bin','lib/nfqws2-asus/update','libexec/nfqws2-asus','var/lib/nfqws2-asus/updates']:(self.opt/name).mkdir(parents=True,exist_ok=True)
        self.lock=self.opt/'var/lib/nfqws2-asus/updates/apply.lock';self.lock.touch(mode=0o600)
        self.guard=self.base/'guard.sh';self.guard.write_text(source.read_text().replace('/opt/',str(self.opt)+'/'))
        php=self.opt/'bin/php-cgi';php.write_text('#!/bin/sh\nfor arg do previous=$last; last=$arg; done\ncase "$previous:$last" in\n'
            'shell-authorize:*) test -f '+shlex.quote(str(self.base/'authorized'))+';;\n'
            '*:shell-init|*:shell-check) exit 0;;\n*) exit 1;;\nesac\n');php.chmod(0o700)
        bb=self.opt/'libexec/nfqws2-asus/busybox';bb.write_text('#!/bin/sh\nexec "$@"\n');bb.chmod(0o700)
        (self.opt/'bin/flock').symlink_to(shutil.which('flock'))
    def script(self,tail='echo entered',action='start'):
        return '. '+shlex.quote(str(self.guard))+'\nasus_update_enter core '+action+' || exit $?\n'+tail
    def test_ordinary_action_holds_shared_lease_until_exit(self):
        p=subprocess.Popen(['sh','-c',self.script('echo entered; sleep .3')],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(p.stdout.readline().strip(),'entered')
            with self.lock.open('r+') as f:
                with self.assertRaises(BlockingIOError):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(p.wait(timeout=2),0)
            with self.lock.open('r+') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:
            if p.poll() is None:p.kill();p.wait()
            p.stdout.close()
    def test_real_packaged_busybox_needs_no_flock_applet(self):
        bb=self.opt/'libexec/nfqws2-asus/busybox';bb.write_text('#!/bin/sh\necho "flock: applet not found" >&2\nexit 127\n')
        p=subprocess.run(['sh','-c',self.script()],capture_output=True,text=True,timeout=2)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.strip(),'entered')
    def test_active_update_blocks_normal_start_and_reconcile(self):
        with self.lock.open('r+') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            for action in ['start','reconcile']:
                p=subprocess.run(['sh','-c',self.script(action=action)],capture_output=True,text=True,timeout=2)
                self.assertNotEqual(p.returncode,0);self.assertNotIn('entered',p.stdout)
    def test_only_verified_transaction_can_bypass_exclusive_lease(self):
        (self.base/'authorized').touch()
        with self.lock.open('r+') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            p=subprocess.run(['sh','-c',self.script()],capture_output=True,text=True,timeout=2)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.strip(),'entered')
    def test_long_lived_own_children_close_both_service_and_update_leases(self):
        for source in ['asus/lifecycle.sh','asus/web-lib.sh']:
            for line in (ROOT/source).read_text().splitlines():
                if '9>&-' in line:self.assertIn('8>&-',line)


if __name__=='__main__':unittest.main()
