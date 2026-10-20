import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class DpiCatalogTests(unittest.TestCase):
    def test_profile_is_pinned_and_does_not_include_unbounded_targets(self):
        catalog_path=ROOT/'support/dpi-catalog.json'
        self.assertTrue(catalog_path.is_file(),'optional detector manifest has not been implemented')
        c=json.loads(catalog_path.read_text())
        self.assertEqual([g['id'] for g in c['groups']],list(range(7)))
        self.assertEqual(c['default_groups'],[1,2])
        self.assertEqual(len(c['profile']['dns']),9)
        self.assertEqual(len(c['profile']['domains']),6)
        self.assertEqual(len(c['profile']['tcp']),8)
        self.assertEqual(len(c['profile']['sni']),16)
        profile=json.dumps(c['profile'],ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()
        self.assertEqual(c['profile_sha256'],hashlib.sha256(profile).hexdigest())
        self.assertEqual(c['artifacts']['aarch64-3.10']['sha256'],'721e005cee83a72d17b403a26bd051fed280f9fd44218d517329f0a60f8ea27a')
        legacy=c['artifacts']['armv7-2.6']
        self.assertEqual(legacy['source'],'bundled-legacy')
        self.assertEqual(legacy['sha256'],'c0e0045bab2ae654a9f0fef125602fc042b6f54705afdfa0d6bfc10557e74863')
        self.assertEqual(legacy['accepted_installed'],[c['artifacts']['armv7-3.2']])
