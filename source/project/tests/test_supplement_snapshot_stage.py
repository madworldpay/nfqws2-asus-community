"""Prepared-only snapshots never own config/resource publication stages."""
import base64, json, os, subprocess, unittest
from test_dpi_normalize import PHP, PUBLIC
from test_strategy_supplement import RECIPE
import test_supplement_full_originals as originals_fixture
import test_supplement_local_plan as plan_fixture


class SupplementSnapshotStageTests(unittest.TestCase):
    def setUp(self):
        originals_fixture.SupplementFullOriginalsTests.setUp(self)

    def call(self,kind):
        code=r'''require $argv[1].'/import-transaction.php';require_once $argv[1].'/strategy-supplement.php';
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$r=$argv[2];$u=(int)$argv[3];$events=[];
        $s=new AsusImportStore($r.'/journal',$u);$pin=static function($p){clearstatcache(true,$p);$v=lstat($p);return array_intersect_key($v,array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));};
        $deps=['checkpoint'=>function($phase)use($r,&$events){$f=fopen($r.'/journal/writer.lock','rb');$got=flock($f,LOCK_EX|LOCK_NB);if($got)flock($f,LOCK_UN);fclose($f);$events[]=['phase'=>$phase,'rival_acquired'=>$got];}];
        $t=new AsusImportTransaction($s,new AsusSmartDnsStore($r.'/dns',$u),$r.'/source',$r.'/source/nfqws2.conf',$u,$deps);$b=$t->supplementState()['binding'];
        $out=['prepared'=>$t->supplementPrepareOriginals($d['recipe'],['target.example'],$b)];$good=$s->state();$j=$good['current'];$stage=null;
        if($d['kind']==='forged_directory_authority'){
            foreach(['parents','directories']as $key){$bad=$good;$bad['current'][$key]=[];$s->save($bad);try{$s->state();$out['validation'][$key]='BAD_accepted';}catch(Throwable $e){$out['validation'][$key]=$e->getMessage();}}
            $s->save($good);
        }else{
            if($d['kind']!=='none'){
                if($d['kind']==='config')$stage=$r.'/source/.import-'.$j['id'].'-config';
                else{foreach($j['files']as $i=>$f)if(str_ends_with($f['path'],'/auto.list')){$target=$r.'/source/lists/auto.list';$stage=dirname($target).'/.import-'.$j['id'].'-'.$i;}}
                if($stage===null)throw new RuntimeException('FIXTURE_NO_AUTO');
                if($d['kind']==='hardlink'){if(!link($target,$stage))throw new RuntimeException('FIXTURE_LINK');}
                elseif($d['kind']==='symlink'){$foreign=$r.'/foreign-keep';file_put_contents($foreign,'FOREIGN_TARGET');if(!symlink($foreign,$stage))throw new RuntimeException('FIXTURE_SYMLINK');}
                else{if(file_put_contents($stage,'FOREIGN_STAGE_DO_NOT_DELETE')!==strlen('FOREIGN_STAGE_DO_NOT_DELETE')||!chmod($stage,0600))throw new RuntimeException('FIXTURE_WRITE');}
                $out['stage_before']=['path'=>$stage,'pin'=>$pin($stage),'link'=>is_link($stage)?readlink($stage):null,'raw_base64'=>is_link($stage)?null:base64_encode(file_get_contents($stage))];
            }
            try{$out['recovered']=$t->recover();}catch(Throwable $e){$out['error']=$e->getMessage();}
            if($stage!==null){clearstatcache(true,$stage);$out['stage_after']=@lstat($stage)===false?null:['path'=>$stage,'pin'=>$pin($stage),'link'=>is_link($stage)?readlink($stage):null,'raw_base64'=>is_link($stage)?null:base64_encode(file_get_contents($stage))];}
        }
        $out['state']=$s->state();$out['backups']=[];foreach($j['backups']as $name=>$p)$out['backups'][$name]=base64_encode($s->read($name));
        $f=fopen($r.'/journal/writer.lock','rb');$out['lock_free_after']=flock($f,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($f,LOCK_UN);fclose($f);
        echo json_encode($out+['events'=>$events],JSON_THROW_ON_ERROR);'''
        request=json.dumps(dict(kind=kind,recipe=RECIPE)).encode();(self.temp/'php-r.private').write_text(code);(self.temp/'request.private.json').write_bytes(request)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.temp),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (self.temp/'stdout.private').write_bytes(q.stdout);(self.temp/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stderr.decode()[:2000]);v=json.loads(q.stdout)
        self.assertTrue(v['lock_free_after']);self.assertTrue(all(e['rival_acquired']is False for e in v['events']))
        return v

    def preserved(self,v):
        self.assertEqual(v.get('stage_after'),v['stage_before'],'snapshot recovery removed or changed an unowned stage')
        self.assertEqual(v.get('error'),'restore_required');self.assertNotIn('recovered',v)
        self.assertEqual(v['state']['current']['state'],'restore_required')

    def test_foreign_config_stage_survives_snapshot_recovery_untouched(self):
        v=self.call('config');self.preserved(v);self.assertEqual(base64.b64decode(v['stage_after']['raw_base64']),b'FOREIGN_STAGE_DO_NOT_DELETE')
        self.assertEqual(self.config.read_text(),self.current)

    def test_foreign_AUTO_resource_stage_survives_snapshot_recovery_untouched(self):
        v=self.call('resource');self.preserved(v);self.assertEqual((self.root/'lists/auto.list').read_bytes(),b'learned.example\n')

    def test_even_same_inode_hardlinked_stage_is_not_snapshot_owned(self):
        v=self.call('hardlink');self.preserved(v);self.assertEqual(v['stage_after']['pin']['nlink'],2)
        self.assertEqual((self.root/'lists/auto.list').stat().st_ino,v['stage_after']['pin']['ino'])

    def test_existing_symlink_refusal_also_preserves_the_foreign_target(self):
        v=self.call('symlink');self.preserved(v);self.assertEqual((self.temp/'foreign-keep').read_bytes(),b'FOREIGN_TARGET')

    def test_snapshot_journal_cannot_claim_directory_publication_authority(self):
        v=self.call('forged_directory_authority');self.assertEqual(v['validation'],{'parents':'invalid_state','directories':'invalid_state'})
        self.assertEqual(plan_fixture.SupplementLocalPlanTests.source_pins(self),self.before)

    def test_snapshot_with_no_stages_closes_without_source_mutation(self):
        v=self.call('none');self.assertNotIn('error',v);self.assertEqual(v['recovered']['state'],'rolled_back')
        self.assertEqual(plan_fixture.SupplementLocalPlanTests.source_pins(self),self.before)
        self.assertFalse(list(self.root.rglob('.import-*')))


if __name__=='__main__':unittest.main()
