"""Parent protocol/state contracts use the real registered stdin transport."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from test_dpi_normalize import PHP, PUBLIC

ID='a'*32
DNS='c'*64

class CustomSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((PUBLIC/'strategy-picker-custom-supervisor.php').is_file(),
                        'Custom parent supervision is not implemented')

    def observe(self,body='',context='',output='',slow=False,checkpoint='',leaf_response=''):
        holders=[]
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory)
            try:
                for role in ['work','guard']:
                    p=subprocess.Popen([PHP,'-n','-r','usleep(20000000);',
                        str(PUBLIC/'strategy-picker-runtime.php'),'--',role,ID],
                        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                    holders.append(p)
                    for _ in range(100):
                        args=Path(f'/proc/{p.pid}/cmdline').read_bytes().rstrip(b'\0').split(b'\0')
                        if args[-4:]==[os.fsencode(PUBLIC/'strategy-picker-runtime.php'),b'--',role.encode(),ID.encode()]:break
                        time.sleep(.005)
                    else:self.fail('Actor did not exec')
                (root/'leaf.php').write_text('''<?php
require $argv[1].'/strategy-picker-custom-worker.php';
$s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);
[$stage,$id,$nonce]=array_slice($argv,-3);
$deps=['resolve'=>static function($host)use($argv){
 file_put_contents($argv[2].'/dns',"called\\n",FILE_APPEND);'''+('usleep(4000000);'if slow else '')+'''
 return ['8.8.8.8'];},'probe'=>static function($host,$answer,$tls,$seconds)use($argv){
 file_put_contents($argv[2].'/probes',json_encode([$host,$answer,$tls,$seconds])."\\n",FILE_APPEND);
 $r=AsusDpiSiteCheck::response('response');$r['http_status']=403;'''+leaf_response+'''return $r;}];
try{$input=NfqwsStrategyPickerCustomWorker::readInput(fopen('php://stdin','rb'));
 echo json_encode((new NfqwsStrategyPickerCustomWorker($s,$deps))->execute($stage,$id,$nonce,$input));}
catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);exit(2);}
''')
                parent=root/'parent.php'
                parent.write_text('''<?php umask(0077);
require $argv[1].'/strategy-picker-custom-supervisor.php';
$root=$argv[2];$uid=(int)$argv[3];$php=$argv[4];
$s=new NfqwsStrategyPickerState($root.'/picker',$uid,$root.'/profile-config');$id=str_repeat('a',32);
$s->write(['id'=>$id,'state'=>'running','phase'=>'discovering','deadline'=>AsusUpdateStore::uptime()+120,'actuator'=>null]);
foreach(['work'=>(int)$argv[5],'guard'=>(int)$argv[6]]as $role=>$pid)
 $s->write(['id'=>$id,'identity'=>NfqwsStrategyPickerRuntime::identity($pid)],'actor-'.$role.'.json');
$lock=$s->lock();$runtime=new NfqwsStrategyPickerRuntime($s,new NfqwsStrategyPickerConfig($s,$root.'/nfqws2.conf',$uid));
$dnsCalls=0;$transports=[];$dnsValue=str_repeat('c',64);
$dns=static function()use(&$dnsCalls,&$dnsValue,$s){$dnsCalls++;'''+context+'''
 return ['schema_version'=>1,'state'=>'known','sha256'=>$dnsValue];};
$check=static function()use($s,$root,$id){'''+checkpoint+'''
 $j=$s->read();if(($j['id']??null)!==$id||$j['state']!=='running')throw new RuntimeException('stale_state');
 if(file_exists($s->path('cancel-'.$id)))throw new RuntimeException('cancelled');
 if(AsusUpdateStore::uptime()>=$j['deadline'])throw new RuntimeException('timed_out');
 foreach(['work','guard']as $role){$a=$s->read('actor-'.$role.'.json');
  if(($a['id']??null)!==$id||!NfqwsStrategyPickerRuntime::sameActor($a['identity']??null))throw new RuntimeException('guard_lost');}};
$transport=static function($args,$seconds,$input,$check)use($s,$root,$uid,$php,$runtime,&$transports){
 $j=$s->read();$transports[]=['argv'=>$args,'seconds'=>$seconds,'descriptor'=>$j['custom_worker']??null,'payload'=>$input];
 $actual=[$php,'-n','-f',$root.'/leaf.php','--',__PUBLIC__,$root,(string)$uid,...array_slice($args,-5)];
 $v=(new ReflectionMethod($runtime,'actuator'))->invoke($runtime,$actual,$seconds,$input,$check);
 $transports[count($transports)-1]['child_result']=$v;
 '''+output+'''return $v;};
$sup=new NfqwsStrategyPickerCustomSupervisor($s,$check,$transport,$dns);
$out=[];try{'''+(body or '''$out['manifest']=$sup->prepare(['nnmclub.to','rutor.info']);
$out['first']=$sup->probe();$out['second']=$sup->probe();''')+'''
}catch(Throwable $e){$out['error']=$e->getMessage();}
$out['state']=$s->read();$out['transports']=$transports;$out['dns_context_calls']=$dnsCalls;
echo json_encode($out);flock($lock,LOCK_UN);fclose($lock);
'''.replace('__PUBLIC__',repr(str(PUBLIC))))
                # The replacement covers the whole generated document.
                parent.write_text(parent.read_text().replace('__PUBLIC__',repr(str(PUBLIC))))
                started=time.monotonic()
                result=subprocess.run([PHP,'-n','-f',str(parent),'--',str(PUBLIC),directory,
                    str(os.getuid()),PHP,str(holders[0].pid),str(holders[1].pid)],
                    capture_output=True,text=True,timeout=12)
                self.assertEqual(result.returncode,0,result.stderr+result.stdout)
                self.assertEqual(result.stderr,'')
                out=json.loads(result.stdout)
                out['dns_calls']=(root/'dns').read_text().count('called')if(root/'dns').exists()else 0
                out['probe_calls']=[json.loads(x)for x in(root/'probes').read_text().splitlines()]if(root/'probes').exists()else []
                out['elapsed']=time.monotonic()-started
                out['holders_alive']=all(p.poll()is None for p in holders)
                return out
            finally:
                for p in holders:
                    if p.poll()is None:p.terminate()
                    p.communicate(timeout=3)

    def manifest(self):
        return {'schema_version':1,'hosts':['nnmclub.to','rutor.info'],'dns_context':DNS,
            'pins':[{'host':h,'answer':['8.8.8.8'],'address':'8.8.8.8'}for h in ['nnmclub.to','rutor.info']],
            'policy':'uts46-533d68c-nfc-ebd57cc-std3-bidi-contextj-nontransitional-v1',
            'fingerprint':'php-openssl-pinned-https-v1'}

    def test_integral_and_fractional_deadlines_keep_exact_persisted_descriptor_authority(self):
        with tempfile.TemporaryDirectory()as directory:
            code='''umask(0077);require $argv[1].'/strategy-picker-custom-supervisor.php';
            $s=new NfqwsStrategyPickerState($argv[2].'/picker',(int)$argv[3]);$out=[];
            foreach([228162.0,228162.25]as $deadline){
              $d=(new ReflectionMethod(NfqwsStrategyPickerCustomSupervisor::class,'descriptor'))->invoke(
                null,'prepare',str_repeat('b',32),'complete-input',$deadline);
              $s->write(['custom_worker'=>$d]);$stored=$s->read()['custom_worker'];
              $bad=$stored;$bad['deadline']++;
              $out[]=['same'=>$stored===$d,'changed_same'=>$bad===$d,'payload'=>$d['payload_sha256']];}
            echo json_encode($out);'''
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),directory,str(os.getuid())],capture_output=True,text=True,timeout=5)
            self.assertEqual(r.returncode,0,r.stderr+r.stdout)
            self.assertEqual(json.loads(r.stdout),[{'same':True,'changed_same':False,
                'payload':hashlib.sha256(b'complete-input').hexdigest()}]*2)

    def test_prepare_and_repeated_probes_bind_one_manifest_and_registered_descriptors(self):
        out=self.observe();self.assertNotIn('error',out)
        self.assertEqual(out['manifest'],self.manifest());self.assertEqual(out['state']['custom_manifest'],self.manifest())
        expected=hashlib.sha256(json.dumps(self.manifest(),separators=(',',':')).encode()).hexdigest()
        self.assertEqual(out['state']['custom_manifest_sha256'],expected)
        self.assertEqual(out['first'].get('manifest_sha256'),expected)
        self.assertEqual(out['second'].get('manifest_sha256'),expected)
        self.assertEqual(out['dns_calls'],2);self.assertEqual(len(out['probe_calls']),8)
        self.assertIsNone(out['state'].get('custom_worker'));self.assertIsNone(out['state']['actuator'])
        for n,run in enumerate(out['transports']):
            stage='prepare'if n==0 else'probe';d=run['descriptor']
            self.assertEqual(d['stage'],stage);self.assertEqual(d['nonce'],run['argv'][-1])
            self.assertEqual(d['payload_sha256'],hashlib.sha256(run['payload'].encode()).hexdigest())
            self.assertEqual(run['argv'][-5:-1],[str(PUBLIC/'strategy-picker-custom-worker.php'),'--',stage,ID])
            self.assertNotIn('nnmclub.to',run['argv']);self.assertLessEqual(run['seconds'],90)
        self.assertTrue(out['holders_alive'])

    def test_invalid_targets_or_unknown_dns_never_launch_a_child(self):
        for hosts in [[],['YouTube.com'],['a.com']*2,[f'site{i}.example.com' for i in range(11)]]:
            with self.subTest(hosts=hosts):
                out=self.observe('$sup->prepare('+json.dumps(hosts)+');')
                self.assertIn('error',out);self.assertEqual(out['transports'],[]);self.assertEqual(out['dns_calls'],0)
        out=self.observe(context="return ['schema_version'=>1,'state'=>'unknown','sha256'=>null];")
        self.assertEqual(out['error'],'dns_context_unknown');self.assertEqual(out['transports'],[])

    def test_context_change_during_prepare_does_not_commit_pins(self):
        out=self.observe(context="if($dnsCalls===2)$dnsValue=str_repeat('d',64);")
        self.assertEqual(out['error'],'dns_context_changed');self.assertNotIn('custom_manifest',out['state'])
        self.assertIsNone(out['state'].get('custom_worker'));self.assertEqual(out['probe_calls'],[])

    def test_immutable_pin_tampering_or_dns_change_refuses_probe(self):
        for mutation in ["$j=$s->read();$j['custom_manifest']['pins'][0]['address']='1.1.1.1';$s->write($j);",
                         "$dnsValue=str_repeat('d',64);"]:
            with self.subTest(mutation=mutation):
                out=self.observe("$sup->prepare(['nnmclub.to','rutor.info']);"+mutation+'$sup->probe();')
                self.assertIn(out['error'],['stale_state','dns_context_changed']);self.assertEqual(out['probe_calls'],[])
                self.assertEqual(len(out['transports']),1)

    def test_malformed_prepare_results_never_become_a_persistent_manifest(self):
        for transform in ["$v['output']='[]';","$v['output']='{';",
            "$a=json_decode($v['output'],true);$a['pins'][0]['answer'][]='127.0.0.1';$v['output']=json_encode($a);",
            "$a=json_decode($v['output'],true);$a['extra']='ignored?';$v['output']=json_encode($a);"]:
            with self.subTest(transform=transform):
                out=self.observe(output=transform)
                self.assertEqual(out['error'],'incomparable_result');self.assertNotIn('custom_manifest',out['state'])
                self.assertIsNone(out['state'].get('custom_worker'))

    def test_duplicate_missing_extra_and_wrong_probe_rows_are_rejected(self):
        for transform in ["$a['observations'][1]=$a['observations'][0];",'array_pop($a[\'observations\']);',
                          "$a['observations'][]=$a['observations'][0];","$a['observations'][0]['tls']='quic';",
                          "$a['observations'][0]['response']['http_status']='200';",
                          "$a['observations']=(object)$a['observations'];"]:
            with self.subTest(transform=transform):
                change="if($args[count($args)-3]==='probe'){$a=json_decode($v['output'],true);"+transform+"$v['output']=json_encode($a);}"
                out=self.observe(output=change)
                self.assertEqual(out['error'],'incomparable_result');self.assertNotIn('first',out)
                self.assertIsNone(out['state'].get('custom_worker'))

    def test_foreign_job_or_descriptor_is_not_overwritten_by_cleanup(self):
        for change in ["$j['id']=str_repeat('e',32);","$j['custom_worker']=['nonce'=>'foreign'];"]:
            with self.subTest(change=change):
                out=self.observe(output='$j=$s->read();'+change+"$s->write($j);")
                self.assertEqual(out['error'],'stale_state');self.assertNotIn('custom_manifest',out['state'])
                if 'id' in change:self.assertEqual(out['state']['id'],'e'*32)
                else:self.assertEqual(out['state']['custom_worker'],{'nonce':'foreign'})

    def test_duplicate_json_members_at_root_and_in_pins_never_become_a_manifest(self):
        replacements=[('"schema_version":1','"schema_version":0,"schema_version":1'),
                      ('"answer":["8.8.8.8"]','"answer":["127.0.0.1"],"answer":["8.8.8.8"]'),
                      ('"schema_version":1',r'"schema_version":0,"\u0073chema_version":1')]
        for old,new in replacements:
            with self.subTest(new=new):
                change="$v['output']=str_replace("+repr(old)+','+repr(new)+",$v['output']);"
                out=self.observe(output=change)
                self.assertEqual(out.get('error'),'incomparable_result')
                self.assertNotIn('custom_manifest',out['state']);self.assertEqual(out['probe_calls'],[])

    def test_post_probe_context_conflict_preserves_foreign_control_and_refuses_result(self):
        for when in [2,4]:
            for field,value in [('custom_worker',"['nonce'=>'foreign']"),('actuator',"['foreign'=>true]")]:
                with self.subTest(when=when,field=field):
                    change="if($dnsCalls==="+str(when)+"){$j=$s->read();$j["+repr(field)+"]="+value+";$s->write($j);}"
                    out=self.observe(body="$sup->prepare(['nnmclub.to','rutor.info']);$out['first']=$sup->probe();",context=change)
                    self.assertEqual(out.get('error'),'stale_state');self.assertNotIn('first',out)
                    expected={'nonce':'foreign'}if field=='custom_worker'else{'foreign':True}
                    self.assertEqual(out['state'][field],expected)
                    if when==2:self.assertNotIn('custom_manifest',out['state'])

    def test_cancel_and_hard_deadline_reap_the_owned_leaf_and_clear_the_descriptor(self):
        cases=[("if(file_exists($root.'/dns'))throw new RuntimeException('cancelled');",'', 'cancelled'),
               ('',"$j=$s->read();$j['deadline']=AsusUpdateStore::uptime()+1.5;$s->write($j);",'timed_out')]
        for check,before,want in cases:
            with self.subTest(want=want):
                out=self.observe(body=before+"$sup->prepare(['nnmclub.to','rutor.info']);",slow=True,checkpoint=check)
                self.assertEqual(out['error'],want);self.assertLess(out['elapsed'],3.5)
                self.assertIsNone(out['state']['actuator']);self.assertIsNone(out['state'].get('custom_worker'))
                self.assertTrue(out['holders_alive']);self.assertNotIn('custom_manifest',out['state'])

if __name__=='__main__':unittest.main()
