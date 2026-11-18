"""Run the actual independent guardian against bounded private worker/probe fixtures."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from test_dpi_normalize import ROOT, PUBLIC, PHP
from test_dpi_process import stage_paths


class DpiLoadGuardTests(unittest.TestCase):
    def guard_case(self, mode):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);job='e'*32;run=base/'state'/'runs'/job;run.mkdir(parents=True,mode=0o700)
            memory=base/'memory';memory.write_text('MemAvailable: 1048576 kB\n')
            if mode!='legacy':
                (run/'load.plan').write_text('4 0\n'if mode!='invalid'else'999 0\n');(run/'load.plan').chmod(0o600)
            worker=base/'worker';worker.write_text('#!/bin/sh\nprintf yes > "'+str(run/'worker-seen')+'"\nprintf / > "'+str(run/'probe.cwd')+'"\nprintf ready > "'+str(run/'probe.request')+'"\nwhile [ ! -f "'+str(run/'probe.exit')+'" ]; do sleep 0.01; done\n');worker.chmod(0o755)
            probe=base/'fixture-probe';probe.write_text('#!/bin/sh\nprintf "%s" "${DPI_WORKERS:-}|$TOKIO_WORKER_THREADS" > "'+str(run/'threads')+'"\nprintf "%s" "$$" > "'+str(run/'child.pid')+'"\n'+('trap "" TERM\nexec sleep 30\n'if mode=='pressure'else'exit 0\n'));probe.chmod(0o755)
            busybox=Path(os.environ.get('BUSYBOX_TEST_BINARY','/usr/bin/busybox'))
            stage_paths(base,busybox,worker,probe)
            script=(ROOT/'asus/dpi/guard.sh').read_text().replace('/proc/meminfo',str(memory))
            guard=base/'guard.sh';guard.write_text(script)
            (run/'deadline').write_text(str(float(Path('/proc/uptime').read_text().split()[0])+5));(run/'deadline').chmod(0o600)
            p=subprocess.Popen([str(busybox),'sh',str(guard),job],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            child_fd=None
            try:
                until=time.monotonic()+2
                while not(run/'threads').exists()and p.poll()is None and time.monotonic()<until:time.sleep(.01)
                if (run/'child.pid').exists():
                    pid=int((run/'child.pid').read_text())
                    try:
                        fd=os.pidfd_open(pid)
                        fields=(Path('/proc')/str(pid)/'stat').read_text().split(') ')[1].split()
                        if int(fields[1])==p.pid:child_fd=fd
                        else:os.close(fd)
                    except (ProcessLookupError,FileNotFoundError):pass
                if mode=='pressure':memory.write_text('MemAvailable: 1024 kB\n')
                stdout,stderr=p.communicate(timeout=10)
                self.assertEqual(stderr,b'');self.assertTrue((run/'outcome').exists())
                outcome=(run/'outcome').read_text().strip()
                if mode=='invalid':
                    self.assertFalse((run/'worker-seen').exists(),'invalid execution plan admitted a worker')
                    self.assertFalse((run/'threads').exists());self.assertEqual(outcome,'invalid_state')
                elif mode=='pressure':
                    self.assertEqual(outcome,'timed_out')
                    pid=int((run/'child.pid').read_text());stat=Path('/proc')/str(pid)/'stat'
                    self.assertTrue(not stat.exists()or stat.read_text().split(') ')[1].startswith('Z '),'owned probe survived its original deadline')
                else:
                    self.assertEqual((run/'threads').read_text(),'|1'if mode=='legacy'else'4|4')
                    self.assertEqual(outcome,'completed')
            finally:
                if p.poll()is None:p.terminate();p.wait(timeout=5)
                if child_fd is not None:
                    try:signal.pidfd_send_signal(child_fd,signal.SIGKILL)
                    except ProcessLookupError:pass
                    finally:os.close(child_fd)

    def test_advanced_server_plan_selects_four_workers(self):self.guard_case('advanced')
    def test_legacy_job_keeps_native_default_and_existing_tokio_hint(self):self.guard_case('legacy')
    def test_low_reported_memory_keeps_work_until_its_original_deadline(self):self.guard_case('pressure')
    def test_invalid_plan_never_launches_worker_or_probe(self):self.guard_case('invalid')

    def test_memory_failure_is_visible_before_guard_outcome_publish(self):
        with tempfile.TemporaryDirectory()as tmp:
            base=Path(tmp);run=base/'state/runs'/('d'*32);run.mkdir(parents=True,mode=0o700)
            for name,value in [('ack','ready'),('closing','closed'),('ending.reason','insufficient_memory')]:
                (run/name).write_text(value+'\n');(run/name).chmod(0o600)
            for name in ['dpi-store.php','dpi-options.php','dpi-load-policy.php','support-json-schema.php','platform.php']:(base/name).write_bytes((PUBLIC/name).read_bytes())
            (base/'dpi-runtime.php').write_text((PUBLIC/'dpi-runtime.php').read_text().replace('/opt/var/lib/nfqws2-asus/dpi-detector',str(base/'state')))
            r=subprocess.run([PHP,'-n','-r',"require $argv[1];try{(new AsusDpiRuntime())->probe(str_repeat('d',32),['/native'],'/',5);}catch(Throwable $e){echo $e->getMessage();}",str(base/'dpi-runtime.php')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,'insufficient_memory')


if __name__=='__main__':unittest.main()
