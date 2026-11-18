"""Config publication guards under the existing Picker journal and engine lock."""
import base64,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC


class PickerConfigDurabilityTests(unittest.TestCase):
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
        namespace PickerConfigProbe;
        use \NfqwsPlatform;use \NfqwsDeviceProfilesPaths;use \AsusImportConfig;use \NfqwsStrategyPickerMode;use \RuntimeException;use \Throwable;
        function event($op,$path,$extra=[]){$acquired=null;if(\is_file($GLOBALS['r'].'/picker/engine.lock')){$l=\fopen($GLOBALS['r'].'/picker/engine.lock','rb');$acquired=\flock($l,LOCK_EX|LOCK_NB);if($acquired)\flock($l,LOCK_UN);\fclose($l);}$GLOBALS['events'][]=['op'=>$op,'path'=>$path,'rival_acquired'=>$acquired]+$extra;}
        function drift(){if($GLOBALS['drifted'])return;$GLOBALS['drifted']=true;$p=$GLOBALS['r'].'/nfqws2.conf';$raw=\file_get_contents($p);\rename($p,$GLOBALS['r'].'/displaced-config');\file_put_contents($p,$raw);\chmod($p,0664);}
        function fwrite($f,$raw){$uri=\stream_get_meta_data($f)['uri'];if(\str_starts_with(\basename($uri),'.picker-')&&$GLOBALS['fault']==='partial')return \fwrite($f,\substr($raw,0,7));return \fwrite($f,$raw);}
        function fsync($f):bool{
            $uri=\stream_get_meta_data($f)['uri'];$s=\fstat($f);$dir=($s['mode']&0170000)===0040000;$ok=\fsync($f);event('fsync',$uri,['directory'=>$dir,'actual_result'=>$ok]);$mode=$GLOBALS['fault'];
            if(!$dir&&\str_starts_with(\basename($uri),'.stage-')&&$mode==='intent_drift')drift();
            if(!$dir&&\str_starts_with(\basename($uri),'.stage-')&&$mode==='final_journal_drift'){++$GLOBALS['journal_writes'];if($GLOBALS['journal_writes']===2)drift();}
            if(!$dir&&\str_starts_with(\basename($uri),'.picker-')){
                if($mode==='file_false')return false;
                if($mode==='destination_drift')drift();
                if($mode==='stage_swap'){\rename($uri,$GLOBALS['r'].'/displaced-stage');\file_put_contents($uri,'FOREIGN_STAGE_PRESERVE');\chmod($uri,0640);}
            }
            if($dir&&$uri===$GLOBALS['r']&&$mode==='directory_false')return false;
            return $ok;
        }
        function rename($a,$b):bool{
            if($GLOBALS['fault']==='rename_second'&&\str_starts_with(\basename($a),'.picker-')){$now=\time();while(\time()===$now)\usleep(20000);}
            $ok=\rename($a,$b);event('rename',$b,['from'=>$a,'actual_result'=>$ok]);
            if($ok&&$b===$GLOBALS['r'].'/nfqws2.conf'){
                if($GLOBALS['fault']==='published_corrupt')\file_put_contents($b,'CORRUPT_AFTER_CONFIG_RENAME');
                if($GLOBALS['fault']==='published_foreign'){\rename($b,$GLOBALS['r'].'/displaced-published');\file_put_contents($b,"EXACT_LOCAL_CANDIDATE\n");\chmod($b,0664);}
            }return $ok;
        }
        PHP;
        $GLOBALS['r']=$r;$GLOBALS['events']=[];$GLOBALS['fault']='';$GLOBALS['drifted']=false;$GLOBALS['journal_writes']=0;eval($wrapper.$d['body']);
        $pin=static function($p){clearstatcache(true,$p);return array_intersect_key(lstat($p),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));};
        $record=static function($p)use($pin){return ['pin'=>$pin($p),'raw_base64'=>base64_encode(file_get_contents($p))];};
        $global=$d['mode']==='global';$s=$global?new NfqwsStrategyPickerState($r.'/picker',$u):new \PickerConfigProbe\NfqwsStrategyPickerState($r.'/picker',$u);$lock=$s->lock();
        $p=$r.'/nfqws2.conf';file_put_contents($p,"ORIGINAL_OWNER_CONFIG\n");chmod($p,0664);$c=$global?new NfqwsStrategyPickerConfig($s,$p,$u):new \PickerConfigProbe\NfqwsStrategyPickerConfig($s,$p,$u);
        $out=['snapshot'=>$c->snapshot(false),'before'=>$record($p)];$GLOBALS['events']=[];$GLOBALS['fault']=$d['mode'];
        try{$c->replace("EXACT_LOCAL_CANDIDATE\n");$out['candidate']=$record($p);if(in_array($d['mode'],['global','normal','rename_second'],true)){$c->restore();$out['restored']=$s->read()['restored'];}$out['success']=true;}catch(Throwable $e){$out['error']=$e->getMessage();}
        $GLOBALS['fault']='';$out['after']=$record($p);$out['journal']=$s->read();$out['stages']=[];foreach(glob($r.'/.picker-*')as $stage)$out['stages'][$stage]=$record($stage);
        foreach(['displaced-config','displaced-stage','displaced-published']as $name)if(file_exists($r.'/'.$name))$out[$name]=$record($r.'/'.$name);
        $out['events']=$GLOBALS['events'];flock($lock,LOCK_UN);fclose($lock);$l=fopen($r.'/picker/engine.lock','rb');$out['lock_free_after']=flock($l,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($l,LOCK_UN);fclose($l);echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request=json.dumps({'mode':mode,'body':body}).encode()
        for name,raw in [('php-r.private',code.encode()),('request.private.json',request),('actual-classes.private',body.encode())]:(self.root/name).write_bytes(raw)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (self.root/'stdout.private').write_bytes(q.stdout);(self.root/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stderr.decode()[:2500]);v=json.loads(q.stdout)
        self.assertTrue(v['lock_free_after']);self.assertTrue(all(e['rival_acquired']is False for e in v['events']))
        return v

    def refused(self,v):self.assertIn('error',v);self.assertNotIn('success',v)

    def test_config_replace_and_restore_sync_actual_parent_and_preserve_0664_bytes(self):
        v=self.call('normal');self.assertTrue(v.get('success'),v.get('error'));self.assertTrue(v['restored'])
        self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64']);self.assertEqual(v['after']['pin']['mode']&0o777,0o664)
        barriers=[e for e in v['events']if e['op']=='fsync'and e['directory']and e['path']==str(self.root)]
        self.assertEqual(len(barriers),2,'config replace/restore have no actual directory barriers');self.assertTrue(all(e['actual_result']for e in barriers))

    def test_directory_barrier_failure_preserves_uncertain_candidate_without_success(self):
        v=self.call('directory_false');self.refused(v);self.assertEqual(base64.b64decode(v['after']['raw_base64']),b'EXACT_LOCAL_CANDIDATE\n');self.assertFalse(v['journal']['restored'])

    def test_actual_published_corruption_is_refused_and_preserved(self):
        v=self.call('published_corrupt');self.refused(v);self.assertEqual(base64.b64decode(v['after']['raw_base64']),b'CORRUPT_AFTER_CONFIG_RENAME')

    def test_actual_published_same_bytes_foreign_inode_is_refused_and_preserved(self):
        v=self.call('published_foreign');self.refused(v);self.assertEqual(v['after']['raw_base64'],v['displaced-published']['raw_base64']);self.assertNotEqual(v['after']['pin']['ino'],v['displaced-published']['pin']['ino'])

    def test_same_bytes_destination_swap_during_file_sync_is_preserved(self):
        v=self.call('destination_drift');self.refused(v);self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64']);self.assertNotEqual(v['after']['pin']['ino'],v['before']['pin']['ino']);self.assertEqual(v['displaced-config']['raw_base64'],v['before']['raw_base64'])

    def test_same_bytes_destination_swap_during_prior_intent_is_preserved(self):
        v=self.call('intent_drift');self.refused(v);self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64']);self.assertNotEqual(v['after']['pin']['ino'],v['before']['pin']['ino'])

    def test_final_journal_write_cannot_hide_same_bytes_foreign_publication(self):
        v=self.call('final_journal_drift');self.refused(v);self.assertEqual(v['after']['raw_base64'],v['displaced-config']['raw_base64']);self.assertNotEqual(v['after']['pin']['ino'],v['displaced-config']['pin']['ino'])

    def test_swapped_foreign_stage_keeps_actual_bytes_mode_and_displaced_own_stage(self):
        v=self.call('stage_swap');self.refused(v);self.assertEqual(v['after'],v['before']);self.assertEqual(len(v['stages']),1)
        stage=next(iter(v['stages'].values()));self.assertEqual(base64.b64decode(stage['raw_base64']),b'FOREIGN_STAGE_PRESERVE');self.assertEqual(stage['pin']['mode']&0o777,0o640);self.assertEqual(base64.b64decode(v['displaced-stage']['raw_base64']),b'EXACT_LOCAL_CANDIDATE\n')

    def test_partial_config_stage_preserved_and_original_config_unchanged(self):
        v=self.call('partial');self.refused(v);self.assertEqual(v['after'],v['before']);self.assertEqual(len(v['stages']),1,'partial config stage was deleted');self.assertEqual(len(base64.b64decode(next(iter(v['stages'].values()))['raw_base64'])),7)

    def test_config_file_sync_failure_preserves_original_without_publication(self):
        v=self.call('file_false');self.refused(v);self.assertEqual(v['after'],v['before'])

    def test_own_config_rename_may_cross_actual_ctime_second_without_false_conflict(self):
        v=self.call('rename_second');self.assertTrue(v.get('success'),v.get('error'));self.assertTrue(v['restored']);self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64'])

    def test_global_unmodified_production_classes_publish_and_restore_local_config(self):
        v=self.call('global');self.assertTrue(v.get('success'),v.get('error'));self.assertTrue(v['restored']);self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64']);self.assertEqual(base64.b64decode(v['candidate']['raw_base64']),b'EXACT_LOCAL_CANDIDATE\n')


if __name__=='__main__':unittest.main()
