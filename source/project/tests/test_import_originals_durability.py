"""Owned LOCAL backup publication: actual fsync/rename/readers with fault wrappers."""
import base64,hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC

class ImportOriginalsDurabilityTests(unittest.TestCase):
    def call(self,fault='',nested=False,name=None,large=False):
        root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=os.environ['NFQWS_SUPPLEMENT_ARTIFACT_DIR']))
        source=(PUBLIC/'import-store.php').read_text();body=source[source.index('final class AsusImportStore'):]
        code=r'''require $argv[1].'/import-store.php';
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
        $GLOBALS['DURABILITY']=['fault'=>$d['fault'],'active'=>false,'fired'=>false,'events'=>[],'destination'=>null];
        $wrappers=<<<'PHP'
        namespace DurabilityProbe;
        use \AsusShareRead;use \AsusDpiStore;use \NfqwsResourcePaths;use \RuntimeException;use \Throwable;
        function fsync($f):bool {
            $g=&$GLOBALS['DURABILITY'];$s=\fstat($f);$directory=($s['mode']&0170000)===0040000;$path=\stream_get_meta_data($f)['uri'];
            $event=['kind'=>$directory?'directory_fsync':'file_fsync','path'=>$path,'active'=>$g['active']];
            if($g['active']&&(($directory&&$g['fault']==='dir_fail')||(!$directory&&$g['fault']==='file_fail'))){$event['ok']=false;$g['events'][]=$event;return false;}
            $ok=\fsync($f);$event['ok']=$ok;$g['events'][]=$event;
            if($g['active']&&!$directory&&!$g['fired']){
                $g['fired']=true;
                if($g['fault']==='destination_drift')\file_put_contents($g['destination'],'FOREIGN_DESTINATION');
                if($g['fault']==='stage_swap'){
                    \rename($path,$path.'.displaced');\file_put_contents($path,'FOREIGN_STAGE');\chmod($path,0600);$g['foreign_stage']=$path;
                }
            }
            return $ok;
        }
        function rename(string $from,string $to):bool {
            $g=&$GLOBALS['DURABILITY'];$ok=\rename($from,$to);$g['events'][]=['kind'=>'rename','from'=>$from,'to'=>$to,'ok'=>$ok];
            if($ok&&$g['active']){
                if($g['fault']==='published_corrupt')\file_put_contents($to,'CORRUPT_AFTER_RENAME');
                if($g['fault']==='published_swap'){\rename($to,$to.'.displaced');\file_put_contents($to,'FOREIGN_PUBLISHED');\chmod($to,0600);}
            }
            return $ok;
        }
        PHP;
        eval($wrappers.$d['class_body']);
        $directory=$argv[2].($d['nested']?'/new/a/journal':'/journal');$uid=(int)$argv[3];
        $store=new \DurabilityProbe\AsusImportStore($directory,$uid);$store->directory(true);
        $name=$d['name'];$destination=$directory.'/'.$name;
        file_put_contents($destination,'OLD_ORIGINAL');chmod($destination,0600);
        $GLOBALS['DURABILITY']['destination']=$destination;$GLOBALS['DURABILITY']['active']=true;
        $bytes=$d['large']?str_repeat('x',262145):base64_decode($d['raw_base64'],true);$out=['accepted'=>false];
        try{$store->write($name,$bytes);$out['accepted']=true;}catch(Throwable $e){$out['error']=$e->getMessage();}
        $g=$GLOBALS['DURABILITY'];$files=[];
        foreach(scandir($directory)as $name)if($name!=='.'&&$name!=='..')$files[$name]=['raw_base64'=>base64_encode(file_get_contents($directory.'/'.$name)),'metadata'=>lstat($directory.'/'.$name)];
        echo json_encode($out+['events'=>$g['events'],'directory'=>$directory,'files'=>$files,'foreign_stage'=>$g['foreign_stage']??null],JSON_THROW_ON_ERROR);'''
        name=name or 'a'*32+'.file-0';raw=b'\x00original AUTO\n\xff'
        request=json.dumps({'fault':fault,'nested':nested,'name':name,'large':large,'raw_base64':base64.b64encode(raw).decode(),'class_body':body}).encode()
        (root/'original-class.private').write_text(body);(root/'php-r.private').write_text(code);(root/'request.private.json').write_bytes(request)
        run=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (root/'stdout.private').write_bytes(run.stdout);(root/'stderr.private').write_bytes(run.stderr)
        self.assertEqual((run.returncode,run.stderr),(0,b''),run.stdout.decode()+run.stderr.decode());return json.loads(run.stdout),root,name,raw

    def test_file_then_rename_then_directory_fsync_precedes_successful_backup_return(self):
        v,r,n,raw=self.call();self.assertTrue(v['accepted']);events=[e['kind']for e in v['events']if e.get('active',True)]
        self.assertEqual(events,['file_fsync','rename','directory_fsync']);self.assertEqual(base64.b64decode(v['files'][n]['raw_base64']),raw);self.assertEqual(v['files'][n]['metadata']['mode']&0o777,0o600)

    def test_every_new_backup_directory_entry_syncs_its_parent(self):
        v,r,n,raw=self.call(nested=True);self.assertTrue(v['accepted']);parents=[e['path']for e in v['events']if e['kind']=='directory_fsync'and not e['active']]
        self.assertEqual(parents,[str(r),str(r/'new'),str(r/'new/a')])

    def test_postrename_corruption_is_preserved_and_never_successful(self):
        v,r,n,raw=self.call('published_corrupt');self.assertFalse(v['accepted']);self.assertEqual(v.get('error'),'source_changed');self.assertEqual(base64.b64decode(v['files'][n]['raw_base64']),b'CORRUPT_AFTER_RENAME')

    def test_postrename_inode_swap_preserves_foreign_and_displaced_original(self):
        v,r,n,raw=self.call('published_swap');self.assertFalse(v['accepted']);self.assertEqual(v.get('error'),'source_changed');self.assertEqual(base64.b64decode(v['files'][n]['raw_base64']),b'FOREIGN_PUBLISHED');self.assertEqual(base64.b64decode(v['files'][n+'.displaced']['raw_base64']),raw)

    def test_destination_drift_during_stage_is_not_overwritten(self):
        v,r,n,raw=self.call('destination_drift');self.assertFalse(v['accepted']);self.assertEqual(v.get('error'),'source_changed');self.assertEqual(base64.b64decode(v['files'][n]['raw_base64']),b'FOREIGN_DESTINATION');self.assertFalse(any(e['kind']=='rename'for e in v['events']))

    def test_swapped_stage_and_displaced_inode_are_preserved(self):
        v,r,n,raw=self.call('stage_swap');self.assertFalse(v['accepted']);self.assertEqual(v.get('error'),'source_changed');self.assertEqual(base64.b64decode(v['files'][n]['raw_base64']),b'OLD_ORIGINAL')
        path=Path(v['foreign_stage']);self.assertTrue(path.exists());self.assertEqual(path.read_bytes(),b'FOREIGN_STAGE');self.assertEqual(path.with_name(path.name+'.displaced').read_bytes(),raw)

    def test_failed_directory_fsync_leaves_uncertain_published_bytes_and_refuses(self):
        v,r,n,raw=self.call('dir_fail');self.assertFalse(v['accepted']);self.assertEqual(v.get('error'),'storage_unavailable');self.assertEqual(base64.b64decode(v['files'][n]['raw_base64']),raw)

    def test_failed_file_fsync_keeps_prior_backup_and_removes_only_owned_stage(self):
        v,r,n,raw=self.call('file_fail');self.assertFalse(v['accepted']);self.assertEqual(v.get('error'),'insufficient_space');self.assertEqual(set(v['files']),{n});self.assertEqual(base64.b64decode(v['files'][n]['raw_base64']),b'OLD_ORIGINAL')

    def test_same_durable_publication_for_state_and_original_cap_unchanged(self):
        v,r,n,raw=self.call(name='state.json');self.assertTrue(v['accepted']);self.assertEqual([e['kind']for e in v['events']if e.get('active',True)],['file_fsync','rename','directory_fsync'])
        v,r,n,raw=self.call(large=True);self.assertFalse(v['accepted']);self.assertEqual(v.get('error'),'output_limit');self.assertEqual(base64.b64decode(v['files'][n]['raw_base64']),b'OLD_ORIGINAL')

    def test_unmodified_production_class_writes_backup_and_state_under_same_real_mutex(self):
        root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=os.environ['NFQWS_SUPPLEMENT_ARTIFACT_DIR']))
        code=r'''require $argv[1].'/import-store.php';$d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
        $s=new AsusImportStore($argv[2].'/journal',(int)$argv[3]);$raw=base64_decode($d['raw_base64'],true);$name=str_repeat('b',32).'.conf';
        $out=$s->locked(function()use($s,$raw,$name,$argv){
            $rival=fopen($argv[2].'/journal/writer.lock','rb');$held=flock($rival,LOCK_EX|LOCK_NB);if($held)flock($rival,LOCK_UN);fclose($rival);
            $s->write($name,$raw);$state=['schema_version'=>1,'current'=>null,'history'=>[]];$s->save($state);
            return ['rival_acquired'=>$held,'actual_class'=>get_class($s),'backup_sha256'=>hash('sha256',$s->read($name)),'state'=>$s->state()];
        });$rival=fopen($argv[2].'/journal/writer.lock','rb');$out['lock_free_after']=flock($rival,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($rival,LOCK_UN);fclose($rival);
        echo json_encode($out,JSON_THROW_ON_ERROR);'''
        raw=b'USER="nobody"\n# durable original\n';request=json.dumps({'raw_base64':base64.b64encode(raw).decode()}).encode()
        (root/'php-r.private').write_text(code);(root/'request.private.json').write_bytes(request)
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (root/'stdout.private').write_bytes(r.stdout);(root/'stderr.private').write_bytes(r.stderr)
        self.assertEqual((r.returncode,r.stderr),(0,b''),r.stdout.decode()+r.stderr.decode());value=json.loads(r.stdout)
        self.assertEqual(value['actual_class'],'AsusImportStore');self.assertIs(value['rival_acquired'],False);self.assertIs(value['lock_free_after'],True)
        self.assertEqual(value['backup_sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(value['state'],{'schema_version':1,'current':None,'history':[]})
        self.assertEqual((root/'journal'/('b'*32+'.conf')).read_bytes(),raw)

    def test_unowned_leftover_stage_is_not_deleted_by_later_prune(self):
        root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=os.environ['NFQWS_SUPPLEMENT_ARTIFACT_DIR']))
        code=r'''require $argv[1].'/import-store.php';$s=new AsusImportStore($argv[2].'/journal',(int)$argv[3]);$s->directory(true);
        $p=$argv[2].'/journal/.write-'.str_repeat('c',32);file_put_contents($p,'FOREIGN_UNOWNED_STAGE');chmod($p,0600);$before=lstat($p);$out=[];
        try{$s->prune();}catch(Throwable $e){$out['error']=$e->getMessage();}clearstatcache(true,$p);
        echo json_encode($out+['present'=>is_file($p),'before'=>$before,'after'=>is_file($p)?lstat($p):null,'raw'=>is_file($p)?file_get_contents($p):null],JSON_THROW_ON_ERROR);'''
        (root/'php-r.private').write_text(code);(root/'request.private.json').write_text('{}')
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(root),str(os.getuid())],capture_output=True,timeout=25)
        (root/'stdout.private').write_bytes(r.stdout);(root/'stderr.private').write_bytes(r.stderr)
        self.assertEqual((r.returncode,r.stderr),(0,b''),r.stdout.decode()+r.stderr.decode());v=json.loads(r.stdout)
        self.assertEqual(v.get('error'),'restore_required');self.assertIs(v['present'],True);self.assertEqual(v['raw'],'FOREIGN_UNOWNED_STAGE');self.assertEqual(v['before'],v['after'])

if __name__=='__main__':unittest.main()
