"""Verify exact-series native DNS payloads and exclude upstream service files."""
import hashlib,json,os,unittest
from pathlib import Path
from test_openwrt_builder import builder
CACHE=os.environ.get('NFQWS_TEST_SMARTDNS_CACHE')
@unittest.skipUnless(CACHE,'Requires verified OpenWrt SmartDNS cache')
class NativeSmartDnsPayload(unittest.TestCase):
    def test_engine_is_pinned_for_each_series_and_architecture(self):
        self.assertTrue(hasattr(builder,'smartdns_payload'),'Native SmartDNS packaging is missing')
        catalog=json.loads((builder.HERE/'smartdns-assets.json').read_text())
        for series,arches in catalog['artifacts'].items():
            for arch,record in arches.items():
                with self.subTest(series=series,arch=arch):
                    target=builder.native_metadata(series,arch)
                    files=builder.smartdns_payload(target,CACHE,True,os.environ.get('NFQWS_TEST_APK_TOOL'))
                    binary,mode=files['usr/share/nfqws2/optional/smartdns']
                    self.assertEqual(hashlib.sha256(binary).hexdigest(),record['binary_sha256']);self.assertEqual(mode,0o644)
                    artifact=json.loads(files['usr/share/nfqws2/smartdns-native-artifact.json'][0])
                    self.assertEqual((artifact['series'],artifact['arch']),(series,arch))
                    self.assertEqual(artifact['artifact']['files']['smartdns']['sha256'],hashlib.sha256(binary).hexdigest())
                    self.assertNotIn('etc/config/smartdns',files);self.assertNotIn('etc/init.d/smartdns',files)
                    self.assertIn('usr/lib/nfqws2/smartdns/runtime.sh',files)
                    self.assertNotIn('opt/', '\n'.join(files))

if __name__=='__main__':unittest.main()
