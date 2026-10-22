"""Frozen public workers must survive real opkg without changing active relay settings."""
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile
import unittest
import test_package_update_apply as apply_fixture
from test_package_update_guard import NATIVE
from test_packages import ROOT, read_ipk

spec=importlib.util.spec_from_file_location('relay_builder',ROOT/'asus/build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
OPKG=ROOT/'.work/packaging-audit-20261012/opkg-x64'
LEGACY={
    64:(Path(os.environ.get('UPDATE_OLD64_IPK_TEST_FILE',ROOT/'.work/build64-release/nfqws2-asus_1.3.1-asus6+b64_aarch64-3.10.ipk')),'66de4430505bfb61053b9e0587126a8a88a0a434f06731b404f1506a504b1558'),
    65:(Path(os.environ.get('UPDATE_OLD65_IPK_TEST_FILE',ROOT/'.work/build65-channel-final/nfqws2-asus_1.3.1-asus6+b65_aarch64-3.10.ipk')),'91157e4008534353b7d9980bb17928cc7a1a290efd14bf5f2f74f47a81e7fe86'),
}
OLD=b'{"enabled":false,"url":""}\n'
ACTIVE='opt/etc/nfqws-asus-web/support-relay.json'

@unittest.skipUnless(NATIVE.is_file() and OPKG.is_file() and all(p.is_file() for p,h in LEGACY.values()),'frozen64/65 IPKs, native PHP and actual opkg fixtures required')
class LegacyRelayUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_fixture.PackageUpdateApplyTests.setUpClass();cls.legacy={}
        for build,(path,digest) in LEGACY.items():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise AssertionError('legacy IPK pin changed')
            data=read_ipk(path)['data'];prefix='opt/share/nfqws-asus-web/'
            cls.legacy[build]={n[len(prefix):]:raw for n,(m,raw) in data.items() if n.startswith(prefix) and '/' not in n[len(prefix):] and n.endswith('.php')}
    @classmethod
    def tearDownClass(cls):apply_fixture.PackageUpdateApplyTests.tearDownClass()
    def section(self,files):
        out=io.BytesIO()
        with tarfile.open(fileobj=out,mode='w:gz',format=tarfile.USTAR_FORMAT) as t:
            for n in sorted({str(q) for n in files for q in Path(n).parents if str(q)!='.'}):
                m=tarfile.TarInfo(n);m.type=tarfile.DIRTYPE;m.mode=0o755;t.addfile(m)
            for n,(raw,mode) in files.items():
                m=tarfile.TarInfo(n);m.mode=mode;m.size=len(raw);t.addfile(m,io.BytesIO(raw))
        return out.getvalue()
    def package(self,path,name,version,raw=None,hooks=None,template=False):
        header=(f'Package: {name}\nVersion: {version}\nArchitecture: aarch64-3.10\nDescription: old worker relay regression\n'+('Depends: iptables, libc\nReplaces: nfqws-asus-web\nConflicts: nfqws-asus-web\n' if name=='nfqws2-asus' else '')).encode()
        controls={'control':(header,0o644)};files={}
        if raw is not None:files[ACTIVE]=(raw,0o600);controls['conffiles']=(('/'+ACTIVE+'\n').encode(),0o644)
        if template:files['opt/share/nfqws2-asus/support-relay-default.json']=(self.factory,0o644)
        for k,v in (hooks or {}).items():controls[k]=(v,0o755)
        path.write_bytes(self.section({'debian-binary':(b'2.0\n',0o644),'control.tar.gz':(self.section(controls),0o644),'data.tar.gz':(self.section(files),0o644)}));return path
    def run_case(self,build,default,choice,preserve=True):
        f=apply_fixture.PackageUpdateApplyTests('test_running_stops_before_install_and_restores_once');f.setUp();self.addCleanup(f.doCleanups)
        # The test daemon execs asynchronously; the real init waits for its daemon.
        f.service.core.write_text(f.service.core.read_text()+'\n/bin/sleep .03\n')
        for q in f.application.iterdir():q.unlink()
        for name,raw in self.legacy[build].items():(f.application/name).write_bytes(raw);(f.application/name).chmod(0o600)
        self.factory=(ROOT/'asus/support-relay.json').read_bytes();(f.opt/'tmp').mkdir();tmp=f.base/'opkg-tmp';tmp.mkdir();cfg=f.base/'opkg.conf';cfg.write_text('dest root /\narch aarch64-3.10 160\n')
        args=[str(OPKG),'-f',str(cfg),'-o',str(f.base),'--tmp-dir',str(tmp),'--force-postinstall','install'];f.status.write_text('')
        # Package versions are synthetic; the whole staged application is byte-exact public64/65.
        for name,version,raw in [('iptables','1',None),('libc','1',None),('nfqws2-asus','1.3.1-asus6+b10',default)]:
            r=subprocess.run(args+[str(self.package(f.base/(name+'.ipk'),name,version,raw))],capture_output=True,text=True,timeout=10);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        for directory in [f.opt,*f.opt.rglob('*')]:
            if directory.is_dir():directory.chmod(0o755)
        active=f.base/ACTIVE
        if choice is not None:active.write_bytes(choice)
        active.chmod(0o600);expected=active.read_bytes();before=active.stat()
        f.install_hooks();hooks={'prerm':(f.base/'prerm').read_bytes(),'postinst':(f.base/'postinst').read_bytes()}
        if preserve:
            hooks['preinst']=b'#!/bin/sh\n'+builder.relay_preserver('prepare','1.3.1-asus6+b11',opt=str(f.opt),php=str(NATIVE),owner=os.getuid(),busybox='/bin/busybox',script_parent=str(f.opt/'tmp'))
            hooks['postinst']=b'#!/bin/sh\n'+builder.relay_preserver('finish','1.3.1-asus6+b11',opt=str(f.opt),php=str(NATIVE),owner=os.getuid(),busybox='/bin/busybox',script_parent=str(f.opt/'tmp'))+hooks['postinst']
        candidate=self.package(f.op/'package.ipk','nfqws2-asus','1.3.1-asus6+b11',self.factory,hooks,template=True)
        f.body.write_text('#!/bin/sh\nprintf opkg >> '+shlex.quote(str(f.base/'installs'))+'\n'+shlex.join(args+[str(candidate)])+' > '+shlex.quote(str(f.base/'real-opkg.stdout'))+' 2> '+shlex.quote(str(f.base/'real-opkg.stderr'))+'\n')
        manifest=json.loads((f.op/'manifest.json').read_text());manifest['packages'][0].update(size=candidate.stat().st_size,sha256=hashlib.sha256(candidate.read_bytes()).hexdigest());raw=json.dumps(manifest,separators=(',',':')).encode();sig=base64.b64encode(subprocess.check_output(['openssl','dgst','-sha256','-sign',str(f.key)],input=raw)).decode();old_revision=f.candidate['revision'];revision=hashlib.sha256(raw).hexdigest()
        for folder in [f.state,f.op]:(folder/'manifest.json').write_bytes(raw);(folder/'manifest.sig').write_text(sig)
        f.candidate.update(revision=revision,package=manifest['packages'][0]);(f.op/'candidate.json').write_text(json.dumps(f.candidate));f.entry.write_text(f.entry.read_text().replace(old_revision,revision))
        files={}
        for q in f.runtime.rglob('*'):
            if q.is_file() and q.name!='closure.json':
                mode=0o700 if q.stat().st_mode&0o111 else 0o600;q.chmod(mode);files[q.relative_to(f.runtime).as_posix()]={'mode':mode,'size':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()}
        (f.runtime/'closure.json').write_text(json.dumps({'schema':1,'files':dict(sorted(files.items())),'loader':'ld-fixture.so','bytes':sum(v['size'] for v in files.values())}));(f.runtime/'closure.json').chmod(0o600)
        shutil.rmtree(f.op/'backup');(f.state/'operations.json').unlink();f.execute('setup');f.service.running();result=f.execute()
        self.assertRegex(f.status.read_text(),r'Package: nfqws2-asus\nVersion: 1.3.1-asus6\+b11')
        if not preserve:
            self.assertEqual((result['state'],result['code'],f.commands()),('failed','settings_changed',['stop']));return {'runtime':build,'state':result['state'],'code':result['code'],'commands':f.commands()}
        self.assertEqual((result['state'],result.get('code'),result.get('core_state')),('succeeded',None,'running'),(result,(f.base/'real-opkg.stderr').read_text()))
        self.assertIs(result['settings_verified'],True);self.assertEqual(f.commands(),['stop','start']);self.assertEqual(active.read_bytes(),expected)
        after=active.stat();self.assertEqual((after.st_mode,after.st_uid,after.st_gid),(before.st_mode,before.st_uid,before.st_gid));self.assertFalse((f.opt/'var/lib/nfqws2-asus/relay-config-preserve').exists())
        # The public frozen closure was neither patched nor taught a settings exception.
        for name,raw in self.legacy[build].items():self.assertEqual((f.application/name).read_bytes(),raw)
        return {'runtime':build,'state':result['state'],'settings_verified':result['settings_verified'],'core_state':result['core_state'],'commands':f.commands(),'config_sha256':hashlib.sha256(expected).hexdigest(),'mode':after.st_mode&0o777,'uid':after.st_uid,'gid':after.st_gid,'frozen_php_files':len(self.legacy[build]),'stage_cleaned':True}
    def test_old64_failure_is_reproduced_without_preserver(self):self.run_case(64,OLD,None,preserve=False)
    def test_real_opkg_retries_after_successful_prepare_then_preinstall_abort(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);opt=base/'opt';opt.mkdir();(opt/'tmp').mkdir();tmp=base/'tmp';tmp.mkdir()
            cfg=base/'opkg.conf';cfg.write_text('dest root /\narch aarch64-3.10 160\n')
            args=[str(OPKG),'-f',str(cfg),'-o',str(base),'--tmp-dir',str(tmp),'--force-postinstall','install']
            old=self.package(base/'old.ipk','nfqws2-asus','1.3.1-asus6+b10',OLD)
            for name in ['iptables','libc']:
                r=subprocess.run(args+[str(self.package(base/(name+'.ipk'),name,'1'))],capture_output=True,timeout=10);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run(args+[str(old)],capture_output=True,timeout=10);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            for d in [opt,*opt.rglob('*')]:
                if d.is_dir():d.chmod(0o755)
            self.factory=(ROOT/'asus/support-relay.json').read_bytes();active=base/ACTIVE;before=active.stat();marker=base/'abort-once'
            hooks={}
            for script,action in [('preinst','prepare'),('postinst','finish')]:
                hooks[script]=b'#!/bin/sh\n'+builder.relay_preserver(action,'1.3.1-asus6+b11',opt=str(opt),php=str(NATIVE),owner=os.getuid(),busybox='/bin/busybox',script_parent=str(opt/'tmp'))
            hooks['preinst']+=('if [ ! -f '+shlex.quote(str(marker))+' ]; then : > '+shlex.quote(str(marker))+'; exit 1; fi\n').encode()
            candidate=self.package(base/'new.ipk','nfqws2-asus','1.3.1-asus6+b11',self.factory,hooks,template=True)
            failed=subprocess.run(args+[str(candidate)],capture_output=True,timeout=10);self.assertNotEqual(failed.returncode,0,failed.stdout+failed.stderr)
            self.assertEqual(active.read_bytes(),OLD);self.assertEqual(active.stat().st_ino,before.st_ino)
            stage=opt/'var/lib/nfqws2-asus/relay-config-preserve';self.assertTrue(stage.is_dir())
            retry=subprocess.run(args+[str(candidate)],capture_output=True,timeout=10);self.assertEqual(retry.returncode,0,retry.stdout+retry.stderr)
            self.assertFalse(stage.exists());self.assertEqual(active.read_bytes(),OLD)
            after=active.stat();self.assertEqual((after.st_mode,after.st_uid,after.st_gid),(before.st_mode,before.st_uid,before.st_gid))
            self.assertRegex((opt/'lib/opkg/status').read_text(),r'Package: nfqws2-asus\nVersion: 1.3.1-asus6\+b11')
    def test_real_builder_inlines_hooks_without_expanding_legacy_control_names(self):
        import tempfile
        data=read_ipk(LEGACY[64][0])['data'];factory=(ROOT/'asus/support-relay.json').read_bytes()
        payload={'opt/libexec/nfqws2-asus/busybox':(data['opt/libexec/nfqws2-asus/busybox'][1],0o755),
                 ACTIVE:(factory,0o600),'opt/share/nfqws2-asus/support-relay-default.json':(factory,0o644)}
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)
            builder.package(output,'nfqws2-asus','1.3.1-asus6+b11','iptables, libc','nfqws-asus-web',payload,'unified','/'+ACTIVE+'\n','aarch64-3.10','aarch64-3.10','aarch64-3.10')
            package=read_ipk(next(output.glob('*.ipk')));controls=package['control']
            self.assertEqual(set(controls),{'control','conffiles','preinst','postinst','prerm','postrm','busybox-migration-aarch64-3.10'})
            for action in ['preinst','postinst']:
                raw=controls[action][1];self.assertIn(b'final class AsusRelayConffile',raw);self.assertLess(len(raw),131072)
                self.assertNotIn(b'-f /dev/stdin',raw);self.assertIn(b'$ASUS_MIGRATION_DIR/.relay-script.XXXXXX',raw)
                r=subprocess.run(['/bin/sh','-n'],input=raw,capture_output=True,timeout=5);self.assertEqual(r.returncode,0,r.stderr)
    def test_all_owner_choices_survive_both_frozen_runtimes(self):
        factory=(ROOT/'asus/support-relay.json').read_bytes()
        for build in [64,65]:
            for name,default,choice in [('stock64-disabled',OLD,None),('stock65-public',factory,None),('custom-disabled',OLD,b'{"enabled":false,"url":"https://operator.example/nfqws-support/v1/reports"}\n'),('custom-enabled',OLD,b'{"enabled":true,"url":"https://operator.example/nfqws-support/v1/reports"}\n')]:
                with self.subTest(runtime=build,choice=name):self.run_case(build,default,choice)

if __name__=='__main__':unittest.main()
