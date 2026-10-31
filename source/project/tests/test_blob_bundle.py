"""Pinned blob bytes and metadata are identical in both package families."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class BlobBundleTests(unittest.TestCase):
    def setUp(self):
        self.loader = module('blob_bundle', ROOT / 'asus/blob_bundle.py')

    def test_twelve_pinned_files_have_closed_runtime_metadata_and_public_sources(self):
        files, catalog, sources = self.loader.load_bundle()
        self.assertEqual(len(files), 12)
        self.assertEqual(set(catalog), {'schema_version', 'files'})
        self.assertEqual(catalog['schema_version'], 1)
        self.assertEqual(len(catalog['files']), 12)
        self.assertEqual({item['format'] for item in catalog['files']}, {'tls', 'quic', 'stun'})
        for item in catalog['files']:
            self.assertEqual(set(item), {'name', 'sha256', 'byte_length', 'format', 'label'})
            data = files[item['name']]
            self.assertEqual(item['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(item['byte_length'], len(data))
        self.assertTrue(all(item['source_repo'] == 'bol-van/zapret2' and item['source_ref'] == '221d7dff24bfec0cd5ac0a5070b8acef2008af3d' for item in sources['files']))

    def test_build_refuses_changed_bytes_unsafe_names_symlinks_and_unlisted_files(self):
        for mutation in ['bytes', 'name', 'symlink', 'unlisted']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                directory = Path(td) / 'blobs'
                shutil.copytree(ROOT / 'asus/blobs', directory)
                path = directory / 'files/tls_clienthello.bin'
                if mutation == 'bytes':
                    path.write_bytes(b'wrong')
                elif mutation == 'symlink':
                    path.unlink(); path.symlink_to('/dev/null')
                elif mutation == 'unlisted':
                    (directory / 'files/extra.bin').write_bytes(b'unknown')
                else:
                    catalog = json.loads((directory / 'catalog.json').read_text())
                    catalog['files'][0]['name'] = '../bad.bin'
                    (directory / 'catalog.json').write_text(json.dumps(catalog))
                with self.assertRaises((ValueError, RuntimeError)):
                    self.loader.load_bundle(directory)

    @unittest.skipUnless(os.environ.get('NFQWS_TEST_ENGINE_DIR'), 'Requires verified engines')
    def test_native_payload_seeds_every_blob_and_pins_it_in_baseline(self):
        builder = module('native_blob_builder', ROOT / 'openwrt/build.py')
        target = builder.native_metadata('24.10', 'arm_cortex-a9', 76)
        engine = (Path(os.environ['NFQWS_TEST_ENGINE_DIR']) / 'nfqws2-armv7').read_bytes()
        files, catalog, sources = self.loader.load_bundle()
        payload = builder.payload_files(target, engine)
        baseline = json.loads(payload['usr/share/nfqws2/report-baseline.json'][0])
        self.assertEqual(json.loads(payload['usr/share/nfqws2/blob-catalog.json'][0]), catalog)
        self.assertEqual(json.loads(payload['usr/share/nfqws2/blob-sources.json'][0]), sources)
        for name, data in files.items():
            self.assertEqual(payload['usr/share/nfqws2/defaults/blobs/' + name], (data, 0o644))
            self.assertEqual(baseline['resources']['blob/' + name], {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            self.assertNotIn('etc/nfqws2/blobs/' + name, payload)
        with self.assertRaisesRegex(RuntimeError, 'blob'):
            builder.payload_files(target, engine, {'opt/etc/nfqws2/blobs/tls_clienthello.bin': b'changed upstream'})


if __name__ == '__main__':
    unittest.main()
