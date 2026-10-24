"""A live engine must not hide replacement of actual dnsmasq forwarding."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC
import test_smartdns_connect as hooks
from test_smartdns_profile import profile


class RoutingStatusTests(unittest.TestCase):
    def test_only_exclusive_managed_default_forwarding_is_reported(self):
        call = hooks.SmartDnsHookTests().call
        for config, expected in [
            ('interface=br0\nno-resolv\nserver=127.0.0.1#6054\n', True),
            ('no-resolv\nserver=1.1.1.1@vpn0\n', False),
            ('no-resolv\nserver=127.0.0.1#6054\nserver=8.8.8.8\n', False),
            ('no-resolv\nserver=127.0.0.1#6054\nconf-file=/opt/vpn/dns.conf\n', False),
            ('server=127.0.0.1#6054\n', False),
        ]:
            with self.subTest(config=config):
                self.assertEqual(call('isForwarded', config), {'value': expected})

    def view(self, mode):
        code=r'''require $argv[1].'/smartdns-config-api.php';
        $root=$argv[2];$store=new AsusSmartDnsStore($root,(int)$argv[3]);$p=json_decode(stream_get_contents(STDIN),true);
        $hash=$store->saveDraft($p);$base=str_repeat('a',64);$id=str_repeat('c',32);$mode=$argv[4];
        $store->savePreview(['id'=>str_repeat('b',32),'profile_hash'=>$hash,'baseline_hash'=>$base,'expires_uptime'=>PHP_FLOAT_MAX]);
        $store->begin($id,$hash,$base);$backup=$store->backup(['candidate_profile'=>$p]);
        $confirmed=$mode!=='preview';
        $store->transition($id,['applying'],['state'=>$confirmed?'confirmed':'preview_ready','active'=>$confirmed?['profile'=>$p,'profile_hash'=>$hash,'backup_id'=>$backup]:null]);
        if($mode!=='manual_off')$store->saveIntent(['schema_version'=>1,'profile'=>$p,'profile_hash'=>$hash,'engine_sha'=>str_repeat('e',64),'source_request_id'=>$id]);
        else $store->transition($id,['confirmed'],['state'=>'rolled_back','active'=>null]);
        $native=$confirmed&&$mode!=='manual_off'?['request_id'=>$id,'profile_hash'=>$hash,'phase'=>'confirmed']:null;
        $before=[];foreach(glob($root.'/*') as $f)if(is_file($f))$before[basename($f)]=hash_file('sha256',$f);
        $out=AsusSmartDnsConfigApi::dispatch(['cmd'=>'smartdnsconfigstatus','csrf_token'=>'test'],[
          'store'=>$store,'jobs_deps'=>['native'=>fn()=>$native,'healthy'=>fn()=>true],
          'routing'=>fn()=>$mode==='managed'?'managed':'external']);
        $after=[];foreach(glob($root.'/*') as $f)if(is_file($f))$after[basename($f)]=hash_file('sha256',$f);
        $out['readonly']=$before===$after;echo json_encode($out);'''
        with tempfile.TemporaryDirectory() as d:
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(Path(d)/'state'),str(os.getuid()),mode],
                             input=json.dumps(profile()),capture_output=True,text=True,timeout=6)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertEqual(p.stderr,'')
            return json.loads(p.stdout)

    def test_confirmed_engine_with_external_forwarding_has_a_visible_warning(self):
        out=self.view('external')
        self.assertEqual(out['status']['state'],'confirmed')
        self.assertEqual(out.get('routing'),'external')
        self.assertEqual(out['resume_code'],'routing_lost')
        self.assertTrue(out['readonly'])

    def test_repaired_forwarding_clears_warning_without_mutating_the_journal(self):
        out=self.view('managed')
        self.assertEqual(out.get('routing'),'managed')
        self.assertIsNone(out['resume_code'])
        self.assertTrue(out['readonly'])

    def test_saved_intent_is_not_hidden_by_a_preview_ready_draft(self):
        out=self.view('preview')
        self.assertEqual(out['resume_code'],'resume_required')
        self.assertTrue(out['readonly'])

    def test_manual_disconnect_does_not_create_resume_intent(self):
        out=self.view('manual_off')
        self.assertIsNone(out['resume_code'])
        self.assertIsNone(out['confirmed_profile'])
        self.assertTrue(out['readonly'])
