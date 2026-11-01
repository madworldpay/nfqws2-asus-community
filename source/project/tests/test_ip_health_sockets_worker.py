"""Run the fixed detached coordinator in a private root, with real mutexes/opkg/PHP."""
import fcntl
import json
import os
from pathlib import Path
import signal
import shlex
import subprocess
import time
import unittest
import test_ip_health_sockets as fixtures
from test_dpi_normalize import PHP, PUBLIC, ROOT

class SocketsWorkerTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.IpHealthSocketsTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.f=self.fixture;self.opt=self.f.opt;self.base=self.f.base;self.updates=self.opt/'var/lib/nfqws2-asus/updates'
        self.source=ROOT/'asus/ip-health-sockets/worker.php';self.assertTrue(self.source.is_file(),'fixed sockets coordinator missing')
        self.worker=self.base/'worker.php';source=self.source.read_text().replace('/opt/',str(self.opt)+'/')
        source=source.replace(str(self.opt)+'/share/nfqws-asus-web/',str(PUBLIC)+'/')
        source=source.replace('0\\s+0\\s+0\\s+0',str(os.getuid())+'\\s+'+str(os.getuid())+'\\s+'+str(os.getuid())+'\\s+'+str(os.getuid()))
        source=source.replace('new AsusUpdateStore()', 'new AsusUpdateStore('+repr(str(self.updates))+','+str(os.getuid())+')')
        source=source.replace('new NfqwsIpHealthSockets()', 'new NfqwsIpHealthSockets(json_decode(file_get_contents('+repr(str(self.f.options_file))+'),true))')
        self.worker.write_text(source)
    def consent(self,enabled):
        directory=self.opt/'etc/nfqws2/ip-health';directory.mkdir(parents=True,mode=0o700);directory.parent.chmod(0o755)
        path=directory/'bans.json';path.write_text(json.dumps({'schema_version':1,'enabled':enabled,'generation':'none','entries':{},'history':{},'recheck':[]}));path.chmod(0o600)
    def run_worker(self,*args,env=None):return subprocess.run([PHP,'-n','-d','register_argc_argv=1',str(self.worker),'--',*args],capture_output=True,text=True,env=env,timeout=15)
    def test_disabled_saved_setting_and_stopped_default_do_not_acquire_module(self):
        p=self.run_worker('run');self.assertEqual(p.returncode,2,p.stdout+p.stderr);self.assertFalse(self.f.state.exists());self.assertFalse(self.f.installed())
        self.consent(False);p=self.run_worker('run');self.assertEqual(p.returncode,2,p.stdout+p.stderr);self.assertFalse(self.f.state.exists());self.assertFalse(self.f.installed())
    def test_saved_enabled_installs_without_starting_core(self):
        self.consent(True);p=self.run_worker('run');self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(json.loads(p.stdout),{'state':'ready','code':None});self.assertTrue(self.f.installed());self.assertFalse((self.opt/'etc/init.d').exists())
    def test_shared_updater_lease_prevents_install_until_real_exclusive_holder_releases(self):
        self.consent(True);self.updates.mkdir(parents=True,mode=0o700);(self.updates/'operations').mkdir(mode=0o700)
        (self.opt/'var').chmod(0o755);(self.opt/'var/lib').chmod(0o755);(self.opt/'var/lib/nfqws2-asus').chmod(0o755)
        lock=self.updates/'apply.lock';lock.touch(mode=0o600)
        with lock.open('r+') as f:
            fcntl.flock(f,fcntl.LOCK_EX);p=subprocess.Popen([PHP,'-n',str(self.worker),'--','run'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            time.sleep(.25);self.assertIsNone(p.poll());self.assertFalse(self.f.installed());fcntl.flock(f,fcntl.LOCK_UN)
        out,err=p.communicate(timeout=12);self.assertEqual(p.returncode,0,out+err);self.assertTrue(self.f.installed())
    def test_direct_preflight_and_http_invocation_cannot_authorize_boundary(self):
        self.consent(True);job=self.f.prepare();p=self.run_worker('preflight',job,'install');self.assertNotEqual(p.returncode,0);self.assertFalse((self.f.state/'operations'/job/'boundary.json').exists())
        p=self.run_worker('status',env=os.environ|{'REQUEST_METHOD':'GET'});self.assertNotEqual(p.returncode,0)
    def test_absent_default_requires_live_core_intent_and_successful_fixed_health_check(self):
        run=self.base/'core-run';run.mkdir(mode=0o700);self.f.options['run']=str(run);self.f.save_options()
        engine=self.opt/'usr/bin/nfqws2';engine.parent.mkdir(parents=True);engine.parent.parent.chmod(0o755);engine.parent.chmod(0o755)
        subprocess.run(['gcc','-x','c','-o',str(engine),'-'],input='#include <unistd.h>\nint main(void){sleep(15);return 0;}\n',text=True,capture_output=True,check=True);engine.chmod(0o755)
        init=self.opt/'etc/init.d/S51nfqws2';init.parent.mkdir();init.parent.chmod(0o755);init.write_text('#!/bin/sh\n[ "$1" = check ] || exit 9\nexit 1\n');init.chmod(0o755)
        core=subprocess.Popen([str(engine)]);self.addCleanup(lambda:core.poll() is None and (core.terminate(),core.wait()))
        for name,value in [('pid',str(core.pid)),('enabled','1')]:
            path=run/name;path.write_text(value);path.chmod(0o600)
        self.assertEqual(self.run_worker('run').returncode,2);self.assertFalse(self.f.installed())
        init.write_text('#!/bin/sh\n[ "$1" = check ] || exit 9\nexit 0\n')
        p=self.run_worker('run');self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertTrue(self.f.installed())
        self.assertFalse((self.opt/'etc/nfqws2/ip-health/bans.json').exists(),'default admission does not invent saved user settings')
    def test_reconcile_runs_only_after_native_and_both_worker_leases_are_released(self):
        self.consent(True);control_source=ROOT/'asus/ip-health-sockets/control.sh';self.assertTrue(control_source.is_file())
        control=self.base/'control.sh';script=control_source.read_text().replace('/opt/',str(self.opt)+'/').replace(str(self.opt)+'/lib/nfqws2-asus/ip-health-sockets/worker.php',str(self.worker)).replace(str(self.opt)+'/bin/php-cgi',PHP)
        control.write_text(script);control.chmod(0o700)
        init=self.opt/'etc/init.d/S51nfqws2';init.parent.mkdir();init.parent.chmod(0o755)
        checks='import fcntl;from pathlib import Path;paths='+repr([str(self.updates/'apply.lock'),str(self.f.state/'apply.lock'),str(self.opt/'tmp/opkg.lock')])+';handles=[open(p,"a+") for p in paths];[fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB) for f in handles[:2]];fcntl.lockf(handles[2],fcntl.LOCK_EX|fcntl.LOCK_NB);Path('+repr(str(self.base/'reconciled'))+').write_text("released")'
        init.write_text('#!/bin/sh\n[ "$1" = reconcile ] || exit 9\nexec '+shlex.join(['/usr/bin/python3','-c',checks])+'\n');init.chmod(0o755)
        p=subprocess.run([str(control),'run'],capture_output=True,text=True,timeout=15);self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual((self.base/'reconciled').read_text(),'released')
    def test_queue_survives_original_shell_session_hup(self):
        self.consent(True);control_source=ROOT/'asus/ip-health-sockets/control.sh';self.assertTrue(control_source.is_file())
        control=self.base/'control.sh';script=control_source.read_text().replace('/opt/',str(self.opt)+'/').replace(str(self.opt)+'/lib/nfqws2-asus/ip-health-sockets/control.sh',str(control)).replace(str(self.opt)+'/lib/nfqws2-asus/ip-health-sockets/worker.php',str(self.worker)).replace(str(self.opt)+'/bin/php-cgi',PHP).replace(str(self.opt)+'/libexec/nfqws2-asus/busybox','/bin/busybox')
        control.write_text(script);control.chmod(0o700)
        (self.opt/'var/run').mkdir(parents=True);(self.opt/'var').chmod(0o755);(self.opt/'var/run').chmod(0o755)
        p=subprocess.Popen(['/bin/sh','-c',str(control)+' queue; echo queued; sleep 15'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        try:
            self.assertEqual(p.stdout.readline().strip(),b'queued');os.killpg(p.pid,signal.SIGHUP);p.communicate(timeout=3)
            deadline=time.monotonic()+8
            while time.monotonic()<deadline and not self.f.installed():time.sleep(.05)
            self.assertTrue(self.f.installed(),'detached capability worker did not survive HUP')
        finally:
            if p.poll() is None:p.kill();p.communicate()
