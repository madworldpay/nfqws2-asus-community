"""Inspect the actual installable artifacts, including their maintainer scripts."""
import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read_ipk(path):
    result = {}
    with tarfile.open(path) as outer:
        for section in ['control', 'data']:
            with tarfile.open(fileobj=io.BytesIO(outer.extractfile(section+'.tar.gz').read())) as inner:
                result[section] = {m.name.removeprefix('./'): (m, inner.extractfile(m).read())
                                   for m in inner if m.isfile()}
    return result


class PackageTests(unittest.TestCase):
    def test_full_component_notices_and_adaptation_license_are_installed_once(self):
        for package in self.packages().values():
            data = package['data']
            for name in ['LICENSE', 'THIRD-PARTY-NOTICES.txt']:
                path = 'opt/share/licenses/nfqws2-asus/' + name
                self.assertIn(path, data)
                self.assertEqual(data[path][1], (ROOT/name).read_bytes())
                self.assertEqual(data[path][0].mode, 0o644)
            copies = [name for name in data if name.endswith('/THIRD-PARTY-NOTICES.txt')]
            self.assertEqual(copies, ['opt/share/licenses/nfqws2-asus/THIRD-PARTY-NOTICES.txt'])
            control = package['control']['control'][1].decode()
            self.assertNotRegex(control, r'GT-BE19000(?!AI)')
            self.assertIn('ASUS routers', control)
            self.assertIn('LGPL-2.1', control)

    def test_import_guide_is_installed_with_exact_source(self):
        for package in self.packages().values():
            path='opt/share/doc/nfqws2-asus/IMPORT.md'
            self.assertIn(path,package['data'])
            self.assertEqual(package['data'][path][1],(ROOT/'docs/IMPORT.md').read_bytes())

    def test_unified_share_files_and_schemas_match_current_sources(self):
        for package in self.packages().values():
            data=package['data']
            for name in ['import-api.php','import-config.php','import-document.php','import-plan.php','import-store.php','import-transaction.php','index.php','smartdns-store.php','smartdns-config-api.php','ark.php','share-api.php','share-bundle.php','share-source.php','share-strategy.php',
                         'share-location-worker.php','dpi-saved-store.php','dpi-saved-projector.php','support-report-dns.php','router-wan.php',
                         'share-read.php','share-resources.php','share-dependencies.php','share-dns.php',
                         'share-contributions.php','share-v4.php','share-bundle-v4.php','support-json-schema.php']:
                path='opt/share/nfqws-asus-web/'+name
                self.assertIn(path,list(data))
                self.assertEqual(data[path][1],(ROOT/'webui/web/public'/name).read_bytes())
            for name in ['dpi-saved.schema.json','strategy.schema.json','share-envelope.schema.json','report.schema.json',
                         'strategy-v2.schema.json','resources.schema.json','dns-share.schema.json','share-v4.schema.json']:
                path='opt/share/nfqws2-asus/'+name
                self.assertIn(path,list(data))
                self.assertEqual(data[path][1],(ROOT/'support'/name).read_bytes())
            baseline=json.loads(data['opt/share/nfqws2-asus/report-baseline.json'][1])
            self.assertEqual(baseline['web_version'],(ROOT/'webui/VERSION').read_text().strip())
            self.assertEqual(data['opt/bin/nfqws2-dpi'][1],(ROOT/'asus/dpi/cli.sh').read_bytes())
            self.assertNotIn('opt/etc/nfqws-asus-web/share-identity/id',data)
            name='aarch64' if 'aarch64-3.10' in package['control']['control'][1].decode() else 'armv7'
            meta=json.loads((ROOT/'asus/share/bin/launchers.json').read_text())
            self.assertEqual(meta['source_sha256'],hashlib.sha256((ROOT/'asus/share/location-launch.c').read_bytes()).hexdigest())
            guard=data['opt/libexec/nfqws2-asus/location-launch'][1]
            self.assertEqual(hashlib.sha256(guard).hexdigest(),meta['outputs'][name]['sha256'])

    def test_update_launcher_is_static_matching_abi_and_bound_to_source(self):
        meta=json.loads((ROOT/'asus/update/bin/launchers.json').read_text())
        self.assertEqual(meta['source_sha256'],hashlib.sha256((ROOT/'asus/update/opkg-launch.c').read_bytes()).hexdigest())
        for family,package in self.packages().items():
            data=package['data'];path='opt/libexec/nfqws2-asus/update-launch'
            self.assertIn(path,list(data));actual=data[path][1];key='aarch64' if family=='aarch64-3.10' else 'armv7'
            self.assertEqual(hashlib.sha256(actual).hexdigest(),meta['outputs'][key]['sha256'])
            self.assertEqual(actual,(ROOT/f'asus/update/bin/{key}-opkg-launch').read_bytes())
            self.assertEqual(data[path][0].mode,0o755);self.assertEqual(actual[:4],b'\x7fELF')
            self.assertEqual(int.from_bytes(actual[18:20],'little'),183 if key=='aarch64' else 40)

    def test_package_update_trust_material_is_public_and_matches_source(self):
        for package in self.packages().values():
            data = package['data']
            for source, path in [
                ('updates/package-manifest.schema.json', 'opt/share/nfqws2-asus/package-manifest.schema.json'),
                ('updates/trusted-release-key.pem', 'opt/share/nfqws2-asus/update-release-key.pem'),
                ('webui/web/public/update-manifest.php', 'opt/share/nfqws-asus-web/update-manifest.php'),
            ]:
                self.assertIn(path, list(data))
                self.assertEqual(data[path][1], (ROOT/source).read_bytes())
                self.assertEqual(data[path][0].mode, 0o644)
            key = data['opt/share/nfqws2-asus/update-release-key.pem'][1]
            self.assertTrue(key.startswith(b'-----BEGIN PUBLIC KEY-----'))
            self.assertNotIn(b'PRIVATE KEY', key)

    def test_diagnostic_manifest_matches_actual_engine_and_strategy_payload(self):
        for package in self.packages().values():
            data = package['data']
            manifest_path = 'opt/share/nfqws2-asus/report-baseline.json'
            self.assertIn(manifest_path, list(data))
            manifest = json.loads(data[manifest_path][1])
            self.assertEqual(manifest['schema_version'], 1)
            self.assertEqual(manifest['engine']['sha256'], hashlib.sha256(data['opt/usr/bin/nfqws2'][1]).hexdigest())
            for name, meta in manifest['resources'].items():
                kind, name = name.split('/', 1)
                path = 'opt/etc/nfqws2/' + ('blobs' if kind == 'blob' else 'lua') + '/' + name
                actual = data[path][1]
                self.assertEqual(meta['bytes'], len(actual))
                self.assertEqual(meta['sha256'], hashlib.sha256(actual).hexdigest())
            for name in ['support-report.php','support-report-io.php','support-report-values.php',
                         'support-report-platform.php','support-report-network.php']:
                self.assertIn('opt/share/nfqws-asus-web/' + name, list(data))
                self.assertEqual(data['opt/share/nfqws-asus-web/' + name][1],
                                 (ROOT/'webui/web/public'/name).read_bytes(),
                                 name+' must be rebuilt from current public source')

    def test_smartdns_wizard_payload_and_static_recovery_helpers(self):
        for family,package in self.packages().items():
            data=package['data'];key='aarch64' if family=='aarch64-3.10' else 'armv7';prefix='opt/lib/nfqws2-asus/smartdns/'
            for name in ['config-worker.sh','config-worker.php','native-state.sh','native-common.sh','primary-dns.sh','recovery.sh','lifecycle.sh','runtime.sh','control.sh','control.php','forwarding.awk','hook-edit.awk']:
                self.assertIn(prefix+name,list(data));self.assertEqual(data[prefix+name][1],(ROOT/'asus/smartdns'/name).read_bytes())
            tools=json.loads(data[prefix+'tools.json'][1])
            for stem,meta_name in [('dns-probe','probes.json'),('session-owner','owners.json')]:
                blob=data[prefix+stem][1];meta=json.loads((ROOT/'asus/smartdns/bin'/meta_name).read_text())
                self.assertEqual(meta['source_sha256'],hashlib.sha256((ROOT/'asus/smartdns'/(stem+'.c')).read_bytes()).hexdigest())
                self.assertEqual(hashlib.sha256(blob).hexdigest(),meta['outputs'][key]['sha256']);self.assertEqual(hashlib.sha256(blob).hexdigest(),tools[stem.replace('-','_')+'_sha256'])
                self.assertEqual(blob[:4],b'\x7fELF');self.assertEqual(data[prefix+stem][0].mode,0o755)
            for name in ['smartdns-config-api.php','smartdns-config-jobs.php','smartdns-report.php','smartdns-lifecycle.php','router-checkup.php','smartdns-profile.php','smartdns-store.php','smartdns-probe.php','smartdns-candidate.php','smartdns-baseline.php','smartdns-native.php','smartdns-validation.php']:
                self.assertEqual(data['opt/share/nfqws-asus-web/'+name][1],(ROOT/'webui/web/public'/name).read_bytes())
            self.assertIn('opt/bin/nfqws2-smartdns-control',list(data));self.assertIn('opt/etc/init.d/S80nfqws2-smartdns',list(data))
            for path in data:
                self.assertFalse(path.startswith('jffs/'));self.assertNotIn('resume-intent.json',path);self.assertNotIn('/smartdns/jobs/',path)

    def packages(self):
        files = sorted(Path(os.environ.get('PACKAGES_DIR', ROOT/'dist')).glob('*.ipk'))
        self.assertEqual(len(files), 2, 'Build both IPKs first: python3 asus/build.py')
        self.assertTrue(all(p.name.startswith('nfqws2-asus_') for p in files), 'each architecture must include core and web')
        return {p.name.rsplit('_',1)[1].removesuffix('.ipk'): read_ipk(p) for p in files}

    def test_cloud_catalog_and_both_languages_are_in_both_packages(self):
        for package in self.packages().values():
            data=package['data']
            for name in ['profile-catalog.php','profile-catalog-transport.php','profile-catalog-api.php']:
                self.assertEqual(data['opt/share/nfqws-asus-web/'+name][1],(ROOT/'webui/web/public'/name).read_bytes())
            for source,name in [('support/profile-catalog.schema.json','profile-catalog.schema.json'),('asus/profile-catalog-public.pem','profile-catalog-public.pem')]:
                self.assertEqual(data['opt/share/nfqws2-asus/'+name][1],(ROOT/source).read_bytes())
            scripts=b'\n'.join(value[1] for path,value in data.items() if path.startswith('opt/share/nfqws-asus-web/assets/') and path.endswith('.js'))
            for phrase in ['Из облака','From cloud','Глобальные стратегии','Global strategies','Фрэнк одобряет...','Frank approves...']:
                self.assertIn(phrase.encode(),scripts)
            self.assertFalse(any('private.pem' in p or '/profile-catalog/files/' in p for p in data))

    def test_default_strategy_mode_is_auto_in_both_packages(self):
        for package in self.packages().values():
            template=package['data']['opt/etc/nfqws2/nfqws2.conf.notactive'][1]
            self.assertIn(b'NFQWS_EXTRA_ARGS="$MODE_AUTO"',template)

    def test_core_is_complete_and_has_no_keenetic_runtime(self):
        p = self.packages()['aarch64-3.10']
        data = p['data']
        for path in ['opt/usr/bin/nfqws2', 'opt/etc/init.d/S51nfqws2',
                     'opt/libexec/nfqws2-asus/busybox', 'opt/lib/nfqws2-asus/bin/stat',
                     'opt/lib/nfqws2-asus/platform.sh', 'opt/lib/nfqws2-asus/lifecycle.sh',
                     'opt/lib/nfqws2-asus/args.sh', 'opt/etc/nfqws2/nfqws2.conf.notactive',
                     'opt/etc/nfqws2/lua/zapret-lib.lua', 'opt/etc/nfqws2/lua/zapret-antidpi.lua',
                     'opt/etc/nfqws2/lua/zapret-auto.lua',
                     'opt/share/nfqws2-asus/defaults/blobs/quic_initial.bin']:
            self.assertIn(path, list(data))
        binary = data['opt/usr/bin/nfqws2'][1]
        self.assertEqual(binary[:5], b'\x7fELF\x02')
        self.assertEqual(int.from_bytes(binary[18:20], 'little'), 183, 'ARM64 ELF required')
        self.assertFalse(any('/ndm/' in name for name in data))
        for path, (_, content) in data.items():
            if path.startswith(('opt/lib/nfqws2-asus/', 'opt/etc/init.d/')):
                self.assertNotIn(b'ndmc', content, path)
        control = p['control']['control'][1].decode()
        self.assertIn('Architecture: aarch64-3.10', control)
        depends = next(line for line in control.splitlines() if line.startswith('Depends:'))
        self.assertNotIn('busybox', depends, 'A fresh Entware busybox preinst needs its own missing binary')
        self.assertIn('Conflicts: nfqws2-keenetic, nfqws-keenetic, tpws-keenetic', control)
        self.assertIn('opt/etc/nfqws2/lists/auto.list.notactive', data)
        self.assertNotIn('opt/etc/nfqws2/nfqws2.conf', data)
        self.assertNotIn('opt/etc/nfqws2/lists/auto.list', data)

    def test_blob_bundle_is_seed_only_complete_and_matches_catalog_in_both_packages(self):
        catalog=json.loads((ROOT/'asus/blobs/catalog.json').read_text())
        self.assertEqual(len(catalog['files']),12)
        for package in self.packages().values():
            data=package['data'];prefix='opt/share/nfqws2-asus/'
            self.assertEqual(json.loads(data[prefix+'blob-catalog.json'][1]),catalog)
            self.assertEqual(json.loads(data[prefix+'blob-sources.json'][1]),json.loads((ROOT/'asus/blobs/sources.json').read_text()))
            baseline=json.loads(data[prefix+'report-baseline.json'][1])
            self.assertFalse(any(path.startswith('opt/etc/nfqws2/blobs/')for path in data),'Owner blobs must not be overwritten by package unpacking')
            for row in catalog['files']:
                meta,raw=data[prefix+'defaults/blobs/'+row['name']]
                self.assertEqual(meta.mode,0o644)
                self.assertEqual(len(raw),row['byte_length'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
                self.assertEqual(baseline['resources']['blob/'+row['name']],{'bytes':len(raw),'sha256':row['sha256']})
            for name in ['blob-api.php','blob-store.php','import-keenetic.php']:
                self.assertEqual(data['opt/share/nfqws-asus-web/'+name][1],(ROOT/'webui/web/public'/name).read_bytes())
            postinst=package['control']['postinst'][1]
            self.assertIn(b'asus_install_blob_defaults || exit $?',postinst)

    def test_web_is_complete_and_does_not_install_global_server(self):
        self.assertIn('armv7', list(self.packages()), 'one ARMv7 package must serve both Entware ABIs')
        p = self.packages()['armv7']
        data = p['data']
        for path in ['opt/share/nfqws-asus-web/index.html', 'opt/share/nfqws-asus-web/index.php',
                     'opt/share/nfqws-asus-web/asus.php', 'opt/share/nfqws-asus-web/ark.php', 'opt/etc/init.d/S81nfqws-asus-web',
                     'opt/etc/nfqws-asus-web/auth.json',
                     'opt/libexec/nfqws-asus-web/lighttpd',
                     'opt/lib/nfqws-asus-web/lighttpd/armv7-2.6/mod_cgi.so',
                     'opt/lib/nfqws-asus-web/lighttpd/armv7-3.2/mod_cgi.so']:
            self.assertIn(path, list(data))
        self.assertFalse(any('/etc/lighttpd/' in name or 'S80lighttpd' in name for name in data))
        control = p['control']['control'][1].decode()
        for dependency in ['php8-cgi', 'php8-mod-session', 'libpcre2', 'libnettle']:
            self.assertIn(dependency, control)
        self.assertNotIn('nfqws2-asus (', control)
        self.assertIn('Replaces: nfqws-asus-web\n', control)
        self.assertNotIn('php8-mod-curl', control)
        self.assertNotIn(b'opkg upgrade', data['opt/share/nfqws-asus-web/index.php'][1])
        self.assertEqual(data['opt/etc/nfqws-asus-web/auth.json'][0].mode, 0o600)
        self.assertIn(b'/opt/etc/nfqws-asus-web/auth.json\n', p['control']['conffiles'][1])

    def test_enabled_ipv6_adds_ipv6_socket_binding_for_multiple_wans(self):
        args = self.packages()['aarch64-3.10']['data']['opt/lib/nfqws2-asus/args.sh'][1].decode()
        r = subprocess.run(['sh', '-c', args + '''
        USER=nobody; NFQUEUE_NUM=300; ISP_INTERFACE='eth0 eth1'
        IPV6_ENABLED=1; LOG_LEVEL=0; NFQWS_ARGS='--filter-tcp=443'
        _startup_args
        '''], text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('--bind-fix4', r.stdout)
        self.assertIn('--bind-fix6', r.stdout)
        r = subprocess.run(['sh', '-c', args + '''
        USER=nobody; NFQUEUE_NUM=300; ISP_INTERFACE='eth0 eth1'
        IPV6_ENABLED=0; LOG_LEVEL=0; NFQWS_ARGS='--filter-tcp=443'
        _startup_args
        '''], text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('--bind-fix6', r.stdout)

    def scripts(self, action, core=0, web=0, no_start=False):
        p=self.packages()['aarch64-3.10']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); init=root/'opt/etc/init.d'; init.mkdir(parents=True)
            for directory in [root/'opt',root/'opt/etc',init]:directory.chmod(0o755)
            for name,code in [('S51nfqws2',core),('S81nfqws-asus-web',web)]:
                f=init/name; f.write_text(f'#!/bin/sh\necho "{name} $1" >> "{tmp}/calls"\nexit {code}\n'); f.chmod(0o755)
            script=p['control'][action][1].decode().replace('/opt/', tmp+'/opt/').replace("'/opt'",repr(tmp+'/opt'))
            # Host applets/PHP and this fixture's owner stand in for Entware;
            # execute the packaged preserver, rather than skipping its hook.
            if 'final class AsusRelayConffile' in script:
                from test_package_update_guard import NATIVE
                self.assertTrue(NATIVE.is_file(),'native PHP required for packaged maintainer scripts')
                script=script.replace('ASUS_MIGRATION_BUSYBOX='+tmp+'/opt/libexec/nfqws2-asus/busybox','ASUS_MIGRATION_BUSYBOX=/bin/busybox').replace('ASUS_MIGRATION_OWNER=0','ASUS_MIGRATION_OWNER='+str(os.getuid()))
                script=script.replace(tmp+'/opt/bin/php-cgi',str(NATIVE))
                digest=hashlib.sha256((ROOT/'asus/support-relay.json').read_bytes()).hexdigest()
                script=script.replace("'"+digest+"',0))->", "'"+digest+"',"+str(os.getuid())+"))->")
            r=subprocess.run(['sh','-c',script],text=True,capture_output=True,
                             env={**os.environ,'NFQWS_ASUS_NO_START':str(int(no_start))})
            calls=(root/'calls').read_text().splitlines() if (root/'calls').exists() else []
            return r,calls

    def test_postinst_starts_web_before_core_and_propagates_failures(self):
        for code in [0,7]:
            r,calls=self.scripts('postinst',core=code)
            self.assertEqual(r.returncode,code,r.stderr)
            self.assertEqual(calls,['S81nfqws-asus-web start','S51nfqws2 start'])
        r,calls=self.scripts('postinst',web=9)
        self.assertEqual(r.returncode,9,r.stderr)
        self.assertEqual(calls,['S81nfqws-asus-web start'])

    def test_prerm_keeps_web_available_when_core_cannot_stop(self):
        r,calls=self.scripts('prerm',core=7)
        self.assertEqual(r.returncode,7,r.stderr)
        self.assertEqual(calls,['S51nfqws2 stop'])
        r,calls=self.scripts('prerm')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(calls,['S51nfqws2 stop','S81nfqws-asus-web stop'])

    def test_archive_ownership_and_script_modes(self):
        for p in self.packages().values():
            for section in p.values():
                for name, (info, _) in section.items():
                    self.assertEqual((info.uid, info.gid), (0, 0), name)
                    if name in ['preinst', 'postinst', 'prerm', 'postrm'] or '/init.d/' in name:
                        self.assertEqual(info.mode, 0o755, name)


    def test_diagnostic_install_starts_web_and_leaves_core_stopped(self):
        r,calls=self.scripts('postinst',no_start=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(calls,['S81nfqws-asus-web start'])

    def test_all_native_files_match_package_architecture(self):
        for arch,p in self.packages().items():
            cls,machine = (1,40) if arch=='armv7' else (2,183)
            names = ['opt/usr/bin/nfqws2']
            if arch == 'armv7':
                for abi in ['armv7-2.6', 'armv7-3.2']:
                    names.extend([f'opt/libexec/nfqws2-asus/{abi}/busybox',
                                  f'opt/libexec/nfqws-asus-web/{abi}/lighttpd',
                                  f'opt/lib/nfqws-asus-web/lighttpd/{abi}/mod_cgi.so'])
                for shim in ['opt/libexec/nfqws2-asus/busybox', 'opt/libexec/nfqws-asus-web/lighttpd']:
                    self.assertEqual(p['data'][shim][1][:10], b'#!/bin/sh\n', 'fresh legacy install must bootstrap with the stock shell')
            else:
                names.extend(['opt/libexec/nfqws2-asus/busybox',
                              'opt/libexec/nfqws-asus-web/lighttpd', 'opt/lib/nfqws-asus-web/lighttpd/mod_cgi.so'])
            for name in names:
                binary=p['data'][name][1]
                self.assertEqual(binary[:5],b'\x7fELF'+bytes([cls]),name)
                self.assertEqual(int.from_bytes(binary[18:20],'little'),machine,name)
            self.assertIn(f"Architecture: {'all' if arch == 'armv7' else arch}\n",p['control']['control'][1].decode())
            self.assertIn('opt/etc/init.d/S51nfqws2',p['data'])
            self.assertIn('opt/etc/init.d/S81nfqws-asus-web',p['data'])
            self.assertNotIn('opt/etc/nfqws-asus-web/ark-backup.json',p['data'])


if __name__ == '__main__': unittest.main()
