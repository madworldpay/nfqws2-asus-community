"""Failure recovery is allowed only for exactly the original owned application files."""
import os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PHP=os.environ.get('PHP_TEST_BINARY')
@unittest.skipUnless(PHP,'Requires matching PHP runtime')
class NativePayloadFingerprint(unittest.TestCase):
 def test_content_modes_links_and_inventory_scope_control_recovery(self):
  with tempfile.TemporaryDirectory()as td:
   r=subprocess.run([PHP,'-n','-f',str(ROOT/'tests/test_openwrt_update_payload.php'),'--',td,str(os.getuid())],text=True,capture_output=True,timeout=10)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');self.assertIn('PASS:',r.stdout)
if __name__=='__main__':unittest.main()
