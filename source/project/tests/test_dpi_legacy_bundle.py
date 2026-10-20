"""Legacy installation uses only the pinned, non-executable package payload."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC


class DpiLegacyBundleTests(unittest.TestCase):
    def install(self, variant='ok'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = bytearray(64)
            data[:6] = b'\x7fELF\x01\x01'
            data[18:20] = (40).to_bytes(2, 'little')
            data = bytes(data)
            source = root / 'bundle'
            source.write_bytes(data)
            source.chmod(0o644)
            artifact = {'name':'dpi-detector-armv5te','source':'bundled-legacy','size':64,
                        'sha256':hashlib.sha256(data).hexdigest(),'elf_class':1,'elf_machine':40}
            if variant == 'hash':
                source.write_bytes(data[:-1] + b'x')
            if variant == 'writable':
                source.chmod(0o666)
            if variant == 'link':
                original = root / 'original'
                source.rename(original)
                source.symlink_to(original)
            (root / 'artifact.json').write_text(json.dumps(artifact))
            code = '''require $argv[1].'/dpi-install.php';
            $p=$argv[2];$a=json_decode(file_get_contents($p.'/artifact.json'),true);
            $fetch=function(){throw new RuntimeException('UNEXPECTED_NETWORK');};
            $probe=function(){return ['exit'=>0,'stdout'=>"dpi-detector 5.0.0-alpha.21\\n"];};
            $i=new AsusDpiInstaller($p.'/managed',(int)$argv[3],$a,$fetch,$probe,$p.'/bundle');
            try{$first=$i->install(str_repeat('a',32));$second=$i->install(str_repeat('b',32));
            echo json_encode(['first'=>$first,'second'=>$second,'sha256'=>hash_file('sha256',$i->binary())]);}
            catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
            result = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stderr,'')
            value = json.loads(result.stdout)
            self.assertFalse(list((root / 'managed').glob('.stage-*')))
            if 'error' in value:
                self.assertFalse((root / 'managed/active.json').exists())
            return value, artifact['sha256']

    def test_legacy_install_is_local_verified_and_idempotent(self):
        value, digest = self.install()
        self.assertNotIn('error',value)
        self.assertTrue(value['first']['installed'])
        self.assertEqual(value['first'],value['second'])
        self.assertEqual(value['sha256'],digest)

    def test_wrong_package_payload_cannot_activate(self):
        self.assertEqual(self.install('hash')[0],{'error':'download_hash'})

    def test_link_or_writable_package_payload_cannot_activate(self):
        for variant in ['link','writable']:
            with self.subTest(variant=variant):
                self.assertEqual(self.install(variant)[0],{'error':'invalid_state'})

    def previous_installation(self, tampered=False):
        # Changing the preferred artifact must not disable an already accepted,
        # still byte-verified release. Arbitrary or modified bytes stay rejected.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            managed = root / 'managed'
            managed.mkdir(mode=0o711)
            managed.chmod(0o711)
            previous = b'previous verified detector'
            digest = hashlib.sha256(previous).hexdigest()
            binary = managed / digest
            binary.write_bytes(previous + (b'x' if tampered else b''))
            binary.chmod(0o755)
            metadata = managed / 'active.json'
            before = json.dumps({'version':'v5.0.0-alpha.21','sha256':digest}).encode()
            metadata.write_bytes(before)
            metadata.chmod(0o600)
            artifact = {'name':'dpi-detector-armv5te','source':'bundled-legacy',
                        'size':64,'sha256':'a'*64,'elf_class':1,'elf_machine':40,
                        'accepted_installed':[{'size':len(previous),'sha256':digest}]}
            (root / 'artifact.json').write_text(json.dumps(artifact))
            code = '''require $argv[1].'/dpi-install.php';
            $p=$argv[2];$a=json_decode(file_get_contents($p.'/artifact.json'),true);
            $unexpected=function(){throw new RuntimeException('UNEXPECTED_REINSTALL');};
            $i=new AsusDpiInstaller($p.'/managed',(int)$argv[3],$a,$unexpected,$unexpected);
            $state=$i->installed();$value=['state'=>$state];
            try{$value['binary']=basename($i->binary());$value['install']=$i->install(str_repeat('c',32));}
            catch(Throwable $e){$value['error']=$e->getMessage();}
            echo json_encode($value);'''
            result = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stderr,'')
            self.assertEqual(metadata.read_bytes(),before)
            self.assertEqual(binary.read_bytes(),previous + (b'x' if tampered else b''))
            return json.loads(result.stdout), digest

    def test_preferred_artifact_change_preserves_verified_installed_release(self):
        value, digest = self.previous_installation()
        self.assertEqual(value,{'state':{'installed':True,'version':'v5.0.0-alpha.21'},
                                'binary':digest,'install':{'installed':True,'version':'v5.0.0-alpha.21'}})

    def test_modified_previous_release_is_not_accepted(self):
        value, _ = self.previous_installation(tampered=True)
        self.assertEqual(value,{'state':{'installed':False,'version':None},'error':'not_installed'})
