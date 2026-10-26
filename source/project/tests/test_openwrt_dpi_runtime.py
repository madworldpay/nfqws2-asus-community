"""Real native BusyBox guardian, privilege drop and bounded process lifetime."""
import json,os,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTAINER=os.environ.get('NFQWS_TEST_DOCKER')

@unittest.skipUnless(CONTAINER,'Requires isolated OpenWrt rootfs')
class NativeDpiGuardian(unittest.TestCase):
 def sh(self,script,input=None,timeout=20):
  return subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',script],input=input,text=True,capture_output=True,timeout=timeout)
 def case(self,mode):
  spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
  self.assertTrue(CONTAINER.startswith('nfqws-openwrt'));self.assertNotEqual(spec['HostConfig']['NetworkMode'],'host')
  base='/tmp/nfqws-native-guardian-'+mode;job='a'*32;run=base+'/state/runs/'+job
  self.sh('rm -rf '+base+'; mkdir -p '+run+' '+base+'/scripts; chmod 755 '+base+'; chmod 700 '+run)
  for name in ['guard.sh','probe.sh','drop.sh','stop.sh']:
   self.sh('cat > '+base+'/scripts/'+name,input=(ROOT/'asus/dpi'/name).read_text())
  module=ROOT/'openwrt/dpi-paths.sh'
  self.assertTrue(module.exists(),'native guardian path contract missing')
  paths=module.read_text().replace('/tmp/nfqws2-native-state/dpi-detector',base+'/state').replace('/usr/lib/nfqws2/dpi',base+'/scripts').replace('/usr/bin/php-cgi',base+'/worker')
  self.sh('cat > '+base+'/scripts/paths.sh',input=paths)
  self.sh('cat > '+base+'/worker',input='#!/bin/sh\necho $$ > '+base+'/worker.pid\nwhile :; do sleep 1; done\n')
  self.sh('chmod 755 '+base+'/worker; chmod 644 '+base+'/scripts/*')
  self.sh('cat > '+run+'/args',input='/bin/busybox\nsh\n-c\ncat /proc/self/status; trap "" TERM; exec sleep 30\n')
  r=self.sh('awk \'{printf "%.3f\\n",$1+'+('3'if mode=='deadline'else'15')+'}\' /proc/uptime > '+run+'/deadline; printf / > '+run+'/probe.cwd; printf ready > '+run+'/probe.request; /bin/busybox start-stop-daemon -S -b -p '+run+'/unused-guard.pid -x /bin/busybox -- sh '+base+'/scripts/guard.sh '+job)
  self.assertEqual(r.returncode,0,r.stderr)
  try:
   r=self.sh('n=0; while ! test -s '+run+'/g0.stdout && test "$n" -lt 5; do sleep 1; n=$((n+1)); done; cat '+run+'/g0.stdout; cat '+run+'/probe.pid')
   self.assertEqual(r.returncode,0,r.stderr);self.assertIn('Uid:\t65534\t65534\t65534\t65534',r.stdout)
   for cap in ['CapInh','CapPrm','CapEff','CapAmb']:self.assertRegex(r.stdout,cap+r':\s+0+\n')
   if mode=='cancel':self.sh('touch '+run+'/cancel')
   if mode=='workerdeath':self.sh('read pid < '+base+'/worker.pid; kill -KILL "$pid"')
   r=self.sh('n=0; while ! test -s '+run+'/outcome && test "$n" -lt 9; do sleep 1; n=$((n+1)); done; cat '+run+'/outcome; read pid start < '+run+'/probe.pid; if test -f /proc/$pid/stat; then read line < /proc/$pid/stat; rest=${line##*) }; set -- $rest; test "$1" = Z || exit 91; fi; test ! -e '+run+'/g0.stdout')
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   self.assertEqual(r.stdout.strip(),{'cancel':'cancelled','deadline':'timed_out','workerdeath':'interrupted'}[mode])
  finally:self.sh('test ! -s '+run+'/guard.pid || { read pid start < '+run+'/guard.pid; kill -TERM "$pid" 2>/dev/null; }; :')
 def test_native_cancel_drops_privileges_and_stops_child(self):self.case('cancel')
 def test_native_deadline_drops_privileges_and_stops_child(self):self.case('deadline')
 def test_native_worker_death_stops_child(self):self.case('workerdeath')
