"""Keep cross-platform import and exported log destinations under regression coverage."""
import os,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.environ.get('PHP_TEST_BINARY'),'Requires matching PHP runtime')
class NativeImportRoundTrip(unittest.TestCase):
    def test_author_intent_resource_paths_and_redacted_output_logs(self):
        result=subprocess.run([os.environ['PHP_TEST_BINARY'],'-n','-f',str(ROOT/'tests/test_openwrt_import.php')],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stderr,'')
        self.assertIn('Portable native/Entware imports',result.stdout)
