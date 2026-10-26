"""Native bootstrap provisioning refuses unfinished system state and non-install plans."""
import os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class NativeInstallShell(unittest.TestCase):
 def call(self,body,stdin=''):
  module=ROOT/'openwrt/install-shell.sh';self.assertTrue(module.is_file(),'Native bootstrap needs bounded signed-feed and install-only prerequisite helpers')
  return subprocess.run(['sh','-c',module.read_text()+'\n'+body],input=stdin,text=True,capture_output=True,timeout=10)
 def test_healthy_native_flags_pass_and_foreign_incomplete_rows_cannot_be_autoconfigured(self):
  with tempfile.TemporaryDirectory()as td:
   path=Path(td)/'db'
   for fmt,records in [('ipk',[("Package: libc\nStatus: install hold installed\n",0),("Package: libc\nStatus: install prefer,user installed\n",0),("Package: libc\nStatus: install user unpacked\n",1),("Package: libc\nStatus: install user installed\n\nPackage: nfqws2-native\nStatus: install user unpacked\n",0)]),('apk',[("P:libc\nV:1\nf:S\n",0),("P:libc\nV:1\nf:s\n",1),("P:libc\nV:1\nf:S\n\nP:nfqws2-native\nV:1\nf:s\n",0)])]:
    for text,want in records:
     with self.subTest(fmt=fmt,text=text):
      path.write_text(text);p=self.call('nfqws_native_database_safe '+fmt+' '+str(path));self.assertEqual(p.returncode,want,p.stdout+p.stderr)
 def test_only_existing_signed_opkg_feed_configuration_is_accepted(self):
  with tempfile.TemporaryDirectory()as td:
   p=Path(td)/'opkg.conf'
   for value,want in [('option check_signature\n',0),('option check_signature 1\n',0),('# option check_signature\n',1),('option check_signature 0\n',1),('option check_signature\noption check_signature 0\n',1)]:
    p.write_text(value);r=self.call('nfqws_native_signed_config '+str(p));self.assertEqual(r.returncode,want,r.stdout+r.stderr)
 def test_dependency_provisioning_cannot_upgrade_remove_or_reinstall_existing_packages(self):
  for fmt,raw,want in [('ipk','',1),('apk','',1),('ipk','Installing php8-cgi (8.3.36-r1) to root...\n',0),('ipk','Upgrading php8-cgi on root from 8.3.35 to 8.3.36...\n',1),('ipk','Removing package dnsmasq from root...\n',1),('apk','(1/1) Installing php8-cgi (8.4.27-r1)\nOK: 30.0 MiB in 40 packages\n',0),('apk','(1/1) Upgrading libc (1.2.5 -> 1.2.6)\nOK: 30.0 MiB in 40 packages\n',1),('apk','(1/1) Reinstalling php8-cgi (8.4.27-r1)\n',1),('apk','(1/1) Removing firewall4 (1)\n',1)]:
   with self.subTest(fmt=fmt,raw=raw):
    p=self.call('nfqws_native_install_only_plan '+fmt,raw);self.assertEqual(p.returncode,want,p.stdout+p.stderr)
if __name__=='__main__':unittest.main()
