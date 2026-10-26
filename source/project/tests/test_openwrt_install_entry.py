"""The native command carries trusted code and rejects input before mutations."""
import importlib.util,os,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class BootstrapEntry(unittest.TestCase):
 def test_standalone_native_entry_is_embedded_deterministically_in_common_installer(self):
  spec=importlib.util.spec_from_file_location('native_bundle',ROOT/'openwrt/install-bundle.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  self.assertTrue(hasattr(m,'shell'),'Native installer needs an actual executable shell branch, not verifier helpers only')
  shell=m.shell();self.assertEqual(shell,m.shell());p=subprocess.run(['sh','-n'],input=shell,text=True,capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
  self.assertIn('NFQWS_NATIVE_BUNDLE',shell);self.assertIn('nfqws_native_main()',shell)
  installer=(ROOT.parents[1]/'install.sh').read_text();self.assertIn(shell,installer);self.assertIn('if [ -f /etc/openwrt_release ]',installer)
 def test_generated_command_rejects_unknown_mode_before_fetch_or_package_actions(self):
  c=os.environ.get('NFQWS_TEST_DOCKER');self.assertTrue(c,'Use real OpenWrt ash')
  spec=importlib.util.spec_from_file_location('native_bundle',ROOT/'openwrt/install-bundle.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  self.assertTrue(hasattr(m,'shell'),'Executable native shell branch is missing')
  p=subprocess.run(['docker','exec','-i',c,'sh'],input=m.shell()+'\nnfqws_native_main --unknown\n',text=True,capture_output=True,timeout=10)
  self.assertNotEqual(p.returncode,0);self.assertIn('параметр',p.stderr.lower())
if __name__=='__main__':unittest.main()
