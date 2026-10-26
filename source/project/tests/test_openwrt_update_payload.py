"""Failure recovery is allowed only for exactly the original owned application files."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PHP=os.environ.get('PHP_TEST_BINARY')
@unittest.skipUnless(PHP,'Requires matching PHP runtime')
class NativePayloadFingerprint(unittest.TestCase):
 def test_content_modes_links_and_inventory_scope_control_recovery(self):
  with tempfile.TemporaryDirectory()as td:
   r=subprocess.run([PHP,'-n','-f',str(ROOT/'tests/test_openwrt_update_payload.php'),'--',td,str(os.getuid())],text=True,capture_output=True,timeout=10)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');self.assertIn('PASS:',r.stdout)
 @unittest.skipUnless(os.environ.get('NFQWS_TEST_ENGINE_DIR')and os.environ.get('NFQWS_TEST_SMARTDNS_CACHE'),'Requires verified complete native core payload')
 def test_every_file_in_real_native_core_packages_can_be_fingerprinted(self):
  from test_openwrt_builder import builder
  source=builder.source_payload(os.environ['NFQWS_TEST_SMARTDNS_CACHE'],True)
  engine=(Path(os.environ['NFQWS_TEST_ENGINE_DIR'])/'nfqws2-armv7').read_bytes()
  for series in ['24.10','25.12']:
   with self.subTest(series=series),tempfile.TemporaryDirectory()as td:
    files=builder.payload_files(builder.native_metadata(series,'arm_cortex-a9',72),engine,source);builder.write_files(Path(td),files)
    code='require $argv[1];$v=NfqwsOpenWrtUpdatePayload::fromPaths(json_decode(stream_get_contents(STDIN),true),$argv[2],(int)$argv[3]);if(!NfqwsOpenWrtUpdatePayload::unchanged($v,$argv[2],(int)$argv[3]))throw new RuntimeException("full native payload mismatch");echo "PASS";'
    r=subprocess.run([PHP,'-n','-r',code,str(ROOT/'webui/web/public/openwrt-update-payload.php'),td,str(os.getuid())],input=json.dumps(['/'+p for p in files]),capture_output=True,text=True,timeout=15)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stdout,'PASS')
if __name__=='__main__':unittest.main()
