"""Committed private bytes, rather than editable compact rows, own a score."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from test_dpi_normalize import PHP, PUBLIC


class CustomSamplesTests(unittest.TestCase):
    def observe(self, body='', checkpoint='', probe='', context='', initial='', kill_stage=None, recovery=''):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if kill_stage:
                checkpoint = '''$j=$s->read();$pending=$j['custom_sample_pending']??null;
if(is_array($pending['identity']??null)){
 $f=$s->root.'/custom-'.$id.'-'.$pending['id'].'.json';clearstatcache(true,$f);
 if(is_file($f)&&'''+('filesize($f)===0' if kill_stage == 'empty' else 'filesize($f)>0')+'''){
  file_put_contents(dirname($s->root).'/kill-ready','ready');while(true)usleep(10000);}}
'''+checkpoint
            script = root/'test.php'
            script.write_text('''<?php umask(0077);
$file=$argv[1].'/strategy-picker-custom-samples.php';
if(!is_file($file)){echo json_encode(['error'=>'not_implemented']);exit;}
require $file;$resources=$argv[2].'/resources';mkdir($resources,0700);
foreach(['lists','lua','blobs']as $kind)mkdir($resources.'/'.$kind,0700);
$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3],$resources);
$id=str_repeat('a',32);$config=str_repeat('b',64);$dns=str_repeat('c',64);
$ctx=['nfqws'=>'running','ark'=>'absent','tun_observed'=>false,'dns'=>['schema_version'=>1,'state'=>'known','sha256'=>$dns]];
$hashContext=static function($v){ksort($v);return hash('sha256',json_encode($v,JSON_THROW_ON_ERROR));};$contextSha=$hashContext($ctx);
$manifest=['schema_version'=>1,'hosts'=>['nnmclub.to'],'dns_context'=>$dns,
 'pins'=>[['host'=>'nnmclub.to','answer'=>['8.8.8.8'],'address'=>'8.8.8.8']],
 'policy'=>NfqwsIdna::POLICY,'fingerprint'=>AsusDpiSiteCheckProbe::PINNED_FINGERPRINT];
$manifestSha=hash('sha256',json_encode($manifest,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR));
$s->write(['id'=>$id,'state'=>'running','phase'=>'measuring','boot'=>AsusUpdateStore::boot(),
 'deadline'=>AsusUpdateStore::uptime()+120,'current'=>$config,'custom_hosts'=>$manifest['hosts'],
 'custom_manifest'=>$manifest,'custom_manifest_sha256'=>$manifestSha,'restored'=>false]);
$lock=$s->lock();$calls=0;$checks=0;
$check=static function()use($s,$id,$config,&$checks){$checks++;'''+checkpoint+'''
 $j=$s->read();if(($j['id']??null)!==$id)throw new RuntimeException('stale_state');
 if(file_exists($s->path('cancel-'.$id)))throw new RuntimeException('cancelled');
 if(($j['current']??null)!==$config)throw new RuntimeException('source_changed');
 if(AsusUpdateStore::uptime()>=$j['deadline'])throw new RuntimeException('timed_out');};
$context=static function()use(&$ctx,$s){'''+context+'''return $ctx;};
$probe=static function()use(&$calls,$s,&$ctx,$manifestSha,$dns){$calls++;'''+probe+'''
 $r=AsusDpiSiteCheck::response('response');$r['http_status']=200;
 $r['redirect']='https://example.com/private?token=secret';
 return ['schema_version'=>1,'hosts'=>['nnmclub.to'],'dns_context'=>$dns,
  'fingerprint'=>AsusDpiSiteCheckProbe::PINNED_FINGERPRINT,'manifest_sha256'=>$manifestSha,
  'observations'=>[['host'=>'nnmclub.to','tls'=>'tls12','response'=>$r],['host'=>'nnmclub.to','tls'=>'tls13','response'=>$r]]];};
$samples=new NfqwsStrategyPickerCustomSamples($s,$check,$context,(int)$argv[3]);$out=[];
try{'''+initial+(body or '''$a=$samples->capture('candidate',$config,1,$contextSha,$probe);
$b=$samples->capture('candidate',$config,2,$contextSha,$probe);
$out['a']=$a;$out['b']=$b;$out['pair']=$samples->pair($id,'candidate');
$out['loaded']=$samples->load($id,$a['sample_id']);''')+'''
}catch(Throwable $e){$out['error']=$e->getMessage();}
$out['calls']=$calls;$out['checks']=$checks;$out['state']=$s->read();$out['files']=[];
foreach(scandir($s->root)as $name)if(str_starts_with($name,'custom-')){
 $p=$s->root.'/'.$name;$a=lstat($p);$out['files'][$name]=['mode'=>$a['mode']&0777,'nlink'=>$a['nlink'],
 'bytes'=>$a['size'],'sha256'=>is_file($p)&&!is_link($p)?hash_file('sha256',$p):null];}
echo json_encode($out,JSON_THROW_ON_ERROR);flock($lock,LOCK_UN);fclose($lock);
''')
            args = [PHP, '-n', '-f', str(script), '--', str(PUBLIC), directory, str(os.getuid())]
            if kill_stage:
                child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    until = time.monotonic()+3
                    while not (root/'kill-ready').exists() and child.poll() is None and time.monotonic()<until:
                        time.sleep(.01)
                    self.assertTrue((root/'kill-ready').exists(), 'Capture did not reach the requested commit boundary')
                    child.kill(); child.communicate(timeout=3)
                    self.assertEqual(child.returncode, -9)
                finally:
                    if child.poll() is None: child.kill(); child.communicate(timeout=3)
                recovery_path = root/'recovery.php'
                recovery_path.write_text('''<?php
require $argv[1].'/strategy-picker-custom-samples.php';
$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$j=$s->read();
$samples=new NfqwsStrategyPickerCustomSamples($s,static function(){throw new RuntimeException('unexpected_checkpoint');},null,(int)$argv[3]);
$sample=$j['custom_sample_pending']['id'];$out=[];
try{'''+recovery+'''}catch(Throwable $e){$out['error']=$e->getMessage();}
$j=$s->read();$out+=['state'=>$j,'file_count'=>count(glob($s->root.'/custom-*.json'))];
try{$samples->load($j['id'],$sample);$out['load']='accepted';}
catch(Throwable $e){$out['load']=$e->getMessage();}
echo json_encode($out,JSON_THROW_ON_ERROR);''')
                args[3] = str(recovery_path)
            result = subprocess.run(args, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
            self.assertEqual(result.stderr, '')
            return json.loads(result.stdout)

    def retire_runtime(self):
        return """$file=dirname($s->root).'/nfqws2.conf';file_put_contents($file,'original');
