"""Existing Picker journal durability before an actual LOCAL config mutation."""
import base64, hashlib, json, os, subprocess, tempfile, unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC


class PickerJournalDurabilityTests(unittest.TestCase):
    def setUp(self):
        artifact=os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifact:self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=artifact))
        else:
            tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)

    def call(self,mode):
        source=(PUBLIC/'strategy-picker-core.php').read_text()
        body=source[source.index('final class NfqwsStrategyPickerState'):source.index('/** Export the winner')]
        code=r'''require $argv[1].'/strategy-picker-core.php';$d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$r=$argv[2];$u=(int)$argv[3];
        $wrapper=<<<'PHP'
        namespace PickerJournalProbe;
        use \NfqwsPlatform;use \NfqwsDeviceProfilesPaths;use \AsusImportConfig;use \NfqwsStrategyPickerMode;use \RuntimeException;use \Throwable;
        function fsync($f):bool{
            $s=\fstat($f);$uri=\stream_get_meta_data($f)['uri'];$kind=($s['mode']&0170000)===0040000?'directory':'file';$ok=\fsync($f);
            $rival=null;if(\is_file($GLOBALS['probe_root'].'/picker/engine.lock')){$lock=\fopen($GLOBALS['probe_root'].'/picker/engine.lock','rb');$rival=\flock($lock,LOCK_EX|LOCK_NB);if($rival)\flock($lock,LOCK_UN);\fclose($lock);}
            $GLOBALS['probe_events'][]=['op'=>'fsync','kind'=>$kind,'path'=>$uri,'actual_result'=>$ok,'rival_acquired'=>$rival];
            $fault=$GLOBALS['probe_fault'];
            if($kind==='directory'&&$fault==='directory_false')return false;
            if($kind==='file'&&\str_starts_with(\basename($uri),'.stage-')){
                if($fault==='file_false')return false;
                if($fault==='destination_drift'){$p=$GLOBALS['probe_root'].'/picker/state.json';$raw=\file_get_contents($p);\rename($p,$GLOBALS['probe_root'].'/displaced-destination');\file_put_contents($p,$raw);\chmod($p,0600);}
                if($fault==='stage_swap'){\rename($uri,$GLOBALS['probe_root'].'/displaced-stage');\file_put_contents($uri,'FOREIGN_STAGE_PRESERVE');\chmod($uri,0600);}
            }
            return $ok;
        }
        function fwrite($f,$raw){
            if($GLOBALS['probe_fault']==='partial')return \fwrite($f,\substr($raw,0,7));
            return \fwrite($f,$raw);
        }
        function rename($a,$b):bool{
            $ok=\rename($a,$b);$GLOBALS['probe_events'][]=['op'=>'rename','from'=>$a,'to'=>$b,'actual_result'=>$ok];
            if($ok&&$GLOBALS['probe_fault']==='published_corrupt'&&$b===$GLOBALS['probe_root'].'/picker/state.json')\file_put_contents($b,'CORRUPT_AFTER_RENAME');
            return $ok;
        }
        PHP;
        $GLOBALS['probe_root']=$r;$GLOBALS['probe_fault']='';$GLOBALS['probe_events']=[];eval($wrapper.$d['body']);
        $pin=static function($p){clearstatcache(true,$p);return array_intersect_key(lstat($p),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));};
        $s=$d['mode']==='global'?new NfqwsStrategyPickerState($r.'/picker',$u):new \PickerJournalProbe\NfqwsStrategyPickerState($r.'/picker',$u);$lock=$s->lock();$out=[];
        if(in_array($d['mode'],['intent','global'],true)){
            $path=$r.'/nfqws2.conf';file_put_contents($path,"ORIGINAL_OWNER_CONFIG\n");chmod($path,0664);
            $c=$d['mode']==='global'?new NfqwsStrategyPickerConfig($s,$path,$u):new \PickerJournalProbe\NfqwsStrategyPickerConfig($s,$path,$u);
            $out['snapshot']=$c->snapshot(false);$out['config_before']=['pin'=>$pin($path),'raw_base64'=>base64_encode(file_get_contents($path))];
        }else $s->write(['tag'=>'before']);
        $p=$r.'/picker/state.json';$out['before']=['pin'=>$pin($p),'raw_base64'=>base64_encode(file_get_contents($p))];
        $out['setup_events']=$GLOBALS['probe_events'];$GLOBALS['probe_events']=[];$GLOBALS['probe_fault']=$d['mode']==='intent'?'directory_false':$d['mode'];
        try{
            if($d['mode']==='global'){$c->replace("EXACT_LOCAL_CANDIDATE\n");$out['candidate']=base64_encode($c->raw());$c->restore();$out['restored']=$s->read()['restored'];}
            elseif($d['mode']==='intent')$c->replace("EXACT_LOCAL_CANDIDATE\n");
            else $s->write($d['value']);
            $out['success']=true;
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $GLOBALS['probe_fault']='';$out['after']=['pin'=>$pin($p),'raw_base64'=>base64_encode(file_get_contents($p))];
        if(isset($c))$out['config_after']=['pin'=>$pin($path),'raw_base64'=>base64_encode(file_get_contents($path))];
        $out['stages']=[];foreach(glob($r.'/picker/.stage-*')as $name)$out['stages'][$name]=['pin'=>$pin($name),'raw_base64'=>base64_encode(file_get_contents($name))];
        $out['events']=$GLOBALS['probe_events'];flock($lock,LOCK_UN);fclose($lock);$f=fopen($r.'/picker/engine.lock','rb');$out['lock_free_after']=flock($f,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($f,LOCK_UN);fclose($f);
        echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request=json.dumps(dict(mode=mode,body=body,value={'tag':'actual_new_journal','text':'Русский LOCAL buffer'})).encode()
        for name,raw in [('php-r.private',code.encode()),('request.private.json',request),('actual-classes.private',body.encode())]:(self.root/name).write_bytes(raw)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (self.root/'stdout.private').write_bytes(q.stdout);(self.root/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stderr.decode()[:2500]);v=json.loads(q.stdout)
        self.assertTrue(v['lock_free_after']);self.assertTrue(all(e.get('rival_acquired')is False for e in v['events']if e['op']=='fsync'))
        return v

    def test_published_journal_has_actual_directory_barrier_and_exact_readback(self):
        v=self.call('normal');self.assertTrue(v.get('success'),v.get('error'))
        barriers=[e for e in v['events']if e['op']=='fsync'and e['kind']=='directory'];self.assertTrue(barriers,'missing directory durability barrier');self.assertTrue(all(e['actual_result']for e in barriers))
        self.assertEqual(json.loads(base64.b64decode(v['after']['raw_base64'])),{'tag':'actual_new_journal','text':'Русский LOCAL buffer'})
        self.assertEqual(v['after']['pin']['mode']&0o777,0o600)

    def test_new_journal_root_creation_syncs_its_actual_guarded_parent(self):
        v=self.call('normal');self.assertTrue(v.get('success'),v.get('error'))
        self.assertTrue(any(e['op']=='fsync'and e['kind']=='directory'and e['path']==str(self.root)and e['actual_result']for e in v['setup_events']),'new root entry has no actual parent fsync')

    def test_directory_fsync_failure_refuses_without_rolling_back_published_bytes(self):
        v=self.call('directory_false');self.assertIn('error',v.keys());self.assertNotIn('success',v)
        self.assertEqual(json.loads(base64.b64decode(v['after']['raw_base64']))['tag'],'actual_new_journal')

    def test_actual_after_rename_corruption_is_preserved_and_refused(self):
        v=self.call('published_corrupt');self.assertIn('error',v.keys());self.assertNotIn('success',v)
        self.assertEqual(base64.b64decode(v['after']['raw_base64']),b'CORRUPT_AFTER_RENAME')

    def test_same_bytes_foreign_destination_inode_is_preserved_before_publication(self):
        v=self.call('destination_drift');self.assertIn('error',v.keys());self.assertNotIn('success',v)
        self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64']);self.assertNotEqual(v['after']['pin']['ino'],v['before']['pin']['ino'])
        self.assertEqual((self.root/'displaced-destination').read_bytes(),base64.b64decode(v['before']['raw_base64']))

    def test_swapped_stage_and_displaced_original_are_preserved_without_publication(self):
        v=self.call('stage_swap');self.assertIn('error',v.keys());self.assertNotIn('success',v)
        self.assertEqual(v['after'],v['before']);self.assertEqual(len(v['stages']),1)
        self.assertEqual(base64.b64decode(next(iter(v['stages'].values()))['raw_base64']),b'FOREIGN_STAGE_PRESERVE');self.assertTrue((self.root/'displaced-stage').exists())

    def test_partial_stage_is_retained_instead_of_deleting_unknown_bytes(self):
        v=self.call('partial');self.assertIn('error',v.keys());self.assertEqual(v['after'],v['before']);self.assertEqual(len(v['stages']),1,'partial stage was deleted')
        self.assertEqual(len(base64.b64decode(next(iter(v['stages'].values()))['raw_base64'])),7)

    def test_file_fsync_failure_preserves_previous_journal(self):
        v=self.call('file_false');self.assertIn('error',v.keys());self.assertNotIn('success',v);self.assertEqual(v['after'],v['before'])

    def test_actual_config_replace_stops_when_intent_journal_directory_barrier_fails(self):
        v=self.call('intent');self.assertIn('error',v.keys());self.assertNotIn('success',v)
        self.assertEqual(v['config_after'],v['config_before']);self.assertEqual(base64.b64decode(v['config_after']['raw_base64']),b'ORIGINAL_OWNER_CONFIG\n')

    def test_unmodified_global_Picker_state_and_config_complete_local_replace_restore(self):
        v=self.call('global');self.assertTrue(v.get('success'),v.get('error'));self.assertTrue(v['restored'])
        self.assertEqual(base64.b64decode(v['candidate']),b'EXACT_LOCAL_CANDIDATE\n');self.assertEqual(v['config_after']['raw_base64'],v['config_before']['raw_base64'])
        self.assertEqual(v['config_after']['pin']['mode']&0o777,0o664)


if __name__=='__main__':unittest.main()
