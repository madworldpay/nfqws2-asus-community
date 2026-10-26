"""Ordinary native service operations retain SH through the whole mutation."""
import fcntl,os,shlex,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class NativeServiceLease(unittest.TestCase):
 def setUp(self):
  source=ROOT/'openwrt/update/service-lease.sh';self.assertTrue(source.exists(),'native service lease wrapper missing')
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.lock=self.base/'apply.lock';self.lock.touch(mode=0o600)
  php=self.base/'php';php.write_text('#!/bin/sh\nfor arg do previous=$last; last=$arg; done\ncase "$previous:$last" in authorize:*) test -f '+shlex.quote(str(self.base/'authorized'))+';; *:init) exit 0;; check:*) test ! -f '+shlex.quote(str(self.base/'manual-busy'))+';; *) exit 1;; esac\n');php.chmod(0o700)
  self.guard=self.base/'guard.sh';self.guard.write_text(source.read_text().replace('/usr/bin/php8-cgi',str(php)).replace('/tmp/nfqws2-native-state/updates/apply.lock',str(self.lock)).replace('/usr/bin/flock',shutil.which('flock')))
 def script(self,tail='echo entered',component='core',action='start'):
  return '. '+shlex.quote(str(self.guard))+'\nnfqws_native_update_enter '+component+' '+action+' || exit $?\n'+tail
 def test_shared_lease_stays_held_until_the_whole_service_caller_exits(self):
  p=subprocess.Popen(['sh','-c',self.script('echo entered; sleep .3')],stdout=subprocess.PIPE,text=True)
  try:
   self.assertEqual(p.stdout.readline().strip(),'entered')
   with self.lock.open('r+')as f:
    with self.assertRaises(BlockingIOError):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
   self.assertEqual(p.wait(timeout=2),0)
   with self.lock.open('r+')as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  finally:
   if p.poll()is None:p.kill();p.wait()
   p.stdout.close()
 def test_active_update_blocks_start_stop_reload_and_firewall_before_mutation(self):
  with self.lock.open('r+')as f:
   fcntl.flock(f,fcntl.LOCK_EX)
   for component,action in [('core','start'),('core','stop'),('core','reload'),('core','firewall'),('core','remove-firewall'),('web','restart')]:
    with self.subTest(component=component,action=action):
     p=subprocess.run(['sh','-c',self.script(component=component,action=action)],env={**os.environ,'NFQWS_UPDATE_ALLOWED':'1'},text=True,capture_output=True,timeout=2);self.assertNotEqual(p.returncode,0);self.assertNotIn('entered',p.stdout)
 def test_live_manual_manager_is_refused_even_when_os_lease_is_free(self):
  (self.base/'manual-busy').touch();p=subprocess.run(['sh','-c',self.script()],text=True,capture_output=True,timeout=2);self.assertNotEqual(p.returncode,0);self.assertNotIn('entered',p.stdout)
  with self.lock.open('r+')as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 def test_only_private_process_authorization_can_bypass_exclusive_lease(self):
  (self.base/'authorized').touch()
  with self.lock.open('r+')as f:
   fcntl.flock(f,fcntl.LOCK_EX);p=subprocess.run(['sh','-c',self.script()],text=True,capture_output=True,timeout=2);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.strip(),'entered')
if __name__=='__main__':unittest.main()
