"""Actual global Runtime/State/Config original boundary; no guard/native doubles."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC

class PickerOriginalBoundaryTests(unittest.TestCase):
    def setUp(self):
        artifact=os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifact:self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=artifact))
        else:
            temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)

    def call(self,mode):
        runtime=(PUBLIC/'strategy-picker-runtime.php').read_bytes()
        source=runtime.decode()
        begin=source.index('            if(isset($j)&&')
        end=source.index('            throw $e;',begin)
        catch=source[begin:end]
        self.assertEqual(catch.count('$this->assertOriginal();'),1)
        code=r'''umask(0077);require $argv[1].'/strategy-picker-runtime.php';$r=$argv[2];$u=(int)$argv[3];$d=json_decode(file_get_contents($argv[4]),true,32,JSON_THROW_ON_ERROR);
        if(in_array($d['mode'],['alias_capture','alias_service','alias_retirement','alias_retirement_unknown','alias_retirement_current'],true)){
            if(is_dir('/opt')&&!is_link('/opt')&&scandir('/opt')===['.','..'])rmdir('/opt');
            if(file_exists('/opt')||is_link('/opt'))throw new RuntimeException('fixture_opt_not_empty');
            symlink('/entware','/opt');
        }
        mkdir($r,0700);mkdir('/opt/etc/nfqws2',0755,true);
        if(in_array($d['mode'],['alias_capture','alias_service','alias_retirement','alias_retirement_unknown','alias_retirement_current'],true)){
            $path='/opt/etc/nfqws2/nfqws2.conf';file_put_contents($path,"NFQWS_ARGS=\"--filter-tcp=443\"\n");chmod($path,0664);
            mkdir('/opt/etc/nfqws2/lists',0755);file_put_contents('/opt/etc/nfqws2/lists/google.list',"google.com\n");chmod('/opt/etc/nfqws2/lists/google.list',0666);
            mkdir('/opt/etc/nfqws-asus-web/strategy-picker',0700,true);mkdir('/opt/etc/nfqws2/strategy-picker',0755);
            $record=static function($p){clearstatcache(true,$p);return ['sha256'=>hash_file('sha256',$p),'metadata'=>array_intersect_key(lstat($p),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']))];};
            $out=['opt'=>readlink('/opt'),'before'=>[$record($path),$record('/opt/etc/nfqws2/lists/google.list')]];
            try{
                if(in_array($d['mode'],['alias_service','alias_retirement','alias_retirement_unknown','alias_retirement_current'],true)){
                    file_put_contents($path,"NFQWS_EXTRA_ARGS=\"--hostlist-auto=/opt/etc/nfqws2/lists/auto.list\"\n");
                    file_put_contents('/opt/etc/nfqws2/lists/auto.list',"seed.example\n");chmod('/opt/etc/nfqws2/lists/auto.list',0644);chown('/opt/etc/nfqws2/lists/auto.list',65534);
                    $store=new NfqwsStrategyPickerState('/opt/etc/nfqws-asus-web/strategy-picker');$config=new NfqwsStrategyPickerConfig($store,$path);$config->snapshot(false);$runtime=new NfqwsStrategyPickerRuntime($store,$config);$j=$store->read();$j['state']='running';$j['library_namespace']='job-v1';$j['resources_sha256']=(new ReflectionMethod($runtime,'resourcesFingerprint'))->invoke($runtime);$store->write($j);
                    $lib=(new ReflectionMethod($runtime,'library'))->invoke($runtime);
                }else $lib=new NfqwsDeviceProfilesLibrary('/opt/etc/nfqws-asus-web/strategy-picker/job-'.str_repeat('a',32),'/opt/etc/nfqws2/strategy-picker/'.str_repeat('a',32),'/opt/etc/nfqws2');
                $created=$lib->capture('Current');$out['entry']=$lib->entry($created['id']);
                if(in_array($d['mode'],['alias_service','alias_retirement','alias_retirement_unknown','alias_retirement_current'],true)){require '/project/tests/fixtures/picker-service-alias.php';$out['cycle']=fixtureServiceAlias($runtime,$store,$config,$out['entry'],$d['mode']);}
            }
            catch(Throwable $e){$out['error']=$e->getMessage();$out['trace']=$e->getTraceAsString();}
            $out['after']=[$record($path),$record('/opt/etc/nfqws2/lists/google.list')];echo json_encode($out,JSON_THROW_ON_ERROR);exit;
        }
        $p=$r.'/nfqws2.conf';file_put_contents($p,"NFQWS_MODE=list\nNFQWS_ARGS=\"--filter-tcp=443\"\n");chmod($p,0664);
        $s=new NfqwsStrategyPickerState($r.'/picker',$u);$lock=$s->lock();$c=new NfqwsStrategyPickerConfig($s,$p,$u);$c->snapshot(false);$runtime=new NfqwsStrategyPickerRuntime($s,$c);
        if(in_array($d['mode'],['recovered_stop','recovered_stop_foreign'],true)){
            $original=$c->raw();$c->replace($original."# temporary fixture input\n");$c->restore();$j=$s->read();$id=$j['id'];
            mkdir('/opt/etc/init.d',0755,true);$service=NfqwsPlatform::serviceCommand('stop')[0];
            file_put_contents($service,"#!/bin/sh\nif [ \"\$1\" = diagnostics ]; then echo '{\"process_running\":false}'; else sleep 3; fi\n");chmod($service,0755);
            $processes=[];$proofs=[];
            foreach(['work','guard']as $role){$q=proc_open(['/bin/sh','-c','sleep 3; :',$argv[1].'/strategy-picker-runtime.php','--',$role,$id],[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes);$processes[]=$q;$pid=proc_get_status($q)['pid'];$proofs[$role]=null;for($try=0;$try<50;$try++){$proofs[$role]=NfqwsStrategyPickerRuntime::identity($pid);if($proofs[$role]!==null&&array_slice($proofs[$role]['argv'],-4)===[$argv[1].'/strategy-picker-runtime.php','--',$role,$id])break;usleep(10000);}if($proofs[$role]===null||array_slice($proofs[$role]['argv'],-4)!==[$argv[1].'/strategy-picker-runtime.php','--',$role,$id])throw new RuntimeException('fixture_actor_missing');$s->write(['id'=>$id,'identity'=>$proofs[$role]],'actor-'.$role.'.json');}
            $q=proc_open(NfqwsPlatform::serviceCommand('stop'),[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes);$processes[]=$q;$pid=proc_get_status($q)['pid'];$actuator=null;for($try=0;$try<50;$try++){$actuator=NfqwsStrategyPickerRuntime::identity($pid);if($actuator!==null&&in_array('stop',$actuator['argv'],true))break;usleep(10000);}if($actuator===null)throw new RuntimeException('fixture_actuator_missing');
            foreach($processes as $q)proc_close($q);
            $g=$s->read('actor-guard.json',$guardPin);$j=$s->read();$j['library_namespace']='job-v1';$j['state']='recovery_required';$j['actuator']=$actuator;
            $j['actuator_intent']=['argv'=>NfqwsPlatform::serviceCommand('stop'),'deadline'=>microtime(true)-1,'nonce'=>str_repeat('a',32),'parent'=>$proofs['work'],'possible_input'=>true];
            $j['actuator_attention']=['intent'=>$j['actuator_intent'],'reason'=>$d['mode']==='recovered_stop_foreign'?'foreign':'recovery_required','resource_pid'=>$pid,'resource_reaped'=>true];
            $j['engine_trial']=['guard'=>$g['identity'],'guard_pin'=>$guardPin];$s->write($j);
            mkdir($s->root.'/library',0700);$foreign=$s->root.'/library/foreign.json';file_put_contents($foreign,'UNKNOWN_OLD_LIBRARY');chmod($foreign,0600);
            $before=['raw'=>file_get_contents($foreign),'pin'=>lstat($foreign)];
            try{(new ReflectionMethod($runtime,'clearPrevious'))->invoke($runtime,$j);$out['new_snapshot']=$c->snapshot(false)['id'];}catch(Throwable $e){$out['error']=$e->getMessage();}
            $history=new NfqwsStrategyPickerState($s->root.'/job-'.$id);$out['history']=$history->read();$out['old']=$j;$out['current']=$s->read();$out['original_config']=$c->raw()===$original;$out['unknown_library_preserved']=file_get_contents($foreign)===$before['raw']&&lstat($foreign)===$before['pin'];
            echo json_encode($out,JSON_THROW_ON_ERROR);exit;
        }
        if(in_array($d['mode'],['next_start','next_start_legacy','next_start_failed'],true)){
            mkdir('/opt/etc/nfqws2/lists',0755);$list='/opt/etc/nfqws2/lists/google.list';
            file_put_contents($list,"old.example\n");chmod($list,0644);
            $j=$s->read();$j['resources_sha256']=(new ReflectionMethod($runtime,'resourcesFingerprint'))->invoke($runtime);$j['state']=$d['mode']==='next_start_failed'?'failed':'completed';$j['restored']=true;
            if($d['mode']==='next_start_failed')$j['library_namespace']='job-v1';$s->write($j);
            file_put_contents($p,"NFQWS_MODE=list\nNFQWS_ARGS=\"--filter-tcp=80,443\"\n");chmod($p,0664);
            file_put_contents($list,"current.example\n");
            $record=static function($p){clearstatcache(true,$p);return ['sha256'=>hash_file('sha256',$p),'metadata'=>array_intersect_key(lstat($p),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']))];};
            $out=['before'=>[$record($p),$record($list)]];
            if(in_array($d['mode'],['next_start_legacy','next_start_failed'],true)){
                $private=$s->root;
                if($d['mode']==='next_start_failed'){$private.='/job-'.$j['id'];mkdir($private,0700);}
                mkdir($private.'/library',0700);$legacy=$private.'/library/'.($d['mode']==='next_start_failed'?'.stage-0123456789abcdef':'saved-0123456789abcdef.json');
                file_put_contents($legacy,json_encode(['schema_version'=>1,'id'=>'saved-0123456789abcdef','name'=>'Previous result','config'=>[],'files'=>[],'mutable_files'=>[]]));
                $out['legacy_before']=$record($legacy);
            }
            try{
                (new ReflectionMethod($runtime,'clearPrevious'))->invoke($runtime,$j);$next=$c->snapshot(false);$out['new_original_sha256']=$next['original_sha256'];$out['new_binding']=$next['config_binding']['current'];
                if(in_array($d['mode'],['next_start_legacy','next_start_failed'],true)){$next['library_namespace']='job-v1';$s->write($next);$out['new_library']=(new ReflectionMethod($runtime,'library'))->invoke($runtime)->listing();}
            }
            catch(Throwable $e){$out['error']=$e->getMessage();}
            if(in_array($d['mode'],['next_start_legacy','next_start_failed'],true))$out['legacy_after']=$record($legacy);
            $out['after']=[$record($p),$record($list)];flock($lock,LOCK_UN);fclose($lock);echo json_encode($out,JSON_THROW_ON_ERROR);exit;
        }
        if($d['mode']==='readable_resources'){
            mkdir('/opt/etc/nfqws2/lists',0755);$list='/opt/etc/nfqws2/lists/google.list';
            file_put_contents($list,"google.com\n");chmod($list,0666);
            $record=static function($p){clearstatcache(true,$p);return ['sha256'=>hash_file('sha256',$p),'metadata'=>array_intersect_key(lstat($p),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']))];};
            $out=['before'=>$record($list)];
            try{$out['fingerprint']=(new ReflectionMethod($runtime,'resourcesFingerprint'))->invoke($runtime);}
            catch(Throwable $e){$out['error']=$e->getMessage();}
            $out['after']=$record($list);
            try{NfqwsDeviceProfilesPaths::guard(dirname($list),basename($list));$out['writer_allowed']=true;}
            catch(Throwable $e){$out['writer_refusal']=$e->getMessage();}
            flock($lock,LOCK_UN);fclose($lock);echo json_encode($out,JSON_THROW_ON_ERROR);exit;
        }
        $j=$s->read();$j['resources_sha256']=(new ReflectionMethod($runtime,'resourcesFingerprint'))->invoke($runtime);$s->write($j);
        $pin=static function($p){clearstatcache(true,$p);return array_intersect_key(lstat($p),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));};
        $record=static function($p)use($pin){return ['pin'=>$pin($p),'raw_base64'=>base64_encode(file_get_contents($p))];};
        $out=['original'=>$record($p)];
        if($d['mode']==='catch_legacy'){$j=$s->read();unset($j['config_binding'],$j['config_binding_version']);$s->write($j);}
        if(in_array($d['mode'],['inode','catch_inode'],true)){$raw=file_get_contents($p);rename($p,$r.'/displaced-original');file_put_contents($p,$raw);chmod($p,0664);}
        if($d['mode']==='catch_mtime')touch($p,$pin($p)['mtime']+3);
        if($d['mode']==='catch_mode')chmod($p,0640);
        $j=$s->read();$out['before']=$record($p);$out['journal_before']=$j;
        $rival=fopen($r.'/picker/engine.lock','rb');$out['lock_conflict_before']=!flock($rival,LOCK_EX|LOCK_NB);if(!$out['lock_conflict_before'])flock($rival,LOCK_UN);fclose($rival);
        try{
            if(str_starts_with($d['mode'],'catch_')){
                $e=new RuntimeException('OWN_LOCAL_LAUNCH_FAILURE_NO_PROCESS');
                $f=Closure::bind(function()use($j,$e,$d){eval($d['catch']);},$runtime,NfqwsStrategyPickerRuntime::class);$f();
            }else (new ReflectionMethod($runtime,'assertOriginal'))->invoke($runtime);
            $out['success']=true;
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $out['after']=$record($p);$out['journal_after']=$s->read();if(is_file($r.'/displaced-original'))$out['displaced']=$record($r.'/displaced-original');
        flock($lock,LOCK_UN);fclose($lock);$f=fopen($r.'/picker/engine.lock','rb');$out['lock_free_after']=flock($f,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($f,LOCK_UN);fclose($f);echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request=json.dumps({'mode':mode,'catch':catch}).encode()
        for name,raw in [('actual-runtime.private.php',runtime),('php-r.private',code.encode()),('request.private.json',request)]:(self.root/name).write_bytes(raw)
        # Full production fingerprint requires the actual ROOT platform inventory.
        # Its tree is deliberately empty; these five cases cover Config only.
        script=self.root/'case.php';script.write_text('<?php '+code);script.chmod(0o644)
        request_file=self.root/'request.private.json';request_file.chmod(0o644)
        cid=subprocess.check_output(['docker','create','--init','--pull=never','--network','none',
            '--cap-drop','ALL',*(['--cap-add','CHOWN','--cap-add','DAC_OVERRIDE']if mode in ('alias_service','alias_retirement','alias_retirement_unknown','alias_retirement_current')else[]),'--security-opt','no-new-privileges:true',*([]if mode in ('alias_capture','alias_service','alias_retirement','alias_retirement_unknown','alias_retirement_current')else['--read-only']),'--pids-limit','16',
            '--memory','96m','--tmpfs','/tmp:rw,nosuid,nodev,size=8m','--tmpfs',('/entware'if mode in ('alias_capture','alias_service','alias_retirement','alias_retirement_unknown','alias_retirement_current')else'/opt')+(':rw,exec,nosuid,nodev,mode=0755,size=4m'if mode in ('recovered_stop','recovered_stop_foreign')else':rw,nosuid,nodev,mode=0755,size=4m'),
            '--mount',f'type=bind,src={PUBLIC.parents[2]},dst=/project,readonly',
            '--mount',f'type=bind,src={script},dst=/case.php,readonly',
            '--mount',f'type=bind,src={request_file},dst=/request.json,readonly',
            '--entrypoint','/usr/bin/php8-cgi',os.environ['NFQWS_TEST_GUARD_PHP_IMAGE'],
            '-n','-d','register_argc_argv=1','-q','-f','/case.php','--','/project/webui/web/public','/tmp/fixture','0','/request.json'],text=True).strip()
        (self.root/'container-id.private').write_text(cid)
        try:p=subprocess.run(['docker','start','-a',cid],capture_output=True,timeout=25)
        finally:
            subprocess.run(['docker','rm','-f',cid],check=True,stdout=subprocess.DEVNULL)
            self.assertNotEqual(subprocess.run(['docker','inspect',cid],capture_output=True).returncode,0)
        (self.root/'stdout.private').write_bytes(p.stdout);(self.root/'stderr.private').write_bytes(p.stderr)
        self.assertEqual((p.returncode,p.stderr),(0,b''),p.stdout.decode(errors='replace')+p.stderr.decode(errors='replace'))
        v=json.loads(p.stdout)
        if mode not in ('recovered_stop','recovered_stop_foreign','readable_resources','next_start','next_start_legacy','next_start_failed','alias_capture','alias_service','alias_retirement','alias_retirement_unknown','alias_retirement_current'):
            self.assertTrue(v['lock_conflict_before']);self.assertTrue(v['lock_free_after'])
        return v

    def test_plan_reads_existing_world_writable_list_without_granting_writer_permission(self):
        v=self.call('readable_resources')
        self.assertNotIn('error',v)
        self.assertRegex(v['fingerprint'],r'^[a-f0-9]{64}$')
        self.assertEqual(v['before'],v['after'])
        self.assertEqual(v['after']['metadata']['mode']&0o777,0o666)
        self.assertEqual(v.get('writer_refusal'),'unsafe_panel_file')
        self.assertNotIn('writer_allowed',v)

    def test_next_start_uses_current_config_and_lists_after_completed_restored_job(self):
        v=self.call('next_start')
        self.assertNotIn('error',v)
        self.assertEqual(v['before'],v['after'])
        self.assertEqual(v['new_original_sha256'],v['before'][0]['sha256'])
        self.assertEqual(v['new_binding'],v['before'][0]['metadata'])

    def test_next_start_preserves_legacy_library_and_uses_separate_job_library(self):
        v=self.call('next_start_legacy')
        self.assertNotIn('error',v)
        self.assertEqual(v['before'],v['after'])
        self.assertEqual(v['legacy_before'],v['legacy_after'])
        self.assertEqual(v['new_library'],[])

    def test_capture_uses_physical_entware_path_for_its_private_metadata(self):
        v=self.call('alias_capture')
        self.assertNotIn('error',v)
        self.assertEqual(v['opt'],'/entware')
        self.assertEqual(v['before'],v['after'])
        self.assertEqual(v['entry']['resource_binding_version'],1)

    def test_retry_after_restored_setup_failure_preserves_unpublished_metadata(self):
        v=self.call('next_start_failed')
        self.assertNotIn('error',v)
        self.assertEqual(v['before'],v['after'])
        self.assertEqual(v['legacy_before'],v['legacy_after'])
        self.assertEqual(v['new_library'],[])

    def test_service_tracks_auto_learning_when_candidate_uses_physical_entware_path(self):
        v=self.call('alias_service')
        self.assertNotIn('error',v)
        c=v['cycle']
        self.assertIsNotNone(c['trial_after_start'])
        self.assertEqual(c['stopped_observation'],c['actual_stopped'])
        self.assertEqual(c['frozen_seed']['lists/auto.list']['sha256'],c['actual_stopped']['sha256'])
        self.assertEqual(c['next_recipe_auto'],'')
        self.assertIsNone(c['trial_after_stop'])
        self.assertTrue(c['restored'])
        self.assertTrue(c['cancelled_copies_retained'])

    def test_recovered_reaped_stop_allows_a_new_snapshot_and_preserves_full_old_attention(self):
        v=self.call('recovered_stop')
        self.assertNotIn('error',v)
        self.assertEqual(v['history'],v['old'])
        self.assertNotEqual(v['current']['id'],v['old']['id'])
        self.assertTrue(v['original_config'])
        self.assertTrue(v['unknown_library_preserved'])

    def test_other_stop_attention_still_refuses_and_preserves_current_journal(self):
        v=self.call('recovered_stop_foreign')
        self.assertEqual(v.get('error'),'recovery_required')
        self.assertEqual(v['current'],v['old'])
        self.assertIsNone(v['history'])
        self.assertTrue(v['unknown_library_preserved'])

    def test_new_start_archives_own_copy_retirement_attention_without_deleting_remaining_copies(self):
        v=self.call('alias_retirement')
        self.assertNotIn('error',v)
        c=v['cycle']
        self.assertIsNone(c['next_error'])
        self.assertTrue(c['cancelled_copies_retained'])
        self.assertTrue(c['attention_preserved_in_archive'])
        self.assertTrue(c['metadata_preserved'])
        self.assertTrue(c['new_job_created'])

    def test_new_start_keeps_copy_attention_and_snapshots_current_inputs_after_old_job(self):
        v=self.call('alias_retirement_current')
        self.assertNotIn('error',v)
        c=v['cycle']
        self.assertIsNone(c['next_error'])
        self.assertTrue(c['attention_preserved_in_archive'])
        self.assertTrue(c['metadata_preserved'])
        self.assertTrue(c['cancelled_copies_retained'])
        self.assertEqual(c['new_original_sha256'],c['current_input_before']['sha256'])
        self.assertEqual(c['current_input_after'],c['current_input_before'])
        self.assertTrue(c['new_job_created'])

    def test_new_start_preserves_and_refuses_other_attention(self):
        v=self.call('alias_retirement_unknown')
        self.assertNotIn('error',v)
        c=v['cycle']
        self.assertEqual(c['next_error'],'recovery_required')
        self.assertTrue(c['metadata_preserved'])
        self.assertTrue(c['journal_preserved'])

    def refused(self,v):
        self.assertEqual(v.get('error'),'source_changed')
        self.assertNotIn('success',v)
        self.assertEqual(v['before'],v['after'])
        self.assertEqual(v['journal_before'],v['journal_after'])

    def test_start_failure_refuses_samebytes_foreign_inode(self):self.refused(self.call('catch_inode'))
    def test_start_failure_refuses_original_mtime_drift(self):self.refused(self.call('catch_mtime'))
    def test_start_failure_refuses_original_mode_drift(self):self.refused(self.call('catch_mode'))
    def test_explicit_legacy_start_failure_retains_content_only_result(self):
        v=self.call('catch_legacy');self.assertTrue(v.get('success'),v);self.assertEqual(v['before'],v['after']);self.assertEqual(v['journal_after']['state'],'failed');self.assertTrue(v['journal_after']['restored'])
    def test_clean_start_failure_retains_original_noinput_failure_result(self):
        v=self.call('catch_clean');self.assertTrue(v.get('success'),v);self.assertEqual(v['before'],v['after']);self.assertEqual(v['journal_after']['state'],'failed');self.assertTrue(v['journal_after']['restored'])

if __name__=='__main__':unittest.main()
