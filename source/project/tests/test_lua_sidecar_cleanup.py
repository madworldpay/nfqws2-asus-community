"""Only newly generated, exact factory alternatives may be removed."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


class LuaSidecarCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for directory in ['factory/lua','active/lua']:(self.root/directory).mkdir(parents=True)
        for directory in self.root.rglob('*'):
            if directory.is_dir():directory.chmod(0o755)
        self.factory=self.root/'factory/lua/stock.lua';self.factory.write_bytes(b'-- signed stock\n');self.factory.chmod(0o644)
        self.copy=self.root/'active/lua/stock.lua-opkg';self.copy.write_bytes(self.factory.read_bytes());self.copy.chmod(0o644)
        self.journal=self.root/'before';self.journal.write_text('NFQWS LUA SIDECARS 1\n');self.journal.chmod(0o600)

    def call(self):
        code='''require $argv[1].'/openwrt-resource-upgrade.php';try{
        $v=NfqwsOpenWrtResourceUpgrade::cleanupOpkgSidecars($argv[2].'/before',$argv[2].'/factory',$argv[2].'/active',(int)$argv[3]);
        echo json_encode(['removed'=>$v]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([str(PHP),'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)

    def test_only_new_identical_factory_copy_is_removed(self):
        self.assertEqual(self.call(),{'removed':['stock.lua-opkg']})
        self.assertFalse(self.copy.exists());self.assertEqual(self.factory.read_bytes(),b'-- signed stock\n')
        self.assertEqual(self.call(),{'removed':[]})

    def test_preexisting_name_is_never_removed_even_when_bytes_match_factory(self):
        self.journal.write_text('NFQWS LUA SIDECARS 1\nstock.lua-opkg\n')
        saved=self.root/'stock.lua-opkg';saved.write_bytes(self.copy.read_bytes());saved.chmod(0o644)
        self.assertEqual(self.call(),{'removed':[]});self.assertTrue(self.copy.is_file())

    def test_preexisting_bytes_and_mode_are_restored_only_over_verified_factory(self):
        self.journal.write_text('NFQWS LUA SIDECARS 1\nstock.lua-opkg\n')
        saved=self.root/'stock.lua-opkg';saved.write_bytes(b'-- original alternative\n');saved.chmod(0o600)
        self.assertEqual(self.call(),{'removed':[]});self.assertEqual(self.copy.read_bytes(),saved.read_bytes())
        self.assertEqual(self.copy.stat().st_mode&0o777,0o600)
        self.assertEqual(self.call(),{'removed':[]})
        self.copy.write_bytes(b'-- concurrent owner edit\n')
        self.assertEqual(self.call(),{'error':'settings_changed'});self.assertEqual(self.copy.read_bytes(),b'-- concurrent owner edit\n')

    def test_missing_or_unsafe_backup_never_authorizes_restore_or_cleanup(self):
        self.journal.write_text('NFQWS LUA SIDECARS 1\nstock.lua-opkg\n')
        self.assertEqual(self.call(),{'error':'invalid_state'});self.assertEqual(self.copy.read_bytes(),self.factory.read_bytes())
        (self.root/'stock.lua-opkg').symlink_to(self.factory)
        self.assertEqual(self.call(),{'error':'invalid_state'});self.assertTrue(self.copy.is_file())

    def test_nonfactory_bytes_and_different_permissions_are_preserved(self):
        self.copy.write_bytes(b'-- owner content\n')
        self.assertEqual(self.call(),{'removed':[]});self.assertEqual(self.copy.read_bytes(),b'-- owner content\n')
        self.copy.write_bytes(self.factory.read_bytes());self.copy.chmod(0o600)
        self.assertEqual(self.call(),{'removed':[]});self.assertTrue(self.copy.is_file())

    def test_links_and_writable_files_are_preserved_without_touching_their_target(self):
        outside=self.root/'outside';outside.write_bytes(self.factory.read_bytes());outside.chmod(0o644)
        for kind in ['symbolic','hard','writable']:
            with self.subTest(kind=kind):
                self.copy.unlink()
                if kind=='symbolic':self.copy.symlink_to(outside)
                elif kind=='hard':os.link(outside,self.copy)
                else:self.copy.write_bytes(self.factory.read_bytes());self.copy.chmod(0o666)
                self.assertEqual(self.call(),{'removed':[]});self.assertTrue(self.copy.exists())
                self.assertEqual(outside.read_bytes(),b'-- signed stock\n')

    def test_missing_journal_does_not_infer_ownership(self):
        self.journal.unlink();self.assertEqual(self.call(),{'removed':[]});self.assertTrue(self.copy.exists())

    def test_hidden_factory_names_cannot_claim_hidden_operator_files(self):
        factory=self.root/'factory/lua/.hidden.lua';factory.write_bytes(b'-- hidden\n');factory.chmod(0o644)
        hidden=self.root/'active/lua/.hidden.lua-opkg';hidden.write_bytes(b'-- hidden\n');hidden.chmod(0o644)
        self.assertEqual(self.call(),{'removed':['stock.lua-opkg']});self.assertEqual(hidden.read_bytes(),b'-- hidden\n')

    def test_invalid_or_unprotected_journal_fails_before_removing_any_copy(self):
        for raw in ['wrong header\n','NFQWS LUA SIDECARS 1','NFQWS LUA SIDECARS 1\n../stock.lua-opkg\n',
                    'NFQWS LUA SIDECARS 1\nstock.lua-opkg\nstock.lua-opkg\n',
                    'NFQWS LUA SIDECARS 1\n'+'x.lua-opkg\n'*513]:
            with self.subTest(raw=raw[:60]):
                self.journal.write_text(raw);self.assertEqual(self.call(),{'error':'invalid_state'});self.assertTrue(self.copy.exists())
        self.journal.write_text('NFQWS LUA SIDECARS 1\n');self.journal.chmod(0o644)
        self.assertEqual(self.call(),{'error':'invalid_state'});self.assertTrue(self.copy.exists())

    def test_all_factory_proofs_are_validated_before_cleanup(self):
        (self.root/'factory/lua/unsafe.lua').symlink_to(self.factory)
        target=self.root/'active/lua/unsafe.lua-opkg';target.write_bytes(self.factory.read_bytes());target.chmod(0o644)
        self.assertEqual(self.call(),{'error':'invalid_state'});self.assertTrue(self.copy.exists());self.assertTrue(target.exists())


if __name__=='__main__':unittest.main()
