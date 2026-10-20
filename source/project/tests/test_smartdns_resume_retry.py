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

if __name__=='__main__':
    unittest.main()
