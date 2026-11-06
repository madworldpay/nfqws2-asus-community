"""Both package families ship the exact shared service-check controller."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SiteCheckPackagingTests(unittest.TestCase):
    def test_shared_backend_reaches_both_payloads(self):
        public = ROOT / 'webui/web/public'
        source = public / 'dpi-site-check.php'
        self.assertTrue(source.is_file(), 'service-check backend is missing')
        with tempfile.TemporaryDirectory() as folder:
            dist = Path(folder)
            (dist / 'index.html').write_text('fixture')
            for p in public.glob('*.php'):
                (dist / p.name).write_bytes(p.read_bytes())
            for family, prefix in [
                ('asus', 'opt/share/nfqws-asus-web/'),
                ('openwrt', 'usr/share/nfqws2-web/'),
            ]:
                with self.subTest(family=family):
                    spec = importlib.util.spec_from_file_location(
                        'site_check_' + family, ROOT / family / 'build.py')
                    builder = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(builder)
                    payload = builder.web_payload(dist)
                    self.assertEqual(payload[prefix + source.name],
                                     (source.read_bytes(), 0o644))


if __name__ == '__main__':
    unittest.main()
