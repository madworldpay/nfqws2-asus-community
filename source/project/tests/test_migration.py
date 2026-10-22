"""Real Entware opkg replacement with controlled service boundaries."""
import importlib.util
import os
import re
import shlex
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('builder',ROOT/'asus/build.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
OPKG=Path(os.environ.get('OPKG_TEST_BINARY',ROOT/'.work/packaging-audit-20261012/opkg-x64'))
BUSYBOX=Path(os.environ.get('MIGRATION_BUSYBOX_TEST_BINARY','/bin/busybox'))

@unittest.skipUnless(OPKG.exists() and BUSYBOX.exists(),'matching test opkg/BusyBox not supplied')
class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.w=Path(self.tmp.name); self.root=self.w/'root';(self.root/'opt/tmp').mkdir(parents=True)
        self.cfg=self.w/'opkg.conf';self.cfg.write_text('dest root /\narch aarch64-3.10 10\n')
        (self.w/'tmp').mkdir()
        self.base=[str(OPKG),'-f',str(self.cfg),'-o',str(self.root),'--force-postinstall','--tmp-dir',str(self.w/'tmp')]
    def run_opkg(self,*args,ok=True):
        r=subprocess.run(self.base+list(map(str,args)),text=True,capture_output=True,timeout=15)
        if ok:self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        return r
    def package(self,name,version,data,combined=False,postfail=0):
        extra='Conflicts: nfqws-asus-web\nReplaces: nfqws-asus-web\n' if combined else ('Depends: nfqws2-asus\n' if name=='nfqws-asus-web' else '')
        ctrl={'control':(f'Package: {name}\nVersion: {version}\nArchitecture: aarch64-3.10\nDescription: fixture\n{extra}'.encode(),0o644),
              'conffiles':(('\n'.join('/'+n for n in data if not n.endswith('.notactive'))+'\n').encode(),0o644)}
        for action in ['preinst','postinst','prerm','postrm']:
            body=f'echo "{name} {action}" >> "{self.w}/trace"\n'
            if combined and action in ['preinst','postinst']:
                migration=ROOT/'asus/ipk/migration.sh'
                self.assertTrue(migration.exists(),'persistent migration snapshot missing')
                code=migration.read_text().replace('/opt/',str(self.root)+'/opt/').replace('ASUS_MIGRATION_OWNER=0',f'ASUS_MIGRATION_OWNER={os.getuid()}')
                # These upgrade fixtures have an existing runtime. Exercise its
                # real applets; missing-runtime reinstall has separate coverage.
                code=re.sub(r'(?m)^ASUS_MIGRATION_BUSYBOX=.*$', 'ASUS_MIGRATION_BUSYBOX='+shlex.quote(str(BUSYBOX)),code)
                body+=code+'\nasus_migration_'+('save' if action=='preinst' else 'restore')+' || exit $?\n'
                if action=='postinst':
                    defaults=ROOT/'asus/ipk/defaults.sh'
                    self.assertTrue(defaults.exists(), 'non-replacing defaults installer missing')
                    body+=defaults.read_text().replace('/opt/',str(self.root)+'/opt/')+'\nasus_install_defaults || exit $?\n'
                if action=='postinst':body+=f'[ {postfail} = 0 ] || exit {postfail}\nasus_migration_complete || exit $?\n'
            ctrl[action]=(('#!/bin/sh\n'+body+'exit 0\n').encode(),0o755)
        dest=self.w/f'{name}_{version}.ipk';dest.write_bytes(b.compressed_tar({'debian-binary':(b'2.0\n',0o644),'control.tar.gz':(b.compressed_tar(ctrl),0o644),'data.tar.gz':(b.compressed_tar({k:(v,0o600) for k,v in data.items()}),0o644)}));return dest
    def fixtures(self,web=True):
        core={'opt/etc/nfqws2/nfqws2.conf':b'factory','opt/etc/nfqws2/lists/user.list':b'factory-list'}
        auth={'opt/etc/nfqws-asus-web/auth.json':b'factory-auth'}
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus3',core))
        if web:self.run_opkg('install',self.package('nfqws-asus-web','0.1.4',auth))
        self.values={**{k:b'changed-'+v for k,v in core.items()},'opt/etc/nfqws2/lists/custom.list':b'custom'}
        if web:self.values.update({'opt/etc/nfqws-asus-web/auth.json':b'private-password','opt/etc/nfqws-asus-web/ark-backup.json':b'active-backup'})
        for name,content in self.values.items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content);p.chmod(0o600)
        return {**core,**auth}
    def assert_preserved(self):
        for name,content in self.values.items():
            p=self.root/name;self.assertEqual(p.read_bytes(),content,name);self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600,name)
    def test_split_migration_preserves_data_and_transfers_ownership(self):
        data=self.fixtures();self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',data,True))
        self.assert_preserved()
        files=self.run_opkg('files','nfqws2-asus').stdout
        self.assertIn('nfqws-asus-web/auth.json',files)
        self.assertNotIn('nfqws-asus-web -',self.run_opkg('list-installed').stdout)
        self.run_opkg('remove','nfqws-asus-web');self.assert_preserved()
        snap=self.root/'opt/etc/nfqws2-asus-migration/snapshot'
        self.assertTrue((snap/'manifest').is_file()); self.assertEqual(stat.S_IMODE(snap.stat().st_mode),0o700)
        trace=(self.w/'trace').read_text().splitlines()
        self.assertLess(trace.index('nfqws-asus-web prerm'),len(trace)-1-trace[::-1].index('nfqws2-asus preinst'))
        before=(snap/'manifest').read_bytes()
        self.run_opkg('install',self.w/'nfqws2-asus_1.3.1-asus5.ipk');self.assert_preserved();self.assertEqual((snap/'manifest').read_bytes(),before)
    def test_completed_snapshot_never_overwrites_later_user_edits(self):
        data=self.fixtures();self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',data,True))
        self.values['opt/etc/nfqws-asus-web/auth.json']=b'new-password-after-migration'
        (self.root/'opt/etc/nfqws-asus-web/auth.json').write_bytes(self.values['opt/etc/nfqws-asus-web/auth.json'])
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus6',data,True))
        self.assert_preserved()

    def test_stale_opkg_save_does_not_replace_live_config(self):
        data=self.fixtures()
        (self.root/'opt/etc/nfqws2/nfqws2.conf.opkg-save').write_bytes(b'STALE CONFIG')
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',data,True))
        self.assert_preserved()

    def test_retry_after_core_failure_preserves_panel_edits(self):
        data=self.fixtures()
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',data,True,7),ok=False)
        for name,value in [('opt/etc/nfqws2/nfqws2.conf',b'USER FIX AFTER FAILURE'),
                           ('opt/etc/nfqws-asus-web/auth.json',b'NEW PANEL PASSWORD'),
                           ('opt/etc/nfqws-asus-web/ark-backup.json',b'BACKUP RESTORED BY USER')]:
            self.values[name]=value;(self.root/name).write_bytes(value)
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus6',data,True))
        self.assert_preserved()

    def test_interrupted_data_checkpoint_can_be_retried(self):
        data=self.fixtures();d=self.root/'opt/etc/nfqws2-asus-migration';d.mkdir(mode=0o700)
        (d/'data-restored.new').write_text('interrupted checkpoint')
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',data,True))
        self.assert_preserved();self.assertTrue((d/'data-restored').is_file())

    def test_new_templates_preserve_even_unmodified_active_data(self):
        old={'opt/etc/nfqws2/nfqws2.conf':b'OLD DEFAULT', 'opt/etc/nfqws2/lists/user.list':b'OLD LIST'}
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus3',old))
        new={k+'.notactive':b'NEW DEFAULT' for k in old}
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',new,True))
        for name,value in old.items():self.assertEqual((self.root/name).read_bytes(),value)
        for name,value in new.items():self.assertEqual((self.root/name).read_bytes(),value)
        updated={k:b'NEXT DEFAULT' for k in new}
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus6',updated,True))
        for name,value in old.items():self.assertEqual((self.root/name).read_bytes(),value)
        for name,value in updated.items():self.assertEqual((self.root/name).read_bytes(),value)

    def test_fresh_install_activates_missing_templates_only(self):
        new={'opt/etc/nfqws2/nfqws2.conf.notactive':b'FRESH DEFAULT', 'opt/etc/nfqws2/lists/user.list.notactive':b'FRESH LIST'}
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',new,True))
        for name,value in new.items():self.assertEqual((self.root/name.removesuffix('.notactive')).read_bytes(),value)

    def test_update_leaves_deleted_list_absent_and_new_list_as_template(self):
        first={'opt/etc/nfqws2/nfqws2.conf.notactive':b'FIRST','opt/etc/nfqws2/lists/user.list.notactive':b'FIRST LIST'}
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',first,True))
        (self.root/'opt/etc/nfqws2/lists/user.list').unlink()
        second={**first,'opt/etc/nfqws2/lists/added.list.notactive':b'NEW OPTIONAL LIST'}
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus6',second,True))
        self.assertFalse((self.root/'opt/etc/nfqws2/lists/user.list').exists())
        self.assertFalse((self.root/'opt/etc/nfqws2/lists/added.list').exists())
        self.assertTrue((self.root/'opt/etc/nfqws2/lists/added.list.notactive').is_file())

    def test_interrupted_fresh_unpack_initializes_latest_templates_on_retry(self):
        first={'opt/etc/nfqws2/nfqws2.conf.notactive':b'OLD UNPACKED','opt/etc/nfqws2/lists/user.list.notactive':b'OLD UNPACKED LIST'}
        for name,value in first.items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
        latest={name:b'LATEST TEMPLATE' for name in first}
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',latest,True))
        for name,value in latest.items():
            self.assertEqual((self.root/name).read_bytes(),value)
            self.assertTrue((self.root/name.removesuffix('.notactive')).exists(), 'retry must initialize active files')
            self.assertEqual((self.root/name.removesuffix('.notactive')).read_bytes(),value)
        self.assertTrue((self.root/'opt/etc/nfqws2-asus-migration/defaults-initialized').is_file())

    def test_fresh_combined_install_has_no_old_data(self):
        data={'opt/etc/nfqws2/nfqws2.conf':b'fresh','opt/etc/nfqws-asus-web/auth.json':b'fresh-auth'}
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',data,True))
        for name,value in data.items():self.assertEqual((self.root/name).read_bytes(),value)

    def test_core_only_and_fresh_install(self):
        data=self.fixtures(False);self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',data,True));self.assert_preserved()
    def test_postinst_failure_keeps_snapshot_and_retry_restores_original(self):
        data=self.fixtures();new=self.package('nfqws2-asus','1.3.1-asus5',data,True,7)
        self.run_opkg('install',new,ok=False);self.assert_preserved()
        snap=self.root/'opt/etc/nfqws2-asus-migration/snapshot';before=(snap/'manifest').read_bytes()
        self.package('nfqws2-asus','1.3.1-asus6',data,True)
        self.run_opkg('install',self.w/'nfqws2-asus_1.3.1-asus6.ipk');self.assert_preserved();self.assertEqual((snap/'manifest').read_bytes(),before)
    def test_symlink_snapshot_fails_before_payload_install(self):
        data=self.fixtures(); parent=self.root/'opt/etc/nfqws2-asus-migration';parent.symlink_to(self.w/'unsafe')
        self.run_opkg('install',self.package('nfqws2-asus','1.3.1-asus5',data,True),ok=False)
        self.assert_preserved();self.assertFalse((self.w/'unsafe').exists())
