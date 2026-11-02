"""Final settings belong to the stopped transaction, not download preparation."""
import json
import hashlib
import fcntl
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import threading
import unittest

import test_package_update_apply as apply_fixtures


@unittest.skipUnless(apply_fixtures.NATIVE.is_file(), 'native PHP fixture required')
class PackageUpdateQuiesceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):apply_fixtures.PackageUpdateApplyTests.setUpClass()
    @classmethod
    def tearDownClass(cls):apply_fixtures.PackageUpdateApplyTests.tearDownClass()
    def setUp(self):
        self.c=apply_fixtures.PackageUpdateApplyTests();self.c.setUp();self.addCleanup(self.c.doCleanups)
    def prepared_settings(self):
        c=self.c;backup=c.op/'backup'
        if backup.exists():shutil.rmtree(backup)
        code='require $argv[1]."/update-prepare.php";AsusUpdateSnapshot::capture($argv[2],$argv[3],(int)$argv[4]);'
        subprocess.run([str(c.php),'-n','-r',code,str(c.application),str(c.opt),str(backup),str(os.getuid())],check=True,capture_output=True)
    def attest(self):
        c=self.c;env={**c.env,'status':c.status.read_text(),'installed':'1.3.1-asus6+b10','pending':False}
        code='require $argv[1]."/update-rollback.php";try{echo json_encode(["proof"=>AsusUpdateRollback::attest(json_decode(stream_get_contents(STDIN),true))]);}catch(Throwable $e){echo json_encode(["error"=>$e->getMessage()]);}'
        r=subprocess.run([str(c.php),'-n','-r',code,str(apply_fixtures.PUBLIC)],input=json.dumps(env),capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def reseal(self):
        c=self.c;files={}
        for path in c.runtime.rglob('*'):
            if path.is_file() and path.name!='closure.json':
                mode=0o700 if path.stat().st_mode&0o111 else 0o600;path.chmod(mode)
                files[path.relative_to(c.runtime).as_posix()]={'mode':mode,'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        closure=c.runtime/'closure.json';closure.write_text(json.dumps({'schema':1,'files':dict(sorted(files.items())),'loader':'ld-fixture.so','bytes':sum(item['size'] for item in files.values())}));closure.chmod(0o600)
        db=json.loads((c.state/'operations.json').read_text());db['operations'][c.id]['runtime_digest']=hashlib.sha256(closure.read_bytes()).hexdigest();(c.state/'operations.json').write_text(json.dumps(db))
    def inject(self,needle,extra):
        path=self.c.application/'update-worker.php';text=path.read_text();self.assertIn(needle,text);path.write_text(text.replace(needle,extra+needle,1));self.reseal()
    def test_unconsumed_auxiliary_state_refuses_before_any_service_stop(self):
        for relative in ['etc/nfqws2-asus-migration/snapshot','var/lib/nfqws2-asus/relay-config-preserve']:
            with self.subTest(relative=relative):
                c=self.c;path=c.opt/relative;path.mkdir(parents=True,mode=0o700)
                for parent in path.parents:
                    if parent==c.opt:break
                    parent.chmod(0o755)
                self.assertEqual(self.attest().get('error'),'recovery_required')
                result=c.execute();self.assertEqual(result['state'],'failed',result);self.assertEqual(result['code'],'recovery_required')
                self.assertEqual(c.commands(),[]);self.assertFalse((c.base/'installs').exists())
                shutil.rmtree(path.parent if relative.startswith('etc/') else path)
                # A terminal operation needs a fresh fixture for the second case.
                if relative.startswith('etc/'):
                    c.doCleanups();self.c=apply_fixtures.PackageUpdateApplyTests();self.c.setUp();self.addCleanup(self.c.doCleanups)
    def test_unknown_web_status_never_becomes_an_off_intent(self):
        for body in ['exit 75','sleep .2; exit 1']:
            with self.subTest(body=body):
                c=self.c;c.service.running();c.service.web.write_text('#!/bin/sh\n'+body+'\n')
                config=json.loads((c.base/'config.json').read_text());config['service']['service_timeout']=.03;(c.base/'config.json').write_text(json.dumps(config))
                result=c.execute();self.assertEqual(result['state'],'failed',result);self.assertEqual(result['code'],'web_stop_failed')
                self.assertEqual(c.commands(),[]);self.assertFalse((c.base/'installs').exists());self.assertFalse((c.op/'quiesce.json').exists())
                c.doCleanups();self.c=apply_fixtures.PackageUpdateApplyTests();self.c.setUp();self.addCleanup(self.c.doCleanups)
    def test_definitively_off_web_stays_off_after_success(self):
        c=self.c;c.service.web.write_text('#!/bin/sh\n[ "$1" = status ] && exit 1\necho "$1" >> '+shlex.quote(str(c.base/'web-commands'))+'\nexit 0\n')
        result=c.execute();self.assertEqual(result['state'],'succeeded',result);self.assertFalse((c.base/'web-commands').exists())
        self.assertFalse(json.loads((c.op/'quiesce.json').read_text())['web_running'])
    def guarded_crash(self,needle="if($this->original($this->prepare->environment(),$candidate,$id)!==$q['attestation'])",deadline=10):
        c=self.c;marker=c.base/'crash-marker';release=c.base/'crash-release'
        self.inject(needle,'file_put_contents('+json.dumps(str(marker))+',"held");while(!is_file('+json.dumps(str(release))+'))usleep(5000);')
        config=json.loads((c.base/'config.json').read_text());config['deadline']=deadline;(c.base/'config.json').write_text(json.dumps(config))
        p=subprocess.Popen([str(c.php),'-n',str(c.entry),'guard-apply',c.id],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.addCleanup(lambda:(p.kill(),p.wait()) if p.poll() is None else None)
        until=time.monotonic()+3
        while not marker.exists() and p.poll() is None and time.monotonic()<until:time.sleep(.005)
        self.assertTrue(marker.exists(),'real native preflight did not reach crash barrier')
        return p,release
    def test_guardian_restores_running_service_after_apply_child_sigkill(self):
        c=self.c;c.service.running();p,release=self.guarded_crash();q=json.loads((c.op/'quiesce.json').read_text())
        os.kill(q['worker']['pid'],9);time.sleep(.04)
        self.assertIsNone(p.poll());self.assertEqual(json.loads((c.state/'operations.json').read_text())['operations'][c.id]['state'],'applying')
        # The still-live guardian protects the handoff, although the child died.
        code='require $argv[1]."/update-guard.php";try{$s=new AsusUpdateStore($argv[2],(int)$argv[3]);$f=(new AsusUpdateGuard($s,(int)$argv[3]))->mutationLease();fclose($f);echo "allowed";}catch(Throwable $e){echo $e->getMessage();}'
        r=subprocess.check_output([str(c.php),'-n','-r',code,str(c.application),str(c.state),str(os.getuid())],timeout=3);self.assertEqual(r,b'busy')
        release.touch();out,err=p.communicate(timeout=10);self.assertEqual(p.returncode,0,out+err);self.assertEqual(err,b'')
        job=json.loads((c.state/'operations.json').read_text())['operations'][c.id]
        self.assertEqual(job['state'],'failed',job);self.assertEqual(job['code'],'interrupted');self.assertEqual(job['core_state'],'running')
        self.assertFalse((c.base/'installs').exists());self.assertFalse((c.op/'boundary.json').exists());self.assertEqual(c.commands(),['stop','stop','start'])
        self.assertTrue(json.loads((c.op/'quiesce-result.json').read_text())['restored'])
        pid=int((c.service.run/'pid').read_text());c.service.identities.append((pid,Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19]))
    def test_duplicate_recovery_cannot_terminalize_the_live_apply(self):
        c=self.c;c.service.running();p,release=self.guarded_crash();before=(c.state/'operations.json').read_bytes();ticket=(c.state/'transaction.json').read_bytes()
        r=subprocess.run([str(c.php),'-n',str(c.entry),'restore-before-install',c.id],capture_output=True,timeout=3)
        self.assertEqual(r.returncode,1,r.stdout+r.stderr);self.assertEqual((c.state/'operations.json').read_bytes(),before);self.assertEqual((c.state/'transaction.json').read_bytes(),ticket)
        self.assertFalse((c.op/'quiesce-recovery-error.json').exists());self.assertIsNone(p.poll());release.touch();out,err=p.communicate(timeout=10);self.assertEqual(err,b'')
        self.assertEqual(json.loads((c.state/'operations.json').read_text())['operations'][c.id]['state'],'succeeded')
        pid=int((c.service.run/'pid').read_text());c.service.identities.append((pid,Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19]))
    def test_wrong_guardian_during_handoff_cannot_claim_or_modify_the_operation(self):
        c=self.c;c.service.running();p,release=self.guarded_crash();q=json.loads((c.op/'quiesce.json').read_text());os.kill(q['worker']['pid'],9)
        # This unrelated direct helper has no genuine guardian ancestor. Even
        # with every recorded old process dead it cannot replay saved ON.
        release.touch();p.kill();p.communicate(timeout=3)
        until=time.monotonic()+3
        while Path('/proc/'+str(q['installer']['pid'])+'/exe').exists() and time.monotonic()<until:time.sleep(.01)
        guard=json.loads((c.op/'guard.json').read_text());guard['guardian']['start_ticks']='1';(c.op/'guard.json').write_text(json.dumps(guard))
        before=(c.state/'operations.json').read_bytes();ticket=(c.state/'transaction.json').read_bytes()
        r=subprocess.run([str(c.php),'-n',str(c.entry),'restore-before-install',c.id],capture_output=True,timeout=3)
        self.assertEqual(r.returncode,1);self.assertEqual((c.state/'operations.json').read_bytes(),before);self.assertEqual((c.state/'transaction.json').read_bytes(),ticket);self.assertEqual(c.commands(),['stop'])
    def test_guardian_restores_after_final_snapshot_and_duplicate_is_inert(self):
        c=self.c;c.service.running();p,release=self.guarded_crash("$this->ticket($id,'installing');if($q['web_running'])")
        q=json.loads((c.op/'quiesce.json').read_text());self.assertTrue((c.op/'quiesced-backup/snapshot.json').exists());os.kill(q['worker']['pid'],9);release.touch();out,err=p.communicate(timeout=10)
        self.assertEqual(p.returncode,0,out+err);job=json.loads((c.state/'operations.json').read_text())['operations'][c.id];self.assertEqual(job['core_state'],'running',job);self.assertTrue(job['settings_verified'])
        before=(c.state/'operations.json').read_bytes();ticket=(c.state/'transaction.json').read_bytes();commands=c.commands()
        r=subprocess.run([str(c.php),'-n',str(c.entry),'restore-before-install',c.id],capture_output=True,timeout=3)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual((c.state/'operations.json').read_bytes(),before);self.assertEqual((c.state/'transaction.json').read_bytes(),ticket);self.assertEqual(c.commands(),commands)
        self.assertFalse((c.base/'installs').exists());pid=int((c.service.run/'pid').read_text());c.service.identities.append((pid,Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19]))
    def test_recovery_never_forces_a_foreign_manager_mutex(self):
        c=self.c;c.service.running();marker=c.base/'recover-lock-marker';gate=c.base/'recover-lock-release'
        needle="$this->install($id,['action'=>'rollback-verify']);"
        # First occurrence is the fixed recovery method, not ordinary catch.
        self.inject(needle,'file_put_contents('+json.dumps(str(marker))+',"held");while(!is_file('+json.dumps(str(gate))+'))usleep(5000);')
        p,release=self.guarded_crash();q=json.loads((c.op/'quiesce.json').read_text());os.kill(q['worker']['pid'],9);release.touch()
        until=time.monotonic()+3
        while not marker.exists() and p.poll() is None and time.monotonic()<until:time.sleep(.005)
        self.assertTrue(marker.exists())
        with c.lock.open('r+b') as held:
            fcntl.lockf(held,fcntl.LOCK_EX|fcntl.LOCK_NB);gate.touch();out,err=p.communicate(timeout=10)
            self.assertEqual(p.returncode,0,out+err);self.assertEqual(c.lock.stat().st_ino,os.fstat(held.fileno()).st_ino)
        job=json.loads((c.state/'operations.json').read_text())['operations'][c.id];self.assertEqual(job['code'],'recovery_required',job)
        self.assertEqual(c.commands(),['stop']);self.assertFalse((c.base/'installs').exists());self.assertFalse((c.service.run/'pid').exists())
    def test_guardian_tampered_original_payload_never_restarts_old_core(self):
        c=self.c;c.service.running();p,release=self.guarded_crash();q=json.loads((c.op/'quiesce.json').read_text());os.kill(q['worker']['pid'],9)
        (c.opt/'lib/opkg/info/nfqws2-asus.control').write_text('Package: nfqws2-asus\nVersion: changed\nArchitecture: aarch64-3.10\n')
        release.touch();out,err=p.communicate(timeout=10);self.assertEqual(p.returncode,0,out+err)
        job=json.loads((c.state/'operations.json').read_text())['operations'][c.id];self.assertEqual(job['code'],'recovery_required',job)
        self.assertEqual(c.commands(),['stop']);self.assertFalse((c.base/'installs').exists());self.assertFalse((c.service.run/'pid').exists())
    def test_lost_guardian_never_replays_saved_running_intent(self):
        c=self.c;c.service.running();p,release=self.guarded_crash();q=json.loads((c.op/'quiesce.json').read_text());os.kill(q['worker']['pid'],9);p.kill();p.communicate(timeout=3);release.touch()
        until=time.monotonic()+3
        while Path('/proc/'+str(q['installer']['pid'])+'/exe').exists() and time.monotonic()<until:time.sleep(.01)
        before=(c.state/'operations.json').read_bytes();ticket=(c.state/'transaction.json').read_bytes()
        r=subprocess.run([str(c.php),'-n',str(c.entry),'restore-before-install',c.id],capture_output=True,timeout=3)
        self.assertEqual(r.returncode,1,r.stdout+r.stderr);self.assertEqual((c.state/'operations.json').read_bytes(),before);self.assertEqual((c.state/'transaction.json').read_bytes(),ticket)
        self.assertEqual(c.commands(),['stop']);self.assertFalse((c.service.run/'pid').exists());self.assertFalse((c.base/'installs').exists())
    def test_guardian_can_restore_when_killed_before_the_first_stop(self):
        c=self.c;c.service.running();p,release=self.guarded_crash("$this->ticket($id,'stopping',['installer'=>$installer,'intent'=>$checkpoint['intent']])")
        self.assertEqual(c.commands(),[]);q=json.loads((c.op/'quiesce.json').read_text());os.kill(q['worker']['pid'],9);release.touch();out,err=p.communicate(timeout=10)
        self.assertEqual(p.returncode,0,out+err);job=json.loads((c.state/'operations.json').read_text())['operations'][c.id]
        self.assertEqual(job['core_state'],'running',job);self.assertEqual(c.commands(),['stop','start']);self.assertFalse((c.base/'installs').exists())
        pid=int((c.service.run/'pid').read_text());c.service.identities.append((pid,Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19]))
    def test_snapshot_enospc_restores_running_active_config_and_retains_diagnostic(self):
        c=self.c;c.service.running();active=c.service.run/'runtime.conf';active.write_text('ACTIVE=good\n');active.chmod(0o600)
        draft=c.opt/'etc/nfqws2/nfqws2.conf';draft.write_text('UNAPPLIED DRAFT');before=draft.read_bytes()
        self.inject("AsusUpdateSnapshot::capture($env['opt'],$this->settings($id),$this->owner());","throw new RuntimeException('insufficient_space');")
        result=c.execute();self.assertEqual(result['code'],'insufficient_space',result);self.assertEqual(result['core_state'],'running');self.assertEqual(c.commands(),['stop','stop','start'])
        self.assertEqual((c.service.run/'runtime.conf').read_text(),'ACTIVE=good\n');self.assertEqual(draft.read_bytes(),before);self.assertFalse((c.op/'boundary.json').exists());self.assertFalse((c.base/'installs').exists())
    def test_waiting_and_latched_off_intents_survive_the_transaction(self):
        for mode in ['waiting','latched']:
            with self.subTest(mode=mode):
                c=self.c;(c.service.run/'enabled').touch(mode=0o600)
                if mode=='waiting':(c.service.base/'no-wan').touch()
                else:
                    config=c.opt/'etc/nfqws2/restart-schedule.conf';config.write_text('enabled=0\ninterval_hours=24\nwatchdog_enabled=1\nrevision='+'a'*32+'\nwatchdog_revision='+'b'*32+'\n');config.chmod(0o600)
                    latch='b'*32+' 3 0 locked\n';(c.service.run/'watchdog-state').write_text(latch);(c.service.run/'watchdog-state').chmod(0o600)
                    data=json.loads((c.base/'config.json').read_text());data['service']['config']=str(config.parent);(c.base/'config.json').write_text(json.dumps(data))
                result=c.execute();self.assertEqual(result['state'],'succeeded',result);self.assertEqual(result['core_state'],'waiting_for_wan' if mode=='waiting' else 'stopped')
                self.assertEqual(c.commands(),['stop','start'] if mode=='waiting' else ['stop'])
                if mode=='latched':self.assertEqual((c.service.run/'watchdog-state').read_text(),latch);self.assertTrue((c.service.run/'enabled').exists())
                c.doCleanups();self.c=apply_fixtures.PackageUpdateApplyTests();self.c.setUp();self.addCleanup(self.c.doCleanups)
    def test_partial_stop_failure_never_claims_the_existing_pid_as_restored(self):
        c=self.c;old=c.service.running();original=c.service.core.read_text();c.service.core.write_text(original.replace('stop) if [','stop) rm -f '+shlex.quote(str(c.service.run/'enabled'))+'; exit 1\nif [',1))
        result=c.execute();self.assertEqual(result['code'],'recovery_required',result);self.assertIsNone(old.poll());self.assertNotIn('core_state',result)
        self.assertEqual(c.commands(),['stop','stop']);self.assertFalse((c.base/'installs').exists());self.assertFalse((c.op/'quiesce-result.json').exists())
    def test_guardian_recovers_after_deadline_without_replaying_install(self):
        c=self.c;c.service.running();p,release=self.guarded_crash(deadline=.12);time.sleep(.16);release.touch()
        out,err=p.communicate(timeout=10);self.assertEqual(p.returncode,0,out+err);self.assertEqual(err,b'')
        job=json.loads((c.state/'operations.json').read_text())['operations'][c.id]
        self.assertEqual(job['core_state'],'running',job);self.assertEqual(job['code'],'timed_out');self.assertFalse((c.base/'installs').exists())
        self.assertTrue((c.op/'cancel.json').exists());self.assertFalse((c.op/'boundary.json').exists())
        pid=int((c.service.run/'pid').read_text());c.service.identities.append((pid,Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19]))
    def test_interrupted_checkpoint_bulk_is_preindexed_without_stopping_services(self):
        c=self.c;c.service.running();active=c.service.run/'runtime.conf';active.write_bytes(b'x'*1048576);active.chmod(0o600)
        app=c.base/'checkpoint-app';shutil.copytree(c.application,app);path=app/'update-lifecycle.php';text=path.read_text()
        marker=c.base/'checkpoint-copy-marker';needle='try{if(fwrite($f,$raw)!==strlen($raw)'
        self.assertIn(needle,text);text=text.replace(needle,'if($name==="runtime.conf"){fwrite($f,substr($raw,0,4096));fflush($f);file_put_contents('+json.dumps(str(marker))+',"held");while(true)usleep(10000);}'+needle,1);path.write_text(text)
        directory=c.op/'service-state';code='require $argv[1]."/update-lifecycle.php";(new AsusUpdateLifecycle(json_decode($argv[2],true)))->checkpoint($argv[3]);'
        proc=subprocess.Popen([str(c.php),'-n','-r',code,str(app),json.dumps(c.service.options),str(directory)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            until=time.monotonic()+3
            while not marker.exists() and proc.poll() is None and time.monotonic()<until:time.sleep(.005)
            self.assertTrue(marker.exists());proc.kill();proc.communicate(timeout=3)
        finally:
            if proc.poll() is None:proc.kill();proc.communicate()
        ledger=json.loads((directory/'staging.json').read_text())['files'];self.assertEqual(ledger['.stage-runtime.conf']['size'],1048576)
        self.assertEqual((directory/'.stage-runtime.conf').stat().st_size,4096);self.assertEqual(c.commands(),[]);self.assertFalse((c.op/'quiesce.json').exists())
        note=directory/'operator-note';note.write_text('KEEP')
        code='require $argv[1]."/update-store.php";$s=new AsusUpdateStore($argv[2],(int)$argv[3]);(new ReflectionMethod($s,"clean"))->invoke($s,$argv[4]);'
        r=subprocess.run([str(c.php),'-n','-r',code,str(c.application),str(c.state),str(os.getuid()),c.id],capture_output=True,timeout=3)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertFalse((directory/'.stage-runtime.conf').exists());self.assertEqual(note.read_text(),'KEEP');self.assertEqual(c.commands(),[])
    def test_incoherent_running_without_enabled_is_refused_before_stop(self):
        c=self.c;child=c.service.running();(c.service.run/'enabled').unlink();result=c.execute()
        self.assertEqual(result['state'],'failed',result);self.assertEqual(result['code'],'invalid_state');self.assertEqual(c.commands(),[]);self.assertIsNone(child.poll())
        self.assertFalse((c.base/'installs').exists());self.assertFalse((c.op/'quiesce.json').exists());self.assertFalse((c.service.run/'enabled').exists())
    def test_receipt_failure_before_boundary_restores_attested_old_service(self):
        c=self.c;c.service.running();self.inject("$this->store->writeFile('operations/'.$id.'/services-stopped.json'", "throw new RuntimeException('insufficient_space');")
        result=c.execute();self.assertEqual(result['state'],'failed',result);self.assertEqual(result['code'],'insufficient_space');self.assertEqual(result['core_state'],'running')
        self.assertFalse((c.op/'boundary.json').exists());self.assertFalse((c.base/'installs').exists());self.assertEqual(c.commands(),['stop','stop','start'])
        self.assertTrue(json.loads((c.op/'quiesce-result.json').read_text())['restored'])
    def test_changed_original_configuration_after_stop_is_never_started_or_overwritten(self):
        c=self.c;c.service.running();needle="if($this->original($this->prepare->environment(),$candidate,$id)!==$q['attestation'])"
        config=c.opt/'etc/nfqws2/nfqws2.conf';self.inject(needle,'file_put_contents('+json.dumps(str(config))+',"CHANGED BY OTHER OWNER");')
        result=c.execute();self.assertEqual(result['state'],'failed',result);self.assertEqual(result['code'],'recovery_required');self.assertEqual(c.commands(),['stop'])
        self.assertFalse((c.base/'installs').exists());self.assertEqual(config.read_text(),'CHANGED BY OTHER OWNER')
    def test_original_attestation_ignores_only_validated_live_learning(self):
        c=self.c;auto=c.opt/'etc/nfqws2/lists/auto.list';auto.write_text('one.example\n');auto.chmod(0o600)
        first=self.attest();self.assertIn('proof',first)
        auto.write_text('one.example\ntwo.example\n');self.assertEqual(self.attest(),first)
        config=c.opt/'etc/nfqws2/nfqws2.conf';config.write_text('OWNER CHANGED CONFIG');self.assertNotEqual(self.attest(),first)
    def test_health_learning_may_appear_but_enabled_and_private_guards_remain_attested(self):
        c=self.c;first=self.attest();self.assertIn('proof',first)
        directory=c.opt/'etc/nfqws2/ip-health';directory.mkdir(mode=0o700,exist_ok=True);path=directory/'bans.json'
        state={'schema_version':1,'enabled':True,'generation':'none','entries':{},'history':{},'recheck':[]}
        path.write_text(json.dumps(state));path.chmod(0o600);self.assertEqual(self.attest(),first)
        state['history']={'8.8.8.8':int(time.time())};path.write_text(json.dumps(state));self.assertEqual(self.attest(),first)
        state['enabled']=False;path.write_text(json.dumps(state));self.assertNotEqual(self.attest(),first)
        path.chmod(0o666);self.assertIn('error',self.attest())
    def test_health_atomic_writer_is_locked_out_of_the_entire_static_projection(self):
        c=self.c;directory=c.opt/'etc/nfqws2/ip-health';directory.mkdir(mode=0o700)
        state={'schema_version':1,'enabled':True,'generation':'none','entries':{},'history':{},'recheck':[]}
        bans=directory/'bans.json';bans.write_text(json.dumps(state));bans.chmod(0o600)
        lock=directory/'state.lock';lock.touch(mode=0o600);baseline=self.attest();self.assertIn('proof',baseline)
        temp=directory/'.write-0123456789abcdef01234567';temp.write_text(json.dumps(state));temp.chmod(0o600)
        with lock.open('r+b') as held:
            fcntl.flock(held,fcntl.LOCK_EX)
            def finish_write():os.replace(temp,bans);fcntl.flock(held,fcntl.LOCK_UN)
            writer=threading.Timer(.12,finish_write);writer.start()
            try:observed=self.attest()
            finally:writer.join()
        self.assertEqual(observed,baseline);self.assertEqual(self.attest(),baseline)
    def test_preparation_estimate_cannot_race_an_atomic_health_temp_disappearing(self):
        c=self.c;directory=c.opt/'etc/nfqws2/ip-health';directory.mkdir(mode=0o700)
        state={'schema_version':1,'enabled':True,'generation':'none','entries':{},'history':{},'recheck':[]}
        bans=directory/'bans.json';bans.write_text(json.dumps(state));bans.chmod(0o600)
        lock=directory/'state.lock';lock.touch(mode=0o600);temp=directory/'.write-0123456789abcdef01234567';temp.write_text(json.dumps(state));temp.chmod(0o600)
        app=c.base/'estimate-app';app.mkdir(mode=0o700)
        for source in apply_fixtures.PUBLIC.glob('*.php'):shutil.copyfile(source,app/source.name)
        path=app/'update-prepare.php';text=path.read_text();needle='$s=@lstat($p);if(!$s)return;'
        self.assertIn(needle,text);path.write_text(text.replace(needle,needle+"if(str_contains($relative,'/.write-'))usleep(200000);",1))
        with lock.open('r+b') as held:
            fcntl.flock(held,fcntl.LOCK_EX)
            def finish_write():os.replace(temp,bans);fcntl.flock(held,fcntl.LOCK_UN)
            writer=threading.Timer(.05,finish_write);writer.start()
            try:
                code='require $argv[1]."/update-prepare.php";try{AsusUpdateSnapshot::estimate($argv[2],(int)$argv[3]);echo "estimated";}catch(Throwable $e){echo $e->getMessage();}'
                r=subprocess.run([str(c.php),'-n','-r',code,str(app),str(c.opt),str(os.getuid())],capture_output=True,text=True,timeout=5)
            finally:writer.join()
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stdout,'estimated');self.assertEqual(r.stderr,'')
    def test_dynamic_file_exclusions_do_not_allow_links_or_custom_list_changes(self):
        c=self.c;lists=c.opt/'etc/nfqws2/lists';custom=lists/'custom-auto.list';custom.write_text('first.example\n');custom.chmod(0o600)
        first=self.attest();self.assertIn('proof',first);custom.write_text('second.example\n');self.assertNotEqual(self.attest(),first)
        auto=lists/'auto.list';auto.symlink_to(custom);self.assertIn('error',self.attest())
    def test_active_runtime_restore_never_applies_the_saved_draft(self):
        c=self.c;c.service.running();active=c.service.run/'runtime.conf';active.write_text('ACTIVE_SETTING=old\n');active.chmod(0o600)
        draft=c.opt/'etc/nfqws2/nfqws2.conf';draft.write_text('UNAPPLIED INVALID OWNER DRAFT');before=draft.read_bytes()
        core=c.service.core.read_text()
        core=core.replace('start) : >','start) cat "$CONFFILE" > '+shlex.quote(str(c.base/'used-config'))+' || exit 9\n: >',1);c.service.core.write_text(core)
        code='require $argv[1]."/update-lifecycle.php";try{$v=new AsusUpdateLifecycle(json_decode($argv[2],true));$v->checkpoint($argv[3]);$v->stop(true);echo json_encode(["state"=>$v->restoreCheckpoint($argv[3])]);}catch(Throwable $e){echo json_encode(["error"=>$e->getMessage()]);}'
        r=subprocess.run([str(c.php),'-n','-r',code,str(apply_fixtures.PUBLIC),json.dumps(c.service.options),str(c.base/'service-checkpoint')],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');self.assertEqual(json.loads(r.stdout),{'state':'running'})
        self.assertEqual((c.base/'used-config').read_text(),'ACTIVE_SETTING=old\n');self.assertEqual(draft.read_bytes(),before)
        pid=int((c.service.run/'pid').read_text());c.service.identities.append((pid,Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19]))
    def test_checkpoint_read_does_not_treat_its_own_atime_update_as_a_mutation(self):
        c=self.c;c.service.running();active=c.service.run/'runtime.conf';active.write_text('ACTIVE=old\n');active.chmod(0o600)
        for path in c.service.run.iterdir():os.utime(path,(time.time()-172800,time.time()-172800))
        code='require $argv[1]."/update-lifecycle.php";try{$v=new AsusUpdateLifecycle(json_decode($argv[2],true));$v->checkpoint($argv[3]);echo "captured";}catch(Throwable $e){echo $e->getMessage();}'
        r=subprocess.run([str(c.php),'-n','-r',code,str(apply_fixtures.PUBLIC),json.dumps(c.service.options),str(c.base/'service-checkpoint')],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stdout,'captured');self.assertEqual(r.stderr,'')
    def test_live_guardian_identity_blocks_legacy_mutations_before_child_registration(self):
        c=self.c;gate=c.base/'guardian-gate';child=c.base/'gated-child.php';child.write_text('<?php file_put_contents($argv[1],(string)getmypid());while(!is_file($argv[2]))usleep(1000);')
        driver=c.base/'guardian.php';driver.write_text('<?php require $argv[1]."/update-watchdog.php";$s=new AsusUpdateStore($argv[2],(int)$argv[3]);(new AsusUpdateWatchdog($s,(int)$argv[3]))->run($argv[4],[PHP_BINARY,"-n",$argv[5],$argv[6],$argv[7]],AsusUpdateStore::uptime()+5);')
        p=subprocess.Popen([str(c.php),'-n',str(driver),str(apply_fixtures.PUBLIC),str(c.state),str(os.getuid()),c.id,str(child),str(c.base/'guarded-child-pid'),str(gate)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            until=time.monotonic()+2
            while not (c.base/'guarded-child-pid').exists() and time.monotonic()<until:time.sleep(.005)
            self.assertTrue((c.base/'guarded-child-pid').exists())
            db=json.loads((c.state/'operations.json').read_text());job=db['operations'][c.id]
            self.assertEqual(job.get('identity',{}).get('pid'),p.pid,'legacy Guard must see the surviving guardian, never a dead child')
            db['operations'][c.id]['apply_uptime']=0;(c.state/'operations.json').write_text(json.dumps(db))
            code='require $argv[1]."/update-guard.php";try{$s=new AsusUpdateStore($argv[2],(int)$argv[3]);$f=(new AsusUpdateGuard($s,(int)$argv[3]))->mutationLease();fclose($f);echo "allowed";}catch(Throwable $e){echo $e->getMessage();}'
            result=subprocess.check_output([str(c.php),'-n','-r',code,str(apply_fixtures.PUBLIC),str(c.state),str(os.getuid())],timeout=5).decode();self.assertEqual(result,'busy')
        finally:
            gate.touch();p.communicate(timeout=5)
    def test_running_writer_changes_are_captured_only_after_stop(self):
        c=self.c;lists=c.opt/'etc/nfqws2/lists';lists.mkdir(mode=0o755,exist_ok=True);auto=lists/'auto.list';auto.write_text('prepared.example\n');auto.chmod(0o600)
        self.prepared_settings();gate=c.base/'writer-enabled';gate.touch()
        finished=c.base/'writer-finished'
        writer=subprocess.Popen([sys.executable,'-c','import pathlib,sys,time; g=pathlib.Path(sys.argv[1]); p=pathlib.Path(sys.argv[2]); n=0\nwhile g.exists():\n n+=1;p.write_text("learned-%d.example\\n"%n);time.sleep(.01)\npathlib.Path(sys.argv[3]).touch()',str(gate),str(auto),str(finished)])
        self.addCleanup(lambda:(writer.terminate(),writer.wait()) if writer.poll() is None else None)
        original=c.service.core.read_text();c.service.core.write_text(original.replace('case "$1" in','case "$1" in\nstop) rm -f '+shlex.quote(str(gate))+'; while [ ! -f '+shlex.quote(str(finished))+' ]; do sleep .01; done;;\nesac\ncase "$1" in',1))
        until=time.monotonic()+2
        while auto.read_text()=='prepared.example\n' and time.monotonic()<until:time.sleep(.01)
        self.assertNotEqual(auto.read_text(),'prepared.example\n');c.service.running();result=c.execute()
        self.assertEqual(result['state'],'succeeded',result);self.assertEqual(c.commands(),['stop','start'])
        writer.wait(timeout=2);saved=c.op/'quiesced-backup/etc/nfqws2/lists/auto.list'
        self.assertEqual(saved.read_bytes(),auto.read_bytes());self.assertTrue((c.op/'quiesced-backup/snapshot.json').is_file())
    def test_stopped_core_still_quiesces_its_observer_without_starting(self):
        c=self.c;observer=c.base/'observer-active';observer.touch()
        original=c.service.core.read_text();c.service.core.write_text(original.replace('stop) if [','stop) rm -f '+shlex.quote(str(observer))+'\nif [',1))
        result=c.execute();self.assertEqual(result['state'],'succeeded',result)
        self.assertEqual(result['core_state'],'stopped');self.assertEqual(c.commands(),['stop']);self.assertFalse(observer.exists())


if __name__=='__main__':unittest.main()
