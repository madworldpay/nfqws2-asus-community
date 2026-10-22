"""A package upgrade must carry relay owner settings across old staged workers."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_package_update_guard import NATIVE

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(NATIVE.is_file(),'native PHP fixture required')
class RelayConffileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.opt=self.base/'opt';self.active=self.opt/'etc/nfqws-asus-web/support-relay.json';self.active.parent.mkdir(parents=True)
        self.template=self.opt/'share/nfqws2-asus/support-relay-default.json';self.template.parent.mkdir(parents=True)
        self.factory=(ROOT/'asus/support-relay.json').read_bytes();self.template.write_bytes(self.factory);self.template.chmod(0o644)
        (self.opt/'tmp').mkdir(mode=0o755);self.sha=hashlib.sha256(self.factory).hexdigest();self.stage=self.opt/'var/lib/nfqws2-asus/relay-config-preserve'
        self.status=self.opt/'lib/opkg/status';self.status.parent.mkdir(parents=True);
        for d in [self.opt,*self.opt.rglob('*')]:
            if d.is_dir():d.chmod(0o755)
        self.status.write_text('Package: nfqws2-asus\nVersion: 1\nStatus: install ok installed\n\n');self.status.chmod(0o600)
    def call(self,action,disable=""):
        code='''$p=$argv[1];if(!is_file($p)){echo json_encode(['error'=>'missing_relay_preserver']);exit;}require $p;
        try{$r=new AsusRelayConffile($argv[2],'1.3.1-asus6+b66',$argv[3],(int)$argv[4]);$r->{$argv[5]}();echo json_encode(['ok'=>true]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        r=subprocess.run([str(NATIVE),'-n','-d','disable_functions='+disable,'-r',code,str(ROOT/'asus/ipk/relay-config.php'),str(self.opt),self.sha,str(os.getuid()),action],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def write(self,raw):self.active.write_bytes(raw);self.active.chmod(0o600)
    def test_all_existing_choices_and_metadata_survive_factory_unpack(self):
        for raw in [b'{"enabled":false,"url":""}\n',self.factory,b'{"enabled":false,"url":"https://operator.example/nfqws-support/v1/reports"}\n',b'{"enabled":true,"url":"https://operator.example/nfqws-support/v1/reports"}\n']:
            with self.subTest(raw=raw):
                self.write(raw);before=self.active.stat();self.assertEqual(self.call('prepare'),{'ok':True})
                self.write(self.factory);self.assertEqual(self.call('finish'),{'ok':True})
                self.assertEqual(self.active.read_bytes(),raw);after=self.active.stat();self.assertEqual((after.st_mode,after.st_uid,after.st_gid),(before.st_mode,before.st_uid,before.st_gid));self.assertFalse(self.stage.exists())
                self.assertEqual(self.call('finish'),{'ok':True})
    def test_fresh_install_keeps_ready_factory_but_upgrade_preserves_absence(self):
        self.status.unlink();self.assertEqual(self.call('prepare'),{'ok':True});self.write(self.factory);self.assertEqual(self.call('finish'),{'ok':True});self.assertEqual(self.active.read_bytes(),self.factory)
        self.active.unlink();self.status.write_text('Package: nfqws2-asus\nVersion: 1\nStatus: install ok installed\n\n');self.status.chmod(0o600);self.assertEqual(self.call('prepare'),{'ok':True});self.write(self.factory);self.assertEqual(self.call('finish'),{'ok':True});self.assertFalse(self.active.exists())
    def test_embedded_hooks_run_with_all_three_matching_cgi_runtimes(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('relay_hook_builder',ROOT/'asus/build.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        old=b'{"enabled":false,"url":""}\n'
        for abi in ['aarch64','armv7','armv7-legacy']:
            with self.subTest(abi=abi):
                php=ROOT/'.work/packaging-audit-20261012'/(abi+'-cgi-wrapper');self.assertTrue(php.is_file())
                self.write(old)
                for action in ['prepare','finish']:
                    if action=='finish':self.write(self.factory)
                    script=builder.relay_preserver(action,'1.3.1-asus6+b66',opt=str(self.opt),php=str(php),owner=os.getuid(),busybox='/bin/busybox',script_parent=str(self.opt/'tmp'))
                    p=subprocess.run(['/bin/sh'],input=script,capture_output=True,timeout=10)
                    self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stdout,b'');self.assertEqual(p.stderr,b'')
                self.assertEqual(self.active.read_bytes(),old)

    def test_unexpected_edit_is_not_overwritten_or_cleaned(self):
        self.write(b'{"enabled":false,"url":""}\n');self.assertEqual(self.call('prepare'),{'ok':True});self.write(b'OWNER NEW EDIT')
        self.assertIn('error',self.call('finish'));self.assertEqual(self.active.read_bytes(),b'OWNER NEW EDIT');self.assertTrue(self.stage.exists())
    def test_stage_tampering_and_unknown_files_fail_closed(self):
        self.write(b'{"enabled":false,"url":""}\n');self.assertEqual(self.call('prepare'),{'ok':True});self.write(self.factory)
        backup=self.stage/'file';backup.write_bytes(b'TAMPERED');self.assertIn('error',self.call('finish'));self.assertEqual(self.active.read_bytes(),self.factory)
    def test_unsafe_active_stage_parent_and_factory_paths_fail_closed(self):
        outside=self.base/'outside';outside.write_bytes(b'KEEP');self.active.symlink_to(outside)
        self.assertIn('error',self.call('prepare'));self.assertEqual(outside.read_bytes(),b'KEEP');self.active.unlink()
        self.write(b'{"enabled":false,"url":""}\n');self.stage.parent.mkdir(parents=True,exist_ok=True);self.stage.symlink_to(outside)
        self.assertIn('error',self.call('prepare'));self.assertEqual(outside.read_bytes(),b'KEEP')
    def test_kernel_lease_blocks_parallel_writer_without_deleting_its_lock(self):
        import fcntl
        self.write(b'{"enabled":false,"url":""}\n');self.stage.parent.mkdir(mode=0o700,parents=True);(self.opt/'var').chmod(0o755);(self.opt/'var/lib').chmod(0o755);lock=self.stage.with_name(self.stage.name+'.lock');lock.touch(mode=0o600)
        with lock.open('r+') as held:
            fcntl.flock(held,fcntl.LOCK_EX);self.assertIn('error',self.call('prepare'));self.assertTrue(lock.exists());self.assertFalse(self.stage.exists())
        self.assertEqual(self.call('prepare'),{'ok':True})
    def test_prepare_reuses_intact_stage_after_preinstall_abort(self):
        old=b'{"enabled":false,"url":""}\n';self.write(old);self.assertEqual(self.call('prepare'),{'ok':True})
        before={p.name:(p.stat(),p.read_bytes()) for p in self.stage.iterdir()}
        self.assertEqual(self.call('prepare'),{'ok':True})
        for name,(meta,raw) in before.items():
            p=self.stage/name;self.assertEqual(p.read_bytes(),raw);self.assertEqual((p.stat().st_ino,p.stat().st_mtime_ns),(meta.st_ino,meta.st_mtime_ns))
        self.write(self.factory);self.assertEqual(self.call('finish'),{'ok':True});self.assertEqual(self.active.read_bytes(),old)
    def test_prepare_does_not_reuse_equal_bytes_from_a_replaced_inode(self):
        old=b'{"enabled":false,"url":""}\n';self.write(old);self.assertEqual(self.call('prepare'),{'ok':True})
        replacement=self.active.with_suffix('.replacement');replacement.write_bytes(old);replacement.chmod(0o600);replacement.replace(self.active)
        self.assertIn('error',self.call('prepare'));self.assertEqual(self.active.read_bytes(),old);self.assertEqual((self.stage/'file').read_bytes(),old)
    def test_prepare_reuse_rejects_equal_bytes_from_a_replaced_backup_inode(self):
        old=b'{"enabled":false,"url":""}\n';self.write(old);self.assertEqual(self.call('prepare'),{'ok':True})
        backup=self.stage/'file';replacement=self.stage/'replacement';replacement.write_bytes(old);replacement.chmod(0o600);replacement.replace(backup)
        self.assertIn('error',self.call('prepare'));self.assertIn('error',self.call('finish'));self.assertEqual(self.active.read_bytes(),old);self.assertTrue(self.stage.exists())
    def test_prepare_reuse_rejects_changed_factory_and_unknown_stage_data(self):
        self.write(b'{"enabled":false,"url":""}\n');self.assertEqual(self.call('prepare'),{'ok':True})
        metadata=self.stage/'metadata.json';original=metadata.read_bytes();value=json.loads(original);value['factory_sha256']='0'*64;metadata.write_text(json.dumps(value))
        self.assertIn('error',self.call('prepare'));self.assertEqual(metadata.read_text(),json.dumps(value))
        metadata.write_bytes(original);(self.stage/'foreign').write_text('KEEP');self.assertIn('error',self.call('prepare'));self.assertEqual((self.stage/'foreign').read_text(),'KEEP')
    def test_parallel_prepare_never_replaces_previous_backup(self):
        self.write(b'{"enabled":false,"url":""}\n');self.assertEqual(self.call('prepare'),{'ok':True});saved=(self.stage/'file').read_bytes()
        self.write(self.factory);self.assertIn('error',self.call('prepare'));self.assertEqual((self.stage/'file').read_bytes(),saved)
    def test_invalid_modes_hardlinks_and_oversized_files_are_refused(self):
        old=b'{"enabled":false,"url":""}\n';self.write(old);self.active.chmod(0o644)
        self.assertIn('error',self.call('prepare'));self.active.chmod(0o600)
        link=self.base/'second-name';os.link(self.active,link);self.assertIn('error',self.call('prepare'));link.unlink()
        self.write(b'x'*2049);self.assertIn('error',self.call('prepare'));self.assertFalse(self.stage.exists())
    def test_failed_sync_never_publishes_partial_stage_or_active_config(self):
        old=b'{"enabled":false,"url":""}\n';self.write(old)
        self.assertIn('error',self.call('prepare','fsync'));self.assertEqual(self.active.read_bytes(),old);self.assertFalse(self.stage.exists())
        self.assertEqual(self.call('prepare'),{'ok':True});self.write(self.factory)
        self.assertIn('error',self.call('finish','fsync'));self.assertEqual(self.active.read_bytes(),self.factory);self.assertTrue(self.stage.exists())
        self.assertEqual(self.call('finish'),{'ok':True});self.assertEqual(self.active.read_bytes(),old)
    def test_writable_ancestor_is_refused_even_with_private_leaf(self):
        self.write(b'{"enabled":false,"url":""}\n');self.assertEqual(self.call('prepare'),{'ok':True});self.write(self.factory);(self.opt/'var').chmod(0o777)
        self.assertIn('error',self.call('finish'));self.assertEqual(self.active.read_bytes(),self.factory)
    def test_stage_version_is_refused(self):
        old=b'{"enabled":false,"url":""}\n';self.write(old);self.assertEqual(self.call('prepare'),{'ok':True});self.write(self.factory)
        meta=self.stage/'metadata.json';value=json.loads(meta.read_text());value['version']='1.3.1-asus6+b67';meta.write_text(json.dumps(value));self.assertIn('error',self.call('finish'));self.assertEqual(self.active.read_bytes(),self.factory)

    def test_invalid_factory_and_unknown_stage_member_are_preserved(self):
        self.write(b'{"enabled":false,"url":""}\n');self.assertEqual(self.call('prepare'),{'ok':True});self.write(self.factory);self.template.write_bytes(b'INVALID')
        self.assertIn('error',self.call('finish'));self.assertEqual(self.active.read_bytes(),self.factory)
        self.template.write_bytes(self.factory);(self.stage/'foreign').write_text('KEEP');self.assertIn('error',self.call('finish'));self.assertEqual((self.stage/'foreign').read_text(),'KEEP')

if __name__=='__main__':unittest.main()
