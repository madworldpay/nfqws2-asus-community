"""Real broker admission and package shutdown, without router services."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import shutil
import test_dpi_terminal as native
from test_dpi_normalize import PHP, PUBLIC

CGI=os.environ.get('DPI_TERMINAL_CGI_TEST_BINARY')


class DpiTerminalLifecycleTests(unittest.TestCase):
    setUpClass=classmethod(native.DpiTerminalTests.setUpClass.__func__)
    tearDownClass=classmethod(native.DpiTerminalTests.tearDownClass.__func__)
    setUp=native.DpiTerminalTests.setUp
    stop=native.DpiTerminalTests.stop
    launch=native.DpiTerminalTests.launch
    request=native.DpiTerminalTests.request
    poll_until=native.DpiTerminalTests.poll_until
    def lifecycle(self, code):
        self.assertTrue((PUBLIC/'dpi-terminal-lifecycle.php').is_file(),
                        'package lifecycle must stop the actual broker')
        source = '''require $argv[1].'/dpi-terminal-lifecycle.php';
        try {$gate=new AsusDpiTerminalLifecycle($argv[2],(int)$argv[3]);'''+code+'''
        }catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        result=subprocess.run([PHP,'-n','-r',source,str(PUBLIC),str(self.run),str(os.getuid())],
                              capture_output=True,text=True,timeout=8)
        self.assertEqual((result.returncode,result.stderr),(0,''),result.stdout)
        return json.loads(result.stdout)

    def test_package_shutdown_stops_broker_and_descendants(self):
        self.launch();self.poll_until(b'CWD=');self.request(b'I 1\nd')
        _,_,_,out=self.poll_until(b'CHILD=');child=int(out.split(b'CHILD=')[1].split()[0])
        self.assertEqual(self.lifecycle("$gate->stop();echo json_encode('stopped');"),'stopped')
        self.assertFalse((self.run/'control.sock').exists())
        self.assertTrue((self.run/'status').read_text().startswith('stopped '))
        status=Path(f'/proc/{child}/stat')
        if status.exists():self.assertEqual(status.read_text().split(') ')[1][0],'Z')
        self.assertEqual(self.lifecycle("$gate->stop();echo json_encode('stopped');"),'stopped')

    def test_running_terminal_rejects_install_before_reserving_job(self):
        self.launch();self.poll_until(b'CWD=')
        code='''require $argv[1].'/dpi-jobs.php';
        $store=new AsusDpiStore(dirname($argv[2]).'/jobs',(int)$argv[3]);
        $jobs=new AsusDpiJobs($store,['terminal_gate'=>$gate,'available'=>fn()=>['available'=>true],
          'launch'=>function(){throw new RuntimeException('UNEXPECTED_LAUNCH');}]);
        try{$jobs->startInstall('11111111-1111-4111-8111-111111111111',true);}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage(),'active'=>$store->status()['active']]);}'''
        self.assertEqual(self.lifecycle(code),{'error':'busy','active':None})

    def test_shutdown_rejects_foreign_runtime_without_touching_files(self):
        self.run.chmod(0o755)
        self.assertEqual(self.lifecycle("$gate->stop();echo json_encode('stopped');"),{'error':'invalid_state'})
        self.assertEqual(self.run.stat().st_mode&0o777,0o755)

    def test_update_stops_terminal_before_stopping_web_service(self):
        self.launch();self.poll_until(b'CWD=')
        init=Path(self.tmp.name)/'web-init'
        init.write_text('#!/bin/sh\n[ ! -S '+str(self.run/'control.sock')+' ]\n')
        init.chmod(0o755)
        code='''require $argv[1].'/update-lifecycle.php';
        $l=new AsusUpdateLifecycle(['owner'=>(int)$argv[3],'terminal_root'=>$argv[2],
           'web_init'=>dirname($argv[2]).'/web-init']);$l->webStop();echo json_encode('stopped');'''
        self.assertEqual(self.lifecycle(code),'stopped')
        self.assertFalse((self.run/'control.sock').exists())

    def test_idle_admission_and_shutdown_share_terminal_control_lock(self):
        import fcntl
        lock=self.run/'control.lock';lock.touch(mode=0o600)
        with lock.open('r+') as held:
            fcntl.flock(held,fcntl.LOCK_EX)
            self.assertEqual(self.lifecycle("echo json_encode($gate->idle(fn()=>'entered'));"),{'error':'busy'})
            self.assertEqual(self.lifecycle("$gate->stop();echo json_encode('stopped');"),{'error':'busy'})
        self.assertEqual(self.lifecycle("echo json_encode($gate->idle(fn()=>'entered'));"),'entered')


@unittest.skipUnless(CGI,'Requires a real PHP-CGI binary via DPI_TERMINAL_CGI_TEST_BINARY')
class DpiTerminalCgiLifecycleTests(unittest.TestCase):
    setUpClass=classmethod(native.DpiTerminalTests.setUpClass.__func__)
    tearDownClass=classmethod(native.DpiTerminalTests.tearDownClass.__func__)

    def test_cgi_cli_dispatch_stops_broker_but_rejects_http_nonroot_and_extra_arguments(self):
        with tempfile.TemporaryDirectory(prefix='dpi-cgi-lifecycle-') as td:
            base=Path(td);run=base/'runtime';run.mkdir(mode=0o700)
            program=base/'program';program.mkdir(mode=0o700)
            detector=program/'detector';shutil.copyfile(self.detector,detector);detector.chmod(0o755)
            helper=base/'broker';shutil.copyfile(native.ROOT/'asus/dpi/bin/dpi-terminal-x86_64',helper);helper.chmod(0o755)
            controller=base/'lifecycle.php'
            source=(PUBLIC/'dpi-terminal-lifecycle.php').read_text()
            boundary="$this->root=$root??'/tmp/nfqws2-dpi-terminal';"
            self.assertEqual(source.count(boundary),1)
            controller.write_text(source.replace(boundary,"$this->root=$root??'"+str(run)+"';"))
            included=base/'included.php';included.write_text("<?php require __DIR__.'/lifecycle.php'; echo 'INCLUDED';")
            probe=base/'probe.php';probe.write_text("<?php echo json_encode([PHP_SAPI,$_SERVER['SCRIPT_FILENAME']??null,$argv[0]??null]);")
            command=[CGI,'-n','-d','register_argc_argv=1','-q','-f']
            observed=subprocess.run(command+[str(probe)],capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(observed.stdout),['cgi-fcgi',None,str(probe)],'Regression requires actual CGI without SCRIPT_FILENAME')
            rejected=subprocess.run(command+[str(controller),'--','stop'],capture_output=True,timeout=5)
            if os.geteuid()!=0:self.assertEqual(rejected.returncode,1,'Non-root CGI must not enter the operator stop path')
            subprocess.run(['sudo','-n','chown','-R','root:root',str(base)],check=True)
            try:
                started=subprocess.run(['sudo','-n',str(helper),str(run),str(detector),str(program),'100','30','en'],capture_output=True,timeout=5)
                self.assertEqual(started.returncode,0,started.stderr)
                root=['sudo','-n']+command
                for args in [[],['--','stop','extra'],['--','other']]:
                    result=subprocess.run(root+[str(controller),*args],capture_output=True,timeout=5)
                    self.assertEqual(result.returncode,2,'Only the exact stop argument is allowed')
                result=subprocess.run(['sudo','-n','env','REQUEST_METHOD=POST','SCRIPT_FILENAME='+str(controller),CGI,'-n','-d','cgi.force_redirect=0','-d','register_argc_argv=1','-q','-f',str(controller),'--','stop'],capture_output=True,timeout=5)
                self.assertEqual(result.returncode,1,('HTTP CGI must never stop the operator broker',result.stdout,result.stderr))
                result=subprocess.run(root+[str(included),'--','stop'],capture_output=True,timeout=5)
                self.assertEqual((result.returncode,result.stdout),(0,b'INCLUDED'),'Including the module must not invoke its CLI entrypoint')
                self.assertEqual(subprocess.check_output(['sudo','-n','test','-S',str(run/'control.sock')]),b'')
                stopped=subprocess.run(root+[str(controller),'--','stop'],capture_output=True,timeout=8)
                self.assertEqual(stopped.returncode,0,stopped.stderr)
                self.assertTrue(subprocess.check_output(['sudo','-n','cat',str(run/'status')]).startswith(b'stopped '))
                self.assertEqual(subprocess.run(['sudo','-n','test','-S',str(run/'control.sock')]).returncode,1)
            finally:
                # Clean only this root-owned test fixture, including on a red run.
                code="require $argv[1];(new AsusDpiTerminalLifecycle($argv[2]))->stop();"
                subprocess.run(['sudo','-n',PHP,'-n','-r',code,str(controller),str(run)],capture_output=True,timeout=8)
                subprocess.run(['sudo','-n','chown','-R',f'{os.getuid()}:{os.getgid()}',str(base)],check=True)
