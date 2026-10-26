import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC


class DpiInstallTests(unittest.TestCase):
    def test_killed_installer_stage_is_reconciled(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'managed'
            code='''require $argv[1].'/dpi-install.php';$root=$argv[2];$artifact=['size'=>64,'sha256'=>str_repeat('a',64),'elf_class'=>2,'elf_machine'=>183];
            $i=new AsusDpiInstaller($root,(int)$argv[3],$artifact,function($a,$dest){file_put_contents($dest,str_repeat('x',32));chmod($dest,0600);sleep(30);});$i->install(str_repeat('d',32));'''
            p=subprocess.Popen([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            stage=root/('.stage-'+('d'*32));end=time.monotonic()+3
            try:
                while not stage.exists() and time.monotonic()<end:time.sleep(0.01)
                self.assertTrue(stage.exists());p.send_signal(signal.SIGTERM);p.communicate(timeout=3)
                self.assertTrue(stage.exists(),'test must exercise skipped PHP finally')
                clean='''require $argv[1].'/dpi-install.php';(new AsusDpiInstaller($argv[2],(int)$argv[3]))->cleanupStages();'''
                r=subprocess.run([PHP,'-n','-r',clean,str(PUBLIC),str(root),str(os.getuid())],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(list(root.iterdir()),[])
            finally:
                if p.poll() is None:p.kill();p.communicate()

    def test_conservative_legacy_memory_parser(self):
        code='''require $argv[1].'/dpi-install.php';$out=[];foreach(json_decode(stream_get_contents(STDIN),true) as $raw)$out[]=AsusDpiInstaller::availableMemoryKiB($raw);echo json_encode($out);'''
        inputs=['MemAvailable: 65536 kB\n','MemAvailable: 65535 kB\n',
                'MemFree: 100000 kB\nBuffers: 100 kB\nCached: 50000 kB\nShmem: 1000 kB\n',
                'MemFree: 63000 kB\nCached: 90000 kB\n','MemFree: -1 kB\n',
                'MemFree: 99999999999999999999 kB\n','MemFree: 70000 kB\nMemFree: 90000 kB\n',
                'MemAvailable: nope\nMemFree: 90000 kB\n','Cached: 90000 kB\n']
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(inputs),capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'')
        self.assertEqual(json.loads(r.stdout),[65536,65535,100000,63000,0,0,0,0,0])

    def test_orphan_stages_are_swept_without_touching_current_or_manual_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'managed';root.mkdir(mode=0o711)
            names=['.stage-'+('a'*32),'.active-'+('a'*32),'.stage-'+('b'*32),'manual','.stage-not-ours']
            for name in names:(root/name).write_text('canary');(root/name).chmod(0o600)
            outside=Path(directory)/'outside';outside.write_text('keep')
            (root/('.stage-'+('c'*32))).symlink_to(outside)
            code='''require $argv[1].'/dpi-install.php';$i=new AsusDpiInstaller($argv[2],fileowner($argv[2]));$i->cleanupStages(str_repeat('b',32));echo json_encode(scandir($argv[2]));'''
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);remaining=json.loads(r.stdout)
            self.assertNotIn(names[0],remaining);self.assertNotIn(names[1],remaining)
            for name in names[2:]:self.assertIn(name,remaining)
            self.assertTrue((root/('.stage-'+('c'*32))).is_symlink());self.assertEqual(outside.read_text(),'keep')
    def test_atomic_install_and_idempotence_preserve_manual_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'manual').write_text('PRIVATE_CANARY');payload=bytearray(64);payload[:6]=b'\x7fELF\x02\x01';payload[18:20]=(183).to_bytes(2,'little');payload=bytes(payload)
            (p/'asset').write_bytes(payload)
            fixture={'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'elf_class':2,'elf_machine':183,'name':'test','url':'https://github.com/test'}
            (p/'fixture').write_text(json.dumps(fixture))
            code='''require $argv[1].'/dpi-install.php';umask(0077);$artifact=json_decode(file_get_contents($argv[2].'/fixture'),true);$calls=0;$versions=[];
            $fetch=function($a,$dest,$deadline)use(&$calls){$calls++;copy(dirname($dest).'/../asset',$dest);};
            $probe=function($job,$args,$cwd,$limit)use(&$versions){$versions[]=$args;return ['exit'=>0,'stdout'=>"dpi-detector 5.0.0-alpha.21\\n"];};
            $i=new AsusDpiInstaller($argv[2].'/managed',fileowner($argv[2]),$artifact,$fetch,$probe);
            $a=$i->install(str_repeat('a',32));$b=$i->install(str_repeat('b',32));
            echo json_encode([$a,$b,$calls,$versions,file_get_contents($argv[2].'/manual')]);'''
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(p)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'')
            a,b,calls,versions,manual=json.loads(r.stdout);self.assertTrue(a['installed']);self.assertEqual(a,b);self.assertEqual(calls,1)
            self.assertEqual([v[1:] for v in versions],[['--version']]);self.assertEqual(manual,'PRIVATE_CANARY')
            self.assertEqual((p/'managed/active.json').stat().st_mode&0o777,0o600)

    def test_big_endian_pinned_mips_can_install(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);payload=bytearray(64);payload[:6]=b'\x7fELF\x01\x02';payload[18:20]=b'\0\x08'
            (p/'asset').write_bytes(payload)
            fixture={'size':64,'sha256':hashlib.sha256(payload).hexdigest(),'elf_class':1,'elf_data':2,'elf_machine':8}
            (p/'fixture').write_text(json.dumps(fixture))
            code='''require $argv[1].'/dpi-install.php';umask(0077);$a=json_decode(file_get_contents($argv[2].'/fixture'),true);
            $i=new AsusDpiInstaller($argv[2].'/managed',fileowner($argv[2]),$a,function($a,$dest){copy(dirname($dest).'/../asset',$dest);},function(){return ['exit'=>0,'stdout'=>"dpi-detector 5.0.0-alpha.21\\n"];});
            echo json_encode($i->install(str_repeat('a',32)));'''
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(p)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertTrue(json.loads(r.stdout)['installed'])

    def test_bad_hash_elf_or_version_cannot_activate(self):
        code='''require $argv[1].'/dpi-install.php';$root=$argv[2];$a=['size'=>64,'sha256'=>hash('sha256',str_repeat('x',64)),'elf_class'=>2,'elf_machine'=>183,'name'=>'test','url'=>'https://github.com/test'];
        $i=new AsusDpiInstaller($root,fileowner(dirname($root)),$a,function($a,$dest){file_put_contents($dest,str_repeat('x',64));},function(){throw new Exception('version must not run');});
        try{$i->install(str_repeat('c',32));echo 'UNSAFE';}catch(Throwable $e){echo $e->getMessage();}'''
        with tempfile.TemporaryDirectory() as directory:
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),directory+'/managed'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');self.assertEqual(r.stdout,'unsupported_binary')
            self.assertFalse(Path(directory+'/managed/active.json').exists())
            self.assertEqual(list(Path(directory+'/managed').iterdir()),[])
