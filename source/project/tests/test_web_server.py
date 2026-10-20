import unittest
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import os
import socket
import time
import urllib.request
import urllib.error
import test_platform as platform
from test_packages import read_ipk
ROOT = platform.ROOT


class WebServerTests(unittest.TestCase):
    run_sh = platform.PlatformTests.run_sh
    def test_packaged_lighttpd_serves_generated_config_with_shipped_modules(self):
        audit = ROOT/'.work/packaging-audit-20261012'
        if not (audit/'qemu-arm').exists():
            self.skipTest('QEMU ARM runtime not supplied')
        package_dir = Path(os.environ.get('PACKAGES_DIR', ROOT/'dist'))
        packages = list(package_dir.glob('nfqws2-asus_*_armv7.ipk'))
        self.assertEqual(len(packages), 1)
        data = read_ipk(packages[0])['data']
        for abi, sysroot in [('armv7-2.6', 'armv7-legacy-sysroot'),
                             ('armv7-3.2', 'armv7-sysroot')]:
            with self.subTest(abi=abi), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                binary = root/'lighttpd'
                binary.write_bytes(data[f'opt/libexec/nfqws-asus-web/{abi}/lighttpd'][1])
                binary.chmod(0o755)
                modules = root/'modules'; modules.mkdir()
                prefix = f'opt/lib/nfqws-asus-web/lighttpd/{abi}/'
                for name, (info, content) in data.items():
                    if name.startswith(prefix) and name.endswith('.so'):
                        (modules/Path(name).name).write_bytes(content)
                (root/'opt/share/nfqws-asus-web').mkdir(parents=True)
                generated = self.run_sh(
                    f'. "{ROOT / "asus/web-lib.sh"}"\nweb_config\n',
                    {'WEB_RUN': td, 'WEB_BIND': '127.0.0.1'})
                self.assertEqual(generated.returncode, 0, generated.stderr)
                config = root/'lighttpd.conf'
                config.write_text(generated.stdout.replace('/opt/', td+'/opt/'))
                result = subprocess.run(
                    [str(audit/'qemu-arm'), '-L', str(audit/sysroot),
                     str(binary), '-m', str(modules), '-tt', '-f', str(config)],
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                # Check runtime module loading and HTTP, as well as syntax.
                (root/'opt/share/nfqws-asus-web/index.html').write_text('ready')
                with socket.socket() as listener:
                    listener.bind(('127.0.0.1', 0))
                    port = listener.getsockname()[1]
                config.write_text(config.read_text().replace(
                    'server.port = 90', f'server.port = {port}'))
                process = subprocess.Popen(
                    [str(audit/'qemu-arm'), '-L', str(audit/sysroot),
                     str(binary), '-m', str(modules), '-D', '-f', str(config)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    deadline = time.monotonic()+5
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            self.fail(process.communicate()[1])
                        try:
                            with opener.open(f'http://127.0.0.1:{port}/', timeout=.3) as response:
                                self.assertEqual(response.read(), b'ready')
                            break
                        except (urllib.error.URLError, TimeoutError):
                            time.sleep(.05)
                    else:
                        self.fail('Packaged lighttpd did not serve HTTP')
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.communicate(timeout=5)

    def test_web_selects_matching_binary_and_module_for_each_entware_abi(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for abi in ['armv7-2.6', 'armv7-3.2', 'aarch64-3.10']:
                family = 'armv7' if abi.startswith('armv7') else abi
                lib = root/'opt/lib/nfqws2-asus'; lib.mkdir(parents=True, exist_ok=True)
                (lib/'target.sh').write_text(f"ASUS_PACKAGE_ARCH='{family}'\n")
                (lib/'abi.sh').write_text((ROOT/'asus/abi.sh').read_text().replace('/opt/',td+'/opt/'))
                cfg = root/'opt/etc/opkg.conf'; cfg.parent.mkdir(parents=True,exist_ok=True)
                cfg.write_text(f'arch all 100\narch {abi} 160\n')
                body = (ROOT/'asus/web-lib.sh').read_text().replace('/opt/',td+'/opt/')
                body += '\nweb_runtime || exit $?\nprintf "%s\\n%s\\n" "$WEB_BIN" "$WEB_MODULE_DIR"\n'
                r = self.run_sh(body)
                self.assertEqual(r.returncode,0,r.stderr)
                suffix = '/'+abi if family=='armv7' else ''
                self.assertEqual(r.stdout.splitlines(),[td+'/opt/libexec/nfqws-asus-web'+suffix+'/lighttpd',
                                                      td+'/opt/lib/nfqws-asus-web/lighttpd'+suffix])

    def test_stop_recognizes_own_previous_abi_process(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); run = root/'run'; run.mkdir()
            old = root/'opt/libexec/nfqws-asus-web/armv7-2.6/lighttpd'
            old.parent.mkdir(parents=True); shutil.copyfile(sys.executable,old); old.chmod(0o755)
            modern = root/'opt/libexec/nfqws-asus-web/armv7-3.2/lighttpd'
            modern.parent.mkdir(); shutil.copyfile(sys.executable,modern); modern.chmod(0o755)
            # A relocated venv interpreter still needs its original stdlib.
            process = subprocess.Popen([str(old),'-c','import time;time.sleep(30)','-f',str(run/'lighttpd.conf')],
                                       env={**os.environ,'PYTHONHOME':sys.base_prefix})
            try:
                (run/'pid').write_text(str(process.pid))
                body=(ROOT/'asus/web-lib.sh').read_text().replace('/opt/',td+'/opt/')
                env={'WEB_BIN':str(modern),'WEB_RUN':str(run)}
                result=self.run_sh(body+'\nweb_running && exit 8\nweb_owned_running\n',env)
                self.assertEqual(result.returncode,0,result.stderr)
                result=self.run_sh(body+'\nweb_owned_running\n',{**env,'WEB_RUN':str(root/'other')})
                self.assertEqual(result.returncode,1,result.stderr)
                result=self.run_sh(body+'\nweb_kill\n',env)
                self.assertEqual(result.returncode,0,result.stderr)
                process.wait(timeout=5)
                self.assertFalse((run/'pid').exists())
            finally:
                if process.poll() is None: process.terminate(); process.wait(timeout=5)
    def test_web_listener_is_bound_to_router_lan(self):
        lib = ROOT / 'asus/web-lib.sh'
        r = self.run_sh(f'''
        [ ! -f "{lib}" ] || . "{lib}"
        nvram() {{ echo 192.0.2.1; }}
        WEB_RUN=/tmp/nfqws-asus-web; WEB_BIND=$(web_lan)
        web_config
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('server.bind = "192.0.2.1"', r.stdout)
        self.assertNotIn('0.0.0.0', r.stdout)
        self.assertIn('server.port = 90', r.stdout)

    def test_unsuitable_lan_addresses_fail_closed(self):
        lib = ROOT / 'asus/web-lib.sh'
        for addr in ['0.0.0.0', '255.255.255.255', '127.0.0.1', '192.0.2.999', '192.0.2.1\nserver.port=80']:
            r = self.run_sh(f'''
            [ ! -f "{lib}" ] || . "{lib}"
            nvram() {{ printf '%s' "$ADDR"; }}
            web_lan
            ''', {'ADDR':addr})
            self.assertEqual(r.returncode, 1, r.stderr)

    def test_temporary_lan_loss_keeps_recovery_enabled(self):
        lib = ROOT / 'asus/web-lib.sh'
        r = self.run_sh(f'''
        . "{lib}"
        WEB_RUN=$(mktemp -d); touch "$WEB_RUN/enabled"
        web_running() {{ return 0; }}; web_lan() {{ return 1; }}
        web_kill() {{ echo STOP; }}; web_start() {{ echo START; }}
        cru() {{ echo UNEXPECTED_CRON_DELETE; }}
        web_reconcile
        test -f "$WEB_RUN/enabled" && echo ENABLED
        rm -r "$WEB_RUN"
        ''')
        self.assertEqual(r.stdout.splitlines(), ['STOP', 'ENABLED'])

    def test_web_process_recognized_through_symlinked_install_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / 'runtime'
            runtime.mkdir()
            usb = Path(tmp) / 'usb'
            usb.mkdir()
            opt = Path(tmp) / 'opt'
            opt.symlink_to(usb, target_is_directory=True)
            (usb / 'server').symlink_to(sys.executable)
            server = subprocess.Popen([str(opt / 'server'), '-c',
                                       'import time; time.sleep(30)', '-f',
                                       str(runtime / 'lighttpd.conf')])
            try:
                (runtime / 'pid').write_text(str(server.pid))
                body = f'''
                . "{ROOT / 'asus/web-lib.sh'}"
                web_running
                '''
                env = {'WEB_BIN': str(opt / 'server'), 'WEB_RUN': str(runtime)}
                r = self.run_sh(body, env)
                self.assertEqual(r.returncode, 0, r.stderr)
                other = Path(tmp) / 'other'
                other.mkdir()
                (other / 'pid').write_text(str(server.pid))
                # The config argument must identify this service's runtime.
                r = self.run_sh(body, {**env, 'WEB_RUN': str(other)})
                self.assertEqual(r.returncode, 1, r.stderr)
            finally:
                server.terminate()
                server.wait(timeout=5)
