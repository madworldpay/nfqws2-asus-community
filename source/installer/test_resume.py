"""Exercise the ASUS bootstrap's detached lifetime with real shell processes."""
import importlib.util
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
PROJECT=ROOT/'source/project'
PHP=Path(os.environ.get('PHP_NATIVE_TEST_BINARY',Path.home()/'.local/state/nfqws2-asus/development/package-updates-20261016/native-php/root/usr/bin/php8.5'))


class AsusResumeBootstrapTests(unittest.TestCase):
    def wait_file(self,path):
        end=time.monotonic()+5
        while not path.exists() and time.monotonic()<end:time.sleep(.02)
        self.assertTrue(path.exists(),f'Missing detached worker result: {path}')

    def test_detached_package_transaction_survives_parent_termination_with_archive_and_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);work=base/'transaction';work.mkdir(mode=0o700)
            package=work/'package.ipk';package.write_bytes(b'verified original artifact')
            marker=base/'started';result=base/'completed';lease=base/'bootstrap.lock';lease.touch(mode=0o600)
            child=base/'opkg-fixture.sh'
            child.write_text('#!/bin/sh\ntouch '+shlex.quote(str(marker))+'\nsleep .8\ncat "$1" > '+shlex.quote(str(result))+'\nprintf "opkg completed\\n"\n')
            child.chmod(0o700)
            source=(ROOT/'install.sh').read_text().split('# BEGIN GENERATED NATIVE OPENWRT INSTALLER')[0]
            source=source.split('# Keep the entry point last')[0]
            runner=base/'parent.sh'
            runner.write_text(source+'\nWORK='+shlex.quote(str(work))+'\nKEEP_WORK=0\nexec 9>>'+shlex.quote(str(lease))+'\nflock -n 9 || exit 1\ntrap cleanup 0\ntrap "exit 143" HUP TERM\nnfqws_asus_background '+shlex.quote(str(child))+' '+shlex.quote(str(package))+'\n')
            parent=subprocess.Popen(['/bin/sh',str(runner)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                self.wait_file(marker)
                os.killpg(parent.pid,signal.SIGHUP)
                parent.wait(timeout=3)
                # The detached child still owns the bootstrap lease after SSH.
                with lease.open('r+') as held:
                    with self.assertRaises(BlockingIOError):fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
                self.wait_file(result)
                self.assertEqual(result.read_bytes(),b'verified original artifact')
                self.assertEqual(package.read_bytes(),b'verified original artifact')
                self.wait_file(work/'job.status')
                self.assertEqual((work/'job.status').read_text(),'0\n')
                self.assertIn('opkg completed',(work/'job.log').read_text())
            finally:
                if parent.poll() is None:parent.kill();parent.wait()

    def test_stock_fallback_survives_ssh_hup_and_keeps_lease_with_or_without_setsid(self):
        for setsid in [False,True]:
            with self.subTest(setsid=setsid),tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp);work=base/'transaction';work.mkdir(mode=0o700);tools=base/'bin';tools.mkdir()
                for name in ['rm','cat','mv','sleep','tr','flock']:(tools/name).symlink_to(shutil.which(name))
                if setsid:(tools/'setsid').symlink_to(shutil.which('setsid'))
                busybox=base/'stock-busybox'
                busybox.write_text('#!/bin/sh\ncase "$1" in\n--list) printf "ash\\ncat\\n";;\nstart-stop-daemon) echo "applet not found" >&2; exit 127;;\n*) exec /bin/busybox "$@";;\nesac\n');busybox.chmod(0o700)
                package=work/'package.ipk';package.write_bytes(b'verified package')
                started=base/'started';completed=base/'completed';lease=base/'bootstrap.lock';lease.touch(mode=0o600)
                child=base/'opkg.sh';child.write_text('#!/bin/sh\nprintf started > '+shlex.quote(str(started))+'\n/bin/sleep .8\n/bin/cat "$1" > '+shlex.quote(str(completed))+'\nprintf "opkg completed\\n"\n');child.chmod(0o700)
                source=(ROOT/'install.sh').read_text().split('# BEGIN GENERATED ASUS RECOVERY INSTALLER')[0]
                source=source.replace('/bin/busybox',str(busybox)).replace('PATH=/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin','PATH='+str(tools))
                runner=base/'parent.sh';runner.write_text(source+'\nWORK='+shlex.quote(str(work))+'\nKEEP_WORK=0\nexec 9>>'+shlex.quote(str(lease))+'\nflock -n 9 || exit 1\ntrap cleanup 0\ntrap "exit 143" HUP TERM\nnfqws_asus_background '+shlex.quote(str(child))+' '+shlex.quote(str(package))+'\n')
                parent=subprocess.Popen(['/bin/busybox','ash',str(runner)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                try:
                    self.wait_file(started);os.killpg(parent.pid,signal.SIGHUP);parent.wait(timeout=3)
                    with lease.open('r+') as held:
                        with self.assertRaises(BlockingIOError):fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    self.wait_file(completed);self.wait_file(work/'job.status')
                    self.assertEqual(completed.read_bytes(),b'verified package');self.assertEqual((work/'job.status').read_text(),'0\n')
                    self.assertIn('opkg completed',(work/'job.log').read_text());self.assertEqual(work.stat().st_mode&0o777,0o700)
                finally:
                    if parent.poll() is None:parent.kill();parent.wait()

    def bundle(self):
        path=PROJECT/'asus/install-bundle.py'
        self.assertTrue(path.exists(),'ASUS needs its own trusted bootstrap closure before installed Build80 can recover')
        spec=importlib.util.spec_from_file_location('asus_bundle',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    @unittest.skipUnless(PHP.exists(),'native PHP required')
    def test_embedded_trusted_closure_extracts_and_refuses_changed_code(self):
        module=self.bundle()
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);bundle=work/'bundle.php'
            # Bind only the OS root/ownership boundary to this unprivileged fixture.
            code=module.render().decode().replace(r'Uid:\s+0\s+0\s+0\s+0',r'Uid:\s+'+str(os.getuid())+r'\s+'+str(os.getuid())+r'\s+'+str(os.getuid())+r'\s+'+str(os.getuid()))
            code=code.replace("['uid']!==0","['uid']!=="+str(os.getuid()))
            bundle.write_text(code)
            result=subprocess.run([str(PHP),'-n',str(bundle),'extract',str(work)],text=True,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual((work/'app/update-package.php').read_bytes(),(PROJECT/'webui/web/public/update-package.php').read_bytes())
            self.assertEqual((work/'resources/update-release-key.pem').read_bytes(),(PROJECT/'updates/trusted-release-key.pem').read_bytes())
            self.assertEqual((work/'worker.php').read_bytes(),(PROJECT/'asus/install-worker.php').read_bytes())
            self.assertEqual((work/'launchers/aarch64-opkg-launch').read_bytes(),(PROJECT/'asus/update/bin/aarch64-opkg-launch').read_bytes())
            before=(work/'app/update-package.php').read_bytes();(work/'app/update-package.php').write_bytes(before+b'\n// changed\n')
            refused=subprocess.run([str(PHP),'-n',str(bundle),'extract',str(work)],text=True,capture_output=True,timeout=10)
            self.assertNotEqual(refused.returncode,0)
            self.assertIn('runtime_changed',refused.stderr)

    def test_generated_bundle_is_reproducible_and_both_installers_match(self):
        module=self.bundle();self.assertEqual(module.render(),module.render())
        shell=module.shell();result=subprocess.run(['sh','-n'],input=shell,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        for path in [ROOT/'install.sh',ROOT/'source/installer/install.sh']:
            self.assertIn(shell,path.read_text())


if __name__=='__main__':unittest.main()
