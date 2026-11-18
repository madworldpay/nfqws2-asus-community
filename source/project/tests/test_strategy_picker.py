import json, os, subprocess, tempfile, unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC

class PickerTests(unittest.TestCase):
    def php(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            code="umask(0077);require $argv[1].'/strategy-picker-core.php';"+body
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),tmp,str(os.getuid())],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)

    def test_service_actuator_lock_wait_hint_is_explicit_and_other_children_do_not_inherit_it(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$s->write(['id'=>str_repeat('a',32),'state'=>'running','phase'=>'warming']);$runtime=new NfqwsStrategyPickerRuntime($s);$m=new ReflectionMethod($runtime,'actuator');$out=[];foreach([false,true,false]as $wait){$out[]=$m->invoke($runtime,['/bin/sh','-c','printf %s \"${NFQWS_CORE_LOCK_WAIT-unset}\"'],2,null,null,$wait);}echo json_encode(['children'=>$out,'actuator'=>$s->read()['actuator']??null,'intent'=>$s->read()['actuator_intent']??null]);""")
        self.assertEqual(r,{'children':[{'status':0,'output':'unset'},{'status':0,'output':'1'},{'status':0,'output':'unset'}],
                            'actuator':None,'intent':None})

    def test_all_four_service_combinations_include_the_fixed_tracker_goal(self):
        r=self.php("""$services=['youtube','discord','instagram','torrents'];$out=[];for($mask=1;$mask<16;$mask++){$parts=[];foreach($services as $i=>$service)if($mask&(1<<$i))$parts[]=$service;try{$out[]=NfqwsStrategyPickerGoals::parse(implode(',',array_reverse($parts)));}catch(RuntimeException $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        services=['youtube','discord','instagram','torrents']
        self.assertEqual(r,[','.join(s for i,s in enumerate(services)if mask&(1<<i))for mask in range(1,16)])

    def test_target_union_prioritizes_selected_services_and_keeps_all_stock_controls(self):
        r=self.php("""$stock=['www.youtube.com','nnmclub.to','x.com/i/api/1.1/graphql/user_flow.json'];$out=[];foreach(['youtube','youtube,discord','torrents','all']as $goal){try{$out[]=NfqwsStrategyPickerGoals::probeDomains($stock,$goal);}catch(Throwable $e){$out[]='missing_target_union';}}echo json_encode($out);""")
        stock=['www.youtube.com','nnmclub.to','x.com/i/api/1.1/graphql/user_flow.json']
        youtube=['youtube.com','www.youtube.com']
        discord=['discord.com','gateway.discord.gg','media.discordapp.net']
        instagram=['instagram.com','www.instagram.com']
        trackers=['nnmclub.to','rutracker.org','rutor.info','tapochek.net']
        for actual,priority in zip(r,[youtube,youtube+discord,trackers,youtube+discord+instagram+trackers]):
            self.assertEqual(actual,list(dict.fromkeys(priority+stock)))

    def test_selected_tracker_goal_requires_all_fixed_site_rows(self):
        r=self.php("""$make=function($candidate){$rows=[];foreach(['www.youtube.com','rutor.info']as $host)$rows[]=['domain'=>$host,'http'=>'ok','tls12'=>!$candidate&&$host==='rutor.info'?'timeout':'ok','tls13'=>'ok','quic'=>'unsupported'];return NfqwsStrategyPickerScore::measure(['state'=>'completed','coverage'=>['domains'=>2,'tcp'=>1],'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>$rows]]],['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'a','status'=>'ok']]]]]]]);};try{$a=$make(false);$c=$make(true);$out=NfqwsStrategyPickerScore::compare([$a,$a],[$c,$c],'torrents');}catch(RuntimeException $e){$out=['reason'=>$e->getMessage()];}echo json_encode($out);""")
        self.assertEqual(r,{'eligible':False,'reason':'incomparable_result','gain':0})

    def test_tracker_goal_ranks_its_sites_instead_of_unrelated_tcp_success(self):
        r=self.php("""$make=function($tracker,$tcp){$rows=[];foreach(['www.youtube.com','nnmclub.to','rutracker.org','rutor.info','tapochek.net']as $host)$rows[]=['domain'=>$host,'http'=>'ok','tls12'=>!$tracker&&$host==='rutor.info'?'timeout':'ok','tls13'=>'ok','quic'=>'unsupported'];return NfqwsStrategyPickerScore::measure(['state'=>'completed','coverage'=>['domains'=>5,'tcp'=>2],'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>$rows]]],['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'a','status'=>'ok'],['id'=>'b','status'=>$tcp?'ok':'timeout']]]]]]]);};try{$a=$make(false,false);$unrelated=$make(false,true);$targeted=$make(true,false);$out=[NfqwsStrategyPickerScore::compare([$a,$a],[$unrelated,$unrelated],'torrents'),NfqwsStrategyPickerScore::compare([$a,$a],[$targeted,$targeted],'torrents')];}catch(RuntimeException $e){$out=['reason'=>$e->getMessage()];}echo json_encode($out);""")
        self.assertIsInstance(r,list)
        self.assertEqual(r[0]['reason'],'goal_no_improvement')
        self.assertFalse(r[0]['eligible']);self.assertTrue(r[1]['eligible'])
        self.assertEqual(r[1]['selected']['torrents']['tls12'],{'ok':4,'total':4})

    def test_missing_nnm_or_rutracker_cannot_make_the_required_tracker_goal_win(self):
        r=self.php("""$out=[];foreach(['nnmclub.to','rutracker.org']as $missing){$make=function($candidate)use($missing){$rows=[];foreach(['www.youtube.com','nnmclub.to','rutracker.org','rutor.info','tapochek.net']as $host)if($host!==$missing)$rows[]=['domain'=>$host,'http'=>'ok','tls12'=>!$candidate&&$host==='rutor.info'?'timeout':'ok','tls13'=>'ok','quic'=>'unsupported'];return NfqwsStrategyPickerScore::measure(['state'=>'completed','coverage'=>['domains'=>4,'tcp'=>1],'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>$rows]]],['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'a','status'=>'ok']]]]]]]);};$a=$make(false);$c=$make(true);$out[$missing]=NfqwsStrategyPickerScore::compare([$a,$a],[$c,$c],'torrents');}echo json_encode($out);""")
        for host in ['nnmclub.to','rutracker.org']:
            self.assertEqual(r[host],{'eligible':False,'reason':'incomparable_result','gain':0})

    def test_domain_budget_covers_the_added_tracker_controls(self):
        r=self.php("""$b=NfqwsStrategyPickerBudget::choose(2,70000,0);try{echo json_encode(NfqwsStrategyPickerBudget::coverDomains($b,38));}catch(Throwable $e){echo json_encode(['missing_domain_budget'=>true]);}""")
        self.assertEqual(r.get('group_seconds'),364)
        self.assertEqual(r.get('probe_seconds'),758)
        self.assertEqual(r.get('domain_count'),38)

    def test_fast_child_exit_is_collected_without_losing_real_failure_codes(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$m=new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'closeProcess');$out=[];foreach([0,7]as $code){$pipes=[];$p=proc_open(['/bin/sh','-c','sleep 0.05; exit '.$code],[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes);$s=proc_get_status($p);foreach($pipes as $f)fclose($f);$out[]=$m->invoke(null,$p,$s['exitcode']);}$pipes=[];$p=proc_open(['/bin/true'],[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes);usleep(100000);$s=proc_get_status($p);foreach($pipes as $f)fclose($f);$out[]=$m->invoke(null,$p,$s['exitcode']);echo json_encode($out);""")
        self.assertEqual(r,[0,7,0])

    def test_finished_child_diagnostics_are_drained_with_a_fixed_output_limit(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$read=new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'readPipes');$close=new ReflectionMethod(NfqwsStrategyPickerRuntime::class,'closeProcess');$out=[];foreach(['',str_repeat('x',65535)]as $prefix){$pipes=[];$p=proc_open(['/bin/sh','-c','printf stdout; printf stderr >&2; exit 7'],[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes);usleep(100000);$s=proc_get_status($p);foreach($pipes as $f)stream_set_blocking($f,false);$raw=$read->invoke(null,$pipes,$prefix);foreach($pipes as $f)fclose($f);$out[]=['status'=>$close->invoke(null,$p,$s['exitcode']),'bytes'=>strlen($raw),'tail'=>substr($raw,strlen($prefix))];}echo json_encode($out);""")
        self.assertEqual(r,[{'status':7,'bytes':12,'tail':'stdoutstderr'},
                            {'status':7,'bytes':65537,'tail':'st'}])

    def test_protocol_counts_preserve_denominators_and_youtube(self):
        r=self.php("""$d=['state'=>'completed','coverage'=>['domains'=>2,'tcp'=>2],'groups'=>[
        ['group'=>2,'document'=>['results'=>['domain_inspection'=>[
        ['domain'=>'youtube.com','http'=>'ok','tls12'=>'ok','tls13'=>'tls_dropped','quic'=>'timeout'],
        ['domain'=>'example.com','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'unsupported']]]]],
        ['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'a','status'=>'ok'],['id'=>'b','status'=>'timeout']]]]]]];
        echo json_encode(NfqwsStrategyPickerScore::measure($d));""")
        self.assertEqual(r['metrics']['tcp'],{'ok':1,'total':2})
        self.assertEqual(r['metrics']['tls13'],{'ok':1,'total':2})
        self.assertEqual(r['metrics']['quic'],{'ok':0,'total':1})
        self.assertEqual(r['youtube'],{'http':True,'tls12':True,'tls13':False,'quic':False})

    def test_partial_or_changed_context_cannot_rank(self):
        r=self.php("""$r=[];foreach([['state'=>'partial'],['state'=>'completed','context'=>['changed'=>true]]] as $d){try{NfqwsStrategyPickerScore::measure($d);$r[]=false;}catch(Throwable $e){$r[]=$e->getMessage();}}echo json_encode($r);""")
        self.assertEqual(r,['incomparable_result','incomparable_result'])

    def test_youtube_or_tls_regression_cannot_win_by_total(self):
        r=self.php("""$m=['tcp'=>['ok'=>60,'total'=>110],'http'=>['ok'=>25,'total'=>35],'tls12'=>['ok'=>25,'total'=>35],'tls13'=>['ok'=>25,'total'=>35],'quic'=>['ok'=>10,'total'=>21]];
        $a=['metrics'=>$m,'targets'=>'abc','youtube'=>['http'=>true,'tls12'=>true,'tls13'=>true,'quic'=>true]];
        $b=$a;$b['metrics']['tcp']['ok']=110;$b['youtube']['quic']=false;
        $c=$a;$c['metrics']['tcp']['ok']=110;$c['metrics']['tls13']['ok']=24;
        echo json_encode([NfqwsStrategyPickerScore::compare([$a,$a],[$b,$b]),NfqwsStrategyPickerScore::compare([$a,$a],[$c,$c])]);""")
        self.assertEqual([x['eligible'] for x in r],[False,False])
        self.assertEqual([x['reason'] for x in r],['youtube_regression','tls_regression'])

    def test_repeat_worst_case_and_target_mismatch(self):
        r=self.php("""$a=['metrics'=>array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>2,'total'=>5]),'targets'=>'abc','youtube'=>['http'=>true,'tls12'=>true,'tls13'=>true,'quic'=>true]];
        $b=$a;$b['metrics']['tcp']['ok']=4;$c=$a;$c['metrics']['tcp']['ok']=3;
        $d=$b;$d['targets']='different';echo json_encode([NfqwsStrategyPickerScore::compare([$a,$a],[$b,$c]),NfqwsStrategyPickerScore::compare([$a,$a],[$b,$d])]);""")
        self.assertTrue(r[0]['eligible']);self.assertEqual(r[0]['gain'],1)
        self.assertEqual(r[1]['reason'],'incomparable_result')

    def test_journal_restores_only_owned_config_and_keeps_exact_bytes(self):
        r=self.php("""$root=$argv[2];$file=$root.'/nfqws2.conf';file_put_contents($file,"# original\nA=1\n");chmod($file,0600);
        $s=new NfqwsStrategyPickerState($root.'/picker',(int)$argv[3]);$t=new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]);
        $t->snapshot(false);$t->replace("# candidate\nA=2\n");$t->restore();echo json_encode([file_get_contents($file),$s->read()['running_before']]);""")
        self.assertEqual(r,['# original\nA=1\n',False])

    def test_foreign_change_is_not_overwritten(self):
        r=self.php("""$file=$argv[2].'/nfqws2.conf';file_put_contents($file,'before');chmod($file,0600);$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$t=new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]);$t->snapshot(true);$t->replace('candidate');file_put_contents($file,'foreign');try{$t->restore();}catch(Throwable $e){$error=$e->getMessage();}echo json_encode([$error,file_get_contents($file)]);""")
        self.assertEqual(r,['source_changed','foreign'])

    def test_intent_written_before_config_switch_can_recover_after_crash(self):
        r=self.php("""$file=$argv[2].'/nfqws2.conf';file_put_contents($file,'before');chmod($file,0600);$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$t=new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]);$t->snapshot(true);$j=$s->read();unset($j['config_binding_version'],$j['config_binding']);$j['known'][]=hash('sha256','candidate');$s->write($j);file_put_contents($file,'candidate');$t->restore();echo json_encode(file_get_contents($file));""")
        self.assertEqual(r,'before')

    def test_stale_apply_cannot_replace_edited_original(self):
        r=self.php("""$file=$argv[2].'/nfqws2.conf';file_put_contents($file,'before');chmod($file,0600);$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$t=new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]);$t->snapshot(true);file_put_contents($file,'user edited');try{$t->replace('candidate');}catch(Throwable $e){$error=$e->getMessage();}echo json_encode([$error,file_get_contents($file)]);""")
        self.assertEqual(r,['source_changed','user edited'])

    def test_runtime_request_rejects_paths_extra_fields_and_stale_ids(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$out=[];foreach([
        ['cmd'=>'pickerstart','csrf_token'=>'x','request_id'=>str_repeat('a',32),'consent'=>'test'],
        ['cmd'=>'pickerstart','csrf_token'=>'x','request_id'=>'../../foreign','consent'=>'test'],
        ['cmd'=>'pickerapply','csrf_token'=>'x','id'=>str_repeat('a',32),'path'=>'/etc/shadow'],
        ['cmd'=>'pickerstart','csrf_token'=>'x','request_id'=>str_repeat('a',32),'consent'=>'no']
        ]as $p){try{NfqwsStrategyPickerRuntime::validateRequest($p);$out[]='ok';}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,['ok','invalid_request','invalid_request','consent_required'])

    def test_actor_requires_matching_boot_ticks_and_full_argv(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$a=NfqwsStrategyPickerRuntime::identity(getmypid());$valid=NfqwsStrategyPickerRuntime::sameActor($a);$a['ticks']='foreign';echo json_encode([$valid,NfqwsStrategyPickerRuntime::sameActor($a)]);""")
        self.assertEqual(r,[True,False])

    def test_hardware_budget_reduces_work_on_low_memory_or_busy_cpu(self):
        r=self.php("""echo json_encode([NfqwsStrategyPickerBudget::choose(1,48000,0.2),NfqwsStrategyPickerBudget::choose(4,300000,0.5),NfqwsStrategyPickerBudget::choose(4,300000,7.0)]);""")
        self.assertLess(r[0]['concurrency'],r[1]['concurrency'])
        self.assertLess(r[2]['concurrency'],r[1]['concurrency'])
        self.assertLess(r[0]['max_profiles'],r[1]['max_profiles'])

    def test_expanded_recipes_change_only_reviewed_numeric_operands(self):
        r=self.php("""$raw=['NFQWS_ARGS'=>'--lua-desync=fake:repeats=4 --lua-desync=multisplit:pos=1,midsld','NFQWS_ARGS_QUIC'=>'','NFQWS_ARGS_CUSTOM'=>'','NFQWS_ARGS_UDP'=>''];echo json_encode(NfqwsStrategyPickerRecipes::expand($raw,4));""")
        self.assertGreaterEqual(len(r),1)
        for row in r:
            self.assertNotIn('repeats=6',row['config']['NFQWS_ARGS'])
            self.assertNotIn('repeats=8',row['config']['NFQWS_ARGS'])
            self.assertNotIn('--lua-init=',row['config']['NFQWS_ARGS'])

    def test_retained_resource_export_preserves_originals_and_checks_frozen_bytes(self):
        r=self.php("""$root=$argv[2];foreach(['source','target']as $x){mkdir($root.'/'.$x);foreach(['lists','lua','blobs']as $k)mkdir($root.'/'.$x.'/'.$k);}
        file_put_contents($root.'/source/lists/user.list','new');file_put_contents($root.'/target/lists/user.list','original');
        $e=['config'=>['NFQWS_ARGS'=>'--hostlist='.$root.'/source/lists/user.list'],'files'=>['lists/user.list'=>hash('sha256','new')],'mutable_files'=>[]];
        $c=NfqwsStrategyPickerResources::retain($e,$root.'/source',$root.'/target',(int)$argv[3]);
        $new=substr($c['NFQWS_ARGS'],strlen('--hostlist='));$out=[file_get_contents($root.'/target/lists/user.list'),file_get_contents($new),str_contains($new,'picker-')];
        file_put_contents($root.'/source/lists/user.list','changed');try{NfqwsStrategyPickerResources::retain($e,$root.'/source',$root.'/target',(int)$argv[3]);}catch(Throwable $e){$out[]=$e->getMessage();}echo json_encode($out);""")
        self.assertEqual(r,['original','new',True,'source_changed'])

    def test_mode_uses_resolved_extra_args_not_nonexistent_mode_setting(self):
        r=self.php("""$s='MODE_AUTO="--hostlist-auto=/opt/etc/nfqws2/lists/auto.list"'."\n".'MODE_LIST="--hostlist=/opt/etc/nfqws2/lists/user.list"'."\n".'MODE_ALL="--hostlist-exclude=/opt/etc/nfqws2/lists/exclude.list"'."\n";
        $r=[];foreach(['AUTO','LIST','ALL']as $mode)$r[]=NfqwsStrategyPickerMode::read($s.'NFQWS_EXTRA_ARGS="$MODE_'.$mode.'"'."\n");echo json_encode($r);""")
        self.assertEqual(r,['auto','list','all'])

    def test_resource_alias_rebinds_physical_paths_to_normal_managed_paths(self):
        r=self.php("""$root=$argv[2];mkdir($root.'/source');mkdir($root.'/source/lists');mkdir($root.'/target');mkdir($root.'/target/lists');symlink($root.'/source',$root.'/alias');file_put_contents($root.'/source/lists/a.list','x');
        $e=['config'=>['NFQWS_ARGS'=>'--hostlist='.$root.'/source/lists/a.list'],'files'=>['lists/a.list'=>hash('sha256','x')],'mutable_files'=>[]];$out=NfqwsStrategyPickerResources::retain($e,$root.'/alias',$root.'/target',(int)$argv[3]);echo json_encode($out['NFQWS_ARGS']);""")
        self.assertIn('/target/',r);self.assertNotIn('/source/',r);self.assertNotIn('/alias/',r)

    def test_cancellation_marker_is_bound_to_the_requested_job(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$a=str_repeat('a',32);$b=str_repeat('b',32);$s->write(['id'=>$a,'state'=>'running','profiles'=>[]]);$r=new NfqwsStrategyPickerRuntime($s);$r->cancel($a);$s->write(['id'=>$b,'state'=>'running','profiles'=>[]]);echo json_encode([file_exists($argv[2].'/picker/cancel-'.$a),file_exists($argv[2].'/picker/cancel-'.$b)]);""")
        self.assertEqual(r,[True,False])

    def test_stale_worker_cannot_recover_a_new_job(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$file=$argv[2].'/nfqws2.conf';file_put_contents($file,'before');$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$c=new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]);$j=$c->snapshot(false);$j['id']=str_repeat('b',32);$s->write($j);$c->replace('candidate');$r=new NfqwsStrategyPickerRuntime($s,$c);$r->work(str_repeat('a',32));echo json_encode([$s->read()['state'],file_get_contents($file)]);""")
        self.assertEqual(r,['preparing','candidate'])

    def test_resource_fingerprint_ignores_auto_but_detects_custom_lua_edits(self):
        r=self.php("""$a=['files'=>[['kind'=>'lists','name'=>'auto.list','sha256'=>'a','state'=>'available'],['kind'=>'lua','name'=>'custom.lua','sha256'=>'b','state'=>'available']]];
        $b=$a;$b['files'][0]['sha256']='learned';$c=$a;$c['files'][1]['sha256']='edited';
        echo json_encode([NfqwsStrategyPickerResources::fingerprint($a,['lists/auto.list'])===NfqwsStrategyPickerResources::fingerprint($b,['lists/auto.list']),NfqwsStrategyPickerResources::fingerprint($a,['lists/auto.list'])===NfqwsStrategyPickerResources::fingerprint($c,['lists/auto.list'])]);""")
        self.assertEqual(r,[True,False])

    def test_runtime_bootstrap_can_enter_the_shared_import_writer(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$root=$argv[2];$uid=(int)$argv[3];$tx=new AsusImportTransaction(new AsusImportStore($root.'/import',$uid),new AsusSmartDnsStore($root.'/dns',$uid),$root,$root.'/nfqws2.conf',$uid);$tx->writer(function()use($root){file_put_contents($root.'/marker','protected');});echo json_encode(file_get_contents($root.'/marker'));""")
        self.assertEqual(r,'protected')

    def test_cleanup_directory_guard_accepts_owned_folder_and_rejects_symlink(self):
        r=self.php("""$root=$argv[2];mkdir($root.'/owned');symlink($root.'/owned',$root.'/alias');$uid=(int)$argv[3];$out=[NfqwsStrategyPickerResources::directory($root.'/owned',$uid)];try{NfqwsStrategyPickerResources::directory($root.'/alias',$uid);}catch(Throwable $e){$out[]=$e->getMessage();}echo json_encode([basename($out[0]),$out[1]]);""")
        self.assertEqual(r,['owned','unsafe_panel_file'])

    def test_boot_recovery_restores_bytes_and_respects_former_off_state(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$file=$argv[2].'/nfqws2.conf';file_put_contents($file,"# original\\n");$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$c=new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]);$j=$c->snapshot(false);$c->replace('temporary');$j=$s->read();$j['boot']='previous-boot';$j['state']='running';$s->write($j);$runtime=new NfqwsStrategyPickerRuntime($s,$c);echo json_encode([$runtime->recoverBoot(),file_get_contents($file),$s->read()['state'],$s->read()['restored']]);""")
        self.assertEqual(r,[False,'# original\n','interrupted',True])

    def test_boot_recovery_never_overwrites_foreign_configuration(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$file=$argv[2].'/nfqws2.conf';file_put_contents($file,'original');$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$c=new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]);$j=$c->snapshot(true);$j['boot']='previous-boot';$j['state']='running';$s->write($j);file_put_contents($file,'external edit');try{(new NfqwsStrategyPickerRuntime($s,$c))->recoverBoot();}catch(Throwable $e){$error=$e->getMessage();}echo json_encode([$error,file_get_contents($file)]);""")
        self.assertEqual(r,['source_changed','external edit'])

    def test_boot_retries_verified_recovery_required_after_reboot(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$file=$argv[2].'/nfqws2.conf';file_put_contents($file,'original');$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$c=new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]);$c->snapshot(false);$c->replace('temporary');$j=$s->read();$j['boot']='previous-boot';$j['state']='recovery_required';$s->write($j);$allow=(new NfqwsStrategyPickerRuntime($s,$c))->recoverBoot();echo json_encode([$allow,file_get_contents($file),$s->read()['restored']]);""")
        self.assertEqual(r,[False,'original',True])

    def test_unresolved_recovery_in_current_boot_blocks_service_start(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$file=$argv[2].'/nfqws2.conf';file_put_contents($file,'original');$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$c=new NfqwsStrategyPickerConfig($s,$file,(int)$argv[3]);$j=$c->snapshot(false);$j['state']='recovery_required';$s->write($j);try{(new NfqwsStrategyPickerRuntime($s,$c))->recoverBoot();$out='allowed';}catch(Throwable $e){$out=$e->getMessage();}echo json_encode($out);""")
        self.assertEqual(r,'recovery_required')

    def test_probe_exec_cannot_inherit_engine_or_shared_writer_lock(self):
        r=self.php("""require $argv[1].'/import-store.php';$root=$argv[2];$uid=(int)$argv[3];$store=new NfqwsStrategyPickerState($root.'/picker',$uid);$lock=$store->lock();$imports=new AsusImportStore($root.'/imports',$uid);$out=$imports->locked(function(){ $pipes=[];$p=proc_open(['/bin/sh','-c','ls -l /proc/self/fd'],[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['file','/dev/null','w']],$pipes);$s=stream_get_contents($pipes[1]);fclose($pipes[1]);proc_close($p);return $s;});echo json_encode([str_contains($out,'engine.lock'),str_contains($out,'writer.lock')]);flock($lock,LOCK_UN);fclose($lock);""")
        self.assertEqual(r,[False,False])

    def test_completed_but_truncated_or_duplicate_results_cannot_rank(self):
        r=self.php("""$row=['domain'=>'youtube.com','http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'ok'];$tcp=['id'=>'a','status'=>'ok'];$d=['state'=>'completed','coverage'=>['domains'=>2,'tcp'=>2],'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>[$row]]]],['group'=>3,'document'=>['results'=>['tcp16'=>[$tcp]]]]]];$out=[];foreach([false,true]as $duplicate){if($duplicate){$d['groups'][0]['document']['results']['domain_inspection'][]=$row;$d['groups'][1]['document']['results']['tcp16'][]=$tcp;}try{NfqwsStrategyPickerScore::measure($d);$out[]='accepted';}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,['incomparable_result','incomparable_result'])

    def test_extended_recipes_isolate_tcp_quic_and_preserve_custom_rules(self):
        r=self.php("""$c=['NFQWS_ARGS'=>'--lua-desync=fake:blob=tls:repeats=6','NFQWS_ARGS_QUIC'=>'--lua-desync=fake:blob=quic:repeats=11','NFQWS_ARGS_CUSTOM'=>'--lua-desync=fake:repeats=9','NFQWS_ARGS_UDP'=>'--lua-desync=fake:repeats=8'];echo json_encode(NfqwsStrategyPickerRecipes::expand($c,4));""")
        pairs=[]
        for row in r:
            c=row['config'];self.assertEqual(c['NFQWS_ARGS_CUSTOM'],'--lua-desync=fake:repeats=9');self.assertEqual(c['NFQWS_ARGS_UDP'],'--lua-desync=fake:repeats=8')
            pairs.append((c['NFQWS_ARGS']!='--lua-desync=fake:blob=tls:repeats=6',c['NFQWS_ARGS_QUIC']!='--lua-desync=fake:blob=quic:repeats=11'))
        self.assertIn((True,False),pairs);self.assertIn((False,True),pairs);self.assertIn((True,True),pairs)

    def test_low_concurrency_gets_time_for_full_protocol_coverage(self):
        r=self.php("""echo json_encode([NfqwsStrategyPickerBudget::choose(1,48000,0.1),NfqwsStrategyPickerBudget::choose(4,300000,0.1)]);""")
        self.assertGreater(r[0]['group_seconds'],r[1]['group_seconds'])
        for b in r:
            self.assertGreaterEqual(b['group_seconds'],35*4*8/b['concurrency'])
            self.assertGreaterEqual(b['probe_seconds'],2*b['group_seconds'])
            self.assertLessEqual(b['probe_seconds'],1800)

    def test_guard_diagnostics_do_not_erase_last_worker_memory(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$id=str_repeat('a',32);$s->write(['id'=>$id,'state'=>'running','phase'=>'warming']);$s->write(['id'=>$id,'identity'=>['pid'=>getmypid()]],'actor-work.json');$r=new NfqwsStrategyPickerRuntime($s);$phase=new ReflectionMethod($r,'phase');$phase->invoke($r,'measuring');$before=$s->read()['last_worker_memory']??null;$s->write(['id'=>$id,'identity'=>['pid'=>999999]],'actor-work.json');$s->write(['id'=>$id,'identity'=>['pid'=>getmypid()]],'actor-guard.json');$phase->invoke($r,'restoring');$after=$s->read();echo json_encode([$before!==null,$before===($after['last_worker_memory']??null),isset($after['last_guard_memory'])]);""")
        self.assertEqual(r,[True,True,True])

    def test_winning_auto_seed_is_preserved_when_later_recipes_change_the_copy(self):
        r=self.php("""$root=$argv[2];foreach(['source','target']as $x){mkdir($root.'/'.$x);mkdir($root.'/'.$x.'/lists');}file_put_contents($root.'/source/lists/auto.list','winner');$e=['config'=>['NFQWS_ARGS'=>'--hostlist-auto='.$root.'/source/lists/auto.list'],'files'=>['lists/auto.list'=>hash('sha256','')],'mutable_files'=>['lists/auto.list']];$seed=NfqwsStrategyPickerResources::snapshotMutable($e,$root.'/source',(int)$argv[3]);file_put_contents($root.'/source/lists/auto.list','later recipe');$c=NfqwsStrategyPickerResources::retain($e,$root.'/source',$root.'/target',(int)$argv[3],$seed);$path=substr($c['NFQWS_ARGS'],strlen('--hostlist-auto='));echo json_encode([file_get_contents($path),file_get_contents($root.'/source/lists/auto.list')]);""")
        self.assertEqual(r,['winner','later recipe'])

    @unittest.skipIf(os.getuid()==0,'permission failure requires a non-root test process')
    def test_unreadable_auto_is_not_saved_as_an_empty_winning_seed(self):
        r=self.php("""$root=$argv[2];mkdir($root.'/lists');$path=$root.'/lists/auto.list';file_put_contents($path,'winner');chmod($path,0000);$e=['files'=>['lists/auto.list'=>hash('sha256','')],'mutable_files'=>['lists/auto.list']];try{NfqwsStrategyPickerResources::snapshotMutable($e,$root,(int)$argv[3]);$out='accepted';}catch(Throwable $e){$out=$e->getMessage();}finally{chmod($path,0600);}echo json_encode($out);""")
        self.assertEqual(r,'storage_unavailable')

    def test_active_poll_reports_admission_check_without_hashing_detector_again(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$s->write(['id'=>str_repeat('a',32),'state'=>'running','started_at'=>123,'profiles'=>[]]);$r=(new NfqwsStrategyPickerRuntime($s))->status();echo json_encode([$r['active'],$r['detector']]);""")
        self.assertEqual(r,[True,{'installed':True,'available':True,'verification':'admission','verified_at':123}])

    def test_old_or_cross_job_winner_seed_does_not_offer_apply(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$id=str_repeat('a',32);$s->write(['id'=>$id,'state'=>'completed','profiles'=>[],'winner'=>'stock','restored'=>true]);$runtime=new NfqwsStrategyPickerRuntime($s);$out=[$runtime->status()['job']['can_apply']];foreach([str_repeat('b',32),$id]as $seedId){$s->write(['id'=>$seedId,'winner'=>'stock','files'=>[]],'winner-auto.json');$out[]=$runtime->status()['job']['can_apply'];}echo json_encode($out);""")
        self.assertEqual(r,[False,False,True])

    @unittest.skipIf(os.getuid()==0,'permission failure requires a non-root test process')
    def test_unreadable_original_cannot_be_backed_up_as_empty_configuration(self):
        r=self.php("""$root=$argv[2];$p=$root.'/nfqws2.conf';file_put_contents($p,'original');chmod($p,0000);$s=new NfqwsStrategyPickerState($root.'/picker',(int)$argv[3]);$c=new NfqwsStrategyPickerConfig($s,$p,(int)$argv[3]);try{$c->snapshot(true);$out='accepted';}catch(Throwable $e){$out=$e->getMessage();}finally{chmod($p,0600);}echo json_encode([$out,$s->read(),file_get_contents($p)]);""")
        self.assertEqual(r,['storage_unavailable',None,'original'])

    def test_goal_accepts_known_service_sets_and_rejects_duplicates_or_telegram(self):
        r=self.php("""$out=[];foreach(['all','youtube','instagram,discord','youtube,youtube','all,youtube','telegram','https://foreign.test']as $v){try{$out[]=NfqwsStrategyPickerGoals::parse($v);}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,['all','youtube','discord,instagram','invalid_request','invalid_request','invalid_request','invalid_request'])

    def test_selected_goal_does_not_win_from_unrelated_tcp_improvement(self):
        r=self.php("""$m=array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>2,'total'=>5]);$a=['metrics'=>$m,'targets'=>'fixed','youtube'=>array_fill_keys(['http','tls12','tls13','quic'],true),'services'=>['youtube'=>array_fill_keys(['http','tls12','tls13','quic'],['ok'=>1,'total'=>1])]];$b=$a;$b['metrics']['tcp']['ok']=4;echo json_encode([NfqwsStrategyPickerScore::compare([$a,$a],[$b,$b],'all'),NfqwsStrategyPickerScore::compare([$a,$a],[$b,$b],'youtube')]);""")
        self.assertTrue(r[0]['eligible']);self.assertFalse(r[1]['eligible']);self.assertEqual(r[1]['reason'],'goal_no_improvement')

    def test_selected_service_improvement_must_not_mask_another_selected_service_loss(self):
        r=self.php("""$m=array_fill_keys(['tcp','http','tls12','tls13','quic'],['ok'=>2,'total'=>5]);$one=array_fill_keys(['http','tls12','tls13','quic'],['ok'=>0,'total'=>1]);$a=['metrics'=>$m,'targets'=>'fixed','youtube'=>array_fill_keys(['http','tls12','tls13','quic'],false),'services'=>['youtube'=>$one,'instagram'=>$one]];$a['services']['instagram']['tls13']['ok']=1;$b=$a;$b['services']['youtube']['tls13']['ok']=1;$b['services']['instagram']['tls13']['ok']=0;echo json_encode([NfqwsStrategyPickerScore::compare([$a,$a],[$b,$b],'youtube'),NfqwsStrategyPickerScore::compare([$a,$a],[$b,$b],'youtube,instagram')]);""")
        self.assertTrue(r[0]['eligible']);self.assertFalse(r[1]['eligible']);self.assertEqual(r[1]['reason'],'goal_regression')

    def test_native_domains_are_grouped_by_service_without_suffix_lookalikes(self):
        r=self.php("""$rows=[];foreach(['www.youtube.com','discord.com','gateway.discord.gg','media.discordapp.net','www.instagram.com','www.instagram.com.evil.test']as $host)$rows[]=['domain'=>$host,'http'=>'ok','tls12'=>'ok','tls13'=>'ok','quic'=>'unsupported'];$d=['state'=>'completed','coverage'=>['domains'=>6,'tcp'=>1],'groups'=>[['group'=>2,'document'=>['results'=>['domain_inspection'=>$rows]]],['group'=>3,'document'=>['results'=>['tcp16'=>[['id'=>'a','status'=>'ok']]]]]]];echo json_encode(NfqwsStrategyPickerScore::measure($d)['services']);""")
        self.assertEqual({k:v['tls13']['total']for k,v in r.items()},{'youtube':1,'discord':3,'instagram':1})

    def test_goal_is_optional_only_for_start_requests(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$out=[];foreach([['cmd'=>'pickerextended','request_id'=>str_repeat('a',32),'consent'=>'test','goal'=>'youtube,instagram'],['cmd'=>'pickerstatus','goal'=>'youtube'],['cmd'=>'pickerstart','request_id'=>str_repeat('a',32),'consent'=>'test','goal'=>'telegram']]as $p){$p['csrf_token']='x';try{NfqwsStrategyPickerRuntime::validateRequest($p);$out[]='ok';}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,['ok','invalid_request','invalid_request'])

    def test_recovery_gate_keeps_technical_channel_available_without_unlocking_restart(self):
        for cmd,expected in [('technicalstatus','allowed'),('technicalstop','allowed'),('technicalstart','allowed'),('restart',{'error':'recovery_required'})]:
            body="""$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$s->write(['state'=>'recovery_required']);$api=file_get_contents($argv[1].'/strategy-picker-api.php');$api=str_replace("NfqwsPlatform::settings()['web_config'].'/strategy-picker'",var_export($argv[2].'/picker',true),$api);$api=str_replace('new NfqwsStrategyPickerState($root);','new NfqwsStrategyPickerState($root,'.(int)$argv[3].');',$api);$api=str_replace('__DIR__',var_export($argv[1],true),$api);eval('?>'.$api);nfqwsStrategyPickerDispatch(['cmd'=>COMMAND],'x');echo json_encode('allowed');""".replace('COMMAND',json.dumps(cmd))
            self.assertEqual(self.php(body),expected)

    def test_running_selection_keeps_panel_file_reads_available_but_blocks_writes(self):
        for cmd,expected in [('filenames','allowed'),('filecontent','allowed'),('filesave',{'error':'busy'})]:
            with self.subTest(command=cmd):
                body="""$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$s->write(['state'=>'running']);$api=file_get_contents($argv[1].'/strategy-picker-api.php');$api=str_replace("NfqwsPlatform::settings()['web_config'].'/strategy-picker'",var_export($argv[2].'/picker',true),$api);$api=str_replace('new NfqwsStrategyPickerState($root);','new NfqwsStrategyPickerState($root,'.(int)$argv[3].');',$api);$api=str_replace('__DIR__',var_export($argv[1],true),$api);eval('?>'.$api);nfqwsStrategyPickerDispatch(['cmd'=>COMMAND],'x');echo json_encode('allowed');""".replace('COMMAND',json.dumps(cmd))
                self.assertEqual(self.php(body),expected)

if __name__=='__main__':unittest.main()
