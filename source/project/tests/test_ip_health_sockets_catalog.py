"""Family payloads retain both exact legacy PHP choices as inert pinned data."""
import hashlib
import importlib.util
import json
import unittest

from test_ip_health_sockets import FIXTURES, ROOT

spec=importlib.util.spec_from_file_location('ip_health_multi_php_builder',ROOT/'asus/build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


@unittest.skipUnless((FIXTURES/'php8-mod-sockets_8.4.7-1_armv7-2.6.ipk').is_file(),'verified Gary legacy sockets fixture required')
class MultiVersionSocketsCatalogTests(unittest.TestCase):
    def payload(self,family):
        files=builder.ip_health_sockets_payload(FIXTURES,True,family)
        catalog=json.loads(files['opt/share/nfqws2-asus/ip-health-sockets/catalog.json'][0])
        for entry in catalog['entries']:
            raw,mode=files['opt/share/nfqws2-asus/ip-health-sockets/ipks/'+entry['filename']]
            self.assertEqual(mode,0o644)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),entry['sha256'])
        self.assertFalse(any(name.startswith(('opt/etc/','opt/bin/','opt/lib/')) for name in files))
        return catalog['entries']

    def test_arm_package_keeps_both_legacy_php_versions_and_the_modern_choice(self):
        entries=self.payload('armv7')
        self.assertEqual({(e['abi'],e['php_package_version']) for e in entries},{('armv7-2.6','8.2.8-1'),('armv7-2.6','8.4.7-1'),('armv7-3.2','8.4.16-4')})
        self.assertEqual(len(entries),3)

    def test_aarch64_package_cannot_ship_either_legacy_arm_choice(self):
        entries=self.payload('aarch64-3.10')
        self.assertEqual([(e['abi'],e['php_package_version']) for e in entries],[('aarch64-3.10','8.4.16-4')])
