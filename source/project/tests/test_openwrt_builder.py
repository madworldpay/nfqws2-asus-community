"""Native packaging has its own architecture, dependencies and upgrade contract."""
import importlib.util
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('openwrt_builder',ROOT/'openwrt/build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
ENGINE_DIR=os.environ.get('NFQWS_TEST_ENGINE_DIR')


class NativeBuilderTests(unittest.TestCase):
    def test_release_filenames_are_unique_across_series_and_architectures(self):
        names=[]
        for series in ['24.10','25.12']:
            for arch in ['arm_cortex-a9','x86_64']:
                m=builder.native_metadata(series,arch,72)
                name=builder.package_filename(m)
                self.assertEqual(name,f"nfqws2-native_{m['version']}_{arch}.{m['format']}")
                names.append(name)
        self.assertEqual(len(set(names)),4)

    def test_ipk_apk_metadata_is_native_and_does_not_change_entware(self):
        for series,fmt,version in [('24.10','ipk','1.3.2-1'),('25.12','apk','1.3.2-r1')]:
            with self.subTest(series=series):
                m=builder.native_metadata(series,'arm_cortex-a9')
                self.assertEqual((m['package'],m['format'],m['version'],m['arch']),('nfqws2-native',fmt,version,'arm_cortex-a9'))
                for dep in ['kmod-nft-queue','kmod-nfnetlink-queue','php8-cgi','flock','firewall4']:
                    self.assertIn(dep,m['dependencies'])
                self.assertFalse(any('/opt' in d or 'entware' in d for d in m['dependencies']))

    def test_architecture_series_and_release_cannot_inject_metadata(self):
        for args in [('24.10','all',1),('25.12','armv7-3.2',1),('24.10\n','arm_cortex-a9',1),('24.10','arm_cortex-a9',0),('24.10','arm_cortex-a9','1;reboot')]:
            with self.subTest(args=args),self.assertRaises(ValueError):builder.native_metadata(*args)

    def test_defaults_are_portable_and_discover_uplinks(self):
        config=builder.native_defaults().decode()
        self.assertIn('ISP_INTERFACE=""',config)
        self.assertIn('/etc/nfqws2/lua/zapret-lib.lua',config)
        self.assertIn('ASUS_CLIENT_MODE="all"',config)
        self.assertNotIn('/opt/',config)
        self.assertNotIn('POLICY_NAME=',config)

    def test_native_panel_uses_explicit_profile_and_native_dependencies(self):
        for dep in ['uhttpd','php8-mod-session','php8-mod-openssl','php8-mod-curl','ca-bundle']:
            self.assertIn(dep,builder.DEPENDENCIES)
        with tempfile.TemporaryDirectory()as td:
            dist=Path(td)
            (dist/'index.html').write_text('fixture')
            for source in (ROOT/'webui/web/public').glob('*.php'):(dist/source.name).write_bytes(source.read_bytes())
            files=builder.web_payload(dist)
            profile=json.loads(files['usr/share/nfqws2-web/platform-profile.json'][0])
            self.assertEqual(profile,{'schema_version':1,'platform':'openwrt'})
            self.assertIn('usr/lib/nfqws2-web/nfqws2-native-web',files.keys())
            self.assertIn('usr/lib/nfqws2-web/php-cgi.sh',files.keys())
            self.assertNotIn('etc/config/uhttpd',files)
            self.assertNotIn('etc/init.d/uhttpd',files)

    def test_native_package_refuses_stale_backend_even_when_all_filenames_exist(self):
        with tempfile.TemporaryDirectory()as td:
            dist=Path(td);(dist/'index.html').write_text('fixture')
            for source in (ROOT/'webui/web/public').glob('*.php'):(dist/source.name).write_bytes(source.read_bytes())
            (dist/'openwrt-package-quiesce.php').write_text('<?php /* older backend */')
            with self.assertRaises(RuntimeError):builder.web_payload(dist)

    def test_staging_never_inherits_group_writable_developer_directories(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td)/'payload';old=os.umask(0o002)
            try:builder.write_files(root,{'usr/lib/nfqws2/test':(b'data',0o644)})
            finally:os.umask(old)
            for p in [root,*root.rglob('*')]:
                self.assertEqual(stat.S_IMODE(p.stat().st_mode)&0o022,0,str(p))

    @unittest.skipUnless(ENGINE_DIR,'Requires verified upstream engine payloads')
    def test_native_baseline_pins_resources_and_installs_public_catalog_contract(self):
        target=builder.native_metadata('24.10','arm_cortex-a9')
        raw=(Path(ENGINE_DIR)/'nfqws2-armv7').read_bytes();lua=b'return 1\n'
        files=builder.payload_files(target,raw,{'opt/etc/nfqws2/lua/demo.lua.gz':gzip.compress(lua)})
        baseline=json.loads(files['usr/share/nfqws2/report-baseline.json'][0])
        self.assertEqual(baseline['resources']['lua/demo.lua'],{'bytes':len(lua),'sha256':hashlib.sha256(lua).hexdigest()})
        self.assertEqual(baseline['package_version'],target['version'])
        self.assertEqual(baseline['build_number'],int((ROOT/'BUILD_NUMBER').read_text()))
        self.assertEqual(baseline['resources']['lua/local-guarded-ts.lua']['sha256'],hashlib.sha256((ROOT/'asus/lua/local-guarded-ts.lua').read_bytes()).hexdigest())
        artifact=json.loads(files['usr/share/nfqws2/dpi-native-artifact.json'][0])
        self.assertEqual((artifact['arch'],artifact['engine']),('arm_cortex-a9','arm'))
        self.assertEqual(artifact['artifact']['sha256'],'c0e0045bab2ae654a9f0fef125602fc042b6f54705afdfa0d6bfc10557e74863')
        self.assertIn('usr/lib/nfqws2/dpi/paths.sh',files)
        for name,mode in [('quiesce.php',0o644),('quiesce.sh',0o755),('package-functions.sh',0o644)]:
            self.assertTrue('usr/lib/nfqws2/update/'+name in files,'Missing native controller payload: '+name)
            self.assertEqual(files['usr/lib/nfqws2/update/'+name][1],mode)
        functions=files['usr/lib/nfqws2/update/package-functions.sh'][0].decode()
        self.assertIn('nfqws_package_stop_services_internal()',functions)
        self.assertNotIn('case "$NFQWS_PKG_ACTION" in',functions)
        raw,mode=files['usr/share/nfqws2/optional/dpi-detector-armv5te']
        self.assertEqual((hashlib.sha256(raw).hexdigest(),mode),('c0e0045bab2ae654a9f0fef125602fc042b6f54705afdfa0d6bfc10557e74863',0o644))
        for name in ['strategy-v2.schema.json','profile-catalog.schema.json','profile-catalog-public.pem']:
            self.assertIn('usr/share/nfqws2/'+name,files.keys())
        self.assertEqual(files['usr/share/nfqws2/openwrt-package-manifest.schema.json'][0],(ROOT/'updates/openwrt-package-manifest.schema.json').read_bytes())
        self.assertEqual(files['usr/share/nfqws2/update-release-key.pem'][0],(ROOT/'updates/trusted-release-key.pem').read_bytes())

    @unittest.skipUnless(ENGINE_DIR,'Requires verified upstream engine payloads')
    def test_only_apk_packages_register_the_native_precommit_veto(self):
        engine=(Path(ENGINE_DIR)/'nfqws2-armv7').read_bytes()
        for series,expected in [('24.10',False),('25.12',True)]:
            files=builder.payload_files(builder.native_metadata(series,'arm_cortex-a9'),engine)
            hook='lib/apk/commit_hooks.d/10-nfqws2-native'
            self.assertEqual(hook in files,expected,'Wrong native commit hook registration for '+series)
            self.assertEqual('usr/lib/nfqws2/update/apk-precommit.php' in files,expected)
            if expected:
                self.assertEqual(files[hook],((ROOT/'openwrt/update/apk-precommit.sh').read_bytes(),0o755))

    @unittest.skipUnless(ENGINE_DIR,'Requires verified upstream engine payloads')
    def test_payload_only_contains_selected_static_engine_and_native_paths(self):
        raw=(Path(ENGINE_DIR)/'nfqws2-armv7').read_bytes()
        files=builder.payload_files(builder.native_metadata('24.10','arm_cortex-a9'),raw)
        self.assertEqual(files['usr/bin/nfqws2'],(raw,0o755))
        for name in ['usr/lib/nfqws2/control.sh','usr/lib/nfqws2/resource-upgrade.php','usr/lib/nfqws2/nfqws2-native','usr/share/nfqws2/defaults/nfqws2.conf','lib/upgrade/keep.d/nfqws2-native']:
            self.assertIn(name,files.keys())
        self.assertNotIn('etc/init.d/nfqws2-native',files)  # no default_postinst auto-start
        self.assertNotIn('etc/nfqws2/nfqws2.conf',files)  # never overwrite active files
        self.assertFalse(any(p.startswith('opt/')or p.endswith('.ko')or'/libc.so'in p for p in files))
        profile=json.loads(files['usr/share/nfqws2/platform.json'][0])
        self.assertEqual((profile['platform'],profile['arch']),('openwrt','arm_cortex-a9'))
        for mode in [value[1] for value in files.values()]:self.assertEqual(mode&0o022,0)

    @unittest.skipUnless(ENGINE_DIR,'Requires verified upstream engine payloads')
    def test_offline_install_preserves_config_and_readable_engine_resources(self):
        target=builder.native_metadata('24.10','arm_cortex-a9')
        files=builder.payload_files(target,(Path(ENGINE_DIR)/'nfqws2-armv7').read_bytes())
        files|=builder.smartdns_runtime_files()
        for name in ['lua/zapret-lib.lua','blobs/tls_clienthello.bin']:
            files['usr/share/nfqws2/defaults/'+name]=(b'test',0o644)
        with tempfile.TemporaryDirectory()as td:
            root=Path(td)/'root';builder.write_files(root,files)
            web=root/'usr/lib/nfqws2-web/nfqws2-native-web';web.parent.mkdir(parents=True);web.write_text('fixture')
            builder.write_files(root,{'usr/share/nfqws2/defaults/web-config':((ROOT/'openwrt/web-config').read_bytes(),0o600)})
            active=root/'etc/nfqws2/nfqws2.conf';active.parent.mkdir(parents=True);active.write_text('# preserve my config\n')
            custom=active.parent/'lua/manual.lua';custom.parent.mkdir(mode=0o755);custom.write_text('my Lua\n')
            hook=Path(td)/'postinst';hook.write_bytes(builder.package_hook(target,'postinstall'))
            subprocess.run(['fakeroot','sh',str(hook)],env={**os.environ,'IPKG_INSTROOT':str(root)},check=True,capture_output=True)
            self.assertEqual(active.read_text(),'# preserve my config\n')
            self.assertEqual(custom.read_text(),'my Lua\n')
            self.assertEqual((custom.parent/'local-guarded-ts.lua').read_bytes(),(ROOT/'asus/lua/local-guarded-ts.lua').read_bytes())
            self.assertEqual(os.readlink(root/'etc/init.d/nfqws2-native'),'/usr/lib/nfqws2/nfqws2-native')
            for name in ['lists','lua','blobs']:
                self.assertEqual(stat.S_IMODE((root/'etc/nfqws2'/name).stat().st_mode),0o755)
            self.assertEqual(stat.S_IMODE((root/'etc/nfqws2/lists/user.list').stat().st_mode),0o644)
            self.assertEqual(stat.S_IMODE(active.stat().st_mode),0o600)
            self.assertEqual(os.readlink(root/'etc/init.d/nfqws2-native-web'),'/usr/lib/nfqws2-web/nfqws2-native-web')
            self.assertEqual(os.readlink(root/'etc/init.d/nfqws2-native-dns'),'/usr/lib/nfqws2/smartdns/nfqws2-native-dns')
            self.assertEqual(os.readlink(root/'etc/init.d/nfqws2-native-dns-resume'),'/usr/lib/nfqws2/smartdns/nfqws2-native-dns-resume')
            auth=json.loads((root/'etc/nfqws2-web/auth.json').read_text())
            self.assertEqual(auth,{'mode':'system','username':'root','password_hash':''})
            self.assertEqual(stat.S_IMODE((root/'etc/nfqws2-web/auth.json').stat().st_mode),0o600)
            self.assertIn("option network 'lan'",(root/'etc/config/nfqws2-web').read_text())


if __name__=='__main__':unittest.main()
