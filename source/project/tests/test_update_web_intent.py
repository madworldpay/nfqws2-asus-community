"""A busy or failed web status must not be mistaken for a stopped panel."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_package_update_guard import NATIVE
from test_dpi_normalize import PUBLIC

@unittest.skipUnless(NATIVE.is_file() and shutil.which('cc'), 'native PHP and C compiler required')
class UpdateWebIntentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.base.chmod(0o700)
        self.run=self.base/'web-run';self.run.mkdir(mode=0o700);self.init=self.base/'web-init';self.engine=self.base/'lighttpd';self.children=[];self.addCleanup(self.cleanup_children)
        subprocess.run(['cc','-x','c','-','-o',str(self.engine)],input='#include <unistd.h>\nint main(){for(;;)pause();}\n',text=True,capture_output=True,check=True,timeout=10)
        self.options={'owner':os.getuid(),'web_init':str(self.init),'web_run':str(self.run),'web_engine':str(self.engine),'service_timeout':.04}
        self.status('exit 1')
    def cleanup_children(self):
        for p in self.children:
            if p.poll() is None:p.terminate()
            p.wait(timeout=2)
    def status(self,body):self.init.write_text('#!/bin/sh\n'+body+'\n');self.init.chmod(0o700)
    def child(self,owned=True,pid=True):
        config=self.run/'lighttpd.conf' if owned else self.base/'other.conf'
        p=subprocess.Popen([str(self.engine),'-f',str(config)]);self.children.append(p)
        if pid:(self.run/'pid').write_text(str(p.pid));(self.run/'pid').chmod(0o600)
        return p
    def call(self):
        code='require $argv[1]."/update-lifecycle.php";try{$v=new AsusUpdateLifecycle(json_decode($argv[2],true));echo json_encode(["running"=>$v->webRunning()]);}catch(Throwable $e){echo json_encode(["error"=>$e->getMessage()]);}'
        r=subprocess.run([str(NATIVE),'-n','-r',code,str(PUBLIC),json.dumps(self.options)],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def test_cleanly_stopped_and_running_status(self):
        self.assertEqual(self.call(),{'running':False});self.status('exit 0');self.assertEqual(self.call(),{'running':True})
    def test_busy_timeout_and_other_status_are_unknown(self):
        for body in ['exit 75','sleep 1','exit 2']:
            with self.subTest(body=body):self.status(body);self.assertEqual(self.call(),{'error':'web_stop_failed'})
    def test_failed_status_with_live_owned_daemon_is_never_off_even_without_pid(self):
        for pid in [True,False]:
            with self.subTest(pid=pid):
                p=self.child(pid=pid);self.assertEqual(self.call(),{'error':'web_stop_failed'});self.assertIsNone(p.poll());p.terminate();p.wait(timeout=2)
                (self.run/'pid').unlink(missing_ok=True)
    def test_unrelated_daemon_is_untouched_and_unsafe_pid_is_rejected(self):
        p=self.child(owned=False);self.assertEqual(self.call(),{'running':False});self.assertIsNone(p.poll())
        (self.run/'pid').unlink();outside=self.base/'outside';outside.write_text('KEEP');(self.run/'pid').symlink_to(outside)
        self.assertEqual(self.call(),{'error':'web_stop_failed'});self.assertEqual(outside.read_text(),'KEEP');self.assertIsNone(p.poll())

if __name__=='__main__':unittest.main()