$r=new NfqwsStrategyPickerRuntime($s,new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]));
(new ReflectionMethod($r,'clearPrevious'))->invoke($r,$s->read());
$out['config']=file_get_contents($file);"""

    def test_runtime_archives_completed_journal_and_keeps_committed_samples_without_library(self):
        out=self.observe(body="""$samples->capture('one',$config,1,$contextSha,$probe);
$samples->capture('one',$config,2,$contextSha,$probe);
file_put_contents($s->root.'/custom-'.str_repeat('f',32).'-'.str_repeat('e',32).'.json','foreign');
file_put_contents($s->root.'/user-report.txt','keep');
$j=$s->read();$j['state']='completed';$j['restored']=true;$s->write($j);
"""+self.retire_runtime()+"""
$archive=new NfqwsStrategyPickerState($s->root.'/job-'.$id,(int)$argv[3],$s->configDirectory);
$out['archive']=$archive->read();$out['user']=file_get_contents($s->root.'/user-report.txt');""")
        self.assertNotIn('error',out)
        self.assertEqual(out['archive'],out['state'])
        refs=out['archive']['custom_sample_refs']
        self.assertEqual(len(refs),2)
        for ref in refs:
            name='custom-'+out['state']['id']+'-'+ref['id']+'.json'
            self.assertEqual(out['files'][name]['sha256'],ref['sha256'])
        self.assertEqual(len(out['files']),3)
        self.assertEqual(out['user'],'keep')
        self.assertEqual(out['config'],'original')

    def test_runtime_unknown_pending_aborts_without_discarding_old_journal(self):
        out=self.observe(body="""$j=$s->read();$j['state']='failed';$j['restored']=true;
