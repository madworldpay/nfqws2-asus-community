"""Real owned children: exec transitions, local backend loss, and scoped cleanup."""
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import test_technical_channel as technical

PHP=technical.PHP
PUBLIC=technical.PUBLIC


@unittest.skipUnless(PHP, 'native PHP fixture required')
class TechnicalChildTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.runtime=self.root/'run';self.runtime.mkdir(mode=0o700)
        self.processes=[];self.addCleanup(self.stop_children)
        self.config={'runtime':str(self.runtime),'journal':str(self.root/'journal.json'),'owner':os.getuid(),'temporary_parent':str(self.root),'ssh':str(self.root/'ssh')}
        c='''#include <unistd.h>
#include <stdio.h>
#include <sys/socket.h>
#include <netinet/in.h>
int main(int argc,char **argv){int s=socket(AF_INET,SOCK_STREAM,0),one=1;setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&one,sizeof(one));struct sockaddr_in a={.sin_family=AF_INET,.sin_addr.s_addr=htonl(INADDR_LOOPBACK),.sin_port=0};socklen_t n=sizeof(a);if(bind(s,(void*)&a,n)||listen(s,4)||getsockname(s,(void*)&a,&n))return 2;char p[4096];snprintf(p,sizeof(p),"%s.%ld.port",argv[0],(long)getpid());FILE *f=fopen(p,"w");if(!f)return 3;fprintf(f,"%d",ntohs(a.sin_port));fclose(f);const char *pid=__DEFAULT_PID__;int server=0;for(int i=1;i<argc;i++){if(!strcmp(argv[i],"-F"))server=1;if(!strcmp(argv[i],"-P")&&i+1<argc)pid=argv[++i];}if(server){f=fopen(pid,"w");if(!f)return 4;fprintf(f,"%ld",(long)getpid());fclose(f);}for(;;)pause();}
'''
        c=c.replace('#include <stdio.h>','#include <stdio.h>\n#include <string.h>').replace('__DEFAULT_PID__',json.dumps(str(self.root/'normal-ssh.pid')))
        compiled=subprocess.run(['cc','-x','c','-','-o',str(self.root/'child')],input=c,capture_output=True,text=True,timeout=10)
        self.assertEqual(compiled.returncode,0,compiled.stderr)
        for name in ['ssh','dropbear']:
            shutil.copyfile(self.root/'child',self.root/name);(self.root/name).chmod(0o755)

    def stop_children(self):
        for p in self.processes:
            if p.poll() is None:p.kill()
            p.wait(timeout=3)

    def call(self,code,**data):
        script="require $argv[1].'/technical-channel.php';$v=json_decode(stream_get_contents(STDIN),true);try{$result=(function($v){"+code+"})($v);echo json_encode(['ok'=>$result]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}"
        r=subprocess.run([PHP,'-n','-r',script,str(PUBLIC)],input=json.dumps(data),capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def identity(self,pid):return self.call('return AsusTechnicalProcess::identity($v["pid"]);',pid=pid)['ok']

    def start(self,name='ssh'):
        argv=[str(self.root/name),'30'];p=subprocess.Popen(argv);self.processes.append(p)
        return p,argv,self.identity(p.pid)

    def port(self,record,argv):
        path=Path(argv[0]+'.'+str(record['pid'])+'.port');deadline=time.monotonic()+2
        while not path.exists() and time.monotonic()<deadline:time.sleep(.005)
        self.assertTrue(path.exists(),'native fixture must own a real loopback listener')
        value=int(path.read_text())
        with socket.socket() as probe:
            probe.settimeout(.2);self.assertEqual(probe.connect_ex(('127.0.0.1',value)),0)
        return value

    def rebind(self,port):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);listener.bind(('127.0.0.1',port));listener.listen(1)

    def transition(self):
        gate=self.root/'exec-now';entry=self.root/'transition.php'
        if gate.exists():gate.unlink()
        entry.write_text('<?php while(!is_file($argv[1]))usleep(1000);pcntl_exec($argv[2],["30"]);exit(2);')
        p=subprocess.Popen([PHP,'-n',str(entry),str(gate),str(self.root/'ssh')]);self.processes.append(p)
        before=self.identity(p.pid);self.assertIsNotNone(before);gate.touch()
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            after=self.identity(p.pid)
            if after and after['exe']==str(self.root/'ssh'):break
            time.sleep(.01)
        self.assertEqual(after['exe'],str(self.root/'ssh'));self.assertNotEqual(before['exe'],after['exe'])
        self.assertEqual((before['pid'],before['starttime'],before['boot_id']),(after['pid'],after['starttime'],after['boot_id']))
        return p,[str(self.root/'ssh'),'30'],before

    def save(self,state):
        path=self.runtime/'state.json';path.write_text(json.dumps(state));path.chmod(0o600)

    def state(self,server,transport):
        return {'state':'connected','stage':'transport','session_id':'a'*32,'activation_id':'a'*32,
            'identity':self.identity(os.getpid()),'expires_at':int(time.time())+30,'uptime_deadline':1e12,
            'server_process':server[2],'transport':transport[2],
            'child_argv':{'server_process':server[1],'transport':transport[1]}}

    def status(self):return self.call('$c=new AsusTechnicalChannel($v["config"]);return $c->status();',config=self.config)

    def running(self,blocked=False,corrupt=False,terminate_spy=False):
        app=self.root/'app';app.mkdir()
        for path in PUBLIC.glob('*.php'):shutil.copyfile(path,app/path.name)
        home=self.root/'home';(home/'.ssh').mkdir(parents=True,mode=0o700);home.chmod(0o700)
        keys=home/'.ssh/authorized_keys';keys.write_text('owner-key\n');keys.chmod(0o640)
        technical.TechnicalChannelTests.setUpClass();signer=technical.TechnicalChannelTests()
        pem=self.root/'public.pem';pem.write_text(signer.pem);pem.chmod(0o600)
        self.config.update(public_key=str(pem),library=str(self.root/'library'))
        (self.root/'library').mkdir(mode=0o700)
        runtime=app/'technical-channel-runtime.php';code=runtime.read_text()
        left=code.index('    private function rootAccount(): array');right=code.index('    private function localServer(',left)
        code=code[:left]+'''    private function rootAccount(): array{return ['root',__HOME__];}
'''.replace('__HOME__',json.dumps(str(home)))+code[right:]
        left=code.index('    private function localServer(');right=code.index('    /** Called by a forced-command key.',left)
        code=code[:left]+'''    private function localServer(string $id):array{
            $args=[__SERVER__,'30'];$p=proc_open($args,[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes);usleep(100000);return [$p,12345,$args];}
'''.replace('__SERVER__',json.dumps(str(self.root/'dropbear')))+code[right:]
        if blocked:
            transition=self.root/'blocked-exec.php';transition.write_text('<?php while(!is_file($argv[1]))usleep(1000);pcntl_exec($argv[2],array_slice($argv,3));')
            code=code.replace('$p=@proc_open($args,',"$p=@proc_open(array_merge([PHP_BINARY,'-n',"+json.dumps(str(transition))+','+json.dumps(str(self.root/'release-exec'))+'],$args),',1)
        if corrupt:
            marker="$s['child_argv']['transport']=$args;"
            self.assertIn(marker,code)
            injected="file_put_contents("+json.dumps(str(self.root/'startup-proof.json'))+",json_encode($s));unlink($this->path('state.json'));symlink("+json.dumps(str(self.root/'unrelated'))+",$this->path('state.json'));throw new RuntimeException('unsafe_key_file');"
            code=code.replace(marker,marker+injected,1);(self.root/'unrelated').write_text('OWNER SENTINEL')
        if terminate_spy:code=code.replace('proc_terminate(','fixtureTerminate(')
        runtime.write_text(code)
        state={'state':'connecting','stage':'prepare','session_id':'a'*32,'activation_id':'a'*32,'identity':None,'transport':None,'started_at':int(time.time()),'expires_at':int(time.time())+30,'uptime_deadline':1e12}
        self.save(state);(self.runtime/'invitation').write_text(signer.link());(self.runtime/'invitation').chmod(0o600)
        spy=''
        if terminate_spy:
            spy='function fixtureTerminate($p,$signal){$s=proc_get_status($p);file_put_contents('+json.dumps(str(self.root/'terminate.jsonl'))+',json_encode($s)."\\n",FILE_APPEND);return $s["running"]?proc_terminate($p,$signal):false;}'
        driver=self.root/'runner.php';driver.write_text('<?php '+spy+' require '+json.dumps(str(app/'technical-channel.php'))+';$c=new AsusTechnicalChannel('+self.php_array_config()+');try{$c->run(str_repeat("a",32));}catch(Throwable $e){file_put_contents("php://stderr",$e->getMessage());exit(1);}')
        p=subprocess.Popen([PHP,'-n',str(driver)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);self.processes.append(p)
        deadline=time.monotonic()+3;registered=None
        while time.monotonic()<deadline:
            proof=self.root/'startup-proof.json'
            if corrupt and proof.exists():registered=json.loads(proof.read_text());break
            try:registered=json.loads((self.runtime/'state.json').read_text())
            except (OSError,ValueError):registered=None
            if registered and isinstance(registered.get('transport'),dict):break
            if p.poll() is not None:break
            time.sleep(.005)
        self.assertIsNotNone(registered,'actual run must register children')
        def cleanup_orphans():
            for role in ['transport','server_process']:
                record=registered.get(role)
                if not record:continue
                now=self.identity(record['pid'])
                if now and all(now[k]==record[k] for k in ['pid','starttime','boot_id']):os.kill(record['pid'],9)
        self.addCleanup(cleanup_orphans)
        return p,registered,keys

    def php_array_config(self):
        return 'json_decode('+json.dumps(json.dumps(self.config))+',true)'

    def test_exact_child_context_kills_after_exec_but_default_identity_stays_strict(self):
        p,argv,old=self.transition();unrelated,_,_=self.start('dropbear')
        self.call('AsusTechnicalProcess::kill($v["identity"]);return true;',identity=old)
        self.assertIsNone(p.poll(),'default kill must retain exact-executable identity policy')
        self.call('AsusTechnicalProcess::kill($v["identity"],$v["argv"],$v["owner"]);return true;',identity=old,argv=argv,owner=os.getuid())
        deadline=time.monotonic()+.6
        while p.poll() is None and time.monotonic()<deadline:time.sleep(.01)
        self.assertIsNotNone(p.poll(),'explicit exact child context must survive its legitimate PHP-to-executable transition')
        self.assertIsNone(unrelated.poll())

    def test_wrong_start_boot_uid_argv_and_reused_pid_never_kill(self):
        p,argv,old=self.transition();unrelated,_,_=self.start('dropbear')
        cases=[(old|{'starttime':str(int(old['starttime'])+1)},argv,os.getuid()),
               (old|{'boot_id':'wrong-boot'},argv,os.getuid()),(old,argv,os.getuid()+1),
               (old,[argv[0],'29'],os.getuid()),
               (old|{'pid':unrelated.pid,'starttime':str(int(old['starttime'])+1)},argv,os.getuid())]
        for identity,command,owner in cases:
            with self.subTest(identity=identity,argv=command,owner=owner):
                self.call('AsusTechnicalProcess::kill($v["identity"],$v["argv"],$v["owner"]);return true;',identity=identity,argv=command,owner=owner)
                self.assertIsNone(p.poll());self.assertIsNone(unrelated.poll())

    def test_registered_local_backend_exit_closes_only_its_transport(self):
        server=self.start('dropbear');transport=self.transition();unrelated,_,_=self.start('dropbear')
        port=self.port(transport[2],transport[1]);self.save(self.state(server,transport));server[0].terminate();server[0].wait(timeout=2)
        result=self.status();self.assertEqual(result['ok']['state'],'failed',result)
        self.assertEqual(result['ok']['code'],'connection_failed')
        deadline=time.monotonic()+.6
        while transport[0].poll() is None and time.monotonic()<deadline:time.sleep(.01)
        self.assertIsNotNone(transport[0].poll(),'a dead backend must not retain the owned outbound listener')
        self.rebind(port)
        self.assertIsNone(unrelated.poll())

    def test_partial_startup_without_registered_pair_is_not_adopted_or_torn_down(self):
        state={'state':'connecting','stage':'local_server','session_id':'a'*32,'activation_id':'a'*32,
            'identity':self.identity(os.getpid()),'expires_at':int(time.time())+30,'uptime_deadline':1e12}
        self.save(state);self.assertEqual(self.status()['ok']['state'],'connecting')
        self.assertEqual(json.loads((self.runtime/'state.json').read_text()),state)

    def test_malformed_new_context_cannot_fall_back_to_legacy_kill(self):
        server=self.start('dropbear');transport=self.start('ssh');state=self.state(server,transport)
        state['child_argv']['transport']='malformed';self.save(state)
        result=self.status();self.assertEqual(result['ok']['state'],'failed')
        self.assertIsNone(transport[0].poll(),'malformed explicit proof must not silently choose legacy cleanup')

    def test_stop_expiry_and_replacement_preserve_owned_scope(self):
        for action in ['stop','expiry','replacement']:
            with self.subTest(action=action):
                server=self.start('dropbear');transport=self.transition();state=self.state(server,transport)
                port=self.port(transport[2],transport[1])
                if action=='expiry':state['expires_at']=int(time.time())-1
                if action=='replacement':state['activation_id']='b'*32
                self.save(state)
                if action=='replacement':
                    result=self.call('$c=new AsusTechnicalChannel($v["config"]);$m=new ReflectionMethod($c,"clean");return $m->invoke($c,$v["old"],"failed","interrupted");',config=self.config,old=state|{'activation_id':'a'*32})
                    self.assertEqual(result['ok']['activation_id'],'b'*32)
                    self.assertIsNone(server[0].poll());self.assertIsNone(transport[0].poll())
                else:
                    result=self.call('$c=new AsusTechnicalChannel($v["config"]);return $c->{$v["action"]}();',config=self.config,action='stop' if action=='stop' else 'status')
                    self.assertEqual(result['ok']['state'],'stopped' if action=='stop' else 'expired')
                    deadline=time.monotonic()+.6
                    while (server[0].poll() is None or transport[0].poll() is None) and time.monotonic()<deadline:time.sleep(.01)
                    self.assertIsNotNone(server[0].poll());self.assertIsNotNone(transport[0].poll())
                    self.rebind(port)
                if (self.runtime/'state.json').exists():(self.runtime/'state.json').unlink()

    def test_existing_shell_guardian_recovers_after_worker_crash_and_exec(self):
        keys=self.root/'keys';keys.write_bytes(b'original-owner-key\n');keys.chmod(0o640)
        self.call('$j=new AsusTechnicalJournal($v["path"],$v["owner"]);$j->apply([["path"=>$v["keys"],"line"=>"owned-temporary-key"]]);return true;',path=self.config['journal'],owner=os.getuid(),keys=str(keys))
        (self.root/'config.json').write_text(json.dumps(self.config))
        transition=self.root/'child.php';transition.write_text('<?php while(!is_file($argv[1]))usleep(1000);pcntl_exec($argv[2],["30"]);exit(2);')
        worker=self.root/'worker.php';worker.write_text('''<?php
require '''+json.dumps(str(PUBLIC/'technical-channel.php'))+''';
$root=__DIR__;$config=json_decode(file_get_contents($root.'/config.json'),true);$mode=$argv[count($argv)-2];$id=$argv[count($argv)-1];
if($mode==='recover'){$c=new AsusTechnicalChannel($config);file_put_contents($root.'/guardian-result.json',json_encode($c->status()));exit(0);}
$state=['state'=>'connected','stage'=>'transport','session_id'=>$id,'activation_id'=>$id,'identity'=>AsusTechnicalProcess::identity(getmypid()),'expires_at'=>time()+30,'uptime_deadline'=>1e12,'child_argv'=>[]];$handles=[];
foreach(['server_process'=>'dropbear','transport'=>'ssh'] as $role=>$name){
    $command=[$root.'/'.$name,'30'];$gate=$root.'/'.$role.'-exec';
    $p=proc_open([PHP_BINARY,'-n',$root.'/child.php',$gate,$root.'/'.$name],[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes);
    $ps=proc_get_status($p);$state[$role]=AsusTechnicalProcess::identity($ps['pid']);$state['child_argv'][$role]=$command;$handles[]=$p;
    touch($gate);$until=microtime(true)+2;do{$live=AsusTechnicalProcess::identity($ps['pid']);if(($live['exe']??null)===$root.'/'.$name)break;usleep(1000);}while(microtime(true)<$until);
}
AsusTechnicalFiles::write($config['runtime'].'/state.json',json_encode($state),0600,$config['owner']);file_put_contents($root.'/ready.json',json_encode($state));while(true)usleep(100000);
''')
        guardian=self.root/'session.sh';source=(technical.ROOT/'asus/technical-channel/session.sh').read_text()
        source=source.replace('/opt/lib/nfqws2-asus/technical-channel/session.sh',str(guardian)).replace('/opt/lib/nfqws2-asus/technical-channel/worker.php',str(worker)).replace('/opt/bin/php-cgi',shlex.quote(str(PHP))+' -n')
        guardian.write_text(source);guardian.chmod(0o700)
        p=subprocess.Popen(['/bin/sh',str(guardian),'a'*32],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);self.processes.append(p)
        deadline=time.monotonic()+3
        while not (self.root/'ready.json').exists() and p.poll() is None and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue((self.root/'ready.json').exists(),'existing guardian must launch the fixture worker')
        state=json.loads((self.root/'ready.json').read_text())
        def cleanup_orphans():
            for role in ['transport','server_process','identity']:
                record=state[role];now=self.identity(record['pid'])
                if now and all(now[k]==record[k] for k in ['pid','starttime','boot_id']):os.kill(record['pid'],9)
        self.addCleanup(cleanup_orphans)
        ports=[]
        for role in ['server_process','transport']:
            self.assertNotEqual(state[role]['exe'],self.identity(state[role]['pid'])['exe']);ports.append(self.port(state[role],state['child_argv'][role]))
        os.kill(state['identity']['pid'],9);out,err=p.communicate(timeout=3)
        self.assertEqual(p.returncode,0,out+err)
        self.assertEqual(json.loads((self.root/'guardian-result.json').read_text())['state'],'failed')
        for role in ['server_process','transport']:self.assertIsNone(self.identity(state[role]['pid']),role+' survived the existing crash guardian')
        for port in ports:self.rebind(port)
        self.assertEqual(keys.read_bytes(),b'original-owner-key\n');self.assertEqual(keys.stat().st_mode&0o777,0o640)
        self.assertFalse(Path(self.config['journal']).exists())

    def test_actual_run_loop_closes_listener_when_local_backend_exits(self):
        p,state,keys=self.running();port=self.port(state['transport'],state['child_argv']['transport'])
        os.kill(state['server_process']['pid'],9);out,err=p.communicate(timeout=3)
        self.assertEqual(p.returncode,0,out+err)
        self.assertEqual(json.loads((self.runtime/'state.json').read_text())['code'],'connection_failed')
        self.rebind(port);self.assertEqual(keys.read_text(),'owner-key\n');self.assertFalse((self.runtime/'server.pid').exists())

    def test_final_resource_cleanup_never_signals_an_already_reaped_child(self):
        p,state,_=self.running(terminate_spy=True)
        os.kill(state['server_process']['pid'],9)
        p.communicate(timeout=4);self.assertEqual(p.returncode,0)
        log=self.root/'terminate.jsonl'
        calls=[json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        self.assertFalse(any(not call['running'] for call in calls),'a reaped proc handle can address a reused unrelated PID')

    def test_bounded_exec_registration_serializes_concurrent_status(self):
        p,state,keys=self.running(blocked=True)
        script="require $argv[1].'/technical-channel.php';$c=new AsusTechnicalChannel(json_decode($argv[2],true));echo json_encode($c->status());"
        status=subprocess.Popen([PHP,'-n','-r',script,str(self.root/'app'),json.dumps(self.config)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);self.processes.append(status)
        time.sleep(.05);self.assertIsNone(status.poll(),'status must wait for bounded child adoption under the runtime lock')
        (self.root/'release-exec').touch();out,err=status.communicate(timeout=2)
        self.assertEqual(err,'');self.assertEqual(json.loads(out)['state'],'connecting')
        self.assertIsNone(p.poll())
        self.call('$c=new AsusTechnicalChannel($v["config"]);return $c->stop();',config=self.config);p.communicate(timeout=3)

    def test_startup_cleanup_failure_still_closes_owned_resources(self):
        p,state,keys=self.running(corrupt=True);out,err=p.communicate(timeout=3)
        self.assertNotEqual(p.returncode,0,out+err)
        self.assertEqual((self.root/'unrelated').read_text(),'OWNER SENTINEL')
        for role in ['transport','server_process']:self.assertIsNone(self.identity(state[role]['pid']),role+' leaked after clean() failed')

    def test_unadopted_child_times_out_without_persisting_a_session(self):
        p,state,keys=self.running(blocked=True);started=time.monotonic();out,err=p.communicate(timeout=3)
        self.assertLess(time.monotonic()-started,2);self.assertNotEqual(p.returncode,0,out+err)
        self.assertEqual(json.loads((self.runtime/'state.json').read_text())['code'],'launch_failed')
        for role in ['transport','server_process']:self.assertIsNone(self.identity(state[role]['pid']))
        self.assertEqual(keys.read_text(),'owner-key\n');self.assertFalse((self.runtime/'server.pid').exists())

    def test_removed_operator_key_is_not_reinserted_while_worker_is_live(self):
        p,state,keys=self.running();keys.write_text('owner-key\n');keys.chmod(0o640)
        result=self.status();self.assertEqual(result['ok']['state'],'connecting')
        self.assertEqual(keys.read_text(),'owner-key\n');self.assertEqual(result['ok']['expires_at'],state['expires_at'])
        self.call('$c=new AsusTechnicalChannel($v["config"]);return $c->stop();',config=self.config);p.communicate(timeout=3)
        self.assertEqual(keys.read_text(),'owner-key\n')

    def test_preexisting_unknown_private_pidfile_is_not_overwritten(self):
        pidfile=self.runtime/'server.pid';pidfile.write_text('OWNER PRIVATE SENTINEL');pidfile.chmod(0o600)
        p,state,keys=self.running();out,err=p.communicate(timeout=3)
        self.assertNotEqual(p.returncode,0,out+err);self.assertEqual(pidfile.read_text(),'OWNER PRIVATE SENTINEL');self.assertEqual(keys.read_text(),'owner-key\n')

    def test_local_server_uses_private_pidfile_without_clobbering_normal_ssh(self):
        app=self.root/'pid-app';app.mkdir()
        for path in PUBLIC.glob('*.php'):shutil.copyfile(path,app/path.name)
        proc=self.root/'proc/999';proc.mkdir(parents=True)
        (proc/'comm').write_text('dropbear\n');(proc/'exe').symlink_to(self.root/'dropbear')
        key=self.root/'hostkey';key.write_bytes(b'private fixture hostkey');key.chmod(0o600)
        (proc/'cmdline').write_bytes(b'dropbear\0-r\0'+str(key).encode()+b'\0')
        runtime=app/'technical-channel-runtime.php';code=runtime.read_text().replace("glob('/proc/[0-9]*/comm')","glob("+json.dumps(str(self.root/'proc/[0-9]*/comm'))+")")
        code=code.replace("readlink('/proc/'.$pid.'/exe')","readlink("+json.dumps(str(self.root/'proc'))+".'/'.$pid.'/exe')").replace("file_get_contents('/proc/'.$pid.'/cmdline')","file_get_contents("+json.dumps(str(self.root/'proc'))+".'/'.$pid.'/cmdline')")
        runtime.write_text(code.replace("$st['uid']!==0","$st['uid']!=="+str(os.getuid())))
        sentinel=self.root/'normal-ssh.pid';sentinel.write_text('OWNER NORMAL SSH PID');sentinel.chmod(0o640)
        pidfile=self.runtime/'server.pid';pidfile.write_bytes(b'');pidfile.chmod(0o600)
        script="require $argv[1].'/technical-channel.php';$c=new AsusTechnicalChannel(json_decode($argv[2],true));$m=new ReflectionMethod($c,'localServer');[$p,$port,$args]=$m->invoke($c,str_repeat('a',32));usleep(100000);$ps=proc_get_status($p);$i=AsusTechnicalProcess::identity($ps['pid']);AsusTechnicalProcess::kill($i);proc_close($p);echo json_encode(['pid'=>$ps['pid'],'args'=>$args]);"
        p=subprocess.run([PHP,'-n','-r',script,str(app),json.dumps(self.config)],capture_output=True,text=True,timeout=3)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        answer=json.loads(p.stdout);self.assertEqual(sentinel.read_text(),'OWNER NORMAL SSH PID')
        self.assertIn('-P',answer['args']);at=answer['args'].index('-P');self.assertEqual(answer['args'][at+1],str(pidfile));self.assertEqual(pidfile.read_text(),str(answer['pid']))

    def test_pidfile_replacement_is_never_unlinked_by_owned_cleanup(self):
        path=self.runtime/'server.pid';path.write_bytes(b'');path.chmod(0o600);s=path.stat()
        state={'state':'connecting','stage':'prepare','session_id':'a'*32,'activation_id':'a'*32,'server_pidfile':{'dev':s.st_dev,'ino':s.st_ino}}
        self.save(state)
        with path.open('rb'):
            path.unlink();path.write_text('OWNER REPLACEMENT');path.chmod(0o600)
            result=self.call('$c=new AsusTechnicalChannel($v["config"]);$m=new ReflectionMethod($c,"clean");return $m->invoke($c,$v["state"],"stopped");',config=self.config,state=state)
        self.assertEqual(result,{'error':'unsafe_key_file'});self.assertEqual(path.read_text(),'OWNER REPLACEMENT')


if __name__=='__main__':unittest.main()
