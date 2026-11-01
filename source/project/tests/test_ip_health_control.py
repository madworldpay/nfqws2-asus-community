"""Execute the fixed ASUS reconcile coordinator; no router or core changes."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'ip-health/control.sh'


class IpHealthControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.run=self.root/'run';self.run.mkdir(mode=0o700);self.private=self.run/'ip-health-private';self.private.mkdir(mode=0o700)
        self.assertTrue(SOURCE.exists(),'fixed async reconcile helper missing')
        self.entry=self.root/'control.sh';self.init=self.root/'S51nfqws2'
        self.init.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "'+str(self.root/'calls')+'"\nsleep .3\ntouch "'+str(self.root/'done')+'"\n');self.init.chmod(0o755)
        text=SOURCE.read_text().replace('/tmp/nfqws2-asus',str(self.run)).replace('/opt/libexec/nfqws2-asus/busybox','/usr/bin/busybox').replace('/opt/lib/nfqws2-asus/ip-health/control.sh',str(self.entry)).replace('/opt/etc/init.d/S51nfqws2',str(self.init)).replace('/opt/bin/flock','/usr/bin/flock')
        text=text.replace('[ "$(id -u)" = 0 ]',f'[ "$(id -u)" = {os.getuid()} ]').replace('drwx------:0',f'drwx------:{os.getuid()}').replace('-rw-------:1:0',f'-rw-------:1:{os.getuid()}')
        self.entry.write_text(text);self.entry.chmod(0o755)

    def test_detached_hup_safe_duplicate_coordinator_drops_inherited_apply_lease(self):
        # The outer caller exits after queue acceptance, while its worker runs.
        p=subprocess.Popen(['sh','-c','exec 8>"$1"; flock -s 8; "$2" queue','fixture',str(self.root/'apply.lock'),str(self.entry)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        out,err=p.communicate(timeout=2);self.assertEqual(p.returncode,0,out+err)
        deadline=time.monotonic()+2
        while not (self.root/'calls').exists()and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue((self.root/'calls').exists());os.killpg(p.pid,signal.SIGHUP)
        lease=(self.root/'apply.lock').open('a');self.addCleanup(lease.close)
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        duplicate=subprocess.run([str(self.entry),'queue'],capture_output=True,timeout=2);self.assertEqual(duplicate.returncode,0,duplicate.stderr)
        deadline=time.monotonic()+2
        while not (self.root/'done').exists()and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue((self.root/'done').exists(),'coordinator/core helper survives process-group HUP')
        self.assertEqual((self.root/'calls').read_text().splitlines(),['reconcile'])

    def test_unknown_arguments_and_unsafe_private_runtime_are_rejected_before_launch(self):
        for args in [[],['run'],['queue','start'],['worker','start']]:
            p=subprocess.run([str(self.entry),*args],capture_output=True,timeout=2);self.assertNotEqual(p.returncode,0)
        self.private.chmod(0o777)
        p=subprocess.run([str(self.entry),'queue'],capture_output=True,timeout=2);self.assertNotEqual(p.returncode,0)
        self.assertFalse((self.root/'calls').exists())
