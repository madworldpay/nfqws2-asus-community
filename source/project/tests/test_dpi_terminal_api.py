"""The PHP boundary drives the real broker; paths are trusted constructor inputs."""
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
import test_dpi_terminal as native

ROOT = native.ROOT

PHP = os.environ.get('PHP_TEST_BINARY') or shutil.which('php')


@unittest.skipUnless(PHP and shutil.which('gcc'), 'PHP and gcc required')
class DpiTerminalApiTests(unittest.TestCase):
    setUpClass = classmethod(native.DpiTerminalTests.setUpClass.__func__)
    tearDownClass = classmethod(native.DpiTerminalTests.tearDownClass.__func__)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / 'run'
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.stop)

    def stop(self):
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.connect(str(self.run/'control.sock'));s.sendall(b'S\n');s.recv(200)
        except OSError:
            pass

    def call(self, post, owner='browser-one'):
        source = ROOT/'webui/web/public/dpi-terminal.php'
        self.assertTrue(source.exists(), 'terminal API has not been implemented')
        code = '''require $argv[1];$p=json_decode(stream_get_contents(STDIN),true);
        try {AsusDpiTerminal::validate($p);$api=new AsusDpiTerminal(hash('sha256',$argv[4]),$argv[2],(int)$argv[6],$argv[3],fn()=>$argv[5],fn($reports)=>['removed'=>true,'reports_removed'=>$reports],new AsusDpiStore(dirname($argv[2]).'/jobs',(int)$argv[6]));echo json_encode($api->handle($p));}
        catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()]);}'''
        r = subprocess.run([PHP, '-n', '-r', code, str(source), str(self.run),
                            str(self.helper), owner, str(self.detector), str(os.getuid())],
                           input=json.dumps(post), text=True, capture_output=True, timeout=8)
        self.assertEqual((r.returncode, r.stderr), (0, ''), r.stdout)
        return json.loads(r.stdout)

    def post(self, cmd, **kwargs):
        return {'cmd':cmd, 'csrf_token':'csrf', **kwargs}

    def start(self, owner='browser-one', request_id='1'*32):
        return self.call(self.post('dpiterminalstart',cols='100',rows='30',language='en',request_id=request_id),owner)

    def test_remove_requires_explicit_fields_and_cannot_stop_another_browser(self):
        first=self.start();self.assertEqual(first['state'],'running')
        remove=self.post('dpiterminalremove',consent='remove',delete_reports='0')
        self.assertEqual(self.call(remove,'other'),{'error':'busy'})
        for bad in [dict(remove,consent=''),dict(remove,delete_reports='yes'),dict(remove,path='/tmp/outside')]:
            self.assertEqual(self.call(bad),{'error':'invalid_request'})
        self.assertEqual(self.call(remove),{'removed':True,'reports_removed':False})
        self.assertFalse((self.run/'control.sock').exists(),'owned Detector must stop before its executable can be removed')
        self.assertEqual(self.call(dict(remove,delete_reports='1')),{'removed':True,'reports_removed':True})

    def test_own_start_retry_reuses_session_other_browser_cannot_read_or_stop(self):
        first=self.start();self.assertEqual(first['state'],'running')
        self.assertRegex(first['terminal_id'], r'^[a-f0-9]{32}$')
        self.assertEqual(self.start()['terminal_id'],first['terminal_id'])
        self.assertEqual(self.start('other'), {'error':'busy'})
        for cmd, extra in [('dpiterminalpoll',{'offset':'0'}),('dpiterminalstop',{})]:
            p=self.post(cmd,terminal_id=first['terminal_id'],**extra)
            self.assertEqual(self.call(p,'other'),{'error':'missing_terminal'})
        out=self.call(self.post('dpiterminalpoll',terminal_id=first['terminal_id'],offset='0'))
        self.assertLessEqual(len(base64.b64decode(out['data'])),32768)
        stopped=self.call(self.post('dpiterminalstop',terminal_id=first['terminal_id']))
        self.assertEqual(stopped['state'],'stopped')
        next_run=self.start(request_id='2'*32);self.assertNotEqual(next_run['terminal_id'],first['terminal_id'])
        self.assertLessEqual(len(list(self.run.iterdir())),7)

    def test_open_nonce_prevents_late_close_from_stopping_a_new_open(self):
        first=self.start(request_id='1'*32)
        self.assertEqual(first['state'],'running')
        self.assertEqual(self.start(request_id='1'*32)['terminal_id'],first['terminal_id'])
        self.assertEqual(self.start(request_id='2'*32),{'error':'busy'})
        stop=self.post('dpiterminalstop',terminal_id=first['terminal_id'])
        self.assertEqual(self.call(stop)['state'],'stopped')
        retained=self.start(request_id='1'*32)
        self.assertEqual((retained['terminal_id'],retained['state']),(first['terminal_id'],'stopped'))
        second=self.start(request_id='2'*32)
        self.assertEqual(second['state'],'running')
        self.assertNotEqual(second['terminal_id'],first['terminal_id'])
        self.assertEqual(self.call(stop),{'error':'missing_terminal'})
        self.assertEqual(self.start(request_id='2'*32)['terminal_id'],second['terminal_id'])
        poll=self.call(self.post('dpiterminalpoll',terminal_id=second['terminal_id'],offset='0'))
        self.assertEqual(poll['state'],'running')

    def test_same_open_retry_after_native_exit_returns_original_session(self):
        first=self.start(request_id='1'*32)
        self.call(self.post('dpiterminalinput',terminal_id=first['terminal_id'],data=base64.b64encode(b'q').decode()))
        import time
        until=time.monotonic()+2
        while time.monotonic()<until:
            state=self.call(self.post('dpiterminalpoll',terminal_id=first['terminal_id'],offset='0'))
            if state['state']=='exited':break
            time.sleep(.025)
        self.assertEqual(state['state'],'exited')
        retry=self.start(request_id='1'*32)
        self.assertEqual((retry['terminal_id'],retry['state'],retry['exit_code']),(first['terminal_id'],'exited',7))
        second=self.start(request_id='2'*32)
        self.assertNotEqual(second['terminal_id'],first['terminal_id'])
        self.assertEqual(second['state'],'running')

    def test_closed_fields_and_input_limits_fail_before_creating_runtime(self):
        start=self.post('dpiterminalstart',cols='100',rows='30',language='en',request_id='1'*32)
        for changes in [{'binary':'/bin/sh'},{'language':'--help'},{'cols':'79'},{'cols':'241'},{'rows':'9'},{'rows':'81'},{'csrf_token':[]},{'rows':'030'},{'request_id':'A'*32},{'request_id':'bad'}]:
            self.assertEqual(self.call(start|changes),{'error':'invalid_request'})
        for data in ['!!!!',base64.b64encode(b'x'*1025).decode(),'', 'eA==\n']:
            self.assertEqual(self.call(self.post('dpiterminalinput',terminal_id='a'*32,data=data)),{'error':'invalid_request'})
        self.assertFalse(self.run.exists())

    def test_verified_binary_and_helper_availability_and_private_files(self):
        self.assertEqual(self.call(self.post('dpiterminalinfo')),{'available':True,'installed':True,'code':None})
        first=self.start();self.assertEqual(first['state'],'running')
        self.assertEqual(self.run.stat().st_mode & 0o777,0o700)
        for name in ['control.lock','broker.lock','output','status','terminal.json','control.sock']:
            self.assertEqual((self.run/name).lstat().st_mode & 0o777,0o600)
        (self.run/'terminal.json').unlink();(self.run/'terminal.json').symlink_to(self.detector)
        self.assertEqual(self.call(self.post('dpiterminalpoll',terminal_id=first['terminal_id'],offset='0')),{'error':'invalid_state'})

    def test_unavailable_detector_architecture_is_reported_without_launching(self):
        code='''require $argv[1];$t=new AsusDpiTerminal(hash('sha256','browser'),null,(int)$argv[3],$argv[2],
        function(){throw new RuntimeException('unsupported_abi');});
        echo json_encode($t->handle(['cmd'=>'dpiterminalinfo','csrf_token'=>'csrf']));'''
        r=subprocess.run([PHP,'-n','-r',code,str(ROOT/'webui/web/public/dpi-terminal.php'),str(self.helper),str(os.getuid())],capture_output=True,text=True)
        self.assertEqual((r.returncode,r.stderr),(0,''))
        self.assertEqual(json.loads(r.stdout),{'available':False,'installed':False,'code':'unsupported_abi'})


if __name__ == '__main__':
    unittest.main()
