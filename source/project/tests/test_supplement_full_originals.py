"""Exact saved LOCAL plan/full actual kit -> existing journal originals only."""
import base64,hashlib,json,os,subprocess,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC
from test_strategy_supplement import RECIPE
import test_supplement_local_plan as plan_fixture


class SupplementFullOriginalsTests(unittest.TestCase):
    def setUp(self):
        plan_fixture.SupplementLocalPlanTests.setUp(self)
        (self.root/'blobs/custom.bin').write_bytes(b'\x00FULL_ORIGINAL_BLOB\xff')
        self.current=self.config.read_text().replace(' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua"',' --lua-init=@/opt/etc/nfqws2/lua/zapret-antidpi.lua --blob=owned:@/opt/etc/nfqws2/blobs/custom.bin"').replace('--lua-desync=multidisorder:pos=2','--lua-desync=fake:blob=owned')
        self.config.write_text(self.current)
        self.before=plan_fixture.SupplementLocalPlanTests.source_pins(self)
        (self.temp/'SOURCE-BEFORE.private.json').write_text(json.dumps(self.before))

    def call(self,mode):
        code=r'''require $argv[1].'/import-transaction.php';require_once $argv[1].'/strategy-supplement.php';
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$r=$argv[2];$u=(int)$argv[3];
        if($d['mode']!=='ordinary'&&!method_exists('AsusImportTransaction','supplementPrepareOriginals')){echo json_encode(['missing_api'=>true]);exit;}
        $s=new AsusImportStore($r.'/journal',$u);$events=[];$fired=false;
        $deps=['checkpoint'=>function($phase)use($r,$d,$s,&$events,&$fired){
            $f=fopen($r.'/journal/writer.lock','rb');$held=flock($f,LOCK_EX|LOCK_NB);if($held)flock($f,LOCK_UN);fclose($f);$events[]=['phase'=>$phase,'rival_acquired'=>$held];
            if($phase==='journal'&&!$fired){$fired=true;$j=$s->state()['current'];
                if($d['mode']==='metadata_drift')chmod($r.'/source/lists/auto.list',0640);
                if($d['mode']==='AUTO_drift')file_put_contents($r.'/source/lists/auto.list','FOREIGN_AUTO');
                if($d['mode']==='backup_corrupt')foreach($j['files']as $i=>$file)if(str_ends_with($file['path'],'/auto.list'))file_put_contents($r.'/journal/'.$j['id'].'.file-'.$i,'CORRUPT_ORIGINAL');
            }
        }];$t=new AsusImportTransaction($s,new AsusSmartDnsStore($r.'/dns',$u),$r.'/source',$r.'/source/nfqws2.conf',$u,$deps);
        $binding=$t->supplementState()['binding'];$out=[];$rival=null;
        if($d['mode']==='rival'){$rival=fopen($r.'/journal/writer.lock','rb');if(!flock($rival,LOCK_EX|LOCK_NB))throw new RuntimeException('FIXTURE_NO_RIVAL');}
        try{
            if($d['mode']==='ordinary'){$saved=$t->supplementPortablePreview($d['recipe'],['target.example'],$binding,true);$out['ordinary_apply']=$t->apply($saved['local_plan'],str_repeat('a',32));$out['ordinary_undo']=$t->undo(str_repeat('a',32));}
            else{$out['result']=$t->supplementPrepareOriginals($d['recipe'],['target.example'],$binding);
                if($d['mode']==='pending'){try{$t->supplementPrepareOriginals($d['recipe'],['target.example'],$binding);$out['BAD_second']=true;}catch(Throwable $e){$out['second_error']=$e->getMessage();}}
                if($d['mode']==='recover')$out['recovered']=$t->recover();
            }
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        if($rival!==null){flock($rival,LOCK_UN);fclose($rival);}
        $out['state']=$s->state();$backups=[];$j=$out['state']['current'];
        if($j!==null){foreach($j['backups']as $name=>$pin)$backups[$name]=['raw_base64'=>base64_encode($s->read($name)),'pin'=>$pin];}
        $f=fopen($r.'/journal/writer.lock','rb');$out['lock_free_after']=flock($f,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($f,LOCK_UN);fclose($f);
        echo json_encode($out+['events'=>$events,'backups'=>$backups],JSON_THROW_ON_ERROR);'''
        request=json.dumps(dict(recipe=RECIPE,mode=mode)).encode();(self.temp/'php-r.private').write_text(code);(self.temp/'request.private.json').write_bytes(request)
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.temp),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (self.temp/'stdout.private').write_bytes(p.stdout);(self.temp/'stderr.private').write_bytes(p.stderr)
        self.assertEqual((p.returncode,p.stderr),(0,b''),p.stdout.decode()+p.stderr.decode());v=json.loads(p.stdout);self.assertFalse(v.get('missing_api'),'missing full originals preparation API')
        self.assertTrue(v['lock_free_after']);self.assertTrue(all(e['rival_acquired']is False for e in v['events']));return v

    def test_full_kit_including_reused_AUTO_is_durably_copied_without_source_publication(self):
        v=self.call('normal');self.assertNotIn('error',v,v.get('error'));r=v['result'];j=v['state']['current'];self.assertEqual(j['state'],'prepared')
        self.assertEqual(j['id'],r['journal_id']);self.assertEqual(j['before'],hashlib.sha256(self.current.encode()).hexdigest());self.assertEqual(j['after'],r['local_plan_binding']['postplan_config_sha256'])
        self.assertEqual(len(j['files']),6);self.assertEqual(len(j['backups']),7);self.assertEqual(j['request_digest'],r['originals_binding_sha256'])
        for i,file in enumerate(j['files']):
            self.assertEqual(file['before'],file['sha256']);source=self.root/file['path'].removeprefix('/opt/etc/nfqws2/')
            self.assertEqual(base64.b64decode(v['backups'][j['id']+f'.file-{i}']['raw_base64']),source.read_bytes())
        self.assertEqual(plan_fixture.SupplementLocalPlanTests.source_pins(self),self.before)
        for key in ['backup_ready','can_apply','can_export','combined_verified','actual_device_calls']:self.assertIs(r[key],False)
        self.assertFalse(any(e['phase'].startswith(('stage_','file_','config'))for e in v['events']))

    def test_prepared_original_journal_closes_duplicate_entry_without_rewriting_backups(self):
        v=self.call('pending');self.assertEqual(v.get('second_error'),'busy');self.assertNotIn('BAD_second',v);self.assertEqual(v['state']['current']['state'],'prepared')
        self.assertEqual(plan_fixture.SupplementLocalPlanTests.source_pins(self),self.before)

    def test_external_writer_refuses_before_any_original_backup_or_journal(self):
        v=self.call('rival');self.assertEqual(v.get('error'),'busy');self.assertIsNone(v['state']['current']);self.assertEqual(v['backups'],[])
        self.assertEqual(plan_fixture.SupplementLocalPlanTests.source_pins(self),self.before)

    def test_AUTO_drift_during_snapshot_preserves_foreign_bytes_and_requires_attention(self):
        v=self.call('AUTO_drift');self.assertNotIn('result',v);self.assertIn('error',v);self.assertEqual(v['state']['current']['state'],'restore_required')
        self.assertEqual((self.root/'lists/auto.list').read_bytes(),b'FOREIGN_AUTO');self.assertEqual(self.config.read_text(),self.current)

    def test_corrupt_original_backup_is_preserved_without_source_mutation(self):
        v=self.call('backup_corrupt');self.assertNotIn('result',v);self.assertEqual(v['state']['current']['state'],'restore_required')
        self.assertEqual(plan_fixture.SupplementLocalPlanTests.source_pins(self),self.before);self.assertTrue(any(base64.b64decode(x['raw_base64'])==b'CORRUPT_ORIGINAL'for x in v['backups'].values()))

    def test_existing_recovery_closes_clean_prepared_snapshot_without_republishing_resources(self):
        v=self.call('recover');self.assertNotIn('error',v,v.get('error'));self.assertEqual(v['recovered']['state'],'rolled_back');self.assertEqual(plan_fixture.SupplementLocalPlanTests.source_pins(self),self.before)

    def test_extracted_preparation_preserves_ordinary_config_last_apply_and_undo(self):
        v=self.call('ordinary');self.assertNotIn('error',v,v.get('error'));self.assertEqual(v['ordinary_apply']['state'],'committed');self.assertEqual(v['ordinary_undo']['state'],'undone')
        self.assertEqual(self.config.read_text(),self.current);self.assertEqual(v['state']['current']['files'],[])
        now=plan_fixture.SupplementLocalPlanTests.source_pins(self);self.assertEqual({k:x for k,x in now.items()if k!='nfqws2.conf'},{k:x for k,x in self.before.items()if k!='nfqws2.conf'})


    def test_source_permission_drift_is_preserved_and_refused_after_backup_IO(self):
        v=self.call('metadata_drift');self.assertNotIn('result',v);self.assertEqual(v['state']['current']['state'],'restore_required')
        self.assertEqual((self.root/'lists/auto.list').stat().st_mode&0o777,0o640);self.assertEqual(self.config.read_text(),self.current)


    def test_own_backup_rename_accepts_observed_ctime_change_across_actual_second(self):
        source=(PUBLIC/'import-store.php').read_text();body=source[source.index('final class AsusImportStore'):]
        code=r'''require $argv[1].'/import-store.php';$d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
        $wrapper=<<<'PHP'
        namespace RenameCtimeProbe;
        use \AsusShareRead;use \AsusDpiStore;use \NfqwsResourcePaths;use \RuntimeException;use \Throwable;
        function fsync($f):bool{
            $ok=\fsync($f);$s=\fstat($f);
            if(($s['mode']&0170000)===0100000){$start=\time();while(\time()===$start)\usleep(10000);$GLOBALS['ctime_observed_before_rename']=$s['ctime'];}
            return $ok;
        }
        PHP;
        eval($wrapper.$d['body']);$s=new \RenameCtimeProbe\AsusImportStore($argv[2].'/ctime-journal',(int)$argv[3]);$name=str_repeat('c',32).'.conf';$out=[];
        try{$s->write($name,'ACTUAL_ORIGINAL');$out['success']=true;}catch(Throwable $e){$out['error']=$e->getMessage();}
        $p=$argv[2].'/ctime-journal/'.$name;clearstatcache(true,$p);$out['actual_metadata']=lstat($p);$out['actual_raw']=file_get_contents($p);$out['before_rename_ctime']=$GLOBALS['ctime_observed_before_rename'];echo json_encode($out,JSON_THROW_ON_ERROR);'''
        request=json.dumps(dict(body=body)).encode();(self.temp/'php-r.private').write_text(code);(self.temp/'request.private.json').write_bytes(request);(self.temp/'actual-class.private').write_text(body)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.temp),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (self.temp/'stdout.private').write_bytes(q.stdout);(self.temp/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stdout.decode()+q.stderr.decode());v=json.loads(q.stdout)
        self.assertGreater(v['actual_metadata']['ctime'],v['before_rename_ctime']);self.assertTrue(v.get('success'),v.get('error'));self.assertEqual(v['actual_raw'],'ACTUAL_ORIGINAL')


if __name__=='__main__':unittest.main()
