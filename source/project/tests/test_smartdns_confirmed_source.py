"""Saved consent is a validation source, independent of an unfinished draft."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC
from test_smartdns_profile import profile


class ConfirmedSourceTests(unittest.TestCase):
    def scenario(self, mode):
        code = r'''require $argv[1].'/smartdns-validation.php';
        require_once $argv[1].'/smartdns-connect.php';
        $store=new AsusSmartDnsStore($argv[2],(int)$argv[3]);$a=json_decode(stream_get_contents(STDIN),true);
        $hash=AsusSmartDnsProfile::hash($a);$base=str_repeat('a',64);$id=str_repeat('b',32);$mode=$argv[4];
        $intent=['schema_version'=>1,'profile'=>$a,'profile_hash'=>$hash,'engine_sha'=>str_repeat('e',64),'source_request_id'=>str_repeat('c',32)];
        $store->saveIntent($intent);$b=$a;$b['upstreams'][0]['label']='unfinished next profile';$store->saveDraft($b);
        $bytes=file_get_contents($argv[2].'/draft.json');$observed=null;
        try {
          $store->beginValidation($id,$hash,$base,'confirmed');
          $deps=['authenticate'=>fn()=>true,'baseline'=>fn()=>['hash'=>$base],'bundle'=>fn()=>'/verified-fixture-bundle',
            'candidate'=>function($request)use(&$observed,$store,$mode,$intent){
              $observed=$request['config'];
              if($mode==='revoke')$store->saveIntent(null);
              if($mode==='replace_consent'){$next=$intent;$next['source_request_id']=str_repeat('d',32);$store->saveIntent($next);}
              if($mode==='replace_engine'){$next=$intent;$next['engine_sha']=str_repeat('f',64);$store->saveIntent($next);}
              $rows=[];foreach($request['names'] as $name)foreach(['A','AAAA'] as $type)$rows[]=['name'=>$name,'type'=>$type,
                'udp'=>['ok'=>true,'rcode'=>0,'truncated'=>false,'answers'=>[$type==='A'?'192.0.2.1':'2001:db8::1']],'tcp'=>null];
              return ['started'=>true,'syntax_ok'=>true,'results'=>$rows];}];
          (new AsusSmartDnsValidationJob($store,null,$deps))->work($id);
          $status=$store->status();$out=['state'=>$status['state'],'code'=>$status['code']];
          if($status['state']==='preview_ready'){
            $preview=$store->preview($status['preview_id']);$out['preview_source']=$preview['profile_source']??'draft';
            $out['candidate']=$store->candidate($preview);
            if($mode==='revoke_preview'){$store->saveIntent(null);try{$store->preview($status['preview_id']);$out['revoked_preview']='accepted';}catch(Throwable $e){$out['revoked_preview']=$e->getMessage();}}
            if($mode==='http_apply'){
              try{(new AsusSmartDnsConnection($store))->apply(str_repeat('f',32),$preview['id'],$hash,$base);$out['http']='accepted';}
              catch(Throwable $e){$out['http']=$e->getMessage();}
            }
          }
        }catch(Throwable $e){$out=['error'=>$e->getMessage()];}
        $out['draft_unchanged']=file_get_contents($argv[2].'/draft.json')===$bytes;
        $out['intent_present']=$store->intent()!==null;echo json_encode($out);'''
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), str(Path(d)/'store'), str(os.getuid()), mode],
                               input=json.dumps(profile()), capture_output=True, text=True, timeout=8)
            self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
            self.assertEqual(p.stderr, '')
            return json.loads(p.stdout)

    def test_confirmed_profile_is_validated_without_replacing_next_draft(self):
        out = self.scenario('ready')
        self.assertNotIn('error', out)
        self.assertEqual(out['state'], 'preview_ready')
        self.assertEqual(out['preview_source'], 'confirmed')
        self.assertEqual(out['candidate']['upstreams'][0]['label'], 'main')
        self.assertTrue(out['draft_unchanged'])

    def test_revoked_or_replaced_consent_cannot_publish_a_saved_preview(self):
        for mode in ['revoke', 'replace_consent', 'replace_engine']:
            with self.subTest(mode=mode):
                out = self.scenario(mode)
                self.assertNotIn('error', out)
                self.assertEqual(out['state'], 'failed')
                self.assertTrue(out['draft_unchanged'])

    def test_disconnect_invalidates_an_already_published_saved_preview(self):
        out = self.scenario('revoke_preview')
        self.assertEqual(out.get('revoked_preview'), 'stale_preview', out)
        self.assertFalse(out['intent_present'])
        self.assertTrue(out['draft_unchanged'])

    def test_ordinary_http_apply_cannot_use_a_root_resume_preview(self):
        out = self.scenario('http_apply')
        self.assertEqual(out.get('http'), 'stale_preview', out)
        self.assertTrue(out['draft_unchanged'])
