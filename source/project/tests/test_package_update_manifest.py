import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_TLS_TEST_BINARY')
OPENSSL = os.environ.get('PHP_OPENSSL_TEST_EXTENSION')


@unittest.skipUnless(PHP and OPENSSL, 'matching PHP/OpenSSL test runtime required')
class PackageUpdateManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.key = Path(cls.tmp.name) / 'ephemeral-test-key.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
                        'rsa_keygen_bits:3072', '-out', str(cls.key)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.public = subprocess.check_output(['openssl', 'pkey', '-in', str(cls.key), '-pubout']).decode()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def manifest(self):
        version = '1.3.1-asus6+b11'
        return {'schema_version': 1, 'package_version': version, 'core_version': '1.3.1-asus6',
                'web_version': '0.1.4', 'build': 11, 'notes': 'Новые настройки DPI.',
                'packages': [{'family': family, 'filename': f'nfqws2-asus_{version}_{family}.ipk',
                              'size': 1500000, 'sha256': 'a' * 64}
                             for family in ['aarch64-3.10', 'armv7']]}

    def signed(self, value):
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        sig = subprocess.check_output(['openssl', 'dgst', '-sha256', '-sign', str(self.key)], input=raw.encode())
        return raw, base64.b64encode(sig).decode()

    def call(self, value=None, *, raw=None, signature=None, family=None, installed='1.3.1-asus6+b10'):
        if raw is None:
            raw, default_sig = self.signed(self.manifest() if value is None else value)
        else:
            _, default_sig = self.signed(raw)
        payload = {'raw': raw, 'signature': default_sig if signature is None else signature,
                   'key': self.public, 'family': family, 'installed': installed}
        script = '''if(!is_file($argv[1])){echo json_encode(['error'=>'missing_manifest']);exit;}
        require $argv[1];$p=json_decode(stream_get_contents(STDIN),true);
        try{$v=AsusPackageManifest::verify($p['raw'],$p['signature'],$p['key']);
        if($p['family']!==null)$v=AsusPackageManifest::candidate($v,$p['family'],$p['installed']);
        echo json_encode(['value'=>$v]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        r = subprocess.run([PHP, '-n', '-d', 'extension=' + OPENSSL, '-r', script,
                            str(ROOT / 'webui/web/public/update-manifest.php')],
                           input=json.dumps(payload), text=True, capture_output=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stderr, '')
        return json.loads(r.stdout)

    def test_exact_signed_bytes_and_build_only_candidate(self):
        raw, signature = self.signed(self.manifest())
        verified = self.call(raw=raw, signature=signature)['value']
        self.assertEqual(verified['revision'], hashlib.sha256(raw.encode()).hexdigest())
        candidate = self.call(raw=raw, signature=signature, family='armv7')['value']
        self.assertEqual(candidate['build'], 11)
        self.assertEqual(candidate['core_version'], '1.3.1-asus6')
        self.assertEqual(candidate['web_version'], '0.1.4')
        self.assertEqual(candidate['package']['family'], 'armv7')

    def test_changed_bytes_or_invalid_signature_are_rejected(self):
        raw, signature = self.signed(self.manifest())
        self.assertEqual(self.call(raw=raw + ' ', signature=signature), {'error': 'invalid_signature'})
        for sig in ['!', signature[:-4], signature + 'A', 'A' * 1100]:
            self.assertEqual(self.call(raw=raw, signature=sig), {'error': 'invalid_signature'})
        self.assertIn('value', self.call(raw=raw, signature=signature + '\n'))

    def test_closed_schema_rejects_duplicate_and_unknown_fields(self):
        raw, _ = self.signed(self.manifest())
        self.assertEqual(self.call(raw=raw[:-1] + ',"build":11}'), {'error': 'invalid_manifest'})
        value = self.manifest()
        value['url'] = 'https://untrusted.invalid/file.ipk'
        self.assertEqual(self.call(value), {'error': 'invalid_manifest'})

    def test_filename_hash_size_and_release_identity_are_bound(self):
        changes = [({'build': 12}, None), ({'build': True}, None),
                   ({'core_version': '1.3.1-asus5'}, None),
                   ({'web_version': 'latest'}, None), ({'packages': []}, None),
                   ({'notes': 'x' * 2001}, None),
                   ({'filename': '../nfqws2-asus.ipk'}, 0),
                   ({'filename': 'https://untrusted.invalid/file.ipk'}, 0),
                   ({'size': 33554433}, 0), ({'size': 1.5}, 0),
                   ({'sha256': 'z' * 64}, 0), ({'family': 'all'}, 0)]
        for change, index in changes:
            with self.subTest(change=change):
                value = self.manifest()
                (value if index is None else value['packages'][index]).update(change)
                self.assertEqual(self.call(value), {'error': 'invalid_manifest'})

    def test_duplicate_or_missing_target_family_is_not_a_current_release(self):
        value = self.manifest()
        value['packages'][1] = copy.deepcopy(value['packages'][0])
        self.assertEqual(self.call(value), {'error': 'invalid_manifest'})
        value = self.manifest()
        value['packages'] = value['packages'][:1]
        self.assertEqual(self.call(value, family='armv7'), {'error': 'unsupported_package'})
        self.assertEqual(self.call(family='mips'), {'error': 'unsupported_abi'})

    def test_same_build_or_signed_core_downgrade_does_not_offer_install(self):
        self.assertEqual(self.call(family='armv7', installed='1.3.1-asus6+b11'), {'value': None})
        self.assertEqual(self.call(family='armv7', installed='1.3.1-asus6+b12'), {'value': None})
        self.assertEqual(self.call(family='armv7', installed='1.3.1-asus7+b10'), {'value': None})
        self.assertEqual(self.call(family='armv7', installed='garbage'), {'error': 'unsupported_version'})

    def test_higher_core_version_requires_a_higher_global_build(self):
        self.assertIsNotNone(self.call(family='aarch64-3.10', installed='1.3.0-asus6+b10')['value'])
        self.assertEqual(self.call(family='aarch64-3.10', installed='1.3.0-asus6+b11'), {'value': None})

    def test_size_limit_applies_even_to_signed_json(self):
        raw, _ = self.signed(self.manifest())
        self.assertEqual(self.call(raw=raw + ' ' * 32768), {'error': 'invalid_manifest'})


if __name__ == '__main__':
    unittest.main()