$j['custom_sample_pending']=['foreign'=>'preserve'];$s->write($j);
"""+self.retire_runtime())
        self.assertEqual(out.get('error'),'storage_unavailable',out)
        self.assertEqual(out['state']['custom_sample_pending'],{'foreign':'preserve'})
        self.assertNotIn('custom_samples_retired',out['state'])
        self.assertEqual(out['state']['id'],'a'*32)

    def test_runtime_does_not_retire_active_unrestored_or_described_work(self):
        for extra in ["$j['state']='running';", "$j['restored']=false;",
                      "$j['actuator']=['foreign'=>'preserve'];", "$j['custom_worker']=['foreign'=>'preserve'];"]:
            with self.subTest(extra=extra):
                out=self.observe(body="""$samples->capture('one',$config,1,$contextSha,$probe);
$j=$s->read();$j['state']='completed';$j['restored']=true;"""+extra+"""$s->write($j);
"""+self.retire_runtime())
                expected='recovery_required' if 'actuator' in extra or 'custom_worker' in extra else 'busy'
                self.assertEqual(out.get('error'),expected,out)
                self.assertEqual(len(out['files']),1)
                self.assertEqual(len(out['state']['custom_sample_refs']),1)

    def test_runtime_preserves_worker_authority_before_first_capture_and_snapshot(self):
        out=self.observe(body="""$j=$s->read();$j['state']='completed';$j['restored']=true;
$j['custom_worker']=['stage'=>'prepare','foreign'=>'preserve'];$s->write($j);
"""+self.retire_runtime()+"""
(new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]))->snapshot(false);""")
        self.assertEqual(out.get('error'),'recovery_required',out)
        self.assertEqual(out['state']['id'],'a'*32)
        self.assertEqual(out['state']['custom_worker'],{'stage':'prepare','foreign':'preserve'})
        self.assertNotIn('custom_samples_retired',out['state'])

    def test_runtime_stale_old_id_cannot_retire_current_job(self):
        out=self.observe(body="""$samples->capture('one',$config,1,$contextSha,$probe);
$j=$s->read();$j['state']='completed';$j['restored']=true;$s->write($j);
$r=new NfqwsStrategyPickerRuntime($s);$old=$j;$old['id']=str_repeat('f',32);
(new ReflectionMethod($r,'clearPrevious'))->invoke($r,$old);""")
        self.assertEqual(out.get('error'),'source_changed',out)
        self.assertEqual(out['state']['id'],'a'*32)
        self.assertEqual(len(out['state']['custom_sample_refs']),1)
        self.assertEqual(len(out['files']),1)

    def test_runtime_legacy_journal_and_absent_job_do_not_gain_custom_state(self):
        out=self.observe(body="""$j=$s->read();$j['state']='completed';$j['restored']=true;$s->write($j);"""+self.retire_runtime()+"""
