"""Resume waits for a validator's short journal write, without replaying mutations."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from test_dpi_normalize import PHP, PUBLIC
from test_smartdns_profile import profile


class SmartDnsResumeReadRetryTests(unittest.TestCase):
    def run_case(self, mode):
        code = r'''require $argv[1].'/smartdns-lifecycle.php';
        if(!method_exists(AsusSmartDnsLifecycle::class,'readStatus')){echo json_encode(['error'=>'missing_resume_read_retry']);exit;}
        $store=new AsusSmartDnsStore($argv[2],(int)$argv[3]);$tries=0;$mode=$argv[4];
        $reader=function()use($store,&$tries,$mode){$tries++;if($mode==='invalid')throw new RuntimeException('invalid_state');if($mode==='busy')throw new RuntimeException('busy');return $store->status();};
        touch($argv[2].'/reader-ready');$start=hrtime(true);
        try{$value=(new ReflectionMethod(AsusSmartDnsLifecycle::class,'readStatus'))->invoke(null,$reader,$start+(in_array($mode,['held','busy'],true)?300000000:3000000000));$out=['state'=>$value['state']];}
        catch(Throwable $e){$out=['error'=>$e->getMessage()];}
        $out['tries']=$tries;$out['elapsed']=(hrtime(true)-$start)/1e9;echo json_encode($out);'''
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'state'
            root.mkdir(mode=0o700)
            lock = root/'state.lock'
            lock.touch(mode=0o600)
            with lock.open('r') as held:
                fcntl.flock(held, fcntl.LOCK_EX)
                def release():
                    end = time.monotonic()+4
                    while not (root/'reader-ready').exists() and time.monotonic()<end:
                        time.sleep(.01)
                    time.sleep(.25)
                    fcntl.flock(held, fcntl.LOCK_UN)
                thread = threading.Thread(target=release) if mode=='release' else None
                if thread:
                    thread.start()
                r = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid()),mode],capture_output=True,text=True,timeout=5)
                if thread:
                    thread.join()
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertEqual(r.stderr,'')
            return json.loads(r.stdout)

    def test_real_journal_write_lock_is_readable_after_release(self):
        out=self.run_case('release')
        self.assertEqual(out.get('state'),'idle',out)
        self.assertGreaterEqual(out['elapsed'],.2)
        self.assertLess(out['elapsed'],1.5)

    def test_a_held_lock_has_a_bounded_deadline(self):
        out=self.run_case('held')
        self.assertEqual(out.get('error'),'busy',out)
        # One store read may wait up to one second for its journal lock.
        self.assertGreaterEqual(out['elapsed'],.9)
        self.assertLess(out['elapsed'],1.5)

    def test_passive_busy_errors_retry_only_until_deadline(self):
        out=self.run_case('busy')
        self.assertEqual(out.get('error'),'busy',out)
        self.assertGreaterEqual(out['tries'],2)
        self.assertGreaterEqual(out['elapsed'],.25)
        self.assertLess(out['elapsed'],1)

    def test_other_read_errors_are_not_retried(self):
        out=self.run_case('invalid')
        self.assertEqual(out.get('error'),'invalid_state',out)
        self.assertEqual(out['tries'],1)


class SmartDnsQueuedResumeGenerationTests(unittest.TestCase):
    """The real root entry waits before loading code that may switch DNS."""
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.app=self.root/'app';self.app.mkdir()
        for file in PUBLIC.glob('*.php'):
            (self.app/file.name).write_bytes(file.read_bytes())
        self.dns=self.root/'dns';self.updates=self.root/'updates';self.engine=self.root/'engine'
        self.updates.mkdir(mode=0o700);self.lock=self.updates/'apply.lock';self.lock.touch(mode=0o600)
        self.attempted=self.app/'lease-attempted';self.loaded=self.root/'loaded-generation'
        # Observe real lease attempts; its locking and authorization stay intact.
        guard=self.app/'update-guard.php';source=guard.read_text()
        needle='public function mutationLease()\n    {'
        self.assertIn(needle,source)
        guard.write_text(source.replace(needle,needle+'\n        file_put_contents(__DIR__.\'/lease-attempted\',\'1\');',1))
        self.module=(PUBLIC/'smartdns-lifecycle.php').read_text()
        self.write_generation('old')
        source=(PUBLIC.parents[2]/'asus/smartdns/control.php').read_text()
        uid=os.getuid()
        source=source.replace(r'/^Uid:\s+0\s+0\s+0\s+0\s*$/m',rf'/^Uid:\s+{uid}\s+{uid}\s+{uid}\s+{uid}\s*$/m')
        source=source.replace('/opt/share/nfqws-asus-web/',str(self.app)+'/')
        source=source.replace('/opt/etc/nfqws-asus-web/smartdns/resume-intent.json',str(self.dns/'resume-intent.json'))
        source=source.replace('new AsusUpdateStore()',f'new AsusUpdateStore({json.dumps(str(self.updates))},{uid})')
        source=source.replace('new AsusSmartDnsStore()',f'new AsusSmartDnsStore({json.dumps(str(self.dns))},{uid})')
        installer=f'new AsusSmartDnsInstaller({json.dumps(str(self.engine))},{uid})'
        source=source.replace('new AsusSmartDnsInstaller()',installer)
        source=source.replace(f'new AsusSmartDnsNativeBackend($store,{installer})',f'new AsusSmartDnsNativeBackend($store,{installer},[\'library\'=>{json.dumps(str(self.root/"library"))}],[\'owner\'=>{uid}])')
        source=source.replace('new AsusSmartDnsLifecycle($store,$backend)',f'new AsusSmartDnsLifecycle($store,$backend,{installer})')
        source=source.replace("$s['uid']!==0",f"$s['uid']!=={uid}")
        self.control=self.root/'control.php';self.control.write_text(source)

    def write_generation(self,generation):
        # Only observe module loading. Every real lifecycle method is unchanged.
        marker='file_put_contents('+json.dumps(str(self.loaded))+','+json.dumps(generation)+');'
        (self.app/'smartdns-lifecycle.php').write_text(self.module.replace('<?php','<?php\n'+marker,1))

    def save_consent(self):
        code='''require $argv[1].'/smartdns-store.php';$store=new AsusSmartDnsStore($argv[2],(int)$argv[3]);$p=json_decode(stream_get_contents(STDIN),true);$store->saveIntent(['schema_version'=>1,'profile'=>$p,'profile_hash'=>AsusSmartDnsProfile::hash($p),'engine_sha'=>str_repeat('a',64),'source_request_id'=>str_repeat('b',32)]);'''
        result=subprocess.run([PHP,'-n','-r',code,str(self.app),str(self.dns),str(os.getuid())],input=json.dumps(profile()),capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return (self.dns/'resume-intent.json').read_bytes()

    def start_resume(self):
        process=subprocess.Popen([PHP,'-n','-f',str(self.control),'--','resume'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(self.stop_process,process)
        return process

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.kill();process.communicate()

    def wait_for_lease(self,process):
        end=time.monotonic()+3
        while not self.attempted.exists() and process.poll() is None and time.monotonic()<end:
            time.sleep(.01)
        self.assertTrue(self.attempted.exists(),'resume must reach the real updater lease')
        self.assertIsNone(process.poll(),'resume must wait while apply.lock is held')

    def assert_safe_missing_engine(self,process,consent):
        output,error=process.communicate(timeout=5)
        self.assertEqual(error,'')
        self.assertEqual(process.returncode,1,output)
        self.assertEqual(json.loads(output),{'state':'action_required','code':'engine_changed'})
        self.assertEqual((self.dns/'resume-intent.json').read_bytes(),consent,'waiting or stale code must never consume saved consent')
        self.assertFalse(self.engine.exists(),'the test must not install an engine or alter DNS')

    def test_held_apply_lease_prevents_loading_smartdns_action_code(self):
        consent=self.save_consent()
        with self.lock.open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);process=self.start_resume()
            try:
                self.wait_for_lease(process)
                self.assertFalse(self.loaded.exists(),'queued resume must acquire apply.lock before loading SmartDNS classes')
            finally:
                fcntl.flock(lock,fcntl.LOCK_UN)
                self.assert_safe_missing_engine(process,consent)

    def test_resume_loads_current_generation_after_update_releases_lease(self):
        consent=self.save_consent()
        with self.lock.open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);process=self.start_resume()
            try:
                self.wait_for_lease(process)
                self.write_generation('new')
            finally:
                fcntl.flock(lock,fcntl.LOCK_UN)
                self.assert_safe_missing_engine(process,consent)
        self.assertEqual(self.loaded.read_text(),'new','a queued resume must never execute the pre-update lifecycle generation')

    def test_resume_without_saved_consent_is_inert_even_during_update(self):
        with self.lock.open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);process=self.start_resume()
            try:
                output,error=process.communicate(timeout=3)
            finally:
                fcntl.flock(lock,fcntl.LOCK_UN)
        self.assertEqual((process.returncode,output,error),(0,'',''))
        self.assertFalse(self.dns.exists())

if __name__=='__main__':
    unittest.main()
