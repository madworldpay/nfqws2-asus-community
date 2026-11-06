"""Public add-on publication exercises real files and ephemeral RSA keys only."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
PUBLISHER = HERE / 'addons.py'


class AddonPublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory()
        cls.key = Path(cls.keys.name) / 'ephemeral-test-only.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
                        'rsa_keygen_bits:3072', '-out', str(cls.key)],
                       check=True, capture_output=True)
        cls.key.chmod(0o600)
        cls.public = subprocess.check_output(['openssl', 'pkey', '-in', str(cls.key), '-pubout'])

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.inputs = self.base / 'reviewed'
        self.inputs.mkdir()
        self.output = self.base / 'v1' / 'addons'
        self.metadata = self.base / 'approved.json'
        self.document = {'type': 'nfqws2_import_addon', 'schema_version': 1,
                         'id': 'riot-web', 'title': 'Riot web domain scope',
                         'description': 'Web domains use the selected base strategy. Game UDP is not verified.',
                         'kind': 'scope_domains_v1', 'domains': ['riotgames.com', 'riotcdn.net']}
        self.approval = {'schema_version': 1, 'revision': 1, 'addons': [{
            'id': 'riot-web', 'title': self.document['title'],
            'description': self.document['description'], 'attribution': 'Original public example',
            'updated_at': '2026-11-06T00:00:00Z', 'revision': 1, 'min_build': 92,
            'file': 'riot-web.json', 'source_sha256': ''}]}
        self.review()

    def review(self, document=None, raw=None):
        if document is not None:
            self.document = document
        self.raw = raw if raw is not None else json.dumps(self.document, ensure_ascii=False, indent=2).encode() + b'\n'
        (self.inputs / 'riot-web.json').write_bytes(self.raw)
        self.approval['addons'][0]['source_sha256'] = hashlib.sha256(self.raw).hexdigest()

    def run_publisher(self, success=True, key=None, output=None, write_metadata=True):
        if write_metadata:
            self.metadata.write_text(json.dumps(self.approval), encoding='utf-8')
        result = subprocess.run([sys.executable, str(PUBLISHER), '--metadata', str(self.metadata),
                                 '--addons-dir', str(self.inputs), '--key', str(key or self.key),
                                 '--output', str(output or self.output)],
                                capture_output=True, text=True, timeout=20)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def envelope(self, output=None):
        envelope = json.loads(((output or self.output) / 'catalog.json').read_bytes())
        self.assertEqual(set(envelope), {'manifest', 'signature'})
        raw = base64.b64decode(envelope['manifest'], validate=True)
        signature = base64.b64decode(envelope['signature'], validate=True)
        public = self.base / 'public.pem'
        public.write_bytes(self.public)
        signature_file = self.base / 'signature.bin'
        signature_file.write_bytes(signature)
        verify = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(public),
                                 '-signature', str(signature_file)], input=raw, capture_output=True)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertEqual(len(signature), 384)
        return json.loads(raw), raw

    def test_exact_reviewed_bytes_signed_hash_and_deterministic_envelope(self):
        self.run_publisher()
        manifest, raw = self.envelope()
        digest = hashlib.sha256(self.raw).hexdigest()
        self.assertEqual(manifest, {'schema_version': 1, 'revision': 1, 'addons': [{
            'id': 'riot-web', 'title': 'Riot web domain scope',
            'description': 'Web domains use the selected base strategy. Game UDP is not verified.',
            'attribution': 'Original public example', 'updated_at': '2026-11-06T00:00:00Z',
            'revision': 1, 'min_build': 92, 'size': len(self.raw), 'sha256': digest}]})
        self.assertEqual((self.output / 'files' / (digest + '.json')).read_bytes(), self.raw)
        self.assertEqual({str(p.relative_to(self.output)) for p in self.output.rglob('*') if p.is_file()},
                         {'catalog.json', 'files/' + digest + '.json'})
        second = self.base / 'second' / 'addons'
        self.run_publisher(output=second)
        self.assertEqual((self.output / 'catalog.json').read_bytes(), (second / 'catalog.json').read_bytes())
        self.approval['addons'][0] = dict(reversed(list(self.approval['addons'][0].items())))
        reordered = self.base / 'reordered' / 'addons'
        self.run_publisher(output=reordered)
        self.assertEqual((self.output / 'catalog.json').read_bytes(), (reordered / 'catalog.json').read_bytes())
        self.assertEqual(raw, json.dumps(manifest, ensure_ascii=False, separators=(',', ':')).encode())
        self.assertNotIn(b'PRIVATE KEY', (self.output / 'catalog.json').read_bytes())
        tampered = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(self.base / 'public.pem'),
                                   '-signature', str(self.base / 'signature.bin')],
                                  input=raw + b' ', capture_output=True)
        self.assertNotEqual(tampered.returncode, 0)

    def test_new_revision_keeps_old_objects_and_old_revision_cannot_replace_catalog(self):
        self.run_publisher()
        before = (self.output / 'catalog.json').read_bytes()
        old = hashlib.sha256(self.raw).hexdigest()
        for revision in [1, 0]:
            self.approval['revision'] = revision
            self.run_publisher(False)
            self.assertEqual((self.output / 'catalog.json').read_bytes(), before)
        self.approval['revision'] = 2
        self.approval['addons'][0]['revision'] = 2
        self.document['domains'].append('playvalorant.com')
        self.review()
        self.run_publisher()
        self.assertEqual(self.envelope()[0]['revision'], 2)
        self.assertTrue((self.output / 'files' / (old + '.json')).is_file())
        self.assertEqual(len(list((self.output / 'files').glob('*.json'))), 2)

    def test_unreviewed_bytes_and_corrupt_immutable_object_leave_catalog_intact(self):
        self.run_publisher()
        before = (self.output / 'catalog.json').read_bytes()
        self.approval['revision'] = 2
        (self.inputs / 'riot-web.json').write_bytes(self.raw + b' ')
        self.assertIn('review', self.run_publisher(False).stderr)
        (self.inputs / 'riot-web.json').write_bytes(self.raw)
        (self.output / 'files' / (hashlib.sha256(self.raw).hexdigest() + '.json')).write_bytes(b'corrupt')
        self.assertIn('immutable', self.run_publisher(False).stderr)
        self.assertEqual((self.output / 'catalog.json').read_bytes(), before)

    def test_rejects_non_public_domains_and_duplicate_or_unnormalized_names(self):
        invalid = ['127.0.0.1', '8.8.8.8', '2001:4860:4860::8888', '*.riotgames.com',
                   'https://riotgames.com', 'riotgames.com/path', 'riotgames.com:443',
                   'riotgames.com;reboot', '$(reboot).com', 'a_b.com', '-a.com', 'a-.com',
                   'a..com', 'RIOTGAMES.COM', 'riotgames.com.', ' riotgames.com',
                   'localhost', 'router.local', 'router.lan', 'router.home', 'router.internal',
                   'site.invalid', 'site.test', 'site.example', 'service.onion', 'router.home.arpa',
                   'a.123', 'a.' + 'b' * 64, 'a' * 64 + '.com', 'éxample.com', 'a.com\n']
        for domain in invalid:
            with self.subTest(domain=domain):
                self.document['domains'] = [domain]
                self.review()
                self.assertIn('domain', self.run_publisher(False).stderr)
        for domains in [[], ['riotgames.com', 'riotgames.com'], ['site%d.com' % i for i in range(65)], [7], 'riotgames.com']:
            with self.subTest(domains=domains):
                self.document['domains'] = domains
                self.review()
                self.run_publisher(False)
        self.assertFalse(self.output.exists())

    def test_only_exact_data_schema_and_matching_reviewed_identity_are_allowed(self):
        original = copy.deepcopy(self.document)
        mutations = [dict(type='strategy'), dict(schema_version=True), dict(schema_version=2),
                     dict(kind='lua'), dict(lua='return true'), dict(dns={'server': '8.8.8.8'}),
                     dict(id='different'), dict(title='Different title'), dict(description='Different scope')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.review(original | mutation)
                self.run_publisher(False)
        self.review(raw=b'{"type":"nfqws2_import_addon","type":"strategy"}')
        self.assertIn('duplicate', self.run_publisher(False).stderr)
        self.review(raw=b'{"domains":[NaN]}')
        self.run_publisher(False)
        self.assertFalse(self.output.exists())

    def test_documents_are_strict_utf8_json_and_oversized_inputs_are_never_signed(self):
        for raw in [json.dumps(self.document).encode('utf-16'),
                    b'\xef\xbb\xbf' + json.dumps(self.document).encode(), b' ' * 65537]:
            with self.subTest(prefix=raw[:12]):
                self.review(raw=raw)
                self.run_publisher(False)
        self.assertFalse(self.output.exists())

    def test_invalid_last_entry_never_partially_writes_new_public_objects(self):
        self.approval['addons'].append(self.approval['addons'][0] | {
            'id': 'bad-second', 'file': 'second.json', 'source_sha256': '0' * 64})
        (self.inputs / 'second.json').write_bytes(b'{}')
        self.run_publisher(False)
        self.assertFalse(self.output.exists())

    def test_metadata_bounds_closed_fields_unique_ids_and_real_utc_dates(self):
        original = copy.deepcopy(self.approval)
        changes = [('id', 'bad.id'), ('id', 'a' * 65), ('title', ' '), ('title', 't' * 121),
                   ('description', 'd' * 601), ('attribution', 'a' * 241),
                   ('updated_at', '2026-02-30T00:00:00Z'), ('updated_at', '2026-11-06T00:00:00+00:00'),
                   ('revision', True), ('revision', 0), ('revision', 2147483648),
                   ('min_build', 91), ('min_build', 1000000000), ('file', '../riot-web.json'),
                   ('source_sha256', 'A' * 64), ('url', 'https://other.test/file.json')]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                self.approval = copy.deepcopy(original)
                self.approval['addons'][0][field] = value
                self.run_publisher(False)
        for mutation in [dict(schema_version=True), dict(revision=True), dict(revision=2147483648),
                         dict(profiles=[]), dict(addons=original['addons'] * 2), dict(addons=original['addons'] * 65)]:
            with self.subTest(mutation=mutation):
                self.approval = original | mutation
                self.run_publisher(False)
        self.assertFalse(self.output.exists())

    def test_64_domains_and_empty_catalog_are_supported_without_expanding_authority(self):
        self.document['domains'] = ['site%d.com' % index for index in range(64)]
        self.review()
        self.run_publisher()
        self.assertEqual(len(json.loads((self.output / 'files' / (hashlib.sha256(self.raw).hexdigest() + '.json')).read_bytes())['domains']), 64)
        self.approval = {'schema_version': 1, 'revision': 2, 'addons': []}
        self.run_publisher()
        self.assertEqual(self.envelope()[0], {'schema_version': 1, 'revision': 2, 'addons': []})

    def test_existing_profile_feed_is_untouched_and_wrong_output_directory_is_refused(self):
        self.output.parent.mkdir()
        legacy = self.output.parent / 'catalog.json'
        legacy.write_bytes(b'closed-profile-v1-canary')
        self.run_publisher()
        self.assertEqual(legacy.read_bytes(), b'closed-profile-v1-canary')
        self.run_publisher(False, output=self.output.parent)
        self.assertEqual(legacy.read_bytes(), b'closed-profile-v1-canary')

    def test_signing_key_is_explicit_rsa3072_private_and_outside_output(self):
        self.metadata.write_text(json.dumps(self.approval))
        missing = subprocess.run([sys.executable, str(PUBLISHER), '--metadata', str(self.metadata),
                                  '--addons-dir', str(self.inputs), '--output', str(self.output)],
                                 capture_output=True, text=True, timeout=20,
                                 env=os.environ | {'NFQWS_CATALOG_PRIVATE_KEY': str(self.key)})
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('--key', missing.stderr)
        for algorithm, options in [('RSA', ['-pkeyopt', 'rsa_keygen_bits:2048']),
                                   ('EC', ['-pkeyopt', 'ec_paramgen_curve:P-256'])]:
            key = self.base / (algorithm + '.pem')
            subprocess.run(['openssl', 'genpkey', '-algorithm', algorithm, *options, '-out', str(key)],
                           check=True, capture_output=True)
            key.chmod(0o600)
            self.run_publisher(False, key=key)
        public_key = self.base / 'not-private.pem'
        public_key.write_bytes(self.public)
        public_key.chmod(0o600)
        self.run_publisher(False, key=public_key)
        bad_permissions = self.base / 'open.pem'
        bad_permissions.write_bytes(self.key.read_bytes())
        bad_permissions.chmod(0o644)
        self.assertIn('permissions', self.run_publisher(False, key=bad_permissions).stderr)
        inside_output = self.base / 'private-inside' / 'addons'
        inside_output.mkdir(parents=True)
        inside_key = inside_output / 'private.pem'
        inside_key.write_bytes(self.key.read_bytes())
        inside_key.chmod(0o600)
        self.assertIn('outside', self.run_publisher(False, key=inside_key, output=inside_output).stderr)
        self.assertFalse((inside_output / 'catalog.json').exists())
        self.assertFalse(self.output.exists())

    def test_symlinks_hardlinks_and_inputs_inside_served_directory_are_refused(self):
        source = self.inputs / 'riot-web.json'
        saved = self.base / 'saved.json'
        source.rename(saved)
        source.symlink_to(saved)
        self.run_publisher(False)
        source.unlink()
        os.link(saved, source)
        self.run_publisher(False)
        source.unlink()
        source.write_bytes(self.raw)
        self.output.parent.mkdir()
        self.output.symlink_to(self.inputs, target_is_directory=True)
        self.run_publisher(False)
        self.output.unlink()
        self.output = self.inputs / 'addons' / '..'
        self.run_publisher(False)
        self.assertFalse((self.inputs / 'catalog.json').exists())

    def test_forged_previous_envelope_cannot_be_replaced_even_at_new_revision(self):
        self.run_publisher()
        catalog = self.output / 'catalog.json'
        original = json.loads(catalog.read_bytes())
        self.approval['revision'] = 2
        for mutation in [dict(signature=base64.b64encode(b'x' * 384).decode()),
                         dict(manifest=base64.b64encode(b'{}').decode()), dict(url='https://other.test')]:
            with self.subTest(mutation=mutation):
                corrupted = json.dumps(original | mutation).encode()
                catalog.write_bytes(corrupted)
                self.run_publisher(False)
                self.assertEqual(catalog.read_bytes(), corrupted)

    def test_public_riot_seed_is_publishable_with_exact_reviewed_domain_scope(self):
        self.inputs = HERE / 'examples'
        self.metadata = self.inputs / 'approved-addons.example.json'
        self.run_publisher(write_metadata=False)
        manifest, _ = self.envelope()
        self.assertEqual(len(manifest['addons']), 1)
        entry = manifest['addons'][0]
        self.assertEqual(entry['min_build'], 92)
        published = json.loads((self.output / 'files' / (entry['sha256'] + '.json')).read_bytes())
        self.assertEqual(published['domains'], ['riotgames.com', 'riotcdn.net',
                                                'leagueoflegends.com', 'playvalorant.com'])
        self.assertEqual(published['kind'], 'scope_domains_v1')
        self.assertIn('базовой стратегией', published['title'])
        self.assertIn('не является проверенным обходом игрового UDP', published['description'])

    def test_catalog_accepts_64_entries_and_rejects_a_manifest_over_65536_bytes(self):
        template = self.approval['addons'][0]
        self.approval['addons'] = []
        for index in range(64):
            identity = 'web-%d' % index
            document = self.document | {'id': identity}
            raw = json.dumps(document).encode()
            filename = identity + '.json'
            (self.inputs / filename).write_bytes(raw)
            self.approval['addons'].append(template | {'id': identity, 'file': filename,
                                                       'source_sha256': hashlib.sha256(raw).hexdigest()})
        self.run_publisher()
        self.assertEqual(len(self.envelope()[0]['addons']), 64)
        for entry in self.approval['addons']:
            document = self.document | {'id': entry['id'], 'title': 't' * 120, 'description': 'd' * 600}
            raw = json.dumps(document).encode()
            (self.inputs / entry['file']).write_bytes(raw)
            entry.update(title=document['title'], description=document['description'],
                         attribution='a' * 240, source_sha256=hashlib.sha256(raw).hexdigest())
        target = self.base / 'oversized' / 'addons'
        self.assertIn('catalog too large', self.run_publisher(False, output=target).stderr)
        self.assertFalse(target.exists())

    @unittest.skipUnless(os.environ.get('PHP_TEST_BINARY'), 'PHP_TEST_BINARY with OpenSSL enables client compatibility check')
    def test_published_seed_is_accepted_by_the_actual_php_client(self):
        self.inputs = HERE / 'examples'
        self.metadata = self.inputs / 'approved-addons.example.json'
        self.run_publisher(write_metadata=False)
        manifest, _ = self.envelope()
        code = """require $argv[1].'/import-addon-catalog.php';
          $index=AsusImportAddonCatalog::verify(file_get_contents($argv[2]),file_get_contents($argv[3]));
          $document=AsusImportAddonCatalog::document(file_get_contents($argv[4]));
          echo json_encode(['index'=>$index,'document'=>$document],JSON_THROW_ON_ERROR);"""
        document = self.output / 'files' / (manifest['addons'][0]['sha256'] + '.json')
        result = subprocess.run([os.environ['PHP_TEST_BINARY'], '-n', '-r', code,
                                 str(HERE.parent / 'webui/web/public'), str(self.output / 'catalog.json'),
                                 str(self.base / 'public.pem'), str(document)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        verified = json.loads(result.stdout)
        self.assertEqual(verified['index'], manifest)
        self.assertEqual(verified['document'], json.loads(document.read_bytes()))


if __name__ == '__main__':
    unittest.main()
