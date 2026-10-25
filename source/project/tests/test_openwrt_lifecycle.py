"""Use OpenWrt's real JSON parser at the firmware boundary, not a copied parser."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
JSONFILTER=os.environ.get('NFQWS_TEST_JSONFILTER')


class OpenWrtServiceTests(unittest.TestCase):
    def run_init(self, action, *, failed=False):
        """Real init script, with only procd/OS calls replaced at the boundary."""
        with tempfile.TemporaryDirectory() as td:
            binary=Path(td)/'bin';binary.mkdir()
            control=binary/'control';control.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$TEST_LOG"
[ "$1" != preflight ] || [ "$FAIL_PREFLIGHT" != 1 ]
''');control.chmod(0o755)
            launch=Path(td)/'launch.env';launch.write_text("NFQWS_LAUNCH_ARGS='--user=nobody --qnum=300 --filter-tcp=443'\n")
            body='''
NFQWS_CONTROL="$CONTROL"; NFQWS_RUN="$RUN"; action="$ACTION"
. "$INIT"
procd_open_instance() { echo procd-open >> "$TEST_LOG"; }
procd_set_param() { printf 'procd-%s\\n' "$*" >> "$TEST_LOG"; }
procd_close_instance() { echo procd-close >> "$TEST_LOG"; }
start_service
service_started
'''
            r=subprocess.run(['sh','-c',body],capture_output=True,text=True,env={**os.environ,
                'CONTROL':str(control),'RUN':td,'INIT':str(ROOT/'openwrt/nfqws2.init'),
                'ACTION':action,'FAIL_PREFLIGHT':'1' if failed else '0','TEST_LOG':td+'/calls'})
            calls=Path(td+'/calls').read_text().splitlines() if Path(td+'/calls').exists() else []
            return r,calls

    def test_failed_preflight_never_changes_existing_procd_instance(self):
        for action in ['start','restart','reload','boot']:
            r,calls=self.run_init(action,failed=True)
            self.assertNotEqual(r.returncode,0)
            self.assertEqual(calls,['preflight'])

    def test_foreground_supervision_and_actual_queue_check(self):
        r,calls=self.run_init('start')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(calls[0:2],['preflight','firewall'])
        self.assertIn('procd-command /usr/bin/nfqws2 --user=nobody --qnum=300 --filter-tcp=443',calls)
        self.assertIn('procd-respawn 3600 5 5',calls)
        self.assertEqual(calls[-1],'check-started')
        self.assertFalse(any('--daemon' in c or '--pidfile' in c for c in calls))

    def test_queue_facts_validate_rows_and_report_packet_sequence(self):
        for text,expected in [('', 'unbound null null'),
            ('300 1234 0 2 65535 0 0 19 1\n','bound 19 1234'),
            ('300 1234 0 2 65535 0 0 bad 1\n','unknown null null'),
            ('300 1234 0 2 65535 0 0 19 1\n'*2,'unknown null null')]:
            with self.subTest(text=text),tempfile.TemporaryDirectory() as td:
                fixture=Path(td)/'queues';fixture.write_text(text)
                r=subprocess.run(['sh','-c','. "$LIB"; nfqws_queue_facts 300 "$QUEUE_FILE"'],
                    env={**os.environ,'LIB':str(ROOT/'openwrt/platform.sh'),'QUEUE_FILE':str(fixture)},text=True,capture_output=True)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertEqual(r.stdout.strip(),expected)

    def test_readiness_wait_uses_base_busybox_integer_sleep(self):
        r=subprocess.run(['sh','-c','''
. "$LIB"
checks=0
nfqws_check() { checks=$((checks+1)); [ "$checks" -ge 3 ]; }
sleep() { [ "$1" = 1 ] || return 1; printf 'sleep=%s\n' "$1"; }
nfqws_wait_started
'''],env={**os.environ,'LIB':str(ROOT/'openwrt/platform.sh')},capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.splitlines(),['sleep=1','sleep=1'])


@unittest.skipUnless(JSONFILTER,'Set NFQWS_TEST_JSONFILTER to the native OpenWrt parser')
class OpenWrtUplinkTests(unittest.TestCase):
    def run_discovery(self, entries, explicit=''):
        with tempfile.TemporaryDirectory() as td:
            fixture=Path(td)/'interfaces.json';fixture.write_text(json.dumps({'interface':entries}))
            script='''
. "$PLATFORM_LIB"
ubus() { [ "$*" = 'call network.interface dump' ] || return 1; cat "$FIXTURE"; }
jsonfilter() { "$REAL_JSONFILTER" "$@"; }
ip() { [ "$1 $2 $3" = 'link show dev' ] && [ "$4" != missing ]; }
nfqws_uplinks
'''
            return subprocess.run(['sh','-c',script],capture_output=True,text=True,
                env={**os.environ,'PLATFORM_LIB':str(ROOT/'openwrt/platform.sh'),
                     'FIXTURE':str(fixture),'REAL_JSONFILTER':JSONFILTER,'ISP_INTERFACE':explicit})

    def test_logical_pppoe_ipv6_and_vlan_devices_are_unique(self):
        entries=[{'interface':'lan','up':True,'l3_device':'br-lan','proto':'static','route':[]},
                 {'interface':'internet','up':True,'l3_device':'pppoe-internet','device':'eth0.7','proto':'pppoe','route':[{'target':'0.0.0.0','mask':0}]},
                 {'interface':'internet6','up':True,'l3_device':'pppoe-internet','proto':'dhcpv6','route':[{'target':'::','mask':0}]},
                 {'interface':'backup','up':True,'l3_device':'eth1.22','proto':'dhcp','route':[{'target':'0.0.0.0','mask':0}]}]
        r=self.run_discovery(entries)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.splitlines(),['pppoe-internet','eth1.22'])

    def test_down_and_vpn_interfaces_are_not_automatic_uplinks(self):
        entries=[{'interface':'vpn','up':True,'l3_device':'wg0','proto':'wireguard','route':[{'target':'0.0.0.0','mask':0}]},
                 {'interface':'down','up':False,'l3_device':'eth2','proto':'dhcp','route':[{'target':'0.0.0.0','mask':0}]},
                 {'interface':'wan','up':True,'l3_device':'wan','proto':'static','route':[{'target':'0.0.0.0','mask':0}]}]
        r=self.run_discovery(entries)
        self.assertEqual(r.stdout.strip(),'wan')

    def test_explicit_interfaces_are_checked_and_can_include_tunnel(self):
        r=self.run_discovery([], 'wan wg0');self.assertEqual(r.stdout.splitlines(),['wan','wg0'])
        for bad in ['missing','wan;reboot','wan "wg0"']:
            with self.subTest(bad=bad):
                r=self.run_discovery([],bad);self.assertNotEqual(r.returncode,0)
                self.assertEqual(r.stdout,'')

    def test_no_active_default_route_is_a_wait_state_not_an_arbitrary_device(self):
        r=self.run_discovery([{'interface':'lan','up':True,'l3_device':'br-lan','route':[]}])
        self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,'')


if __name__=='__main__':unittest.main()
