"""Package/boot DNS lifecycle preserves prior consent and verifies restore first."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
from test_smartdns_profile import profile

class SmartDnsLifecycleTests(unittest.TestCase):
    def run_case(self,mode):
        code=r'''$f=$argv[1].'/smartdns-lifecycle.php';if(!is_file($f)){echo json_encode(['error'=>'missing_dns_lifecycle']);exit;}require $f;
        $mode=$argv[4];$store=new AsusSmartDnsStore($argv[2],(int)$argv[3]);$profile=json_decode(stream_get_contents(STDIN),true);$hash=AsusSmartDnsProfile::hash($profile);$id=str_repeat('c',32);$events=[];
        if($mode!=='fresh'){$store->saveDraft($profile);$store->savePreview(['id'=>str_repeat('b',32),'profile_hash'=>$hash,'baseline_hash'=>str_repeat('a',64),'expires_uptime'=>PHP_FLOAT_MAX]);$store->begin($id,$hash,str_repeat('a',64));$backup=$store->backup(['candidate_profile'=>$profile]);$store->transition($id,['applying'],['state'=>'confirmed','active'=>['profile'=>$profile,'profile_hash'=>$hash,'backup_id'=>$backup]]);}
        $deps=['digest'=>fn()=>str_repeat('e',64),'blocked'=>fn()=>false,'reconcile'=>fn()=>$store->status(),
          'rollback'=>function($id)use($store,&$events,$mode){$events[]='restore_dns';if($mode==='conflict')return $store->transition($id,['confirmed'],['state'=>'conflict','code'=>'hook_conflict']);$events[]='stop_runtime';return $store->transition($id,['confirmed'],['state'=>'rolled_back','active'=>null]);}];
        try{$life=new AsusSmartDnsLifecycle($store,null,null,$deps);$out=$life->stop($mode==='remove'?'remove':'upgrade');$out['intent']=$store->intent();$out['events']=$events;$out['active']=$store->active();$out['created']=is_dir($argv[2]);}
        catch(Throwable $e){$out=['error'=>$e->getMessage(),'intent'=>$store->intent(),'events'=>$events,'active'=>$store->active()];}echo json_encode($out);'''
        with tempfile.TemporaryDirectory() as d:
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(Path(d)/'state'),str(os.getuid()),mode],input=json.dumps(profile()),capture_output=True,text=True,timeout=5)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def test_fresh_install_has_no_profile_and_no_dns_side_effect(self):
        out=self.run_case('fresh');self.assertIsNone(out['intent']);self.assertFalse(out['created']);self.assertEqual(out['events'],[])
    def test_upgrade_saves_only_confirmed_profile_before_verified_restore(self):
        out=self.run_case('upgrade');self.assertEqual(out['state'],'rolled_back');self.assertEqual(out['events'],['restore_dns','stop_runtime'])
        self.assertEqual(out['intent']['profile']['upstreams'][0]['label'],'main');self.assertEqual(out['intent']['engine_sha'],'e'*64);self.assertIsNone(out['active'])
    def test_failed_restore_aborts_package_removal_and_retains_runtime_and_intent(self):
        out=self.run_case('conflict');self.assertEqual(out['error'],'dns_restore_failed');self.assertEqual(out['events'],['restore_dns']);self.assertIsNotNone(out['active']);self.assertIsNotNone(out['intent'])
    def test_remove_clears_resume_intent_only_after_safe_restore(self):
        out=self.run_case('remove');self.assertEqual(out['state'],'rolled_back');self.assertIsNone(out['intent']);self.assertEqual(out['events'],['restore_dns','stop_runtime'])

    def test_updater_keeps_an_ownerless_pending_switch_blocked(self):
        code=r'''require $argv[1].'/smartdns-lifecycle.php';require $argv[1].'/update-worker.php';
        $root=$argv[2];$owner=(int)$argv[3];$profile=json_decode(stream_get_contents(STDIN),true);$store=new AsusSmartDnsStore($root.'/dns',$owner);$hash=$store->saveDraft($profile);
        $store->savePreview(['id'=>str_repeat('b',32),'profile_hash'=>$hash,'baseline_hash'=>str_repeat('a',64),'expires_uptime'=>PHP_FLOAT_MAX]);
        $store->begin(str_repeat('c',32),$hash,str_repeat('a',64));$store->transition(str_repeat('c',32),['applying'],['state'=>'awaiting_confirmation','deadline_uptime'=>1]);
        $backend=new AsusSmartDnsNativeBackend($store,new AsusSmartDnsInstaller(),['native'=>$root.'/missing-jffs'],['owner'=>$owner]);
        $worker=new AsusUpdateWorker(new AsusUpdateStore($root.'/updates',$owner),null,null,['owner'=>$owner,'dns_store'=>$store,'dns_backend'=>$backend]);
        try{(new ReflectionMethod($worker,'assertDnsUpdateReady'))->invoke($worker);echo json_encode(['value'=>'allowed']);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage(),'state'=>$store->status()['state']]);}'''
        with tempfile.TemporaryDirectory() as d:
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),d,str(os.getuid())],input=json.dumps(profile()),capture_output=True,text=True,timeout=5)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');out=json.loads(r.stdout)
            self.assertEqual(out['error'],'busy');self.assertEqual(out['state'],'conflict')

class SmartDnsMaintainerBoundaryTests(unittest.TestCase):
    def test_restore_failure_aborts_before_core_or_web_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);calls=root/'calls';opt=root/'opt'
            for name,body in {
                'lib/nfqws2-asus/smartdns/control.sh':'printf "dns %s\\n" "$1" >> "'+str(calls)+'";exit 7',
                'etc/init.d/S51nfqws2':'printf "core\\n" >> "'+str(calls)+'"',
                'etc/init.d/S81nfqws-asus-web':'printf "web\\n" >> "'+str(calls)+'"',
            }.items():
                p=opt/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o700)
            source=(PUBLIC.parents[2]/'asus/ipk/unified-prerm').read_text().replace('/opt/',str(opt)+'/')
            hook=root/'prerm';hook.write_text(source)
            r=subprocess.run(['/bin/sh',str(hook),'upgrade'],capture_output=True,text=True,timeout=3)
            self.assertEqual(r.returncode,7,r.stdout+r.stderr);self.assertEqual(calls.read_text(),'dns upgrade\n')

if __name__=='__main__':unittest.main()
