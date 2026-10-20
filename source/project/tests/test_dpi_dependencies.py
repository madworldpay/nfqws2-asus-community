import json,os,unittest
from pathlib import Path
from test_packages import read_ipk,ROOT

class DpiPackageTests(unittest.TestCase):
    def test_optional_component_has_complete_private_runtime_and_pinned_public_data(self):
        paths=list(Path(os.environ.get('PACKAGES_DIR',ROOT/'dist')).glob('*.ipk'));self.assertEqual(len(paths),2)
        for path in paths:
            data=read_ipk(path)['data']
            for name in ['guard.sh','probe.sh','drop.sh','stop.sh','worker.php','cli.php']:
                key='opt/lib/nfqws2-asus/dpi/'+name;self.assertIn(key,list(data));self.assertEqual(data[key][1],(ROOT/'asus/dpi'/name).read_bytes());self.assertEqual(data[key][0].uid,0)
                self.assertNotIn('opt/share/nfqws-asus-web/'+name,data)
            for name in ['dpi-catalog.json','dpi-profile.json','dpi-native-defaults.json','dpi-analysis-v2.schema.json','dpi-report.schema.json','dpi-envelope.schema.json','report.schema.json']:
                self.assertEqual(data['opt/share/nfqws2-asus/'+name][1],(ROOT/'support'/name).read_bytes())
            self.assertEqual(data['opt/bin/nfqws2-dpi'][1],(ROOT/'asus/dpi/cli.sh').read_bytes())
            self.assertIn('opt/share/licenses/nfqws2-asus/dpi-detector-MIT.txt',list(data))
            self.assertIn('opt/share/doc/nfqws2-asus/USAGE.md',list(data))
            self.assertFalse(any('dpi-detector-linux-' in name for name in data),'optional upstream binary must not install implicitly')
            self.assertFalse(any('dpi' in name and '/init.d/' in name for name in data))
