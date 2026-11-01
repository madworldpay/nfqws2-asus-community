"""Quiesce only the exact legacy queued CLI worker, using real child processes."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from test_dpi_normalize import PUBLIC, ROOT
from test_package_update_guard import NATIVE


@unittest.skipUnless(NATIVE.is_file(),'native PHP fixture required for executable identity')
class UpdateSmartDnsResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.php=self.root/'php-cgi'
        shutil.copyfile(NATIVE,self.php);self.php.chmod(0o700)
        self.control=self.root/'control.php';self.lock=self.root/'apply.lock';self.lock.touch(mode=0o600)
        self.control.write_text('<?php touch(__FILE__.".".getmypid().".ready");$f=fopen(__DIR__."/apply.lock","r");while(!flock($f,LOCK_SH|LOCK_NB))usleep(100000);file_put_contents(__FILE__.".action","unexpected");sleep(5);')
        self.held=self.lock.open('r');fcntl.flock(self.held,fcntl.LOCK_EX);self.addCleanup(self.held.close)
        self.children=[];self.addCleanup(self.cleanup_children)

    def cleanup_children(self):
        for child in self.children:
            if child.poll() is None:child.kill()
            child.wait(timeout=3)

    def worker(self,mode='resume',extra=(),executable=None,ignore_term=False):
        args=[str(self.php),'-n','-d','register_argc_argv=1','-q','-f',str(self.control),'--',mode,*extra]
        setup=(lambda:signal.signal(signal.SIGTERM,signal.SIG_IGN)) if ignore_term else None
        child=subprocess.Popen(args,executable=executable,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,preexec_fn=setup)
        self.children.append(child);end=time.monotonic()+3
        while not Path(str(self.control)+'.'+str(child.pid)+'.ready').exists() and child.poll() is None and time.monotonic()<end:time.sleep(.01)
        self.assertIsNone(child.poll(),'fixture must be waiting on the real apply lease')
        return child

    def call(self,_runtime=None,**overrides):
        options={'php':str(self.php),'script':str(self.control),'owner':os.getuid(),'seconds':1.5}|overrides
        code='''$p=$argv[1].'/update-smartdns-resume.php';if(!is_file($p)){echo json_encode(['error'=>'missing_resume_quiescer']);exit;}require $p;try{echo json_encode((new AsusUpdateSmartDnsResume(json_decode(stream_get_contents(STDIN),true)))->quiesce());}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        result=subprocess.run((_runtime or [str(NATIVE)])+['-n','-r',code,str(PUBLIC)],input=json.dumps(options),capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertEqual(result.stderr,'')
        return json.loads(result.stdout)

    def test_exact_legacy_resume_is_stopped_and_foreign_php_is_preserved(self):
        target=self.worker();foreign=self.worker('status');extra=self.worker(extra=('foreign',))
        self.assertEqual(self.call(),{'matched':1,'stopped':1})
        target.wait(timeout=2);self.assertIsNone(foreign.poll());self.assertIsNone(extra.poll())
        self.assertFalse(Path(str(self.control)+'.action').exists())

    def test_same_argv_with_different_executable_or_owner_is_not_signalled(self):
        other=self.root/'other-php';shutil.copyfile(NATIVE,other);other.chmod(0o700)
        foreign=self.worker(executable=str(other))
        self.assertEqual(self.call(),{'matched':0,'stopped':0});self.assertIsNone(foreign.poll())
        target=self.worker()
        self.assertEqual(self.call(owner=os.getuid()+1),{'matched':0,'stopped':0});self.assertIsNone(target.poll())

    def test_unresponsive_owned_worker_fails_closed_within_deadline(self):
        target=self.worker(ignore_term=True);start=time.monotonic()
        self.assertEqual(self.call(seconds=.35),{'error':'dns_resume_stop_failed'})
        self.assertLess(time.monotonic()-start,2);self.assertIsNone(target.poll())
        self.assertFalse(Path(str(self.control)+'.action').exists())

    def test_process_bound_failure_never_signals_a_partial_match_set(self):
        target=self.worker()
        self.assertEqual(self.call(max_processes=1),{'error':'dns_resume_stop_failed'})
        self.assertIsNone(target.poll())

    def test_arm32_php_deadlines_can_scan_and_stop_exact_worker(self):
        fixtures=ROOT/'.work/packaging-audit-20261012';qemu=fixtures/'qemu-arm'
        roots=[fixtures/'armv7-legacy-sysroot',fixtures/'armv7-sysroot']
        if not qemu.is_file() or any(not (root/'opt/bin/php8-cli').is_file() for root in roots):
            self.skipTest('ARM32 QEMU and both Entware PHP runtimes required')
        for root in roots:
            with self.subTest(runtime=root.name):
                runtime=[str(qemu),'-L',str(root),str(root/'opt/bin/php8-cli')]
                proof=subprocess.run(runtime+['-n','-r','echo PHP_INT_SIZE," ",gettype(hrtime(true));'],capture_output=True,text=True,timeout=5)
                self.assertEqual((proof.returncode,proof.stdout,proof.stderr),(0,'4 double',''))
                target=self.worker();foreign=self.worker('status')
                self.assertEqual(self.call(_runtime=runtime),{'matched':1,'stopped':1})
                target.wait(timeout=2);self.assertIsNone(foreign.poll())
                stubborn=self.worker(ignore_term=True);start=time.monotonic()
                self.assertEqual(self.call(_runtime=runtime,seconds=.15),{'error':'dns_resume_stop_failed'})
                self.assertLess(time.monotonic()-start,2);self.assertIsNone(stubborn.poll())
                stubborn.kill();stubborn.wait(timeout=2)
