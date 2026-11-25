"""Reuse the actual guarded State buffer for journal reads and Config fences."""
import base64,json,os,subprocess,tempfile,unittest,time
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC


class PickerJournalReaderTests(unittest.TestCase):
    def setUp(self):
        artifact=os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifact:self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=artifact))
        else:
            t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)

    def call(self,mode):
        core=(PUBLIC/'strategy-picker-core.php').read_text();body=core[core.index('final class NfqwsStrategyPickerState'):core.index('/** Export the winner')]
        code=r'''require $argv[1].'/strategy-picker-core.php';$d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$r=$argv[2];$u=(int)$argv[3];
        $wrapper=<<<'PHP'
        namespace JournalReaderProbe;
        use \NfqwsPlatform;use \AsusImportConfig;use \NfqwsStrategyPickerMode;use \RuntimeException;use \Throwable;
        final class NfqwsDeviceProfilesPaths {
            public static function guard($directory,$name,$owner) {
                if($GLOBALS['armed']&&$GLOBALS['mode']==='before_lock'&&$name==='state.json'){
                    $handle=\fopen($directory,'rb');
                    try{
                        $acquired=\flock($handle,LOCK_EX|LOCK_NB);
                        $GLOBALS['guard_checks'][]=$acquired;
                        if($acquired)throw new RuntimeException('unsafe_panel_file');
                    }finally{\fclose($handle);}
                }
                return \class_exists('NfqwsDeviceProfilesPaths',false)
                    ?\NfqwsDeviceProfilesPaths::guard($directory,$name,$owner)
                    :NfqwsPlatform::guardFile($directory,$name,$owner);
            }
        }
        function class_exists($class,$autoload=true){
            return ($class==='NfqwsDeviceProfilesPaths'&&$GLOBALS['mode']==='before_lock')||\class_exists($class,$autoload);
        }
        function swap(){if($GLOBALS['drifted'])return;$GLOBALS['drifted']=true;$p=$GLOBALS['target'];$raw=\file_get_contents($p);\rename($p,$GLOBALS['r'].'/displaced-journal');\file_put_contents($p,$raw);\chmod($p,0600);}
        function lstat($p){
            if($GLOBALS['armed']&&$GLOBALS['mode']==='between'&&$p===$GLOBALS['target']&&$GLOBALS['reads']===1&&!$GLOBALS['drifted']){
                if($GLOBALS['read_kind']==='file'||$GLOBALS['postread_stats']++>=1)swap();
            }return \lstat($p);
        }
        function afterRead($p,$raw,$kind){
            if(!$GLOBALS['armed']||$p!==$GLOBALS['target'])return $raw;++$GLOBALS['reads'];$GLOBALS['read_kind']=$kind;
            $l=\fopen($GLOBALS['r'].'/picker/engine.lock','rb');$a=\flock($l,LOCK_EX|LOCK_NB);if($a)\flock($l,LOCK_UN);\fclose($l);$GLOBALS['events'][]=['kind'=>$kind,'rival_acquired'=>$a];
            if(!$GLOBALS['drifted']){
                if(\in_array($GLOBALS['mode'],['swap','actor'],true))swap();
                if($GLOBALS['mode']==='corrupt'){$GLOBALS['drifted']=true;\file_put_contents($p,'BROKEN_JOURNAL_AFTER_READ');}
                if($GLOBALS['mode']==='mtime'){$GLOBALS['drifted']=true;$s=\lstat($p);\touch($p,$s['mtime']+3);}
            }return $raw;
        }
        function file_get_contents($p,...$args){return afterRead($p,\file_get_contents($p,...$args),'file');}
        function stream_get_contents($f,...$args){return afterRead(\stream_get_meta_data($f)['uri'],\stream_get_contents($f,...$args),'fd');}
        PHP;
        $GLOBALS['r']=$r;$GLOBALS['mode']=$d['mode'];$GLOBALS['armed']=false;$GLOBALS['drifted']=false;$GLOBALS['reads']=0;$GLOBALS['read_kind']='';$GLOBALS['postread_stats']=0;$GLOBALS['events']=[];$GLOBALS['guard_checks']=[];eval($wrapper.$d['body']);
        $pin=static function($p){clearstatcache(true,$p);return array_intersect_key(lstat($p),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));};$record=static function($p)use($pin){return ['pin'=>$pin($p),'raw_base64'=>base64_encode(file_get_contents($p))];};
        $mode=$d['mode'];$global=in_array($mode,['pin','missing','default','invalid','cap','clean_config'],true);$s=$global?new NfqwsStrategyPickerState($r.'/picker',$u):new \JournalReaderProbe\NfqwsStrategyPickerState($r.'/picker',$u);$lock=$s->lock();$name=$mode==='actor'?'actor-guard.json':'state.json';$p=$s->path($name);$GLOBALS['target']=$p;$out=[];
        if(in_array($mode,['between','clean_config'],true)){$cf=$r.'/nfqws2.conf';file_put_contents($cf,"ORIGINAL_OWNER_CONFIG\n");chmod($cf,0664);$c=$global?new NfqwsStrategyPickerConfig($s,$cf,$u):new \JournalReaderProbe\NfqwsStrategyPickerConfig($s,$cf,$u);$c->snapshot(false);$out['config_before']=$record($cf);}
        elseif($mode!=='missing')$s->write(['kind'=>'LOCAL_READER_BYTES_ONLY','value'=>'Русский журнал'], $name);
        if($mode==='invalid')file_put_contents($p,'partial{');if($mode==='cap')file_put_contents($p,str_repeat('x',1048577));
        $out['before']=file_exists($p)?$record($p):null;$observed=['sentinel'=>1];$GLOBALS['armed']=true;
        try{
            if(isset($c))$out['result_raw']=base64_encode($c->raw(true));
            elseif(in_array($mode,['pin','missing'],true))$out['result']=$s->read($name,$observed);
            else $out['result']=$s->read($name);
            $out['success']=true;
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $GLOBALS['armed']=false;$out['observed_pin']=$observed;$out['after']=file_exists($p)?$record($p):null;$out['events']=$GLOBALS['events'];$out['actual_target_reads']=$GLOBALS['reads'];$out['drifted']=$GLOBALS['drifted'];$out['guard_checks']=$GLOBALS['guard_checks'];if(file_exists($r.'/displaced-journal'))$out['displaced']=$record($r.'/displaced-journal');if(isset($cf))$out['config_after']=$record($cf);
        flock($lock,LOCK_UN);fclose($lock);$l=fopen($r.'/picker/engine.lock','rb');$out['lock_free_after']=flock($l,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($l,LOCK_UN);fclose($l);echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request=json.dumps({'mode':mode,'body':body}).encode()
        for name,raw in [('php-r.private',code.encode()),('request.private.json',request),('actual-classes.private',body.encode())]:(self.root/name).write_bytes(raw)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (self.root/'stdout.private').write_bytes(q.stdout);(self.root/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stdout.decode()[:2000]+q.stderr.decode()[:1000]);v=json.loads(q.stdout);self.assertTrue(v['lock_free_after']);self.assertTrue(all(e['rival_acquired']is False for e in v['events']));return v

    def test_actual_writer_waits_for_guard_journal_read_without_false_source_change(self):
        setup=r"require $argv[1].'/strategy-picker-core.php';$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$s->write(['phase'=>'before']);"
        args=[str(PUBLIC),str(self.root),str(os.getuid())]
        q=subprocess.run([PHP,'-n','-r',setup,*args],capture_output=True,timeout=20)
        self.assertEqual((q.returncode,q.stderr),(0,b''))
        core=(PUBLIC/'strategy-picker-core.php').read_text();body=core[core.index('final class NfqwsStrategyPickerState'):core.index('/** Export the winner')]
        (self.root/'state-classes.php').write_text(body)
        reader=r"""require $argv[1].'/strategy-picker-core.php';$r=$argv[2];
        $wrapper=<<<'PHP'
        namespace ActualJournalRead;
        use \NfqwsPlatform;use \NfqwsDeviceProfilesPaths;use \RuntimeException;use \Throwable;
        function stream_get_contents($f,...$args){$v=\stream_get_contents($f,...$args);$p=\stream_get_meta_data($f)['uri'];
          if(\basename($p)==='state.json'){\file_put_contents($GLOBALS['root'].'/read-held','held');$end=\microtime(true)+3;while(!\file_exists($GLOBALS['root'].'/writer-attempt')){if(\microtime(true)>$end)throw new RuntimeException('fixture_writer_not_started');\usleep(10000);}\usleep(250000);}return $v;}
        PHP;
        $GLOBALS['root']=$r;eval($wrapper.file_get_contents($r.'/state-classes.php'));$s=new \ActualJournalRead\NfqwsStrategyPickerState($r.'/picker',(int)$argv[3]);
        try{$v=$s->read();echo json_encode(['value'=>$v,'writer_finished_while_reading'=>file_exists($r.'/writer-done')],JSON_THROW_ON_ERROR);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()],JSON_THROW_ON_ERROR);}"""
        writer=r"require $argv[1].'/strategy-picker-core.php';$r=$argv[2];$s=new NfqwsStrategyPickerState($r.'/picker',(int)$argv[3]);file_put_contents($r.'/writer-attempt','attempt');$s->write(['phase'=>'after']);file_put_contents($r.'/writer-done','done');echo json_encode($s->read(),JSON_THROW_ON_ERROR);"
        processes=[]
        try:
            read=subprocess.Popen([PHP,'-n','-r',reader,*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE);processes.append(read)
            end=time.monotonic()+5
            while not (self.root/'read-held').exists():
                self.assertLess(time.monotonic(),end,'actual reader did not reach held read')
                time.sleep(.01)
            write=subprocess.Popen([PHP,'-n','-r',writer,*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE);processes.append(write)
            rout,rerr=read.communicate(timeout=20);wout,werr=write.communicate(timeout=20)
            for name,raw in [('reader.stdout',rout),('reader.stderr',rerr),('writer.stdout',wout),('writer.stderr',werr)]:(self.root/name).write_bytes(raw)
            self.assertEqual((read.returncode,rerr,write.returncode,werr),(0,b'',0,b''))
            value=json.loads(rout)
            self.assertEqual(value.get('value'),{'phase':'before'},value)
            self.assertFalse(value['writer_finished_while_reading'])
            self.assertEqual(json.loads(wout),{'phase':'after'})
        finally:
            for process in processes:
                if process.poll() is None:process.kill()
                process.wait(timeout=5)

    def test_named_journal_validation_waits_for_the_directory_lock(self):
        result=self.call('before_lock')
        self.assertTrue(result.get('success'),result.get('error'))
        self.assertEqual(result['guard_checks'],[False,False])
        self.assertEqual(result['result']['kind'],'LOCAL_READER_BYTES_ONLY')
        self.assertEqual(result['after'],result['before'])

    def test_global_read_returns_actual_full_PHP9_pin_of_same_guarded_JSON(self):
        v=self.call('pin');self.assertTrue(v.get('success'),v.get('error'));self.assertEqual(v['observed_pin'],v['before']['pin']);self.assertEqual(v['after'],v['before']);self.assertEqual(v['result']['kind'],'LOCAL_READER_BYTES_ONLY')
    def test_missing_global_read_clears_optional_pin_and_returns_null(self):
        v=self.call('missing');self.assertTrue(v.get('success'),v.get('error'));self.assertIsNone(v['result']);self.assertIsNone(v['observed_pin']);self.assertIsNone(v['after'])
    def test_named_journal_swap_after_actual_read_refuses_stale_JSON(self):
        v=self.call('swap');self.assertTrue(v['drifted']);self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64']);self.assertNotEqual(v['after']['pin']['ino'],v['before']['pin']['ino'])
    def test_actor_named_reader_swap_preserves_unknown_actor_file_without_acceptance(self):
        v=self.call('actor');self.assertTrue(v['drifted']);self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after']['raw_base64'],v['displaced']['raw_base64'])
    def test_actual_postread_corrupt_bytes_are_preserved_without_returning_old_JSON(self):
        v=self.call('corrupt');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(base64.b64decode(v['after']['raw_base64']),b'BROKEN_JOURNAL_AFTER_READ')
    def test_actual_same_inode_mtime_drift_during_read_refuses_stale_JSON(self):
        v=self.call('mtime');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after']['pin']['ino'],v['before']['pin']['ino']);self.assertEqual(v['after']['pin']['mtime'],v['before']['pin']['mtime']+3)
    def test_Config_fence_rejects_same_JSON_foreign_journal_inode_between_TWO_clean_reads(self):
        v=self.call('between');self.assertTrue(v['drifted']);self.assertEqual(v['actual_target_reads'],2);self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64']);self.assertNotEqual(v['after']['pin']['ino'],v['before']['pin']['ino']);self.assertEqual(v['config_after'],v['config_before'])
    def test_default_global_reader_preserves_existing_JSON_result(self):
        v=self.call('default');self.assertTrue(v.get('success'),v.get('error'));self.assertEqual(v['result'],{'kind':'LOCAL_READER_BYTES_ONLY','value':'Русский журнал'});self.assertEqual(v['after'],v['before'])
    def test_global_invalid_JSON_remains_error_and_preserves_actual_bytes(self):
        v=self.call('invalid');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after'],v['before'])
    def test_global_reader_cap_remains_1MiB_and_preserves_oversized_file(self):
        v=self.call('cap');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after'],v['before']);self.assertEqual(v['after']['pin']['size'],1048577)
    def test_global_Config_bound_reader_accepts_actual_clean_same_journal(self):
        v=self.call('clean_config');self.assertTrue(v.get('success'),v.get('error'));self.assertEqual(v['config_after'],v['config_before']);self.assertEqual(v['after'],v['before']);self.assertEqual(v['result_raw'],v['config_before']['raw_base64'])

    def test_browser_close_and_connection_expiry_are_permanent_for_that_job(self):
        code = r"""
        require $argv[1].'/strategy-picker-runtime.php';
        $store=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);
        $runtime=new NfqwsStrategyPickerRuntime($store);
        $job=['id'=>str_repeat('a',32),'request_id'=>str_repeat('b',32),
            'window_id'=>str_repeat('c',32),'state'=>'preparing','boot'=>AsusUpdateStore::boot()];
        $presence=['cmd'=>'pickerwindow','csrf_token'=>'fixture','request_id'=>$job['request_id'],
            'window_id'=>$job['window_id'],'presence'=>'open'];
        $out=[];
        $out['too_early']=$runtime->dispatch($presence)['recorded'];
        $store->openBrowser($job);
        $store->write($job);
        $out['initial']=$store->browserState($job);
        $out['foreign']=$runtime->dispatch(array_replace($presence,['window_id'=>str_repeat('d',32),'presence'=>'closed']))['recorded'];
        $out['first_pulse']=$runtime->dispatch($presence)['recorded'];
        $out['live']=$store->browserState($job);
        $out['exit']=$runtime->dispatch(array_replace($presence,['presence'=>'closed']))['recorded'];
        $out['after_exit']=$store->browserState($job);
        $out['late_after_exit']=$runtime->dispatch($presence)['recorded'];
        $job['id']=str_repeat('e',32);
        $store->openBrowser($job);
        $store->write($job);
        $pulse=$store->read('browser.json');
        $pulse['until']=AsusUpdateStore::uptime()-1;
        $store->write($pulse,'browser.json');
        $out['after_loss']=$store->browserState($job);
        $out['late_after_loss']=$runtime->dispatch($presence)['recorded'];
        $out['apply']=$store->browserState(array_replace($job,['state'=>'applying']));
        unset($job['window_id']);
        $out['legacy']=$store->browserState($job);
        echo json_encode($out,JSON_THROW_ON_ERROR);
        """
        result=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],
                              capture_output=True,text=True,timeout=20)
        self.assertEqual((result.returncode,result.stderr),(0,''),result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout),{
            'too_early':False,'initial':'waiting','foreign':False,'first_pulse':True,'live':'present',
            'exit':True,'after_exit':'closed','late_after_exit':False,'after_loss':'closed',
            'late_after_loss':False,'apply':'present','legacy':'present',
        })


if __name__=='__main__':unittest.main()
