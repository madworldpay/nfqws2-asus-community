"""Real bounded State files for measured artifacts; no device or quality receipt."""
import json, os, subprocess, tempfile, unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC

class MeasuredResultStoreTests(unittest.TestCase):
    def run_php(self, body):
        with tempfile.TemporaryDirectory(prefix='measured-results-',dir=os.environ.get('TMPDIR')) as temp:
            code="require $argv[1].'/strategy-picker-core.php';$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);"+body
            p=subprocess.run([str(PHP),'-r',code,str(PUBLIC),temp,str(os.getuid())],text=True,capture_output=True,timeout=25)
            self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)

    def test_later_AUTO_and_failed_parent_do_not_replace_an_earlier_measured_artifact(self):
        v=self.run_php(r"""$job=str_repeat('a',32);$s->write(['id'=>$job,'state'=>'running']);
          $first=['job_id'=>$job,'round'=>1,'profile'=>['id'=>'candidate','variant'=>['NFQWS_ARGS'=>'first'],'runs'=>[['sample_id'=>'first']]],'files'=>['lists/AUTO'=>['data'=>base64_encode('AUTO-first'),'sha256'=>hash('sha256','AUTO-first')]]];
          $a=$s->createMeasuredResult($first);$before=stat($s->root.'/job-'.$job.'/result-'.$a['id'].'.json');
          $second=$first;$second['round']=2;$second['profile']['variant']['NFQWS_ARGS']='second';$second['files']['lists/AUTO']=['data'=>base64_encode('AUTO-second'),'sha256'=>hash('sha256','AUTO-second')];
          $b=$s->createMeasuredResult($second);$s->write(['id'=>$job,'state'=>'failed','code'=>'detector_failed']);
          clearstatcache();echo json_encode(['first'=>$s->measuredResult($a,$job),'second'=>$s->measuredResult($b,$job),'original_identity_exact'=>$before===stat($s->root.'/job-'.$job.'/result-'.$a['id'].'.json'),'parent'=>$s->read()]);""")
        self.assertEqual(v['first']['profile']['variant']['NFQWS_ARGS'],'first')
        self.assertEqual(v['first']['files']['lists/AUTO']['data'],'QVVUTy1maXJzdA==')
        self.assertEqual(v['second']['profile']['variant']['NFQWS_ARGS'],'second')
        self.assertTrue(v['original_identity_exact']);self.assertEqual(v['parent']['state'],'failed')

    def test_wrong_parent_or_changed_artifact_cannot_acquire_a_result_receipt(self):
        v=self.run_php(r"""$job=str_repeat('a',32);$s->write(['id'=>$job,'state'=>'running']);$a=$s->createMeasuredResult(['job_id'=>$job,'profile'=>[],'files'=>[]]);$errors=[];
          foreach([$a+['foreign'=>true],['id'=>$a['id'],'sha256'=>str_repeat('0',64)]]as $ref){try{$s->measuredResult($ref,$job);$errors[]='ACCEPTED';}catch(Throwable $e){$errors[]=$e->getMessage();}}
          try{$s->measuredResult($a,str_repeat('b',32));$errors[]='ACCEPTED';}catch(Throwable $e){$errors[]=$e->getMessage();}
          file_put_contents($s->root.'/job-'.$job.'/result-'.$a['id'].'.json','{}');try{$s->measuredResult($a,$job);$errors[]='ACCEPTED';}catch(Throwable $e){$errors[]=$e->getMessage();}
          echo json_encode($errors);""")
        self.assertEqual(len(v),4);self.assertNotIn('ACCEPTED',v)

    def test_archived_job_still_owns_its_measured_artifact_after_a_new_start(self):
        v=self.run_php(r"""$id=str_repeat('a',32);$s->write(['id'=>$id,'state'=>'running']);
          $ref=$s->createMeasuredResult(['job_id'=>$id,'profile'=>['name'=>'first measured program'],'files'=>['lists/AUTO'=>['data'=>base64_encode('original AUTO')]]]);
          $done=['id'=>$id,'state'=>'failed','restored'=>true,'measured_results'=>[$ref]];$s->write($done);
          $history=new NfqwsStrategyPickerState($s->root.'/job-'.$id,(int)$argv[3]);$history->write($done);
          $s->write(['id'=>str_repeat('b',32),'state'=>'running']);$out=[];
          try{$out['old']=$history->measuredResult($ref,$id);}catch(Throwable $e){$out['error']=$e->getMessage();}
          try{$s->measuredResult($ref,str_repeat('b',32));$out['cross_job_accepted']=true;}catch(Throwable $e){$out['cross_job_accepted']=false;}
          echo json_encode($out);""")
        self.assertNotIn('error',v,'Starting another generation made a preserved measured result unavailable')
        self.assertEqual(v['old']['profile']['name'],'first measured program')
        self.assertFalse(v['cross_job_accepted'])

    def test_complete_export_larger_than_one_state_file_keeps_its_own_bytes(self):
        v=self.run_php(r"""$id=str_repeat('a',32);$s->write(['id'=>$id,'state'=>'running']);
          if(!method_exists($s,'createMeasuredDocument')){echo json_encode(['available'=>false]);exit;}
          $original=json_encode(['fixture'=>'opaque exported JSON byte fixture, not a device result','AUTO'=>str_repeat('original-AUTO-',90000)]);
          $ref=$s->createMeasuredDocument(['job_id'=>$id,'profile'=>['name'=>'first']],$original);
          $later=$s->createMeasuredDocument(['job_id'=>$id,'profile'=>['name'=>'second']],str_replace('original-AUTO-','modified-AUTO-',$original));
          $s->write(['id'=>$id,'state'=>'failed','restored'=>true]);$files=glob($s->root.'/job-'.$id.'/result-*.json');
          echo json_encode(['available'=>true,'old_sha'=>hash('sha256',$s->measuredDocument($ref,$id)),'expected'=>hash('sha256',$original),'new_sha'=>hash('sha256',$s->measuredDocument($later,$id)),'largest_file'=>max(array_map('filesize',$files)),'document_bytes'=>strlen($original)]);""")
        self.assertTrue(v['available'],'A complete immutable result document still cannot be retained within existing State file bounds')
        self.assertGreater(v['document_bytes'],1048576)
        self.assertLessEqual(v['largest_file'],1048576)
        self.assertEqual(v['old_sha'],v['expected']);self.assertNotEqual(v['new_sha'],v['old_sha'])

    def test_result_document_survives_archival_and_rejects_changed_content_part(self):
        v=self.run_php(r"""$id=str_repeat('a',32);$s->write(['id'=>$id,'state'=>'running']);
          if(!method_exists($s,'createMeasuredDocument')){echo json_encode(['available'=>false]);exit;}
          $raw=str_repeat('immutable resource snapshot ',20000);$ref=$s->createMeasuredDocument(['job_id'=>$id,'profile'=>['name'=>'first']],$raw);
          $done=['id'=>$id,'state'=>'failed','restored'=>true];$s->write($done);$old=new NfqwsStrategyPickerState($s->root.'/job-'.$id,(int)$argv[3]);$old->write($done);
          $s->write(['id'=>str_repeat('b',32),'state'=>'running']);$before=hash('sha256',$old->measuredDocument($ref,$id));
          $artifact=$old->measuredResult($ref,$id);$part=$artifact['document']['parts'][0];file_put_contents($old->path('result-'.$part['id'].'.json'),'{}');
          $changed_accepted=false;try{$old->measuredDocument($ref,$id);$changed_accepted=true;}catch(Throwable $e){}
          echo json_encode(['available'=>true,'before'=>$before,'expected'=>hash('sha256',$raw),'changed_accepted'=>$changed_accepted]);""")
        self.assertTrue(v['available']);self.assertEqual(v['before'],v['expected']);self.assertFalse(v['changed_accepted'])

if __name__=='__main__':unittest.main()
