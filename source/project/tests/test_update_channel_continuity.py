"""Only a genuine updater may stop the web server without revoking support."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dpi_normalize import ROOT

class UpdateChannelContinuityTests(unittest.TestCase):
    def exercise(self, authorization):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);web=subprocess.Popen(['sleep','30']);channel=subprocess.Popen(['sleep','30'])
            try:
                auth='' if authorization is None else 'asus_update_transaction() { [ "$1" = web-stop ] && '+('true' if authorization else 'false')+'; }\n'
                code='. '+str(ROOT/'asus/web-lib.sh')+'\n'+auth+f'''
web_technical_channel() {{ printf '%s\\n' "$1" >> {root/'calls'}; kill {channel.pid}; }}
web_kill() {{ kill {web.pid}; }}
cru() {{ :; }}
WEB_RUN={d}
web_stop
'''
                env={**os.environ,'NFQWS_UPDATE_PRESERVE_CHANNEL':'1'}
                p=subprocess.run(['/bin/sh','-c',code],capture_output=True,text=True,env=env,timeout=3)
                self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'')
                web.wait(timeout=2)
                if authorization:
                    self.assertIsNone(channel.poll(),'updater killed the independent channel')
                    self.assertFalse((root/'calls').exists())
                else:
                    channel.wait(timeout=2);self.assertEqual((root/'calls').read_text(),'stop\n')
            finally:
                for child in [web,channel]:
                    if child.poll() is None:child.terminate()
                    child.wait(timeout=2)
    def test_authorized_update_keeps_channel_process_alive(self):self.exercise(True)
    def test_normal_web_stop_revokes_channel_even_with_an_environment_flag(self):self.exercise(False)
    def test_legacy_missing_authorizer_revokes_channel(self):self.exercise(None)

import shlex
import test_package_update_apply as apply_fixtures

@unittest.skipUnless(apply_fixtures.NATIVE.is_file(), 'native PHP fixture required')
class UpdateChannelTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):apply_fixtures.PackageUpdateApplyTests.setUpClass()
    @classmethod
    def tearDownClass(cls):apply_fixtures.PackageUpdateApplyTests.tearDownClass()
    def test_real_installer_ancestry_keeps_channel_and_later_manual_stop_revokes_it(self):
        c=apply_fixtures.PackageUpdateApplyTests();c.setUp();self.addCleanup(c.doCleanups)
        channel=subprocess.Popen(['sleep','30'])
        self.addCleanup(lambda:(channel.terminate(),channel.wait()) if channel.poll() is None else None)
        calls=c.base/'channel-calls';web=c.base/'web-runtime';web.mkdir(mode=0o700)
        guard=shlex.join([str(c.php),'-n',str(c.entry),'authorize'])
        c.service.web.write_text('#!/bin/sh\ncase "$1" in status|start) exit 0;; stop) ;; *) exit 2;; esac\n. '+shlex.quote(str(ROOT/'asus/web-lib.sh'))+'\n'+
            'asus_update_transaction() { '+guard+' "$1"; }\n'+
            'web_technical_channel() { echo "$1" >> '+shlex.quote(str(calls))+'; kill '+str(channel.pid)+'; }\n'+
            'web_kill() { :; }\ncru() { :; }\nWEB_RUN='+shlex.quote(str(web))+'\nweb_stop\n')
        c.service.running();result=c.execute()
        self.assertEqual(result['state'],'succeeded',result);self.assertIsNone(channel.poll());self.assertFalse(calls.exists())
        r=subprocess.run([str(c.service.web),'stop'],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);channel.wait(timeout=2);self.assertEqual(calls.read_text(),'stop\n')
