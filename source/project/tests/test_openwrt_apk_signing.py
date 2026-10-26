"""Create a real APK and verify its signature with the official native tool."""
import os,subprocess,tempfile,unittest
from pathlib import Path
from test_openwrt_builder import builder

CACHE=os.environ.get('NFQWS_TEST_SMARTDNS_CACHE')
APK=os.environ.get('NFQWS_TEST_APK_TOOL')

@unittest.skipUnless(CACHE and APK,'Requires pinned SDK and native asset cache')
class NativeApkSigning(unittest.TestCase):
    def test_created_apk_verifies_with_own_key_and_rejects_missing_key_or_tamper(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);key=root/'private.pem';keys=root/'keys';keys.mkdir();stage=root/'payload';out=root/'out';out.mkdir()
            subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            key.chmod(0o600)
            subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(keys/'native.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            target=builder.native_metadata('25.12','x86_64',72);target['dependencies']=[]
            builder.write_files(stage,{'usr/share/nfqws2/signature-fixture.txt':(b'verified native package\n',0o644)})
            hooks={name:b'#!/bin/sh\nexit 0\n'for name in ['preinst','postinst','prerm','postrm']}
            pkg=builder.build_apk(target,stage,hooks,CACHE,out,True,sign_key=key)
            self.assertEqual(pkg.name,'nfqws2-native_1.3.2-r72_x86_64.apk')
            good=subprocess.run([APK,'verify','--keys-dir',str(keys),str(pkg)],capture_output=True,text=True)
            self.assertEqual(good.returncode,0,good.stdout+good.stderr)
            bad=subprocess.run([APK,'verify',str(pkg)],capture_output=True,text=True)
            self.assertNotEqual(bad.returncode,0,'An unrelated native/system keyring must not trust this key')
            raw=bytearray(pkg.read_bytes());raw[len(raw)//2]^=1;pkg.write_bytes(raw)
            tampered=subprocess.run([APK,'verify','--keys-dir',str(keys),str(pkg)],capture_output=True,text=True)
            self.assertNotEqual(tampered.returncode,0,'A trusted key must not permit corrupt payload bytes')

if __name__=='__main__':unittest.main()
