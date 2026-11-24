"""Run the real installer against private files and synthetic service/Docker tools."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'webui/web/src/utils/mtproto-install.sh'
KEY = '1234567890abcdef1234567890abcdef'  # Synthetic, never a device credential.
NEW_KEY = 'abcdef1234567890abcdef1234567890'


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.config = {'port': 18443, 'secret': KEY, 'owner_metadata': {'keep': True}}
        self.candidate = self.base / 'native'
        self.service = self.base / 'nfqws-mtproto.service'
        self.state = self.base / 'state.json'
        self.state.write_text(json.dumps({'running': True, 'calls': [], 'probe_fail': False}))
        archive = self.base / 'source.tgz'
        prefix = 'tg-ws-proxy-6690b788432fd0f59b0f38e228494bcd6bede1ca/'
        with tarfile.open(archive, 'w:gz') as tar:
            for name, content in {'proxy/__init__.py': '', 'proxy/_aes.py': 'Cipher=algorithms=modes=None',
                                  'utils/__init__.py': '', 'LICENSE': 'fixture',
                                  'httpx.py': '', 'h2.py': '', 'certifi.py': ''}.items():
                data = content.encode(); entry = tarfile.TarInfo(prefix + name); entry.size = len(data)
                tar.addfile(entry, io.BytesIO(data))
        self.archive = archive
        # The config writer uses actual Python. Only venv/pip and the external
        # Telegram probe are substituted; no service or network connection starts.
        self.tool('python3', f'''import os,pathlib,sys
a=sys.argv[1:]
if a[:2]==['-m','venv']:
 p=pathlib.Path(a[2])/'bin';p.mkdir(parents=True);(p/'python').symlink_to({str(self.bin/'python3')!r});sys.exit(0)
if a[:2]==['-m','pip']:sys.exit(0)
if a and a[0]=='-c' and 'NFQWS_MT_PROBE_ROOT' in os.environ:
 import json
 s=json.load(open({str(self.state)!r}));sys.exit(1 if s['probe_fail'] else 0)
os.execv({sys.executable!r},[{sys.executable!r}]+a)
''')
        self.tool('systemctl', f'''import json,sys
p={str(self.state)!r};s=json.load(open(p));a=sys.argv[1:];s['calls'].append(a);ok=True
if a[0]=='is-active':ok=s['running']
elif a[0]=='is-enabled':ok=True
elif a[0]=='cat':ok=False
elif a[0]=='stop':s['running']=False
elif a[0]=='start' or (a[0]=='enable' and '--now' in a):s['running']=True
json.dump(s,open(p,'w'));sys.exit(0 if ok else 1)
''')
        self.tool('curl', f'import shutil,sys\na=sys.argv[1:];shutil.copyfile({str(archive)!r},a[a.index("-o")+1])\n')
        self.tool('id', 'print(0)\n')
        self.tool('sleep', 'pass\n')

    def tool(self, name, code):
        path = self.bin / name
        path.write_text('#!' + sys.executable + '\n' + code)
        path.chmod(0o700)

    def installed(self, running=True, raw=None):
        self.candidate.mkdir()
        (self.candidate / 'venv/bin').mkdir(parents=True)
        (self.candidate / 'venv/bin/python').symlink_to(self.bin / 'python3')
        (self.candidate / 'config.json').write_text(raw or json.dumps(self.config))
        (self.candidate / 'run.py').write_text('from proxy.tg_ws_proxy import main\n')
        self.service.write_text(str(self.candidate / 'run.py'))
        state = json.loads(self.state.read_text()); state['running'] = running; self.state.write_text(json.dumps(state))

    def run_installer(self, action='update', method='linux', proposed_key=NEW_KEY, preflight=False):
        raw = SOURCE.read_text()
        # Relocate only managed system paths and replace external tools. The
        # validation, config writer and rollback/commit code remain production.
        mappings = [('/usr/local/share/nfqws-mtproto', str(self.candidate)),
                    ('/etc/systemd/system/nfqws-mtproto.service', str(self.service)),
                    ('/opt/share/nfqws-mtproto', str(self.candidate)),
                    ('/opt/etc/init.d/S98nfqws-mtproto', str(self.service)),
                    ('/run/systemd/system', str(self.base)),
                    ('/opt', str(self.base / 'opt'))]
        for before, after in mappings:
            raw = raw.replace(before, after)
        raw = raw.replace('PATH=', 'PATH=' + str(self.bin) + ':', 1)
        raw = raw.replace('for d in /', 'for d in ' + str(self.bin) + ' /', 1)
        raw = raw.replace('8e93c7c17074f49ba69f97abae75d196317c215eb278e943d3c5f3b073b4c145', hashlib.sha256(self.archive.read_bytes()).hexdigest())
        # Empty Python modules stand in for the pinned dependency download.
        raw = raw.replace('cp -R "$source/proxy" "$source/utils" "$source/LICENSE" "$root/app/"',
                          'cp -R "$source/proxy" "$source/utils" "$source/LICENSE" "$source/httpx.py" "$source/h2.py" "$source/certifi.py" "$root/app/"')
        if preflight:
            raw = raw.split('# An explicit update/removal', 1)[0] + '\nprintf "%s:%s:%s\\n" "$NFQWS_MT_PORT" "$NFQWS_MT_KEY" "$previous_running"\n'
        script = self.base / 'install.sh'
        script.write_text("#!/bin/sh\nset -eu\nNFQWS_MT_LANG=en\nNFQWS_MT_METHOD=" + method +
                          "\nNFQWS_MT_ACTION=" + action + "\nNFQWS_MT_PORT=24443\nNFQWS_MT_KEY=" + proposed_key +
                          "\nNFQWS_MT_LINK='https://t.me/proxy?server=proxy.example.org&port=24443&secret=dd" + proposed_key + "'\n" + raw)
        return subprocess.run(['/bin/sh', str(script)], capture_output=True, text=True, timeout=15)

    def test_running_update_keeps_connection_and_full_config_then_repeats(self):
        self.installed()
        for _ in range(2):
            result = self.run_installer()
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = json.loads((self.candidate / 'config.json').read_text())
            self.assertTrue(actual == self.config, 'Update must preserve port, key and existing non-executable configuration data')
            self.assertTrue(json.loads(self.state.read_text())['running'])
            self.assertIn('port=18443&secret=dd' + KEY, result.stdout)
            self.assertNotIn(NEW_KEY, result.stdout + result.stderr)

    def test_stopped_update_keeps_connection_and_returns_to_stopped(self):
        self.installed(running=False)
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.candidate / 'config.json').read_text())['secret'], KEY)
        self.assertFalse(json.loads(self.state.read_text())['running'], 'An update must not leave a previously stopped proxy running')

    def test_duplicate_or_partial_config_is_warned_without_changes(self):
        self.installed(raw='{"port":18443,"secret":"' + KEY + '","secret":"' + NEW_KEY + '"}')
        before = (self.candidate / 'config.json').read_bytes()
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0, 'Duplicate connection keys must not be silently selected')
        self.assertEqual((self.candidate / 'config.json').read_bytes(), before)
        self.assertIn('nothing was changed', result.stderr)
        self.assertEqual(json.loads(self.state.read_text())['calls'], [], 'Validation must precede service mutation')

    def test_missing_unit_keeps_recoverable_config(self):
        self.installed()
        self.service.unlink()
        before = (self.candidate / 'config.json').read_bytes()
        result = self.run_installer(action='install')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.candidate / 'config.json').read_bytes(), before)
        self.assertIn('Incomplete previous', result.stderr)

    def test_failure_rolls_back_exact_config_and_former_state(self):
        self.installed()
        before = (self.candidate / 'config.json').read_bytes()
        state = json.loads(self.state.read_text()); state['probe_fail'] = True; self.state.write_text(json.dumps(state))
        result = self.run_installer()
        self.assertEqual(result.returncode, 19)
        self.assertEqual((self.candidate / 'config.json').read_bytes(), before)
        self.assertTrue(json.loads(self.state.read_text())['running'])
        self.assertNotIn('secret=', result.stdout)

    def test_fresh_install_uses_its_single_supplied_secret(self):
        result = self.run_installer(action='install')
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads((self.candidate / 'config.json').read_text())
        self.assertTrue(actual == {'port': 24443, 'secret': NEW_KEY})
        # A repeated fresh-install command becomes a checked update; it must
        # retain the first connection rather than adopting another proposal.
        self.config = actual
        self.assertIn('secret=dd' + NEW_KEY, result.stdout)
        repeated = self.run_installer(action='install', proposed_key=KEY)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertTrue(json.loads((self.candidate / 'config.json').read_text()) == actual)

    def docker(self, running=True, env_extra=None, bindings=None, probe_fail=False):
        state_file = self.base / 'docker.json'
        env = ['PROXY_SECRET=' + KEY, 'PROXY_HOST=127.0.0.1', 'PROXY_PORT=1443',
               'PROXY_DC_IPS=2:149.154.167.220', 'PROXY_POOL_SIZE=4', 'CFPROXY_DOMAIN=relay.example.org']
        state_file.write_text(json.dumps({'calls': [], 'probe_fail': probe_fail, 'containers': {
            'nfqws-mtproto': {'id': 'a' * 64, 'running': running,
                'image': 'lordarrin/tg-ws-proxy@sha256:' + '1' * 64,
                'cmd': ['python', 'proxy/tg_ws_proxy.py'], 'env': env + (env_extra or []),
                'bindings': bindings or {'1443/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '18443'}]}}
        }}))
        self.tool('docker', f'''import json,re,sys
p={str(state_file)!r};s=json.load(open(p));a=sys.argv[1:];s['calls'].append(a)
def save():json.dump(s,open(p,'w'))
save();c=s['containers'];cmd=a[0]
if a[:2]==['container','inspect']:sys.exit(0 if a[-1] in c else 1)
if cmd=='inspect':
 v=c[a[-1]];fmt=a[2]
 if fmt=='{{{{.Config.Image}}}}':print(v['image'])
 elif '.Config.Cmd' in fmt:print(json.dumps(v['cmd']))
 elif '.Config.Env' in fmt:print('\\n'.join(json.dumps(row) if '%q' in fmt else row for row in v['env']))
 elif '.HostConfig.PortBindings' in fmt:
  ports=re.findall(r'"([0-9]+/tcp)"',fmt);key=ports[0] if ports else '1443/tcp';rows=v['bindings'].get(key,[])
  if ('len .HostConfig.PortBindings' in fmt and len(v['bindings'])!=1) or ('len .' in fmt and 'HostIp' in fmt and len(rows)!=1):print('invalid')
  elif not rows:print('invalid')
  elif 'HostIp' in fmt:print(rows[0]['HostIp']+'|'+rows[0]['HostPort'])
  else:print(rows[0]['HostPort'])
 elif '.State.Running' in fmt:print(str(v['running']).lower())
 elif '.Id' in fmt:print(v['id'])
 else:sys.exit(2)
elif cmd=='rename':c[a[2]]=c.pop(a[1]);save()
elif cmd in ['start','stop']:c[a[1]]['running']=cmd=='start';save();print(c[a[1]]['id'])
elif cmd=='create':
 env=[a[i+1] for i,x in enumerate(a) if x=='-e'];s['created']=a
 c['nfqws-mtproto']={{'id':'b'*64,'running':False,'image':'new','cmd':[],'env':env,'bindings':{{}}}}
 c['b'*64]=c['nfqws-mtproto'];save();print('b'*64)
elif cmd=='rm':
 target=a[-1];victim=c.get(target)
 for name in list(c):
  if c[name]==victim:del c[name]
 save()
elif cmd=='exec':sys.exit(1 if s['probe_fail'] else 0)
elif cmd not in ['info','pull']:sys.exit(2)
''')
        return state_file

    def test_docker_update_preserves_connection_relay_pool_and_bind_address(self):
        state_file = self.docker()
        result = self.run_installer(method='docker')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(state_file.read_text()); args = state['created']
        actual = dict(args[i + 1].split('=', 1) for i, value in enumerate(args) if value == '-e')
        expected = {'PROXY_SECRET': KEY, 'PROXY_HOST': '127.0.0.1', 'PROXY_PORT': '1443',
                    'PROXY_DC_IPS': '2:149.154.167.220', 'PROXY_POOL_SIZE': '4', 'CFPROXY_DOMAIN': 'relay.example.org'}
        self.assertTrue(actual == expected, 'Docker update must retain all supported existing proxy parameters')
        self.assertEqual(args[args.index('-p') + 1], '127.0.0.1:18443:1443', 'Do not broaden a loopback-only published port')
        self.assertIn('port=18443&secret=dd' + KEY, result.stdout)
        self.assertNotIn(NEW_KEY, result.stdout + result.stderr)

    def test_docker_duplicate_environment_is_rejected_before_mutations(self):
        state_file = self.docker(env_extra=['PROXY_SECRET=' + NEW_KEY])
        result = self.run_installer(method='docker')
        self.assertNotEqual(result.returncode, 0, 'Duplicate secret entries cannot be guessed')
        state = json.loads(state_file.read_text())
        self.assertFalse(any(call[0] in ['rename', 'stop', 'create', 'rm'] for call in state['calls']))
        self.assertTrue(state['containers']['nfqws-mtproto']['running'])

    def test_docker_ambiguous_binding_is_rejected_without_replacing_container(self):
        state_file = self.docker(bindings={'1443/tcp': [{'HostIp': '', 'HostPort': '18443'}, {'HostIp': '', 'HostPort': '28443'}]})
        result = self.run_installer(method='docker')
        self.assertNotEqual(result.returncode, 0, 'Multiple published connection ports need manual review')
        state = json.loads(state_file.read_text())
        self.assertFalse(any(call[0] in ['rename', 'stop', 'create', 'rm'] for call in state['calls']))

    def test_docker_stopped_update_remains_stopped_and_failure_restores_owner(self):
        state_file = self.docker(running=False)
        result = self.run_installer(method='docker')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(state_file.read_text())['containers']['nfqws-mtproto']['running'])
        state_file = self.docker(probe_fail=True)
        result = self.run_installer(method='docker')
        self.assertNotEqual(result.returncode, 0)
        current = json.loads(state_file.read_text())['containers']['nfqws-mtproto']
        self.assertEqual(current['id'], 'a' * 64)
        self.assertTrue(current['running'])
        self.assertIn('PROXY_SECRET=' + KEY, current['env'])

    def test_docker_incomplete_or_invalid_parameters_are_not_defaulted(self):
        for missing in [True, False]:
            state_file = self.docker()
            state = json.loads(state_file.read_text())
            env = state['containers']['nfqws-mtproto']['env']
            if missing:
                env[:] = [row for row in env if not row.startswith('CFPROXY_DOMAIN=')]
            else:
                env[:] = ['PROXY_POOL_SIZE=0' if row.startswith('PROXY_POOL_SIZE=') else row for row in env]
            state_file.write_text(json.dumps(state))
            result = self.run_installer(method='docker')
            self.assertNotEqual(result.returncode, 0, 'Do not guess missing or invalid runtime parameters')
            state = json.loads(state_file.read_text())
            self.assertFalse(any(call[0] in ['rename', 'stop', 'create', 'rm'] for call in state['calls']))

    def test_entware_running_and_stopped_config_is_read_without_candidate_key(self):
        self.installed()
        opt = self.base / 'opt'
        (opt / 'bin').mkdir(parents=True)
        (opt / 'etc/init.d').mkdir(parents=True)
        (opt / 'bin/opkg').symlink_to('/bin/false')
        (opt / 'bin/python3').symlink_to(self.bin / 'python3')
        self.service.write_text('#!/bin/sh\n# ' + str(self.candidate / 'run.py') + '\nexec ' + str(self.bin / 'systemctl') + ' is-active --quiet nfqws-mtproto.service\n')
        self.service.chmod(0o700)
        for running in [True, False]:
            state = json.loads(self.state.read_text()); state['running'] = running; self.state.write_text(json.dumps(state))
            result = self.run_installer(method='entware', preflight=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), '18443:' + KEY + ':' + ('yes' if running else 'no'))

    def test_docker_multiline_parameter_is_not_silently_truncated(self):
        state_file = self.docker()
        state = json.loads(state_file.read_text())
        state['containers']['nfqws-mtproto']['env'][-1] = 'CFPROXY_DOMAIN=relay.example.org\nIGNORED=value'
        state_file.write_text(json.dumps(state))
        result = self.run_installer(method='docker')
        self.assertNotEqual(result.returncode, 0, 'An invalid multiline relay must not become a different valid configuration')
        self.assertFalse(any(call[0] in ['rename', 'stop', 'create', 'rm'] for call in json.loads(state_file.read_text())['calls']))

    def test_docker_internal_port_and_ipv6_binding_are_retained(self):
        state_file = self.docker(bindings={'2443/tcp': [{'HostIp': '::1', 'HostPort': '18443'}]})
        state = json.loads(state_file.read_text())
        state['containers']['nfqws-mtproto']['env'][1:3] = ['PROXY_HOST=::1', 'PROXY_PORT=2443']
        state_file.write_text(json.dumps(state))
        result = self.run_installer(method='docker')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(state_file.read_text()); args = state['created']
        self.assertEqual(args[args.index('-p') + 1], '[::1]:18443:2443')
        self.assertIn('PROXY_PORT=2443', args)
        self.assertEqual(next(call for call in state['calls'] if call[0] == 'exec')[-3:], ['::1', '2443', '15'])


if __name__ == '__main__':
    unittest.main()
