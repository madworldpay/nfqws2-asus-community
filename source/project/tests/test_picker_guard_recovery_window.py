"""Run the actual guard in a root-owned, network-isolated fixture on both layouts."""
from pathlib import Path
import json,os,shutil,subprocess,tempfile,unittest,uuid
ROOT=Path(__file__).resolve().parents[1]
IMAGE='nfqws-openwrt-test:25.12.6-php'

@unittest.skipUnless(os.environ.get('NFQWS_TEST_GUARD_PHP_IMAGE')==IMAGE,
                     'Requires cached isolated root PHP image for actual guard timing')
class GuardRecoveryWindowTests(unittest.TestCase):
    def run_guard(self,platform):
        task='picker-guard-window-'+uuid.uuid4().hex
        cid=None
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);web=root/'web'
            shutil.copytree(ROOT/'webui/web/public',web)
            for source in (ROOT/'experimental/device-profiles').glob('device-profiles-*.php'):
                self.assertFalse((web/source.name).exists());shutil.copyfile(source,web/source.name)
            # Container root retains no DAC override. Expose only this public
            # snapshot and individual scripts; private temp ancestors stay 0700.
            for path in web.rglob('*'):
                self.assertFalse(path.is_symlink())
                path.chmod(0o755 if path.is_dir()else 0o644)
            web.chmod(0o755)
            fixtures=ROOT/'tests/fixtures'
            mounts=['--mount',f'type=bind,src={web},dst=/fixture-web,readonly',
                    '--mount',f'type=bind,src={fixtures/"picker-guard-recovery-master.php"},dst=/fixtures/master.php,readonly',
                    '--mount',f'type=bind,src={fixtures/"picker-guard-recovery-worker.php"},dst=/fixtures/worker.php,readonly',
                    '--mount',f'type=bind,src={ROOT/"openwrt/config.php"},dst=/fixtures/config.php,readonly']
            try:
                create=['docker','create','--pull=never','--name','nfqws-'+task,'--label','org.nfqws2.task='+task,
                        '--network','none','--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only',
                        '--pids-limit','24','--memory','96m','--cpus','0.5',
                        '--tmpfs','/tmp:rw,nosuid,nodev,size=16m','--tmpfs','/opt:rw,nosuid,nodev,mode=0755,size=24m',
                        '--tmpfs','/etc/nfqws2:rw,nosuid,nodev,mode=0755,size=1m','--tmpfs','/etc/nfqws2-web:rw,nosuid,nodev,mode=0755,size=1m',
                        '--tmpfs','/usr/share/nfqws2-web:rw,nosuid,nodev,mode=0755,size=24m','--tmpfs','/usr/lib/nfqws2:rw,nosuid,nodev,mode=0755,size=2m',
                        *mounts,'--entrypoint','/usr/bin/php8-cgi',IMAGE,'-n','-d','register_argc_argv=1',
                        '-d','max_execution_time=0','-d','max_input_time=0','-q','-f','/fixtures/master.php','--',platform]
                cid=subprocess.check_output(create,text=True).strip()
                result=subprocess.run(['docker','start','-a',cid],capture_output=True,text=True,timeout=250)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(result.stderr,'')
                rows=[json.loads(line)for line in result.stdout.splitlines()if line.strip()]
                self.assertIs(rows[-1]['passed'],True)
                self.assertEqual(rows[-1]['platform'],platform)
                events={row['event']:row for row in rows[:-1]}
                self.assertLess(events['unknown_live_context_preserved']['seconds'],6)
                self.assertIs(events['unknown_live_context_preserved']['work_still_alive'],True)
                self.assertIs(events['unknown_live_context_preserved']['restored'],False)
                self.assertEqual(events['unknown_live_context_preserved']['code'],'recovery_required')
                inspection=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
                self.assertFalse(inspection['State']['OOMKilled'])
                self.assertEqual(inspection['HostConfig']['NetworkMode'],'none')
            finally:
                if cid:
                    info=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
                    self.assertEqual(info['Config']['Labels']['org.nfqws2.task'],task)
                    self.assertEqual(info['Name'],'/nfqws-'+task)
                    subprocess.run(['docker','rm','-f',cid],check=True,stdout=subprocess.DEVNULL)
                    self.assertNotEqual(subprocess.run(['docker','inspect',cid],capture_output=True).returncode,0)

    def test_asus_unknown_live_context_is_preserved_without_signalling(self):
        self.run_guard('asus-entware')

    def test_openwrt_unknown_live_context_is_preserved_without_signalling(self):
        self.run_guard('openwrt')
