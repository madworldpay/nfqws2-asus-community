import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from test_dpi_normalize import ROOT


class SmartDnsGuardTests(unittest.TestCase):
    def test_deadline_stops_its_suspended_worker_and_worker_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);job='a'*32
            php=root/'php'
            php.write_text('#!/bin/sh\nprintf "%s\\n" "$$" > "'+str(root/'worker')+'"\nsleep 60 &\nprintf "%s\\n" "$!" > "'+str(root/'child')+'"\nkill -STOP "$$"\nwait\n')
            php.chmod(0o700)
            bb=os.environ.get('BUSYBOX_TEST_BINARY',str(ROOT/'.work/packaging-audit-20261012/aarch64-busybox-wrapper'))
            code=(ROOT/'asus/smartdns/worker.sh').read_text().replace('/opt/libexec/nfqws2-asus/busybox',bb).replace('/opt/lib/nfqws2-asus/smartdns-engine',str(root)).replace('/opt/bin/php-cgi',str(php)).replace('+150','+2')
            script=root/'guard.sh';script.write_text(code)
            p=subprocess.Popen(['/bin/sh',str(script),job],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                try:out,err=p.communicate(timeout=7)
                except subprocess.TimeoutExpired:self.fail('guardian did not enforce its monotonic deadline')
                self.assertEqual(err,b'');self.assertEqual(p.returncode,0)
                self.assertEqual((root/('outcome-'+job)).read_text().strip(),'timed_out')
                for name in ['worker','child']:
                    pid=int((root/name).read_text());stat=Path('/proc')/str(pid)/'stat'
                    if stat.exists():self.assertEqual(stat.read_text().rsplit(')',1)[1].split()[0],'Z')
            finally:
                for name in ['worker','child']:
                    if (root/name).exists():
                        try:os.kill(int((root/name).read_text()),signal.SIGKILL)
                        except ProcessLookupError:pass
                if p.poll() is None:p.kill()
                p.communicate()
