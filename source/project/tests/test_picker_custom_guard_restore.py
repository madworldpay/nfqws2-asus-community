"""Actual independent guard after parent SIGKILL, on both package layouts."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
IMAGE='nfqws-openwrt-test:25.12.6-php'


@unittest.skipUnless(os.environ.get('NFQWS_TEST_GUARD_PHP_IMAGE')==IMAGE,
                     'Requires cached isolated root PHP image for actual guard timing')
class CustomGuardRestoreTests(unittest.TestCase):
    def run_guard(self, platform):
        task='picker-custom-guard-'+uuid.uuid4().hex
        cid=None
        evidence={'task':task,'platform':platform}
        proof_root=os.environ.get('NFQWS_TEST_CUSTOM_GUARD_EVIDENCE_DIR')
        with tempfile.TemporaryDirectory()as directory:
            web=Path(directory)/'web'
            shutil.copytree(ROOT/'webui/web/public',web)
            for source in (ROOT/'experimental/device-profiles').glob('device-profiles-*.php'):
                self.assertFalse((web/source.name).exists())
                shutil.copyfile(source,web/source.name)
            for path in web.rglob('*'):
                self.assertFalse(path.is_symlink())
                path.chmod(0o755 if path.is_dir()else 0o644)
            web.chmod(0o755)
            fixtures=ROOT/'tests/fixtures'
            mounts=['--mount',f'type=bind,src={web},dst=/fixture-web,readonly',
                    '--mount',f'type=bind,src={ROOT/"openwrt/config.php"},dst=/fixtures/config.php,readonly']
            for name,dest in [('master','master'),('worker','custom-worker'),('leaf','custom-leaf')]:
                mounts+=['--mount',f'type=bind,src={fixtures/"picker-custom-guard-"}{name}.php,dst=/fixtures/{dest}.php,readonly']
            tmpfs=[]
            for path,size in [('/tmp','16m'),('/opt','32m'),('/etc/nfqws2','1m'),('/etc/nfqws2-web','2m'),
                              ('/etc/init.d','1m'),('/usr/share/nfqws2-web','32m'),('/usr/lib/nfqws2','2m')]:
                tmpfs+=['--tmpfs',f'{path}:rw,exec,nosuid,nodev,mode=0755,size={size}']
            try:
                cid=subprocess.check_output(['docker','create','--pull=never','--name','nfqws-'+task,
                    '--label','org.nfqws2.task='+task,'--network','none','--cap-drop','ALL',
                    '--security-opt','no-new-privileges:true','--read-only','--pids-limit','48',
                    '--memory','128m','--cpus','0.5',*tmpfs,*mounts,'--entrypoint','/usr/bin/php8-cgi',
                    IMAGE,'-n','-d','register_argc_argv=1','-d','max_execution_time=0','-d','max_input_time=0',
                    '-q','-f','/fixtures/master.php','--',platform],text=True).strip()
                result=subprocess.run(['docker','start','-a',cid],capture_output=True,text=True,timeout=120)
                evidence.update({'id':cid,'status':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
                self.assertEqual(result.stderr,'',result.stdout+result.stderr)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                rows=[json.loads(line)for line in result.stdout.splitlines()if line.strip()]
                self.assertEqual(rows[-1],{'passed':True,'platform':platform,'cases':4})
                self.assertEqual([r['stage']for r in rows[:-1]],['empty','full','child','foreign'])
                self.assertTrue(all(row['passed']for row in rows[:-1]))
                inspection=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
                self.assertFalse(inspection['State']['OOMKilled'])
                self.assertEqual(inspection['HostConfig']['NetworkMode'],'none')
            finally:
                if cid:
                    info=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
                    self.assertEqual(info['Config']['Labels']['org.nfqws2.task'],task)
                    self.assertEqual(info['Name'],'/nfqws-'+task)
                    subprocess.run(['docker','rm','-f',cid],check=True,stdout=subprocess.DEVNULL)
                    absent=subprocess.run(['docker','inspect',cid],capture_output=True).returncode!=0
                    self.assertTrue(absent)
                    evidence['container_removed_independently_verified']=absent
                if proof_root:
                    proof=Path(proof_root)
                    self.assertTrue(proof.is_absolute())
                    proof.mkdir(parents=True,exist_ok=True)
                    (proof/(platform+'.json')).write_text(json.dumps(evidence,indent=2)+'\n')

    def test_asus_guard_recovers_owned_pending_and_child_without_touching_foreign_actors(self):
        self.run_guard('asus-entware')

    def test_openwrt_guard_recovers_owned_pending_and_child_without_touching_foreign_actors(self):
        self.run_guard('openwrt')


if __name__=='__main__':unittest.main()
