"""A guarded job validates the viewed draft and cannot publish a stale preview."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP,PUBLIC
from test_smartdns_profile import profile


class SmartDnsValidationJobTests(unittest.TestCase):
    def scenario(self,mode):
        code=r'''$f=$argv[1].'/smartdns-validation.php';if(!is_file($f)){echo json_encode(['error'=>'missing_validation_worker']);exit;}
        require $f;$p=json_decode(stream_get_contents(STDIN),true);$root=$argv[2];$mode=$argv[4];$id=str_repeat('b',32);$base=str_repeat('a',64);
        $store=new AsusSmartDnsStore($root,(int)$argv[3]);$hash=$store->saveDraft($p);$store->beginValidation($id,$hash,$base);$calls=0;$auth=0;
        $deps=['authenticate'=>function()use(&$auth){$auth++;return true;},'baseline'=>function()use(&$calls,$base,$mode){$calls++;return ['hash'=>$mode==='baseline_changed'&&$calls>1?str_repeat('c',64):$base];},
        'candidate'=>function($request)use($mode){if($mode==='candidate_failed')throw new RuntimeException('invalid_configuration');if($mode==='memory')throw new RuntimeException('insufficient_memory');$rows=[];
          foreach($request['names'] as $name)foreach(['A','AAAA'] as $type)$rows[]=['name'=>$name,'type'=>$type,'udp'=>['ok'=>$mode!=='no_network','rcode'=>0,'truncated'=>false,'answers'=>$mode==='no_network'?[]:[$type==='A'?'192.0.2.1':'2001:db8::1']],'tcp'=>null];
          return ['started'=>true,'syntax_ok'=>true,'results'=>$rows];},'bundle'=>fn()=>'/verified-fixture-bundle'];
        if($mode==='no_guard')unset($deps['authenticate']);
        if($mode==='edited_draft'){$p['upstreams'][0]['label']='new copy';$store->saveDraft($p);}
        try{(new AsusSmartDnsValidationJob($store,null,$deps))->work($id);if($mode==='replay')(new AsusSmartDnsValidationJob($store,null,$deps))->work($id);$out=['status'=>$store->status()];}
        catch(Throwable $e){$out=['error'=>$e->getMessage(),'status'=>$store->status()];}
        $out['auth']=$auth;$out['calls']=$calls;$out['preview_exists']=file_exists($root.'/preview.json');
        if($out['preview_exists'])$out['preview']=json_decode(file_get_contents($root.'/preview.json'),true);
        echo json_encode($out);'''
        with tempfile.TemporaryDirectory() as d:
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(Path(d)/'store'),str(os.getuid()),mode],input=json.dumps(profile()),capture_output=True,text=True,timeout=6)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'');return json.loads(p.stdout)

    def test_success_publishes_preview_after_both_baseline_reads(self):
        out=self.scenario('ready');self.assertEqual(out['status']['state'],'preview_ready')
        self.assertEqual(out['auth'],1);self.assertGreaterEqual(out['calls'],2)
        self.assertEqual(out['status']['preview_id'],out['preview']['id'])
        self.assertTrue(out['preview_exists']);self.assertEqual(out['preview']['baseline_hash'],'a'*64)
        self.assertFalse(out['preview']['service_success_tested'])

    def test_changed_draft_baseline_or_invalid_engine_has_no_usable_preview(self):
        for mode,code in [('edited_draft','stale_draft'),('baseline_changed','stale_baseline'),('candidate_failed','invalid_configuration')]:
            with self.subTest(mode=mode):
                out=self.scenario(mode);self.assertEqual(out['status']['state'],'failed')
                self.assertEqual(out['status']['code'],code);self.assertFalse(out['preview_exists'])

    def test_valid_profile_reaches_preview_without_external_dns_answers(self):
        out=self.scenario('no_network')
        self.assertEqual(out['status']['state'],'preview_ready')
        self.assertIsNone(out['status']['code'])
        self.assertTrue(out['preview_exists'])
        self.assertEqual(out['preview']['scope'],'configuration_only')
        self.assertFalse(out['preview']['service_success_tested'])

    def test_unguarded_invocation_cannot_claim_or_mutate_the_job(self):
        out=self.scenario('no_guard');self.assertEqual(out['error'],'guard_unavailable')
        self.assertEqual(out['status']['state'],'validating');self.assertEqual(out['calls'],0)

    def test_process_reservation_failure_retains_resource_error(self):
        out=self.scenario('memory')
        self.assertEqual(out['status']['state'],'failed')
        self.assertEqual(out['status']['code'],'insufficient_memory')
        self.assertFalse(out['preview_exists'])

    def test_finished_job_replay_does_not_rerun_validation(self):
        out=self.scenario('replay');self.assertEqual(out['status']['state'],'preview_ready')
        self.assertEqual(out['auth'],1);self.assertEqual(out['calls'],3)


if __name__=='__main__':unittest.main()
