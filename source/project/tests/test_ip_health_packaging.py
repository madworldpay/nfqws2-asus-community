"""Inspect emitted own package payload; external pinned archive loading is the boundary."""
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ip_health_asus_builder',ROOT/'asus/build.py')
asus=importlib.util.module_from_spec(spec);spec.loader.exec_module(asus)


class IpHealthPackagingTests(unittest.TestCase):
    def frontend(self,root):
        dist=root/'dist';dist.mkdir()
        (dist/'index.html').write_text('fixture')
        for path in (ROOT/'webui/web/public').glob('*.php'):(dist/path.name).write_bytes(path.read_bytes())
        return dist

    def test_emitted_asus_arch_packages_include_exact_health_files_without_dependency_change(self):
        for arch in asus.TARGETS:
            with self.subTest(arch=arch),tempfile.TemporaryDirectory()as folder:
                root=Path(folder);dist=self.frontend(root);target=asus.TARGETS[arch]
                elf=bytearray(64);elf[:6]=b'\x7fELF'+bytes([target['elf_class'],1]);elf[18:20]=target['elf_machine'].to_bytes(2,'little');elf=bytes(elf)
                def external_asset(name,cache,offline):
                    return {target['engine_member']:elf,'opt/usr/bin/nfqws2':elf,'opt/bin/busybox':elf,'opt/sbin/lighttpd':elf,'opt/lib/lighttpd/mod_cgi.so':elf}
                web_payload=getattr(asus,'web_payload',None)
                self.assertTrue(callable(web_payload),'ASUS packaging needs the freshness-checked public backend boundary')
                with patch.object(asus,'asset',external_asset),patch.object(asus,'raw_asset',lambda name,cache,offline:b'inert verified external archive boundary'),patch.object(asus,'prepare_engine',lambda data,target:data),patch.object(asus,'web_payload',lambda:web_payload(dist)):
                    asus.build_one(root,root,True,arch,82)
                ipk=next(root.glob('*.ipk'))
                with tarfile.open(ipk)as package:
                    control=package.extractfile('control.tar.gz').read();data=package.extractfile('data.tar.gz').read()
                with tarfile.open(fileobj=io.BytesIO(control))as archive:
                    metadata=archive.extractfile('control').read().decode()
                    self.assertIn('Depends: iptables, flock, php8-cgi, php8-mod-session, php8-mod-openssl, ca-bundle, libc, libssp, librt, libpthread, libpcre2, libnettle\n',metadata)
                with tarfile.open(fileobj=io.BytesIO(data))as archive:
                    for name in ['runtime.sh','worker.php','monitor.lua','dns.lua']:
                        member=archive.getmember('opt/lib/nfqws2-asus/ip-health/'+name)
                        self.assertEqual(archive.extractfile(member).read(),(ROOT/'ip-health'/name).read_bytes())
                        self.assertEqual(member.mode,0o644)
                        self.assertEqual((member.uid,member.gid),(0,0))
                    for name in ['api','store','probe','controller','runtime']:
                        self.assertEqual(archive.extractfile('opt/share/nfqws-asus-web/ip-health-'+name+'.php').read(),(ROOT/'webui/web/public'/('ip-health-'+name+'.php')).read_bytes())
                    self.assertEqual(archive.extractfile('opt/lib/nfqws2-asus/ip-health/control.sh').read(),(ROOT/'ip-health/control.sh').read_bytes())
                    self.assertEqual(archive.getmember('opt/lib/nfqws2-asus/ip-health/control.sh').mode,0o755)
                    for name in ['worker.php','control.sh']:
                        self.assertEqual(archive.extractfile('opt/lib/nfqws2-asus/ip-health-sockets/'+name).read(),(ROOT/'asus/ip-health-sockets'/name).read_bytes())
                    self.assertEqual(archive.getmember('opt/libexec/nfqws2-asus/sockets-launch').mode,0o755)
                    self.assertFalse(any(name.endswith('bans.json')or name.endswith('/sockets.so')for name in archive.getnames()))

    def test_optional_sockets_archives_are_family_scoped_signed_data_with_exact_payload_pins(self):
        import hashlib,json
        helper=getattr(asus,'ip_health_sockets_payload',None)
        self.assertTrue(callable(helper),'sockets inert payload missing')
        catalog=json.loads((ROOT/'asus/ip-health-sockets.json').read_text())
        for family,abis in [('armv7',{'armv7-2.6','armv7-3.2'}),('aarch64-3.10',{'aarch64-3.10'})]:
            archives={e['filename']:('verified-'+e['filename']).encode()for e in catalog['entries']}
            with patch.object(asus,'raw_asset',lambda name,cache,offline:archives[name]):
                files=helper(Path('/unused'),True,family)
            installed=json.loads(files['opt/share/nfqws2-asus/ip-health-sockets/catalog.json'][0])
            self.assertEqual({e['abi']for e in installed['entries']},abis)
            for e in installed['entries']:
                self.assertEqual(files['opt/share/nfqws2-asus/ip-health-sockets/ipks/'+e['filename']],(archives[e['filename']],0o644))
                self.assertEqual(set(e['files']),{'opt/etc/php8/20_sockets.ini','opt/lib/php8/sockets.so'})
                self.assertEqual(e['php_package_version'],e['version'])
                self.assertEqual(e['files']['opt/etc/php8/20_sockets.ini']['sha256'],hashlib.sha256(b'extension=sockets.so\n').hexdigest())
                self.assertEqual(asus.ASSETS[e['filename']]['sha256'],e['sha256'])
            self.assertFalse(any(p.endswith('/sockets.so')or p.startswith('opt/etc/php8')for p in files))

    def test_dedicated_sockets_launcher_uses_shared_source_and_its_own_inventory(self):
        import hashlib,json
        manifest=json.loads((ROOT/'asus/update/bin/sockets-launchers.json').read_text())
        for target in asus.TARGETS.values():
            binary,mode=asus.update_launcher(target,stem='sockets-launch',manifest='sockets-launchers.json',source='opkg-launch.c')
            family='aarch64'if target['elf_class']==2 else'armv7'
            self.assertEqual(mode,0o755);self.assertEqual(hashlib.sha256(binary).hexdigest(),manifest['outputs'][family]['sha256'])

    def test_stale_health_backend_is_refused_before_packaging(self):
        with tempfile.TemporaryDirectory()as folder:
            dist=self.frontend(Path(folder));(dist/'ip-health-runtime.php').write_text('<?php /* stale */')
            payload=getattr(asus,'web_payload',None);self.assertTrue(callable(payload),'fresh backend check missing')
            with self.assertRaisesRegex(RuntimeError,'stale'):payload(dist)
