"""A private old-payload archive is restored by real opkg, never by rewriting its DB."""
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import unittest
import shutil
import test_package_update_apply as apply_fixtures

from test_dpi_normalize import PHP, PUBLIC, ROOT

OPKG = ROOT / '.work/packaging-audit-20261012/opkg-x64'


@unittest.skipUnless(OPKG.is_file(), 'actual Entware opkg fixture required')
class PackageRollbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.opt = self.base/'opt'
        (self.opt/'tmp').mkdir(parents=True)
        self.config = self.base/'opkg.conf'; self.config.write_text('dest root /\narch all 100\n')
        self.snapshot = self.base/'rollback'; self.settings = self.base/'settings'
        self.status = self.opt/'lib/opkg/status'
        self.package(self.base/'old.ipk', 80, b'old executable\n')
        self.assertEqual(self.opkg(self.base/'old.ipk').returncode, 0)
        self.owned = self.opt/'usr/bin/nfqws2'
        self.settings_file = self.opt/'etc/nfqws2/nfqws2.conf'
        self.settings_file.write_text('OWNER CONFIG\n'); self.settings_file.chmod(0o600)
        self.call('settings')

    def section(self, values):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz', format=tarfile.USTAR_FORMAT) as out:
            for path in sorted({str(parent) for name in values for parent in Path(name).parents if str(parent) != '.'}):
                member = tarfile.TarInfo(path+'/'); member.type = tarfile.DIRTYPE; member.mode = 0o755; out.addfile(member)
            for name, (raw, mode) in values.items():
                member = tarfile.TarInfo(name); member.size = len(raw); member.mode = mode; out.addfile(member, io.BytesIO(raw))
        return stream.getvalue()

    def package(self, path, build, binary, extras=None):
        control = f'Package: nfqws2-asus\nVersion: 1.3.2-asus6+b{build}\nArchitecture: all\nDescription: rollback fixture\n'.encode()
        files = {'opt/usr/bin/nfqws2': (binary, 0o755), 'opt/etc/nfqws2/nfqws2.conf': (b'factory\n', 0o600)}
        files.update(extras or {})
        if build == 81: files['opt/share/new-only'] = (b'new-only\n', 0o644)
        # ASUS creates active core settings separately; they are not opkg
        # conffiles. The real auth/relay bookkeeping has its own regression.
        path.write_bytes(self.section({'debian-binary': (b'2.0\n', 0o644), 'control.tar.gz': (self.section({'control': (control, 0o644), 'postinst': (b'#!/bin/sh\nexit 0\n', 0o755)}), 0o644), 'data.tar.gz': (self.section(files), 0o644)}))

    def opkg(self, package, umask=0o022):
        return subprocess.run([str(OPKG), '-f', str(self.config), '-o', str(self.base), '--tmp-dir', str(self.opt/'tmp'), '--force-postinstall', '--nodeps', '--force-downgrade', '--force-reinstall', '--force-maintainer', 'install', str(package)], capture_output=True, text=True, timeout=10, umask=umask)

    def call(self, action):
        script = r'''require $argv[1].'/update-prepare.php';
        try {
          $env=['opt'=>$argv[2],'owner'=>(int)$argv[5],'installed'=>$argv[10],'pending'=>false,'status'=>file_get_contents($argv[2].'/lib/opkg/status'),'defaults'=>json_decode($argv[8],true)];
          if($argv[6]==='settings')$result=AsusUpdateSnapshot::capture($argv[2],$argv[4],(int)$argv[5]);
          else {require $argv[1].'/update-rollback.php';$result=match($argv[6]){
            'capture'=>AsusUpdateRollback::capture($env,$argv[3],$argv[4],$argv[7]),
            'load'=>AsusUpdateRollback::load($argv[3],(int)$argv[5]),
            'finalize'=>AsusUpdateRollback::finalize($env,$argv[3],$argv[4]),
            'verify'=>AsusUpdateRollback::verifyInstalled($env,$argv[3],$argv[4]),
            'defaults'=>AsusUpdatePackage::stockDefaults($argv[9],$env['opt'],$env['owner'])};}
          echo json_encode(['value'=>$result]);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        public = getattr(self,'public',PUBLIC)
        installed=getattr(self,'installed','1.3.2-asus6+b80')
        command = shlex.join([PHP, '-n', '-r', script, str(public), str(self.opt), str(self.snapshot), str(self.settings), str(os.getuid()), 'finalize', '', json.dumps(getattr(self,'defaults',{})),str(getattr(self,'reader',self.base/'old.ipk')),installed])
        result = subprocess.run([PHP, '-n', '-d', 'memory_limit=16M', '-r', script, str(public), str(self.opt), str(self.snapshot), str(self.settings), str(os.getuid()), action, '#!/bin/sh\nexec '+command+'\n',json.dumps(getattr(self,'defaults',{})),str(getattr(self,'reader',self.base/'old.ipk')),installed], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_snapshot_restores_actual_old_payload_settings_and_manager_record(self):
        self.assertIn('value', self.call('capture'))
        self.package(self.base/'new.ipk', 81, b'broken NEW executable\n')
        self.assertEqual(self.opkg(self.base/'new.ipk').returncode, 0)
        self.settings_file.write_text('DAMAGED NEW CONFIG\n')
        result = self.opkg(self.snapshot/'package.ipk')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(self.owned.read_bytes(), b'old executable\n')
        self.assertEqual(self.settings_file.read_text(), 'OWNER CONFIG\n')
        self.assertFalse((self.opt/'share/new-only').exists())
        self.assertIn('value', self.call('verify'))
        self.assertIn('Version: 1.3.2-asus6+b80', self.status.read_text())

    def test_real_opkg_legacy_umask_index_is_read_without_chmod_or_db_rewrite(self):
        index=self.opt/'lib/opkg/info/nfqws2-asus.list';index.unlink()
        result=self.opkg(self.base/'old.ipk',umask=0)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(index.stat().st_mode&0o777,0o666)
        self.settings_file.write_text('OWNER CONFIG\n')
        before=(index.read_bytes(),index.stat().st_ino,self.status.read_bytes())
        result=self.call('capture');self.assertIn('value',result,result)
        self.assertEqual((index.read_bytes(),index.stat().st_ino,self.status.read_bytes()),before)
        self.assertEqual(index.stat().st_mode&0o777,0o666)
        self.assertIn('value',self.call('verify'))

    def test_legacy_index_cannot_append_neighbor_or_arbitrary_root_file(self):
        index=self.opt/'lib/opkg/info/nfqws2-asus.list';original=index.read_text();index.chmod(0o666)
        for name in ['share/nfqws2-asus-neighbor/secret','usr/bin/foreign']:
            with self.subTest(name=name):
                path=self.opt/name;path.parent.mkdir(parents=True,exist_ok=True);path.parent.chmod(0o755)
                path.write_text('FOREIGN');path.chmod(0o644);index.write_text(original+'/opt/'+name+'\n')
                self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
                self.assertFalse(self.snapshot.exists());self.assertEqual(path.read_text(),'FOREIGN')

    def test_foreign_claim_inside_project_namespace_refuses_even_ordinary_index(self):
        name='share/nfqws2-asus/foreign-note';path=self.opt/name;path.parent.mkdir(parents=True);path.parent.chmod(0o755)
        path.write_text('FOREIGN');path.chmod(0o644)
        foreign=self.opt/'lib/opkg/info/other-package.list';foreign.write_text('/opt/'+name+'\n');foreign.chmod(0o666)
        index=self.opt/'lib/opkg/info/nfqws2-asus.list';index.write_text(index.read_text()+'/opt/'+name+'\n')
        self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
        self.assertFalse(self.snapshot.exists());self.assertEqual(path.read_text(),'FOREIGN')

    def test_foreign_package_with_underscore_keeps_ownership_protection(self):
        foreign=self.opt/'lib/opkg/info/tailscale_nohf.list'
        foreign.write_text('/opt/bin/tailscale_nohf\n');foreign.chmod(0o666)
        self.status.write_text(self.status.read_text().rstrip()+'\n\nPackage: tailscale_nohf\nVersion: 1.0\nStatus: install user installed\nArchitecture: all\n')
        before=(foreign.read_bytes(),foreign.stat().st_ino,self.status.read_bytes())
        self.assertIn('value',self.call('capture'))
        self.assertEqual((foreign.read_bytes(),foreign.stat().st_ino,self.status.read_bytes()),before)
        self.assertIn('value',self.call('verify'))
        # A valid underscore name still cannot claim any of our files.
        shutil.rmtree(self.snapshot)
        foreign.write_text('/opt/usr/bin/nfqws2\n')
        self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
        self.assertFalse(self.snapshot.exists())

    def test_legacy_index_and_foreign_index_links_are_never_followed(self):
        index=self.opt/'lib/opkg/info/nfqws2-asus.list';raw=index.read_bytes()
        outside=self.base/'outside-index';outside.write_bytes(raw);outside.chmod(0o666)
        for path in [index,index.with_name('foreign.list')]:
            for kind in ['symlink','hardlink']:
                with self.subTest(path=path.name,kind=kind):
                    if path.exists():path.unlink()
                    if kind=='symlink':path.symlink_to(outside)
                    else:os.link(outside,path)
                    self.assertIn(self.call('capture').get('error'),['invalid_state','rollback_unavailable'])
                    self.assertEqual(outside.read_bytes(),raw);self.assertFalse(self.snapshot.exists())
                    path.unlink()
                    if path==index:path.write_bytes(raw);path.chmod(0o644)

    def test_writable_manager_directory_and_payload_are_not_legacy_exceptions(self):
        info=self.opt/'lib/opkg/info'
        for path in [info,info.parent,self.opt/'lib',self.owned]:
            with self.subTest(path=path):
                mode=path.stat().st_mode&0o777;path.chmod(mode|0o022)
                self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
                self.assertFalse(self.snapshot.exists());path.chmod(mode)

    def test_index_reordering_during_capture_is_not_hidden_by_sorted_payload(self):
        self.public=self.base/'app';shutil.copytree(PUBLIC,self.public)
        source=self.public/'update-rollback.php';raw=source.read_text()
        barrier='self::staging($destination,$files,$metadata,$aux,$postinst);'
        self.assertIn(barrier,raw)
        # Deterministic concurrent-manager rewrite after admission, using real files.
        mutation="$p=$opt.'/lib/opkg/info/nfqws2-asus.list';file_put_contents($p,implode(\"\\n\",array_reverse(explode(\"\\n\",trim(file_get_contents($p))))).\"\\n\");"
        source.write_text(raw.replace(barrier,barrier+mutation,1))
        self.assertEqual(self.call('capture'),{'error':'settings_changed'})

    def test_real_foreign_package_index_allows_shared_directories_but_never_foreign_payload(self):
        name='share/nfqws2-asus/foreign-note'
        package=self.base/'foreign.ipk'
        control=b'Package: other-package\nVersion: 1\nArchitecture: all\nDescription: ownership fixture\n'
        package.write_bytes(self.section({'debian-binary':(b'2.0\n',0o644),'control.tar.gz':(self.section({'control':(control,0o644)}),0o644),'data.tar.gz':(self.section({'opt/'+name:(b'FOREIGN',0o644)}),0o644)}))
        result=self.opkg(package,umask=0);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        info=self.opt/'lib/opkg/info';foreign=info/'other-package.list'
        self.assertEqual(foreign.stat().st_mode&0o777,0o666)
        foreign.write_text('/opt\n/opt/usr/bin/\n'+foreign.read_text())
        self.assertIn('value',self.call('capture'))
        shutil.rmtree(self.snapshot)
        own=info/'nfqws2-asus.list';own.write_text(own.read_text()+str(self.opt/name)+'\n')
        self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
        self.assertFalse(self.snapshot.exists());self.assertEqual((self.opt/name).read_bytes(),b'FOREIGN')
        for claim in ['//opt/'+name,'/'+str(self.opt/name),'/opt//'+name,'/opt/'+name+'//']:
            with self.subTest(claim=claim):
                foreign.write_text(claim+'\n')
                try:
                    self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
                    self.assertFalse(self.snapshot.exists());self.assertEqual((self.opt/name).read_bytes(),b'FOREIGN')
                finally:
                    if self.snapshot.exists():shutil.rmtree(self.snapshot)

    def test_index_special_modes_and_size_are_not_legacy_exceptions(self):
        index=self.opt/'lib/opkg/info/nfqws2-asus.list';raw=index.read_bytes()
        for mode in [0o664,0o646,0o1666,0o2666,0o4666]:
            with self.subTest(mode=oct(mode)):
                index.chmod(mode);self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'});self.assertFalse(self.snapshot.exists())
        index.chmod(0o666);index.write_bytes(raw+b'\n'*131073)
        self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'});self.assertFalse(self.snapshot.exists())

    def test_index_replacement_between_stat_and_open_is_detected(self):
        self.public=self.base/'app';shutil.copytree(PUBLIC,self.public)
        source=self.public/'update-rollback.php';raw=source.read_text()
        barrier="$f=@fopen($path,'rb');if(!$f)throw new RuntimeException('rollback_unavailable');"
        self.assertIn(barrier,raw)
        # A writer replaces the path after lstat while preserving bytes and modes.
        mutation="copy($path,$path.'.replacement');chmod($path.'.replacement',lstat($path)['mode']&0777);rename($path.'.replacement',$path);"
        source.write_text(raw.replace(barrier,mutation+barrier,1))
        self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
        self.assertFalse(self.snapshot.exists())

    def test_actual_cli_fallback_sanitizes_entry_failure_and_preserves_precise_record(self):
        self.public=self.base/'app';shutil.copytree(PUBLIC,self.public)
        worker=self.public/'update-worker.php'
        worker.write_text(worker.read_text().replace('{$this->prepare=',"{throw new RuntimeException('PRIVATE_DETAIL');$this->prepare=",1))
        state=self.base/'state';op=state/'operations'/('a'*32);op.mkdir(parents=True,mode=0o700)
        state.chmod(0o700);op.parent.chmod(0o700)
        source=(ROOT/'asus/update/worker.php').read_text()
        source=source.replace(r'0\s+0\s+0\s+0',r'\s+'.join([str(os.getuid())]*4))
        source=source.replace('new AsusUpdateStore();','new AsusUpdateStore('+json.dumps(str(state))+','+str(os.getuid())+');')
        entry=self.base/'entry.php';entry.write_text(source)
        record=op/'rollback-finalize-error.json'
        for existing in [None,{'schema':1,'stage':'context','code':'invalid_state','guard':{'ticket':'missing'}}]:
            with self.subTest(existing=existing):
                if existing is not None:record.write_text(json.dumps(existing));record.chmod(0o600)
                result=subprocess.run([PHP,'-n',str(entry),'--','rollback-finalize','a'*32],capture_output=True,text=True,timeout=3)
                self.assertEqual(result.returncode,1);self.assertEqual(result.stdout+result.stderr,'')
                value=json.loads(record.read_text())
                if existing is not None:self.assertEqual(value,existing)
                else:self.assertEqual(value,{'schema':1,'stage':'entry','code':'update_failed','guard':{'ticket':'missing'}})
                self.assertEqual(record.stat().st_mode&0o777,0o600);self.assertNotIn('PRIVATE_DETAIL',record.read_text())

    def test_candidate_stock_map_reads_only_closed_config_list_and_blob_templates(self):
        self.reader=self.base/'candidate.ipk'
        self.package(self.reader,81,b'NEW',{
            'opt/etc/nfqws2/nfqws2.conf.notactive':(b'factory config',0o600),
            'opt/etc/nfqws2/lists/user.list.notactive':(b'factory list',0o644),
            'opt/share/nfqws2-asus/defaults/blobs/new.bin':(b'NEW',0o644),
            'opt/share/nfqws2-asus/factory/lua/stock.lua':(b'factory Lua',0o644),
            'opt/share/other.bin':(b'FOREIGN',0o644),
        })
        result=self.call('defaults');self.assertIn('value',result,result)
        self.assertEqual(set(result['value']),{'etc/nfqws2/nfqws2.conf','etc/nfqws2/lists/user.list','etc/nfqws2/blobs/new.bin','etc/nfqws2/lua/stock.lua-opkg'})
        self.assertEqual(result['value']['etc/nfqws2/blobs/new.bin']['size'],3)
        self.assertEqual(result['value']['etc/nfqws2/lua/stock.lua-opkg']['sha256'],hashlib.sha256(b'factory Lua').hexdigest())

    def test_candidate_seeded_active_blob_is_quarantined_to_restore_old_absence(self):
        import hashlib
        self.defaults={'etc/nfqws2/blobs/new.bin':{'mode':0o644,'size':3,'sha256':hashlib.sha256(b'NEW').hexdigest()}}
        self.assertIn('value',self.call('capture'))
        blob=self.opt/'etc/nfqws2/blobs/new.bin';blob.parent.mkdir(mode=0o755);blob.write_bytes(b'NEW');blob.chmod(0o644)
        result=self.opkg(self.snapshot/'package.ipk');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotIn('error',result.stdout);self.assertFalse(blob.exists())
        self.assertTrue(any(p.is_file() and p.read_bytes()==b'NEW' for p in (self.snapshot/'quarantine').rglob('*')))
        self.assertIn('value',self.call('verify'))

    def test_different_custom_extra_is_preserved_and_rollback_refuses(self):
        import hashlib
        self.defaults={'etc/nfqws2/blobs/new.bin':{'mode':0o644,'size':3,'sha256':hashlib.sha256(b'NEW').hexdigest()}}
        self.assertIn('value',self.call('capture'))
        blob=self.opt/'etc/nfqws2/blobs/new.bin';blob.parent.mkdir(mode=0o755);blob.write_bytes(b'OWNER CUSTOM');blob.chmod(0o644)
        result=self.opkg(self.snapshot/'package.ipk')
        self.assertIn('error',result.stdout);self.assertEqual(blob.read_bytes(),b'OWNER CUSTOM')

    def test_unknown_operator_note_is_never_added_to_cleanup_index_during_restore(self):
        self.assertIn('value',self.call('capture'))
        note=self.snapshot/'operator-note';note.write_text('KEEP');note.chmod(0o600)
        result=self.opkg(self.snapshot/'package.ipk');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotIn('error',result.stdout)
        self.assertNotIn('operator-note',json.loads((self.snapshot/'cleanup-index.json').read_text())['files'])
        self.assertEqual(note.read_text(),'KEEP')

    def test_unknown_own_manager_metadata_refuses_snapshot(self):
        path=self.opt/'lib/opkg/info/nfqws2-asus.unrecognized';path.write_text('KEEP');path.chmod(0o600)
        self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
        self.assertFalse(self.snapshot.exists())

    def test_modified_snapshot_is_rejected(self):
        self.assertIn('value', self.call('capture'))
        (self.snapshot/'payload/usr/bin/nfqws2').write_text('tampered')
        self.assertEqual(self.call('load'), {'error': 'rollback_failed'})

    def test_missing_own_metadata_or_pending_baseline_never_snapshots(self):
        (self.opt/'lib/opkg/info/nfqws2-asus.control').unlink()
        self.assertEqual(self.call('capture'), {'error': 'rollback_unavailable'})
        self.assertFalse(self.snapshot.exists())

    def test_failed_migration_is_quarantined_and_old_state_restored_without_touching_history_or_lock(self):
        migration=self.opt/'etc/nfqws2-asus-migration';migration.mkdir(mode=0o700)
        (migration/'complete').write_text('old completed\n');(migration/'complete').chmod(0o600)
        history=self.opt/'etc/nfqws2-asus-migration.previous.1';history.mkdir(mode=0o700)
        (history/'complete').write_text('historic\n');(history/'complete').chmod(0o600)
        relay=self.opt/'var/lib/nfqws2-asus';relay.mkdir(parents=True);[p.chmod(0o755) for p in [relay,relay.parent,relay.parent.parent]]
        lock=relay/'relay-config-preserve.lock';lock.touch(mode=0o600);inode=lock.stat().st_ino
        self.assertIn('value',self.call('capture'))
        (migration/'complete').write_text('new failed state\n')
        stage=relay/'relay-config-preserve';stage.mkdir(mode=0o700)
        (stage/'metadata.json').write_text('{}');(stage/'metadata.json').chmod(0o600)
        restored=self.opkg(self.snapshot/'package.ipk');self.assertEqual(restored.returncode,0,restored.stdout+restored.stderr)
        self.assertNotIn('error',restored.stdout)
        self.assertEqual((migration/'complete').read_text(),'old completed\n')
        self.assertEqual((history/'complete').read_text(),'historic\n')
        self.assertEqual(lock.stat().st_ino,inode)
        self.assertFalse(stage.exists())
        self.assertTrue(list((self.snapshot/'quarantine').glob('*')))

    def test_historical_absent_own_row_is_not_an_active_duplicate(self):
        with self.status.open('a') as out:out.write('Package: nfqws2-asus\nVersion: 1.3.2-asus6+b79\nArchitecture: all\nStatus: install prefer,user not-installed\n\n')
        self.assertIn('value',self.call('capture'))

    def test_real_manager_rollback_ignores_historical57_while_live_status_is_uncommitted(self):
        with self.status.open('a') as out:out.write('Package: nfqws2-asus\nVersion: 1.3.2-asus6+b57\nArchitecture: all\nStatus: install prefer,user not-installed\n\n')
        self.assertIn('value',self.call('capture'))
        self.package(self.base/'new.ipk',81,b'NEW executable\n')
        result=self.opkg(self.base/'new.ipk');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        result=self.opkg(self.snapshot/'package.ipk');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotIn('"error"',result.stdout,result.stdout+result.stderr)
        self.assertIn('value',self.call('verify'))
        self.assertEqual(self.owned.read_bytes(),b'old executable\n');self.assertEqual(self.settings_file.read_text(),'OWNER CONFIG\n')

    def test_absent_own_is_never_healthy_and_unexpected_live_version_still_blocks_restore(self):
        self.assertIn('value',self.call('capture'));original=self.status.read_text()
        self.status.write_text(original.replace('+b80','+b57'))
        self.assertEqual(self.call('finalize'),{'error':'rollback_failed'})
        self.status.write_text(original.replace('Status: install user installed','Status: install prefer,user not-installed'))
        self.assertEqual(self.call('verify'),{'error':'rollback_failed'})
        self.snapshot=self.base/'another-snapshot'
        self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'});self.assertFalse(self.snapshot.exists())

    def test_tampered_settings_copy_refuses_before_any_restore_write(self):
        self.assertIn('value',self.call('capture'))
        (self.settings/'etc/nfqws2/nfqws2.conf').write_text('ATTACK\n')
        self.settings_file.write_text('CURRENT CONFIG\n')
        self.assertEqual(self.call('finalize'),{'error':'rollback_failed'})
        self.assertEqual(self.settings_file.read_text(),'CURRENT CONFIG\n')

    def test_writable_learned_list_is_closed_to_known_migration_list_leaf(self):
        migration=self.opt/'etc/nfqws2-asus-migration';lists=migration/'snapshot/lists';lists.mkdir(parents=True,mode=0o700)
        migration.chmod(0o700);(migration/'snapshot').chmod(0o700)
        (migration/'complete').touch(mode=0o600)
        learned=lists/'auto.list';learned.write_text('learned.example\n');learned.chmod(0o666)
        self.assertIn('value',self.call('capture'))
        result=self.opkg(self.snapshot/'package.ipk');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotIn('error',result.stdout)
        self.assertEqual(learned.read_text(),'learned.example\n');self.assertEqual(learned.stat().st_mode&0o777,0o666)

    def test_manifest_path_escape_is_rejected_without_touching_outside_file(self):
        self.assertIn('value',self.call('capture'))
        outside=self.base/'outside';outside.write_text('KEEP')
        manifest=self.snapshot/'snapshot.json';data=json.loads(manifest.read_text())
        data['aux']['migration']['files']={'../../../outside':next(iter(data['payload'].values()))}
        manifest.write_text(json.dumps(data))
        self.assertEqual(self.call('load'),{'error':'rollback_failed'})
        self.assertEqual(outside.read_text(),'KEEP')

    def test_writable_relay_parent_refuses_without_creating_lock(self):
        relay=self.opt/'var/lib/nfqws2-asus';relay.mkdir(parents=True);[p.chmod(0o755) for p in [relay,relay.parent,relay.parent.parent]];relay.chmod(0o777)
        self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
        self.assertFalse((relay/'relay-config-preserve.lock').exists())

    def test_relay_lock_contention_refuses_snapshot_without_replacing_lock(self):
        import fcntl
        relay=self.opt/'var/lib/nfqws2-asus';relay.mkdir(parents=True);[p.chmod(0o755) for p in [relay,relay.parent,relay.parent.parent]]
        lock=relay/'relay-config-preserve.lock';lock.touch(mode=0o600);before=lock.stat().st_ino
        with lock.open('r+b') as lease:
            fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
        self.assertEqual(lock.stat().st_ino,before)

    def test_unconsumed_old_migration_refuses_capture_before_package_mutation(self):
        migration=self.opt/'etc/nfqws2-asus-migration';(migration/'snapshot').mkdir(parents=True,mode=0o700);migration.chmod(0o700)
        self.assertEqual(self.call('capture'),{'error':'recovery_required'})
        self.assertFalse(self.snapshot.exists())

    def test_quarantine_symlink_never_moves_attempt_state_outside_private_operation(self):
        migration=self.opt/'etc/nfqws2-asus-migration';migration.mkdir(mode=0o700);(migration/'complete').write_text('OLD');(migration/'complete').chmod(0o600)
        self.assertIn('value',self.call('capture'))
        outside=self.base/'outside-quarantine';outside.mkdir(mode=0o700);(self.snapshot/'quarantine').symlink_to(outside,target_is_directory=True)
        (migration/'complete').write_text('FAILED NEW')
        self.assertIn('error',self.call('finalize'))
        self.assertEqual(list(outside.iterdir()),[])
        self.assertEqual((migration/'complete').read_text(),'FAILED NEW')

    def test_unrecognized_migration_artifact_refuses_capture(self):
        migration=self.opt/'etc/nfqws2-asus-migration';migration.mkdir(mode=0o700)
        (migration/'foreign-operator-note').write_text('KEEP\n');(migration/'foreign-operator-note').chmod(0o600)
        self.assertEqual(self.call('capture'),{'error':'rollback_unavailable'})
        self.assertEqual((migration/'foreign-operator-note').read_text(),'KEEP\n')

    def test_foreign_pending_or_changed_package_refuses_restore(self):
        self.assertIn('value',self.call('capture'))
        with self.status.open('a') as out:out.write('Package: foreign\nVersion: 2\nStatus: install user installed\n\n')
        self.assertEqual(self.call('finalize'),{'error':'rollback_failed'})


class PublishedPayloadRollbackTests(unittest.TestCase):
    def test_build80_81_82_both_architectures_stream_snapshot_with_modified_settings(self):
        repair=Path.home()/'.local/state/nfqws2-asus/repairs'
        builds=[(80,Path(os.environ.get('ASUS_RECOVERY_ARTIFACTS',repair/'build80-export-20261101/release80/assets'))),
                (81,Path(os.environ.get('ASUS_BUILD81_ARTIFACTS',repair/'build81-asus-20261101/release81/asus'))),
                (82,Path(os.environ.get('ASUS_BUILD82_ARTIFACTS',repair/'build82-hardware-20261101/candidate-asus')))]
        cases=[(build,abi,directory/f'nfqws2-asus_1.3.2-asus6+b{build}_{abi}.ipk')
               for build,directory in builds for abi in ['armv7','aarch64-3.10']
               if (directory/f'nfqws2-asus_1.3.2-asus6+b{build}_{abi}.ipk').is_file()]
        if not cases:self.skipTest('real ASUS package fixtures unavailable')
        for build,abi,package in cases:
            with self.subTest(build=build,abi=abi):
                case=PackageRollbackTests();case.setUp()
                try:
                    shutil.rmtree(case.opt);shutil.rmtree(case.settings)
                    case.installed=f'1.3.2-asus6+b{build}'
                    with tarfile.open(package) as outer:
                        members={m.name.removeprefix('./'):m for m in outer}
                        data=outer.extractfile(members['data.tar.gz']).read();control=outer.extractfile(members['control.tar.gz']).read()
                    owned=[]
                    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                        for member in archive:
                            path=Path(member.name)
                            self.assertEqual(path.parts[0],'opt');self.assertNotIn('..',path.parts)
                            target=case.base/path
                            if member.isdir():target.mkdir(parents=True,exist_ok=True);target.chmod(member.mode)
                            else:
                                self.assertTrue(member.isfile());target.parent.mkdir(parents=True,exist_ok=True)
                                target.write_bytes(archive.extractfile(member).read());target.chmod(member.mode)
                                owned.append('/'+str(path))
                    info=case.opt/'lib/opkg/info';info.mkdir(parents=True)
                    info.chmod(0o755);info.parent.chmod(0o755)
                    with tarfile.open(fileobj=io.BytesIO(control)) as archive:
                        for member in archive:
                            self.assertTrue(member.isfile());name=member.name.removeprefix('./');self.assertNotIn('/',name);target=info/('nfqws2-asus.'+name)
                            target.write_bytes(archive.extractfile(member).read());target.chmod(member.mode)
                    (info/'nfqws2-asus.list').write_text('\n'.join(owned)+'\n');(info/'nfqws2-asus.list').chmod(0o666)
                    conffiles=(info/'nfqws2-asus.conffiles').read_text().splitlines()
                    hashes=''.join(' '+name+' '+hashlib.sha256((case.base/name.lstrip('/')).read_bytes()).hexdigest()+'\n' for name in conffiles)
                    case.status.write_text((info/'nfqws2-asus.control').read_text()+'Status: install user installed\nConffiles:\n'+hashes+'\n');case.status.chmod(0o600)
                    baseline=json.loads((case.opt/'share/nfqws2-asus/report-baseline.json').read_text())
                    for name in baseline['resources']:
                        target=case.opt/'etc/nfqws2'/('blobs/'+name[5:] if name.startswith('blob/') else name)
                        if not target.exists():
                            source=(case.opt/'share/nfqws2-asus/defaults/blobs'/name[5:]) if name.startswith('blob/') else Path(str(target)+'.notactive');self.assertTrue(source.is_file(),str(source))
                            target.parent.mkdir(parents=True,exist_ok=True);target.parent.chmod(0o755);shutil.copy2(source,target)
                    case.settings_file.parent.mkdir(exist_ok=True);case.settings_file.write_text('OWNER MODIFIED ACTIVE CONFIG\n');case.settings_file.chmod(0o600)
                    self.assertIn('value',case.call('settings'))
                    case.reader=case.base/'candidate.ipk';shutil.copyfile(package,case.reader);case.reader.chmod(0o600)
                    defaults=case.call('defaults');self.assertIn('value',defaults,defaults);self.assertGreater(len(defaults['value']),5);case.defaults=defaults['value']
                    result=case.call('capture');self.assertIn('value',result,result)
                    self.assertGreater(len(result['value']['payload']),250)
                    self.assertIn('value',case.call('verify'))
                    self.assertEqual(case.settings_file.read_text(),'OWNER MODIFIED ACTIVE CONFIG\n')
                    target=case.opt/'usr/bin/nfqws2';target.write_bytes(b'one corrupted immutable file')
                    self.assertIn('error',case.call('verify'))
                finally:case.doCleanups()


@unittest.skipUnless(OPKG.is_file() and apply_fixtures.NATIVE.is_file(), 'native PHP and real opkg required')
class PackageRollbackApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):apply_fixtures.PackageUpdateApplyTests.setUpClass()
    @classmethod
    def tearDownClass(cls):apply_fixtures.PackageUpdateApplyTests.tearDownClass()
    def setUp(self):
        self.case=apply_fixtures.PackageUpdateApplyTests('test_running_stops_before_install_and_restores_once')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        c=self.case
        c.status.write_text(c.status.read_text().replace('Version: 1\nStatus:', 'Version: 1\nArchitecture: all\nStatus:'))
        conf=c.base/'actual-opkg.conf';conf.write_text('dest root /\narch all 100\narch aarch64-3.10 150\n')
        # The real native launcher still holds the actual POSIX lease; this
        # adapter only supplies a private-root location to real Entware opkg.
        actual=shlex.join([str(OPKG),'-f',str(conf),'-o',str(c.base),'--tmp-dir',str(c.opt/'tmp'),'--force-postinstall'])
        (c.opt/'tmp').mkdir(exist_ok=True)
        c.body.write_text('#!/bin/sh\ncase "$*" in *rollback/package.ipk*) exec '+actual+' "$@";; esac\n'+actual+' "$@" || exit $?\nexit 17\n')
    def test_partial_install_failure_restores_old_package_before_running_service(self):
        c=self.case;c.service.running();result=c.execute()
        self.assertEqual(result['state'],'failed',result)
        self.assertEqual(result['code'],'update_rolled_back',result)
        self.assertEqual(result['core_state'],'running',result)
        self.assertTrue(result['settings_verified'])
        self.assertEqual((c.opt/'etc/nfqws2/nfqws2.conf').read_text(),'PRIVATE_CONFIG')
        self.assertIn('Version: 1.3.1-asus6+b10',c.status.read_text())
        self.assertEqual(c.commands(),['stop','start'])
        self.assertTrue((c.op/'rollback/snapshot.json').is_file())
    def test_initially_stopped_stays_stopped_after_partial_install_rollback(self):
        c=self.case;result=c.execute()
        self.assertEqual(result['code'],'update_rolled_back',result)
        self.assertEqual(result['core_state'],'stopped',result)
        self.assertEqual(c.commands(),['stop'])

    def test_real_rollback_hook_persists_closed_context_failure_diagnostic(self):
        c=self.case
        code='$p=$argv[1]."/transaction.json";$v=json_decode(file_get_contents($p),true);$v["worker"]["start_ticks"]="1";file_put_contents($p,json_encode($v));'
        mutation=shlex.join([str(c.php),'-n','-r',code,str(c.state)])
        c.body.write_text(c.body.read_text().replace('*) exec ','*) '+mutation+'; exec ',1))
        result=c.execute();self.assertEqual(result['code'],'rollback_failed',result)
        path=c.op/'rollback-finalize-error.json';self.assertTrue(path.is_file())
        value=json.loads(path.read_text());self.assertEqual(value['stage'],'context');self.assertEqual(value['code'],'invalid_state')
        self.assertFalse(value['guard']['worker_alive']);self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertNotIn(str(c.base),path.read_text());self.assertNotIn('start_ticks',path.read_text())

    def test_real_rollback_hook_distinguishes_wrong_phase_authorization_failure(self):
        c=self.case
        code='$p=$argv[1]."/transaction.json";$v=json_decode(file_get_contents($p),true);$v["phase"]="finished";file_put_contents($p,json_encode($v));'
        mutation=shlex.join([str(c.php),'-n','-r',code,str(c.state)])
        c.body.write_text(c.body.read_text().replace('*) exec ','*) '+mutation+'; exec ',1))
        result=c.execute();self.assertEqual(result['code'],'rollback_failed',result)
        path=c.op/'rollback-finalize-error.json';self.assertTrue(path.is_file())
        value=json.loads(path.read_text());self.assertEqual(value['stage'],'authorization');self.assertEqual(value['code'],'rollback_failed')
        self.assertEqual(value['guard']['phase'],'finished');self.assertTrue(value['guard']['worker_alive'])

    def test_real_rollback_hook_reports_changed_runtime_before_guard_admission(self):
        c=self.case;resource=c.runtime/'resources/package-manifest.schema.json'
        mutation='printf " " >> '+shlex.quote(str(resource))
        c.body.write_text(c.body.read_text().replace('*) exec ','*) '+mutation+'; exec ',1))
        result=c.execute();self.assertEqual(result['code'],'rollback_failed',result)
        path=c.op/'rollback-finalize-error.json';self.assertTrue(path.is_file())
        value=json.loads(path.read_text());self.assertEqual(value['stage'],'runtime');self.assertEqual(value['code'],'runtime_changed')

    def test_real_rollback_hook_distinguishes_manager_environment_from_restore(self):
        c=self.case;mutation='ln '+shlex.quote(str(c.status))+' '+shlex.quote(str(c.base/'status-alias'))
        c.body.write_text(c.body.read_text().replace('*) exec ','*) '+mutation+'; exec ',1))
        result=c.execute();self.assertEqual(result['code'],'rollback_failed',result)
        path=c.op/'rollback-finalize-error.json';self.assertTrue(path.is_file())
        value=json.loads(path.read_text());self.assertEqual(value['stage'],'environment');self.assertEqual(value['code'],'rollback_failed')
    def test_signed_candidate_postinst_seed_is_quarantined_by_full_worker_rollback(self):
        import base64,hashlib
        c=self.case;c.fixture.payload({'opt/share/nfqws2-asus/defaults/blobs/new.bin':(b'NEW',0o644)},directories=['opt/','opt/share/','opt/share/nfqws2-asus/','opt/share/nfqws2-asus/defaults/','opt/share/nfqws2-asus/defaults/blobs/'])
        shutil.copyfile(c.fixture.pkg,c.op/'package.ipk')
        manifest=json.loads((c.op/'manifest.json').read_text());manifest['packages']=[c.fixture.candidate['package']]
        raw=json.dumps(manifest,separators=(',',':')).encode();signature=base64.b64encode(subprocess.check_output(['openssl','dgst','-sha256','-sign',str(c.key)],input=raw))
        for directory in [c.op,c.state]:
            (directory/'manifest.json').write_bytes(raw);(directory/'manifest.sig').write_bytes(signature)
        code='require $argv[1]."/update-manifest.php";$m=AsusPackageManifest::verify(file_get_contents($argv[2]),file_get_contents($argv[3]),file_get_contents($argv[4]));echo json_encode(AsusPackageManifest::candidate($m,"aarch64-3.10","1.3.1-asus6+b10"));'
        candidate=json.loads(subprocess.check_output([str(c.php),'-n','-r',code,str(PUBLIC),str(c.op/'manifest.json'),str(c.op/'manifest.sig'),str(c.runtime/'resources/update-release-key.pem')]))
        (c.op/'candidate.json').write_text(json.dumps(candidate));db=json.loads((c.state/'operations.json').read_text());db['operations'][c.id]['revision']=candidate['revision'];(c.state/'operations.json').write_text(json.dumps(db))
        blob=c.opt/'etc/nfqws2/blobs/new.bin';seed=c.opt/'share/nfqws2-asus/defaults/blobs/new.bin'
        command='cp -p '+shlex.quote(str(c.op/'backup/etc/nfqws2/nfqws2.conf'))+' '+shlex.quote(str(c.opt/'etc/nfqws2/nfqws2.conf'))+'\nmkdir -p '+shlex.quote(str(blob.parent))+'\ncp -p '+shlex.quote(str(seed))+' '+shlex.quote(str(blob))+'\nexit 17'
        c.body.write_text(c.body.read_text().replace('exit 17',command))
        c.service.running();result=c.execute();self.assertEqual(result['code'],'update_rolled_back',result)
        self.assertEqual(result['core_state'],'running',result);self.assertFalse(blob.exists())
        self.assertIn('etc/nfqws2/blobs/new.bin',json.loads((c.op/'rollback/snapshot.json').read_text())['defaults'])
        self.assertTrue(any(p.is_file() and p.read_bytes()==b'NEW' for p in (c.op/'rollback/quarantine').rglob('*')))

    def legacy_resume_script(self):
        c=self.case;script=c.opt/'lib/nfqws2-asus/smartdns/control.php';script.parent.mkdir(parents=True,exist_ok=True)
        ready=c.base/'legacy-resume-ready';script.write_text('<?php file_put_contents('+json.dumps(str(ready))+',(string)getmypid());while(true)usleep(100000);');script.chmod(0o600)
        args=[str(c.php),'-n','-d','register_argc_argv=1','-q','-f',str(script),'--','resume']
        def cleanup():
            import signal
            if not ready.is_file():return
            pid=int(ready.read_text())
            try:
                if Path(f'/proc/{pid}/cmdline').read_bytes()==b'\0'.join(str(x).encode() for x in args)+b'\0':os.kill(pid,signal.SIGTERM)
            except (FileNotFoundError,ProcessLookupError):pass
        self.addCleanup(cleanup);return args,ready

    def test_legacy_queued_resume_is_stopped_before_initial_package_boundary(self):
        import time
        c=self.case;args,ready=self.legacy_resume_script()
        child=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);self.addCleanup(lambda:child.wait(timeout=3))
        end=time.monotonic()+2
        while not ready.is_file() and time.monotonic()<end:time.sleep(.01)
        self.assertTrue(ready.is_file());result=c.execute();self.assertEqual(result['code'],'update_rolled_back',result)
        self.assertIsNotNone(child.poll(),'old queued PHP must be gone before updater releases its lease')
        self.assertEqual(json.loads((c.op/'dns-resume-quiesced-before.json').read_text()),{'matched':1,'stopped':1})

    def test_legacy_resume_spawned_during_failed_install_is_stopped_after_old_payload_restore(self):
        c=self.case;args,ready=self.legacy_resume_script()
        text=c.body.read_text();needle='esac\n';spawn=shlex.join(args)+' </dev/null >/dev/null 2>&1 &\nn=0; while [ ! -f '+shlex.quote(str(ready))+' ] && [ "$n" -lt 100 ]; do sleep .01; n=$((n+1)); done\n'
        c.body.write_text(text.replace(needle,needle+spawn,1))
        result=c.execute();self.assertEqual(result['code'],'update_rolled_back',result)
        self.assertTrue(ready.is_file());self.assertEqual(json.loads((c.op/'dns-resume-quiesced-after.json').read_text()),{'matched':1,'stopped':1})
        pid=int(ready.read_text());proc=Path(f'/proc/{pid}/stat')
        self.assertTrue(not proc.exists() or proc.read_text().rsplit(') ',1)[1].split()[0]=='Z')

    def test_dns_resume_is_queued_from_restored_installed_control_after_rollback(self):
        c=self.case;control=c.opt/'lib/nfqws2-asus/smartdns/control.sh';control.parent.mkdir(parents=True)
        log=c.base/'dns-resume';control.write_text('#!/bin/sh\nprintf "%s\\n" "$1" > '+shlex.quote(str(log))+'\ncat '+shlex.quote(str(c.status))+' >> '+shlex.quote(str(log))+'\n');control.chmod(0o755)
        result=c.execute();self.assertEqual(result['code'],'update_rolled_back',result)
        self.assertTrue(log.is_file(),'fresh installed control must queue saved consent after verified restoration')
        self.assertTrue(log.read_text().startswith('queue-resume\n'))
        self.assertIn('Version: 1.3.1-asus6+b10',log.read_text())
        self.assertEqual(json.loads((c.op/'dns-resume.json').read_text()),{'state':'queued'})

    def test_waiting_for_wan_intent_survives_rollback(self):
        c=self.case;(c.service.run/'enabled').touch(mode=0o600);(c.service.base/'no-wan').touch()
        result=c.execute();self.assertEqual(result['code'],'update_rolled_back',result)
        self.assertEqual(result['core_state'],'waiting_for_wan',result)
        self.assertEqual(c.commands(),['stop','start'])

    def test_foreign_package_changed_after_failed_install_blocks_rollback(self):
        c=self.case;c.service.running()
        c.body.write_text(c.body.read_text().replace('exit 17',"printf '\\nPackage: foreign\\nVersion: 1\\nArchitecture: all\\nStatus: install ok installed\\n\\n' >> "+shlex.quote(str(c.status))+"\nexit 17"))
        result=c.execute();self.assertEqual(result['code'],'rollback_failed',result)
        self.assertEqual(c.commands(),['stop'])
        self.assertIn('Package: foreign',c.status.read_text())

    def test_web_health_failure_stops_new_web_before_restoring_old_daemon(self):
        c=self.case;c.service.running()
        # Let real opkg succeed, then make only the new web generation fail.
        c.body.write_text(c.body.read_text().replace('exit 17','cp -p '+shlex.quote(str(c.op/'backup/etc/nfqws2/nfqws2.conf'))+' '+shlex.quote(str(c.opt/'etc/nfqws2/nfqws2.conf'))+'\nexit 0'))
        log=c.base/'web-log';marker=c.base/'web-generation'
        version='awk '+shlex.quote('$0=="Package: nfqws2-asus"{own=1;next}/^Package: /{own=0}own&&/^Version:/{print}')+' '+shlex.quote(str(c.status))
        pidfile=c.base/'web-pid';newpid=c.base/'new-web-pid'
        c.service.web.write_text('#!/bin/sh\nprintf "%s " "$1" >> '+shlex.quote(str(log))+'\n'+version+' >> '+shlex.quote(str(log))+'\n'
          'case "$1" in stop) if [ -f '+shlex.quote(str(pidfile))+' ]; then kill -TERM "$(cat '+shlex.quote(str(pidfile))+')" 2>/dev/null || :; rm -f '+shlex.quote(str(pidfile))+'; fi;;\n'
          'start) /bin/sleep 30 </dev/null >/dev/null 2>&1 & echo $! > '+shlex.quote(str(pidfile))+'\n'+version+' > '+shlex.quote(str(marker))+'\nif grep -q b11 '+shlex.quote(str(marker))+'; then cp '+shlex.quote(str(pidfile))+' '+shlex.quote(str(newpid))+'; fi;; esac\nexit 0\n')
        def remember_web_children():
            for path in [pidfile,newpid]:
                if path.is_file():
                    pid=int(path.read_text())
                    try:start=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19]
                    except FileNotFoundError:pass
                    else:c.service.identities.append((pid,start))
        self.addCleanup(remember_web_children)

        config=json.loads((c.base/'config.json').read_text());config['web_generation']=str(marker);(c.base/'config.json').write_text(json.dumps(config))
        text=c.entry.read_text().replace("['web_health'=>fn()=>true]", "['web_health'=>fn()=>!is_file($base.'/web-generation')||!str_contains(file_get_contents($base.'/web-generation'),'+b11')]")
        c.entry.write_text(text);self.refresh_closure()
        result=c.execute();self.assertEqual(result['code'],'update_rolled_back',result)
        self.assertEqual(result['core_state'],'running',result)
        commands=log.read_text().splitlines();self.assertTrue(any(x.startswith('stop Version: 1.3.1-asus6+b11') for x in commands),commands)
        self.assertTrue(marker.read_text().startswith('Version: 1.3.1-asus6+b10'))
        self.assertTrue(newpid.is_file(),'new web daemon must have started before the injected health failure')
        self.assertNotEqual(pidfile.read_text(),newpid.read_text())
        proc=Path('/proc')/newpid.read_text().strip()/'stat'
        self.assertTrue(not proc.exists() or proc.read_text().rsplit(') ',1)[1].split()[0]=='Z','new daemon must be gone before old service is reported restored')
        self.assertEqual(json.loads((c.op/'update-failure.json').read_text())['code'],'web_health_failed')

    def refresh_closure(self):
        import hashlib
        c=self.case;path=c.runtime/'closure.json';closure=json.loads(path.read_text())
        for name,item in closure['files'].items():
            p=c.runtime/name;item['size']=p.stat().st_size;item['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        closure['bytes']=sum(item['size'] for item in closure['files'].values());path.write_text(json.dumps(closure))
        db=json.loads((c.state/'operations.json').read_text());db['operations'][c.id]['runtime_digest']=hashlib.sha256(path.read_bytes()).hexdigest();(c.state/'operations.json').write_text(json.dumps(db))

    def test_failed_rollback_is_explicit_and_never_starts_unverified_package(self):
        c=self.case;c.service.running();c.body.write_text('#!/bin/sh\nexit 18\n')
        result=c.execute()
        self.assertEqual(result['state'],'failed',result)
        self.assertEqual(result['code'],'rollback_failed',result)
        self.assertEqual(c.commands(),['stop'])


if __name__ == '__main__': unittest.main()
