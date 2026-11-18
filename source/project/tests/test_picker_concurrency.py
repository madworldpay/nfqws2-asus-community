import json
import hashlib
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


class PickerConcurrencyTests(unittest.TestCase):
    def php(self, body, *args):
        script="require $argv[1].'/strategy-picker-core.php';"+body
        result=subprocess.run([PHP,'-n','-r',script,str(PUBLIC),*args],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(result.stderr,'')
        return json.loads(result.stdout)

    def test_selection_accepts_only_canonical_strings_with_a_finite_syntax_bound(self):
        r=self.php("""$out=[];foreach(['auto','1','2','100','101','512','992','1024','1600','0','1000001','01','+1','1.0','1e2',' 2','2 ','AUTO',"2\\n",'',str_repeat('9',100),1,2.0,true,null,[],new stdClass]as $value){try{$out[]=NfqwsStrategyPickerConcurrency::parse($value);}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r[:9],['auto','1','2','100','101','512','992','1024','1600'])
        self.assertEqual(r[9:],['invalid_request']*18)

    def test_main_manual_1600_is_admitted_without_clamping_with_its_actual_resources(self):
        r=self.php("""$b=NfqwsStrategyPickerBudget::choose(4,2800000,0);$p=NfqwsStrategyPickerConcurrency::plan('1600',$b,['cores'=>4,'available_kib'=>2800000,'fd_soft'=>4096]);echo json_encode($p);""")
        self.assertEqual(r['effective'],1600)
        self.assertEqual(r['budget']['concurrency'],1600)
        self.assertEqual(r['admission']['worker_threads'],4)

    def test_manual_large_pool_records_resources_without_invented_admission_thresholds(self):
        r=self.php("""require $argv[1].'/dpi-install.php';$b=NfqwsStrategyPickerBudget::choose(2,60000,0);$out=[];foreach([['2500',60000,1024],['50000',23000,1024],['100000',1000,0]]as [$request,$memory,$fd]){$p=NfqwsStrategyPickerConcurrency::plan($request,$b,['cores'=>2,'available_kib'=>$memory,'fd_soft'=>$fd]);foreach([true,false]as $launch)NfqwsStrategyPickerConcurrency::assertRuntime($p,['cores'=>2,'available_kib'=>$memory,'fd_soft'=>$fd],$launch);$out[]=['requested'=>$p['requested'],'effective'=>$p['effective'],'memory'=>$p['admission']['available_kib'],'fd'=>$p['admission']['fd_soft'],'floor'=>$p['admission']['memory_floor_kib'],'detector'=>AsusDpiInstaller::memoryAvailability($memory,['options'=>['config'=>['MAX_CONCURRENT'=>(int)$request]]])];}echo json_encode($out);""")
        self.assertEqual([v['effective'] for v in r],[2500,50000,100000])
        self.assertEqual([v['memory'] for v in r],[60000,23000,1000])
        self.assertEqual([v['fd'] for v in r],[1024,1024,0])
        self.assertTrue(all(v['floor']==0 and v['detector']=={'available':True,'code':'ready'} for v in r))

    def test_manual_200_uses_observed_two_core_resources_without_512MiB_restriction(self):
        r=self.php("""$b=NfqwsStrategyPickerBudget::choose(2,98304,0);$out=[];try{$p=NfqwsStrategyPickerConcurrency::plan('200',$b,['cores'=>2,'available_kib'=>98304,'fd_soft'=>1024]);$out['pool']=$p['effective'];$out['floor']=$p['admission']['memory_floor_kib'];foreach([true,false]as $launch){NfqwsStrategyPickerConcurrency::assertRuntime($p,['cores'=>2,'available_kib'=>65536,'fd_soft'=>1024],$launch);}$out['launch_and_running']='ready';}catch(Throwable $e){$out['error']=$e->getMessage();}echo json_encode($out);""")
        self.assertEqual(r,{'pool':200,'floor':0,'launch_and_running':'ready'})

    def test_unlimited_job_status_exposes_elapsed_time_without_invented_remaining_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            r=self.php(r"""
                require $argv[1].'/strategy-picker-runtime.php';
                $base=$argv[2];$file=$base.'/nfqws2.conf';
                file_put_contents($file,'# original');chmod($file,0600);
                $s=new NfqwsStrategyPickerState($base.'/state',(int)getmyuid());
                $c=new NfqwsStrategyPickerConfig($s,$file,(int)getmyuid());
                $j=$c->snapshot(false);$j['state']='running';
                $j['budget']=NfqwsStrategyPickerBudget::choose(4,2800000,0);$j['deadline']=null;
                $now=AsusUpdateStore::uptime();$j['started_uptime']=max(0,$now-172800);
                $expected=(int)floor($now-$j['started_uptime']);$s->write($j);
                $baseline=$s->read();$hash=hash_file('sha256',$s->path('state.json'));
                $job=(new NfqwsStrategyPickerRuntime($s,$c))->status()['job'];
                echo json_encode(['elapsed'=>$job['elapsed_seconds']??null,'min_elapsed'=>$expected,
                    'max_elapsed'=>(int)floor(AsusUpdateStore::uptime()-$j['started_uptime']),
                    'remaining_present'=>array_key_exists('remaining_seconds',$job),'remaining'=>$job['remaining_seconds']??null,
                    'journal_unchanged'=>$s->read()===$baseline&&hash_file('sha256',$s->path('state.json'))===$hash]);
            """,directory)
        self.assertTrue(r['remaining_present'])
        self.assertIsNone(r['remaining'])
        self.assertGreaterEqual(r['elapsed'],r['min_elapsed'])
        self.assertLessEqual(r['elapsed'],r['max_elapsed'])
        self.assertTrue(r['journal_unchanged'])

    def test_unlimited_deadline_is_explicit_source_state_and_legacy_bounds_remain_finite(self):
        r=self.php("""$out=[];foreach([['deadline'=>null,'started_uptime'=>10],['deadline'=>12],['deadline'=>null],[],['deadline'=>'12']]as $j){try{$out[]=NfqwsStrategyPickerBudget::overallDeadline($j);}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,[None,12,'stale_state','stale_state','stale_state'])

    def test_status_reports_remaining_time_from_the_original_monotonic_deadline(self):
        r=self.php("""require $argv[1].'/strategy-picker-runtime.php';$base=getenv('TMPDIR').'/picker-remaining-'.bin2hex(random_bytes(8));mkdir($base,0700);$file=$base.'/nfqws2.conf';file_put_contents($file,'# original');chmod($file,0600);$s=new NfqwsStrategyPickerState($base.'/state',(int)getmyuid());$c=new NfqwsStrategyPickerConfig($s,$file,(int)getmyuid());$j=$c->snapshot(false);$j['state']='running';$j['budget']=NfqwsStrategyPickerBudget::choose(4,2800000,0);$j['budget']['deadline_seconds']=120;$j['deadline']=AsusUpdateStore::uptime()+120;$s->write($j);$v=(new NfqwsStrategyPickerRuntime($s,$c))->status();echo json_encode(['remaining'=>$v['job']['remaining_seconds']??null,'elapsed'=>$v['job']['elapsed_seconds']??null,'original_deadline_unchanged'=>$s->read()['deadline']===$j['deadline']]);""")
        self.assertGreaterEqual(r['remaining'],118)
        self.assertLessEqual(r['remaining'],120)
        self.assertLessEqual(r['elapsed'],2)
        self.assertTrue(r['original_deadline_unchanged'])

    def test_auto_preserves_every_legacy_budget_field_even_when_strict_facts_are_unknown(self):
        r=self.php("""$out=[];foreach([[1,48000,.2],[2,70000,0],[4,300000,.5],[4,300000,7]]as $v){$old=NfqwsStrategyPickerBudget::choose(...$v);$p=NfqwsStrategyPickerConcurrency::plan('auto',$old,[]);$out[]=['same'=>$p['budget']===$old,'pool'=>$p['effective'],'requested'=>$p['requested'],'admission'=>$p['admission']];}echo json_encode($out);""")
        self.assertEqual([v['pool']for v in r],[2,4,10,2])
        self.assertTrue(all(v['same']and v['requested']=='auto'and v['admission']is None for v in r))

    def test_manual_pool_is_not_silently_reduced_on_a_busy_device(self):
        r=self.php("""$b=NfqwsStrategyPickerBudget::choose(4,900000,8);$p=NfqwsStrategyPickerConcurrency::plan('100',$b,['cores'=>4,'available_kib'=>900000,'fd_soft'=>1024]);echo json_encode($p);""")
        self.assertEqual(r['effective'],100);self.assertEqual(r['requested'],'100')
        self.assertEqual(r['budget']['concurrency'],100);self.assertTrue(r['budget']['busy'])
        self.assertEqual(r['budget']['max_repeats'],4)
        self.assertEqual(r['budget']['group_seconds'],240)
        self.assertEqual(r['budget']['probe_seconds'],510)

    def test_manual_admission_refuses_unknown_or_coerced_CPU_and_memory_facts(self):
        r=self.php("""$out=[];$b=NfqwsStrategyPickerBudget::choose(4,900000,0);foreach([[],['cores'=>0,'available_kib'=>900000],['cores'=>'4','available_kib'=>900000],['cores'=>4,'available_kib'=>0],['cores'=>4,'available_kib'=>'900000'],['cores'=>4.0,'available_kib'=>900000],['cores'=>4,'available_kib'=>false]]as $facts){try{NfqwsStrategyPickerConcurrency::plan('10',$b,$facts);$out[]='accepted';}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,['unsupported_runtime']*7)

    def test_manual_plans_record_small_memory_without_assumed_floors(self):
        r=self.php("""$b=NfqwsStrategyPickerBudget::choose(4,900000,0);$out=[];foreach([['100',1,24575],['100',1,24576],['200',2,65535],['200',0,65536],['200',2,65536]]as [$pool,$cores,$memory]){try{$p=NfqwsStrategyPickerConcurrency::plan($pool,$b,['cores'=>$cores,'available_kib'=>$memory,'fd_soft'=>2048]);$out[]=['pool'=>$p['effective'],'cores'=>$p['budget']['cores'],'memory'=>$p['budget']['available_kib'],'admission'=>$p['admission']];}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r[0]['pool'],100);self.assertEqual(r[1]['pool'],100)
        self.assertEqual(r[1]['cores'],1);self.assertEqual(r[1]['memory'],24576)
        self.assertEqual(r[2]['pool'],200);self.assertEqual(r[3],'unsupported_runtime')
        self.assertEqual(r[4]['admission']['worker_threads'],4)
        self.assertEqual(r[4]['admission']['memory_floor_kib'],0)

    def test_high_pool_records_descriptors_without_refusing_the_request(self):
        r=self.php("""$b=NfqwsStrategyPickerBudget::choose(4,900000,0);$out=[];foreach([['512',null],['513',null],['513',544],['513',545],['992',1024],['1024',1055],['1024',1056],['992','1024']]as [$pool,$fd]){try{$p=NfqwsStrategyPickerConcurrency::plan($pool,$b,['cores'=>4,'available_kib'=>900000,'fd_soft'=>$fd]);$out[]=$p['effective'];}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,[512,513,513,513,992,1024,1024,'unsupported_runtime'])

    def test_manual_timeout_math_covers_the_full_scope_or_refuses_it(self):
        r=self.php("""$b=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(4,900000,0),38);$out=[];foreach(['1','2','4','10']as $pool){try{$p=NfqwsStrategyPickerConcurrency::plan($pool,$b,['cores'=>4,'available_kib'=>900000]);$out[]=$p['budget'];}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r[0],'concurrency_budget_unavailable')
        self.assertEqual([(v['concurrency'],v['domain_count'],v['group_seconds'],v['probe_seconds'])for v in r[1:]],[(2,38,668,1366),(4,38,364,758),(10,38,240,510)])
        self.assertTrue(all(v['probe_seconds']<=1800 for v in r[1:]))

    def test_custom_whole_series_budget_uses_the_selected_pool_and_keeps_its_hard_bound(self):
        r=self.php("""$b=NfqwsStrategyPickerBudget::coverDomains(NfqwsStrategyPickerBudget::choose(4,900000,0),38);$out=[];foreach(['2','10']as $pool){$p=NfqwsStrategyPickerConcurrency::plan($pool,$b,['cores'=>4,'available_kib'=>900000]);$out[]=NfqwsStrategyPickerBudget::custom($p['budget'],5);}echo json_encode($out);""")
        self.assertEqual([v['concurrency']for v in r],[2,10])
        self.assertGreater(r[0]['deadline_seconds'],r[1]['deadline_seconds'])
        self.assertEqual(r[1]['deadline_seconds'],6480)
        self.assertTrue(all(v['deadline_seconds']<=14400 and v['custom']['max_hosts']==5 for v in r))

    def test_resource_changes_do_not_stop_running_work_and_metadata_is_strict(self):
        r=self.php("""$b=NfqwsStrategyPickerBudget::choose(4,900000,0);$p=NfqwsStrategyPickerConcurrency::plan('992',$b,['cores'=>4,'available_kib'=>900000,'fd_soft'=>1024]);$out=[];foreach([[false,65536,4,1024],[false,65535,4,1024],[true,65536,4,1024],[true,524288,4,1024],[false,900000,3,1024],[false,900000,4,1023]]as [$launch,$memory,$cores,$fd]){try{NfqwsStrategyPickerConcurrency::assertRuntime($p,['cores'=>$cores,'available_kib'=>$memory,'fd_soft'=>$fd],$launch);$out[]='ready';}catch(Throwable $e){$out[]=$e->getMessage();}}foreach(['requested','effective','policy_version']as $key){$bad=$p;$bad[$key]=($key==='effective'?991:'tampered');try{NfqwsStrategyPickerConcurrency::assertRuntime($bad,['cores'=>4,'available_kib'=>900000,'fd_soft'=>1024],false);$out[]='accepted';}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,['ready']*6+['invalid_request']*3)

    def test_manual_pool_binds_the_canonical_work_identity_while_auto_keeps_legacy_digest(self):
        r=self.php("""$old=['search'=>'synthesis','extended'=>false,'goal'=>'youtube,instagram'];$a=NfqwsStrategyPickerRequest::selection(false,'instagram,youtube',true);$b=NfqwsStrategyPickerRequest::selection(false,'youtube,instagram',true,null,'auto');$m=NfqwsStrategyPickerRequest::selection(false,'instagram,youtube',true,null,'32');echo json_encode(['auto'=>$a,'explicit_auto'=>$b,'manual'=>$m,'old_digest'=>NfqwsStrategyPickerRequest::digest($old),'auto_digest'=>NfqwsStrategyPickerRequest::digest($a),'manual_digest'=>NfqwsStrategyPickerRequest::digest($m)]);""")
        self.assertEqual(r['auto'],r['explicit_auto'])
        self.assertNotIn('concurrency',r['auto'])
        self.assertEqual(r['manual'],dict(r['auto'],concurrency='32'))
        legacy=hashlib.sha256(json.dumps([1,None,r['auto']],separators=(',',':')).encode()).hexdigest()
        self.assertEqual(r['auto_digest'],legacy);self.assertEqual(r['old_digest'],legacy)
        self.assertNotEqual(r['manual_digest'],legacy)

    def test_manual_retry_refuses_pool_goal_search_or_custom_scope_changes_under_the_same_id(self):
        r=self.php("""$id=str_repeat('a',32);$custom=['hosts'=>['a.example.com','b.example.com'],'only'=>false];$a=NfqwsStrategyPickerRequest::selection(false,'youtube',true,$custom,'32');$old=$a+['request_id'=>$id,'selection_sha256'=>NfqwsStrategyPickerRequest::digest($a)];$out=[NfqwsStrategyPickerRequest::retry($old,$id,$a)];foreach([[false,'youtube',true,$custom,'33'],[false,'youtube',true,$custom,'auto'],[false,'discord',true,$custom,'32'],[false,'youtube',false,null,'32'],[false,'youtube',true,['hosts'=>['a.example.com'],'only'=>false],'32']]as $args){try{$out[]=NfqwsStrategyPickerRequest::retry($old,$id,NfqwsStrategyPickerRequest::selection(...$args));}catch(Throwable $e){$out[]=$e->getMessage();}}$out[]=NfqwsStrategyPickerRequest::retry($old,str_repeat('b',32),$a);echo json_encode($out);""")
        self.assertEqual(r,[True]+['request_conflict']*5+[False])

    def test_legacy_jobs_decode_as_auto_and_malformed_recorded_manual_choices_do_not_retry(self):
        r=self.php("""$id=str_repeat('a',32);$auto=NfqwsStrategyPickerRequest::selection(false,'all',true);$manual=NfqwsStrategyPickerRequest::selection(false,'all',true,null,'32');$old=$auto+['request_id'=>$id];$out=[NfqwsStrategyPickerRequest::retry($old,$id,$auto)];try{$out[]=NfqwsStrategyPickerRequest::retry($old,$id,$manual);}catch(Throwable $e){$out[]=$e->getMessage();}foreach([null,32,'032','99999']as $choice){$bad=$old;$bad['concurrency']=$choice;try{$out[]=NfqwsStrategyPickerRequest::retry($bad,$id,$auto);}catch(Throwable $e){$out[]=$e->getMessage();}}echo json_encode($out);""")
        self.assertEqual(r,[True]+['request_conflict']*5)


if __name__=='__main__':unittest.main()
