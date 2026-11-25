"""A dead validator's uptime belongs to its boot; status remains read-only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import test_smartdns_recovery as native_fixture
import test_smartdns_resume_retry as entry_fixture

from test_dpi_normalize import PHP, PUBLIC
from test_smartdns_profile import profile


class SmartDnsBootRecoveryTests(unittest.TestCase):
    def scenario(self, mode):
        code = r'''require $argv[1].'/smartdns-config-jobs.php';
        $root=$argv[2];$mode=$argv[4];$owner=(int)$argv[3];
        $old=str_starts_with($mode,'old_');$now=$old?10000.0:1.0;
        $boot=$old?'00000000-0000-0000-0000-000000000000':trim(file_get_contents('/proc/sys/kernel/random/boot_id'));
        $store=new AsusSmartDnsStore($root,$owner,['uptime'=>function()use(&$now){return $now;},'boot'=>fn()=>$boot]);
        $profile=json_decode(stream_get_contents(STDIN),true);$hash=$store->saveDraft($profile);$id=str_repeat('c',32);
        $store->saveIntent(['schema_version'=>1,'profile'=>$profile,'profile_hash'=>$hash,'engine_sha'=>str_repeat('e',64),'source_request_id'=>str_repeat('d',32)]);
        $store->beginValidation($id,$hash,str_repeat('a',64),'confirmed');
        $now=$mode==='same_aged'?12.0:5.0;
        $deps=['owner'=>$owner,'native'=>fn()=>null,'uptime'=>function()use(&$now){return $now;},
          'validation_owner'=>fn($job)=>['known'=>$mode!=='old_unknown','guard_alive'=>$mode==='old_live',
            'anchor_alive'=>false,'worker_alive'=>false,'code'=>null]];
        $jobs=new AsusSmartDnsConfigJobs($store,null,$deps);
        $journal=hash_file('sha256',$root.'/state.json');$draft=hash_file('sha256',$root.'/draft.json');$intent=hash_file('sha256',$root.'/resume-intent.json');
        $before=$store->transaction();$status=$jobs->status();$readOnly=$journal===hash_file('sha256',$root.'/state.json');$blockedBefore=$jobs->blocksUpdate();
        $jobs->reconcile();$after=$store->transaction();
        echo json_encode(['before'=>$before['state'],'status'=>$status,'readonly'=>$readOnly,'current'=>$store->status(),
          'blocked_before'=>$blockedBefore,'blocked_after'=>$jobs->blocksUpdate(),'same_request'=>$after['request_id']===$id,
          'journal_unchanged'=>$journal===hash_file('sha256',$root.'/state.json'),
          'draft_unchanged'=>$draft===hash_file('sha256',$root.'/draft.json'),
          'intent_unchanged'=>$intent===hash_file('sha256',$root.'/resume-intent.json')]);'''
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(Path(directory) / 'state'),
                str(os.getuid()), mode], input=json.dumps(profile()), capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr, '')
            return json.loads(result.stdout)

    def test_dead_previous_boot_validation_is_interrupted_before_old_uptime_elapses(self):
        value = self.scenario('old_dead')
        self.assertEqual(value['status']['state'], 'failed', value)
        self.assertEqual(value['status']['code'], 'interrupted')
        self.assertTrue(value['readonly'])
        self.assertTrue(value['blocked_before'])
        self.assertEqual(value['current']['state'], 'failed')
        self.assertEqual(value['current']['code'], 'interrupted')
        self.assertFalse(value['blocked_after'])
        self.assertTrue(value['same_request'])
        self.assertFalse(value['journal_unchanged'])
        self.assertTrue(value['draft_unchanged'])
        self.assertTrue(value['intent_unchanged'])

    def test_current_boot_young_validation_keeps_its_grace_period(self):
        value = self.scenario('same_young')
        self.assertEqual(value['status']['state'], 'validating')
        self.assertEqual(value['current']['state'], 'validating')
        self.assertTrue(value['journal_unchanged'])
        self.assertTrue(value['blocked_after'])

    def test_current_boot_dead_owner_still_expires_after_ten_seconds(self):
        value = self.scenario('same_aged')
        self.assertEqual(value['status']['state'], 'failed')
        self.assertEqual(value['current']['code'], 'interrupted')
        self.assertFalse(value['blocked_after'])
        self.assertTrue(value['readonly'])

    def test_live_or_unknown_owner_is_not_discarded_as_a_stale_boot(self):
        for mode in ['old_live', 'old_unknown']:
            with self.subTest(mode=mode):
                value = self.scenario(mode)
                self.assertEqual(value['current']['state'], 'validating')
                self.assertTrue(value['journal_unchanged'])
                self.assertTrue(value['blocked_after'])
                self.assertTrue(value['draft_unchanged'])
                self.assertTrue(value['intent_unchanged'])


class SmartDnsBootResumeTests(unittest.TestCase):
    """Real native restore; synthetic engine/validator never touches host DNS."""
    def scenario(self, mode):
        fixture = native_fixture.SmartDnsRecoveryTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        root = fixture.root
        old_boot = '00000000-0000-0000-0000-000000000000'
        fixture.state(phase='conflict', boot_id=old_boot)
        if mode in ['restart_ready', 'restart_forever', 'manual', 'revoked', 'fresh_switch', 'receipt_rotation', 'receipt_wrong_id', 'receipt_truncate']:
            (root/'restart-fail').touch()
        if mode in ['hook_conflict', 'stale_restart_hard']:
            fixture.hook.write_bytes(fixture.hook.read_bytes().replace(b'postconf', b'CHANGED'))
        if mode == 'stale_restart_hard':
            log = fixture.jffs/'recovery.log'
            log.write_text('100.000 '+'c'*32+' dns_restart_failed\n');log.chmod(0o600)
            # A full/unwritable log must not turn a fresh hard failure into the
            # historical shutdown DNS failure that happens to be last on disk.
            common = fixture.jffs/'native-common.sh'
            common.write_text(common.read_text()+'\nsd_log() { return 1; }\n')
        if mode.startswith('receipt_'):
            log = fixture.jffs/'recovery.log'
            log.write_text('99.000 '+'c'*32+' dns_restart_failed\n');log.chmod(0o600)
            common = fixture.jffs/'native-common.sh'
            if mode == 'receipt_rotation':
                body = 'mv "$sd_root/recovery.log" "$sd_root/recovery.log.1"; cat "$sd_root/recovery.log.1" > "$sd_root/recovery.log"; printf "100.000 %s dns_restart_failed\\n" "$sd_request_id" >> "$sd_root/recovery.log"'
            elif mode == 'receipt_wrong_id':
                body = 'printf "100.000 '+'f'*32+' dns_restart_failed\\n" >> "$sd_root/recovery.log"'
            else:
                body = 'printf "100.000 %s dns_restart_failed\\n" "$sd_request_id" > "$sd_root/recovery.log"'
            common.write_text(common.read_text()+'\nsd_log() { '+body+'; }\n')
        code = r'''require $argv[1].'/smartdns-lifecycle.php';
        $bootMethod=method_exists(AsusSmartDnsLifecycle::class,'resumeBoot')?'resumeBoot':'resume';
        $root=$argv[2];$owner=(int)$argv[3];$mode=$argv[4];$boot=trim(file_get_contents('/proc/sys/kernel/random/boot_id'));$old='00000000-0000-0000-0000-000000000000';
        $store=new AsusSmartDnsStore($root.'/dns',$owner,['boot'=>fn()=>$old]);$profile=json_decode(stream_get_contents(STDIN),true);$hash=$store->saveDraft($profile);$id=str_repeat('c',32);$base=str_repeat('a',64);
        $store->savePreview(['id'=>str_repeat('b',32),'profile_hash'=>$hash,'baseline_hash'=>$base,'expires_uptime'=>PHP_FLOAT_MAX]);$store->begin($id,$hash,$base);
        $backup=$store->backup(['candidate_profile'=>$profile]);$store->transition($id,['applying'],['state'=>'confirmed','active'=>['profile'=>$profile,'profile_hash'=>$hash,'backup_id'=>$backup]]);
        $store->saveIntent(['schema_version'=>1,'profile'=>$profile,'profile_hash'=>$hash,'engine_sha'=>str_repeat('e',64),'source_request_id'=>$mode==='foreign'?str_repeat('f',32):$id]);
        $state=file_get_contents($root.'/jffs/state');$state=str_replace(str_repeat('d',64),$hash,$state);file_put_contents($root.'/jffs/state',$state);
        if(str_starts_with($mode,'same_boot')){
          $j=json_decode(file_get_contents($root.'/dns/state.json'),true);$j['job']['boot']=$boot;file_put_contents($root.'/dns/state.json',json_encode($j));
        }
        if($mode==='fresh_switch'){$j=json_decode(file_get_contents($root.'/dns/state.json'),true);$j['job']['boot']=$boot;file_put_contents($root.'/dns/state.json',json_encode($j));}
        if($mode==='no_consent')$store->saveIntent(null);
        $store=new AsusSmartDnsStore($root.'/dns',$owner);
        $bundle=$root.'/engine/'.str_repeat('e',64);mkdir($root.'/engine',0700);mkdir($bundle,0700);mkdir($bundle.'/lib',0700);symlink(str_repeat('e',64),$root.'/engine/current');
        $artifact=['sha256'=>str_repeat('e',64),'version'=>'48.4','files'=>[],'links'=>[]];
        if($mode==='same_boot_previous_engine')$artifact=['sha256'=>str_repeat('f',64),'version'=>'48.5','previous'=>$artifact];
        $installer=new AsusSmartDnsInstaller($root.'/engine',$owner,$artifact);
        $native=new AsusSmartDnsNativeBackend($store,$installer,['native'=>$root.'/jffs','library'=>$root.'/lib'],['owner'=>$owner]);
        $backend=new class($native,$root,$mode,$boot) implements NfqwsSmartDnsBackend {
          public ?array $fresh=null; public int $restores=0;public int $switches=0;
          public function __construct(private $native,private $root,private $mode,private $boot){}
          public function state():?array{return $this->fresh??$this->native->state();}
          public function prepare(array $j,array $s):void{$this->fresh=['request_id'=>$j['request_id'],'profile_hash'=>$j['profile_hash'],'boot_id'=>$this->boot,'phase'=>'prepared'];}
          public function baseline():array{return ['hash'=>str_repeat('a',64),'snapshot'=>[],'conflicts'=>[]];}
          public function healthy():bool{return str_starts_with($this->mode,'same_boot')||($this->fresh['phase']??null)==='confirmed';}
          public function forwarding():string{return 'external';}
          public function lastCode(string $id):?string{return $this->native->lastCode($id);}
          public function guard(array $j,array $p):array{return ['identity'=>[],'guard_identity'=>[]];}
          public function forward(array $j):array{$this->switches++;$this->fresh['phase']='awaiting_confirmation';return ['deadline_uptime'=>(float)explode(' ',file_get_contents('/proc/uptime'))[0]+60];}
          public function dns():bool{return $this->mode!=='new_switch_failure';}
          public function confirm(array $j):bool{$this->fresh['phase']='confirmed';return true;}
          public function restore(array $j,array $s):bool{$this->restores++;if($this->fresh!==null){$this->fresh['phase']='conflict';return false;}return $this->native->restore($j,$s);}
          public function restoreFailure():?string{return $this->fresh!==null?'dns_restart_failed':$this->native->restoreFailure();}
          public function stop(array $j):bool{return $this->native->stop($j);}
          public function dependencies():array{$out=[];foreach(['baseline','prepare','guard','forward','dns','confirm','restore','stop'] as $n)$out[$n]=[$this,$n];$out['release']=fn()=>null;return $out;}
        };
        $validations=0;$pauses=[];$ids=[];$original=$store->intent();
        $deps=['jobs_deps'=>['owner'=>$owner],
          'boot_pause'=>function($seconds)use(&$pauses,$root,$mode,$store){$pauses[]=$seconds;if(in_array($mode,['restart_ready','revoked'],true))unlink($root.'/restart-fail');if($mode==='revoked')$store->saveIntent(null);},
          'validate'=>function($id,$hash,$source)use($store,&$validations,&$ids,$mode,$base){$validations++;$ids[]=$id;
            if($mode==='baseline_throw'&&$validations===1)throw new RuntimeException('baseline_unavailable');
            $store->beginValidation($id,$hash,$base,$source);
            if(in_array($mode,['baseline_ready','baseline_forever'],true)&&($validations===1||$mode==='baseline_forever')){$store->transition($id,['validating'],['state'=>'failed','code'=>'baseline_unavailable']);return;}
            if($mode==='hard_validation'){$store->transition($id,['validating'],['state'=>'failed','code'=>'unsupported_binary']);return;}
            $preview=bin2hex(random_bytes(16));$store->savePreview(['id'=>$preview,'profile_hash'=>$hash,'baseline_hash'=>$base,'expires_uptime'=>PHP_FLOAT_MAX,'checks'=>[['stage'=>'profile','name'=>'example.com','ok'=>true]]]);$store->transition($id,['validating'],['state'=>'preview_ready','preview_id'=>$preview]);
          }];
        $life=new AsusSmartDnsLifecycle($store,$backend,$installer,$deps);
        if(str_starts_with($mode,'status_')){
          file_put_contents($root.'/foreign','private fixture');chmod($root.'/foreign',0600);
          if($mode==='status_symlink')symlink($root.'/foreign',$root.'/dns/boot-status.json');
          elseif($mode==='status_hardlink')link($root.'/foreign',$root.'/dns/boot-status.json');
          else {file_put_contents($root.'/dns/boot-status.json',str_repeat('x',4097));chmod($root.'/dns/boot-status.json',0600);}
        }
        try{$result=$mode==='manual'?$life->resume():$life->$bootMethod();if($mode==='same_boot_previous_engine'&&$result['state']==='confirmed')$life->remember();}catch(Throwable $e){$result=['error'=>$e->getMessage()];}
        echo json_encode(['result'=>$result,'restores'=>$backend->restores,'switches'=>$backend->switches,'validations'=>$validations,'pauses'=>$pauses,'ids'=>$ids,'same_intent'=>$store->intent()===$original,'native'=>$native->state(),'events'=>file_get_contents($root.'/events'),'boot_status'=>is_file($root.'/dns/boot-status.json')?json_decode(file_get_contents($root.'/dns/boot-status.json'),true):null,'boot_status_mode'=>is_file($root.'/dns/boot-status.json')?(fileperms($root.'/dns/boot-status.json')&0777):null]);'''
        result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(root), str(os.getuid()), mode],
            input=json.dumps(profile()), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        value = json.loads(result.stdout)
        self.assertIn('result', value, value)
        return value

    def test_previous_boot_restore_retries_only_proven_dns_restart_failure(self):
        value = self.scenario('restart_ready')
        self.assertEqual(value['result']['state'], 'confirmed', value)
        self.assertEqual(value['restores'], 2)
        self.assertEqual(value['pauses'], [2])
        self.assertEqual(value['validations'], 1)
        self.assertEqual(value['switches'], 1)
        self.assertIn('restart\nrestart\nconfigured\nprobe\n', value['events'])

    def test_boot_retry_is_bounded_and_manual_resume_remains_one_attempt(self):
        for mode, attempts in [('restart_forever', 4), ('manual', 1)]:
            with self.subTest(mode=mode):
                value = self.scenario(mode)
                self.assertEqual(value['result']['state'], 'conflict', value)
                self.assertEqual(value['restores'], attempts)
                self.assertEqual(value['pauses'], [2, 4, 6] if attempts == 4 else [])
                self.assertEqual(value['validations'], 0)
                self.assertTrue(value['same_intent'])

    def test_baseline_retry_gets_new_validation_without_repeating_restore_or_switch(self):
        for mode in ['baseline_ready', 'baseline_throw']:
            with self.subTest(mode=mode):
                value = self.scenario(mode)
                self.assertEqual(value['result']['state'], 'confirmed', value)
                self.assertEqual(value['restores'], 1)
                self.assertEqual(value['validations'], 2)
                self.assertEqual(len(set(value['ids'])), 2)
                self.assertEqual(value['switches'], 1)

    def test_baseline_failures_stop_after_four_fresh_attempts(self):
        value = self.scenario('baseline_forever')
        self.assertEqual(value['result']['code'], 'baseline_unavailable', value)
        self.assertEqual(value['validations'], 4)
        self.assertEqual(value['switches'], 0)
        self.assertEqual(value['pauses'], [2, 4, 6])

    def test_hard_errors_foreign_intent_and_current_boot_failure_are_not_replayed(self):
        for mode in ['hook_conflict', 'foreign', 'fresh_switch', 'hard_validation']:
            with self.subTest(mode=mode):
                value = self.scenario(mode)
                self.assertEqual(value['pauses'], [], value)
                self.assertLessEqual(value['restores'], 1)
                self.assertEqual(value['switches'], 0)

    def test_a_new_switch_failure_never_borrows_the_previous_boot_retry_permission(self):
        value = self.scenario('new_switch_failure')
        self.assertEqual(value['result']['state'], 'conflict', value)
        self.assertEqual(value['pauses'], [])
        self.assertEqual(value['restores'], 2, 'one old restore and one failed fresh cleanup')
        self.assertEqual(value['validations'], 1)
        self.assertEqual(value['switches'], 1)

    def test_no_consent_and_healthy_same_boot_remain_inert(self):
        for mode in ['no_consent', 'same_boot']:
            with self.subTest(mode=mode):
                value = self.scenario(mode)
                self.assertEqual(value['result']['state'], 'idle' if mode == 'no_consent' else 'confirmed', value)
                self.assertEqual((value['restores'], value['validations'], value['switches']), (0, 0, 0))
                self.assertEqual(value['events'], '')

    def test_active_previous_engine_uses_the_original_confirmed_intent(self):
        value = self.scenario('same_boot_previous_engine')
        self.assertEqual(value['result']['state'], 'confirmed', value)
        self.assertTrue(value['same_intent'])
        self.assertEqual((value['restores'], value['validations'], value['switches']), (0, 0, 0))

    def test_revoked_consent_stops_before_the_next_attempt(self):
        value = self.scenario('revoked')
        self.assertEqual(value['result']['state'], 'action_required', value)
        self.assertEqual(value['result']['code'], 'stale_state')
        self.assertEqual(value['restores'], 1)
        self.assertEqual(value['switches'], 0)

    def test_boot_outcome_is_bounded_private_and_contains_only_safe_fields(self):
        value = self.scenario('restart_ready')
        self.assertIsInstance(value['boot_status'], dict, value)
        self.assertEqual(set(value['boot_status']), {'attempt', 'state', 'code', 'boot'})
        self.assertEqual(value['boot_status']['attempt'], 2)
        self.assertEqual(value['boot_status']['state'], 'confirmed')
        self.assertIsNone(value['boot_status']['code'])
        self.assertEqual(value['boot_status_mode'], 0o600)
        self.assertEqual(value['boot_status']['boot'], Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        self.assertNotIn(profile()['upstreams'][0]['address'], json.dumps(value['boot_status']))

    def test_boot_outcome_rejects_links_and_oversized_files_before_dns_actions(self):
        for mode in ['status_symlink', 'status_hardlink', 'status_oversize']:
            with self.subTest(mode=mode):
                value = self.scenario(mode)
                self.assertEqual(value['result'], {'error': 'invalid_state'}, value)
                self.assertEqual((value['restores'], value['validations'], value['switches']), (0, 0, 0))
                self.assertEqual(value['events'], '')

    def test_historical_shutdown_restart_error_is_not_fresh_retry_proof(self):
        value = self.scenario('stale_restart_hard')
        self.assertEqual(value['pauses'], [], value)
        self.assertEqual(value['restores'], 1)

    def test_rotated_truncated_or_wrong_request_receipts_never_authorize_replay(self):
        for mode in ['receipt_rotation', 'receipt_wrong_id', 'receipt_truncate']:
            with self.subTest(mode=mode):
                value = self.scenario(mode)
                self.assertEqual(value['pauses'], [], value)
                self.assertEqual(value['restores'], 1)

    def test_a_failed_boot_records_the_fresh_native_reason_not_public_fallback(self):
        value = self.scenario('restart_forever')
        self.assertEqual(value['boot_status']['attempt'], 4)
        self.assertEqual(value['boot_status']['code'], 'dns_restart_failed', value)


class SmartDnsBootEntryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = entry_fixture.SmartDnsQueuedResumeGenerationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def run_boot(self):
        return subprocess.run([PHP, '-n', '-f', str(self.fixture.control), '--', 'boot-resume'],
            capture_output=True, text=True, timeout=5)

    def test_boot_entry_without_consent_is_inert(self):
        result = self.run_boot()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertFalse(self.fixture.dns.exists())

    def test_boot_entry_keeps_the_existing_single_owner_mutex(self):
        import fcntl
        self.fixture.save_consent()
        lock = self.fixture.dns/'resume.lock'
        lock.touch(mode=0o600)
        with lock.open('r') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            result = self.run_boot()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'error': 'busy'})
        self.assertFalse(self.fixture.engine.exists())

    def test_openwrt_boot_wrapper_invokes_the_common_policy_once(self):
        self.fixture.save_consent()
        source = (PUBLIC.parents[2]/'openwrt/smartdns-resume.sh').read_text()
        source = source.replace('/usr/bin/php-cgi', PHP).replace('/usr/lib/nfqws2/smartdns/control.php', str(self.fixture.control))
        script = self.fixture.root/'native-resume.sh';script.write_text(source);script.chmod(0o700)
        result = subprocess.run(['/bin/sh', str(script)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1, result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout), {'state': 'action_required', 'code': 'engine_changed'})
        status = json.loads((self.fixture.dns/'boot-status.json').read_text())
        self.assertEqual(status['attempt'], 1)
        self.assertEqual(status['code'], 'engine_changed')

    def test_real_queue_detaches_before_update_finishes_then_runs_boot_mode(self):
        import fcntl
        self.fixture.save_consent()
        source = (PUBLIC.parents[2]/'asus/smartdns/control.sh').read_text()
        script = self.fixture.root/'control.sh'
        source = source.replace('/opt/etc/nfqws-asus-web/smartdns/resume-intent.json', str(self.fixture.dns/'resume-intent.json'))
        source = source.replace('/opt/libexec/nfqws2-asus/busybox', '/bin/busybox')
        source = source.replace('/opt/var/run/nfqws2-smartdns-resume.pid', str(self.fixture.root/'resume.pid'))
        source = source.replace('/opt/lib/nfqws2-asus/smartdns/control.sh', str(script))
        source = source.replace('/opt/lib/nfqws2-asus/smartdns/control.php', str(self.fixture.control))
        source = source.replace('/opt/bin/php-cgi', PHP)
        script.write_text(source);script.chmod(0o700)
        status = self.fixture.dns/'boot-status.json'
        with self.fixture.lock.open('r') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            start = time.monotonic()
            result = subprocess.run(['/bin/sh', str(script), 'queue-resume'], capture_output=True, text=True, timeout=2)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertLess(time.monotonic()-start, 1)
            self.assertFalse(self.fixture.loaded.exists())
            self.assertFalse(status.exists())
            fcntl.flock(held, fcntl.LOCK_UN)
        end = time.monotonic()+5
        while time.monotonic()<end:
            if status.exists():
                value = json.loads(status.read_text())
                if value['state'] != 'starting':
                    break
            time.sleep(.02)
        self.assertTrue(status.exists(), 'the real detached queue must invoke boot-resume')
        self.assertEqual(json.loads(status.read_text())['code'], 'engine_changed')
        self.assertFalse(self.fixture.engine.exists())


if __name__ == '__main__':
    unittest.main()
