"""Run the real installer against a disposable router filesystem and HTTP/opkg boundaries."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / 'install.sh'
VERSION = '1.3.2-asus6+b67'


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.installer=INSTALLER
        self.isolated_checksum_tools=False
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.router = self.work / 'router'
        self.bin = self.work / 'bin'
        self.bin.mkdir()
        for name in ['opt/bin', 'opt/tmp', 'opt/etc/init.d', 'opt/etc/nfqws2', 'opt/lib/opkg/info', 'proc']:
            (self.router / name).mkdir(parents=True, exist_ok=True)
        (self.router / 'proc/self').mkdir()
        (self.router / 'proc/self/status').write_text('Uid:\t0\t0\t0\t0\n')
        (self.router / 'proc/meminfo').write_text('MemAvailable: 131072 kB\nMemFree: 65536 kB\nBuffers: 8192 kB\nCached: 8192 kB\n')
        self.owner_file = self.router / 'opt/etc/nfqws2/owner.list'
        self.owner_file.write_text('keep.example\n')
        self.unrelated = self.router / 'opt/tmp/unrelated.ipk'
        self.unrelated.write_bytes(b'not ours')
        self.state = {'arches': 'arch all 100\narch aarch64-3.10 160\n', 'cpu': 'aarch64',
                      'version': '', 'enabled': False, 'free_kb': 1048576,
                      'install_error': False, 'download_error': False}
        self.state_path = self.work / 'state.json'
        self.log = self.work / 'events.jsonl'
        self.http = self.work / 'http'
        self.http.mkdir()
        sums = []
        for family in ['armv7', 'aarch64-3.10']:
            name = f'nfqws2-asus_{VERSION}_{family}.ipk'
            data = ('verified package ' + family).encode()
            (self.http / name).write_bytes(data)
            sums.append(hashlib.sha256(data).hexdigest() + '  ' + name)
        (self.http / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
        self.tool('curl', r'''
args=sys.argv[1:]
url=args[-1]
assert url.startswith('https://github.com/madworldpay/nfqws2-asus-community/releases/'), url
assert '-k' not in args and '--insecure' not in args
out=args[args.index('-o')+1]
emit({'kind':'download','url':url})
if state['download_error']:
    pathlib.Path(out).write_bytes(b'partial')
    sys.exit(22)
name=url.rsplit('/',1)[1]
src=work/'http'/name
if not src.exists():sys.exit(22)
pathlib.Path(out).write_bytes(src.read_bytes())
''')
        self.tool('opkg', r'''
args=sys.argv[1:]
tmp_dir=None
if args[:1]==['--tmp-dir']:tmp_dir=pathlib.Path(args[1]);args=args[2:]
action=args[0]
if action in ['update','install']:
    assert tmp_dir is not None and tmp_dir.is_dir(), args
    assert tmp_dir.name=='opkg' and tmp_dir.parent.name.startswith('nfqws2-asus-install.'), tmp_dir
    assert tmp_dir.parent.parent==work/'router/opt/tmp', tmp_dir
if action=='print-architecture':print(state['arches'],end='')
elif action=='status':
    if state['version']:print('Package: nfqws2-asus\nVersion: '+state['version']+'\nStatus: '+state.get('package_status','install ok installed')+'\n')
elif action=='compare-versions':
    def number(v):return int(v.rsplit('+b',1)[1])
    sys.exit(0 if number(args[1])>number(args[3]) else 1)
elif action=='update':
    emit({'kind':'update'})
    if state.get('update_error'):sys.exit(1)
elif action=='install':
    if args[1]=='coreutils-sha256sum':
        emit({'kind':'dependency','package':args[1]})
        if state.get('dependency_error'):sys.exit(1)
        if state.get('installed_hash_mode')!='missing':
            import shutil
            shutil.copy2(work/'dependency-sha256sum',work/'router/opt/bin/sha256sum')
        sys.exit()
    emit({'kind':'install','asset':pathlib.Path(args[1]).name,'no_start':os.environ.get('NFQWS_ASUS_NO_START')})
    if state['install_error']:
        import subprocess
        if state.get('stop_before_failure'):
            for name in ['S51nfqws2','S81nfqws-asus-web']:
                subprocess.run([str(work/'router/opt/etc/init.d'/name),'stop'],check=True)
            state=json.loads(state_path.read_text())
            state['package_status']=state.get('failure_status','deinstall user installed')
            state['version']=state.get('failure_version',state['version'])
            if state.get('change_payload'): (work/'router/opt/etc/init.d/S51nfqws2').write_text('#!/bin/sh\nexit 1\n')
            if state.get('delete_payload'): (work/'router/opt/etc/init.d/S51nfqws2').unlink()
            state_path.write_text(json.dumps(state))
        sys.exit(1)
    state['version']='1.3.2-asus6+b67'
    state['package_status']=state.get('post_install_status','install ok installed')
    state_path.write_text(json.dumps(state))
else:raise AssertionError(args)
''', self.router / 'opt/bin/opkg')
        self.tool('nvram', "assert sys.argv[1]=='get'; print({'productid':'GT-BE19000AI','odmpid':'','lan_ipaddr':'192.168.50.1','sw_mode':'1'}.get(sys.argv[2],''))")
        self.tool('uname', "print(state['cpu'])")
        self.tool('df', "print('Filesystem 1024-blocks Used Available Capacity Mounted on\\nusb 2097152 10 '+str(state['free_kb'])+' 1% /opt')")
        self.checksum_command(self.work/'dependency-sha256sum', installed=True)

        self.recovery_fixture()
        self.state.update(version='', install_error=False, stop_before_failure=False)

    def recovery_fixture(self):
        paths=[]
        for name,field in [('S51nfqws2','core_running'),('S81nfqws-asus-web','web_running')]:
            path=self.router/'opt/etc/init.d'/name
            self.tool(name, """
