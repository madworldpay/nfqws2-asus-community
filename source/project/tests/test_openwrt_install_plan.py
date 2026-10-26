"""The bootstrap cannot call an unfinished package current or guess an installed identity."""
import os,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.environ.get('PHP_TEST_BINARY'),'Requires matching PHP with OpenSSL')
class NativeInstallPlan(unittest.TestCase):
 def test_verified_native_first_install_updates_and_known_recovery_actions(self):
  r=subprocess.run([os.environ['PHP_TEST_BINARY'],'-n','-f',str(ROOT/'tests/test_openwrt_install_plan.php')],text=True,capture_output=True,timeout=15)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');self.assertIn('PASS:',r.stdout)
if __name__=='__main__':unittest.main()
