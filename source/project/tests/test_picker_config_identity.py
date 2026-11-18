"""New Picker journals bind actual config identity across fresh Config instances."""
import base64,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC


class PickerConfigIdentityTests(unittest.TestCase):
    def setUp(self):
        artifact=os.environ.get('NFQWS_SUPPLEMENT_ARTIFACT_DIR')
        if artifact:self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=artifact))
        else:
            t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)

    def call(self,mode):
        source=(PUBLIC/'strategy-picker-core.php').read_text();body=source[source.index('final class NfqwsStrategyPickerState'):source.index('/** Export the winner')]
        code=r'''require $argv[1].'/strategy-picker-core.php';$d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$r=$argv[2];$u=(int)$argv[3];
        $wrapper=<<<'PHP'
        namespace PickerIdentityProbe;
        use \NfqwsPlatform;use \NfqwsDeviceProfilesPaths;use \AsusImportConfig;use \NfqwsStrategyPickerMode;use \RuntimeException;use \Throwable;
        function fsync($f):bool{$s=\fstat($f);$uri=\stream_get_meta_data($f)['uri'];$ok=\fsync($f);$dir=($s['mode']&0170000)===0040000;$acquired=null;
            if(\is_file($GLOBALS['r'].'/picker/engine.lock')){$l=\fopen($GLOBALS['r'].'/picker/engine.lock','rb');$acquired=\flock($l,LOCK_EX|LOCK_NB);if($acquired)\flock($l,LOCK_UN);\fclose($l);}
            $GLOBALS['events'][]=['path'=>$uri,'directory'=>$dir,'actual_result'=>$ok,'rival_acquired'=>$acquired];
            if(!$dir&&\str_starts_with(\basename($uri),'.stage-')){++$GLOBALS['writes'];
                if($GLOBALS['fault']==='snapshot_io'){$p=$GLOBALS['r'].'/nfqws2.conf';$raw=\file_get_contents($p);\rename($p,$GLOBALS['r'].'/displaced-config');\file_put_contents($p,$raw);\chmod($p,0664);$GLOBALS['fault']='';}
                if($GLOBALS['fault']==='gap'&&$GLOBALS['writes']===2)return false;
            }return $ok;
        }
        PHP;
        $GLOBALS['r']=$r;$GLOBALS['events']=[];$GLOBALS['writes']=0;$GLOBALS['fault']=$d['mode']==='snapshot_io'?'snapshot_io':'';eval($wrapper.$d['body']);
        $pin=static function($p){clearstatcache(true,$p);return array_intersect_key(lstat($p),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));};
        $record=static function($p)use($pin){return ['pin'=>$pin($p),'raw_base64'=>base64_encode(file_get_contents($p))];};
        $special=in_array($d['mode'],['snapshot_io','gap'],true);$s=$special?new \PickerIdentityProbe\NfqwsStrategyPickerState($r.'/picker',$u):new NfqwsStrategyPickerState($r.'/picker',$u);$lock=$s->lock();$p=$r.'/nfqws2.conf';file_put_contents($p,"ORIGINAL_OWNER_CONFIG\n");chmod($p,0664);
        $make=static function()use($special,$s,$p,$u){return $special?new \PickerIdentityProbe\NfqwsStrategyPickerConfig($s,$p,$u):new NfqwsStrategyPickerConfig($s,$p,$u);};$out=['before'=>$record($p)];
        try{$out['snapshot']=$make()->snapshot(false);$out['snapshot_success']=true;}catch(Throwable $e){$out['snapshot_error']=$e->getMessage();}
        $mode=$d['mode'];$out['parent']=array_intersect_key(lstat($r),array_flip(['dev','ino','mode','uid','gid']));
        if($mode==='manifest')$out['journal_snapshot']=$s->read();
        elseif($mode==='snapshot_io'){}
        elseif($mode==='variants'){
            $base=$s->read();$proto=['version'=>1,'file'=>$p,'original'=>$pin($p),'current'=>$pin($p),'parent'=>$out['parent']];$cases=[];
            foreach(['missing_version','missing_binding','wrong_version','extra_binding','extra_pin','missing_pin','string_pin','nlink','current_metadata','original_size','parent_metadata','wrong_file','original_metadata']as $name){
                $v=$base;$v['config_binding_version']=1;$v['config_binding']=array_diff_key($proto,['version'=>true]);
                switch($name){case 'missing_version':unset($v['config_binding_version']);break;case 'missing_binding':unset($v['config_binding']);break;case 'wrong_version':$v['config_binding_version']=2;break;case 'extra_binding':$v['config_binding']['authority']=true;break;case 'extra_pin':$v['config_binding']['current']['extra']=0;break;case 'missing_pin':unset($v['config_binding']['current']['ctime']);break;case 'string_pin':$v['config_binding']['current']['uid']=(string)$u;break;case 'nlink':$v['config_binding']['current']['nlink']=2;break;case 'current_metadata':++$v['config_binding']['current']['gid'];break;case 'original_size':++$v['config_binding']['original']['size'];break;case 'parent_metadata':++$v['config_binding']['parent']['uid'];break;case 'wrong_file':$v['config_binding']['file']=$r.'/other.conf';break;case 'original_metadata':++$v['config_binding']['original']['uid'];break;}
                $s->write($v);$before=$record($p);$row=['name'=>$name,'before'=>$before];try{$make()->restore();$row['success']=true;}catch(Throwable $e){$row['error']=$e->getMessage();}$row['after']=$record($p);$cases[]=$row;
            }$out['variants']=$cases;
        }else{
            if(in_array($mode,['restore_inode','restore_mtime','restore_mode','fresh_instances'],true))$make()->replace("EXACT_LOCAL_CANDIDATE\n");
            if($mode==='gap'){$GLOBALS['writes']=0;$GLOBALS['fault']='gap';try{$make()->replace("EXACT_LOCAL_CANDIDATE\n");$out['replace_success']=true;}catch(Throwable $e){$out['replace_error']=$e->getMessage();}$GLOBALS['fault']='';}
            if(in_array($mode,['legacy','unowned_known'],true)){$v=$s->read();if($mode==='legacy')unset($v['config_binding_version'],$v['config_binding']);$v['known'][]=hash('sha256',"EXACT_LOCAL_CANDIDATE\n");$s->write($v);file_put_contents($p,"EXACT_LOCAL_CANDIDATE\n");}
            if(in_array($mode,['replace_inode','restore_inode'],true)){$raw=file_get_contents($p);rename($p,$r.'/displaced-config');file_put_contents($p,$raw);chmod($p,0664);}
            if($mode==='restore_mtime')touch($p,$pin($p)['mtime']+3);
            if($mode==='restore_mode')chmod($p,0644);
            $out['operation_before']=$record($p);$out['journal_before']=$s->read();
            try{if($mode==='replace_inode')$make()->replace("EXACT_LOCAL_CANDIDATE\n");else $make()->restore();$out['success']=true;}catch(Throwable $e){$out['error']=$e->getMessage();}
        }
        $out['after']=$record($p);$out['journal']=$s->read();$out['events']=$GLOBALS['events'];if(file_exists($r.'/displaced-config'))$out['displaced']=$record($r.'/displaced-config');
        flock($lock,LOCK_UN);fclose($lock);$l=fopen($r.'/picker/engine.lock','rb');$out['lock_free_after']=flock($l,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($l,LOCK_UN);fclose($l);echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request=json.dumps({'mode':mode,'body':body}).encode()
        for name,raw in [('php-r.private',code.encode()),('request.private.json',request),('actual-classes.private',body.encode())]:(self.root/name).write_bytes(raw)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.root),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (self.root/'stdout.private').write_bytes(q.stdout);(self.root/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stdout.decode()[:2000]+q.stderr.decode()[:1000]);v=json.loads(q.stdout);self.assertTrue(v['lock_free_after']);self.assertTrue(all(e['rival_acquired']in (None,False)and e['actual_result']for e in v['events']))
        return v

    def refused_unchanged(self,v):
        self.assertIn('error',v);self.assertNotIn('success',v);self.assertEqual(v['after'],v['operation_before']);self.assertEqual(v['journal'],v['journal_before'])

    def test_snapshot_journal_binds_complete_actual_original_current_and_parent(self):
        v=self.call('manifest');j=v['journal_snapshot'];self.assertEqual(j.get('config_binding_version'),1);self.assertEqual(j['config_binding'],{'file':str(self.root/'nfqws2.conf'),'original':v['before']['pin'],'current':v['before']['pin'],'parent':v['parent']});self.assertEqual(v['after'],v['before'])

    def test_same_bytes_foreign_inode_before_replace_is_preserved(self):self.refused_unchanged(self.call('replace_inode'))
    def test_same_bytes_foreign_inode_before_restore_is_preserved(self):self.refused_unchanged(self.call('restore_inode'))
    def test_same_inode_changed_mtime_before_restore_is_preserved(self):self.refused_unchanged(self.call('restore_mtime'))
    def test_permission_drift_before_restore_preserves_actual_mode_and_bytes(self):self.refused_unchanged(self.call('restore_mode'))

    def test_fresh_instances_advance_source_observed_binding_after_own_publications(self):
        v=self.call('fresh_instances');self.assertTrue(v.get('success'),v.get('error'));self.assertEqual(v['journal'].get('config_binding',{}).get('current'),v['after']['pin']);self.assertEqual(v['journal']['config_binding']['original'],v['before']['pin']);self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64']);self.assertTrue(v['journal']['restored']);self.assertEqual(v['after']['pin']['mode']&0o777,0o664)

    def test_clean_snapshot_restore_closes_without_same_bytes_config_republication(self):
        v=self.call('clean');self.assertTrue(v.get('success'),v.get('error'));self.assertEqual(v['after'],v['before']);self.assertEqual(v['journal'].get('config_binding',{}).get('current'),v['before']['pin'])

    def test_new_bound_journal_known_hash_cannot_authorize_unobserved_write(self):self.refused_unchanged(self.call('unowned_known'))

    def test_real_publication_followed_by_journal_failure_remains_attention_preserve(self):
        v=self.call('gap');self.assertIn('replace_error',v);self.assertNotIn('replace_success',v);self.refused_unchanged(v);self.assertEqual(base64.b64decode(v['after']['raw_base64']),b'EXACT_LOCAL_CANDIDATE\n')

    def test_snapshot_source_drift_during_real_journal_IO_refuses_prepared_result(self):
        v=self.call('snapshot_io');self.assertIn('snapshot_error',v);self.assertNotIn('snapshot_success',v);self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64']);self.assertNotEqual(v['after']['pin']['ino'],v['before']['pin']['ino']);self.assertEqual(v['after']['raw_base64'],v['displaced']['raw_base64'])

    def test_closed_paired_binding_rejects_all_incomplete_or_invalid_variants(self):
        v=self.call('variants');self.assertEqual(len(v['variants']),13)
        for row in v['variants']:
            with self.subTest(row['name']):self.assertIn('error',row);self.assertNotIn('success',row);self.assertEqual(row['after'],row['before'])

    def test_explicit_legacy_without_both_fields_retains_content_only_crash_recovery(self):
        v=self.call('legacy');self.assertTrue(v.get('success'),v.get('error'));self.assertNotIn('config_binding',v['journal']);self.assertNotIn('config_binding_version',v['journal']);self.assertEqual(v['after']['raw_base64'],v['before']['raw_base64']);self.assertTrue(v['journal']['restored'])


if __name__=='__main__':unittest.main()
