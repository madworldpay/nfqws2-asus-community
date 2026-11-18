"""Actual owned ROOT process deaths and resource/native-library integration."""
import json
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import tarfile
import unittest
import uuid
from test_import_plan import documents, selection, CURRENT

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'nfqws-openwrt-test:25.12.6-php'


@unittest.skipUnless(os.environ.get('NFQWS_TEST_GUARD_PHP_IMAGE') == IMAGE,
                     'Requires cached isolated ROOT PHP image')
class PortableAssetRoot(unittest.TestCase):
    def run_root(self, platform):
        task = 'portable-assets-' + uuid.uuid4().hex
        cid = None
        result = None
        with tempfile.TemporaryDirectory(prefix=task) as directory:
            inp = Path(directory) / 'input.json'
            inp.write_text(json.dumps({'docs': documents(), 'selection': selection(), 'config': CURRENT}))
            inp.chmod(0o644)
            try:
                args = ['docker', 'create', '--pull=never', '--name', task,
                        '--label', 'org.nfqws2.task=' + task, '--network', 'none',
                        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                        '--read-only', '--pids-limit', '32', '--memory', '128m', '--cpus', '1']
                for path in ['/tmp', '/opt', '/usr/share/nfqws2', '/usr/share/nfqws2-web']:
                    args += ['--tmpfs', path + ':rw,nosuid,nodev,mode=0755,size=32m']
                for src, dst in [(ROOT / 'webui/web/public', '/fixture-web'),
                                 (ROOT / 'experimental/device-profiles', '/fixture-profiles'),
                                 (ROOT / 'support', '/fixture-support'),
                                 (ROOT / 'openwrt/config.php', '/fixtures/config.php'),
                                 (ROOT / 'tests/fixtures/portable-assets-root.php', '/fixtures/master.php'),
                                 (inp, '/fixtures/input.json')]:
                    args += ['--mount', f'type=bind,src={src},dst={dst},readonly']
                # Keep tmpfs alive for evidence collection after the PHP process
                # finishes. The owned container has a hard 120-second lifetime.
                args += ['--entrypoint', '/bin/sh', IMAGE, '-c', 'exec sleep 120']
                cid = subprocess.check_output(args, text=True).strip()
                subprocess.run(['docker', 'start', cid], check=True, stdout=subprocess.DEVNULL)
                result = subprocess.run(['docker', 'exec', cid, '/usr/bin/php8-cgi', '-n', '-d',
                                         'register_argc_argv=1', '-q', '-f', '/fixtures/master.php',
                                         '--', platform], capture_output=True, text=True, timeout=75)
                self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout + result.stderr)
                try:
                    value = json.loads(result.stdout)
                except ValueError:
                    self.fail('ROOT fixture returned non-JSON: ' + repr(result.stdout))
                self.assertTrue(value['passed']); self.assertEqual(value['platform'], platform)
                self.assertGreaterEqual(value['assertions'], 90)
                self.assertEqual(value['cases'], 27)
                print(json.dumps({'task': task, 'id': cid, **value}), flush=True)
            finally:
                if cid:
                    info = json.loads(subprocess.check_output(['docker', 'inspect', cid], text=True))[0]
                    self.assertEqual(info['Id'], cid); self.assertEqual(info['Name'], '/' + task)
                    self.assertEqual(info['Config']['Labels']['org.nfqws2.task'], task)
                    try:
                        if os.environ.get('NFQWS_TEST_PORTABLE_ASSETS_EVIDENCE_DIR'):
                            folder=Path(os.environ['NFQWS_TEST_PORTABLE_ASSETS_EVIDENCE_DIR'])/task
                            folder.mkdir(parents=True,mode=0o700)
                            archive=subprocess.run(['docker','exec',cid,'/bin/tar','-C','/tmp','-cf','-','portable-assets'],capture_output=True,timeout=15)
                            (folder/'copy.stderr').write_bytes(archive.stderr)
                            (folder/'stdout').write_text(result.stdout if result else '')
                            (folder/'stderr').write_text(result.stderr if result else 'start did not return')
                            self.assertEqual(archive.returncode, 0, archive.stderr.decode(errors='replace'))
                            (folder/'evidence.tar').write_bytes(archive.stdout)
                            with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
                                members=[{'name':m.name,'type':m.type.decode('ascii'),'mode':m.mode,'uid':m.uid,'gid':m.gid,'size':m.size,'link':m.linkname,
                                          'sha256':hashlib.sha256(tar.extractfile(m).read()).hexdigest() if m.isfile() else None} for m in tar]
                            (folder/'archive.json').write_text(json.dumps({'container':cid,'owner':task,'archive_sha256':hashlib.sha256(archive.stdout).hexdigest(),'members':members},indent=2)+'\n')
                    finally:
                        subprocess.run(['docker', 'rm', '-f', cid], check=True, stdout=subprocess.DEVNULL)
                        self.assertNotIn(cid, subprocess.check_output(['docker', 'ps', '-aq', '--no-trunc'], text=True).split())

    def test_asus_root_storage_and_native_library(self):
        self.run_root('asus-entware')

    def test_openwrt_root_storage_and_native_library(self):
        self.run_root('openwrt')