$out['legacy']=$s->read();unlink($s->path('state.json'));$out['empty_before']=$s->read();(new ReflectionMethod($r,'clearPrevious'))->invoke($r,null);
mkdir($s->root.'/library',0700);$orphan=$s->root.'/library/foreign.json';file_put_contents($orphan,'UNKNOWN_PROFILE');$out['orphan_before']=file_get_contents($orphan);
try{(new ReflectionMethod($r,'clearPrevious'))->invoke($r,null);$out['orphan_accepted']=true;}catch(Throwable $e){$out['orphan_error']=$e->getMessage();}
$out['orphan_after']=file_get_contents($orphan);""")
        self.assertNotIn('error',out)
        self.assertNotIn('custom_samples_retired',out['legacy'])
        self.assertIsNone(out['state'])
        self.assertEqual(out['state'],out['empty_before'])
        self.assertEqual(out['orphan_error'],'recovery_required')
        self.assertNotIn('orphan_accepted',out)
        self.assertEqual(out['orphan_before'],out['orphan_after'])

    def test_fresh_capture_is_private_and_pair_is_rederived_from_committed_bytes(self):
        out = self.observe()
        self.assertNotIn('error', out)
        self.assertEqual(out['calls'], 2)
        self.assertNotEqual(out['a']['sample_id'], out['b']['sample_id'])
        self.assertEqual(out['pair'], [out['a'], out['b']])
        self.assertEqual(out['loaded']['score'], out['a'])
        self.assertIn('secret', json.dumps(out['loaded']['document']))
        self.assertNotIn('secret', json.dumps(out['a']))
        self.assertEqual(len(out['files']), 2)
        self.assertTrue(all(f['mode'] == 0o600 and f['nlink'] == 1 for f in out['files'].values()))
        self.assertIsNone(out['state'].get('custom_sample_pending'))
        self.assertEqual(len(out['state']['custom_sample_refs']), 2)

    def test_new_series_captures_samples_in_its_job_bound_round(self):
        r=self.observe(initial="""$j=$s->read();$j['rounds']=2;
          $j['series']=['total'=>2,'current'=>1,'completed'=>0,'selected'=>null,'runs'=>[],'archive_version'=>2];
          $s->write($j);$old=new NfqwsStrategyPickerState($s->root.'/round-1',(int)$argv[3]);
          $old->write(['id'=>str_repeat('d',32),'historical'=>true]);$before=hash_file('sha256',$old->path('state.json'));""",
          body="""$a=$samples->capture('candidate',$config,1,$contextSha,$probe);
          $b=$samples->capture('candidate',$config,2,$contextSha,$probe);$out['pair']=$samples->pair($id,'candidate');
          $part=$s->round(1);$out['round']=basename($part->root);$out['count']=count(glob($part->root.'/custom-*.json'));
          $out['old_unchanged']=hash_file('sha256',$old->path('state.json'))===$before;""")
        self.assertNotIn('error',r)
        self.assertEqual(r['calls'],2)
        self.assertEqual(r['round'],'round-'+'a'*32+'-1')
        self.assertEqual(r['count'],2)
        self.assertTrue(r['old_unchanged'])

    def test_cancel_probe_error_context_drift_and_changed_config_do_not_commit(self):
        cases = [('throw new RuntimeException("cancelled");', 'cancelled'),
                 ('throw new RuntimeException("timed_out");', 'timed_out'),
                 ('$ctx["dns"]["sha256"]=str_repeat("e",64);', 'incomparable_result'),
                 ('$j=$s->read();$j["current"]=str_repeat("f",64);$s->write($j);', 'source_changed')]
        for action, error in cases:
            with self.subTest(error=error):
                out = self.observe(probe=action)
                self.assertEqual(out.get('error'), error, out)
                self.assertFalse(out.get('files'), out)
                self.assertFalse(out['state'].get('custom_sample_refs'))
                self.assertIsNone(out['state'].get('custom_sample_pending'))

    def test_unknown_context_or_manifest_mismatch_never_starts_a_probe(self):
        for initial in ['$ctx["dns"]["state"]="unknown";',
                        '$j=$s->read();$j["custom_manifest_sha256"]=str_repeat("f",64);$s->write($j);']:
            with self.subTest(initial=initial):
                out = self.observe(initial=initial)
                self.assertIn(out.get('error'), ['incomparable_result', 'stale_state'])
                self.assertEqual(out['calls'], 0)
                self.assertFalse(out['files'])

    def test_duplicate_role_repeat_and_overlapping_capture_are_refused(self):
        out = self.observe(body='''$samples->capture('same',$config,1,$contextSha,$probe);
$samples->capture('same',$config,1,$contextSha,$probe);''')
        self.assertEqual(out.get('error'), 'stale_state', out)
        self.assertEqual(out['calls'], 1)
        out = self.observe(initial='''$j=$s->read();$j['custom_sample_pending']=['foreign'=>'preserve'];$s->write($j);''')
        self.assertEqual(out.get('error'), 'busy', out)
        self.assertEqual(out['calls'], 0)
        self.assertEqual(out['state']['custom_sample_pending'], {'foreign': 'preserve'})

    def test_compact_profile_tampering_cannot_replace_original_observations(self):
        out = self.observe(body='''$a=$samples->capture('original',$config,1,$contextSha,$probe);
$j=$s->read();$j['profiles']=[['custom_runs'=>[['sample_id'=>$a['sample_id'],'cells'=>[]]]]];$s->write($j);
$out['loaded']=$samples->load($id,$a['sample_id']);''')
        self.assertNotIn('error', out)
        self.assertEqual(len(out['loaded']['score']['cells']), 2)
        self.assertTrue(out['loaded']['score']['cells'][0]['root_ok'])

    def test_corruption_mode_hardlink_symlink_and_inode_replacement_are_preserved(self):
        for action in ['file_put_contents($file,"corrupt");', 'chmod($file,0644);',
                       'link($file,$s->root."/outside-link");',
                       'unlink($file);symlink($s->root."/state.json",$file);',
                       '$alt=$s->root."/replacement";file_put_contents($alt,file_get_contents($file));chmod($alt,0600);rename($alt,$file);']:
            with self.subTest(action=action):
                out = self.observe(body='''$a=$samples->capture('one',$config,1,$contextSha,$probe);
$file=$s->root.'/custom-'.$id.'-'.$a['sample_id'].'.json';'''+action+'''
$samples->load($id,$a['sample_id']);''')
                self.assertEqual(out.get('error'), 'storage_unavailable', out)
                self.assertEqual(len(out['files']), 1)

    def test_uncommitted_file_is_never_readable_and_foreign_pending_is_preserved(self):
        out = self.observe(checkpoint='''$j=$s->read();$p=$j['custom_sample_pending']??null;
if(is_array($p)&&is_array($p['identity']??null)){
 $j['custom_sample_pending']=['foreign'=>'preserve'];$s->write($j);
}''')
        self.assertEqual(out.get('error'), 'stale_state', out)
        self.assertFalse(out['state'].get('custom_sample_refs'))
        self.assertEqual(out['state']['custom_sample_pending'], {'foreign': 'preserve'})
        self.assertEqual(len(out['files']), 1)

    def test_terminal_cleanup_requires_restore_and_never_deletes_a_corrupt_artifact(self):
        for restored in [False, True]:
            with self.subTest(restored=restored):
                out = self.observe(body='''$a=$samples->capture('one',$config,1,$contextSha,$probe);
$j=$s->read();$j['state']='completed';$j['restored']='''+('true' if restored else 'false')+''';$s->write($j);
'''+('''$file=$s->root.'/custom-'.$id.'-'.$a['sample_id'].'.json';file_put_contents($file,'foreign');''' if restored else '')+'''
$samples->clear($id);''')
                self.assertEqual(out.get('error'), 'storage_unavailable' if restored else 'busy', out)
                self.assertEqual(len(out['files']), 1)

    def test_exact_terminal_cleanup_is_repeatable_without_touching_unrelated_files(self):
        out = self.observe(body='''$samples->capture('one',$config,1,$contextSha,$probe);
$samples->capture('one',$config,2,$contextSha,$probe);file_put_contents($s->root.'/user-report.txt','keep');
$j=$s->read();$j['state']='completed';$j['restored']=true;$s->write($j);
$samples->clear($id);$samples->clear($id);$out['user_file']=file_get_contents($s->root.'/user-report.txt');''')
        self.assertNotIn('error', out)
        self.assertFalse(out['files'])
        self.assertFalse(out['state']['custom_sample_refs'])
        self.assertEqual(out['user_file'], 'keep')

    def test_attempt_limit_and_foreign_orphan_budget_stop_before_probe(self):
        out = self.observe(initial='''$j=$s->read();$j['custom_sample_attempts']=64;$s->write($j);''')
        self.assertEqual(out.get('error'), 'output_limit', out)
        self.assertEqual(out['calls'], 0)
        out = self.observe(initial='''for($i=0;$i<96;$i++){
 $name=$s->root.'/custom-'.str_repeat('f',32).'-'.str_pad(dechex($i),32,'0',STR_PAD_LEFT).'.json';
 file_put_contents($name,'orphan');chmod($name,0600);}''')
        self.assertEqual(out.get('error'), 'output_limit', out)
        self.assertEqual(out['calls'], 0)
        self.assertEqual(len(out['files']), 96)

    def test_cleanup_failure_does_not_replace_the_original_guard_failure(self):
        out = self.observe(checkpoint='''$j=$s->read();
if(is_array($j['custom_sample_pending']['identity']??null)){
 unlink($s->path('state.json'));throw new RuntimeException('guard_lost');}''')
        self.assertEqual(out.get('error'), 'guard_lost', out)
        self.assertEqual(len(out['files']), 1)

    def test_late_foreign_intent_during_context_collection_is_not_overwritten(self):
        out = self.observe(context='''$j=$s->read();if(!isset($j['custom_sample_pending'])){
 $j['custom_sample_pending']=['foreign'=>'preserve'];$s->write($j);}''')
        self.assertEqual(out.get('error'), 'stale_state', out)
        self.assertEqual(out['calls'], 0)
        self.assertFalse(out['files'])
        self.assertEqual(out['state']['custom_sample_pending'], {'foreign': 'preserve'})

    def test_32_commits_and_two_reports_per_role_are_the_hard_limit(self):
        out = self.observe(body='''for($i=0;$i<32;$i++)$samples->capture('trial-'.$i,$config,1,$contextSha,$probe);
$samples->capture('overflow',$config,1,$contextSha,$probe);''')
        self.assertEqual(out.get('error'), 'output_limit', out)
        self.assertEqual(out['calls'], 32)
        self.assertEqual(len(out['files']), 32)
        out = self.observe(body='''$samples->capture('one',$config,1,$contextSha,$probe);$samples->pair($id,'one');''')
        self.assertEqual(out.get('error'), 'incomparable_result', out)

    def test_cleanup_can_resume_after_a_proven_unlink_without_touching_an_orphan(self):
        out = self.observe(body='''$samples->capture('one',$config,1,$contextSha,$probe);
$samples->capture('one',$config,2,$contextSha,$probe);
$j=$s->read();$j['state']='completed';$j['restored']=true;
$j['custom_sample_cleanup']=['refs'=>$j['custom_sample_refs']];$s->write($j);
$ref=$j['custom_sample_refs'][0];unlink($s->root.'/custom-'.$id.'-'.$ref['id'].'.json');
$orphan=$s->root.'/custom-'.str_repeat('f',32).'-'.str_repeat('e',32).'.json';file_put_contents($orphan,'keep');chmod($orphan,0600);
$samples->clear($id);$out['orphan']=file_get_contents($orphan);''')
        self.assertNotIn('error', out)
        self.assertEqual(out['orphan'], 'keep')
        self.assertEqual(len(out['files']), 1)
        self.assertFalse(out['state']['custom_sample_refs'])

    def test_real_supervisor_probe_is_captured_after_registered_child_is_reaped(self):
        from test_picker_custom_supervisor import CustomSupervisorTests
        body = '''require __PUBLIC__.'/strategy-picker-custom-samples.php';
$j=$s->read();$j['current']=str_repeat('b',64);$j['boot']=AsusUpdateStore::boot();$s->write($j);
$sup->prepare(['nnmclub.to']);
$ctx=['nfqws'=>'running','ark'=>'absent','tun_observed'=>false,'dns'=>['schema_version'=>1,'state'=>'known','sha256'=>str_repeat('c',64)]];
ksort($ctx);$hash=hash('sha256',json_encode($ctx,JSON_THROW_ON_ERROR));
$samples=new NfqwsStrategyPickerCustomSamples($s,$check,static fn()=>$ctx,$uid);
$out['score']=$samples->capture('real-child',str_repeat('b',64),1,$hash,fn()=>$sup->probe());
$out['detail']=$samples->load($id,$out['score']['sample_id']);'''
        out = CustomSupervisorTests.observe(self, body=body)
        self.assertNotIn('error', out)
        self.assertEqual(len(out['probe_calls']), 2)
        self.assertEqual(out['detail']['score'], out['score'])
        self.assertTrue(all(x['responded'] and not x['root_ok'] for x in out['score']['cells']))
        self.assertIsNone(out['state'].get('actuator'))
        self.assertIsNone(out['state'].get('custom_worker'))

    def test_sigkill_before_and_after_file_write_never_publishes_a_partial_report(self):
        for stage in ['empty', 'complete']:
            with self.subTest(stage=stage):
                out = self.observe(kill_stage=stage)
                self.assertEqual(out['file_count'], 1)
                self.assertEqual(out['load'], 'incomparable_result')
                self.assertFalse(out['state'].get('custom_sample_refs'))
                self.assertIsInstance(out['state']['custom_sample_pending']['identity'], dict)

    def test_complete_five_host_samples_remain_separate_from_native_denominators(self):
        out = self.observe(initial='''$j=$s->read();$hosts=['nnmclub.to','rutor.info','rutracker.org','tapochek.net','example.com'];
$j['custom_hosts']=$hosts;$j['custom_manifest']['hosts']=$hosts;$j['custom_manifest']['pins']=[];
foreach($hosts as $h)$j['custom_manifest']['pins'][]=['host'=>$h,'answer'=>['8.8.8.8'],'address'=>'8.8.8.8'];
$j['custom_manifest_sha256']=hash('sha256',json_encode($j['custom_manifest'],JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR));$s->write($j);''',
            probe='''$j=$s->read();$rows=[];$r=AsusDpiSiteCheck::response('response');$r['http_status']=200;
foreach($j['custom_hosts']as $h)foreach(['tls12','tls13']as $tls)$rows[]=['host'=>$h,'tls'=>$tls,'response'=>$r];
return ['schema_version'=>1,'hosts'=>$j['custom_hosts'],'dns_context'=>$dns,'fingerprint'=>AsusDpiSiteCheckProbe::PINNED_FINGERPRINT,
'manifest_sha256'=>$j['custom_manifest_sha256'],'observations'=>$rows];''')
        self.assertNotIn('error', out)
        self.assertEqual(len(out['a']['cells']), 10)
        self.assertEqual(len(out['loaded']['document']['envelope']['observations']), 10)
        self.assertNotIn('metrics', out['a'])

    def terminal_recovery(self, action, restored=True):
        return "$j=$s->read();$j['state']='interrupted';$j['restored']="+('true' if restored else 'false')+";$s->write($j);"+action

    def test_sigkill_proven_empty_and_complete_files_recover_without_publishing(self):
        for stage in ['empty', 'complete']:
            with self.subTest(stage=stage):
                out = self.observe(kill_stage=stage, recovery=self.terminal_recovery(
                    "$samples->recoverPending($j['id']);$samples->recoverPending($j['id']);"))
                self.assertNotIn('error', out)
                self.assertEqual(out['file_count'], 0)
                self.assertIsNone(out['state'].get('custom_sample_pending'))
                self.assertFalse(out['state'].get('custom_sample_refs'))
                self.assertEqual(out['load'], 'incomparable_result')

    def test_pending_recovery_requires_terminal_restored_job_and_no_child(self):
        for action in ["$samples->recoverPending($j['id']);",
                       self.terminal_recovery("$samples->recoverPending($j['id']);", restored=False),
                       self.terminal_recovery("$j=$s->read();$j['custom_worker']=['stage'=>'active'];$s->write($j);$samples->recoverPending($j['id']);")]:
            with self.subTest(action=action):
                out = self.observe(kill_stage='complete', recovery=action)
                self.assertEqual(out.get('error'), 'busy', out)
                self.assertEqual(out['file_count'], 1)
                self.assertIsInstance(out['state']['custom_sample_pending'], dict)

    def test_unproven_replaced_or_changed_pending_file_is_preserved_with_intent(self):
        for mutation in ["$j['custom_sample_pending']['identity']=null;$s->write($j);",
                         "file_put_contents($file,'changed');",
                         "chmod($file,04600);",
                         "link($file,$s->root.'/keep-link');",
                         "$copy=$s->root.'/copy';file_put_contents($copy,file_get_contents($file));chmod($copy,0600);rename($copy,$file);",
                         "unlink($file);symlink($s->root.'/state.json',$file);"]:
            with self.subTest(mutation=mutation):
                out = self.observe(kill_stage='complete', recovery=self.terminal_recovery(
                    "$j=$s->read();$file=$s->root.'/custom-'.$j['id'].'-'.$sample.'.json';"+mutation+"$samples->recoverPending($j['id']);"))
                self.assertEqual(out.get('error'), 'recovery_required', out)
                self.assertEqual(out['file_count'], 1)
                self.assertIsInstance(out['state']['custom_sample_pending'], dict)

    def test_pending_recovery_resumes_after_missing_file_and_rejects_receipt_tamper(self):
        out = self.observe(kill_stage='complete', recovery=self.terminal_recovery(
            "$j=$s->read();unlink($s->root.'/custom-'.$j['id'].'-'.$sample.'.json');$samples->recoverPending($j['id']);"))
        self.assertNotIn('error', out)
        self.assertIsNone(out['state'].get('custom_sample_pending'))
        out = self.observe(kill_stage='complete', recovery=self.terminal_recovery(
            "$j=$s->read();$j['custom_sample_pending']['expected']['sha256']=str_repeat('f',64);$s->write($j);$samples->recoverPending($j['id']);"))
        self.assertEqual(out.get('error'), 'recovery_required', out)
        self.assertEqual(out['file_count'], 1)

    def test_primary_error_retains_intent_when_cleanup_cannot_prove_file_ownership(self):
        out = self.observe(checkpoint="""$j=$s->read();$pending=$j['custom_sample_pending']??null;
