"""Large native reports must not exhaust CGI or prevent terminal recovery."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import PHP, PUBLIC


BOOTSTRAP = r'''
// Match asus/dpi/worker.php: test the actual DPI entry dependency boundary.
require $argv[1].'/dpi-jobs.php';
$fixture=json_decode(file_get_contents($argv[3]),true,32,JSON_THROW_ON_ERROR);
$GLOBALS['report_resources']=['/proc/stat'=>"cpu 1 2 3 4\n".implode('',array_map(fn($i)=>"cpu$i 1 2 3 4\n",range(0,$fixture['cores']-1))),'/proc/meminfo'=>"MemAvailable: ".$fixture['memory']." kB\n",'/proc/self/limits'=>"Max open files 1024 4096 files\n"];
$GLOBALS['report_fatal']=$fixture['fatal'];
$shim= <<<'PHP'
namespace ReportMemoryHarness;
use \RuntimeException;use \Throwable;
use \AsusDpiStore;use \AsusDpiOptions;use \AsusDpiNative;use \AsusDpiAnalysis;
use \AsusDpiNormalizer;use \AsusDpiRuntime;use \AsusDpiInstaller;use \AsusDpiCatalog;
use \AsusDpiTerminalLifecycle;use \AsusDpiDnsContext;use \NfqwsPlatform;
function ini_set($key,$value){
 if($key==='memory_limit'&&($GLOBALS['deny_heap_growth']??false))return false;
 return \ini_set($key,$value);
}
function file_get_contents($p,...$args){
 if($p==='/proc/stat'&&$GLOBALS['report_fatal'])exit(73);
 return $GLOBALS['report_resources'][$p]??\file_get_contents($p,...$args);
}
PHP;
$policy=substr(file_get_contents($argv[1].'/dpi-load-policy.php'),5);
$jobs=str_replace('__DIR__',var_export($argv[1],true),substr(file_get_contents($argv[1].'/dpi-jobs.php'),5));
eval($shim.$policy.$jobs);
$v=$fixture['native'];$options=AsusDpiOptions::normalize($v['options']);
$store=new AsusDpiStore($argv[2].'/state',(int)$argv[4]);
$context=['nfqws'=>'running','ark'=>'absent','tun_observed'=>false];
'''


def fixture(count=1000, cores=4, memory=524288, fatal=False):
    targets = [{'id':f'PRIVATE_CANARY_{i}', 'ip':'198.51.100.22', 'port':443,
                'sni':'endpoint.example'} for i in range(count)]
    rows = [{**t, 'asn':'TEST-ASN', 'provider':'synthetic', 'status':'ok',
             'detail':'elapsed_1234ms', 'duration_ms':1234, 'received_kb':16}
            for t in targets]
    domains = [f'fixture{i}.example' for i in range(38)]
    domain_rows = [{'domain':d,'http':'ok','tls12':'ok','tls13':'ok',
                    'quic':'quic_ok'} for d in domains]
    return {'cores':cores,'memory':memory,'fatal':fatal,'native':{
        'options':{'config':{'MAX_CONCURRENT':200,'IP_VERSION':'ipv4',
                            'TLS_FINGERPRINT':'rustls','TIMEOUT':8},
                   'targets':{'domains':domains,'tcp':targets}},
        'groups':[{'group':2,'document':{'schema_version':1,'results':{
                    'domain_inspection':domain_rows}}},
                  {'group':3,'document':{'schema_version':1,'results':{'tcp16':rows}}}]}}


SETUP_JOB = r'''
$job=$store->reserve('11111111-1111-4111-8111-111111111111','run',
 ['tests'=>[2,3],'heavy_consent'=>[],'options'=>$options]);
'''
ORPHAN = SETUP_JOB + r'''
$store->update($job['id'],['state'=>'running','groups'=>$v['groups'],
 'messages'=>[['group'=>3,'text'=>'PRIVATE_CANARY message']],
 'context_before'=>$context]);
$dbpath=$argv[2].'/state/jobs.json';$db=json_decode(file_get_contents($dbpath),true);
$db['jobs'][$job['id']]['started_at']-=10;file_put_contents($dbpath,json_encode($db));
$before=hash_file('sha256',$argv[2].'/state/'.$job['id'].'.groups.json');
$jobs=new ReportMemoryHarness\AsusDpiJobs($store);
'''


class ReportMemoryTests(unittest.TestCase):
    def test_after_dns_evidence_survives_death_inside_optional_export(self):
        body=SETUP_JOB+r'''$n=0;$context['dns']=['schema_version'=>1,'state'=>'known','sha256'=>str_repeat('a',64)];
        $w=new ReportMemoryHarness\AsusDpiWorker($store,['work'=>fn()=>$argv[2],'binary'=>fn()=>'/synthetic-native',
          'probe'=>function()use(&$n,$v){return ['exit'=>0,'stdout'=>json_encode($v['groups'][$n++]['document'])];},
          'context'=>function(?array &$failure=null)use($context){static $calls=0;if(++$calls===1)return $context;
            $observed=AsusDpiDnsContext::observe(['platform'=>'asus-entware','primary'=>fn()=>throw new RuntimeException('DNS_PRIVATE_CANARY')]);
            $failure=$observed['failure'];$context['dns']=$observed['context'];$GLOBALS['report_fatal']=true;return $context;}]);$w->run($job['id']);'''
        with tempfile.TemporaryDirectory() as tmp:
            first=self.execute(body,limit='64M',directory=tmp)
            self.assertEqual(first.returncode,73,first.stdout+first.stderr)
            dbpath=Path(tmp)/'state/jobs.json';db=json.loads(dbpath.read_text());job=next(iter(db['jobs'].values()))
            self.assertEqual(job.get('context_after',{}).get('dns',{}).get('state'),'unknown')
            messages=json.loads((Path(tmp)/'state'/(job['id']+'.messages.json')).read_text())
            self.assertIn('DNS context unavailable (after): primary external:0',json.dumps(messages))
            db['jobs'][job['id']]['started_at']-=10;dbpath.write_text(json.dumps(db))
            recover=r'''$count=0;$jobs=new ReportMemoryHarness\AsusDpiJobs($store,['recovery_context'=>function(?array &$failure=null)use(&$count,$context){$count++;return $context;}]);$jobs->active();echo json_encode(['native'=>json_decode($store->readNative('JOBID'),true),'new_samples'=>$count]);'''.replace('JOBID',job['id'])
            result=self.execute(recover,limit='64M',directory=tmp)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            value=json.loads(result.stdout)
            self.assertEqual(value['new_samples'],0)
            self.assertEqual(value['native']['state'],'interrupted')
            self.assertEqual(value['native']['context']['after']['dns']['state'],'unknown')
            self.assertIn('DNS context unavailable (after): primary external:0',json.dumps(value['native']['messages']))
            self.assertNotIn('DNS_PRIVATE_CANARY',json.dumps(value))

    def test_recovery_dns_failure_is_journaled_before_its_optional_export_dies(self):
        body=ORPHAN+r'''$jobs=new ReportMemoryHarness\AsusDpiJobs($store,['recovery_context'=>function(?array &$failure=null)use($context){
          $observed=AsusDpiDnsContext::observe(['platform'=>'asus-entware','primary'=>fn()=>throw new RuntimeException('DNS_PRIVATE_CANARY')]);
          $failure=$observed['failure'];$context['dns']=$observed['context'];$GLOBALS['report_fatal']=true;return $context;}]);$jobs->active();'''
        with tempfile.TemporaryDirectory() as tmp:
            result=self.execute(body,limit='64M',directory=tmp)
            self.assertEqual(result.returncode,73,result.stdout+result.stderr)
            db=json.loads((Path(tmp)/'state/jobs.json').read_text());job=next(iter(db['jobs'].values()))
            self.assertEqual(job['state'],'interrupted')
            messages=json.loads((Path(tmp)/'state'/(job['id']+'.messages.json')).read_text())
            self.assertIn('DNS context unavailable (recovery): primary external:0',json.dumps(messages))
            self.assertNotIn('DNS_PRIVATE_CANARY',json.dumps(messages))

    def execute(self, body, data=None, limit='8M', disabled=False, directory=None):
        data = fixture() if data is None else data
        if directory is None:
            with tempfile.TemporaryDirectory() as tmp:
                return self.execute(body,data,limit,disabled,tmp)
        path=Path(directory)/'fixture.json';path.write_text(json.dumps(data))
        args=[PHP,'-n','-d','memory_limit='+limit]
        if disabled: args+=['-d','disable_functions=ini_set']
        args+=['-r',BOOTSTRAP+body,str(PUBLIC),directory,str(path),str(os.getuid())]
        return subprocess.run(args,capture_output=True,text=True,timeout=30)

    def result(self, body, **kwargs):
        r=self.execute(body,**kwargs)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)

    def test_full_native_result_patch_from_eight_mib_retains_all_rows_without_identity(self):
        body=r'''$job=['started_at'=>1760000000,'params'=>['tests'=>[2,3]]];
        $p=ReportMemoryHarness\AsusDpiWorker::resultPatch($job,$v['groups'],$options,'completed',1760000001,$context,$context,[]);
        $r=json_decode($p['result'],true);echo json_encode(['state'=>$r['state'],'rows'=>count($r['groups'][1]['rows']),'last'=>$r['groups'][1]['rows'][999]['target'],'coverage'=>$r['coverage']['tcp'],'pool'=>$r['settings']['metrics']['max_concurrent'],'bytes'=>strlen($p['result']),'native_bytes'=>strlen($p['native']),'leak'=>str_contains($p['result'],'PRIVATE_CANARY')||str_contains($p['result'],'198.51.100.22'),'heap_limit'=>ini_get('memory_limit')]);'''
        r=self.result(body)
        self.assertEqual([r['state'],r['rows'],r['last'],r['coverage'],r['pool']],
                         ['completed',1000,'tcp-1000',1000,200])
        self.assertLessEqual(r['bytes'],262144);self.assertLessEqual(r['native_bytes'],1048576)
        self.assertFalse(r['leak']);self.assertEqual(r['heap_limit'],'32M')

    def test_large_worker_reserves_heap_before_parsing_native_groups(self):
        body=SETUP_JOB+r'''$i=0;$w=new ReportMemoryHarness\AsusDpiWorker($store,
         ['work'=>fn()=>$argv[2],'binary'=>fn()=>'/synthetic-native',
          'probe'=>function()use(&$i,$v){return ['exit'=>0,'stdout'=>json_encode($v['groups'][$i++]['document'])];},
          'context'=>fn()=>$context]);
        $w->run($job['id']);$s=$store->status();$r=json_decode($store->readResult($job['id']),true);
        echo json_encode(['active'=>$s['active'],'state'=>$s['history'][0]['state'],'probes'=>$i,'rows'=>count($r['groups'][1]['rows']),'heap_limit'=>ini_get('memory_limit')]);'''
        self.assertEqual(self.result(body),{'active':None,'state':'completed','probes':2,
                                          'rows':1000,'heap_limit':'32M'})

    def test_orphan_recovers_large_exports_from_eight_mib(self):
        body=ORPHAN+r'''$status=$jobs->status();$n=json_decode($store->readNative($job['id']),true);
        $r=json_decode($store->readResult($job['id']),true);
        echo json_encode(['active'=>$status['active'],'state'=>$status['history'][0]['state'],'native_state'=>$n['state'],'rows'=>count($r['groups'][1]['rows']),'groups_preserved'=>$before===hash_file('sha256',$argv[2].'/state/'.$job['id'].'.groups.json')]);'''
        self.assertEqual(self.result(body),{'active':None,'state':'interrupted',
                         'native_state':'interrupted','rows':1000,'groups_preserved':True})

    def test_resource_observations_allow_orphan_report_and_real_heap_refusal_keeps_it_idle(self):
        body=ORPHAN+r'''$status=$jobs->status();echo json_encode(['active'=>$status['active'],'state'=>$status['history'][0]['state'],'code'=>$status['history'][0]['code'],'native'=>$status['history'][0]['native_available'],'groups_preserved'=>$before===hash_file('sha256',$argv[2].'/state/'.$job['id'].'.groups.json')]);'''
        for cores,memory,denied in [(4,524287,False),(2,1048576,False),(4,524287,True)]:
            with self.subTest(cores=cores,memory=memory,heap_change_denied=denied):
                self.assertEqual(self.result(body,data=fixture(cores=cores,memory=memory),disabled=denied),
                    {'active':None,'state':'interrupted','code':'unsupported_runtime' if denied else 'interrupted',
                     'native':not denied,'groups_preserved':True})

    def test_admin_denied_heap_change_preserves_terminal_and_original_evidence(self):
        body=ORPHAN+r'''$status=$jobs->status();$next=$store->reserve('22222222-2222-4222-8222-222222222222','run',['tests'=>[2],'heavy_consent'=>[]]);echo json_encode(['active'=>$status['active'],'state'=>$status['history'][0]['state'],'code'=>$status['history'][0]['code'],'next_queued'=>$next['state'],'groups_preserved'=>$before===hash_file('sha256',$argv[2].'/state/'.$job['id'].'.groups.json')]);'''
        self.assertEqual(self.result(body,disabled=True),{'active':None,'state':'interrupted',
            'code':'unsupported_runtime','next_queued':'queued','groups_preserved':True})

    def test_fatal_optional_report_is_followed_by_an_idle_persistent_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=self.execute(ORPHAN+"$jobs->status();",data=fixture(fatal=True),directory=tmp)
            self.assertNotEqual(r.returncode,0)
            code="require $argv[1].'/dpi-store.php';$s=new AsusDpiStore($argv[2].'/state',(int)$argv[3]);echo json_encode($s->status(false));"
            read=subprocess.run([PHP,'-n','-d','memory_limit=8M','-r',code,str(PUBLIC),tmp,str(os.getuid())],capture_output=True,text=True)
            self.assertEqual(read.returncode,0,read.stdout+read.stderr)
            s=json.loads(read.stdout);self.assertIsNone(s['active']);self.assertEqual(s['history'][0]['state'],'interrupted')
            self.assertTrue(list((Path(tmp)/'state').glob('*.groups.json')))

    def test_small_legacy_report_and_larger_existing_heap_are_never_reconfigured(self):
        body="ReportMemoryHarness\\AsusDpiLoadPolicy::reportMemory($options);echo json_encode(ini_get('memory_limit'));"
        self.assertEqual(self.result(body,data=fixture(1,cores=2,memory=60000)),'8M')
        self.assertEqual(self.result(body,limit='64M'),'64M')
        self.assertEqual(self.result(body,limit='-1'),'-1')

    def test_worker_resource_refusal_is_terminal_before_any_probe(self):
        body=SETUP_JOB+r'''$i=0;$w=new ReportMemoryHarness\AsusDpiWorker($store,['work'=>fn()=>$argv[2],'binary'=>fn()=>'/synthetic-native','probe'=>function()use(&$i){++$i;return ['exit'=>1,'stdout'=>''];}]);$w->run($job['id']);$s=$store->status();echo json_encode(['active'=>$s['active'],'state'=>$s['history'][0]['state'],'code'=>$s['history'][0]['code'],'probes'=>$i]);'''
        self.assertEqual(self.result(body,data=fixture(memory=524287),disabled=True),
                         {'active':None,'state':'failed','code':'unsupported_runtime','probes':0})

    def test_deleting_a_result_fences_an_inflight_recovery_writer(self):
        body=SETUP_JOB+r"""$store->update($job['id'],['state'=>'running','groups'=>$v['groups']]);
        $store->update($job['id'],['state'=>'interrupted','finished_at'=>time()]);
        $expected=$store->status(false)['history'][0];$data=$store->recoveryData($expected);
        $store->deleteResult($job['id']);
        try{$store->completeRecovery($expected,['native'=>'PRIVATE_CANARY deleted']);$error=null;}
        catch(Throwable $e){$error=$e->getMessage();}
        echo json_encode(['error'=>$error,'restored'=>is_file($argv[2].'/state/'.$job['id'].'.native.json'),
         'groups'=>$store->status(false)['history'][0]['groups']]);"""
        self.assertEqual(self.result(body, data=fixture(1)),
                         {'error':'request_conflict','restored':False,'groups':[]})

    def test_late_report_memory_refusal_preserves_cancellation_timeout_and_interruption(self):
        body=SETUP_JOB+r"""$calls=0;$w=new ReportMemoryHarness\AsusDpiWorker($store,
         ['work'=>fn()=>$argv[2],'binary'=>fn()=>'/synthetic-native',
          'probe'=>function()use(&$calls,$v){
            if(++$calls===1&&$GLOBALS['keep_group'])return ['exit'=>0,'stdout'=>json_encode($v['groups'][0]['document'])];
            if(\ini_set('memory_limit','8M')===false)throw new \LogicException('fixture_heap');
            $GLOBALS['deny_heap_growth']=true;
            throw new RuntimeException($GLOBALS['probe_failure']);},'context'=>fn()=>$context]);
        $w->run($job['id']);$s=$store->status(false);echo json_encode(['active'=>$s['active'],
         'state'=>$s['history'][0]['state'],'code'=>$s['history'][0]['code'],
         'groups'=>count($s['history'][0]['groups'])]);"""
        for state in ['cancelled','timed_out','interrupted']:
            for keep in [False,True]:
                with self.subTest(state=state,keep_group=keep):
                    setup="$GLOBALS['probe_failure']="+json.dumps(state)+";$GLOBALS['keep_group']="+('true' if keep else 'false')+";"
                    self.assertEqual(self.result(setup+body),{'active':None,'state':state,'code':state,'groups':int(keep)})

    def test_late_report_memory_refusal_is_partial_only_when_a_group_completed(self):
        body=SETUP_JOB+r"""$calls=0;$w=new ReportMemoryHarness\AsusDpiWorker($store,
         ['work'=>fn()=>$argv[2],'binary'=>fn()=>'/synthetic-native',
          'probe'=>function()use(&$calls,$v){
            if(++$calls===1&&$GLOBALS['keep_group'])return ['exit'=>0,'stdout'=>json_encode($v['groups'][0]['document'])];
            if(\ini_set('memory_limit','8M')===false)throw new \LogicException('fixture_heap');
            $GLOBALS['deny_heap_growth']=true;
            throw new RuntimeException('probe_failed');},'context'=>fn()=>$context]);
        $w->run($job['id']);$s=$store->status(false);echo json_encode(['active'=>$s['active'],
         'state'=>$s['history'][0]['state'],'code'=>$s['history'][0]['code'],
         'groups'=>count($s['history'][0]['groups'])]);"""
        for keep in [False,True]:
            with self.subTest(keep_group=keep):
                self.assertEqual(self.result("$GLOBALS['keep_group']="+('true' if keep else 'false')+";"+body),
                    {'active':None,'state':'partial' if keep else 'failed','code':'unsupported_runtime','groups':int(keep)})

    def test_saved_options_digest_is_verified_before_use(self):
        body=SETUP_JOB+r'''$path=$argv[2].'/state/'.$job['id'].'.options.json';$changed=$options;$changed['config']['MAX_CONCURRENT']=400;file_put_contents($path,json_encode($changed));try{$store->readOptions($job['id']);$error=null;}catch(Throwable $e){$error=$e->getMessage();}echo json_encode(['error'=>$error,'actual_pool'=>json_decode(file_get_contents($path),true)['config']['MAX_CONCURRENT']]);'''
        self.assertEqual(self.result(body),{'error':'invalid_state','actual_pool':400})


if __name__=='__main__':unittest.main()
