"""Readonly status projects native truth; only a leased mutator reconciles it."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP,PUBLIC
from test_smartdns_profile import profile


class SmartDnsConfigJobsTests(unittest.TestCase):
    def scenario(self,mode):
        code=r'''$file=$argv[1].'/smartdns-config-jobs.php';if(!is_file($file)){echo json_encode(['error'=>'missing_config_jobs']);exit;}
        require $file;$root=$argv[2];$now=100.0;$id=str_repeat('c',32);$profile=json_decode(stream_get_contents(STDIN),true);$owner=(int)$argv[3];$mode=$argv[4];
        $store=new AsusSmartDnsStore($root,$owner,['uptime'=>function()use(&$now){return $now;}]);$hash=AsusSmartDnsProfile::hash($profile);$base=str_repeat('a',64);$native=null;
        if($mode!=='fresh'){
          $store->saveDraft($profile);
          if(str_starts_with($mode,'validation_')){$store->beginValidation($id,$hash,$base);$now=1000.0;}
          else{$store->savePreview(['id'=>str_repeat('b',32),'profile_hash'=>$hash,'baseline_hash'=>$base,'expires_uptime'=>700]);$store->begin($id,$hash,$base);
            $store->backup(['candidate_profile'=>$profile,'baseline'=>['hook'=>['state'=>'available','value'=>"#!/bin/sh\n",'mode'=>0700],'config'=>['state'=>'available','value'=>"server=9.9.9.9\n"],'server_files'=>[],'fingerprints'=>[]]]);
            $store->transition($id,['applying'],['state'=>'awaiting_confirmation','deadline_uptime'=>205]);
            $native=['schema'=>'1','request_id'=>$mode==='mismatch'?str_repeat('d',32):$id,'boot_id'=>trim(file_get_contents('/proc/sys/kernel/random/boot_id')),
              'phase'=>in_array($mode,['confirmed','edited_draft','unhealthy'],true)?'confirmed':($mode==='awaiting'?'awaiting_confirmation':'rolled_back'),
              'deadline'=>'220.000','guard_pid'=>'123','guard_ticks'=>'10','runtime_pid'=>'124','runtime_ticks'=>'11','runtime_exe'=>'/opt/lib/nfqws2-asus/smartdns-engine/'.str_repeat('e',64).'/smartdns','hook_created'=>'0','profile_hash'=>$hash];
            if($mode==='edited_draft'){$changed=$profile;$changed['upstreams'][0]['label']='a different draft';$store->saveDraft($changed);}
          }
        }
        $deps=['native'=>fn()=>$native,'healthy'=>fn()=>$mode!=='unhealthy','uptime'=>function()use(&$now){return $now;},
          'validation_owner'=>fn($job)=>['known'=>$mode!=='validation_unknown','guard_alive'=>$mode==='validation_live','anchor_alive'=>$mode==='validation_live','worker_alive'=>false,'code'=>'timed_out']];
        $jobs=new AsusSmartDnsConfigJobs($store,null,$deps);$path=$root.'/state.json';$before=is_file($path)?hash_file('sha256',$path):null;
        $status=$jobs->status();$afterRead=is_file($path)?hash_file('sha256',$path):null;$blocked=$jobs->blocksUpdate();
        $jobs->reconcile();$current=$store->status();$after=is_file($path)?hash_file('sha256',$path):null;
        echo json_encode(['status'=>$status,'current'=>$current,'before'=>$before,'after_read'=>$afterRead,'after'=>$after,'blocked_before'=>$blocked,'blocked_after'=>$jobs->blocksUpdate(),'active'=>$store->active(),'root_created'=>is_dir($root)]);'''
        with tempfile.TemporaryDirectory() as directory:
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(Path(directory)/'state'),str(os.getuid()),mode],input=json.dumps(profile()),capture_output=True,text=True,timeout=6)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)

    def test_fresh_status_and_reconcile_create_no_state(self):
        out=self.scenario('fresh');self.assertEqual(out['status']['state'],'idle')
        self.assertFalse(out['root_created']);self.assertFalse(out['blocked_before'])

    def test_automatic_native_rollback_is_visible_without_status_writes(self):
        out=self.scenario('rolled_back');self.assertEqual(out['status']['state'],'rolled_back')
        self.assertEqual(out['before'],out['after_read']);self.assertNotEqual(out['before'],out['after'])
        self.assertTrue(out['blocked_before']);self.assertFalse(out['blocked_after']);self.assertIsNone(out['active'])

    def test_lost_confirmation_reply_uses_viewed_snapshot_not_a_new_draft(self):
        out=self.scenario('edited_draft');self.assertEqual(out['status']['state'],'confirmed')
        self.assertEqual(out['before'],out['after_read']);self.assertEqual(out['current']['state'],'confirmed')
        self.assertEqual(out['active']['profile']['upstreams'][0]['label'],'main')

    def test_pending_deadline_comes_from_native_guard(self):
        out=self.scenario('awaiting');self.assertEqual(out['status']['deadline_remaining_s'],120)
        self.assertEqual(out['current']['deadline_remaining_s'],120);self.assertTrue(out['blocked_after'])

    def test_mismatched_or_unhealthy_native_state_cannot_confirm_or_unblock_update(self):
        for mode in ['mismatch','unhealthy']:
            with self.subTest(mode=mode):
                out=self.scenario(mode);self.assertEqual(out['status']['state'],'conflict')
                self.assertTrue(out['blocked_after']);self.assertIsNone(out['active'])

    def test_live_owner_survives_elapsed_time_and_unknown_proof_is_not_discarded(self):
        for mode in ['validation_live','validation_unknown']:
            with self.subTest(mode=mode):
                out=self.scenario(mode);self.assertEqual(out['current']['state'],'validating')
                self.assertEqual(out['before'],out['after']);self.assertTrue(out['blocked_after'])

    def test_dead_validation_owner_is_reconciled_only_by_the_mutator(self):
        out=self.scenario('validation_dead');self.assertEqual(out['status']['state'],'failed')
        self.assertEqual(out['before'],out['after_read']);self.assertTrue(out['blocked_before'])
        self.assertEqual(out['current']['code'],'timed_out');self.assertFalse(out['blocked_after'])

    def test_validate_launch_is_idempotent_and_refuses_reused_run_directory(self):
        code=r'''require $argv[1].'/smartdns-config-jobs.php';$root=$argv[2];$owner=(int)$argv[3];$mode=$argv[4];umask(0077);
        $store=new AsusSmartDnsStore($root.'/smartdns',$owner);$profile=json_decode(stream_get_contents(STDIN),true);$hash=$store->saveDraft($profile);$calls=0;$reads=0;$alive=false;
        if($mode==='occupied'){mkdir($root.'/smartdns/jobs',0700);mkdir($root.'/smartdns/jobs/'.str_repeat('c',32),0700);file_put_contents($root.'/smartdns/jobs/'.str_repeat('c',32).'/foreign','untouched');}
        $deps=['owner'=>$owner,'native'=>fn()=>null,'baseline'=>function()use(&$reads){$reads++;return ['hash'=>str_repeat('a',64)];},
          'lease'=>function()use($root){return fopen($root.'/lease','c');},'launch'=>function($id)use(&$calls,&$alive,$mode){$calls++;if($mode==='failed')throw new RuntimeException('launch_failed');$alive=true;},
          'validation_owner'=>function($job)use(&$alive){return ['known'=>true,'guard_alive'=>$alive,'anchor_alive'=>$alive,'worker_alive'=>$alive,'code'=>null];}];
        $jobs=new AsusSmartDnsConfigJobs($store,null,$deps);$out=[];try{$out['first']=$jobs->start(str_repeat('c',32),$hash);$out['second']=$jobs->start(str_repeat('c',32),$hash);}catch(Throwable $e){$out['error']=$e->getMessage();}
        $out['status']=$store->status();$out['calls']=$calls;$out['reads']=$reads;$out['foreign']=is_file($root.'/smartdns/jobs/'.str_repeat('c',32).'/foreign')?file_get_contents($root.'/smartdns/jobs/'.str_repeat('c',32).'/foreign'):null;echo json_encode($out);'''
        for mode in ['ready','occupied','failed']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),directory,str(os.getuid()),mode],input=json.dumps(profile()),capture_output=True,text=True,timeout=5)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');out=json.loads(p.stdout)
                if mode=='ready':
                    self.assertEqual(out['first'],out['second']);self.assertEqual(out['calls'],1);self.assertEqual(out['reads'],1)
                    self.assertEqual(out['first']['state'],'validating')
                elif mode=='occupied':
                    self.assertEqual(out['error'],'invalid_state');self.assertEqual(out['calls'],0);self.assertEqual(out['foreign'],'untouched')
                else:
                    self.assertEqual(out['error'],'launch_failed');self.assertEqual(out['status']['state'],'failed');self.assertEqual(out['calls'],1)

    def test_cleanup_retains_live_unknown_and_recent_runs(self):
        code=r'''require $argv[1].'/smartdns-config-jobs.php';$root=$argv[2];$owner=(int)$argv[3];umask(0077);$store=new AsusSmartDnsStore($root,$owner);$root=$store->directory(true);mkdir($root.'/jobs',0700);
        for($i=1;$i<=8;$i++){$id=str_pad(dechex($i),32,'0',STR_PAD_LEFT);mkdir($root.'/jobs/'.$id,0700);file_put_contents($root.'/jobs/'.$id.'/outcome',"finished\n");touch($root.'/jobs/'.$id,100+$i);}
        $old=$root.'/jobs/'.str_pad('1',32,'0',STR_PAD_LEFT);mkdir($old.'/attempt-1',0700);file_put_contents($old.'/attempt-1/candidate.conf','private');file_put_contents($old.'/runtime.pid','123');touch($old,101);
        $live=str_repeat('a',32);mkdir($root.'/jobs/'.$live,0700);file_put_contents($root.'/jobs/'.$live.'/outcome',"finished\n");
        $foreign=str_repeat('b',32);mkdir($root.'/jobs/'.$foreign,0700);file_put_contents($root.'/jobs/'.$foreign.'/foreign','KEEP');
        $jobs=new AsusSmartDnsConfigJobs($store,null,['owner'=>$owner,'native'=>fn()=>null,'validation_owner'=>fn($j)=>['known'=>true,'guard_alive'=>$j['request_id']===$live,'anchor_alive'=>false,'worker_alive'=>false,'code'=>null]]);
        try{$jobs->cleanup();echo json_encode(scandir($root.'/jobs'));}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        with tempfile.TemporaryDirectory() as d:
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(Path(d)/'state'),str(os.getuid())],capture_output=True,text=True,timeout=5)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');out=json.loads(r.stdout)
            self.assertIsInstance(out,list);self.assertEqual(set(out)-{'.','..'}, {'a'*32,'b'*32,*[format(i,'032x') for i in [6,7,8]]})



class SmartDnsValidationHandoffTests(unittest.TestCase):
    def test_activation_waits_for_known_validator_exit_without_replaying_validation(self):
        code=r"""require $argv[1].'/smartdns-config-jobs.php';$store=new AsusSmartDnsStore($argv[2],(int)$argv[3]);
        $profile=json_decode($argv[4],true);$hash=$store->saveDraft($profile);$preview=str_repeat('b',32);$store->beginValidation(str_repeat('c',32),$hash,str_repeat('d',64));
        $store->transition(str_repeat('c',32),['validating'],['state'=>'preview_ready','preview_id'=>$preview]);
        $before=hash_file('sha256',$argv[2].'/state.json');$reads=0;
        $jobs=new AsusSmartDnsConfigJobs($store,null,['validation_owner'=>function($job)use(&$reads){$reads++;return ['known'=>true,'guard_alive'=>$reads<3,'anchor_alive'=>false,'worker_alive'=>false];}]);
        $jobs->awaitValidationRelease($preview,.5);$ok=['reads'=>$reads,'unchanged'=>$before===hash_file('sha256',$argv[2].'/state.json')];
        foreach(['live','unknown']as $mode){$j=new AsusSmartDnsConfigJobs($store,null,['validation_owner'=>fn($job)=>['known'=>$mode!=='unknown','guard_alive'=>$mode==='live','anchor_alive'=>false,'worker_alive'=>false]]);try{$j->awaitValidationRelease($preview,0);$ok[$mode]='allowed';}catch(Throwable $e){$ok[$mode]=$e->getMessage();}}
        echo json_encode($ok);"""
        with tempfile.TemporaryDirectory() as directory:
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(Path(directory)/'state'),str(os.getuid()),json.dumps(profile())],capture_output=True,text=True,timeout=4)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);out=json.loads(p.stdout)
            self.assertGreaterEqual(out['reads'],3);self.assertTrue(out['unchanged']);self.assertEqual(out['live'],'busy');self.assertEqual(out['unknown'],'busy')


if __name__=='__main__':unittest.main()
