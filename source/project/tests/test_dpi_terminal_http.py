"""Terminal routes preserve panel authentication, anonymous sessions, and CSRF."""
import test_support_mail_api as mail
from test_auth_api import ROOT
import os
import json
import time
import subprocess
import base64
from pathlib import Path


class DpiTerminalHttpTests(mail.SupportMailApiTests):
    def setUp(self):
        super().setUp()
        (self.base/'dpi-terminal.php').write_text((ROOT/'webui/web/public/dpi-terminal.php').read_text())
        (self.base/'dpi-terminal-lifecycle.php').write_text((ROOT/'webui/web/public/dpi-terminal-lifecycle.php').read_text())

    def terminal(self, token):
        return {'cmd':'dpiterminalinfo','csrf_token':token}

    def test_terminal_auth_origin_csrf_and_closed_fields(self):
        self.assertEqual(self.request(self.terminal('bad'))[0],401)
        token=self.login()
        code,info=self.request(self.terminal(token))
        self.assertEqual(code,200)
        self.assertEqual(set(info),{'available','installed','code'})
        self.assertIs(info['available'],False)
        self.assertEqual(self.request(self.terminal('bad'))[0],403)
        self.assertEqual(self.request(self.terminal(token)|{'binary':'/bin/sh'})[0],400)
        self.assertEqual(self.request(self.terminal(token)|{'csrf_token':[]})[0],400)
        self.origin='http://evil.invalid'
        self.assertEqual(self.request(self.terminal(token))[0],403)

    def test_anonymous_panel_keeps_session_csrf_and_start_lease(self):
        token=self.login();self.change('',token)
        token=self.request({'cmd':'login'},'visitor')[1]['csrf_token']
        self.assertEqual(self.request(self.terminal(token),'visitor')[0],200)
        self.assertEqual(self.request(self.terminal(token),'other')[0],403)
        (self.base/'update-busy').touch()
        p={'cmd':'dpiterminalstart','csrf_token':token,'cols':'100','rows':'30','language':'ru','request_id':'1'*32}
        self.assertEqual(self.request(p,'visitor'),(409,{'error':'busy'}))
        self.assertEqual(self.request(self.terminal(token),'visitor')[0],200)

    def standalone_job(self, alive):
        state=self.base/'dpi-state';state.mkdir(mode=0o700)
        source=(self.base/'dpi-store.php').read_text().replace("$root??self::optPath('/var/lib/nfqws2-asus/dpi-detector')",json.dumps(str(state))).replace('private int $owner=0','private int $owner='+str(os.getuid()))
        (self.base/'dpi-store.php').write_text(source)
        for name in ['dpi-jobs.php','dpi-normalize.php','dpi-analysis.php','dpi-native.php']:
            (self.base/name).write_text((ROOT/'webui/web/public'/name).read_text())
        source=(self.base/'dpi-catalog.php').read_text().replace("dirname(__DIR__,3).'/support/dpi-catalog.json'",json.dumps(str(ROOT/'support/dpi-catalog.json')))
        (self.base/'dpi-catalog.php').write_text(source)
        source=(self.base/'dpi-install.php').read_text().replace("$root??AsusDpiStore::optPath('/lib/nfqws2-asus/dpi-detector')",json.dumps(str(self.base/'detector-not-installed')))
        (self.base/'dpi-install.php').write_text(source)
        source=(self.base/'dpi-terminal.php').read_text().replace("$this->root??='/tmp/nfqws2-dpi-terminal'",'$this->root??='+json.dumps(str(self.base/'terminal'))).replace('private int $owner=0','private int $owner='+str(os.getuid()))
        (self.base/'dpi-terminal.php').write_text(source)
        now=time.time();up=float(Path('/proc/uptime').read_text().split()[0]);boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        job={'id':'a'*32,'kind':'install','state':'running','started_at':int(now)-10,'started_uptime':up-10,'boot_id':boot,'finished_at':None,'groups':[],'params':{},'code':None}
        if alive:
            process=subprocess.Popen(['sleep','30'])
            self.addCleanup(lambda:(process.terminate(),process.wait()))
            fields=Path(f'/proc/{process.pid}/stat').read_text().split(') ')[1].split()
            job['identity']={'pid':process.pid,'starttime':fields[19],'exe':os.readlink(f'/proc/{process.pid}/exe'),'boot_id':boot}
        (state/'jobs.json').write_text(json.dumps({'jobs':{'a'*32:job}}));(state/'jobs.json').chmod(0o600)
        return state

    def test_existing_standalone_dpi_job_excludes_terminal_start(self):
        token=self.login();self.standalone_job(True)
        p={'cmd':'dpiterminalstart','csrf_token':token,'cols':'100','rows':'30','language':'ru','request_id':'1'*32}
        self.assertEqual(self.request(p),(409,{'error':'busy'}))

    def test_remove_keeps_auth_csrf_origin_and_update_job_exclusion(self):
        post={'cmd':'dpiterminalremove','csrf_token':'bad','consent':'remove','delete_reports':'0'}
        self.assertEqual(self.request(post)[0],401)
        token=self.login();post['csrf_token']=token
        self.assertEqual(self.request(dict(post,csrf_token='bad'))[0],403)
        self.origin='http://evil.invalid';self.assertEqual(self.request(post)[0],403);self.origin='http://localhost'
        self.standalone_job(True)
        self.assertEqual(self.request(post),(409,{'error':'busy'}))

    def test_same_boot_dead_standalone_job_is_reconciled_before_terminal_start(self):
        token=self.login();state=self.standalone_job(False)
        p={'cmd':'dpiterminalstart','csrf_token':token,'cols':'100','rows':'30','language':'ru','request_id':'1'*32}
        # The terminal reaches its own detector availability check after admission.
        self.assertEqual(self.request(p),(503,{'error':'not_installed'}))
        job=json.loads((state/'jobs.json').read_text())['jobs']['a'*32]
        self.assertEqual((job['state'],job['code']),('interrupted','interrupted'))

    def test_full_binary_chunk_stays_within_browser_response_budget(self):
        token=self.login()
        # Substitute only the terminal producer; exercise the actual route's wire encoding.
        (self.base/'dpi-terminal.php').write_text('''<?php
        final class AsusDpiTerminal {
          function __construct($browser){} static function validate($post){}
          static function error($e){return 'terminal_failed';}
          function handle($post){return ['terminal_id'=>str_repeat('a',32),'state'=>'running','offset'=>32768,'data'=>base64_encode(str_repeat('?',32768)),'exit_code'=>null];}
        }''')
        code='''ini_set('session.save_path',$argv[1]);session_name('nfqws_asus_session');session_id($argv[2]);
        $_SERVER['REQUEST_METHOD']='POST';$_SERVER['HTTP_HOST']='localhost';$_SERVER['HTTP_ORIGIN']='http://localhost';
        $_POST=json_decode(stream_get_contents(STDIN),true);require $argv[1].'/index.php';'''
        post={'cmd':'dpiterminalpoll','csrf_token':token,'terminal_id':'a'*32,'offset':'0'}
        result=subprocess.run([mail.PHP,'-n','-r',code,str(self.base),self.sessions['user-one']],input=json.dumps(post),text=True,capture_output=True,timeout=5)
        self.assertEqual((result.returncode,result.stderr),(0,''))
        self.assertEqual(json.loads(result.stdout)['data'],base64.b64encode(b'?'*32768).decode())
        self.assertLessEqual(len(result.stdout.encode()),49152)
