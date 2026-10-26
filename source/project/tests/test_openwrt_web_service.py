"""The dedicated listener binds only named local addresses by default."""
from pathlib import Path
import subprocess
import unittest
import tempfile

LIB=Path(__file__).resolve().parents[1]/'openwrt/web.sh'

class NativeWebServiceTests(unittest.TestCase):
    def test_invalid_listener_is_rejected_before_procd_replaces_running_instance(self):
        r=self.run_init(False)
        self.assertNotEqual(r.returncode,0)
        self.assertNotIn('OLD_INSTANCE_CLOSED',r.stdout)
        self.assertIn('invalid_panel_listener',r.stderr)

    def run_init(self,busy):
        with tempfile.TemporaryDirectory()as td:
            guard=Path(td)/'guard.sh';guard.write_text('nfqws_native_update_enter() { return '+('1'if busy else'0')+'; }\n')
            source=(LIB.parent/'nfqws2-web.init').read_text().replace('/usr/lib/nfqws2-web/web.sh',str(LIB)).replace('/usr/lib/nfqws2/update/service-lease.sh',str(guard))
            script='''
action=restart
config_load() { echo CONFIG_READ; }
config_get() { eval "$1=invalid"; }
config_list_foreach() { :; }
'''+source+'''
printf 'OLD_INSTANCE_CLOSED\\n'
start_service
'''
            return subprocess.run(['sh','-c',script],text=True,capture_output=True)

    def test_update_refuses_listener_reads_and_procd_restart_before_mutation(self):
        r=self.run_init(True);self.assertNotEqual(r.returncode,0);self.assertNotIn('CONFIG_READ',r.stdout);self.assertNotIn('OLD_INSTANCE_CLOSED',r.stdout)

    def run_listeners(self,addresses,override=''):
        script='''
. "$1"
config_get() { case "$3" in port) eval "$1=90";; network) eval "$1=lan";; esac; }
config_list_foreach() { [ -z "$TEST_OVERRIDE" ] || "$3" "$TEST_OVERRIDE"; }
ubus() { printf '%s' '{"up":true}'; }
jsonfilter() { printf '%s\\n' "$TEST_ADDRESSES"; }
nfqws_web_listeners
'''
        import os
        return subprocess.run(['sh','-c',script,'fixture',str(LIB)],text=True,capture_output=True,
                              env=os.environ|{'TEST_ADDRESSES':addresses,'TEST_OVERRIDE':override})

    def test_loopback_and_current_lan_without_wildcard(self):
        r=self.run_listeners('192.168.87.1\n192.168.88.1')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.splitlines(),['127.0.0.1:90','192.168.87.1:90','192.168.88.1:90'])

    def test_explicit_address_and_hostile_values(self):
        r=self.run_listeners('192.168.87.1','192.168.1.50')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.splitlines(),['127.0.0.1:90','192.168.1.50:90'])
        for value in ['0.0.0.0','1.2.3.999','192.168.1.1;reboot']:
            self.assertNotEqual(self.run_listeners('',value).returncode,0)
