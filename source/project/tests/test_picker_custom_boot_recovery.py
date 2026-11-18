"""Boot restoration closes only an owned previous-boot custom pending intent."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


class CustomBootRecoveryTests(unittest.TestCase):
    def observe(self, mutation='', action=None):
        code=r'''
        umask(0077);require $argv[1].'/strategy-picker-custom-samples.php';
        $root=$argv[2];$uid=(int)$argv[3];$resources=$root.'/resources';mkdir($resources,0700);
        foreach(['lists','lua','blobs']as $kind)mkdir($resources.'/'.$kind,0700);
        $s=new NfqwsStrategyPickerState($root.'/picker',$uid,$resources);
        $file=$root.'/nfqws2.conf';file_put_contents($file,'original');chmod($file,0640);
        $cfg=new NfqwsStrategyPickerConfig($s,$file,$uid);$cfg->snapshot(false);$cfg->replace('candidate');
        $j=$s->read();$id=$j['id'];$old='00000000-0000-4000-8000-000000000000';
        $j['state']='running';$j['boot']=$old;$j['deadline']=AsusUpdateStore::uptime()+600;
        $dns=str_repeat('c',64);$ctx=['nfqws'=>'running','ark'=>'absent','tun_observed'=>false,
          'dns'=>['schema_version'=>1,'state'=>'known','sha256'=>$dns]];ksort($ctx);
        $j['custom_hosts']=['nnmclub.to'];$j['custom_manifest']=['schema_version'=>1,'hosts'=>$j['custom_hosts'],
          'dns_context'=>$dns,'pins'=>[['host'=>'nnmclub.to','answer'=>['8.8.8.8'],'address'=>'8.8.8.8']],
          'policy'=>NfqwsIdna::POLICY,'fingerprint'=>AsusDpiSiteCheckProbe::PINNED_FINGERPRINT];
        $j['custom_manifest_sha256']=hash('sha256',json_encode($j['custom_manifest'],JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR));
        $sample=bin2hex(random_bytes(16));$artifact=$s->root.'/custom-'.$id.'-'.$sample.'.json';
        file_put_contents($artifact,'');chmod($artifact,0600);$st=lstat($artifact);
        $j['custom_sample_attempts']=1;
        $j['custom_sample_pending']=['id'=>$sample,'role'=>'fixture','repeat'=>1,'config_sha256'=>$j['current'],
          'context_sha256'=>hash('sha256',json_encode($ctx,JSON_THROW_ON_ERROR)),'manifest_sha256'=>$j['custom_manifest_sha256'],
          'started_uptime'=>AsusUpdateStore::uptime(),'identity'=>['dev'=>(string)$st['dev'],'ino'=>(string)$st['ino'],
          'uid'=>$st['uid'],'gid'=>$st['gid'],'mode'=>0600,'nlink'=>1],'expected'=>null];
        $nonce=str_repeat('a',32);$j['custom_worker']=['stage'=>'probe','nonce'=>$nonce,
          'payload_sha256'=>$j['custom_manifest_sha256'],'deadline'=>AsusUpdateStore::uptime()+90];
        // A former process number has been reused. Its previous boot authority
        // must never authorize a signal to this live unrelated process.
        $actor=NfqwsStrategyPickerRuntime::identity((int)$argv[4]);
        $j['actuator']=$actor;$j['actuator']['boot']=$old;
        $j['actuator']['argv']=[...$actor['argv'],$argv[1].'/strategy-picker-custom-worker.php','--','probe',$id,$nonce];
        $foreign=$s->root.'/user-report.txt';file_put_contents($foreign,'keep');
        '''+mutation+r'''
        $s->write($j);$r=new NfqwsStrategyPickerRuntime($s,$cfg);$out=[];
        try{
        '''+(action or r'''
          $out['allow_start']=$r->recoverBoot();
          (new ReflectionMethod($r,'clearPrevious'))->invoke($r,$s->read());
          $archive=new NfqwsStrategyPickerState($root.'/picker/job-'.$id,$uid,$resources);
          $out['archived']=$archive->read();
        ''')+r'''
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $out+=['job'=>$s->read(),'raw'=>$cfg->raw(),'artifact_exists'=>file_exists($artifact),
          'artifact_bytes'=>file_exists($artifact)?file_get_contents($artifact):null,
          'foreign_alive'=>NfqwsStrategyPickerRuntime::sameActor($actor),'user_file'=>file_get_contents($foreign)];
        echo json_encode($out,JSON_THROW_ON_ERROR);
        '''
        with tempfile.TemporaryDirectory()as directory:
            other=subprocess.Popen([PHP,'-n','-r','usleep(10000000);'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),directory,str(os.getuid()),str(other.pid)],
                                 capture_output=True,text=True,timeout=8)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                self.assertEqual(r.stderr,'')
                return json.loads(r.stdout)
            finally:
                if other.poll()is None:other.terminate()
                other.communicate(timeout=3)

    def test_old_boot_restores_and_retires_owned_pending_without_signalling_reused_pid(self):
        r=self.observe()
        self.assertNotIn('error',r)
        self.assertFalse(r['allow_start'])
        self.assertTrue(r['job']['restored'])
        self.assertEqual(r['job']['state'],'interrupted')
        self.assertIsNone(r['job'].get('custom_worker'))
        self.assertIsNone(r['job'].get('actuator'))
        self.assertNotIn('custom_sample_pending',r['job'])
        self.assertEqual(r['archived'],r['job'])
        self.assertFalse(r['artifact_exists'])
        self.assertEqual(r['raw'],'original')
        self.assertTrue(r['foreign_alive'])
        self.assertEqual(r['user_file'],'keep')

    def test_unknown_old_boot_descriptor_is_preserved_and_cannot_admit_service_start(self):
        r=self.observe("$j['custom_worker']=['unknown'=>'preserve'];$j['actuator']=null;")
        self.assertEqual(r.get('error'),'recovery_required')
        self.assertEqual(r['job']['state'],'recovery_required')
        self.assertEqual(r['job']['custom_worker'],{'unknown':'preserve'})
        # Refusal precedes Config restoration; an unknown descriptor is not ownership.
        self.assertFalse(r['job']['restored'])
        self.assertTrue(r['artifact_exists'])
        self.assertEqual(r['raw'],'candidate')
        self.assertTrue(r['foreign_alive'])

    def test_previous_boot_actuator_without_custom_descriptor_cannot_block_archival(self):
        r=self.observe("unset($j['custom_worker']);")
        self.assertNotIn('error',r)
        self.assertEqual(r['archived'],r['job'])
        self.assertNotIn('custom_sample_pending',r['archived'])
        self.assertFalse(r['artifact_exists'])
        self.assertIsNone(r['job'].get('actuator'))
        self.assertEqual(r['raw'],'original')
        self.assertTrue(r['foreign_alive'])

    def test_unrecognised_pending_bytes_are_not_removed_after_boot(self):
        r=self.observe("file_put_contents($artifact,'foreign bytes');")
        self.assertEqual(r.get('error'),'recovery_required')
        self.assertEqual(r['job']['state'],'recovery_required')
        self.assertTrue(r['job']['restored'])
        self.assertEqual(r['artifact_bytes'],'foreign bytes')
        self.assertIn('custom_sample_pending',r['job'])
        self.assertEqual(r['raw'],'original')
        self.assertTrue(r['foreign_alive'])

    def test_same_boot_foreign_or_changed_full_argv_never_authorizes_a_signal(self):
        for argv_change in ["$j['actuator']=$actor;",'']:
            with self.subTest(argv_change=argv_change):
                r=self.observe("$j['boot']=AsusUpdateStore::boot();$j['actuator']['boot']=$j['boot'];"+argv_change,
                               "(new ReflectionMethod($r,'customReap'))->invoke($r,false);")
                self.assertEqual(r.get('error'),'recovery_required')
                self.assertEqual(r['job']['state'],'running')
                self.assertEqual(r['raw'],'candidate')
                self.assertTrue(r['foreign_alive'])
                self.assertTrue(r['artifact_exists'])


if __name__=='__main__':unittest.main()
