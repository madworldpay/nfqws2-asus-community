"""Inspect actual IPK/APK artifacts; build checks are separate from hardware tests."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PACKAGE_DIR=os.environ.get('NFQWS_TEST_PACKAGE_DIR')
ARCHES=json.loads((ROOT/'openwrt/release-targets.json').read_text())['architectures']
APK_TOOL=os.environ.get('NFQWS_TEST_APK_TOOL')
spec=importlib.util.spec_from_file_location('artifact_builder',ROOT/'openwrt/build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


@unittest.skipUnless(PACKAGE_DIR,'Requires native artifact build matrix')
class NativeArtifactTests(unittest.TestCase):
    def check_engine(self,profile,data):
        target=builder.native_metadata(profile['series'],profile['arch'])
        builder.platform.validate_engine(data,target)
        self.assertEqual(hashlib.sha256(data).hexdigest(),builder.ASSETS['engines'][target['engine']]['unpacked_sha256'])

    def test_native_ipks_have_correct_ownership_scope_and_engine_per_family(self):
        packages=sorted(Path(PACKAGE_DIR).glob('nfqws2-native*.ipk')) or sorted(Path(PACKAGE_DIR).glob('24.10/*/*.ipk'))
        self.assertEqual(len(packages),len(ARCHES))
        for package in packages:
            with self.subTest(arch=package.parent.name),tarfile.open(package)as outer:
                streams={m.name.removeprefix('./'):outer.extractfile(m).read()for m in outer if m.isfile()}
                with tarfile.open(fileobj=io.BytesIO(streams['data.tar.gz']))as data:
                    for m in data:
                        self.assertEqual((m.uid,m.gid),(0,0),m.name)
                        self.assertEqual(m.mode&0o022,0,m.name)
                        self.assertFalse(m.name.startswith('./opt/'))
                        self.assertFalse(m.name.endswith('.ko'))
                    profile=json.load(data.extractfile('./usr/share/nfqws2/platform.json'))
                    self.assertIn(profile['arch'],ARCHES)
                    self.assertTrue(package.name.endswith('_'+profile['arch']+'.ipk'))
                    self.check_engine(profile,data.extractfile('./usr/bin/nfqws2').read())
                with tarfile.open(fileobj=io.BytesIO(streams['control.tar.gz']))as control:
                    text=control.extractfile('./control').read().decode()
                    self.assertIn('Architecture: '+profile['arch']+'\n',text)
                    self.assertIn('Package: nfqws2-native\n',text)

    @unittest.skipUnless(APK_TOOL,'Requires the official SDK apk reader')
    def test_native_apks_are_readable_by_apk_and_contain_the_selected_static_engine(self):
        packages=sorted(Path(PACKAGE_DIR).glob('nfqws2-native*.apk')) or sorted(Path(PACKAGE_DIR).glob('25.12/*/*.apk'))
        self.assertEqual(len(packages),len(ARCHES))
        for package in packages:
            with self.subTest(arch=package.parent.name):
                result=subprocess.run([APK_TOOL,'adbdump',str(package)],text=True,capture_output=True,check=True,timeout=20)
                text=result.stdout
                arch=re.fullmatch(r'nfqws2-native_[^_]+_(.+)\.apk',package.name)[1]
                self.assertIn(arch,ARCHES)
                self.assertIn('  arch: '+arch+'\n',text)
                self.assertIn('  name: nfqws2-native\n',text)
                for mode in re.findall(r'^\s+mode: (0[0-7]+)$',text,re.M):self.assertEqual(int(mode,8)&0o022,0,mode)
                self.assertEqual(set(re.findall(r'^\s+user: (.+)$',text,re.M)),{'root'})
                with tempfile.TemporaryDirectory()as td:
                    subprocess.run([APK_TOOL,'extract','--allow-untrusted','--no-chown','--destination',td,str(package)],
                        check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
                    root=Path(td);profile=json.loads((root/'usr/share/nfqws2/platform.json').read_text())
                    self.check_engine(profile,(root/'usr/bin/nfqws2').read_bytes())
                    self.assertFalse((root/'opt').exists())


if __name__=='__main__':unittest.main()
