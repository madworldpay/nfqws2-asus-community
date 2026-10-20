import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'updates-feed'))


def load(name):
    path = ROOT/'updates-feed'/f'{name}.py'
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location('update_feed_' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


feed, publisher = load('server'), load('publish')


class PackageUpdateFeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory()
        cls.key = Path(cls.keys.name)/'ephemeral-key.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
                        'rsa_keygen_bits:3072', '-out', str(cls.key)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        cls.public = Path(cls.keys.name)/'public.pem'
        cls.public.write_bytes(subprocess.check_output(['openssl', 'pkey', '-in', str(cls.key), '-pubout']))

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.assertIsNotNone(feed, 'closed feed server missing')
        self.assertIsNotNone(publisher, 'atomic release publisher missing')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.store = self.base/'store'

    def release(self, build=11):
        source = self.base/f'input-{build}'
        source.mkdir()
        version = f'1.3.1-asus6+b{build}'
        packages = []
        for family in ['aarch64-3.10', 'armv7']:
            control = f'Package: nfqws2-asus\nVersion: {version}\nArchitecture: {"all" if family=="armv7" else family}\n'
            inner = io.BytesIO()
            with tarfile.open(fileobj=inner, mode='w:gz') as archive:
                info = tarfile.TarInfo('./control');info.size = len(control)
                archive.addfile(info, io.BytesIO(control.encode()))
            name = f'nfqws2-asus_{version}_{family}.ipk'
            with tarfile.open(source/name, 'w:gz') as archive:
                raw = inner.getvalue();info = tarfile.TarInfo('control.tar.gz');info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
            (source/name).chmod(0o644)
            raw = (source/name).read_bytes()
            packages.append({'family': family, 'filename': name, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        value = {'schema_version': 1, 'package_version': version, 'core_version': '1.3.1-asus6',
                 'web_version': '0.1.4', 'build': build, 'notes': 'Release notes.', 'packages': packages}
        (source/'release.json').write_text(json.dumps(value))
        (source/'release.json').chmod(0o644)
        return source, value

    def publish(self, source, **kwargs):
        return publisher.publish_release(source, self.key, self.store, **kwargs)

    @contextlib.contextmanager
    def server(self):
        server = feed.FeedServer(('127.0.0.1', 0), self.store, 'T'*43, owner=os.getuid())
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}/nfqws-updates/v1'
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)

    def request(self, url, token='T'*43, **headers):
        request = urllib.request.Request(url, headers={'Authorization': 'Bearer '+token, **headers})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def test_publish_exact_artifacts_and_detached_signature(self):
        source, value = self.release()
        result = self.publish(source)
        release = self.store/'releases'/value['package_version']
        manifest = (release/'manifest.json').read_bytes()
        self.assertEqual(json.loads(manifest), value)
        self.assertEqual(result['revision'], hashlib.sha256(manifest).hexdigest())
        signature = self.base/'signature';signature.write_bytes(base64.b64decode((release/'manifest.sig').read_bytes()))
        verify = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(self.public),
                                 '-signature', str(signature)], input=manifest, capture_output=True)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        for package in value['packages']:
            self.assertEqual((release/package['filename']).read_bytes(), (source/package['filename']).read_bytes())
        self.assertEqual(json.loads((self.store/'current.json').read_text()), {'version': value['package_version']})

    def test_private_config_and_auth_fail_without_reflecting_token(self):
        path = self.base/'credential';path.write_text(json.dumps({'token': 'T'*43, 'release_root': str(self.store)}));path.chmod(0o600)
        self.assertEqual(feed.load_config(path, owner=os.getuid())['token'], 'T'*43)
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'invalid_config'):feed.load_config(path, owner=os.getuid())
        self.publish(self.release()[0])
        with self.server() as url:
            status, raw, _ = self.request(url+'/manifest.json', token='WRONG_PRIVATE_TOKEN')
            self.assertEqual(status, 403);self.assertNotIn(b'WRONG_PRIVATE_TOKEN', raw)
            self.assertNotIn(b'package_version', raw)

    def test_systemd_readonly_group_credential_is_only_accepted_explicitly(self):
        path=self.base/'systemd-credential';path.write_text(json.dumps({'token':'T'*43,'release_root':str(self.store)}));path.chmod(0o440)
        with self.assertRaisesRegex(ValueError,'invalid_config'):feed.load_config(path,owner=os.getuid())
        self.assertEqual(feed.load_config(path,owner=os.getuid(),credential=True)['token'],'T'*43)
        path.chmod(0o444)
        with self.assertRaisesRegex(ValueError,'invalid_config'):feed.load_config(path,owner=os.getuid(),credential=True)

    def test_only_fixed_routes_and_exact_package_names_are_served(self):
        source, value = self.release();self.publish(source)
        with self.server() as url:
            self.assertEqual(self.request(url+'/manifest.json')[0], 200)
            name = value['packages'][0]['filename']
            self.assertEqual(self.request(url+'/packages/'+name)[1], (source/name).read_bytes())
            for suffix in ['/', '/packages/', '/packages/../current.json', '/packages/%2e%2e%2fcurrent.json',
                           '/manifest.json?secret=PRIVATE_QUERY', '/current.json', '/manifest.json/extra']:
                status, raw, _ = self.request(url+suffix)
                self.assertEqual(status, 404, suffix);self.assertNotIn(b'PRIVATE_QUERY', raw)

    def test_signature_is_bound_to_manifest_during_atomic_switch(self):
        source, _ = self.release();self.publish(source)
        with self.server() as url:
            raw = self.request(url+'/manifest.json')[1];revision = hashlib.sha256(raw).hexdigest()
            self.publish(self.release(12)[0])
            status, signature, _ = self.request(url+'/manifest.sig', **{'If-Match': '"'+revision+'"'})
            self.assertEqual(status, 200)
            path = self.base/'sig';path.write_bytes(base64.b64decode(signature))
            r = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(self.public), '-signature', str(path)], input=raw, capture_output=True)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(self.request(url+'/manifest.sig', **{'If-Match': '"'+'0'*64+'"'})[0], 412)

    def test_rotation_retains_current_and_previous_and_replay_is_immutable(self):
        for build in [11, 12, 13]:self.publish(self.release(build)[0])
        self.assertEqual(sorted(p.name for p in (self.store/'releases').iterdir()), ['1.3.1-asus6+b12', '1.3.1-asus6+b13'])
        source = self.base/'input-13'
        first = self.publish(source)
        self.assertEqual(self.publish(source), first)
        metadata = json.loads((source/'release.json').read_text());metadata['notes'] = 'Changed same Build.'
        (source/'release.json').write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'release_exists'):self.publish(source)

    def test_bad_hash_or_control_version_is_refused_before_switch(self):
        source, value = self.release();value['packages'][0]['sha256'] = '0'*64
        (source/'release.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'invalid_release'):self.publish(source)
        self.assertFalse((self.store/'current.json').exists())

    def test_signed_metadata_cannot_disagree_with_ipk_control_version(self):
        source, value = self.release()
        package = value['packages'][0]
        control = b'Package: nfqws2-asus\nVersion: 1.3.1-asus6+b9\nArchitecture: aarch64-3.10\n'
        inner = io.BytesIO()
        with tarfile.open(fileobj=inner, mode='w:gz') as archive:
            info = tarfile.TarInfo('./control');info.size = len(control)
            archive.addfile(info, io.BytesIO(control))
        with tarfile.open(source/package['filename'], 'w:gz') as archive:
            raw = inner.getvalue();info = tarfile.TarInfo('control.tar.gz');info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
        raw = (source/package['filename']).read_bytes()
        package.update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        (source/'release.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'invalid_release'):self.publish(source)
        self.assertFalse((self.store/'current.json').exists())

    def test_quota_refusal_keeps_previous_release_and_foreign_files(self):
        self.publish(self.release()[0]);before = (self.store/'current.json').read_bytes()
        foreign = self.store/'operator-note';foreign.write_text('keep')
        foreign.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'insufficient_space'):
            self.publish(self.release(12)[0], quota_bytes=1)
        self.assertEqual((self.store/'current.json').read_bytes(), before)
        self.assertEqual(foreign.read_text(), 'keep')

    def test_symlinks_are_not_served_or_deleted_as_owned_artifacts(self):
        source, value = self.release();self.publish(source)
        package = self.store/'releases'/value['package_version']/value['packages'][0]['filename']
        package.unlink();outside = self.base/'outside';outside.write_text('PRIVATE_OUTSIDE')
        package.symlink_to(outside)
        with self.server() as url:
            status, raw, _ = self.request(url+'/packages/'+package.name)
            self.assertNotEqual(status, 200);self.assertNotIn(b'PRIVATE_OUTSIDE', raw)
        with self.assertRaisesRegex(ValueError, 'invalid_state'):self.publish(self.release(12)[0])
        self.assertEqual(outside.read_text(), 'PRIVATE_OUTSIDE')


if __name__ == '__main__':
    unittest.main()
