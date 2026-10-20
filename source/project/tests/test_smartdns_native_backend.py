"""Preparing independent recovery must never copy the user's profile to JFFS."""
import hashlib
import json
import os
import resource
import signal
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_dpi_normalize import ROOT,PHP,PUBLIC
from test_smartdns_profile import profile,upstream


class SmartDnsNativeBackendTests(unittest.TestCase):
    def scenario(self,mode='ready'):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);library=root/'lib';library.mkdir(mode=0o700)
            if mode=='package_directory':library.chmod(0o755)
            jffs=root/'jffs';jffs.mkdir(mode=0o700)
            if mode=='library_alias':(root/'library-alias').symlink_to(library)
            for name in ['native-state.sh','native-common.sh','primary-dns.sh','recovery.sh','lifecycle.sh','forwarding.awk','hook-edit.awk']:
                shutil.copyfile(ROOT/'asus/smartdns'/name,library/name);(library/name).chmod(0o600)
            probe=(ROOT/'asus/smartdns/bin/aarch64-dns-probe').read_bytes()
            (library/'dns-probe').write_bytes(probe);(library/'dns-probe').chmod(0o700)
            (library/'tools.json').write_text(json.dumps({'schema_version':1,'dns_probe_sha256':hashlib.sha256(probe).hexdigest()}));(library/'tools.json').chmod(0o600)
            if mode=='wrong_probe':(library/'dns-probe').write_bytes(b'changed')
            if mode=='empty_source':(library/'recovery.sh').write_bytes(b'')
            native=jffs/'nfqws2-asus-smartdns'
            if mode=='foreign_directory':native.mkdir(mode=0o700);(native/'foreign').write_text('untouched')
            code=r'''$f=$argv[1].'/smartdns-native.php';if(!is_file($f)){echo json_encode(['error'=>'missing_native_backend']);exit;}
            require $f;$root=$argv[2];$profile=json_decode(stream_get_contents(STDIN),true);$store=new AsusSmartDnsStore($root.'/state',(int)$argv[3]);
            $paths=['native'=>$root.'/jffs/nfqws2-asus-smartdns','library'=>$root.'/lib','hook'=>$root.'/scripts/dnsmasq.postconf'];
            if($argv[4]==='library_alias')$paths['library']=$root.'/library-alias';
            $deps=['owner'=>(int)$argv[3],'baseline_dns'=>fn()=>$argv[4]!=='no_dns','primary_dns'=>fn()=>$argv[4]!=='no_primary','recovery_storage'=>fn()=>$argv[4]!=='usb_recovery'];if($argv[4]==='no_space')$deps['space']=fn()=>1;
            if(in_array($argv[4],['native_jffs_alias','usb_jffs_alias'],true)){unset($deps['recovery_storage']);$deps['mounts']=fn()=>"/dev/jffs $root/jffs ext4 rw,relatime 0 0\n";$deps['canonical_device']=fn($device)=>$argv[4]==='native_jffs_alias'?'/dev/mmcblk0p9':'/dev/sda1';}
            $backend=new AsusSmartDnsNativeBackend($store,new AsusSmartDnsInstaller(),$paths,$deps);
            try {if($argv[4]==='status')$out=$backend->state();else {$backend->prepare(['request_id'=>str_repeat('c',32),'profile_hash'=>AsusSmartDnsProfile::hash($profile)],['candidate_profile'=>$profile,'baseline'=>['hook'=>['state'=>'missing','value'=>'','mode'=>null],'config'=>['state'=>'available','value'=>$argv[4]==='local_conflict'?"address=/example.com/192.0.2.1\n":"server=9.9.9.9\n"]]]);$out=$backend->state();}}
            catch(Throwable $e){$out=['error'=>$e->getMessage()];}echo json_encode($out);'''
            domains=[{'name':'video.example.com','include_subdomains':False}] if mode=='local_conflict' else []
            def limit_write():
                signal.signal(signal.SIGXFSZ,signal.SIG_IGN)
                resource.setrlimit(resource.RLIMIT_FSIZE,(65535,65535))
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid()),mode],input=json.dumps(profile(upstream(label='PRIVATE_PROFILE_CANARY',domains=domains))),capture_output=True,text=True,timeout=5,preexec_fn=limit_write if mode=='write_failure' else None)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
            contents={str(f.relative_to(jffs)):f.read_bytes() for f in jffs.rglob('*') if f.is_file()}
            modes={str(f.relative_to(jffs)):f.stat().st_mode&0o777 for f in jffs.rglob('*')}
            return json.loads(p.stdout),contents,modes

    def test_recovery_contains_only_fixed_code_helper_and_small_identity_state(self):
        state,files,modes=self.scenario();self.assertEqual(state['phase'],'prepared')
        self.assertEqual(state['request_id'],'c'*32);self.assertEqual(state['runtime_pid'],'0')
        self.assertLess(len(files['nfqws2-asus-smartdns/state']),16384)
        self.assertIn('nfqws2-asus-smartdns/recovery.sh',files)
        for name,body in files.items():self.assertNotIn(b'PRIVATE_PROFILE_CANARY',body,name)
        for name,mode in modes.items():self.assertIn(mode,[0o700,0o600],name)

    def test_helper_tampering_or_insufficient_space_has_no_partial_recovery(self):
        for mode,code in [('wrong_probe','unsupported_binary'),('no_space','insufficient_space')]:
            with self.subTest(mode=mode):
                out,files,_=self.scenario(mode);self.assertEqual(out,{'error':code});self.assertEqual(files,{})

    def test_foreign_directory_is_never_claimed_or_overwritten(self):
        out,files,_=self.scenario('foreign_directory');self.assertEqual(out,{'error':'invalid_state'})
        self.assertEqual(files,{'nfqws2-asus-smartdns/foreign':b'untouched'})

    def test_status_on_fresh_router_creates_nothing(self):
        out,files,modes=self.scenario('status');self.assertIsNone(out);self.assertEqual(files,{});self.assertEqual(modes,{})

    def test_preexisting_dns_failure_cannot_arm_a_switch_or_create_recovery_state(self):
        out,files,_=self.scenario('no_dns');self.assertEqual(out,{'error':'native_fallback_unavailable'});self.assertEqual(files,{})

    def test_unverified_primary_daemon_cannot_arm_the_switch(self):
        out,files,_=self.scenario('no_primary');self.assertEqual(out,{'error':'primary_dns_unverified'});self.assertEqual(files,{})

    def test_local_answer_shadowing_a_selected_domain_blocks_before_jffs_writes(self):
        out,files,_=self.scenario('local_conflict');self.assertEqual(out,{'error':'existing_dns_rules'});self.assertEqual(files,{})

    def test_aliased_entware_library_is_verified_at_its_canonical_location(self):
        out,_,_=self.scenario('library_alias');self.assertEqual(out.get('phase'),'prepared')

    def test_recovery_on_usb_cannot_be_presented_as_independent(self):
        out,files,_=self.scenario('usb_recovery');self.assertEqual(out,{'error':'recovery_unavailable'});self.assertEqual(files,{})

    def test_native_jffs_device_alias_is_resolved_but_usb_alias_is_rejected(self):
        out,_,_=self.scenario('native_jffs_alias');self.assertEqual(out.get('phase'),'prepared')
        out,files,_=self.scenario('usb_jffs_alias');self.assertEqual(out,{'error':'recovery_unavailable'});self.assertEqual(files,{})

    def test_real_partial_write_failure_is_private_and_leaves_no_prepared_state(self):
        out,files,modes=self.scenario('write_failure');self.assertEqual(out,{'error':'insufficient_space'});self.assertEqual(files,{});self.assertEqual(modes,{})

    def test_empty_recovery_code_cannot_be_installed_as_a_valid_guard(self):
        out,files,_=self.scenario('empty_source');self.assertEqual(out,{'error':'unsupported_binary'});self.assertEqual(files,{})

    def test_readonly_package_directory_need_not_be_a_private_data_directory(self):
        out,_,_=self.scenario('package_directory');self.assertEqual(out.get('phase'),'prepared')


if __name__=='__main__':unittest.main()
