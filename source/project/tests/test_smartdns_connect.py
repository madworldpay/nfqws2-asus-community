"""Forwarding may replace only the owned block and known upstream directives."""
import json
import subprocess
import unittest
import os
import tempfile
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC
from test_smartdns_profile import profile, upstream


class SmartDnsHookTests(unittest.TestCase):
    def call(self, operation, *args):
        code = '''$f=$argv[1].'/smartdns-connect.php';
        if(!is_file($f)){echo json_encode(['error'=>'missing_connection']);exit;}
        require $f;$v=json_decode(stream_get_contents(STDIN),true);
        try{echo json_encode(['value'=>AsusSmartDnsHook::{$v[0]}(...array_slice($v,1))]);}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps([operation,*args]),capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)

    def test_foreign_hook_text_and_no_trailing_newline_are_preserved(self):
        before='#!/bin/sh\nprintf "foreign\\n"'
        value=self.call('install',before)['value']
        self.assertTrue(value.startswith(before))
        self.assertEqual(self.call('remove',value),{'value':before})
        # New unrelated edits are retained instead of restoring an old snapshot.
        edited=value+'\nprintf "new foreign command\\n"\n'
        self.assertEqual(self.call('remove',edited),{'value':before+'\nprintf "new foreign command\\n"\n'})

    def test_changed_owned_block_is_a_conflict(self):
        value=self.call('install','#!/bin/sh\n')['value']
        changed=value.replace('postconf','CHANGED')
        self.assertEqual(self.call('remove',changed),{'error':'hook_conflict'})

    def test_foreign_early_exit_is_not_hidden_by_an_existing_owned_block(self):
        value=self.call('install','#!/bin/sh\n')['value']
        for edited in ['exit 0\n'+value,value+'\nif true; then exec another-service; fi\n']:
            with self.subTest(edited=edited):self.assertEqual(self.call('install',edited),{'error':'hook_conflict'})

    def test_generated_hook_must_also_fit_the_recovery_limit(self):
        self.assertEqual(self.call('install','#'+('x'*262143)),{'error':'hook_conflict'})

    def test_early_exit_exec_and_unknown_managed_markers_block_connect(self):
        for before in ['#!/bin/sh\nexit 0\n','#!/bin/sh\nexec another-service\n',
                       '# BEGIN NFQWS2 SMARTDNS MANAGED\nforeign\n',
                       'printf x\x00hidden']:
            with self.subTest(before=before):self.assertEqual(self.call('install',before),{'error':'hook_conflict'})

    def test_forwarding_preserves_dhcp_local_names_and_filters_default_sources(self):
        before='interface=br0\ndhcp-range=192.0.2.10,192.0.2.20\nlocal=/home/\naddn-hosts=/etc/hosts\nserver=9.9.9.9\nresolv-file=/tmp/resolv.conf\nservers-file=/tmp/resolv.dnsmasq\nall-servers\n'
        value=self.call('forwarding',before,{'/tmp/resolv.dnsmasq':'server=1.1.1.1\n'})['value']
        for line in ['interface=br0','dhcp-range=192.0.2.10,192.0.2.20','local=/home/','addn-hosts=/etc/hosts']:
            self.assertIn(line+'\n',value)
        self.assertIn('server=127.0.0.1#6054\n',value)
        self.assertEqual(value.count('no-resolv\n'),1)
        self.assertNotIn('resolv-file=',value);self.assertNotIn('servers-file=',value)
        self.assertNotIn('9.9.9.9',value);self.assertNotIn('all-servers',value)

    def test_no_resolv_does_not_hide_domains_in_servers_file(self):
        before='no-resolv\nservers-file=/tmp/resolv.dnsmasq\n'
        self.assertEqual(self.call('forwarding',before,{'/tmp/resolv.dnsmasq':'server=/example.org/9.9.9.9\n'}),{'error':'existing_dns_rules'})

    def test_unknown_include_unreadable_servers_file_or_domain_route_is_not_silently_lost(self):
        for before in ['conf-file=/jffs/custom.conf\n','conf-dir=/jffs/custom\n',
                       'servers-file=/tmp/resolv.dnsmasq\n','server=/corp.example/192.0.2.1\n']:
            with self.subTest(before=before):self.assertEqual(self.call('forwarding',before,{}),{'error':'existing_dns_rules'})

    def test_local_names_are_preserved_but_cannot_shadow_selected_profile_domains(self):
        selected=profile(upstream(domains=[{'name':'video.example.com','include_subdomains':False}]))
        for config,want in [('local=/lan/\n',True),('address=/example.com/192.0.2.1\n',False),
                            ('address=/child.video.example.com/192.0.2.1\n',True),
                            ('host-record=video.example.com,192.0.2.1\n',False),
                            ('cname=video.example.com,router.lan\n',False),('address=/#/192.0.2.1\n',False)]:
            with self.subTest(config=config):self.assertEqual(self.call('profileRouting',config,selected),{'value':want})
        selected['upstreams'][0]['domains'][0]['include_subdomains']=True
        self.assertEqual(self.call('profileRouting','address=/child.video.example.com/192.0.2.1\n',selected),{'value':False})


    def test_merlin_service_names_do_not_block_unrelated_profile(self):
        selected=profile(upstream(domains=[{'name':'video.example.com','include_subdomains':True}]))
        config='address=/use-application-dns.net/\naddress=/_dns.resolver.arpa/\naddress=/mask.icloud.com/mask-h2.icloud.com/\nlocal=/GT-BE19000AI/\nlocal=/2.0.192.in-addr.arpa/\n'
        self.assertEqual(self.call('profileRouting',config,selected),{'value':True})
        self.assertIn('address=/_dns.resolver.arpa/',self.call('forwarding',config,{})['value'])

    def test_service_names_still_conflict_with_selected_parent_and_bad_names_fail(self):
        selected=profile(upstream(domains=[{'name':'resolver.arpa','include_subdomains':True}]))
        self.assertEqual(self.call('profileRouting','address=/_dns.resolver.arpa/\n',selected),{'value':False})
        for config in ['address=/bad..example.com/\n','local=/bad name/\n','address=/#/192.0.2.1\n']:
            self.assertEqual(self.call('profileRouting',config,selected),{'value':False})


class SmartDnsConnectionTests(unittest.TestCase):
    def scenario(self, mode='ready', action='confirm'):
        code=r'''require $argv[1].'/smartdns-connect.php';
        if(!class_exists('AsusSmartDnsConnection')){echo json_encode(['error'=>'missing_transaction']);exit;}
        $in=json_decode(stream_get_contents(STDIN),true);$time=100.0;$events=[];$reads=0;$journalReader=null;
        $store=new AsusSmartDnsStore($argv[2],(int)$argv[3],['boot'=>fn()=>'boot-a','uptime'=>function()use(&$time){return $time;}]);
        $hash=$store->saveDraft($in['profile']);$base=str_repeat('a',64);$id=str_repeat('b',32);$preview=str_repeat('1',32);
        $store->savePreview(['id'=>$preview,'profile_hash'=>$hash,'baseline_hash'=>$base,'expires_uptime'=>700]);
        $deps=['uptime'=>function()use(&$time){return $time;},
          'baseline'=>function()use(&$reads,$base,$in){$reads++;return ['hash'=>$in['mode']==='changed_baseline'&&$reads>1?str_repeat('c',64):$base,'snapshot'=>['hook'=>'foreign'],'conflicts'=>[]];},
          'prepare'=>function($job,$snapshot)use(&$events){$events[]='prepare';},
          'guard'=>function($job,$profile)use(&$events,$in,$argv,&$journalReader){$events[]='guard';if($in['mode']==='guard_fails')throw new RuntimeException('guard_unavailable');
            if($in['mode']==='journal_reader_after_guard'){
              $ready=$argv[2].'/reader-ready';
              $journalReader=proc_open(['/usr/bin/flock','-s',$argv[2].'/state.lock','/bin/sh','-c','printf ready > "$1"; sleep 0.25','reader',$ready],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$unused);
              if(!is_resource($journalReader))throw new RuntimeException('reader_launch_failed');
              for($n=0;$n<100&&!is_file($ready);$n++)usleep(10000);
              if(!is_file($ready))throw new RuntimeException('reader_not_ready');
            }
            return ['guard_identity'=>['pid'=>21],'identity'=>['pid'=>22]];},
          'forward'=>function($job)use(&$events,&$time,$in){$events[]='forward';if($in['mode']==='forward_fails')throw new RuntimeException('dns_restart_failed');return ['deadline_uptime'=>$time+120];},
          'dns'=>function()use(&$events,$in){$events[]='dns';return $in['mode']!=='dns_fails';},
          'confirm'=>function($job)use(&$events){$events[]='confirm';return true;},
          'restore'=>function($job,$snapshot)use(&$events,$in){$events[]='restore';return $in['mode']!=='restore_conflict';},
          'stop'=>function($job)use(&$events){$events[]='stop';return true;},
          'release'=>function($job)use(&$events){$events[]='release';}];
        if($in['mode']==='no_guard')unset($deps['guard']);
        $connection=new AsusSmartDnsConnection($store,$deps);$out=[];
        try{$out[]=$connection->apply($id,$in['mode']==='bad_preview'?str_repeat('2',32):$preview,$hash,$base);}catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}
        if($in['mode']==='stale_confirm')$time=221;
        if($in['mode']==='edit_draft'){$p=$in['profile'];$p['upstreams'][0]['label']='edited after apply';$store->saveDraft($p);}
        if(($out[0]['state']??null)==='awaiting_confirmation'){
          try{if($in['action']==='confirm')$out[]=$connection->confirm($id);elseif($in['action']==='rollback')$out[]=$connection->rollback($id);}
          catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}
        }
        if($in['mode']==='replay'){
          $time=1000;try{$out[]=$connection->apply($id,$preview,$hash,$base);}catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}
          try{$out[]=$connection->confirm($id);}catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}
        }
        if($in['mode']==='history_replay'){
          $other=str_repeat('c',32);
          $connection->apply($other,$preview,$hash,$base);$connection->rollback($other);
          try{$out[]=$connection->apply($id,$preview,$hash,$base);}catch(Throwable $e){$out[]=['error'=>$e->getMessage()];}
        }
        if(is_resource($journalReader))proc_close($journalReader);
        echo json_encode(['results'=>$out,'events'=>$events,'status'=>$connection->status(),'active'=>$store->active()]);'''
        with tempfile.TemporaryDirectory() as d:
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(Path(d)/'state'),str(os.getuid())],
                             input=json.dumps({'mode':mode,'action':action,'profile':profile()}),capture_output=True,text=True,timeout=8)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)

    def test_guard_handshake_precedes_forwarding_and_confirmation_is_explicit(self):
        value=self.scenario(action='none')
        self.assertNotIn('error',value)
        self.assertEqual(value['status']['state'],'awaiting_confirmation')
        self.assertLess(value['events'].index('guard'),value['events'].index('forward'))
        self.assertNotIn('confirm',value['events']);self.assertIsNone(value['active'])
        self.assertEqual(value['status']['deadline_remaining_s'],120)

    def test_polling_reader_after_guard_does_not_abort_or_replay_connection(self):
        value=self.scenario('journal_reader_after_guard')
        self.assertEqual([item.get('state') for item in value['results']],['awaiting_confirmation','confirmed'],value)
        self.assertEqual(value['status']['state'],'confirmed')
        for operation in ['prepare','guard','forward','confirm']:
            self.assertEqual(value['events'].count(operation),1,value)
        self.assertNotIn('restore',value['events'])

    def test_missing_or_failed_guard_never_changes_forwarding(self):
        for mode in ['no_guard','guard_fails']:
            with self.subTest(mode=mode):
                value=self.scenario(mode)
                self.assertNotIn('error',value)
                self.assertNotIn('forward',value['events']);self.assertNotEqual(value['status']['state'],'confirmed')

    def test_changed_baseline_or_unseen_preview_is_rejected_before_forwarding(self):
        for mode in ['changed_baseline','bad_preview']:
            with self.subTest(mode=mode):
                value=self.scenario(mode)
                self.assertNotIn('error',value)
                self.assertNotIn('forward',value['events']);self.assertNotEqual(value['status']['state'],'confirmed')

    def test_rollback_verifies_restore_before_stopping_the_candidate(self):
        value=self.scenario(action='rollback')
        self.assertNotIn('error',value)
        self.assertEqual(value['status']['state'],'rolled_back')
        self.assertLess(value['events'].index('restore'),value['events'].index('stop'))
        self.assertIsNone(value['active'])

    def test_restore_conflict_keeps_candidate_and_unresolved_state(self):
        value=self.scenario('restore_conflict','rollback')
        self.assertNotIn('error',value)
        self.assertEqual(value['status']['state'],'conflict')
        self.assertNotIn('stop',value['events']);self.assertNotIn('release',value['events'])

    def test_expired_confirmation_rolls_back_instead_of_confirming(self):
        value=self.scenario('stale_confirm')
        self.assertNotIn('error',value)
        self.assertEqual(value['status']['state'],'rolled_back')
        self.assertNotIn('confirm',value['events'])

    def test_confirm_activates_the_viewed_copy_even_after_new_draft(self):
        value=self.scenario('edit_draft')
        self.assertNotIn('error',value)
        self.assertEqual(value['status']['state'],'confirmed')
        self.assertEqual(value['active']['profile'],profile())

    def test_lost_responses_do_not_repeat_apply_or_confirm(self):
        value=self.scenario('replay')
        self.assertNotIn('error',value)
        self.assertEqual(value['status']['state'],'confirmed')
        self.assertEqual(value['events'].count('forward'),1);self.assertEqual(value['events'].count('confirm'),1)

    def test_late_replay_after_a_different_finished_job_returns_its_receipt(self):
        value=self.scenario('history_replay','rollback')
        self.assertNotIn('error',value)
        self.assertNotIn('error',value['results'][-1])
        self.assertEqual(value['results'][-1]['state'],'rolled_back')
        self.assertEqual(value['results'][-1]['request_id'],'b'*32)
        self.assertEqual(value['status']['request_id'],'c'*32)
        self.assertEqual(value['events'].count('prepare'),2)


if __name__=='__main__':unittest.main()
