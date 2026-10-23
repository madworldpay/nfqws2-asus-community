"""Run the real installer against a disposable router filesystem and HTTP/opkg boundaries."""
import hashlib
import json
import os
from pathlib import Path
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
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.router = self.work / 'router'
        self.bin = self.work / 'bin'
        self.bin.mkdir()
        for name in ['opt/bin', 'opt/tmp', 'opt/etc/init.d', 'opt/etc/nfqws2', 'proc']:
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
if args[:1]==['--tmp-dir']:args=args[2:]
action=args[0]
if action=='print-architecture':print(state['arches'],end='')
elif action=='status':
    if state['version']:print('Package: nfqws2-asus\nVersion: '+state['version']+'\nStatus: '+state.get('package_status','install ok installed')+'\n')
elif action=='compare-versions':
    def number(v):return int(v.rsplit('+b',1)[1])
    sys.exit(0 if number(args[1])>number(args[3]) else 1)
elif action=='update':emit({'kind':'update'})
elif action=='install':
    emit({'kind':'install','asset':pathlib.Path(args[1]).name,'no_start':os.environ.get('NFQWS_ASUS_NO_START')})
    if state['install_error']:sys.exit(1)
    state['version']='1.3.2-asus6+b67'
    state['package_status']=state.get('post_install_status','install ok installed')
    state_path.write_text(json.dumps(state))
else:raise AssertionError(args)
''', self.router / 'opt/bin/opkg')
        self.tool('nvram', "assert sys.argv[1]=='get'; print({'productid':'GT-BE19000AI','odmpid':'','lan_ipaddr':'192.168.50.1','sw_mode':'1'}.get(sys.argv[2],''))")
        self.tool('uname', "print(state['cpu'])")
        self.tool('df', "print('Filesystem 1024-blocks Used Available Capacity Mounted on\\nusb 2097152 10 '+str(state['free_kb'])+' 1% /opt')")

    def tool(self, name, body, path=None):
        p = path or self.bin / name
        p.write_text('#!/usr/bin/python3\nimport os,sys,pathlib,json\n'
                     'work=pathlib.Path(os.environ["INSTALL_FIXTURE"])\n'
                     'state_path=work/"state.json"\nstate=json.loads(state_path.read_text())\n'
                     'def emit(value):\n with (work/"events.jsonl").open("a") as f:f.write(json.dumps(value)+"\\n")\n' + body + '\n')
        p.chmod(0o755)

    def execute(self, *args):
        self.assertTrue(self.installer.is_file(), 'The one-command installer has not been implemented')
        self.state_path.write_text(json.dumps(self.state))
        enabled = self.router / 'tmp/nfqws2-asus/enabled'
        enabled.parent.mkdir(parents=True, exist_ok=True)
        if self.state['enabled']:enabled.touch()
        text = self.installer.read_text().replace('/opt/', str(self.router) + '/opt/').replace(
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

    def test_first_install_selects_aarch64_and_keeps_processing_off(self):
        r = self.execute()
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertEqual(self.installs(), [{'kind':'install','asset':f'nfqws2-asus_{VERSION}_aarch64-3.10.ipk','no_start':'1'}])
        self.assertIn('http://192.168.50.1:90', r.stdout)

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
