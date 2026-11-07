"""A beta package must contain the whole profile runtime or fail before writing."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class Packaging(unittest.TestCase):
    def module(self):
        path = HERE / 'package_payload.py'
        self.assertTrue(path.is_file(), 'combined package profile integration is missing')
        spec = importlib.util.spec_from_file_location('profile_package_payload', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fixture(self, platform):
        if platform == 'asus-entware':
            files = {
                'opt/etc/init.d/S51nfqws2': (ROOT / 'asus/S51nfqws2', 0o755),
                'opt/lib/nfqws2-asus/platform.sh': (ROOT / 'asus/platform.sh', 0o644),
                'opt/lib/nfqws2-asus/lifecycle.sh': (ROOT / 'asus/lifecycle.sh', 0o644),
                'opt/share/nfqws-asus-web/index.php': (ROOT / 'webui/web/public/index.php', 0o644),
                'opt/etc/nfqws2/nfqws2.conf.notactive': (ROOT / 'core/etc/nfqws2/nfqws2.conf', 0o600),
            }
        else:
            files = {
                'usr/lib/nfqws2/nfqws2-native': (ROOT / 'openwrt/nfqws2.init', 0o755),
                'usr/lib/nfqws2/control.sh': (ROOT / 'openwrt/control.sh', 0o755),
                'usr/lib/nfqws2/firewall.sh': (ROOT / 'openwrt/firewall.sh', 0o644),
                'usr/lib/nfqws2/config.php': (ROOT / 'openwrt/config.php', 0o644),
                'usr/share/nfqws2-web/index.php': (ROOT / 'webui/web/public/index.php', 0o644),
                'usr/share/nfqws2/defaults/nfqws2.conf': (ROOT / 'core/etc/nfqws2/nfqws2.conf', 0o600),
            }
        return {name: (source.read_bytes(), mode) for name, (source, mode) in files.items()}

    def test_both_payloads_ship_complete_runtime_and_exact_hook_manifests(self):
        for platform, web, library, hooks, helper in [
            ('asus-entware', 'opt/share/nfqws-asus-web', 'opt/lib/nfqws2-asus',
             ['opt/etc/init.d/S51nfqws2', 'opt/lib/nfqws2-asus/platform.sh',
              'opt/lib/nfqws2-asus/lifecycle.sh', 'opt/share/nfqws-asus-web/index.php'], 'entware'),
            ('openwrt', 'usr/share/nfqws2-web', 'usr/lib/nfqws2',
             ['usr/lib/nfqws2/nfqws2-native', 'usr/lib/nfqws2/control.sh',
              'usr/lib/nfqws2/firewall.sh', 'usr/share/nfqws2-web/index.php'], 'native'),
        ]:
            with self.subTest(platform=platform):
                before = self.fixture(platform)
                payload = self.module().integrate(before, platform)
                manifest, mode = payload[web + '/device-profiles-build.json']
                manifest = json.loads(manifest)
                self.assertEqual(mode, 0o644)
                self.assertEqual(set(manifest), {'schema_version', 'files'})
                self.assertEqual(manifest['schema_version'], 1)
                self.assertEqual(set(manifest['files']), {'/' + path for path in hooks})
                for path in hooks:
                    self.assertNotEqual(before[path][0], payload[path][0])
                    self.assertEqual(payload[path][1], before[path][1])
                    self.assertEqual(manifest['files']['/' + path], hashlib.sha256(payload[path][0]).hexdigest())
                for name in ['lab', 'library', 'paths', 'plan', 'queues', 'runtime', 'transaction']:
                    self.assertEqual(payload[web + '/device-profiles-' + name + '.php'],
                                     ((HERE / ('device-profiles-' + name + '.php')).read_bytes(), 0o644))
                for source, destination in [('device-profiles-lab.html', 'device-profiles-lab.html'),
                                            ('device-profiles-lab.css', 'device-profiles-lab.css'),
                                            ('device-profiles-lab.js', 'device-profiles-lab.js')]:
                    self.assertEqual(payload[web + '/device-profiles-lab/' + destination],
                                     ((HERE / source).read_bytes(), 0o644))
                self.assertEqual(payload[library + '/device-profiles-' + helper + '.sh'],
                                 ((HERE / ('device-profiles-' + helper + '.sh')).read_bytes(), 0o755))
                self.assertFalse(any('test_' in path or '__pycache__' in path for path in payload))
                self.assertEqual(before, self.fixture(platform), 'integration mutated its source payload')
                for path in hooks[:-1]:
                    result = subprocess.run(['/bin/sh', '-n'], input=payload[path][0], capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_main_panel_link_points_to_an_installed_page(self):
        import re
        text=(ROOT/'webui/web/src/components/MainTabs.tsx').read_text()
        href=re.search(r"const deviceProfilesHref = '([^']+)'",text).group(1)
        for platform,web in [('asus-entware','opt/share/nfqws-asus-web'),('openwrt','usr/share/nfqws2-web')]:
            payload=self.module().integrate(self.fixture(platform),platform)
            self.assertIn(web+href,payload)
            self.assertIn(b'<!doctype html>',payload[web+href][0])

    def test_stock_template_is_a_copy_of_package_default_without_an_active_config(self):
        module = self.module()
        asus = self.fixture('asus-entware')
        template = (b'# package target default\n', 0o600)
        asus['opt/etc/nfqws2/nfqws2.conf.notactive'] = template
        payload = module.integrate(asus, 'asus-entware')
        self.assertEqual(payload['opt/share/nfqws2-asus/defaults/nfqws2.conf'], template)
        self.assertEqual(payload['opt/lib/nfqws2-asus/config.php'], ((ROOT / 'openwrt/config.php').read_bytes(), 0o644))
        self.assertNotIn('opt/etc/nfqws2/nfqws2.conf', payload)
        native = module.integrate(self.fixture('openwrt'), 'openwrt')
        self.assertNotIn('etc/nfqws2/nfqws2.conf', native)
        self.assertNotIn('etc/init.d/nfqws2-native', native)

    def test_asus_shared_parser_has_its_standalone_dependency(self):
        php = os.environ.get('PHP_TEST_BINARY')
        if not php:
            self.skipTest('PHP interpreter not selected')
        payload = self.module().integrate(self.fixture('asus-entware'), 'asus-entware')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prefix = 'opt/lib/nfqws2-asus/'
            for path, (raw, _) in payload.items():
                if path.startswith(prefix) and path.endswith('.php'):
                    (root / Path(path).name).write_bytes(raw)
            result = subprocess.run([php, '-n', '-r',
                                     'require $argv[1]; echo NfqwsNativeConfig::parse(\'TCP_PORTS="443"\')["TCP_PORTS"];',
                                     str(root / 'config.php')], capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout, '443')
            self.assertEqual(result.stderr, '')

    def test_missing_hook_or_stock_payload_fails_without_partial_mutation(self):
        module = self.module()
        for platform in ['asus-entware', 'openwrt']:
            fixture = self.fixture(platform)
            for missing in fixture:
                with self.subTest(platform=platform, missing=missing):
                    payload = {path: value for path, value in fixture.items() if path != missing}
                    before = payload.copy()
                    with self.assertRaises(ValueError):
                        module.integrate(payload, platform)
                    self.assertEqual(payload, before)

    def test_unrecognised_hook_and_double_integration_are_rejected(self):
        module = self.module()
        for platform in ['asus-entware', 'openwrt']:
            payload = self.fixture(platform)
            init = 'opt/etc/init.d/S51nfqws2' if platform == 'asus-entware' else 'usr/lib/nfqws2/nfqws2-native'
            broken = payload | {init: (b'#!/bin/sh\nexit 0\n', 0o755)}
            with self.subTest(platform=platform), self.assertRaises(ValueError):
                module.integrate(broken, platform)
            integrated = module.integrate(payload, platform)
            with self.assertRaises(ValueError):
                module.integrate(integrated, platform)

    def test_active_user_config_cannot_become_package_payload(self):
        module = self.module()
        for platform, active in [('asus-entware', 'opt/etc/nfqws2/nfqws2.conf'),
                                 ('openwrt', 'etc/nfqws2/nfqws2.conf')]:
            with self.subTest(platform=platform), self.assertRaisesRegex(ValueError, 'active_config'):
                module.integrate(self.fixture(platform) | {active: (b'owner settings', 0o600)}, platform)

    def test_incomplete_runtime_source_cannot_produce_a_half_package(self):
        for missing in ['device-profiles-runtime.php', 'device-profiles-native.sh', 'device-profiles-lab.css']:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as folder:
                assets = Path(folder)
                for path in HERE.iterdir():
                    if path.is_file() and (path.name.startswith('device-profiles-') or
                                           path.name in ['native_overlay.py', 'entware_overlay.py', 'dispatcher-hook.php.inc']):
                        shutil.copyfile(path, assets / path.name)
                (assets / missing).unlink()
                module = self.module()
                module.HERE = assets
                with self.assertRaisesRegex(ValueError, 'incomplete_device_profiles_source'):
                    module.integrate(self.fixture('openwrt'), 'openwrt')

    def test_packaged_native_helper_can_be_sourced_again_during_its_cli_operation(self):
        payload = self.module().integrate(self.fixture('openwrt'), 'openwrt')
        raw = payload['usr/lib/nfqws2/device-profiles-native.sh'][0]
        with tempfile.TemporaryDirectory() as folder:
            entry = Path(folder) / 'device-profiles-native.sh'
            entry.write_bytes(raw.replace(b'/usr/lib/nfqws2/device-profiles-native.sh', str(entry).encode()))
            result = subprocess.run(['/bin/sh', '-c',
                                     'NFQWS_LAB_EXECUTING=1; . "$0"; '
                                     'command -v nfqws_lab_preflight >/dev/null && printf hooks_loaded',
                                     str(entry)], capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'hooks_loaded')
            self.assertEqual(result.stderr, '')

    def test_unsupported_platform_cannot_mix_payload_families(self):
        with self.assertRaises(ValueError):
            self.module().integrate(self.fixture('openwrt'), 'unknown')


if __name__ == '__main__':
    unittest.main()