if(is_array($pending['identity']??null)){
 $file=$s->root.'/custom-'.$id.'-'.$pending['id'].'.json';file_put_contents($file,'unknown');
 throw new RuntimeException('guard_lost');}""")
        self.assertEqual(out.get('error'), 'guard_lost', out)
        self.assertEqual(len(out['files']), 1)
        self.assertIsInstance(out['state'].get('custom_sample_pending'), dict)

    def test_retire_cleans_one_proven_terminal_job_and_preserves_foreign_reports(self):
        out = self.observe(body="""$samples->capture('one',$config,1,$contextSha,$probe);
$samples->capture('one',$config,2,$contextSha,$probe);
$orphan=$s->root.'/custom-'.str_repeat('f',32).'-'.str_repeat('e',32).'.json';file_put_contents($orphan,'keep');chmod($orphan,0600);
file_put_contents($s->root.'/user-report.txt','user');
$j=$s->read();$j['state']='completed';$j['restored']=true;$s->write($j);
$samples->retire($id);$samples->retire($id);
$out['orphan']=file_get_contents($orphan);$out['user']=file_get_contents($s->root.'/user-report.txt');""")
        self.assertNotIn('error', out)
        self.assertEqual(out['orphan'], 'keep')
        self.assertEqual(out['user'], 'user')
        self.assertEqual(len(out['files']), 1)
        self.assertTrue(out['state']['custom_samples_retired'])
        self.assertFalse(out['state']['custom_sample_refs'])

    def live_config_setup(self):
        return '''$live=$s->root.'/active.conf';file_put_contents($live,'first');
$config=hash_file('sha256',$live);$j=$s->read();$j['current']=$config;$s->write($j);
$verify=static function()use($s,$live){if(hash_file('sha256',$live)!==$s->read()['current'])throw new RuntimeException('source_changed');};
$samples=new NfqwsStrategyPickerCustomSamples($s,$verify,$context,(int)$argv[3]);'''

    def test_switching_config_between_repeats_is_refused_before_another_probe(self):
        out = self.observe(body=self.live_config_setup()+'''
$samples->capture('candidate',$config,1,$contextSha,$probe);
file_put_contents($live,'second');$next=hash_file('sha256',$live);$j=$s->read();$j['current']=$next;$s->write($j);
$samples->capture('candidate',$next,2,$contextSha,$probe);''')
        self.assertEqual(out.get('error'), 'stale_state', out)
        self.assertEqual(out['calls'], 1)
        self.assertEqual(len(out['files']), 1)

    def test_already_persisted_mixed_configs_do_not_form_a_repeated_result(self):
        out = self.observe(body=self.live_config_setup()+'''
$samples->capture('first',$config,1,$contextSha,$probe);
file_put_contents($live,'second');$next=hash_file('sha256',$live);$j=$s->read();$j['current']=$next;$s->write($j);
$samples->capture('second',$next,2,$contextSha,$probe);
$j=$s->read();foreach($j['custom_sample_refs']as &$ref){
 $file=$s->root.'/custom-'.$id.'-'.$ref['id'].'.json';$doc=json_decode(file_get_contents($file),true);
 $doc['role']='candidate';$raw=json_encode($doc,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);
 file_put_contents($file,$raw);$ref['role']='candidate';$ref['bytes']=strlen($raw);$ref['sha256']=hash('sha256',$raw);
}unset($ref);$s->write($j);$samples->pair($id,'candidate');''')
        self.assertEqual(out.get('error'), 'incomparable_result', out)
        self.assertEqual(out['calls'], 2)


if __name__ == '__main__': unittest.main()
