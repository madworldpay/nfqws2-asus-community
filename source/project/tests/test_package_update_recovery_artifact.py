"""Inspect real signed release artifacts in private roots; never run their scripts."""
import base64
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from test_dpi_normalize import PHP, PUBLIC, ROOT


@unittest.skipUnless(os.environ.get('ASUS_RECOVERY_ARTIFACTS'), 'signed release artifact directory required')
class PackageUpdateRecoveryArtifactTests(unittest.TestCase):
    def test_published_arm_and_aarch64_closures_resume_with_private_conffiles(self):
        assets=Path(os.environ['ASUS_RECOVERY_ARTIFACTS'])
        envelope=json.loads((assets/'public.json').read_text())
        raw=base64.b64decode(envelope['manifest'],validate=True).decode()
        verify='''require $argv[1].'/update-prepare.php';$p=json_decode(stream_get_contents(STDIN),true);
        try{$m=AsusPackageManifest::verify($p['json'],$p['signature'],file_get_contents($argv[2]));echo json_encode(['manifest'=>$m]);}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        r=subprocess.run([PHP,'-n','-d','memory_limit=16M','-r',verify,str(PUBLIC),str(ROOT/'updates/trusted-release-key.pem')],input=json.dumps({'json':raw,'signature':envelope['signature']}),capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');manifest=json.loads(r.stdout)
        self.assertIn('manifest',manifest);manifest=manifest['manifest']
        for family,abi,machine in [('armv7','armv7-2.6','armv7l'),('armv7','armv7-3.2','armv7l'),('aarch64-3.10','aarch64-3.10','aarch64')]:
            with self.subTest(abi=abi), tempfile.TemporaryDirectory() as directory:
                base=Path(directory);opt=base/'opt';opt.mkdir(mode=0o755)
                package=next(p for p in manifest['packages'] if p['family']==family)
                path=base/'package.ipk';shutil.copyfile(assets/package['filename'],path);path.chmod(0o600)
                with tarfile.open(path) as outer:
                    control_bytes=outer.extractfile('control.tar.gz').read();data_bytes=outer.extractfile('data.tar.gz').read()
                with tarfile.open(fileobj=io.BytesIO(control_bytes)) as controls:
                    members={m.name.removeprefix('./'):(m,controls.extractfile(m).read()) for m in controls if m.isfile()}
                control=dict(line.split(': ',1) for line in members['control'][1].decode().strip().splitlines())
                info=opt/'lib/opkg/info';info.mkdir(parents=True,mode=0o755)
                for name in ['preinst','postinst','prerm','postrm']:
                    if name in members:
                        member,data=members[name];installed=info/('nfqws2-asus.'+name);installed.write_bytes(data);installed.chmod(member.mode)
                with tarfile.open(fileobj=io.BytesIO(data_bytes)) as data:
                    for member in data:
                        name=member.name.removeprefix('./');parts=Path(name).parts
                        self.assertEqual(parts[0],'opt');self.assertNotIn('..',parts);self.assertFalse(Path(name).is_absolute())
                        installed=base/name
                        if member.isdir():installed.mkdir(parents=True,exist_ok=True);installed.chmod(member.mode)
                        else:
                            self.assertTrue(member.isfile(),member.name);installed.parent.mkdir(parents=True,exist_ok=True)
                            installed.write_bytes(data.extractfile(member).read());installed.chmod(member.mode)
                # Opkg's database directories are not payload archive members.
                for parent in [opt,opt/'lib',opt/'lib/opkg',info]:parent.chmod(0o755)
                control['Status']='install user unpacked'
                status=''.join(key+': '+value+'\n' for key,value in control.items())+'\n'
                for dependency in control['Depends'].split(','):
                    status+='Package: '+dependency.strip()+'\nVersion: 1\nStatus: install ok installed\n\n'
                candidate={k:manifest[k] for k in ['revision','package_version','core_version','web_version','build','notes']}
                candidate.update(package=package,action='configure')
                inspect='''require $argv[1].'/update-prepare.php';$p=json_decode(stream_get_contents(STDIN),true);
                try{AsusUpdatePackage::inspect($argv[2],$p['candidate'],$p['status'],$p['abi'],$p['machine'],$argv[3],(int)$argv[4]);echo json_encode(['verified'=>true]);}
                catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
                def check():
                    result=subprocess.run([PHP,'-n','-d','memory_limit=16M','-r',inspect,str(PUBLIC),str(path),str(opt),str(os.getuid())],input=json.dumps({'candidate':candidate,'status':status,'abi':abi,'machine':machine}),capture_output=True,text=True,timeout=30)
                    self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'');return json.loads(result.stdout)
                self.assertEqual(check(),{'verified':True})
                for name in ['auth.json','support-relay.json']:(opt/'etc/nfqws-asus-web'/name).write_bytes(b'PRIVATE CONFFILE CANARY')
                self.assertEqual(check(),{'verified':True})
                immutable=opt/'lib/nfqws2-asus/args.sh';immutable.write_bytes(immutable.read_bytes()+b'\nCHANGED\n')
                self.assertEqual(check(),{'error':'recovery_required'})
