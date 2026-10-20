"""The optional installer must never execute an IPK's scripts or replace DNS."""
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC


def archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as tar:
        for name, raw, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == 'link':
                info.type = tarfile.SYMTYPE
                info.linkname = '../../outside'
                tar.addfile(info)
            else:
                info.size = len(raw)
                tar.addfile(info, io.BytesIO(raw))
    return output.getvalue()


class SmartDnsInstallTests(unittest.TestCase):
    def test_orphan_downloads_are_removed_but_current_stage_and_external_links_remain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'managed';root.mkdir(mode=0o700)
            old=root/('.stage-'+'a'*32);old.mkdir(mode=0o700);(old/'download.ipk').write_bytes(b'abandoned')
            active=root/('.stage-'+'b'*32);active.mkdir(mode=0o700)
            outside=Path(directory)/'outside';outside.mkdir();(outside/'canary').write_text('keep')
            link=root/('.stage-'+'c'*32);link.symlink_to(outside)
            code = '''require $argv[1].'/smartdns-install.php';(new AsusSmartDnsInstaller($argv[2],(int)$argv[3]))->cleanupStages(str_repeat('b',32));'''
            p = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertFalse(old.exists());self.assertTrue(active.exists());self.assertTrue(link.is_symlink());self.assertEqual((outside/'canary').read_text(),'keep')

    def probe(self, variant='ok'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = bytearray(64)
            binary[:6] = b'\x7fELF\x01\x01'
            binary[18:20] = (40).to_bytes(2, 'little')
            if variant == 'elf':
                binary[18:20] = (183).to_bytes(2, 'little')
            files = {'smartdns': bytes(binary), 'lib/libc.so': b'loader'}
            prefix = 'opt/usr/local/lib/smartdns/'
            entries = [(prefix+n, raw, 'link' if variant == 'link' and n == 'smartdns' else 'file') for n, raw in files.items()]
            entries += [('opt/etc/init.d/S50smartdns', b'UNWANTED_INIT', 'file')]
            data = archive(entries)
            ipk = archive([('debian-binary', b'2.0\n', 'file'), ('control.tar.gz', archive([('postinst', b'UNWANTED_POSTINST', 'file')]), 'file'), ('data.tar.gz', data, 'file')])
            (root/'asset').write_bytes(ipk)
            (root/'existing-dns.conf').write_text('ORIGINAL_DNS')
            artifact = {'version': '1.2026.08.05-0921', 'version_output': 'smartdns 1.2026.08.05-0921 (Release48.4)', 'size': len(ipk), 'sha256': hashlib.sha256(ipk).hexdigest(),
                        'elf_class': 1, 'elf_machine': 40, 'url': 'https://github.com/fixture',
                        'files': {n: {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for n, raw in files.items()},
                        'links': {'lib/ld-musl-arm.so.1': 'libc.so', 'lib/ld-linux.so': 'ld-musl-arm.so.1'}}
            if variant == 'hash':
                artifact['sha256'] = '0'*64
            (root/'artifact.json').write_text(json.dumps(artifact))
            if variant == 'orphan':
                managed=root/'managed';managed.mkdir(mode=0o700)
                bundle=managed/artifact['sha256'];bundle.mkdir(mode=0o700);(bundle/'lib').mkdir(mode=0o700)
                for name,raw in files.items():
                    (bundle/name).write_bytes(raw);(bundle/name).chmod(0o700)
                for name,target in artifact['links'].items():
                    (bundle/name).symlink_to(target)
            code = '''require $argv[1].'/smartdns-install.php';umask(0077);$p=$argv[2];$a=json_decode(file_get_contents($p.'/artifact.json'),true);$calls=0;
            $fetch=function($a,$dest,$deadline)use($p,&$calls){$calls++;copy($p.'/asset',$dest);};
            $probe=function($args,$cwd,$seconds)use($argv){if($cwd==='/'||$args!==['./smartdns','-v']||$seconds>5)throw new Exception('bad_probe');return ['exit'=>0,'stdout'=>$argv[3]==='version'?'wrong':"smartdns 1.2026.08.05-0921 (Release48.4)\\n"];};
            $i=new AsusSmartDnsInstaller($p.'/managed',fileowner($p),$a,$fetch,$probe);
            try{$first=$i->install(str_repeat('a',32));$second=$i->install(str_repeat('b',32));echo json_encode(['first'=>$first,'second'=>$second,'calls'=>$calls,'path'=>$i->binaryDirectory()]);}
            catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
            result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(root), variant], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            value = json.loads(result.stdout)
            self.assertEqual((root/'existing-dns.conf').read_text(), 'ORIGINAL_DNS')
            self.assertFalse((root/'etc').exists())
            if 'error' not in value:
                bundle = Path(value['path'])
                self.assertEqual((bundle/'smartdns').read_bytes(), bytes(binary))
                self.assertEqual((bundle/'lib/ld-musl-arm.so.1').readlink().as_posix(), 'libc.so')
                self.assertFalse((bundle/'S50smartdns').exists())
                self.assertFalse(list((root/'managed').glob('.stage-*')))
            else:
                self.assertFalse((root/'managed/current').exists())
            return value

    def test_verified_bundle_is_idempotent_and_does_not_install_vendor_scripts(self):
        value = self.probe()
        self.assertTrue(value['first']['installed'])
        self.assertEqual(value['first'], value['second'])
        self.assertEqual(value['calls'], 1)

    def test_bad_download_hash_cannot_activate(self):
        self.assertEqual(self.probe('hash')['error'], 'download_hash')

    def test_interruption_after_bundle_publish_can_recover_without_redownloading(self):
        value=self.probe('orphan')
        self.assertIn('first',value)
        self.assertTrue(value['first']['installed'])
        self.assertEqual(value['calls'],0)

    def test_wrong_cpu_cannot_activate(self):
        self.assertEqual(self.probe('elf')['error'], 'unsupported_binary')

    def test_symlink_instead_of_engine_cannot_escape_or_activate(self):
        self.assertEqual(self.probe('link')['error'], 'invalid_package')

    def test_wrong_reported_version_cannot_activate(self):
        self.assertEqual(self.probe('version')['error'], 'unsupported_binary')
