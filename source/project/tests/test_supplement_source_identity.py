"""Observed original source identities for the prepared-only supplement journal."""
import base64, hashlib, json, os, subprocess, unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC
from test_strategy_supplement import RECIPE
import test_supplement_full_originals as originals_fixture
import test_supplement_local_plan as plan_fixture


class SupplementSourceIdentityTests(unittest.TestCase):
    def setUp(self):
        originals_fixture.SupplementFullOriginalsTests.setUp(self)

    def call(self, fault='', after=False, malformed=False):
        code=r'''require $argv[1].'/import-transaction.php';require_once $argv[1].'/strategy-supplement.php';
        $d=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);$r=$argv[2];$u=(int)$argv[3];$events=[];$observations=[];
        $s=new AsusImportStore($r.'/journal',$u);
        $pin=static function($path){clearstatcache(true,$path);return array_intersect_key(lstat($path),array_flip(['dev','ino','mode','uid','gid','nlink','size','mtime','ctime']));};
        $mutate=function()use($r,$d,$pin,&$observations){
            $path=$r.'/source/'.($d['fault']==='config'?'nfqws2.conf':($d['fault']==='mtime'?'lua/zapret-antidpi.lua':'lists/auto.list'));
            $before=$pin($path);$raw=file_get_contents($path);
            if($d['fault']==='mtime'){if(!touch($path,$before['mtime']+31))throw new RuntimeException('FIXTURE_TOUCH');}
            else{if(!rename($path,$r.'/displaced-original'))throw new RuntimeException('FIXTURE_RENAME');
                if(file_put_contents($path,$raw)!==strlen($raw)||!chmod($path,$before['mode']&0777)||!touch($path,$before['mtime']))throw new RuntimeException('FIXTURE_REPLACE');}
            $observations[]=['path'=>$path,'before'=>$before,'after'=>$pin($path),'sha256'=>hash_file('sha256',$path)];
        };
        $deps=['checkpoint'=>function($phase)use($r,$d,$mutate,&$events){
            $f=fopen($r.'/journal/writer.lock','rb');$held=flock($f,LOCK_EX|LOCK_NB);if($held)flock($f,LOCK_UN);fclose($f);$events[]=['phase'=>$phase,'rival_acquired'=>$held];
            if($phase==='journal'&&$d['fault']!==''&&!$d['after'])$mutate();
        }];
        $t=new AsusImportTransaction($s,new AsusSmartDnsStore($r.'/dns',$u),$r.'/source',$r.'/source/nfqws2.conf',$u,$deps);$binding=$t->supplementState()['binding'];$out=[];
        try{$out['prepared']=$t->supplementPrepareOriginals($d['recipe'],['target.example'],$binding);
            $out['prepared_state']=$s->state();
            if($d['malformed']&&!isset($out['prepared_state']['current']['sources']))$out['missing_manifest']=true;
            elseif($d['malformed']){
                $good=$s->state();$variants=[];
                $a=$good;unset($a['current']['sources']);$variants['missing_sources']=$a;
                $a=$good;unset($a['current']['source_binding_version']);$variants['missing_version']=$a;
                $a=$good;$a['current']['source_binding_version']=2;$variants['version']=$a;
                $a=$good;$a['current']['sources']['extra']=[];$variants['extra_section']=$a;
                $a=$good;unset($a['current']['sources']['config']['ino']);$variants['missing_pin_key']=$a;
                $a=$good;$a['current']['sources']['config']['ino']='not_integer';$variants['pin_type']=$a;
                $a=$good;$a['current']['sources']['config']['nlink']=2;$variants['pin_links']=$a;
                $a=$good;unset($a['current']['sources']['files'][array_key_first($a['current']['sources']['files'])]);$variants['missing_file']=$a;
                $a=$good;$a['current']['sources']['files']['/opt/etc/nfqws2/lists/foreign.list']=$a['current']['sources']['config'];$variants['extra_file']=$a;
                $a=$good;$a['current']['state']='committing';$variants['commit_state']=$a;
                foreach($variants as $name=>$bad){$s->save($bad);try{$s->state();$out['validation'][$name]='BAD_accepted';}catch(Throwable $e){$out['validation'][$name]=$e->getMessage();}}
                $s->save($good);
            }elseif($d['after']){if($d['fault']!=='')$mutate();$out['recovered']=$t->recover();}
        }catch(Throwable $e){$out['error']=$e->getMessage();}
        $out['state']=$s->state();$out['backups']=[];$j=$out['state']['current'];
        foreach($j['backups']??[]as $name=>$p)$out['backups'][$name]=base64_encode($s->read($name));
        $f=fopen($r.'/journal/writer.lock','rb');$out['lock_free_after']=flock($f,LOCK_EX|LOCK_NB);if($out['lock_free_after'])flock($f,LOCK_UN);fclose($f);
        echo json_encode($out+['events'=>$events,'observations'=>$observations],JSON_THROW_ON_ERROR);'''
        request=json.dumps(dict(recipe=RECIPE,fault=fault,after=after,malformed=malformed)).encode()
        (self.temp/'php-r.private').write_text(code);(self.temp/'request.private.json').write_bytes(request)
        q=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(self.temp),str(os.getuid())],input=request,capture_output=True,timeout=25)
        (self.temp/'stdout.private').write_bytes(q.stdout);(self.temp/'stderr.private').write_bytes(q.stderr)
        self.assertEqual((q.returncode,q.stderr),(0,b''),q.stdout.decode()+q.stderr.decode());v=json.loads(q.stdout)
        self.assertTrue(v['lock_free_after']);self.assertTrue(all(x['rival_acquired']is False for x in v['events']))
        return v

    def check_manifest(self,v):
        self.assertNotIn('error',v,v.get('error'));j=v['prepared_state']['current']
        self.assertEqual(j.get('source_binding_version'),1,'missing actual original source identity manifest')
        self.assertEqual(set(j['sources']),{'config','files'})
        self.assertEqual(set(j['sources']['files']),{f['path']for f in j['files']})
        names={'nfqws2.conf':j['sources']['config'],**{k.removeprefix('/opt/etc/nfqws2/'):p for k,p in j['sources']['files'].items()}}
        for name,pin in names.items():
            self.assertEqual(set(pin),{'dev','ino','mode','uid','gid','nlink','size','mtime','ctime'})
            observed=self.before[name]['metadata']
            self.assertEqual(pin,{k:observed['st_'+k+'_ns']//1000000000 if k in ('mtime','ctime')else observed['st_'+k]for k in pin})
        self.assertEqual(len(names),7)

    def refused(self,v):
        self.assertIn('error',v);self.assertNotIn('recovered',v)
        self.assertEqual(v['state']['current']['state'],'restore_required')
        observed=v['observations'];self.assertEqual(len(observed),1)
        path=observed[0]['path'];self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),observed[0]['sha256'])
        self.assertEqual(self.config.read_text(),self.current)

    def test_complete_original_source_manifest_is_observed_without_publication(self):
        v=self.call();self.check_manifest(v)
        self.assertEqual(plan_fixture.SupplementLocalPlanTests.source_pins(self),self.before)
        for flag in ('backup_ready','can_apply','can_export','combined_verified','actual_device_calls'):self.assertIs(v['prepared'][flag],False)

    def test_same_bytes_AUTO_replacement_during_backup_IO_is_preserved_and_refused(self):
        v=self.call('AUTO');self.refused(v);self.assertNotIn('prepared',v)
        self.assertNotEqual(v['observations'][0]['before']['ino'],v['observations'][0]['after']['ino'])
        self.assertEqual((self.temp/'displaced-original').read_bytes(),(self.root/'lists/auto.list').read_bytes())

    def test_same_bytes_config_replacement_during_backup_IO_is_preserved_and_refused(self):
        v=self.call('config');self.refused(v);self.assertNotIn('prepared',v)
        self.assertNotEqual(v['observations'][0]['before']['ino'],v['observations'][0]['after']['ino'])

    def test_source_mtime_change_after_backup_IO_refuses_even_with_exact_bytes(self):
        v=self.call('mtime');self.refused(v);self.assertNotIn('prepared',v)
        self.assertNotEqual(v['observations'][0]['before']['mtime'],v['observations'][0]['after']['mtime'])

    def test_recovery_refuses_later_same_bytes_AUTO_replacement_without_touching_any_source(self):
        v=self.call('AUTO',after=True);self.refused(v);self.assertIn('prepared',v)
        now=plan_fixture.SupplementLocalPlanTests.source_pins(self)
        self.assertEqual({k:p for k,p in now.items()if k!='lists/auto.list'},{k:p for k,p in self.before.items()if k!='lists/auto.list'})

    def test_recovery_refuses_later_same_bytes_config_replacement_without_touching_resources(self):
        v=self.call('config',after=True);self.refused(v);self.assertIn('prepared',v)
        now=plan_fixture.SupplementLocalPlanTests.source_pins(self)
        self.assertEqual({k:p for k,p in now.items()if k!='nfqws2.conf'},{k:p for k,p in self.before.items()if k!='nfqws2.conf'})

    def test_manifest_requires_closed_complete_pair_types_and_prepared_only_states(self):
        v=self.call(malformed=True);self.assertNotIn('error',v,v.get('error'))
        self.assertFalse(v.get('missing_manifest'),'missing source manifest validation')
        self.assertEqual(len(v['validation']),10);self.assertEqual(set(v['validation'].values()),{'invalid_state'})
        self.assertEqual(plan_fixture.SupplementLocalPlanTests.source_pins(self),self.before)

    def test_clean_recovery_retains_complete_source_manifest_and_all_source_inodes(self):
        v=self.call(after=True);self.check_manifest(v);self.assertEqual(v['recovered']['state'],'rolled_back')
        self.assertEqual(v['state']['current']['sources'],v['prepared_state']['current']['sources'])
        self.assertEqual(plan_fixture.SupplementLocalPlanTests.source_pins(self),self.before)


if __name__=='__main__':unittest.main()
