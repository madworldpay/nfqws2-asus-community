import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import test_lab as lab

HERE=Path(__file__).resolve().parent
PHP=os.environ.get('PHP_TEST_BINARY','/usr/bin/php')


class Transaction(unittest.TestCase):
    def run_case(self,case,was_running=True,start_after=True):
        with tempfile.TemporaryDirectory()as root:
            code='''require $argv[1].'/platform.php';
            $file=$argv[2].'/device-profiles-transaction.php';
            if(!is_file($file)){echo json_encode(['error'=>'missing_transaction']);exit;}
            require $file;$store=new NfqwsDeviceProfilesState($argv[3],(int)$argv[7]);
            $old=['mode'=>'common','value'=>'before'];$next=['mode'=>'split','value'=>'after'];
            $store->write('active.json',$old);$running=$argv[5]==='1';$calls=[];$case=$argv[4];
            $driver=[
              'running'=>fn()=>$running,
              'validate'=>function($v)use(&$calls,$case){$calls[]='validate';if($case==='validate-fail')throw new RuntimeException('invalid_profile_engine');},
              'stop'=>function()use(&$running,&$calls){$calls[]='stop';$running=false;},
              'start'=>function()use(&$running,&$calls,$store,$case){$calls[]='start';
                if($store->read('active.json')['value']==='after'&&in_array($case,['start-fail','restore-fail'],true))throw new RuntimeException('profile_start_failed');
                if($case==='restore-fail')throw new RuntimeException('restore_start_failed');$running=true;},
              'check'=>function()use(&$running,&$calls){$calls[]='check';if(!$running)throw new RuntimeException('queue_unavailable');}
            ];
            $job=['id'=>str_repeat('a',32),'state'=>'queued','phase'=>'queued','request_id'=>str_repeat('b',32),'revision'=>str_repeat('c',64)];
            try{$tx=new NfqwsDeviceProfilesTransaction($store,$driver);
              if(in_array($case,['interrupted','foreign-active'],true)){
                $running=false;$job+=['before_active'=>$old,'desired'=>$next,'was_running'=>$argv[5]==='1'];$job['state']='running';
                $store->write('active.json',$case==='foreign-active'?['mode'=>'common','value'=>'foreign']:$next);
                $store->write('job.json',$job);$tx->recover($job);
              }else $tx->execute($job,$next,$argv[6]==='1');}
            catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);exit;}
            echo json_encode(['active'=>$store->read('active.json'),'job'=>$store->read('job.json'),'running'=>$running,'calls'=>$calls]);'''
            p=subprocess.run([PHP,'-n','-r',code,str(lab.PUBLIC),str(HERE),root,case,
                              '1'if was_running else'0','1'if start_after else'0',str(os.getuid())],
                             capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
            return json.loads(p.stdout)

    def test_validation_failure_never_stops_working_service_or_replaces_active(self):
        result=self.run_case('validate-fail');self.assertNotIn('error',result)
        self.assertEqual(result['active']['value'],'before');self.assertTrue(result['running'])
        self.assertEqual(result['calls'],['validate']);self.assertEqual(result['job']['code'],'invalid_profile_engine')

    def test_failed_new_start_restores_exact_old_pointer_and_running_state(self):
        result=self.run_case('start-fail');self.assertNotIn('error',result)
        self.assertEqual(result['active']['value'],'before');self.assertTrue(result['running'])
        self.assertTrue(result['job']['recovered']);self.assertEqual(result['job']['original_code'],'profile_start_failed')
        self.assertEqual(result['calls'],['validate','stop','start','stop','start','check'])

    def test_previous_off_state_is_restored_after_failed_activation(self):
        result=self.run_case('start-fail',False);self.assertNotIn('error',result)
        self.assertEqual(result['active']['value'],'before');self.assertFalse(result['running'])
        self.assertTrue(result['job']['recovered'])

    def test_save_runtime_without_start_keeps_previously_stopped_service_off(self):
        result=self.run_case('ok',False,False);self.assertNotIn('error',result)
        self.assertEqual(result['active']['value'],'after');self.assertFalse(result['running'])
        self.assertEqual(result['job']['state'],'succeeded');self.assertEqual(result['calls'],['validate','stop'])

    def test_success_is_reported_only_after_running_queue_check(self):
        result=self.run_case('ok');self.assertNotIn('error',result)
        self.assertEqual(result['active']['value'],'after');self.assertTrue(result['running'])
        self.assertEqual(result['job']['state'],'succeeded');self.assertEqual(result['calls'],['validate','stop','start','check'])

    def test_failed_recovery_keeps_first_failure_and_reports_recovery_required(self):
        result=self.run_case('restore-fail');self.assertNotIn('error',result)
        self.assertEqual(result['active']['value'],'before')
        self.assertFalse(result['job']['recovered']);self.assertEqual(result['job']['code'],'recovery_required')
        self.assertEqual(result['job']['original_code'],'profile_start_failed')

    def test_detached_guard_recovers_an_interrupted_partial_activation(self):
        result=self.run_case('interrupted');self.assertNotIn('error',result)
        self.assertEqual(result['active']['value'],'before');self.assertTrue(result['running'])
        self.assertEqual(result['job']['code'],'worker_interrupted');self.assertTrue(result['job']['recovered'])
        self.assertEqual(result['calls'],['stop','start','check'])

    def test_recovery_never_replaces_a_foreign_active_pointer_or_stops_its_service(self):
        result=self.run_case('foreign-active');self.assertNotIn('error',result)
        self.assertEqual(result['active']['value'],'foreign');self.assertEqual(result['calls'],[])
        self.assertEqual(result['job']['code'],'recovery_required');self.assertFalse(result['job']['recovered'])

if __name__=='__main__':unittest.main()
