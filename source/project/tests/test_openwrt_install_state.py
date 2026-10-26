import json,os,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.environ.get('PHP_TEST_BINARY'),'Requires matching PHP')
class NativeInstallState(unittest.TestCase):
 def test_absent_healthy_unfinished_and_broken_native_packages_remain_distinct(self):
  p=subprocess.run([os.environ['PHP_TEST_BINARY'],'-n','-f',str(ROOT/'tests/test_openwrt_install_state.php')],text=True,capture_output=True,timeout=10)
  self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');self.assertIn('PASS:',p.stdout)
 @unittest.skipUnless(os.environ.get('NFQWS_TEST_DOCKER'),'Requires isolated native database')
 def test_reading_actual_native_inventory_does_not_mutate_it_or_invent_an_installation(self):
  container=os.environ['NFQWS_TEST_DOCKER'];spec=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
  self.assertTrue(container.startswith('nfqws-openwrt'));self.assertNotEqual(spec['HostConfig']['NetworkMode'],'host')
  code='require $argv[1];$e=NfqwsOpenWrtUpdateEnvironment::firmware(file_get_contents("/etc/openwrt_release"));$before=NfqwsOpenWrtUpdateManager::raw($e);$own=NfqwsOpenWrtInstallState::read($e);if($before!==NfqwsOpenWrtUpdateManager::raw($e))throw new RuntimeException("read-only state changed native database");echo json_encode($own);'
  p=subprocess.run(['docker','exec',container,'php-cli','-r',code,str(ROOT/'openwrt/install-state.php')],capture_output=True,text=True,timeout=10)
  self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');self.assertIsNone(json.loads(p.stdout),'Refusing an already installed native package in this fixture')
if __name__=='__main__':unittest.main()
