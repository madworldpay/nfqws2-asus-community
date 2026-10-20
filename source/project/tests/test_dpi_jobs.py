import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP,PUBLIC,ROOT


class DpiJobsTests(unittest.TestCase):
    def call(self,script):
        with tempfile.TemporaryDirectory() as directory:
            code='''require $argv[1].'/dpi-jobs.php';try{$s=new AsusDpiStore($argv[2].'/state',(int)$argv[3]);$calls=[];
            $dep=['launch'=>function($id,$kind)use(&$calls){$calls[]=[$id,$kind];},'available'=>fn()=>['available'=>true,'code'=>'ready'],'installed'=>fn()=>true];
            $j=new AsusDpiJobs($s,$dep);'''+script+'''}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),directory,str(os.getuid()),str(ROOT)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)
    def test_default_12_and_all_groups_require_exact_heavy_consent(self):
        for groups,consent,error in [([1,2],[],None),([0,1,2,3,4,5,6],[5,6],None),([5],[],'consent_required'),([2],[5],'invalid_request'),([1,1],[],'invalid_request'),([],[],'invalid_request'),([7],[],'invalid_request')]:
            s='echo json_encode([$j->startRun("11111111-1111-4111-8111-111111111111",'+json.dumps(groups)+','+json.dumps(consent)+'),$calls]);'
            r=self.call(s)
            if error:self.assertEqual(r,{'error':error})
            else:self.assertEqual(r[0]['tests'],groups);self.assertEqual(len(r[1]),1)
    def test_request_replay_never_launches_again(self):
        r=self.call('$a=$j->startRun("11111111-1111-4111-8111-111111111111",[1,2],[]);$b=$j->startRun("11111111-1111-4111-8111-111111111111",[1,2],[]);echo json_encode([$a,$b,count($calls)]);')
        self.assertEqual(r[0]['id'],r[1]['id']);self.assertEqual(r[2],1)
    def test_later_failure_preserves_earlier_group_and_marks_context_change(self):
        script='''$job=$s->reserve('11111111-1111-4111-8111-111111111111','run',['tests'=>[2,3],'heavy_consent'=>[]]);$n=0;
        $w=new AsusDpiWorker($s,['work'=>fn($id)=>$argv[2],'binary'=>fn()=>'/synthetic-detector','probe'=>function($id,$args,$cwd,$limit)use(&$n,$argv){$n++;if($n===2)throw new RuntimeException('timed_out');return ['exit'=>0,'stdout'=>json_encode(json_decode(file_get_contents($argv[4].'/tests/fixtures/dpi/group2.json'),true)['raw'])];},'context'=>function()use(&$n){return ['nfqws'=>'running','ark'=>$n?'absent':'loaded','tun_observed'=>false];}]);
        $w->run($job['id']);echo $s->readResult($job['id']);'''
        r=self.call(script);self.assertEqual(r['state'],'timed_out');self.assertEqual([g['group'] for g in r['groups']],[2]);self.assertTrue(r['context']['changed']);self.assertNotIn('PRIVATE_CANARY',json.dumps(r))
    def test_native_defaults_are_not_replaced_by_a_hidden_limited_profile(self):
        r=self.call('echo json_encode([AsusDpiWorker::arguments("/managed/binary",6),AsusDpiWorker::profile()]);')
        args,profile=r;self.assertIn('--json',args);self.assertIn('--tests',args);self.assertNotIn('--burst',args)
        self.assertNotIn('--proxy',args);self.assertNotIn('--iface',args);self.assertNotIn('--concurrency',args);self.assertEqual(profile['MAX_CONCURRENT'],50);self.assertEqual(profile['PROXY_URL'],None)
        self.assertGreater(len(profile['DNS_AVAILABILITY_SERVERS']),9)
    def test_immutable_user_options_reach_probe_and_native_result(self):
        script='''$job=$j->startRun('11111111-1111-4111-8111-111111111111',[2],[],['interface'=>'br0','config'=>['TIMEOUT'=>2]]);
        $args=null;$w=new AsusDpiWorker($s,['work'=>fn($id)=>$argv[2],'binary'=>fn()=>'/native','probe'=>function($id,$a,$cwd,$limit)use(&$args,$argv){$args=$a;return ['exit'=>0,'stdout'=>json_encode(json_decode(file_get_contents($argv[4].'/tests/fixtures/dpi/group2.json'),true)['raw']),'stderr'=>'original message'];},'context'=>fn()=>['nfqws'=>'running','ark'=>'absent','tun_observed'=>false]]);$w->run($job['id']);echo json_encode([$args,json_decode($s->readNative($job['id']),true),json_decode($s->readResult($job['id']),true)]);'''
        r=self.call(script);self.assertIsInstance(r,list);self.assertIn('br0',r[0]);self.assertEqual(r[1]['settings']['config']['TIMEOUT'],2);self.assertIn('original message',json.dumps(r[1]['messages']));self.assertEqual(r[2]['schema_version'],2)

    def test_native_error_messages_remain_available_when_no_group_completed(self):
        script='''$job=$j->startRun('11111111-1111-4111-8111-111111111111',[2],[]);$w=new AsusDpiWorker($s,['work'=>fn($id)=>$argv[2],'binary'=>fn()=>'/native','probe'=>fn()=>['exit'=>2,'stdout'=>'','stderr'=>'original error'],'context'=>fn()=>['nfqws'=>'running','ark'=>'absent','tun_observed'=>false]]);$w->run($job['id']);echo json_encode([json_decode($s->readNative($job['id']),true),$s->status()['history'][0]['native_available']]);'''
        r=self.call(script);self.assertIsInstance(r,list);self.assertEqual(r[0]['groups'],[]);self.assertIn('original error',json.dumps(r[0]['messages']));self.assertTrue(r[1])
    def test_worker_death_recovers_completed_groups_and_original_messages(self):
        script='''$job=$j->startRun('11111111-1111-4111-8111-111111111111',[2],[]);
        $group=AsusDpiNative::group(json_encode(json_decode(file_get_contents($argv[4].'/tests/fixtures/dpi/group2.json'),true)['raw']),2);
        $s->update($job['id'],['state'=>'running','groups'=>[$group],'messages'=>[['group'=>2,'text'=>'original progress message']]]);
        $path=$argv[2].'/state/jobs.json';$db=json_decode(file_get_contents($path),true);$db['jobs'][$job['id']]['started_at']-=10;file_put_contents($path,json_encode($db));
        $status=$j->status();echo json_encode([$status,json_decode($s->readNative($job['id']),true)]);'''
        r=self.call(script);self.assertIsInstance(r,list);self.assertEqual(r[1]['state'],'interrupted');self.assertIn('original progress message',json.dumps(r[1]['messages']));self.assertNotIn('original progress message',json.dumps(r[0]))

    def test_late_stderr_overflow_keeps_both_exports_of_completed_groups(self):
        script='''$job=$j->startRun('11111111-1111-4111-8111-111111111111',[2,3],[]);$n=0;
        $w=new AsusDpiWorker($s,['work'=>fn($id)=>$argv[2],'binary'=>fn()=>'/native','probe'=>function()use(&$n,$argv){if($n++===0){$raw=json_decode(file_get_contents($argv[4].'/tests/fixtures/dpi/group2.json'),true)['raw'];$raw['local_extra']=str_repeat('x',990000);return ['exit'=>0,'stdout'=>json_encode($raw)];}return ['exit'=>2,'stdout'=>'','stderr'=>str_repeat('e',60000)];},'context'=>fn()=>['nfqws'=>'running','ark'=>'absent','tun_observed'=>false]]);
        $w->run($job['id']);$h=$s->status()['history'][0];$out=['state'=>$h['state'],'code'=>$h['code'],'native_available'=>$h['native_available']];
        try{$raw=$s->readNative($job['id']);$d=json_decode($raw,true);$out['native']=['bytes'=>strlen($raw),'groups'=>array_column($d['groups'],'group'),'messages'=>$d['messages'],'truncated'=>$d['messages_truncated']??false];}catch(Throwable $e){$out['native_error']=$e->getMessage();}
        try{$d=json_decode($s->readResult($job['id']),true);$out['analysis']=['groups'=>array_column($d['groups'],'group'),'state'=>$d['state']];}catch(Throwable $e){$out['analysis_error']=$e->getMessage();}
        echo json_encode($out);'''
        r=self.call(script);self.assertTrue(r['native_available'],r)
        self.assertEqual(r['state'],'partial');self.assertEqual(r['code'],'output_limit')
        self.assertEqual(r['native']['groups'],[2]);self.assertLessEqual(r['native']['bytes'],1048576)
        self.assertTrue(r['native']['truncated']);self.assertIn('omitted',json.dumps(r['native']['messages']))
        self.assertEqual(r['analysis'],{'groups':[2],'state':'partial'})

    def test_exit_error_or_missing_json_is_not_completed(self):
        script='''$job=$s->reserve('11111111-1111-4111-8111-111111111111','run',['tests'=>[2],'heavy_consent'=>[]]);$w=new AsusDpiWorker($s,['work'=>fn($id)=>$argv[2],'binary'=>fn()=>'/synthetic-detector','probe'=>fn()=>['exit'=>1,'stdout'=>'PRIVATE_CANARY'],'context'=>fn()=>['nfqws'=>'unknown','ark'=>'unknown','tun_observed'=>false]]);$w->run($job['id']);echo json_encode($s->status());'''
        r=self.call(script);self.assertEqual(r['history'][0]['state'],'failed');self.assertEqual(r['history'][0]['groups'],[])
