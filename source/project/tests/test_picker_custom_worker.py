"""CLI leaf contracts with real process identities and private temporary state."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from test_dpi_normalize import PHP, PUBLIC

WORKER=PUBLIC/'strategy-picker-custom-worker.php'
ID='a'*32
NONCE='b'*32
DNS='c'*64

def encode(value):
    return json.dumps(value,separators=(',',':'))

class CustomWorkerTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(WORKER.is_file(),'The owned custom CLI worker is not implemented')

    def observe(self,document,stage='prepare',mutation='',resolver=None,probe=None,raw=None,php=None):
        # External DNS/TLS are injected at their existing trusted local boundary.
        # Authority, complete JSON validation, pinning and state reads stay real.
        body=raw if raw is not None else encode(document)
        resolver=resolver or "return ['8.8.8.8','8.8.4.4'];"
        probe=probe or "$r=AsusDpiSiteCheck::response('response');$r['http_status']=403;return $r;"
        holders=[]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            try:
                for role in ['work','guard']:
                    actor=subprocess.Popen([PHP,'-n','-r','usleep(20000000);',str(PUBLIC/'strategy-picker-runtime.php'),'--',role,ID],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                    holders.append(actor)
                    # Wait for exec before recording the identity.
                    for _ in range(100):
                        args=Path(f'/proc/{actor.pid}/cmdline').read_bytes().rstrip(b'\0').split(b'\0')
                        if args[-4:]==[os.fsencode(PUBLIC/'strategy-picker-runtime.php'),b'--',role.encode(),ID.encode()]:break
                        time.sleep(.005)
                    else:self.fail('Actor fixture did not exec')
                bootstrap=root/'invoke.php'
                bootstrap.write_text('''<?php
require $argv[1].'/strategy-picker-custom-worker.php';
$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);
$id=str_repeat('a',32);$nonce=str_repeat('b',32);$stage=$argv[4];
try{$input=NfqwsStrategyPickerCustomWorker::readInput(fopen('php://stdin','rb'));}
catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);exit;}
$j=['id'=>$id,'state'=>'running','phase'=>'discovering','deadline'=>AsusUpdateStore::uptime()+90,
    'actuator'=>NfqwsStrategyPickerRuntime::identity(getmypid()),
    'custom_worker'=>['stage'=>$stage,'nonce'=>$nonce,'payload_sha256'=>hash('sha256',$input),'deadline'=>AsusUpdateStore::uptime()+80]];
$s->write($j);
foreach(['work'=>(int)$argv[5],'guard'=>(int)$argv[6]]as $role=>$pid)
    $s->write(['id'=>$id,'identity'=>NfqwsStrategyPickerRuntime::identity($pid)],'actor-'.$role.'.json');
''' + mutation + '''
$deps=['resolve'=>static function($host)use($argv,$s){file_put_contents($argv[2].'/dns',"called\\n",FILE_APPEND);''' + resolver + '''},
'probe'=>static function($host,$answer,$mode,$seconds)use($argv,$s){file_put_contents($argv[2].'/probes',json_encode([$host,$answer,$mode,$seconds])."\\n",FILE_APPEND);''' + probe + '''}];
try{$result=(new NfqwsStrategyPickerCustomWorker($s,$deps))->execute($stage,$id,$nonce,$input);echo json_encode(['result'=>$result]);}
catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}
''')
                argv=[php or PHP,'-n','-d','register_argc_argv=1','-q','-f',str(bootstrap),'--',str(PUBLIC),tmp,str(os.getuid()),stage,str(holders[0].pid),str(holders[1].pid),str(WORKER),'--',stage,ID,NONCE]
                result=subprocess.run(argv,input=body,text=True,capture_output=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr+result.stdout)
                self.assertEqual(result.stderr,'')
                output=json.loads(result.stdout)
                output['dns_calls']=(root/'dns').read_text().count('called') if (root/'dns').exists() else 0
                output['probe_calls']=[json.loads(x)for x in (root/'probes').read_text().splitlines()] if (root/'probes').exists() else []
                return output
            finally:
                for actor in holders:
                    if actor.poll() is None:actor.terminate()
                    actor.communicate(timeout=3)

    def prepare(self):
        return {'schema_version':1,'hosts':['www.youtube.com','nnmclub.to'],'dns_context':DNS}

    def pins(self):
        return {'schema_version':1,'hosts':['nnmclub.to'],'dns_context':DNS,
                'policy':'uts46-533d68c-nfc-ebd57cc-std3-bidi-contextj-nontransitional-v1',
                'fingerprint':'php-openssl-pinned-https-v1',
                'pins':[{'host':'nnmclub.to','answer':['8.8.8.8'],'address':'8.8.8.8'}]}

    def test_prepare_pins_the_complete_answer_and_keeps_only_canonical_targets(self):
        out=self.observe(self.prepare())
        self.assertNotIn('error',out)
        self.assertEqual(out['dns_calls'],2)
        self.assertEqual(out['probe_calls'],[])
        result=out['result']
        self.assertEqual(result['schema_version'],1)
        self.assertEqual(result['hosts'],['www.youtube.com','nnmclub.to'])
        self.assertEqual(result['dns_context'],DNS)
        self.assertEqual(result['pins'],[
            {'host':'www.youtube.com','answer':['8.8.4.4','8.8.8.8'],'address':'8.8.4.4'},
            {'host':'nnmclub.to','answer':['8.8.4.4','8.8.8.8'],'address':'8.8.4.4'}])

    def test_bad_complete_document_or_hostname_set_never_starts_dns(self):
        cases=[{},self.prepare()|{'extra':'ignored?'},self.prepare()|{'hosts':['https://youtube.com/path']},
               self.prepare()|{'hosts':['YouTube.com']},self.prepare()|{'hosts':['nnmclub.to','nnmclub.to']},
               self.prepare()|{'hosts':[f'site{i}.example.com' for i in range(11)]},
               self.prepare()|{'dns_context':None}]
        for value in cases:
            with self.subTest(value=value):
                out=self.observe(value);self.assertIn('error',out);self.assertEqual(out['dns_calls'],0);self.assertEqual(out['probe_calls'],[])
        for raw in ['{"schema_version":1', '[]', 'x'*8193]:
            with self.subTest(raw_bytes=len(raw)):
                out=self.observe(None,raw=raw);self.assertIn('error',out);self.assertEqual(out['dns_calls'],0)

    def test_authority_drift_cancellation_and_deadline_refuse_before_network(self):
        mutations=["$j['id']=str_repeat('d',32);$s->write($j);",
                   "$j['custom_worker']['nonce']=str_repeat('d',32);$s->write($j);",
                   "$j['custom_worker']['payload_sha256']=str_repeat('d',64);$s->write($j);",
                   "$j['custom_worker']['deadline']=AsusUpdateStore::uptime()-1;$s->write($j);",
                   "$j['actuator']['ticks']='0';$s->write($j);",
                   "$j['state']='failed';$s->write($j);",
                   "$s->write(['id'=>str_repeat('d',32)],'actor-work.json');",
                   "$s->write(['id'=>str_repeat('d',32)],'actor-guard.json');",
                   "file_put_contents($s->path('cancel-'.$id),'');"]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                out=self.observe(self.prepare(),mutation=mutation);self.assertIn('error',out);self.assertEqual(out['dns_calls'],0);self.assertEqual(out['probe_calls'],[])

    def test_poisoned_dns_cannot_emit_a_partial_manifest(self):
        for answer in ["return ['8.8.8.8','127.0.0.1'];","return [];","return array_fill(0,17,'8.8.8.8');"]:
            with self.subTest(answer=answer):
                out=self.observe(self.prepare(),resolver=answer)
                self.assertIn('error',out);self.assertNotIn('result',out);self.assertEqual(out['probe_calls'],[])

    def test_duplicate_json_keys_cannot_hide_rejected_targets(self):
        raw='{"schema_version":1,"hosts":["127.0.0.1"],"hosts":["nnmclub.to"],"dns_context":"'+DNS+'"}'
        out=self.observe(None,raw=raw)
        self.assertEqual(out.get('error'),'invalid_request')
        self.assertEqual(out['dns_calls'],0);self.assertEqual(out['probe_calls'],[])

    def test_probe_reuses_the_pins_for_both_exact_tls_versions_without_dns(self):
        out=self.observe(self.pins(),stage='probe',resolver="throw new RuntimeException('unexpected_dns');")
        self.assertNotIn('error',out);self.assertEqual(out['dns_calls'],0)
        self.assertEqual(out['probe_calls'],[['nnmclub.to',['8.8.8.8'],'tls12',8],['nnmclub.to',['8.8.8.8'],'tls13',8]])
        self.assertEqual([x['tls']for x in out['result']['observations']],['tls12','tls13'])
        self.assertEqual([x['host']for x in out['result']['observations']],['nnmclub.to','nnmclub.to'])
        self.assertEqual(out['result']['fingerprint'],'php-openssl-pinned-https-v1')

    def test_whole_pin_manifest_is_checked_before_the_first_probe(self):
        base=self.pins()
        bad=[base|{'pins':[]},base|{'pins':base['pins']*2},base|{'pins':[{'host':'other.com','answer':['8.8.8.8'],'address':'8.8.8.8'}]},
             base|{'pins':[{'host':'nnmclub.to','answer':['127.0.0.1'],'address':'127.0.0.1'}]},
             base|{'pins':[{'host':'nnmclub.to','answer':['8.8.8.8'],'address':'1.1.1.1'}]}]
        for value in bad:
            with self.subTest(value=value):
                out=self.observe(value,stage='probe');self.assertIn('error',out);self.assertEqual(out['dns_calls'],0);self.assertEqual(out['probe_calls'],[])

    def test_json_objects_cannot_substitute_for_host_pin_or_answer_arrays(self):
        base=self.pins()
        cases=[('prepare',self.prepare()|{'hosts':{'0':'nnmclub.to'}}),
               ('probe',base|{'hosts':{'0':'nnmclub.to'}}),
               ('probe',base|{'pins':{'0':base['pins'][0]}}),
               ('probe',base|{'pins':[{'host':'nnmclub.to','answer':{'0':'8.8.8.8'},'address':'8.8.8.8'}]})]
        for stage,value in cases:
            with self.subTest(stage=stage,value=value):
                out=self.observe(value,stage=stage)
                self.assertIn('error',out)
                self.assertEqual(out['dns_calls'],0);self.assertEqual(out['probe_calls'],[])

    def test_real_cli_and_cgi_entry_refuse_http_activation(self):
        binaries=[PHP]
        cgi=os.environ.get('PHP_CGI_TEST_BINARY')
        if cgi:binaries.append(cgi)
        for binary in binaries:
            with self.subTest(binary=binary):
                env=os.environ|{'REQUEST_METHOD':'POST','REMOTE_ADDR':'127.0.0.1','SCRIPT_FILENAME':str(WORKER),'REDIRECT_STATUS':'200'}
                out=subprocess.run([binary,'-n','-d','register_argc_argv=1','-q','-f',str(WORKER),'--','prepare',ID,NONCE],input=encode(self.prepare()),text=True,capture_output=True,env=env,timeout=15)
                self.assertEqual(out.returncode,1,out.stderr+out.stdout)
                if binary!=PHP:
                    _,separator,body=out.stdout.partition('\n\n')
                    self.assertTrue(separator,'CGI headers must be separated from its body')
                else:body=out.stdout
                self.assertEqual(body,'');self.assertEqual(out.stderr,'')

    def test_real_cgi_reads_eof_document_without_cli_stdin_constant(self):
        cgi=os.environ.get('PHP_CGI_TEST_BINARY')
        if not cgi:self.skipTest('Configured actual CGI runtime required')
        out=self.observe(self.prepare(),php=cgi)
        self.assertNotIn('error',out);self.assertEqual(len(out['result']['pins']),2)

    def test_malformed_cli_arguments_refuse_without_waiting_for_stdin(self):
        binaries=[PHP]
        if os.environ.get('PHP_CGI_TEST_BINARY'):binaries.append(os.environ['PHP_CGI_TEST_BINARY'])
        for binary in binaries:
            with self.subTest(binary=binary):
                process=subprocess.Popen([binary,'-n','-d','register_argc_argv=1','-q','-f',str(WORKER),'--','unknown',ID,NONCE],
                                         stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                try:
                    try:code=process.wait(timeout=2)
                    except subprocess.TimeoutExpired:self.fail('Invalid CLI arguments waited for an EOF document')
                    self.assertEqual(code,2)
                finally:
                    if process.poll() is None:process.kill()
                    stdout,stderr=process.communicate(timeout=3)
                self.assertEqual(stdout,b'');self.assertEqual(stderr,b'')

    def test_five_hosts_produce_exactly_ten_independent_tls_observations(self):
        value=self.pins()
        value['hosts']=['a.com','b.com','c.com','d.com','e.com']
        value['pins']=[{'host':host,'answer':['8.8.8.8'],'address':'8.8.8.8'}for host in value['hosts']]
        out=self.observe(value,stage='probe')
        self.assertNotIn('error',out);self.assertEqual(out['dns_calls'],0)
        self.assertEqual([(x['host'],x['tls'])for x in out['result']['observations']],
                         [(host,tls)for host in ['a.com','b.com','c.com','d.com','e.com']for tls in ['tls12','tls13']])
        self.assertEqual(len(out['probe_calls']),10)
        # A 403 stays a response observation; it is not rewritten as site success.
        for row in out['result']['observations']:
            self.assertEqual(row['response']['http_status'],403)
            self.assertNotIn('success',row)

    def test_dead_actor_and_birth_identity_mismatch_never_start_network(self):
        for role in ['work','guard']:
            for operation in ['terminate','wrong-birth']:
                with self.subTest(role=role,operation=operation):
                    if operation=='terminate':
                        mutation="$a=$s->read('actor-"+role+".json')['identity'];$p=proc_open(['/bin/kill','-TERM',(string)$a['pid']],[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes);proc_close($p);usleep(30000);"
                    else:
                        mutation="$a=$s->read('actor-"+role+".json');$a['identity']['ticks']='0';$s->write($a,'actor-"+role+".json');"
                    out=self.observe(self.prepare(),mutation=mutation)
                    self.assertIn('error',out);self.assertEqual(out['dns_calls'],0);self.assertEqual(out['probe_calls'],[])

    def test_cancel_or_expiry_during_dns_does_not_release_partial_pins(self):
        changes=["file_put_contents($s->path('cancel-'.str_repeat('a',32)),'');",
                 "$j=$s->read();$j['custom_worker']['deadline']=AsusUpdateStore::uptime()-1;$s->write($j);"]
        for change in changes:
            with self.subTest(change=change):
                out=self.observe(self.prepare(),resolver=change+"return ['8.8.8.8'];")
                self.assertIn('error',out);self.assertNotIn('result',out)
                self.assertEqual(out['dns_calls'],1);self.assertEqual(out['probe_calls'],[])

    def test_malformed_response_or_cancellation_cannot_return_partial_observations(self):
        probes=["return null;","$r=AsusDpiSiteCheck::response('response');return $r;",
                "$r=AsusDpiSiteCheck::response('response');$r['http_status']=200;$r['bytes_read']=-1;return $r;",
                "$r=AsusDpiSiteCheck::response('response');$r['http_status']=200;$r['redirect']=str_repeat('x',2049);return $r;",
                "file_put_contents($s->path('cancel-'.str_repeat('a',32)),'');$r=AsusDpiSiteCheck::response('response');$r['http_status']=200;return $r;"]
        for probe in probes:
            with self.subTest(probe=probe):
                out=self.observe(self.pins(),stage='probe',probe=probe)
                self.assertIn('error',out);self.assertNotIn('result',out)
                self.assertEqual(out['dns_calls'],0);self.assertEqual(len(out['probe_calls']),1)
