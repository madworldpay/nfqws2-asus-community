"""Real opkg drops legacy package-owned blobs; journal restores owner bytes first."""
import hashlib,os,shlex,stat,subprocess,tempfile,unittest
from pathlib import Path
import test_migration as migration_tests
ROOT=migration_tests.ROOT
OPKG=migration_tests.OPKG
BUSYBOX=migration_tests.BUSYBOX

@unittest.skipUnless(OPKG.exists() and BUSYBOX.exists(),'matching opkg and BusyBox required')
class BlobOpkgUpgradeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name);self.root=self.base/'root';self.opt=self.root/'opt';self.opt.mkdir(parents=True);(self.opt/'tmp').mkdir();(self.base/'tmp').mkdir();conf=self.base/'opkg.conf';conf.write_text('dest root /\narch aarch64-3.10 10\n');self.command=[str(OPKG),'-f',str(conf),'-o',str(self.root),'--force-postinstall','--tmp-dir',str(self.base/'tmp')]
  self.names=['tls_clienthello.bin','quic_initial.bin']+[f'example-{i:02}.bin' for i in range(10)];self.stock={name:bytes([i,255,0])+b'STOCK' for i,name in enumerate(self.names)};self.owner={name:b'OWNER-'+name.encode()+b'\x00\xff' for name in self.names[:2]}
 def run_opkg(self,*args):
  r=subprocess.run(self.command+list(map(str,args)),capture_output=True,text=True,env=os.environ|{'NFQWS_ASUS_NO_START':'1'},timeout=20);self.assertEqual(r.returncode,0,r.stdout+r.stderr);return r
 def package(self,legacy=False):
  version='1.3.1-asus6+b'+('75' if legacy else '76');payload={'opt/libexec/nfqws2-asus/busybox':(BUSYBOX.read_bytes(),0o755)};controls={'control':(f'Package: nfqws2-asus\nVersion: {version}\nArchitecture: aarch64-3.10\nDescription: blob ownership transition\n'.encode(),0o644),'conffiles':(b'',0o644)}
  for name in ['preinst','postinst','prerm','postrm']:controls[name]=(b'#!/bin/sh\nexit 0\n',0o755)
  if legacy:
   payload.update({'opt/etc/nfqws2/blobs/'+name:(self.stock[name],0o644) for name in self.names[:2]})
  else:
   payload.update({'opt/share/nfqws2-asus/defaults/blobs/'+name:(raw,0o644) for name,raw in self.stock.items()});payload['opt/etc/init.d/S81nfqws-asus-web']=(b'#!/bin/sh\nexit 0\n',0o755)
   migration=(ROOT/'asus/ipk/migration.sh').read_text().replace('/opt/',str(self.opt)+'/').replace('ASUS_MIGRATION_OWNER=0','ASUS_MIGRATION_OWNER='+str(os.getuid()));defaults=(ROOT/'asus/ipk/defaults.sh').read_text().replace('/opt/',str(self.opt)+'/');postinst=(ROOT/'asus/ipk/unified-postinst').read_text().replace('/opt/',str(self.opt)+'/')
   controls['preinst']=(('#!/bin/sh\n'+migration+'\nasus_migration_save || exit $?\n').encode(),0o755);controls['postinst']=(('#!/bin/sh\n'+migration+'\n'+defaults+'\n'+postinst).encode(),0o755)
  out=self.base/(version+'.ipk');out.write_bytes(migration_tests.b.compressed_tar({'debian-binary':(b'2.0\n',0o644),'control.tar.gz':(migration_tests.b.compressed_tar(controls),0o644),'data.tar.gz':(migration_tests.b.compressed_tar(payload),0o644)}));return out
 def prepare_owner(self):
  self.run_opkg('install',self.package(True));self.blobs=self.opt/'etc/nfqws2/blobs'
  for name,raw in self.owner.items():p=self.blobs/name;p.write_bytes(raw);p.chmod(0o600)
  (self.blobs/'custom.bin').write_bytes(b'CUSTOM\x00\xff');self.config=self.opt/'etc/nfqws2/nfqws2.conf';self.config.write_bytes(b'OWNER_CONFIG\n');lists=self.config.parent/'lists';lists.mkdir();(lists/'user.list').write_bytes(b'OWNER_LIST\n')
 def assert_owner(self):
  for name,raw in self.owner.items():p=self.blobs/name;self.assertEqual(p.read_bytes(),raw);self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600);self.assertEqual(p.stat().st_nlink,1)
  self.assertEqual((self.blobs/'custom.bin').read_bytes(),b'CUSTOM\x00\xff');self.assertEqual(self.config.read_bytes(),b'OWNER_CONFIG\n');self.assertEqual((self.config.parent/'lists/user.list').read_bytes(),b'OWNER_LIST\n');self.assertEqual(len(list(self.blobs.glob('*.bin'))),13)
 def test_build75_active_package_blobs_move_to_unowned_seeded_resources(self):
  self.prepare_owner();new=self.package();self.run_opkg('install',new);self.assert_owner();listed=self.run_opkg('files','nfqws2-asus').stdout;self.assertNotIn('/opt/etc/nfqws2/blobs/',listed);self.assertIn('/opt/share/nfqws2-asus/defaults/blobs/',listed)
  self.run_opkg('remove','nfqws2-asus');self.assert_owner();self.run_opkg('install',new);self.assert_owner()
 def test_completed_old_journal_without_blobs_does_not_lose_modified_package_files(self):
  self.prepare_owner();state=self.opt/'etc/nfqws2-asus-migration';snapshot=state/'snapshot';snapshot.mkdir(parents=True,mode=0o700);state.chmod(0o700);(snapshot/'config').write_bytes(b'OLDER_OWNER_CONFIG\n');(snapshot/'presence').write_bytes(b'config present\nlists absent\nauth absent\nark absent\n')
  (snapshot/'manifest').write_text(''.join(hashlib.sha256((snapshot/name).read_bytes()).hexdigest()+'  ./'+name+'\n' for name in ['config','presence']))
  for name in ['complete','data-restored','defaults-initialized']:(state/name).write_bytes(b'old release\n');(state/name).chmod(0o600)
  self.run_opkg('install',self.package());self.assert_owner();self.assertTrue((state/'blob-snapshot/restored').is_file());self.assertEqual((snapshot/'config').read_bytes(),b'OLDER_OWNER_CONFIG\n')
