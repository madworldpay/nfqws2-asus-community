import json
import os
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


class SmartDnsJobsTests(unittest.TestCase):
    def test_elapsed_time_never_admits_a_second_job_while_original_worker_is_alive(self):
        with tempfile.TemporaryDirectory() as root:
            code = '''require $argv[1].'/smartdns-api.php';
            $i=new AsusSmartDnsInstaller($argv[2].'/managed',(int)$argv[3]);
            $j=new AsusSmartDnsJobs($i,['available'=>fn()=>['available'=>true,'code'=>'ready'],'launch'=>fn()=>null]);
            $j->start(str_repeat('a',32));$path=$argv[2].'/managed/job.json';$old=json_decode(file_get_contents($path),true);
            $old['state']='running';$old['identity']=AsusDpiRuntime::identity(getmypid());$old['started_uptime']-=181;file_put_contents($path,json_encode($old));
            try{$j->start(str_repeat('b',32));echo 'UNSAFE';}catch(Throwable $e){echo $e->getMessage();}'''
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),root,str(os.getuid())],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertEqual(p.stdout,'busy')

    def test_install_submission_is_idempotent_and_concurrent_request_is_busy(self):
        with tempfile.TemporaryDirectory() as root:
            code = '''require $argv[1].'/smartdns-api.php';$calls=0;
            $i=new AsusSmartDnsInstaller($argv[2].'/managed',(int)$argv[3]);
            $j=new AsusSmartDnsJobs($i,['available'=>fn()=>['available'=>true,'code'=>'ready'],'launch'=>function()use(&$calls){$calls++;}]);
            $a=$j->start(str_repeat('a',32));$b=$j->start(str_repeat('a',32));
            try{$j->start(str_repeat('b',32));$busy='UNSAFE';}catch(Throwable $e){$busy=$e->getMessage();}
            echo json_encode([$a,$b,$calls,$busy]);'''
            p = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), root, str(os.getuid())], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
            a,b,calls,busy = json.loads(p.stdout)
            self.assertEqual(a,b)
            self.assertEqual(calls,1)
            self.assertEqual(busy,'busy')
            self.assertEqual(a['state'],'queued')

    def test_http_contract_requires_consent_and_rejects_paths_and_unknown_fields(self):
        code = '''require $argv[1].'/smartdns-api.php';$out=[];
        foreach(json_decode(stream_get_contents(STDIN),true) as $post){try{AsusSmartDnsApi::validate($post);$out[]='ok';}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);'''
        base = {'cmd':'smartdnsinstall','csrf_token':'x','request_id':'a'*32,'consent':'install'}
        rows = [base, {**base,'consent':'no'}, {**base,'url':'https://evil.invalid'}, {**base,'request_id':'../../outside'}, {'cmd':'smartdnsstatus','csrf_token':'x'}]
        p = subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(rows),capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(json.loads(p.stdout),['ok','consent_required','invalid_request','invalid_request','ok'])
