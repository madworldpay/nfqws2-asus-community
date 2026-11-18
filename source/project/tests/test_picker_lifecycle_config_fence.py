"""Real Config/State plus exact lifecycle methods with explicit actuator DOUBLES."""
import base64,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC


class PickerLifecycleConfigFenceTests(unittest.TestCase):
    def setUp(self):
        artifact=os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifact:self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=artifact))
        else:
            t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)

    def call(self,mode):
        runtime=(PUBLIC/'strategy-picker-runtime.php').read_text();methods=''
        for first,last in [('    private function running():bool','    private static function sameProcess'),('    private function service(string $action):void','    public function status():array'),('    private function phase(string $phase,array $extra=[]):void','    private function launch('),('    private function restore(bool $boot=false):void','    public function work(')]:methods+=runtime[runtime.index(first):runtime.index(last)]
        code=r'''require $argv[1].'/strategy-picker-runtime.php';$d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$r=$argv[2];$u=(int)$argv[3];
        $double=<<<'PHP'
        namespace LifecycleConfigProbe;
        use \NfqwsStrategyPickerState;use \NfqwsStrategyPickerConfig;use \NfqwsDeviceProfilesPaths;use \RuntimeException;use \Throwable;
        function event($kind,$action){$l=\fopen($GLOBALS['r'].'/picker/engine.lock','rb');$a=\flock($l,LOCK_EX|LOCK_NB);if($a)\flock($l,LOCK_UN);\fclose($l);$GLOBALS['events'][]=['kind'=>$kind,'action'=>$action,'rival_acquired'=>$a];}
        function drift(){if($GLOBALS['drifted'])return;$GLOBALS['drifted']=true;$p=$GLOBALS['r'].'/nfqws2.conf';$raw=\file_get_contents($p);\rename($p,$GLOBALS['r'].'/displaced-config');\file_put_contents($p,$raw);\chmod($p,0664);}
        // Service commands and diagnostics are explicit DOUBLES. No actual
        // guard, process, engine, device, ROOT admission or native validator.
        final class NfqwsPlatform{
            public static function settings():array{return ['config'=>$GLOBALS['r']];}
            public static function serviceCommand($action):array{return [$action];}
            public static function run($argv,$seconds,$extra=[],$limit=65536):array{event('diagnostics',$argv[0]);if($GLOBALS['mode']==='service_diag')drift();return ['status'=>0,'output'=>[\json_encode(['process_running'=>$GLOBALS['running'],'nfqueue'=>['state'=>'bound']])]];}
        }
        final class LifecycleHarness{
            public function __construct(private NfqwsStrategyPickerState $store,private NfqwsStrategyPickerConfig $config){}
            private function actor($role,$id,&$pin=null):array{$pin=['guard'=>'EXPLICIT_MODEL'];return ['guard'=>'EXPLICIT_MODEL'];}
            private function actuator(array $argv,int $seconds,?string $input=null,?callable $checkpoint=null,bool $waitForServiceLock=false):array{if(!$waitForServiceLock||$seconds!==60||$input!==null)throw new RuntimeException('invalid_service_lock_budget');event('actuator',$argv[0]);$GLOBALS['running']=$argv[0]==='start';if($GLOBALS['mode']==='service_actuator')drift();return ['status'=>0,'output'=>'LOCAL_ACTUATOR_DOUBLE'];}
            private function stopOwnedProbe():void{event('probe_cleanup','owned-probe-DOUBLE');if($GLOBALS['mode']==='restore_cleanup')drift();}
        PHP;
        $GLOBALS['r']=$r;$GLOBALS['mode']=$d['mode'];$GLOBALS['events']=[];$GLOBALS['drifted']=false;$GLOBALS['running']=false;eval($double.$d['methods'].'}');
        $pin=static function($p){clearstatcache(true,$p);return array_intersect_key(lstat($p),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));};$record=static function($p)use($pin){return ['pin'=>$pin($p),'raw_base64'=>base64_encode(file_get_contents($p))];};
        $s=new NfqwsStrategyPickerState($r.'/picker',$u);$lock=$s->lock();$p=$r.'/nfqws2.conf';file_put_contents($p,"ORIGINAL_OWNER_CONFIG\n");chmod($p,0664);$c=new NfqwsStrategyPickerConfig($s,$p,$u);$mode=$d['mode'];$out=['original'=>$record($p)];
        if($mode!=='no_journal')$c->snapshot(str_starts_with($mode,'restore_'));
        if(str_starts_with($mode,'restore_'))$c->replace("EXACT_LOCAL_CANDIDATE\n");
        if($mode==='legacy'){$v=$s->read();unset($v['config_binding_version'],$v['config_binding']);$s->write($v);file_put_contents($p,'FOREIGN_LEGACY_READ_ONLY');}
        if(in_array($mode,['raw_inode','service_foreign','restore_foreign','restore_boot_foreign'],true))\LifecycleConfigProbe\drift();
        if($mode==='raw_mtime')touch($p,$pin($p)['mtime']+4);
        $out['before']=$record($p);$out['journal_before']=$s->read();$out['default_raw']=base64_encode($c->raw());
        $rival=fopen($r.'/picker/engine.lock','rb');$out['lock_conflict_before']=!flock($rival,LOCK_EX|LOCK_NB);if(!$out['lock_conflict_before'])flock($rival,LOCK_UN);fclose($rival);
        $h=new \LifecycleConfigProbe\LifecycleHarness($s,$c);
        try{
            if(str_starts_with($mode,'service_')){(new ReflectionMethod($h,'service'))->invoke($h,'start');if($mode==='service_clean')(new ReflectionMethod($h,'service'))->invoke($h,'stop');}
            elseif(str_starts_with($mode,'restore_'))(new ReflectionMethod($h,'restore'))->invoke($h,$mode==='restore_boot_foreign');
            else $out['bound_raw']=base64_encode($c->raw(true));
            $out['success']=true;
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        if($mode==='service_foreign'){try{(new ReflectionMethod($h,'service'))->invoke($h,'stop');$out['stop_success']=true;}catch(Throwable $e){$out['stop_error']=$e->getMessage();}}
        $out['after']=$record($p);$out['journal']=$s->read();$out['events']=$GLOBALS['events'];if(file_exists($r.'/displaced-config'))$out['displaced']=$record($r.'/displaced-config');
        flock($lock,LOCK_UN);fclose($lock);$l=fopen($r.'/picker/engine.lock','rb');$out['lock_free_after']=flock($l,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($l,LOCK_UN);fclose($l);echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request=json.dumps({'mode':mode,'methods':methods}).encode()
        for name,raw in [('php-r.private',code.encode()),('request.private.json',request),('actual-lifecycle-methods.private',methods.encode())]:(self.root/name).write_bytes(raw)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (self.root/'stdout.private').write_bytes(q.stdout);(self.root/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stdout.decode()[:2000]+q.stderr.decode()[:1000]);v=json.loads(q.stdout);self.assertTrue(v['lock_conflict_before']);self.assertTrue(v['lock_free_after']);self.assertTrue(all(e['rival_acquired']is False for e in v['events']));return v

    def test_bound_read_rejects_actual_foreign_same_bytes_inode(self):
        v=self.call('raw_inode');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after'],v['before']);self.assertEqual(v['default_raw'],v['before']['raw_base64']);self.assertEqual(v['journal'],v['journal_before'])
    def test_bound_read_rejects_mtime_drift_and_preserves_actual_metadata(self):
        v=self.call('raw_mtime');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after'],v['before'])
    def test_bound_read_requires_actual_journal_and_generic_read_still_works(self):
        v=self.call('no_journal');self.assertIn('error',v);self.assertNotIn('success',v);self.assertIsNone(v['journal']);self.assertEqual(v['default_raw'],v['before']['raw_base64'])
    def test_clean_bound_read_returns_guarded_bytes_without_mutation(self):
        v=self.call('clean');self.assertTrue(v.get('success'),v.get('error'));self.assertEqual(v['bound_raw'],v['before']['raw_base64']);self.assertEqual(v['after'],v['before']);self.assertEqual(v['journal'],v['journal_before'])
    def test_explicit_legacy_read_retains_content_only_semantics_without_authority(self):
        v=self.call('legacy');self.assertTrue(v.get('success'),v.get('error'));self.assertEqual(base64.b64decode(v['bound_raw']),b'FOREIGN_LEGACY_READ_ONLY');self.assertEqual(v['after'],v['before']);self.assertEqual(v['events'],[])
    def test_foreign_config_refuses_start_and_stop_before_any_actuator(self):
        v=self.call('service_foreign');self.assertIn('error',v);self.assertIn('stop_error',v);self.assertNotIn('success',v);self.assertNotIn('stop_success',v);self.assertEqual(v['events'],[]);self.assertEqual(v['after'],v['before'])
    def test_actual_config_drift_during_actuator_double_refuses_service_success(self):
        v=self.call('service_actuator');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after']['raw_base64'],v['displaced']['raw_base64']);self.assertNotEqual(v['after']['pin']['ino'],v['displaced']['pin']['ino'])
    def test_actual_config_drift_during_diagnostics_double_refuses_service_success(self):
        v=self.call('service_diag');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after']['raw_base64'],v['displaced']['raw_base64'])
    def test_clean_start_stop_boundaries_keep_real_config_and_journal_unchanged(self):
        v=self.call('service_clean');self.assertTrue(v.get('success'),v.get('error'));self.assertEqual([e['action']for e in v['events']if e['kind']=='actuator'],['start','stop']);self.assertEqual(v['after'],v['before']);self.assertEqual(v['journal'],v['journal_before'])
    def test_restore_foreign_config_refuses_before_probe_cleanup_and_service_stop(self):
        v=self.call('restore_foreign');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['events'],[]);self.assertEqual(v['after'],v['before']);self.assertEqual(v['journal'],v['journal_before'])
    def test_drift_during_probe_cleanup_refuses_next_service_actuator(self):
        v=self.call('restore_cleanup');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual([e['kind']for e in v['events']],['probe_cleanup']);self.assertEqual(v['after']['raw_base64'],v['displaced']['raw_base64'])
    def test_clean_restore_uses_actual_config_writer_before_double_original_start(self):
        v=self.call('restore_clean');self.assertTrue(v.get('success'),v.get('error'));self.assertEqual(v['after']['raw_base64'],v['original']['raw_base64']);self.assertEqual(v['journal']['config_binding']['current'],v['after']['pin']);self.assertTrue(v['journal']['restored']);self.assertEqual([e['action']for e in v['events']if e['kind']=='actuator'],['stop','start']);self.assertEqual(v['after']['pin']['mode']&0o777,0o664)
    def test_boot_foreign_restore_is_already_refused_without_actuators(self):
        v=self.call('restore_boot_foreign');self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['events'],[]);self.assertEqual(v['after'],v['before'])


if __name__=='__main__':unittest.main()