field=FIELD
action=sys.argv[1]
if action=='status':sys.exit(0 if state.get(field,False) else 1)
emit({'kind':'service','field':field,'action':action})
if action=='start' and state.get('recovery_start_error'):sys.exit(1)
state[field]=action=='start'
state_path.write_text(json.dumps(state))
""".replace('FIELD',repr(field)),path)
            paths.append(str(path))
        (self.router/'opt/lib/opkg/info/nfqws2-asus.list').write_text('\n'.join(paths)+'\n')
        self.state.update(version='1.3.1-asus6+b66',install_error=True,stop_before_failure=True)

    def test_failed_preinst_restores_verified_old_core_and_web(self):
        self.recovery_fixture();self.state.update(core_running=True,web_running=True,enabled=True)
        r=self.execute();self.assertNotEqual(r.returncode,0)
        final=json.loads(self.state_path.read_text())
        self.assertTrue(final['core_running'],r.stdout+r.stderr)
        self.assertTrue(final['web_running'],r.stdout+r.stderr)
        self.assertIn('восстановлено',r.stdout)

    def test_failed_preinst_restores_wait_wan_but_keeps_stopped_services_off(self):
        for enabled,core,web in [(True,False,False),(False,False,True),(False,False,False)]:
            with self.subTest(enabled=enabled,core=core,web=web):
                self.recovery_fixture();self.state.update(enabled=enabled,core_running=core,web_running=web)
                r=self.execute();self.assertNotEqual(r.returncode,0)
                final=json.loads(self.state_path.read_text())
                self.assertEqual(final['core_running'],enabled or core)
                self.assertEqual(final['web_running'],web)

    def test_failed_upgrade_never_starts_changed_partial_or_new_payload(self):
        cases=[{'change_payload':True},{'delete_payload':True},{'failure_status':'install user unpacked'},{'failure_version':VERSION}]
        for case in cases:
            with self.subTest(case=case):
                self.recovery_fixture();self.state.update(enabled=True,core_running=True,web_running=True,**case)
                self.log.unlink(missing_ok=True)
                r=self.execute();self.assertNotEqual(r.returncode,0)
                self.assertFalse(any(e.get('action')=='start' for e in self.events))
                for key in case:self.state.pop(key,None)

    def test_restore_manifest_supports_owner_filenames_with_spaces_and_unicode(self):
        self.recovery_fixture();self.state.update(enabled=True,core_running=True,web_running=True)
        (self.router/'opt/etc/nfqws2/owner space список.list').write_text('example.org\n')
        r=self.execute();self.assertNotEqual(r.returncode,0)
        final=json.loads(self.state_path.read_text())
        self.assertTrue(final['core_running'],r.stdout+r.stderr)
        self.assertTrue(final['web_running'],r.stdout+r.stderr)

    def test_unsafe_recovery_manifest_aborts_before_install_and_service_stops(self):
        self.recovery_fixture();self.state.update(enabled=True,core_running=True,web_running=True)
        os.mkfifo(self.router/'opt/etc/nfqws2/unsupported.pipe')
        r=self.execute();self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.installs(),[])
        self.assertFalse(any(e.get('kind')=='service' for e in self.events))
        final=json.loads(self.state_path.read_text())
        self.assertTrue(final['core_running']);self.assertTrue(final['web_running'])

    def test_failed_recovery_stays_failure_and_reports_it(self):
        self.recovery_fixture();self.state.update(enabled=True,core_running=True,web_running=True,recovery_start_error=True)
        r=self.execute();self.assertNotEqual(r.returncode,0)
        self.assertIn('не удалось',r.stdout+r.stderr)

    def tool(self, name, body, path=None):
        p = path or self.bin / name
        p.write_text('#!/usr/bin/python3\nimport os,sys,pathlib,json\n'
                     'work=pathlib.Path(os.environ["INSTALL_FIXTURE"])\n'
                     'state_path=work/"state.json"\nstate=json.loads(state_path.read_text())\n'
                     'def emit(value):\n with (work/"events.jsonl").open("a") as f:f.write(json.dumps(value)+"\\n")\n' + body + '\n')
        p.chmod(0o755)

    def checksum_command(self, path, mode='working', *, busybox=False, installed=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.tool(path.name, r'''
import hashlib
args=sys.argv[1:]
if BUSYBOX:
    applet=args.pop(0)
    if applet!='sha256sum':os.execv('/bin/busybox',['/bin/busybox',applet]+args)
mode=state.get('installed_hash_mode','working') if INSTALLED else MODE
if mode=='missing':sys.exit(127)
if mode=='broken':sys.exit(1)
if mode=='empty':sys.exit()
name=args[0] if args else '-'
data=sys.stdin.buffer.read() if name=='-' else pathlib.Path(name).read_bytes()
digest=hashlib.sha256(data).hexdigest() if mode=='working' else '0'*64
print(digest+'  '+name)
'''.replace('BUSYBOX',repr(busybox)).replace('INSTALLED',repr(installed)).replace('MODE',repr(mode)),path)

    def without_checksum_tools(self):
        # Only native utility dependencies remain on PATH; no host sha256sum
        # or absolute BusyBox can accidentally satisfy this router fixture.
        self.isolated_checksum_tools=True
        for name in ['tr','awk','grep','mkdir','rm','wc']:
            if not (self.bin/name).exists():(self.bin/name).symlink_to(shutil.which(name))
        for path in [self.bin/'sha256sum',self.router/'opt/bin/sha256sum']:
            path.unlink(missing_ok=True)
        for path in self.busybox_paths():
            self.checksum_command(path,'missing',busybox=True)

    def busybox_paths(self):
        return [self.router/'opt/bin/busybox',self.router/'bin/busybox',
                self.router/'opt/libexec/nfqws2-asus/busybox']

    def execute(self, *args):
        self.assertTrue(self.installer.is_file(), 'The one-command installer has not been implemented')
        self.state_path.write_text(json.dumps(self.state))
        enabled = self.router / 'tmp/nfqws2-asus/enabled'
        enabled.parent.mkdir(parents=True, exist_ok=True)
        if self.state['enabled']:enabled.touch()
        else:enabled.unlink(missing_ok=True)
        text = self.installer.read_text()
        if self.isolated_checksum_tools:
            text=text.replace('PATH=/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin',f'PATH={self.bin}:/opt/bin')
            text=re.sub(r'(?<![\w/])/bin/busybox\b',str(self.router/'bin/busybox'),text)
        text = text.replace('/opt/', str(self.router) + '/opt/').replace(
            '/proc/', str(self.router) + '/proc/').replace('/tmp/nfqws2-asus/', str(self.router) + '/tmp/nfqws2-asus/')
        text = text.replace('PATH=', 'PATH=' + str(self.bin) + ':', 1)
        # Standalone BusyBox ash prefers its built-in uname/df applets to PATH.
        # Bind these OS boundaries explicitly; all installer shell logic stays real.
        text = text.replace('$(uname -m)', f'$("{self.bin}/uname" -m)')
        text = text.replace('df -Pk ', f'"{self.bin}/df" -Pk ')
        script = self.work / 'install.sh'
        script.write_text(text)
        shell = ['/bin/busybox', 'ash'] if os.environ.get('INSTALL_TEST_BUSYBOX') else ['/bin/sh']
        result = subprocess.run(shell + [str(script)] + list(args), env={**os.environ, 'INSTALL_FIXTURE': str(self.work)},
                                text=True, capture_output=True, timeout=15)
        self.events = [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []
        self.assertEqual(self.owner_file.read_text(), 'keep.example\n')
        self.assertEqual(self.unrelated.read_bytes(), b'not ours')
        self.assertEqual(list((self.router/'opt/tmp').glob('nfqws2-asus-install.*')), [])
        return result

    def installs(self):
        return [x for x in self.events if x['kind']=='install']

    def package_changes(self):
        return [x for x in self.events if x['kind'] in ['update','dependency','install']]

    def test_missing_checksum_tool_is_provisioned_before_verified_install(self):
        for mode in [None,'broken','empty','wrong']:
            with self.subTest(sha256sum=mode):
                self.without_checksum_tools()
                if mode:self.checksum_command(self.bin/'sha256sum',mode)
                self.log.unlink(missing_ok=True)
                r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                self.assertEqual(self.package_changes(),[
                    {'kind':'update'},{'kind':'dependency','package':'coreutils-sha256sum'},
                    {'kind':'install','asset':f'nfqws2-asus_{VERSION}_aarch64-3.10.ipk','no_start':'1'}])
                self.assertEqual(json.loads(self.state_path.read_text())['version'],VERSION)

    def test_working_sha256sum_needs_no_checksum_dependency(self):
        self.without_checksum_tools()
        self.checksum_command(self.bin/'sha256sum')
        r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual([x['kind'] for x in self.package_changes()],['update','install'])

    def test_each_working_busybox_falls_back_from_unusable_sha256sum(self):
        for path in self.busybox_paths():
            for mode in ['broken','empty','wrong']:
                with self.subTest(path=path,sha256sum=mode):
                    self.without_checksum_tools()
                    self.checksum_command(self.bin/'sha256sum',mode)
                    self.checksum_command(path,busybox=True)
                    self.log.unlink(missing_ok=True)
                    r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                    self.assertEqual([x['kind'] for x in self.package_changes()],['update','install'])

    def test_unusable_busybox_does_not_hide_working_later_candidate(self):
        for mode in ['broken','empty','wrong']:
            with self.subTest(busybox=mode):
                self.without_checksum_tools()
                for path in self.busybox_paths()[:2]:self.checksum_command(path,mode,busybox=True)
                self.checksum_command(self.busybox_paths()[2],busybox=True)
                self.log.unlink(missing_ok=True)
                r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                self.assertEqual([x['kind'] for x in self.package_changes()],['update','install'])

    def test_checksum_dependency_failures_never_install_nfqws_or_change_services(self):
        for failure in [{'update_error':True},{'dependency_error':True},
                        {'installed_hash_mode':'missing'},{'installed_hash_mode':'broken'},
                        {'installed_hash_mode':'empty'},{'installed_hash_mode':'wrong'}]:
            with self.subTest(failure=failure):
                self.without_checksum_tools()
                self.state.update(update_error=False,dependency_error=False,installed_hash_mode='working',
                                  version='1.3.1-asus6+b66',enabled=True,core_running=True,web_running=True)
                self.state.update(failure)
                self.log.unlink(missing_ok=True)
                r=self.execute();self.assertNotEqual(r.returncode,0,r.stdout+r.stderr)
                self.assertEqual(self.installs(),[])
                self.assertFalse(any(x['kind']=='service' for x in self.events))
                self.assertNotIn('Готово',r.stdout)
                final=json.loads(self.state_path.read_text())
                self.assertTrue(final['core_running']);self.assertTrue(final['web_running'])
                if failure.get('update_error'):
                    self.assertEqual(self.package_changes(),[{'kind':'update'}])
                else:
                    self.assertEqual(self.package_changes(),[
                        {'kind':'update'},{'kind':'dependency','package':'coreutils-sha256sum'}])

    def test_check_without_checksum_tool_reports_dependency_without_package_changes(self):
        self.without_checksum_tools()
        r=self.execute('--check');self.assertNotEqual(r.returncode,0)
        self.assertIn('coreutils-sha256sum',r.stdout+r.stderr)
        self.assertIn('--check',r.stdout+r.stderr)
        self.assertEqual(self.package_changes(),[])
        self.assertFalse(any(x['kind']=='service' for x in self.events))

    def test_ineligible_installs_do_not_provision_checksum_dependency(self):
        for condition in ['invalid_abi','current_version','low_storage','low_ram']:
            with self.subTest(condition=condition):
                self.without_checksum_tools()
                self.state.update(arches='arch all 100\narch aarch64-3.10 160\n',version='',free_kb=1048576)
                (self.router/'proc/meminfo').write_text('MemAvailable: 131072 kB\n')
                if condition=='invalid_abi':self.state['arches']='arch mipsel-3.4 160\n'
                elif condition=='current_version':self.state['version']=VERSION
                elif condition=='low_storage':self.state['free_kb']=1
                else:(self.router/'proc/meminfo').write_text('MemAvailable: 1024 kB\n')
                self.log.unlink(missing_ok=True)
                r=self.execute()
                self.assertEqual(r.returncode,0 if condition=='current_version' else 1,r.stdout+r.stderr)
                self.assertEqual(self.package_changes(),[])
                self.assertFalse(any(x['kind']=='service' for x in self.events))

    def test_corruption_after_checksum_provisioning_never_reaches_nfqws_install(self):
        self.without_checksum_tools()
        (self.http/f'nfqws2-asus_{VERSION}_aarch64-3.10.ipk').write_bytes(b'corrupt')
        r=self.execute();self.assertNotEqual(r.returncode,0)
        self.assertIn('Контрольная сумма',r.stdout+r.stderr)
        self.assertEqual(self.package_changes(),[
            {'kind':'update'},{'kind':'dependency','package':'coreutils-sha256sum'}])
        self.assertEqual(self.installs(),[])
        self.assertFalse(any(x['kind']=='service' for x in self.events))

    def test_first_install_selects_aarch64_and_keeps_processing_off(self):
        r = self.execute()
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertEqual(self.installs(), [{'kind':'install','asset':f'nfqws2-asus_{VERSION}_aarch64-3.10.ipk','no_start':'1'}])
        self.assertIn('http://192.168.50.1:90', r.stdout)

    def test_first_install_without_mktemp(self):
        self.tool('mktemp', 'sys.exit(127)')
        r = self.execute()
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertEqual(self.installs()[0]['no_start'], '1')

    def test_both_arm_abis_select_the_same_arm_package(self):
        for abi in ['armv7-2.6', 'armv7-3.2']:
            with self.subTest(abi=abi):
                self.state.update(arches=f'arch all 100\narch {abi} 160\n', cpu='armv7l')
                self.log.unlink(missing_ok=True)
                r=self.execute()
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                self.assertEqual(self.installs()[0]['asset'],f'nfqws2-asus_{VERSION}_armv7.ipk')

    def test_unknown_primary_abi_does_not_use_supported_secondary(self):
        self.state['arches']='arch all 100\narch aarch64-3.10 160\narch mipsel-3.4 200\n'
        r=self.execute();self.assertNotEqual(r.returncode,0);self.assertEqual(self.installs(),[])

    def test_tied_primary_abis_stop_before_download(self):
        self.state['arches']='arch armv7-3.2 160\narch aarch64-3.10 160\n'
        r=self.execute();self.assertNotEqual(r.returncode,0);self.assertEqual(self.events,[])

    def test_corrupted_package_does_not_reach_opkg(self):
        (self.http/f'nfqws2-asus_{VERSION}_aarch64-3.10.ipk').write_bytes(b'corrupt')
        r=self.execute();self.assertNotEqual(r.returncode,0);self.assertEqual(self.installs(),[])

    def test_partial_download_does_not_reach_opkg(self):
        self.state['download_error']=True
        r=self.execute();self.assertNotEqual(r.returncode,0);self.assertEqual(self.installs(),[])

    def test_malformed_checksum_catalog_does_not_reach_opkg(self):
        (self.http/'SHA256SUMS').write_text('not-a-hash  nfqws2-asus_1.3.2-asus6+b67_aarch64-3.10.ipk\n')
        r=self.execute();self.assertNotEqual(r.returncode,0);self.assertEqual(self.installs(),[])

    def test_duplicate_candidates_are_not_guessed(self):
        p=self.http/'SHA256SUMS';p.write_text(p.read_text()+p.read_text())
        r=self.execute();self.assertNotEqual(r.returncode,0);self.assertEqual(self.installs(),[])

    def test_no_free_storage_does_not_install(self):
        self.state['free_kb']=1
        r=self.execute();self.assertNotEqual(r.returncode,0);self.assertEqual(self.installs(),[])

    def test_opkg_failure_is_not_reported_as_success(self):
        self.state['install_error']=True
        r=self.execute();self.assertNotEqual(r.returncode,0);self.assertNotIn('Готово',r.stdout)

    def test_current_version_is_a_noop(self):
        self.state['version']=VERSION
        r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.installs(),[])
        self.assertFalse(any(x['kind']=='download' and x['url'].endswith('.ipk') for x in self.events))

    def test_reinstall_required_is_not_reported_as_current(self):
        self.state.update(version=VERSION, package_status='install reinstreq installed')
        r=self.execute();self.assertNotEqual(r.returncode,0)
        self.assertNotIn('уже установлен',r.stdout)
        self.assertIn('opkg status nfqws2-asus',r.stderr)
        self.assertEqual(self.installs(),[])

    def test_user_installed_upgrade_preserves_enabled_intent(self):
        self.state.update(version='1.3.1-asus6+b66', package_status='install user installed',
                          post_install_status='install user installed', enabled=True)
        r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.installs(),[{'kind':'install','asset':f'nfqws2-asus_{VERSION}_aarch64-3.10.ipk','no_start':'0'}])
        self.assertIn('Готово',r.stdout)

    def test_current_user_installed_version_is_a_noop(self):
        self.state.update(version=VERSION, package_status='install user installed')
        r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.installs(),[])
        self.assertFalse(any(x['kind']=='update' for x in self.events))
        self.assertIn('уже установлен',r.stdout)

    def test_aborted_upgrade_can_retry_without_losing_enabled_intent(self):
        for flag in ['ok', 'user']:
            for enabled in [False, True]:
                with self.subTest(flag=flag, enabled=enabled):
                    self.state.update(version='1.3.1-asus6+b66', package_status=f'deinstall {flag} installed', enabled=enabled)
                    self.log.unlink(missing_ok=True)
                    r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                    self.assertEqual(self.installs(),[{'kind':'install','asset':f'nfqws2-asus_{VERSION}_aarch64-3.10.ipk','no_start':'0' if enabled else '1'}])
                    self.assertIn('Готово',r.stdout)

    def test_aborted_upgrade_check_only_does_not_change_package_state(self):
        self.state.update(version='1.3.1-asus6+b66', package_status='deinstall user installed', enabled=True)
        r=self.execute('--check');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.installs(),[])
        self.assertFalse(any(x['kind']=='update' for x in self.events))
        self.assertEqual(json.loads(self.state_path.read_text())['package_status'],'deinstall user installed')

    def test_deinstall_wish_cannot_be_reported_as_success_at_current_version_or_postflight(self):
        self.state.update(version=VERSION, package_status='deinstall user installed')
        r=self.execute();self.assertNotEqual(r.returncode,0)
        self.assertNotIn('уже установлен',r.stdout);self.assertEqual(self.installs(),[])
        self.state.update(version='1.3.1-asus6+b66', package_status='deinstall user installed', post_install_status='deinstall user installed')
        r=self.execute();self.assertNotEqual(r.returncode,0)
        self.assertEqual(len(self.installs()),1);self.assertNotIn('Готово',r.stdout)

    def test_retry_does_not_accept_purge_hold_or_partial_installation(self):
        for status in ['purge user installed','deinstall hold installed','deinstall user unpacked','deinstall ok half-configured','deinstall reinstreq installed']:
            with self.subTest(status=status):
                self.state.update(version='1.3.1-asus6+b66',package_status=status)
                r=self.execute();self.assertNotEqual(r.returncode,0)
                self.assertEqual(self.installs(),[])

    def test_first_install_accepts_user_flag_from_opkg(self):
        self.state['post_install_status']='install user installed'
        r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.installs()[0]['no_start'],'1')
        self.assertIn('Готово',r.stdout)

    def test_user_unpacked_install_is_not_upgraded(self):
        self.state.update(version='1.3.1-asus6+b66', package_status='install user unpacked', enabled=True)
        r=self.execute();self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.installs(),[])
        self.assertFalse(any(x['kind']=='update' for x in self.events))
        self.assertTrue((self.router/'tmp/nfqws2-asus/enabled').is_file())

    def test_incomplete_install_is_reported_without_changing_enabled_intent(self):
        self.state.update(version='1.3.1-asus6+b66', package_status='install ok unpacked', enabled=True)
        r=self.execute();self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.installs(),[])
        self.assertFalse(any(x['kind']=='update' for x in self.events))
        self.assertTrue((self.router/'tmp/nfqws2-asus/enabled').is_file())

    def test_successful_opkg_exit_with_incomplete_status_is_not_success(self):
        self.state['post_install_status']='install ok unpacked'
        r=self.execute();self.assertNotEqual(r.returncode,0)
        self.assertNotIn('Готово',r.stdout)

    def test_removed_package_with_retained_config_is_a_first_install(self):
        self.state.update(version='1.3.1-asus6+b66',package_status='deinstall ok config-files')
        r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.installs()[0]['no_start'],'1')

    def test_newer_installed_version_is_not_downgraded(self):
        self.state['version']='1.3.2-asus6+b68'
        r=self.execute();self.assertNotEqual(r.returncode,0);self.assertEqual(self.installs(),[])

    def test_stopped_upgrade_stays_stopped(self):
        self.state['version']='1.3.1-asus6+b66'
        r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.installs()[0]['no_start'],'1')

    def test_enabled_upgrade_including_waiting_for_wan_preserves_intent(self):
        self.state.update(version='1.3.1-asus6+b66',enabled=True)
        r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.installs()[0]['no_start'],'0')

    def test_check_only_verifies_download_without_package_changes(self):
        r=self.execute('--check');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.installs(),[])
        self.assertFalse(any(x['kind']=='update' for x in self.events))
        self.assertTrue(any(x['kind']=='download' and x['url'].endswith('.ipk') for x in self.events))

    def test_low_ram_does_not_install(self):
        (self.router/'proc/meminfo').write_text('MemAvailable: 1024 kB\n')
        r=self.execute();self.assertNotEqual(r.returncode,0);self.assertEqual(self.installs(),[])

    def test_old_kernel_without_memavailable_uses_free_buffers_and_cache(self):
        (self.router/'proc/meminfo').write_text('MemFree: 16384 kB\nBuffers: 8192 kB\nCached: 16384 kB\n')
        r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_gnu_wget_can_install_without_curl(self):
        self.tool('wget', r'''
args=sys.argv[1:]
if args==['--version']:
    print('GNU Wget 1.25.0');sys.exit()
assert '--https-only' in args and '--no-check-certificate' not in args
url=args[-1];out=args[args.index('-O')+1]
assert url.startswith('https://github.com/madworldpay/nfqws2-asus-community/releases/')
emit({'kind':'download','url':url})
pathlib.Path(out).write_bytes((work/'http'/url.rsplit('/',1)[1]).read_bytes())
''')
        # No curl can be discovered in this isolated PATH. Native utilities remain real.
        (self.bin/'curl').unlink()
        for name in ['tr','awk','grep','mkdir','mktemp','rm','wc','sha256sum']:
            (self.bin/name).symlink_to(shutil.which(name))
        old=INSTALLER.read_text()
        temporary=self.work/'wget-install.sh'
        temporary.write_text(old.replace('PATH=/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin',f'PATH={self.bin}'))
        self.installer=temporary
        r=self.execute();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(len(self.installs()),1)


if __name__=='__main__':unittest.main()
