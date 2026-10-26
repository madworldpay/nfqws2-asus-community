"""Native publication metadata comes from verified coherent artifacts, never filenames alone."""
import importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_openwrt_update_package import ROOT,builder,CACHE,APK_TOOL
class NativeRelease(unittest.TestCase):
 def module(self):
  p=ROOT/'openwrt/release.py';self.assertTrue(p.is_file(),'Native releases need a reproducible independent signed manifest pipeline')
  spec=importlib.util.spec_from_file_location('native_release',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 @unittest.skipUnless(CACHE,'Requires verified native IPK tool')
 def test_ipk_manifest_binds_actual_profile_build_manager_arch_size_and_hash(self):
  m=self.module()
  with tempfile.TemporaryDirectory()as td:
   root=Path(td);out=root/'out';out.mkdir();tool=builder.pinned_asset(builder.ASSETS['ipkg_build'],CACHE,True)
   def package(appbuild):
    stage=root/str(appbuild);profile={'platform':'openwrt','series':'24.10','arch':'arm_cortex-a9','format':'ipk','version':'1.3.2-72','application_build':appbuild}
    builder.write_files(stage,{'CONTROL/control':(b'Package: nfqws2-native\nVersion: 1.3.2-72\nArchitecture: arm_cortex-a9\nDescription: Native release fixture\n',0o644),'usr/share/nfqws2/platform.json':(json.dumps(profile).encode(),0o644),'usr/bin/fixture':(b'inert',0o755)})
    subprocess.run(['fakeroot','sh',str(tool),str(stage),str(out)],check=True,capture_output=True);return next(out.glob('*.ipk'))
   pkg=package(71)
   with self.assertRaisesRegex(ValueError,'identity'):m.manifest([pkg],72,'0.1.4','Native fixture')
   pkg=package(72);v=m.manifest([pkg],72,'0.1.4','Native fixture');self.assertEqual((v['platform'],v['package'],v['build']),('openwrt','nfqws2-native',72));p=v['packages'][0];self.assertEqual((p['series'],p['arch'],p['format'],p['version']),('24.10','arm_cortex-a9','ipk','1.3.2-72'));self.assertEqual(p['size'],pkg.stat().st_size);self.assertGreater(p['installed_size'],0)
   with self.assertRaisesRegex(ValueError,'duplicate'):m.manifest([pkg,pkg],72,'0.1.4','Native fixture')
 def test_envelope_accepts_only_the_exact_externally_signed_manifest(self):
  m=self.module()
  with tempfile.TemporaryDirectory()as td:
   root=Path(td);key=root/'private.pem';pub=root/'public.pem';subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,capture_output=True);key.chmod(0o600);subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(pub)],check=True,capture_output=True)
   raw=b'{"fixture":"exact bytes"}\n';signature=subprocess.run(['openssl','dgst','-sha256','-sign',str(key)],input=raw,capture_output=True,check=True).stdout
   value=m.envelope(raw,signature,pub);self.assertEqual(set(value),{'manifest','signature'})
   with self.assertRaisesRegex(ValueError,'signature'):m.envelope(raw+b' ',signature,pub)
 def test_default_publication_matrix_covers_both_series_and_all_ten_native_architectures(self):
  m=self.module();targets=m.targets();self.assertEqual(len(targets),20);self.assertEqual(len({arch for series,arch in targets}),10);self.assertIn(('24.10','arm_cortex-a9'),targets);self.assertIn(('25.12','x86_64'),targets)
 @unittest.skipUnless(CACHE and APK_TOOL,'Requires official native APK SDK')
 def test_apk_manifest_checks_signature_and_actual_installed_identity(self):
  m=self.module()
  with tempfile.TemporaryDirectory()as td:
   root=Path(td);out=root/'out';out.mkdir();key=root/'key.pem';pub=root/'pub.pem';subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(key)],check=True,capture_output=True);key.chmod(0o600);subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(pub)],check=True,capture_output=True)
   target=builder.native_metadata('25.12','x86_64',72);target['dependencies']=[];profile={k:target[k]for k in ['series','arch','format','version']}|{'platform':'openwrt','application_build':72};stage=root/'stage';builder.write_files(stage,{'usr/share/nfqws2/platform.json':(json.dumps(profile).encode(),0o644)})
   pkg=builder.build_apk(target,stage,{name:b'#!/bin/sh\nexit 0\n'for name in ['preinst','postinst','prerm','postrm']},CACHE,out,True,key)
   v=m.manifest([pkg],72,'0.1.4','APK fixture',APK_TOOL,pub);self.assertEqual(v['packages'][0]['format'],'apk')
   raw=bytearray(pkg.read_bytes());raw[30]^=1;pkg.write_bytes(raw)
   with self.assertRaises(ValueError):m.manifest([pkg],72,'0.1.4','APK fixture',APK_TOOL,pub)
if __name__=='__main__':unittest.main()
