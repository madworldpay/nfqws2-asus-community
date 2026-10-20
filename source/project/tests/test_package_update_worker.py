import json
import http.server
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import time
import threading
import unittest
from test_dpi_normalize import PHP, PUBLIC


class PackageUpdateLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.run=self.base/'run';self.run.mkdir(mode=0o700);self.log=self.base/'commands'
        self.core=self.base/'core';self.web=self.base/'web'
        q=shlex.quote
        self.core.write_text('#!/bin/sh\numask 077\nprintf "%s\\n" "$1" >> '+q(str(self.log))+'\ncase "$1" in\n'
          'stop) if [ -f '+q(str(self.base/'stop-fails'))+' ]; then exit 1; fi\n'
          'if [ -f '+q(str(self.run/'pid'))+' ]; then kill -TERM "$(cat '+q(str(self.run/'pid'))+')" 2>/dev/null || :; fi\n'
          'rm -f '+q(str(self.run/'pid'))+' '+q(str(self.run/'enabled'))+';;\n'
          'start) : > '+q(str(self.run/'enabled'))+'\n'
          'if [ ! -f '+q(str(self.base/'no-wan'))+' ]; then /bin/sleep 30 </dev/null >/dev/null 2>&1 & echo $! > '+q(str(self.run/'pid'))+'; fi;;\nesac\n')
        self.core.chmod(0o700);self.web.write_text('#!/bin/sh\nexit 0\n');self.web.chmod(0o700)
        self.options={'run':str(self.run),'engine':str(Path('/bin/sleep').resolve()),'core_init':str(self.core),'web_init':str(self.web),'owner':os.getuid()}
        self.children=[];self.identities=[];self.addCleanup(self.stop_children)
    def stop_children(self):
        for p in self.children:
            if p.poll() is None:p.terminate()
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for pid,start in self.identities:
            try:
                fields=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()
                if fields[19]==start and Path(f'/proc/{pid}/exe').resolve()==Path('/bin/sleep').resolve():os.kill(pid,signal.SIGTERM)
            except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    def running(self):
        p=subprocess.Popen(['/bin/sleep','30']);self.children.append(p)
        (self.run/'pid').write_text(str(p.pid));(self.run/'pid').chmod(0o600)
        (self.run/'enabled').touch(mode=0o600);return p
    def call(self,commands):
        code='''if(!is_file($argv[1].'/update-lifecycle.php')){echo json_encode(['error'=>'missing_lifecycle']);exit;}
        require $argv[1].'/update-lifecycle.php';$p=json_decode(stream_get_contents(STDIN),true);
        try{$s=new AsusUpdateLifecycle($p['options']);$out=[];$intent=null;foreach($p['commands'] as $c){$args=$c[1];foreach($args as &$a)if($a==='INTENT')$a=$intent;unset($a);$v=$s->{$c[0]}(...$args);if($c[0]==='intent')$intent=$v;$out[]=$v;}echo json_encode($out);
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps({'options':self.options,'commands':commands}),capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'')
        pidfile=self.run/'pid'
        if pidfile.is_file() and not pidfile.is_symlink():
            pid=int(pidfile.read_text())
            try:start=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19]
            except FileNotFoundError:pass
            else:self.identities.append((pid,start))
        return json.loads(r.stdout)
    def test_running_intent_stops_then_starts_exactly_once(self):
        self.running();r=self.call([['intent',[]],['stop',[]],['restore',['INTENT']]])
        self.assertIsInstance(r,list);self.assertEqual(r[0]['mode'],'running');self.assertEqual(r[-1],'running')
        self.assertEqual(self.log.read_text().splitlines(),['stop','start'])
    def test_stopped_intent_is_never_started_even_briefly(self):
        r=self.call([['intent',[]],['stop',[]],['restore',['INTENT']]])
        self.assertIsInstance(r,list);self.assertEqual(r[0]['mode'],'stopped');self.assertEqual(r[-1],'stopped');self.assertFalse(self.log.exists())
    def test_waiting_intent_returns_waiting_without_claiming_running(self):
        (self.run/'enabled').touch(mode=0o600);(self.base/'no-wan').touch()
        r=self.call([['intent',[]],['stop',[]],['restore',['INTENT']]])
        self.assertIsInstance(r,list);self.assertEqual(r[0]['mode'],'waiting_for_wan');self.assertEqual(r[-1],'waiting_for_wan')
        self.assertEqual(self.log.read_text().splitlines(),['stop','start'])
    def test_stop_failure_preserves_live_process_and_does_not_start(self):
        p=self.running();(self.base/'stop-fails').touch()
        self.assertEqual(self.call([['stop',[]]]),{'error':'core_stop_failed'});self.assertIsNone(p.poll());self.assertEqual(self.log.read_text().splitlines(),['stop'])
    def test_foreign_pid_and_symlink_do_not_kill_or_start_anything(self):
        (self.run/'pid').write_text(str(os.getpid()));(self.run/'pid').chmod(0o600)
        r=self.call([['intent',[]],['stop',[]]]);self.assertIsInstance(r,list);self.assertEqual(r[0]['mode'],'stopped');self.assertFalse(self.log.exists())
        (self.run/'pid').unlink();outside=self.base/'outside';outside.write_text('KEEP');(self.run/'pid').symlink_to(outside)
        self.assertEqual(self.call([['stop',[]]]),{'error':'invalid_state'});self.assertEqual(outside.read_text(),'KEEP')
    def test_web_health_works_in_minimal_php_without_filter_extension(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):self.send_response(200);self.end_headers()
            def log_message(self,*args):pass
        server=http.server.HTTPServer(('127.0.0.2',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join()))
        config=self.run/'lighttpd.conf';config.write_text('server.bind = "127.0.0.2"\n');config.chmod(0o600)
        code='''require $argv[1].'/update-worker.php';$s=new AsusUpdateStore($argv[2],(int)$argv[3]);
        $w=new AsusUpdateWorker($s,null,null,['owner'=>(int)$argv[3],'web_run'=>$argv[4],'health_port'=>(int)$argv[5]]);
        try{$r=new ReflectionMethod($w,'webHealth');echo json_encode(['health'=>$r->invoke($w)]);}catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        args=[PHP,'-n','-d','disable_functions=filter_var','-r',code,str(PUBLIC),str(self.base/'state'),str(os.getuid()),str(self.run),str(server.server_port)]
        r=subprocess.run(args,capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');self.assertEqual(json.loads(r.stdout),{'health':True})
        for address in ['127.0.0.256','127.0.00.2','localhost','127.0.0.2:80']:
            with self.subTest(address=address):
                config.write_text('server.bind = "'+address+'"\n')
                r=subprocess.run(args,capture_output=True,text=True,timeout=5)
                self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),{'error':'invalid_state'})


if __name__=='__main__':unittest.main()
