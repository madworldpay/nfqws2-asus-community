"""Native bootstrap managers survive loss of the controlling SSH shell."""
import os,shlex,signal,subprocess,time,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
C=os.environ.get('NFQWS_TEST_DOCKER')
@unittest.skipUnless(C,'Requires native BusyBox rootfs')
class BootstrapDetach(unittest.TestCase):
 def test_detached_command_survives_hup_and_records_real_status_without_timeout(self):
  source=(ROOT/'openwrt/install-shell.sh').read_text();self.assertIn('nfqws_native_background()',source,'Native bootstrap needs a detached manager runner, not nohup which OpenWrt omits')
  base='/tmp/native-detach-'+uuid.uuid4().hex
  def sh(code):return subprocess.run(['docker','exec',C,'sh','-c',code],text=True,capture_output=True,timeout=10)
  self.assertEqual(sh('umask 077; mkdir '+base).returncode,0);self.addCleanup(lambda:sh('rm -rf '+base))
  code=source+'\nNFQWS_NATIVE_WORK='+shlex.quote(base)+'\nprintf "%s\\n" "$$" > '+base+'/parent\nnfqws_native_background /bin/sh -c '+shlex.quote('sleep 2; echo finished > '+base+'/marker; exit 7')+'\n'
  p=subprocess.Popen(['docker','exec','-i',C,'sh'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);p.stdin.write(code);p.stdin.close()
  for _ in range(100):
   if sh('test -f '+base+'/job.pid').returncode==0:break
   time.sleep(.03)
  parent=sh('cat '+base+'/parent').stdout.strip();self.assertTrue(parent.isdigit());sh('kill -HUP '+parent)
  for _ in range(150):
   if sh('test -f '+base+'/job.status').returncode==0:break
   time.sleep(.03)
  self.assertEqual(sh('cat '+base+'/marker').stdout,'finished\n');self.assertEqual(sh('cat '+base+'/job.status').stdout.strip(),'7');p.wait(timeout=10);p.stdout.close();p.stderr.close()
if __name__=='__main__':unittest.main()
