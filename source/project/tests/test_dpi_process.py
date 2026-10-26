import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from test_dpi_normalize import PHP, PUBLIC, ROOT


def stage_paths(base,busybox,worker=None,probe=None):
    text=(ROOT/'asus/dpi/paths.sh').read_text().replace('/opt/libexec/nfqws2-asus/busybox',str(busybox)).replace('/opt/var/lib/nfqws2-asus/dpi-detector',str(base/'state'))
    if worker is not None:text=text.replace('/opt/bin/php-cgi',str(worker))
    # A fixture directory holds only trusted worker/probe test programs.
    text=text.replace('/opt/lib/nfqws2-asus/dpi',str(base))
    if probe is not None:
        (base/'probe.sh').write_bytes(probe.read_bytes())
    (base/'paths.sh').write_text(text)


class DpiProcessTests(unittest.TestCase):
    def test_guard_deadline_is_reported_as_timeout_before_outcome_is_published(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);run=base/'state'/'runs'/('d'*32);run.mkdir(parents=True,mode=0o700)
            for name,text in [('ack','ready'),('closing','closed'),('ending.reason','timed_out')]:
                (run/name).write_text(text+'\n');(run/name).chmod(0o600)
            for name in ['dpi-store.php','dpi-options.php','support-json-schema.php','platform.php']:(base/name).write_bytes((PUBLIC/name).read_bytes())
            (base/'dpi-runtime.php').write_text((PUBLIC/'dpi-runtime.php').read_text().replace('/opt/var/lib/nfqws2-asus/dpi-detector',str(base/'state')))
            code="require $argv[1];try{(new AsusDpiRuntime())->probe(str_repeat('d',32),['/native'],'/',5);}catch(Throwable $e){echo $e->getMessage();}"
            p=subprocess.run([PHP,'-n','-r',code,str(base/'dpi-runtime.php')],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout,'timed_out')
    def test_explicit_cancel_is_not_reported_as_unexpected_interruption(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);run=base/'state'/'runs'/('d'*32);run.mkdir(parents=True,mode=0o700)
            for name in ['ack','cancel']:(run/name).write_text('ready\n');(run/name).chmod(0o600)
            for name in ['dpi-store.php','dpi-options.php','support-json-schema.php','platform.php']:(base/name).write_bytes((PUBLIC/name).read_bytes())
            (base/'dpi-runtime.php').write_text((PUBLIC/'dpi-runtime.php').read_text().replace('/opt/var/lib/nfqws2-asus/dpi-detector',str(base/'state')))
            code='''require $argv[1];try{(new AsusDpiRuntime())->probe(str_repeat('d',32),['/synthetic-binary','--version'],'/',5);}catch(Throwable $e){echo $e->getMessage();}'''
            p=subprocess.run([PHP,'-n','-r',code,str(base/'dpi-runtime.php')],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'');self.assertEqual(p.stdout,'cancelled')

    def test_late_probe_cannot_execute_after_guard_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);run=base/'state'/'runs'/('c'*32);run.mkdir(parents=True,mode=0o700)
            (run/'args').write_text('/usr/bin/true\n');(run/'args').chmod(0o600)
            (run/'closing').write_text('closed\n')
            busybox=Path(os.environ.get('BUSYBOX_TEST_BINARY',str(ROOT/'.work/packaging-audit-20261012/aarch64-busybox-wrapper')))
            script=(ROOT/'asus/dpi/probe.sh').read_text().replace('/opt/libexec/nfqws2-asus/busybox',str(busybox)).replace('/opt/var/lib/nfqws2-asus/dpi-detector',str(base/'state')).replace('= 0 ]','= '+str(os.getuid())+' ]').replace('= 0 ]','= '+str(os.getuid())+' ]')
            script=script[:script.index('ulimit -S -v')]+f'printf escaped > "{run}/escaped"\n'
            stage_paths(base,busybox);copy=base/'probe.sh';copy.write_text(script)
            p=subprocess.run([str(busybox),'sh',str(copy),'c'*32],capture_output=True,text=True)
            self.assertFalse((run/'escaped').exists(),'late probe executed after guardian closed admission')

    def test_nonroot_launcher_fails_closed_without_starting_probe(self):
        p=subprocess.run([PHP,'-n','-r',"require $argv[1].'/dpi-runtime.php';echo json_encode((new AsusDpiRuntime())->capabilities());",str(PUBLIC)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('root_required',p.stdout)

    def test_guard_survives_controller_exit_and_kills_term_ignoring_registered_probe(self):self.guard_case('overall')
    def test_group_deadline_survives_dead_php_worker(self):self.guard_case('group')
    def test_worker_killed_before_pid_ack_leaves_no_unbounded_probe(self):self.guard_case('worker_dies')
    def test_guard_owns_delayed_child_before_registration(self):self.guard_case('delayed')
    def test_next_group_deadline_is_not_removed_by_previous_group(self):self.guard_case('next_group')
    def test_output_quota_stops_the_job(self):self.guard_case('output')
    def test_cancel_stops_registered_probe(self):self.guard_case('cancel')

    def guard_case(self,mode):
        guard=ROOT/'asus/dpi/guard.sh';self.assertTrue(guard.is_file(),'independent guardian missing')
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);run=base/'state'/'runs'/('a'*32);run.mkdir(parents=True,mode=0o700)
            probe=base/'probe';probe.write_text("#!/bin/sh\ntrap '' TERM\nprintf '%s\\n' \"$$\" > \"RUN/child-seen\"\n".replace('RUN',str(run))+('while [ ! -f "'+str(run)+'/release" ]; do sleep 0.01; done\nprintf escaped > "'+str(run)+'/escaped"\n' if mode=='delayed' else '')+'exec sleep 30\n');probe.chmod(0o755)
            worker=base/'worker';worker.write_text(('#!/bin/sh\n[ -f "RUN/ack" ] || exit 91\nprintf / > "RUN/probe.cwd"\nprintf ready > "RUN/probe.request"\nwhile [ ! -f "RUN/child-seen" ]; do sleep 0.01; done\n'+('exit 1\n' if mode in ['worker_dies','delayed'] else 'while [ ! -f "RUN/probe.exit" ]; do sleep 0.01; done\n')).replace('RUN',str(run)));worker.chmod(0o755)
            busybox=Path(os.environ.get('BUSYBOX_TEST_BINARY',str(ROOT/'.work/packaging-audit-20261012/aarch64-busybox-wrapper')))
            copy=base/'guard.sh';copy.write_text(guard.read_text().replace('/opt/libexec/nfqws2-asus/busybox',str(busybox)).replace('/opt/var/lib/nfqws2-asus/dpi-detector',str(base/'state')).replace('/opt/bin/php-cgi',str(worker)).replace('/opt/lib/nfqws2-asus/dpi/worker.php',str(base/'ignored.php')).replace('/opt/lib/nfqws2-asus/dpi/probe.sh',str(probe)))
            stage_paths(base,busybox,worker,probe)
            if mode=='next_group':
                probe.write_text(('#!/bin/sh\nif [ ! -e "RUN/first-done" ]; then touch "RUN/first-done"; exit 0; fi\ntrap "" TERM\nprintf "%s\\n" "$$" > "RUN/child-seen"\nexec sleep 30\n').replace('RUN',str(run)))
                worker.write_text(('#!/bin/sh\nprintf / > "RUN/probe.cwd"\nprintf ready > "RUN/probe.request"\nwhile [ ! -f "RUN/probe.exit" ]; do sleep 0.01; done\nrm "RUN/probe.exit"\nawk \'{print $1+1}\' /proc/uptime > "RUN/probe.deadline"\nprintf ready > "RUN/probe.request"\nwhile [ ! -f "RUN/probe.exit" ]; do sleep 0.01; done\n').replace('RUN',str(run)))
                (base/'probe.sh').write_bytes(probe.read_bytes())
                copy.write_text(copy.read_text().replace('"$bb" mv "$run/probe.exit.new" "$run/probe.exit"','"$bb" mv "$run/probe.exit.new" "$run/probe.exit"\n        "$bb" usleep 200000'))
            now=float(Path('/proc/uptime').read_text().split()[0]);(run/'deadline').write_text(str(now+(1.5 if mode=='overall' else 20)));(run/'deadline').chmod(0o600)
            if mode=='group':(run/'probe.deadline').write_text(str(now+1.5));(run/'probe.deadline').chmod(0o600)
            start=time.monotonic();p=subprocess.run([str(busybox),'start-stop-daemon','-S','-b','-x',str(busybox),'--','sh',str(copy),'a'*32],capture_output=True,timeout=3)
            try:
                self.assertEqual(p.returncode,0,p.stderr.decode())
                until=time.monotonic()+2
                while not (run/'child-seen').exists() and time.monotonic()<until:time.sleep(0.01)
                if mode=='cancel':(run/'cancel').write_text('cancel\n');(run/'cancel').chmod(0o600)
                if mode=='output':(run/'g0.stderr').write_bytes(b'x'*65537);(run/'g0.stderr').chmod(0o600)
                end=time.monotonic()+8
                while not (run/'outcome').exists() and time.monotonic()<end:time.sleep(0.05)
                self.assertTrue((run/'outcome').exists(),'detached guardian did not finish')
                self.assertEqual((run/'outcome').read_text().strip(),{'overall':'timed_out','group':'timed_out','cancel':'cancelled','output':'output_limit','worker_dies':'interrupted','delayed':'interrupted','next_group':'timed_out'}[mode])
                self.assertFalse((run/'g0.stderr').exists(),'raw stderr was retained after the guardian finished')
                self.assertGreaterEqual(time.monotonic()-start,3 if mode in ['overall','group'] else 1.9)
                if mode=='delayed':
                    (run/'release').touch();time.sleep(0.1);self.assertFalse((run/'escaped').exists())
                child=int((run/'child-seen').read_text())
                stat=Path(f'/proc/{child}/stat')
                self.assertTrue(not stat.exists() or stat.read_text().split(') ')[1].startswith('Z '),'probe remained live')
            finally:
                if (run/'guard.pid').exists():
                    try:os.kill(int((run/'guard.pid').read_text().split()[0]),signal.SIGKILL)
                    except ProcessLookupError:pass
                if (run/'child-seen').exists():
                    try:os.kill(int((run/'child-seen').read_text()),signal.SIGKILL)
                    except ProcessLookupError:pass

    def test_reused_pid_is_not_signalled(self):
        guard=ROOT/'asus/dpi/guard.sh';self.assertTrue(guard.is_file())
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);run=base/'state'/'runs'/('b'*32);run.mkdir(parents=True,mode=0o700)
            canary=subprocess.Popen(['sleep','15'])
            worker=base/'worker';worker.write_text('#!/bin/sh\nexit 1\n');worker.chmod(0o755)
            (run/'probe.pid').write_text(f'{canary.pid} 1\n');(run/'probe.pid').chmod(0o600)
            (run/'deadline').write_text(str(float(Path('/proc/uptime').read_text().split()[0])+2));(run/'deadline').chmod(0o600)
            busybox=Path(os.environ.get('BUSYBOX_TEST_BINARY',str(ROOT/'.work/packaging-audit-20261012/aarch64-busybox-wrapper')))
            copy=base/'guard.sh';copy.write_text(guard.read_text().replace('/opt/libexec/nfqws2-asus/busybox',str(busybox)).replace('/opt/var/lib/nfqws2-asus/dpi-detector',str(base/'state')).replace('/opt/bin/php-cgi',str(worker)))
            stage_paths(base,busybox,worker)
            try:
                p=subprocess.run([str(busybox),'sh',str(copy),'b'*32],capture_output=True,text=True,timeout=6)
                self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'');self.assertIsNone(canary.poll())
            finally:canary.terminate();canary.wait()

    def test_drop_refuses_an_identity_other_than_65534(self):
        busybox=Path(os.environ.get('BUSYBOX_TEST_BINARY',str(ROOT/'.work/packaging-audit-20261012/aarch64-busybox-wrapper')))
        p=subprocess.run([str(busybox),'sh',str(ROOT/'asus/dpi/drop.sh'),str(busybox),'true'],capture_output=True,text=True)
        self.assertEqual(p.returncode,126,'preflight allowed a probe without the promised UID/GID')
