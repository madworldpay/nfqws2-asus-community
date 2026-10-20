"""Fresh-host installation must not start a packaged port-80 default site."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('install_nginx',ROOT/'support-relay/deploy/install-nginx.py')
installer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class FreshInstallTests(unittest.TestCase):
    def test_package_autostart_is_blocked_until_only_tls_site_is_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); site=root/'site'; site.write_text('server {\n    listen 443 ssl;\n}')
            calls=[]
            def run(args,**kwargs):
                calls.append(args)
                if args[0]=='dpkg-query': return subprocess.CompletedProcess(args,1,'','')
                if args[0]=='apt-get':
                    policy=root/'usr/sbin/policy-rc.d'
                    self.assertEqual((root/'etc/systemd/system/nginx.service').readlink(),Path('/dev/null'))
                    self.assertEqual(subprocess.run([str(policy)]).returncode,101)
                    available=root/'etc/nginx/sites-available'; available.mkdir(parents=True)
                    enabled=root/'etc/nginx/sites-enabled'; enabled.mkdir()
                    (available/'default').write_text('server { listen 80; }')
                    (enabled/'default').symlink_to('../sites-available/default')
                if args[0]=='nginx':
                    self.assertFalse((root/'etc/nginx/sites-enabled/default').exists())
                    self.assertEqual((root/'etc/nginx/sites-enabled/nfqws-support.conf').read_text(),site.read_text())
                    return subprocess.CompletedProcess(args,0,site.read_text(),'')
                if args[:2]==['systemctl','enable']:
                    self.assertIn(['nginx','-t'],calls)
                    self.assertIn(['nginx','-T'],calls)
                return subprocess.CompletedProcess(args,0,'','')
            installer.install(site,root,run)
            self.assertEqual(calls[-1],['systemctl','enable','--now','nginx'])
            self.assertFalse((root/'usr/sbin/policy-rc.d').exists())
            self.assertEqual((root/'etc/nginx/sites-available/default').read_text(),'server { listen 80; }')

    def test_existing_operator_config_or_policy_is_preserved_without_install(self):
        for name in ('etc/nginx/operator.conf','usr/sbin/policy-rc.d'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); existing=root/name; existing.parent.mkdir(parents=True); existing.write_bytes(b'operator state')
                site=root/'site'; site.write_text('server {\n    listen 443 ssl;\n}')
                calls=[]
                def run(args,**kwargs):
                    calls.append(args); return subprocess.CompletedProcess(args,1,'','')
                with self.assertRaises(installer.InstallError): installer.install(site,root,run)
                self.assertEqual(existing.read_bytes(),b'operator state')
                self.assertFalse(any(c[0] in ('apt-get','systemctl') for c in calls))

    def test_failed_validation_never_starts_and_removes_own_temporary_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); site=root/'site'; site.write_text('server {\n    listen 80;\n}'); calls=[]
            def run(args,**kwargs):
                calls.append(args)
                if args[0]=='dpkg-query': return subprocess.CompletedProcess(args,1,'','')
                if args[0]=='apt-get': (root/'etc/nginx/sites-enabled').mkdir(parents=True)
                return subprocess.CompletedProcess(args,0,site.read_text(),'')
            with self.assertRaises(installer.InstallError): installer.install(site,root,run)
            self.assertFalse(any(c[:2]==['systemctl','enable'] for c in calls))
            self.assertEqual((root/'etc/systemd/system/nginx.service').readlink(),Path('/dev/null'))
            self.assertFalse((root/'usr/sbin/policy-rc.d').exists())
