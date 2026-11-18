"""Use real copied public assets; generated chunks are inert fixture bytes."""
import importlib.util
from pathlib import Path
import shutil,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'webui/web/public'
def builder(family):
 spec=importlib.util.spec_from_file_location('fresh_'+family,ROOT/family/'build.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class FrontendFreshnessTests(unittest.TestCase):
 def frontend(self,root):
  dist=root/'dist';shutil.copytree(PUBLIC,dist,ignore=shutil.ignore_patterns('mockServiceWorker.js'))
  (dist/'index.html').write_text('<html>compiled entry</html>');(dist/'assets').mkdir(exist_ok=True)
  (dist/'assets/index.compiled.js').write_text('// compiled fixture');(dist/'assets/index.compiled.js.map').write_text('not packaged')
  return dist
 def test_current_public_and_generated_chunks_are_packaged_byte_exactly_in_both_families(self):
  for family,prefix in [('asus','opt/share/nfqws-asus-web/'),('openwrt','usr/share/nfqws2-web/')]:
   with self.subTest(family=family),tempfile.TemporaryDirectory()as tmp:
    d=self.frontend(Path(tmp));v=builder(family).web_payload(d)
    for asset in ['strategy-picker/picker.js','strategy-picker/picker.css','strategy-picker/index.html','strategy-picker/metrics.js','models.woff2']:
     self.assertEqual(v[prefix+asset],((PUBLIC/asset).read_bytes(),0o644))
    self.assertEqual(v[prefix+'assets/index.compiled.js'],(b'// compiled fixture',0o644));self.assertNotIn(prefix+'assets/index.compiled.js.map',v)
 def test_missing_or_stale_nested_js_css_html_is_rejected_before_packaging(self):
  for family in ['asus','openwrt']:
   for asset in ['strategy-picker/picker.js','strategy-picker/picker.css','strategy-picker/index.html']:
    for operation in ['stale','missing']:
     with self.subTest(family=family,asset=asset,operation=operation),tempfile.TemporaryDirectory()as tmp:
      d=self.frontend(Path(tmp));target=d/asset
      if operation=='stale':target.write_bytes(b'previous build')
      else:target.unlink()
      with self.assertRaisesRegex(RuntimeError,'stale|Rebuild'):builder(family).web_payload(d)
 def test_previous_removed_module_or_unexpected_page_cannot_survive_in_dist(self):
  for family in ['asus','openwrt']:
   for asset in ['old-controller.php','strategy-picker/removed.html','removed-picker.js','assets/removed-controller.php']:
    with self.subTest(family=family,asset=asset),tempfile.TemporaryDirectory()as tmp:
     d=self.frontend(Path(tmp));(d/asset).write_bytes(b'old module')
     with self.assertRaisesRegex(RuntimeError,'stale|Rebuild'):builder(family).web_payload(d)
 def test_symlink_and_mock_service_worker_are_never_packaged(self):
  for family in ['asus','openwrt']:
   for operation in ['file-link','directory-link','mock']:
    with self.subTest(family=family,operation=operation),tempfile.TemporaryDirectory()as tmp:
     root=Path(tmp);d=self.frontend(root)
     if operation=='mock':(d/'mockServiceWorker.js').write_bytes(b'mock')
     elif operation=='file-link':
      (d/'strategy-picker/picker.js').unlink();(d/'strategy-picker/picker.js').symlink_to(PUBLIC/'strategy-picker/picker.js')
     else:
      shutil.rmtree(d/'strategy-picker');(d/'strategy-picker').symlink_to(PUBLIC/'strategy-picker',target_is_directory=True)
     with self.assertRaisesRegex(RuntimeError,'stale|Rebuild'):builder(family).web_payload(d)
