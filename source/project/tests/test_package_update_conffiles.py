"""Real rollback must keep opkg's factory baseline for the next normal upgrade."""
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import unittest
from unittest.mock import patch

import test_package_update_rollback as rollback_fixtures
from test_dpi_normalize import ROOT
OPKG=rollback_fixtures.OPKG


@unittest.skipUnless(OPKG.is_file() and Path('/bin/busybox').is_file(),'actual Entware opkg and BusyBox required')
class RollbackConffileTests(unittest.TestCase):
    def setUp(self):
        self.c=rollback_fixtures.PackageRollbackTests();self.c.setUp();self.addCleanup(self.c.doCleanups);c=self.c
        shutil.rmtree(c.opt);shutil.rmtree(c.settings);(c.opt/'tmp').mkdir(parents=True)
        self.factory={'auth.json':(ROOT/'asus/web-auth.json').read_bytes(),'support-relay.json':(ROOT/'asus/support-relay.json').read_bytes()}
        self.owner={'auth.json':b'{"mode":"custom","username":"owner","password_hash":"test-only-owner-hash"}\n','support-relay.json':b'{"enabled":false,"url":""}\n'}
        self.system=c.base/'system-busybox';self.system.write_text('#!/bin/sh\nexec /bin/busybox "$@"\n');self.system.chmod(0o755)
        c.settings_file.parent.mkdir(parents=True);c.settings_file.write_text('OWNER CONFIG\n');c.settings_file.chmod(0o600)
        self.package(c.base/'old-real.ipk',80);p=c.opkg(c.base/'old-real.ipk');self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertTrue((c.opt/'etc/nfqws2-asus-migration/complete').exists(),'actual completed migration fixture')
        for name,raw in self.owner.items():path=c.opt/'etc/nfqws-asus-web'/name;path.write_bytes(raw);path.chmod(0o600)
        foreign=c.base/'foreign.ipk';foreign.write_bytes(c.section({'debian-binary':(b'2.0\n',0o644),'control.tar.gz':(c.section({'control':(b'Package: other-package\nVersion: 1\nArchitecture: all\nDescription: foreign sentinel\n',0o644)}),0o644),'data.tar.gz':(c.section({'opt/share/foreign-marker':(b'FOREIGN',0o644)}),0o644)}))
        p=c.opkg(foreign);self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.foreign=self.foreign_records();self.assertIn('value',c.call('settings'))

    def package(self,path,build):
        c=self.c;migration=(ROOT/'asus/ipk/migration.sh').read_text().replace('/opt/',str(c.base)+'/opt/').replace('ASUS_MIGRATION_OWNER=0','ASUS_MIGRATION_OWNER='+str(os.getuid())).replace(' /bin/busybox',' '+str(self.system))
        defaults=(ROOT/'asus/ipk/defaults.sh').read_text().replace('/opt/',str(c.base)+'/opt/')
        control=f'Package: nfqws2-asus\nVersion: 1.3.2-asus6+b{build}\nArchitecture: all\nReplaces: nfqws-asus-web\nDescription: real conffile rollback fixture\n'.encode()
        controls={'control':(control,0o644),'conffiles':(b'/opt/etc/nfqws-asus-web/auth.json\n/opt/etc/nfqws-asus-web/support-relay.json\n',0o644),'preinst':(('#!/bin/sh\nASUS_PACKAGE_ABI=aarch64-3.10\n'+migration+'\nasus_migration_save || exit $?\n').encode(),0o755),'postinst':(('#!/bin/sh\n'+migration+'\n'+defaults+'\nasus_migration_restore || exit $?\nasus_install_defaults || exit $?\nasus_migration_complete || exit $?\n').encode(),0o755),'prerm':(b'#!/bin/sh\nexit 0\n',0o755),'postrm':(b'#!/bin/sh\nexit 0\n',0o755)}
        data={'opt/usr/bin/nfqws2':(b'old executable\n' if build==80 else b'candidate executable\n',0o755),'opt/etc/nfqws2/nfqws2.conf.notactive':(b'factory config\n',0o600),'opt/libexec/nfqws2-asus/busybox':(self.system.read_bytes(),0o755)}
        data.update({'opt/etc/nfqws-asus-web/'+name:(raw,0o600) for name,raw in self.factory.items()})
        path.write_bytes(c.section({'debian-binary':(b'2.0\n',0o644),'control.tar.gz':(c.section(controls),0o644),'data.tar.gz':(c.section(data),0o644)}))

    def foreign_records(self):
        return sorted(part for part in self.c.status.read_text().strip().split('\n\n') if not part.startswith('Package: nfqws2-asus\n'))

    def conffiles(self):
        own=next(part for part in self.c.status.read_text().strip().split('\n\n') if part.startswith('Package: nfqws2-asus\n') and ' not-installed' not in part)
        lines=own.splitlines();at=lines.index('Conffiles:')+1;out={}
        for line in lines[at:]:
            if not line.startswith(' '):break
            name,digest=line.split();out[Path(name).name]=digest
        return out

    def test_version_changing_rollback_preserves_factory_baseline_then_normal_upgrade_keeps_owner_files(self):
        c=self.c;expected={name:hashlib.sha256(raw).hexdigest() for name,raw in self.factory.items()};self.assertEqual(self.conffiles(),expected)
        saved=(c.settings/'snapshot.json').read_bytes();result=c.call('capture');self.assertIn('value',result,result)
        with tarfile.open(c.snapshot/'package.ipk') as outer:
            with tarfile.open(fileobj=io.BytesIO(outer.extractfile('data.tar.gz').read())) as data:
                for name,raw in self.factory.items():self.assertEqual(data.extractfile('opt/etc/nfqws-asus-web/'+name).read(),raw,'sealed archive contains factory seed only')
        for name,raw in self.owner.items():self.assertEqual((c.snapshot/'payload/etc/nfqws-asus-web'/name).read_bytes(),raw,'private owner snapshot stays exact')
        self.package(c.base/'new-real.ipk',81);p=c.opkg(c.base/'new-real.ipk');self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        p=c.opkg(c.snapshot/'package.ipk');self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertIn('value',c.call('verify'));self.assertEqual(self.conffiles(),expected,'real opkg must keep original factory hashes, never owner hashes')
        for name,raw in self.owner.items():self.assertEqual((c.opt/'etc/nfqws-asus-web'/name).read_bytes(),raw)
        self.package(c.base/'next-real.ipk',83)
        # Ordinary manager upgrade: no force-maintainer/downgrade/reinstall flags.
        p=subprocess.run([str(OPKG),'-f',str(c.config),'-o',str(c.base),'--tmp-dir',str(c.opt/'tmp'),'--force-postinstall','--nodeps','install',str(c.base/'next-real.ipk')],input='',capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        for name,raw in self.owner.items():self.assertEqual((c.opt/'etc/nfqws-asus-web'/name).read_bytes(),raw,'next ordinary upgrade preserves '+name)
        self.assertEqual(self.conffiles(),expected);self.assertEqual(self.foreign_records(),self.foreign);self.assertEqual((c.opt/'share/foreign-marker').read_bytes(),b'FOREIGN');self.assertEqual((c.settings/'snapshot.json').read_bytes(),saved)

    def test_unknown_owner_equal_missing_or_extra_factory_baselines_refuse_before_snapshot(self):
        c=self.c;original=c.status.read_text();factory=hashlib.sha256(self.factory['auth.json']).hexdigest();owner=hashlib.sha256(self.owner['auth.json']).hexdigest()
        variants=[original.replace(factory,'0'*64),original.replace(factory,owner),original.replace('Conffiles:\n','Conffiles: \n /opt/etc/nfqws2/nfqws2.conf '+'a'*64+'\n'),original.replace(' /opt/etc/nfqws-asus-web/auth.json '+factory+'\n','')]
        for raw in variants:
            with self.subTest(raw_hash=hashlib.sha256(raw.encode()).hexdigest()):
                c.status.write_text(raw);self.assertEqual(c.call('capture'),{'error':'rollback_unavailable'});self.assertFalse(c.snapshot.exists());self.assertEqual(c.status.read_text(),raw)
                for name,value in self.owner.items():self.assertEqual((c.opt/'etc/nfqws-asus-web'/name).read_bytes(),value)
        c.status.write_text(original)

    def test_tampered_snapshot_or_postcommit_conffile_baseline_fails_verification(self):
        c=self.c;self.assertIn('value',c.call('capture'));record=c.snapshot/'snapshot.json';original=record.read_bytes();value=json.loads(original);value['conffiles']['etc/nfqws-asus-web/auth.json']='0'*64
        record.write_text(json.dumps(value));self.assertEqual(c.call('load'),{'error':'rollback_failed'});record.write_bytes(original)
        raw=c.status.read_text();c.status.write_text(raw.replace(hashlib.sha256(self.factory['auth.json']).hexdigest(),hashlib.sha256(self.owner['auth.json']).hexdigest()))
        self.assertEqual(c.call('verify'),{'error':'rollback_failed'})

    def test_real_pending_rollback_then_exact_own_configure_can_capture_the_next_safe_update(self):
        c=self.c;join=shlex.join
        # Keep finalize real and successful, then interrupt this maintainer hook
        # with an explicit failure so actual opkg leaves own package unpacked.
        with patch.object(rollback_fixtures.shlex,'join',lambda args:join(['/bin/sh','-c',join(args)+'; exit 43'])):
            result=c.call('capture')
        self.assertIn('value',result,result);self.package(c.base/'new-real.ipk',81)
        p=subprocess.run([str(OPKG),'-f',str(c.config),'-o',str(c.base),'--tmp-dir',str(c.opt/'tmp'),'--force-postinstall','--nodeps','install',str(c.base/'new-real.ipk')],input='',capture_output=True,text=True,timeout=10,umask=0o022)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        p=c.opkg(c.snapshot/'package.ipk');self.assertNotEqual(p.returncode,0);self.assertIn(' unpacked',c.status.read_text())
        index=c.opt/'lib/opkg/info/nfqws2-asus.list';missing=index.read_bytes()
        for name in self.factory:self.assertNotIn('/opt/etc/nfqws-asus-web/'+name,index.read_text(),'actual manager omits retained conffiles on this failure boundary')
        old=c.base/'old-real.ipk';candidate={'action':'configure','package_version':'1.3.2-asus6+b80','package':{'family':'armv7','size':old.stat().st_size,'sha256':hashlib.sha256(old.read_bytes()).hexdigest()}}
        code='require $argv[1]."/update-prepare.php";try{AsusUpdatePackage::inspect($argv[2],json_decode($argv[3],true),file_get_contents($argv[4]),"armv7-2.6","armv7l",$argv[5],(int)$argv[6]);echo "ok";}catch(Throwable $e){echo $e->getMessage();exit(1);}'
        from test_dpi_normalize import PHP,PUBLIC
        check=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(old),json.dumps(candidate),str(c.status),str(c.opt),str(os.getuid())],capture_output=True,text=True,timeout=10)
        self.assertEqual(check.returncode,0,check.stdout+check.stderr)
        configured=subprocess.run([str(OPKG),'-f',str(c.config),'-o',str(c.base),'--tmp-dir',str(c.opt/'tmp'),'--force-postinstall','configure','nfqws2-asus'],env={**os.environ,'NFQWS_ASUS_NO_START':'1'},capture_output=True,text=True,timeout=10,umask=0o022)
        self.assertEqual(configured.returncode,0,configured.stdout+configured.stderr);self.assertEqual(index.read_bytes(),missing,'configure must not fabricate inventory')
        self.assertIn('value',c.call('verify'))
        c.snapshot=c.base/'next-snapshot';result=c.call('capture');self.assertIn('value',result,result)
        self.assertEqual(index.read_bytes(),missing,'snapshot must not rewrite inventory')
        for name,raw in self.owner.items():self.assertEqual((c.opt/'etc/nfqws-asus-web'/name).read_bytes(),raw)
        self.assertEqual(self.conffiles(),{name:hashlib.sha256(raw).hexdigest() for name,raw in self.factory.items()});self.assertEqual(self.foreign_records(),self.foreign)

    def omit_conffiles_from_index(self):
        path=self.c.opt/'lib/opkg/info/nfqws2-asus.list';lines=path.read_text().splitlines();path.write_text('\n'.join(line for line in lines if line not in ['/opt/etc/nfqws-asus-web/'+name for name in self.factory])+'\n');path.chmod(0o666)
        return path.read_bytes()

    def test_declared_conffile_ownership_never_overrides_foreign_inventory_claims(self):
        c=self.c;self.omit_conffiles_from_index();foreign=c.opt/'lib/opkg/info/foreign-claim.list'
        for name in self.factory:
            for prefix in ['/opt',str(c.opt),'//opt','/'+str(c.opt)]:
                with self.subTest(name=name,prefix=prefix):
                    raw=prefix+'/etc/nfqws-asus-web/'+name+'\n';foreign.write_text(raw);foreign.chmod(0o666)
                    self.assertEqual(c.call('capture'),{'error':'rollback_unavailable'});self.assertFalse(c.snapshot.exists());self.assertEqual(foreign.read_text(),raw)

    def test_declared_missing_index_conffiles_still_reject_links_and_unknown_hashes(self):
        c=self.c;self.omit_conffiles_from_index();target=c.opt/'etc/nfqws-asus-web/auth.json';outside=c.base/'outside-owner';outside.write_bytes(self.owner['auth.json']);outside.chmod(0o600)
        for kind in ['symlink','hardlink']:
            with self.subTest(kind=kind):
                target.unlink()
                if kind=='symlink':target.symlink_to(outside)
                else:os.link(outside,target)
                self.assertIn(c.call('capture').get('error'),['invalid_state','rollback_unavailable']);self.assertFalse(c.snapshot.exists());self.assertEqual(outside.read_bytes(),self.owner['auth.json'])
                target.unlink();target.write_bytes(self.owner['auth.json']);target.chmod(0o600)
        original=c.status.read_text();c.status.write_text(original.replace(hashlib.sha256(self.factory['auth.json']).hexdigest(),'0'*64))
        self.assertEqual(c.call('capture'),{'error':'rollback_unavailable'});self.assertFalse(c.snapshot.exists())


if __name__=='__main__':unittest.main()
