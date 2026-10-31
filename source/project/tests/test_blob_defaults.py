"""Real BusyBox lifecycle: owner blobs survive unpack and stock bytes seed once."""
import hashlib,os,shlex,shutil,stat,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BUSYBOX=Path(os.environ.get('MIGRATION_BUSYBOX_TEST_BINARY','/bin/busybox'))

@unittest.skipUnless(BUSYBOX.exists(),'real BusyBox required')
class BlobDefaultsTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name);self.opt=self.base/'opt';self.active=self.opt/'etc/nfqws2/blobs';self.active.mkdir(parents=True);self.stock=self.opt/'share/nfqws2-asus/defaults/blobs';self.stock.mkdir(parents=True)
  self.state=self.opt/'etc/nfqws2-asus-migration';self.state.mkdir(mode=0o700);(self.state/'defaults-initialized').write_bytes(b'previous marker\n');self.config=self.opt/'etc/nfqws2/nfqws2.conf';self.config.write_bytes(b'OWNER_CONFIG\n');self.lists=self.opt/'etc/nfqws2/lists';self.lists.mkdir();(self.lists/'user.list').write_bytes(b'OWNER_LIST\n')
  self.blobs={f'example-{i:02}.bin':bytes([i,255,0,128])+b'stock' for i in range(12)}
  for name,data in self.blobs.items():p=self.stock/name;p.write_bytes(data);p.chmod(0o644)
  self.private=self.opt/'libexec/nfqws2-asus/busybox';self.private.parent.mkdir(parents=True);shutil.copyfile(BUSYBOX,self.private);self.private.chmod(0o755)
  for path in self.opt.rglob('*'):
   if path.is_dir() and path!=self.state:path.chmod(0o755)
  self.opt.chmod(0o755)
 def code(self):
  return '\n'.join((ROOT/'asus/ipk'/p).read_text().replace('/opt/',str(self.opt)+'/').replace('ASUS_MIGRATION_OWNER=0','ASUS_MIGRATION_OWNER='+str(os.getuid())) for p in ['migration.sh','defaults.sh'])
 def call(self,action='seed',prefix='',postinst=False):
  commands={'save':'asus_migration_save','restore':'asus_migration_restore','seed':'asus_install_blob_defaults','upgrade':'asus_migration_restore && asus_install_defaults && asus_install_blob_defaults','complete':'asus_migration_complete'}
  body=self.code()+'\n'+prefix+'\n'+((ROOT/'asus/ipk/unified-postinst').read_text().replace('/opt/',str(self.opt)+'/') if postinst else commands[action])
  return subprocess.run([str(BUSYBOX),'sh','-c',body],capture_output=True,text=True,env=os.environ|{'NFQWS_ASUS_NO_START':'1'},timeout=10)
 def ok(self,r):self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def unchanged_settings(self):self.assertEqual(self.config.read_bytes(),b'OWNER_CONFIG\n');self.assertEqual((self.lists/'user.list').read_bytes(),b'OWNER_LIST\n')
 def test_stock_blobs_seed_on_existing_defaults_marker_without_overwriting_owner_bytes(self):
  p=self.active/'example-00.bin';p.write_bytes(b'OWNER_BLOB\x00\xff');p.chmod(0o600);before=p.stat();self.ok(self.call());self.assertEqual(len(list(self.active.iterdir())),12);self.assertEqual(p.read_bytes(),b'OWNER_BLOB\x00\xff');self.assertEqual(p.stat().st_ino,before.st_ino);self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
  for name,data in self.blobs.items():
   if name!='example-00.bin':self.assertEqual((self.active/name).read_bytes(),data);self.assertEqual((self.active/name).stat().st_nlink,1)
  self.unchanged_settings();self.ok(self.call());self.assertEqual(p.stat().st_ino,before.st_ino)
 def test_snapshot_restores_modified_legacy_package_blob_after_payload_removal(self):
  p=self.active/'tls_clienthello.bin';p.write_bytes(b'OWNER_TLS\x00\xff');p.chmod(0o600);self.ok(self.call('save'));snapshot=self.state/'snapshot';self.assertTrue((snapshot/'blobs/tls_clienthello.bin').exists());self.assertEqual((snapshot/'blobs/tls_clienthello.bin').read_bytes(),p.read_bytes());p.unlink();self.ok(self.call('upgrade'));self.assertEqual(p.read_bytes(),b'OWNER_TLS\x00\xff');self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600);self.unchanged_settings()
 def test_missing_active_directory_is_created_and_existing_modes_are_preserved(self):
  self.active.rmdir();mode=self.active.parent.stat().st_mode;self.ok(self.call());self.assertEqual(len(list(self.active.iterdir())),12);self.assertEqual(self.active.parent.stat().st_mode,mode);self.unchanged_settings()
 def test_source_and_destination_links_special_files_and_hardlinks_fail_closed(self):
  outside=self.base/'private';outside.write_bytes(b'PRIVATE_CANARY')
  for where in [self.stock,self.active]:
   for kind in ['symlink','hardlink','fifo']:
    with self.subTest(where=where,kind=kind):
     p=where/'unsafe.bin'
     if kind=='symlink':p.symlink_to(outside)
     elif kind=='hardlink':os.link(outside,p)
     else:os.mkfifo(p)
     r=self.call();self.assertNotEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(outside.read_bytes(),b'PRIVATE_CANARY');p.unlink()
  self.unchanged_settings()
 def test_symlink_resource_directory_is_rejected_without_following_it(self):
  outside=self.base/'outside';outside.mkdir();self.active.rmdir();self.active.symlink_to(outside,target_is_directory=True);self.assertNotEqual(self.call().returncode,0);self.assertEqual(list(outside.iterdir()),[])
 def test_snapshot_rejects_unsafe_blob_nodes_before_copy(self):
  outside=self.base/'private';outside.write_bytes(b'PRIVATE_CANARY')
  for kind in ['symlink','hardlink','fifo']:
   with self.subTest(kind=kind):
    p=self.active/'unsafe.bin'
    if kind=='symlink':p.symlink_to(outside)
    elif kind=='hardlink':os.link(outside,p)
    else:os.mkfifo(p)
    r=self.call('save');self.assertNotEqual(r.returncode,0);self.assertFalse((self.state/'snapshot').exists());self.assertEqual(outside.read_bytes(),b'PRIVATE_CANARY');p.unlink()
    for stage in self.state.glob('stage.*'):shutil.rmtree(stage)
 def test_interrupted_stock_copy_publishes_no_partial_file_and_retry_succeeds(self):
  prefix='''asus_migration_cmd() {
  if [ "$1" = cp ] && [ ! -f '''+shlex.quote(str(self.base/'failed-once'))+''' ]; then
    local last arg
    for arg; do last=$arg; done
    printf PARTIAL > "$last"
    printf failed > '''+shlex.quote(str(self.base/'failed-once'))+'''
    return 1
  fi
  "$ASUS_MIGRATION_BUSYBOX" "$@"
}'''
  r=self.call(prefix=prefix);self.assertNotEqual(r.returncode,0);self.assertFalse(any(p.is_file() for p in self.active.glob('*.bin')));self.ok(self.call(prefix=prefix));self.assertEqual(len(list(self.active.glob('*.bin'))),12);self.assertEqual(list(self.active.glob('.nfqws2-default.*')),[])
 def test_postinst_restores_then_seeds_before_starting_the_web(self):
  p=self.active/'owner.bin';p.write_bytes(b'OWNER_BLOB');self.ok(self.call('save'));p.unlink();service=self.opt/'etc/init.d/S81nfqws-asus-web';service.parent.mkdir(parents=True);service.write_text('#!/bin/sh\n[ "$(cat '+shlex.quote(str(p))+')" = OWNER_BLOB ] && [ -f '+shlex.quote(str(self.active/'example-11.bin'))+' ]\n');service.chmod(0o755);self.ok(self.call(postinst=True));self.assertEqual(p.read_bytes(),b'OWNER_BLOB');self.unchanged_settings()
 def legacy_snapshot(self,complete=False):
  self.ok(self.call('save'));snapshot=self.state/'snapshot';shutil.rmtree(snapshot/'blobs');p=snapshot/'presence';p.write_bytes(b''.join(line for line in p.read_bytes().splitlines(keepends=True) if not line.startswith(b'blobs ')))
  rows=[]
  for f in sorted(snapshot.rglob('*')):
   if f.is_file() and f.name!='manifest':rows.append(hashlib.sha256(f.read_bytes()).hexdigest()+'  ./'+f.relative_to(snapshot).as_posix()+'\n')
  (snapshot/'manifest').write_text(''.join(rows))
  if complete:
   for name in ['data-restored','complete']:(self.state/name).write_text('previous release\n');(self.state/name).chmod(0o600)
 def test_completed_legacy_snapshot_still_captures_owner_blobs_before_unpack(self):
  p=self.active/'tls_clienthello.bin';p.write_bytes(b'OWNER_TLS');p.chmod(0o600);self.legacy_snapshot(complete=True);self.config.write_bytes(b'LATEST_OWNER_CONFIG\n');self.ok(self.call('save'));p.unlink();self.ok(self.call('upgrade'));self.assertTrue(p.is_file(),'legacy owner blob was not recovered');self.assertEqual(p.read_bytes(),b'OWNER_TLS');self.assertEqual(self.config.read_bytes(),b'LATEST_OWNER_CONFIG\n');self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
 def test_pending_legacy_snapshot_keeps_its_config_recovery_and_adds_blob_recovery(self):
  p=self.active/'tls_clienthello.bin';p.write_bytes(b'OWNER_TLS');self.legacy_snapshot();self.config.write_bytes(b'PARTIAL_UNPACK\n');before=(self.state/'snapshot/config').read_bytes();self.ok(self.call('save'));p.unlink();self.ok(self.call('upgrade'));self.assertTrue(p.is_file(),'legacy owner blob was not recovered');self.assertEqual(p.read_bytes(),b'OWNER_TLS');self.assertEqual(self.config.read_bytes(),before)
 def test_legacy_blob_restore_retry_preserves_owner_edit_after_checkpoint(self):
  p=self.active/'tls_clienthello.bin';p.write_bytes(b'OWNER_TLS');self.legacy_snapshot(complete=True);self.ok(self.call('save'));p.unlink();self.ok(self.call('upgrade'));self.assertTrue(p.is_file(),'legacy owner blob was not recovered');p.write_bytes(b'OWNER_CHANGED_AFTER_RESTORE');self.ok(self.call('save'));self.ok(self.call('upgrade'));self.assertEqual(p.read_bytes(),b'OWNER_CHANGED_AFTER_RESTORE')
 def test_crash_after_default_link_reclaims_only_private_stage_and_keeps_published_inode(self):
  stage=self.active/'.nfqws2-default.ABCDEF';stage.mkdir(mode=0o700);f=stage/'file';f.write_bytes(b'ALREADY_PUBLISHED_OWNER_BYTES');f.chmod(0o644);target=self.active/'example-00.bin';os.link(f,target);before=target.stat();self.assertEqual(before.st_nlink,2)
  self.ok(self.call());self.assertFalse(stage.exists());self.assertEqual(target.read_bytes(),b'ALREADY_PUBLISHED_OWNER_BYTES');self.assertEqual(target.stat().st_ino,before.st_ino);self.assertEqual(target.stat().st_nlink,1);self.assertEqual(len(list(self.active.iterdir())),12)
 def test_legacy_side_snapshot_tamper_is_rejected_before_payload_can_be_removed(self):
  p=self.active/'tls_clienthello.bin';p.write_bytes(b'OWNER_TLS');self.legacy_snapshot(complete=True);self.ok(self.call('save'));journal=self.state/'blob-snapshot';self.assertTrue(journal.is_dir());(journal/'blobs/tls_clienthello.bin').write_bytes(b'TAMPERED');self.assertNotEqual(self.call('save').returncode,0);self.assertEqual(p.read_bytes(),b'OWNER_TLS')

 def test_writable_destination_parent_is_rejected_without_global_permission_changes(self):
  parent=self.active.parent;parent.chmod(0o777);self.assertNotEqual(self.call().returncode,0);self.assertEqual(stat.S_IMODE(parent.stat().st_mode),0o777);self.assertEqual(list(self.active.iterdir()),[])
 def test_legacy_snapshot_without_any_blob_entry_remains_directly_restorable(self):
  self.legacy_snapshot();self.config.write_bytes(b'PARTIAL_UNPACK\n');self.ok(self.call('restore'));self.assertEqual(self.config.read_bytes(),b'OWNER_CONFIG\n');self.assertFalse((self.state/'blob-snapshot').exists())
 def test_unowned_or_external_hardlink_cannot_masquerade_as_a_default_stage(self):
  outside=self.base/'outside';outside.write_bytes(b'PRIVATE_CANARY');stage=self.active/'.nfqws2-default.ABCDEF';stage.mkdir(mode=0o700);os.link(outside,stage/'file');self.assertNotEqual(self.call().returncode,0);self.assertEqual(outside.read_bytes(),b'PRIVATE_CANARY');self.assertTrue((stage/'file').exists());self.assertEqual(list(self.active.glob('*.bin')),[])
