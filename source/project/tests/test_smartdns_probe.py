"""Profile readiness must not impose an external resolver availability gate."""
import json
import subprocess
import unittest
from test_dpi_normalize import PHP, PUBLIC
from test_smartdns_profile import profile, upstream


class SmartDnsProbeTests(unittest.TestCase):
    def validate(self, value=None, mode='ready'):
        code = r'''$file=$argv[1].'/smartdns-probe.php';
        if(!is_file($file)){echo json_encode(['value'=>['error'=>'missing_probe_coordinator'],'events'=>[]]);exit;}
        require $file;$input=json_decode(stream_get_contents(STDIN),true);$events=[];$time=100.0;
        $deps=['uptime'=>function()use(&$time){return $time;},'bundle'=>fn()=>'/trusted/bundle',
          'baseline'=>fn()=>['hash'=>str_repeat('a',64)],
          'candidate'=>function($request)use(&$events,&$time,$input){
            $events[]=$request;$mode=$input['mode'];
            if($mode==='busy')throw new RuntimeException('port_busy');
            if($mode==='memory')throw new RuntimeException('insufficient_memory');
            if($mode==='budget')$time+=95;
            $out=[];
            foreach($request['names'] as $name)foreach(['A','AAAA'] as $type){
              $ok=$type==='A' && !str_contains($request['config'],'wrong.example') && $mode!=='fail';
              $answer=['ok'=>$ok,'rcode'=>0,'truncated'=>false,'answers'=>$ok?['192.0.2.1']:[],'reason'=>'PRIVATE_ERROR_CANARY'];
              if($mode==='nodata' && $name!=='example.com')$answer=['ok'=>false,'rcode'=>0,'truncated'=>false,'answers'=>[],'reason'=>'no_address'];
              if($mode==='nodata_control')$answer=['ok'=>false,'rcode'=>0,'truncated'=>false,'answers'=>[],'reason'=>'no_address'];
              $udp=$answer;$tcp=$answer;
              if($mode==='tc'){$udp['ok']=false;$udp['truncated']=true;}
              if($mode==='tc_fail'){$udp['ok']=false;$udp['truncated']=true;$tcp['ok']=false;}
              $out[]=['name'=>$name,'type'=>$type,'udp'=>$udp,'tcp'=>$tcp];
            }
            return ['started'=>true,'syntax_ok'=>$mode!=='syntax','results'=>$out];
          }];
        if($input['mode']==='no_guard')unset($deps['candidate']);
        try{$v=(new AsusSmartDnsProbe(new AsusSmartDnsInstaller(),$deps))->validate($input['profile'],str_repeat('b',32));}
        catch(Throwable $e){$v=['error'=>$e->getMessage(),'checks'=>$e instanceof AsusSmartDnsValidationError?$e->checks:[]];}
        echo json_encode(['value'=>$v,'events'=>$events]);'''
        p = subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps({'profile':value or profile(),'mode':mode}),capture_output=True,text=True,timeout=8)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)

    def test_all_selected_servers_are_preserved_in_one_configuration_check(self):
        v=self.validate(profile(upstream(),upstream('special',default=False,domains=[dict(name='image.tmdb.org',include_subdomains=False)])))
        self.assertNotIn('error',v['value'])
        self.assertEqual(len(v['events']),1)
        event=v['events'][0]
        self.assertEqual(event['stage'],'profile')
        self.assertEqual(event['config'].count('server-tls '),2)
        self.assertIn('-exclude-default-group',event['config'])
        self.assertIn('image.tmdb.org',event['config'])
        self.assertEqual(v['value']['scope'],'configuration_only')
        self.assertEqual(v['value']['profile_hash'],v['events'][-1]['profile_hash'])
        self.assertEqual(v['value']['expires_uptime'],700)

    def test_external_no_address_does_not_reject_a_valid_configuration(self):
        p=profile(upstream(domains=[dict(name='githubusercontent.com',include_subdomains=True)]))
        v=self.validate(p,'nodata_control');self.assertNotIn('error',v['value'])
        self.assertFalse(v['value']['service_success_tested'])
        self.assertEqual(v['value']['profile_hash'],self.validate(p)['value']['profile_hash'])

    def test_nonanswering_server_remains_selected_and_tls_verification_stays_enabled(self):
        v=self.validate(profile(upstream(),upstream('wrong',tls_name='wrong.example')))
        self.assertNotIn('error',v['value'])
        self.assertIn('-tls-host-verify wrong.example',v['value']['config'])
        self.assertEqual(v['value']['config'].count('server-tls '),2)
        self.assertNotIn('no-check-certificate',v['value']['config'])
        self.assertNotIn('PRIVATE_ERROR_CANARY',json.dumps(v['value']))

    def test_network_failure_is_not_configuration_failure(self):
        v=self.validate(mode='tc')
        self.assertNotIn('error',v['value'])
        self.assertTrue(all(c['transport']=='tcp' for c in v['value']['checks']))
        self.assertNotIn('error',self.validate(mode='tc_fail')['value'])
        self.assertNotIn('error',self.validate(mode='fail')['value'])

    def test_busy_ports_never_issue_stop_or_kill(self):
        v=self.validate(mode='busy')
        self.assertEqual(v['value']['error'],'port_busy')
        self.assertEqual([e['port'] for e in v['events']],list(range(16053,16063)))
        self.assertTrue(all(set(e).isdisjoint({'stop','kill','pid'}) for e in v['events']))

    def test_global_budget_and_syntax_are_not_success(self):
        self.assertEqual(self.validate(mode='budget')['value']['error'],'timed_out')
        self.assertEqual(self.validate(mode='syntax')['value']['error'],'invalid_configuration')

    def test_resource_exhaustion_is_not_reported_as_bad_dns_or_binary(self):
        self.assertEqual(self.validate(mode='memory')['value']['error'],'insufficient_memory')

    def test_unmanaged_worker_cannot_run_candidates(self):
        self.assertEqual(self.validate(mode='no_guard')['value']['error'],'guard_unavailable')


if __name__=='__main__': unittest.main()
