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

    def test_upgrade_checks_saved_includes_and_repairs_permissions_reopened_before_opkg(self):
        code=r'''require $argv[1].'/smartdns-lifecycle.php';
        $root=$argv[2];$owner=(int)$argv[3];$cfg=$root.'/dnsmasq.conf';$hidden=$root.'/saved.conf';$live=$root.'/current.conf';
        $bytes="server=9.9.9.9@vpn0\n";file_put_contents($hidden,$bytes);file_put_contents($live,$bytes);
        chmod($hidden,0644);chmod($live,0666);file_put_contents($cfg,"no-resolv\nserver=127.0.0.1#6054\n");chmod($cfg,0644);
        file_put_contents($root.'/primary-dns.sh',"#!/bin/sh\nprintf '123 456\\n'\n");chmod($root.'/primary-dns.sh',0755);
        mkdir($root.'/native',0700);
        $store=new AsusSmartDnsStore($root.'/dns',$owner);
        $backend=new AsusSmartDnsNativeBackend($store,new AsusSmartDnsInstaller(),[
            'native'=>$root.'/native','config'=>$cfg,'library'=>$root],['owner'=>$owner]);
        $profile=json_decode(stream_get_contents(STDIN),true);$hash=$store->saveDraft($profile);$id=str_repeat('c',32);
        $store->savePreview(['id'=>str_repeat('b',32),'profile_hash'=>$hash,'baseline_hash'=>str_repeat('a',64),'expires_uptime'=>PHP_FLOAT_MAX]);
        $store->begin($id,$hash,str_repeat('a',64));
        $fingerprints=AsusSmartDnsConfig::collect("conf-file=$hidden\n",$owner,true)['fingerprints'];
        $backup=$store->backup(['baseline'=>['fingerprints'=>['dns_includes'=>$fingerprints]],'candidate_profile'=>$profile]);
        $store->transition($id,['applying'],['state'=>'confirmed','active'=>['profile'=>$profile,'profile_hash'=>$hash,'backup_id'=>$backup]]);
        $publish=static function(string $phase)use($root,$id,$hash){
            $state=['schema'=>'1','request_id'=>$id,'boot_id'=>trim(file_get_contents('/proc/sys/kernel/random/boot_id')),
                    'phase'=>$phase,'deadline'=>'0.000','guard_pid'=>'123','guard_ticks'=>'1',
                    'runtime_pid'=>'124','runtime_ticks'=>'1','runtime_exe'=>'/opt/smartdns','hook_created'=>'0','profile_hash'=>$hash];
            $raw='';foreach($state as $k=>$v)$raw.=$k."\t".$v."\n";file_put_contents($root.'/native/state',$raw);chmod($root.'/native/state',0600);
        };
        $mode=static function($p){clearstatcache(true,$p);return fileperms($p)&0777;};
        $publish('confirmed');chmod($hidden,0666);$restores=0;$firstMode=null;
        $deps=['digest'=>fn()=>str_repeat('e',64),'blocked'=>fn()=>false,'reconcile'=>fn()=>$store->status(),
          'rollback'=>function($id)use($store,$publish,$mode,$hidden,$live,$cfg,&$restores,&$firstMode){
            $restores++;$firstMode=$mode($hidden);$publish('rolled_back');
            file_put_contents($cfg,"conf-file=$live\n");return $store->transition($id,['confirmed'],['state'=>'rolled_back','active'=>null]);
        }];
        try {
            $life=new AsusSmartDnsLifecycle($store,$backend,null,$deps);
            $status=$life->stop('upgrade');$afterRestore=$mode($live);
            chmod($live,0666);$life->verifyUpgradeDns();$lateMode=$mode($live);
            $record=$store->transaction();
            $backups=glob($root.'/dns/backup-*.json');$permissions=[];
            foreach($backups as $file){$v=json_decode(file_get_contents($file),true);$row=($v['files'][$hidden]??$v['files'][$live]??null);if($row)$permissions[]=base64_decode($row['base64'])===$bytes&&($row['fingerprint']['file']['mode']&0777)===0666;}
            $preserved=file_get_contents($live)===$bytes&&file_get_contents($hidden)===$bytes;
            $unsafe="dhcp-script=/opt/untrusted\n";file_put_contents($live,$unsafe);chmod($live,0666);
            $failure=null;try{$life->verifyUpgradeDns();}catch(RuntimeException $e){$failure=$e->getMessage();}
            $out=['state'=>$status['state'],'before_restore'=>$firstMode,'after_restore'=>$afterRestore,'before_opkg'=>$lateMode,
                  'restores'=>$restores,'rollback_backup_intact'=>$record['backup_id']===$backup,
                  'bytes_preserved'=>$preserved,'permission_backups'=>$permissions,'unsafe_code'=>$failure,
                  'unsafe_preserved'=>$mode($live)===0666&&file_get_contents($live)===$unsafe&&glob($root.'/dns/backup-*.json')===$backups];
        } catch(Throwable $e){$out=['error'=>$e->getMessage(),'origin'=>$e->getLine()];}
        echo json_encode($out);'''
        with tempfile.TemporaryDirectory() as d:
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),d,str(os.getuid())],input=json.dumps(profile()),capture_output=True,text=True,timeout=8)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertEqual(r.stderr,'')
        self.assertEqual(json.loads(r.stdout),{
            'state':'rolled_back','before_restore':0o644,'after_restore':0o644,'before_opkg':0o644,
            'restores':1,'rollback_backup_intact':True,'bytes_preserved':True,'permission_backups':[True,True,True],
            'unsafe_code':'dns_permissions_changed','unsafe_preserved':True,
        })

    def test_updater_keeps_an_ownerless_pending_switch_blocked(self):
        code=r'''require $argv[1].'/smartdns-lifecycle.php';require $argv[1].'/update-worker.php';
        $root=$argv[2];$owner=(int)$argv[3];$profile=json_decode(stream_get_contents(STDIN),true);$store=new AsusSmartDnsStore($root.'/dns',$owner);$hash=$store->saveDraft($profile);
        $store->savePreview(['id'=>str_repeat('b',32),'profile_hash'=>$hash,'baseline_hash'=>str_repeat('a',64),'expires_uptime'=>PHP_FLOAT_MAX]);
        $store->begin(str_repeat('c',32),$hash,str_repeat('a',64));$store->transition(str_repeat('c',32),['applying'],['state'=>'awaiting_confirmation','deadline_uptime'=>1]);
        $backend=new AsusSmartDnsNativeBackend($store,new AsusSmartDnsInstaller(),['native'=>$root.'/missing-jffs'],['owner'=>$owner]);
        $worker=new AsusUpdateWorker(new AsusUpdateStore($root.'/updates',$owner),null,null,['owner'=>$owner,'dns_store'=>$store,'dns_backend'=>$backend]);
        try{(new ReflectionMethod($worker,'assertDnsUpdateReady'))->invoke($worker);echo json_encode(['value'=>'allowed']);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage(),'public_code'=>AsusUpdatePrepare::code($e),'state'=>$store->status()['state']]);}'''
        with tempfile.TemporaryDirectory() as d:
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),d,str(os.getuid())],input=json.dumps(profile()),capture_output=True,text=True,timeout=5)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');out=json.loads(r.stdout)
            self.assertEqual(out['error'],'dns_restore_required');self.assertEqual(out['public_code'],'dns_restore_required');self.assertEqual(out['state'],'conflict')

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
