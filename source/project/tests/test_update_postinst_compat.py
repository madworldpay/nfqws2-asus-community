"""Published legacy coordinator receives a sealed, success-gated fresh DNS queue."""
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import time
import unittest
import test_package_update_apply as fixtures
from test_dpi_normalize import PUBLIC,ROOT
from test_package_update_guard import NATIVE
from test_smartdns_profile import profile

ASSETS=Path(os.environ.get('NFQWS_BUILD81_ASSETS',str(ROOT/'.work/published-build81')))
ARTIFACT=ASSETS/'nfqws2-asus_1.3.2-asus6+b81_aarch64-3.10.ipk'

@unittest.skipUnless(NATIVE.is_file() and ARTIFACT.is_file(),'published81 and native process fixtures required')
class LegacyPostinstResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.PackageUpdateApplyTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixtures.PackageUpdateApplyTests.tearDownClass()
    def setUp(self):
        self.assertTrue((PUBLIC/'update-postinst-resume.php').is_file(),'legacy resume bridge missing')
        self.f=fixtures.PackageUpdateApplyTests('test_running_stops_before_install_and_restores_once');self.f.setUp();self.addCleanup(self.f.doCleanups)
        f=self.f;self.base=f.base;self.opt=f.opt;self.intent=self.base/'dns/resume-intent.json';self.intent.parent.mkdir(mode=0o700)
        confirmed=profile();digest=subprocess.check_output([str(NATIVE),'-n','-r','require $argv[1]."/smartdns-profile.php";echo AsusSmartDnsProfile::hash(json_decode(stream_get_contents(STDIN),true));',str(PUBLIC)],input=json.dumps(confirmed).encode()).decode()
        self.intent.write_text(json.dumps({'schema_version':1,'profile':confirmed,'profile_hash':digest,'engine_sha':'e'*64,'source_request_id':'d'*32}));self.intent.chmod(0o600)
        self.draft=self.base/'dns/draft.json';self.draft.write_text('OWNER NEW UNCONFIRMED DRAFT');self.draft.chmod(0o600)
        self.runner=self.base/'bridge.php';self.options={'owner':os.getuid(),'opt':str(self.opt),'opkg':str(f.opkg),'dns':str(self.intent.parent),'busybox':'/usr/bin/busybox','entry':[str(NATIVE),'-n',str(self.runner)],'wait':3}
        self.runner.write_text('<?php require '+json.dumps(str(PUBLIC/'update-postinst-resume.php'))+';$s=new AsusUpdateStore('+json.dumps(str(f.state))+','+str(os.getuid())+');$h=new AsusUpdatePostinstResume($s,json_decode(file_get_contents('+json.dumps(str(self.base/'bridge-options.json'))+'),true));try{$v=$argv[1]==="queue"?$h->schedule():$h->resume($argv[2]);echo json_encode($v);}catch(Throwable $e){echo json_encode(["error"=>$e->getMessage()]);exit(3);}')
        (self.base/'bridge-options.json').write_text(json.dumps(self.options));(self.base/'bridge-options.json').chmod(0o600)
        control=self.opt/'lib/nfqws2-asus/smartdns/control.sh';control.parent.mkdir(parents=True,exist_ok=True)
        control.write_text('#!/bin/sh\ncase "$1" in upgrade|remove) exit 0;; queue-resume) ;; *) exit 9;; esac\ncat '+shlex.quote(str(self.intent))+' > '+shlex.quote(str(self.base/'resumed-confirmed'))+'\n');control.chmod(0o755)
        f.install_hooks();postinst=self.base/'postinst';postinst.write_text(postinst.read_text().replace('asus_migration_complete(){ :; };','asus_migration_complete(){ :; };'))
        # Replace only the fixed installed bridge CLI invocation with a native
        # fixture entry; authorization still uses the real opkg/process ancestry.
        marker=self.opt/'share/nfqws-asus-web/update-postinst-resume.php';marker.parent.mkdir(parents=True);marker.write_text('bridge present');marker.chmod(0o644)
        php=self.opt/'bin/php-cgi';php.parent.mkdir(parents=True,exist_ok=True);php.write_text('#!/bin/sh\nexec '+shlex.join([str(NATIVE),'-n',str(self.runner),'queue'])+'\n');php.chmod(0o755)
        with tarfile.open(ARTIFACT,'r:gz') as outer:
            member=next(m for m in outer if m.name.lstrip('./')=='data.tar.gz');raw=outer.extractfile(member).read()
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as data:
            member=next(m for m in data if m.name.lstrip('./')=='opt/share/nfqws-asus-web/update-worker.php');self.legacy=data.extractfile(member).read()
    def seal(self,legacy=True):
        f=self.f
        if legacy:(f.application/'update-worker.php').write_bytes(self.legacy)
        files={}
        for p in f.runtime.rglob('*'):
            if p.is_file() and p.name!='closure.json':
                mode=0o700 if p.stat().st_mode&0o111 else 0o600;p.chmod(mode);files[p.relative_to(f.runtime).as_posix()]={'mode':mode,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        closure=f.runtime/'closure.json';closure.write_text(json.dumps({'schema':1,'files':dict(sorted(files.items())),'loader':'ld-fixture.so','bytes':sum(x['size'] for x in files.values())}));closure.chmod(0o600)
        db=json.loads((f.state/'operations.json').read_text());db['operations'][f.id]['runtime_digest']=hashlib.sha256(closure.read_bytes()).hexdigest();(f.state/'operations.json').write_text(json.dumps(db));(f.state/'operations.json').chmod(0o600)
    def wait(self):
        end=time.monotonic()+5
        while time.monotonic()<end:
            proof=self.f.op/'dns-resume.json'
            if (self.base/'resumed-confirmed').exists() and proof.is_file() and json.loads(proof.read_text()).get('state')=='queued':break
            time.sleep(.02)
    def test_actual_published81_coordinator_queues_confirmed_intent_after_success_without_touching_draft(self):
        self.seal();out=self.f.execute();self.assertEqual(out['state'],'succeeded',out);self.wait()
        self.assertTrue((self.base/'resumed-confirmed').is_file());self.assertEqual((self.base/'resumed-confirmed').read_bytes(),self.intent.read_bytes());self.assertEqual(self.draft.read_text(),'OWNER NEW UNCONFIRMED DRAFT')
        self.assertEqual(json.loads((self.f.op/'dns-resume.json').read_text())['state'],'queued')
    def test_modern82_coordinator_keeps_resume_ownership_and_does_not_schedule_bridge(self):
        self.seal(False);out=self.f.execute();self.assertEqual(out['state'],'succeeded',out)
        proof=self.f.op/'dns-resume.json';self.assertTrue(proof.is_file());self.assertNotIn('legacy',json.loads(proof.read_text()));self.assertIn('coordinator_owned',(self.f.op/'opkg.log').read_text())
    def test_modern_guardian_job_identity_does_not_activate_the_legacy_bridge(self):
        self.seal(False);self.f.execute('guard-apply')
        out=json.loads((self.f.state/'operations.json').read_text())['operations'][self.f.id]
        self.assertEqual(out['state'],'succeeded',out);self.assertIn('coordinator_owned',(self.f.op/'opkg.log').read_text())
        self.assertNotIn('legacy',json.loads((self.f.op/'dns-resume.json').read_text()))
    def test_legacy_postflight_failure_never_dispatches_dns_resume(self):
        self.seal();self.f.service.web.write_text('#!/bin/sh\nexit 9\n');out=self.f.execute();self.assertEqual(out['state'],'failed',out);time.sleep(.3)
        self.assertFalse((self.base/'resumed-confirmed').exists());self.assertEqual(self.draft.read_text(),'OWNER NEW UNCONFIRMED DRAFT')
    def test_changed_confirmed_intent_after_postinst_is_never_replayed(self):
        self.seal();replacement=self.base/'replacement-intent';replacement.write_text(self.intent.read_text().replace('e'*64,'f'*64));replacement.chmod(0o600)
        self.f.body.write_text(self.f.body.read_text()+'\ncat '+shlex.quote(str(replacement))+' > '+shlex.quote(str(self.intent))+'\n')
        out=self.f.execute();self.assertEqual(out['state'],'succeeded',out);time.sleep(.3)
        self.assertFalse((self.base/'resumed-confirmed').exists());self.assertEqual(self.intent.read_bytes(),replacement.read_bytes());self.assertEqual(json.loads((self.f.op/'dns-resume.json').read_text())['code'],'settings_changed')
    def test_absent_confirmed_intent_is_inert_even_with_an_unconfirmed_draft(self):
        self.seal();self.intent.unlink();out=self.f.execute();self.assertEqual(out['state'],'succeeded',out);self.assertFalse((self.base/'resumed-confirmed').exists());self.assertFalse((self.f.op/'dns-resume.json').exists());self.assertEqual(self.draft.read_text(),'OWNER NEW UNCONFIRMED DRAFT')
    def test_standalone_cli_cannot_forge_postinst_process_proof(self):
        self.seal();p=subprocess.run([str(NATIVE),'-n',str(self.runner),'queue'],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,3);self.assertEqual(json.loads(p.stdout),{'error':'invalid_state'});self.assertFalse((self.f.op/'dns-resume.json').exists())
    def test_actual_entware_cgi_enters_fixed_cli_and_enforces_root_guard(self):
        if os.getuid()==0:self.skipTest('non-root smoke proof only')
        tools=ROOT/'.work/packaging-audit-20261012'
        for emulator,sysroot in [('qemu-arm','armv7-legacy-sysroot'),('qemu-arm','armv7-sysroot'),('qemu-aarch64','aarch64-sysroot')]:
            with self.subTest(sysroot=sysroot):
                p=subprocess.run([str(tools/emulator),'-L',str(tools/sysroot),str(tools/sysroot/'opt/bin/php8-cgi'),'-n','-d','register_argc_argv=1','-q','-f',str(PUBLIC/'update-postinst-resume.php'),'--','queue'],capture_output=True,text=True,timeout=5)
                self.assertEqual(p.returncode,1,'CGI must enter CLI root guard, not silently skip its main entry');self.assertEqual(p.stdout,'');self.assertEqual(p.stderr,'')
    def test_actual_published80_coordinator_uses_the_same_success_gated_bridge(self):
        artifact=Path(os.environ.get('NFQWS_BUILD80_ASSETS',str(ROOT/'.work/published-build80')))/'nfqws2-asus_1.3.2-asus6+b80_aarch64-3.10.ipk'
        if not artifact.is_file():self.skipTest('published80 fixture required')
        with tarfile.open(artifact,'r:gz') as outer:
            member=next(m for m in outer if m.name.lstrip('./')=='data.tar.gz');raw=outer.extractfile(member).read()
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as data:
            member=next(m for m in data if m.name.lstrip('./')=='opt/share/nfqws-asus-web/update-worker.php');self.legacy=data.extractfile(member).read()
        self.seal();out=self.f.execute();self.assertEqual(out['state'],'succeeded',out);self.wait();self.assertTrue((self.base/'resumed-confirmed').is_file());self.assertEqual(json.loads((self.f.op/'dns-resume.json').read_text())['state'],'queued')
    def test_running_worker_executable_must_be_the_sealed_php_or_declared_loader(self):
        self.seal();unsealed=self.f.runtime/'lib/ld-unsealed.so';shutil.copyfile(NATIVE,unsealed);unsealed.chmod(0o700);self.f.php=unsealed
        out=self.f.execute();self.assertEqual(out['state'],'failed');self.assertFalse((self.base/'resumed-confirmed').exists());self.assertIn('runtime_changed',(self.f.op/'opkg.log').read_text())
