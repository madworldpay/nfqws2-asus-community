"""Native rules have client scope, symmetric capture and atomic ownership."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT/'openwrt/firewall.sh'


class OpenWrtFirewallTests(unittest.TestCase):
    def run_sh(self, body, **env):
        return subprocess.run(['sh', '-c', '. '+shlex.quote(str(LIB))+'''\n
nfqws_flow_probe() { NFQWS_FLOW_STATE=${TEST_FLOW_STATE:-none}; NFQWS_FLOW_HANDLE=4; }
'''+body],
                              env={**os.environ, **env}, text=True, capture_output=True)

    def config(self, extra=''):
        return '''
NFQUEUE_NUM=300; TCP_PORTS=80,443; UDP_PORTS=443,3478:3481
IPV6_ENABLED=1; ASUS_CLIENT_MODE=all; ASUS_CLIENTS4=''; ASUS_CLIENTS6=''
NFQWS_WAN='pppoe-wan eth0.20'
''' + extra + '\n'

    def test_both_conntrack_directions_and_logical_uplinks(self):
        r = self.run_sh(self.config()+'nfqws_render_rules')
        self.assertEqual(r.returncode, 0, r.stderr)
        for token in ['table inet nfqws2_native', '"pppoe-wan"', '"eth0.20"',
                      'ct direction original', 'ct direction reply',
                      'ct original packets 1-15', 'ct reply packets 1-15',
                      'tcp dport', 'tcp sport', 'queue num 300 bypass',
                      'meta mark & 0x40000000 != 0 return']:
            self.assertIn(token, r.stdout)
        self.assertIn('3478-3481', r.stdout)
        self.assertNotIn('flush ruleset', r.stdout)
        self.assertNotIn('table inet fw4', r.stdout)

    def test_selected_clients_scope_original_address_for_both_directions(self):
        r = self.run_sh(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='192.168.87.10 192.168.87.20/32'; ASUS_CLIENTS6='2001:db8::/64'")+'nfqws_render_rules')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('192.168.87.10', r.stdout)
        self.assertIn('2001:db8::/64', r.stdout)
        self.assertEqual(r.stdout.count('ct original ip saddr != @clients4 return'), 2)
        self.assertEqual(r.stdout.count('ct original ip6 saddr != @clients6 return'), 2)
        self.assertNotIn('ip daddr !=', r.stdout)

    def test_exclusion_and_disabled_ipv6_do_not_queue_other_family(self):
        r = self.run_sh(self.config("ASUS_CLIENT_MODE=exclude; ASUS_CLIENTS4='192.168.87.10'; IPV6_ENABLED=0")+'nfqws_render_rules')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count('ct original ip saddr @clients4 return'), 2)
        self.assertEqual(r.stdout.count('meta nfproto ipv6 return'), 2)

    def test_invalid_config_cannot_emit_partial_rules(self):
        for bad in ["NFQUEUE_NUM=65536", "NFQWS_WAN='wan;reboot'",
                    "ASUS_CLIENT_MODE=include", "TCP_PORTS='443,99999'",
                    "UDP_PORTS='443,10:1'", "ASUS_CLIENTS4='1.2.3.4;reboot'",
                    "ASUS_CLIENTS6='2001:db8::/129'", "ASUS_CLIENT_MODE=nope"]:
            with self.subTest(bad=bad):
                r = self.run_sh(self.config(bad)+'nfqws_render_rules')
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(r.stdout, '')

    def test_apply_validates_before_atomic_replace(self):
        with tempfile.TemporaryDirectory() as td:
            r = self.run_sh(self.config()+'''
nft() {
 printf '%s\n' "$*" >> "$TEST_LOG"
 case "$*" in 'list table inet nfqws2_native') echo 'comment "NFQWS2 native OpenWrt"';;
 '-c -f '*) return "${FAIL_CHECK:-0}";;
 esac
}
nfqws_firewall_apply
''', NFQWS_RUN=td, TEST_LOG=td+'/calls')
            self.assertEqual(r.returncode, 0, r.stderr)
            calls=Path(td+'/calls').read_text().splitlines()
            self.assertTrue(calls[1].startswith('-c -f '), calls)
            self.assertTrue(calls[2].startswith('-f '), calls)
            self.assertEqual(len(calls), 3)
            text=Path(td+'/rules.nft').read_text()
            self.assertTrue(text.startswith('add table inet nfqws2_native\ndelete table inet nfqws2_native\n'))

    def test_foreign_table_and_failed_validation_are_not_deleted(self):
        for foreign, fail in [('1', '0'), ('0', '1')]:
            with self.subTest(foreign=foreign), tempfile.TemporaryDirectory() as td:
                r = self.run_sh(self.config()+'''
nft() {
 printf '%s\n' "$*" >> "$TEST_LOG"
 case "$*" in
 'list table inet nfqws2_native') [ "$FOREIGN" = 1 ] || echo 'comment "NFQWS2 native OpenWrt"';;
 '-c -f '*) return "$FAIL_CHECK";;
 esac
}
nfqws_firewall_apply
''', NFQWS_RUN=td, TEST_LOG=td+'/calls', FOREIGN=foreign, FAIL_CHECK=fail)
                self.assertNotEqual(r.returncode, 0)
                calls=Path(td+'/calls').read_text().splitlines()
                self.assertFalse(any(c.startswith('-f ') or c.startswith('delete ') for c in calls), calls)

    def test_stop_removes_only_owned_table(self):
        for foreign, expected in [('0', 0), ('1', 1)]:
            with self.subTest(foreign=foreign), tempfile.TemporaryDirectory() as td:
                r = self.run_sh('''
nft() {
 printf '%s\n' "$*" >> "$TEST_LOG"
 case "$*" in 'list table inet nfqws2_native') [ "$FOREIGN" = 1 ] || echo 'comment "NFQWS2 native OpenWrt"';; esac
}
nfqws_firewall_stop
''', TEST_LOG=td+'/calls', FOREIGN=foreign, NFQWS_RUN=td)
                self.assertEqual(r.returncode, expected, r.stderr)
                calls=Path(td+'/calls').read_text()
                if foreign == '0':
                    self.assertIn('-f ', calls)
                else:
                    self.assertNotIn('-f ', calls)

    def test_selective_offload_uses_original_client_and_returns_to_fw4(self):
        r=self.run_sh(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='192.168.87.10'; ASUS_CLIENTS6='2001:db8::/64'")+'''
NFQWS_FLOW_STATE=system; NFQWS_FLOW_HANDLE=4; NFQWS_FLOW_DEFINITION='add flowtable inet fw4 ft { hook ingress priority 0; devices = { "eth0" }; counter; }'
nfqws_render_flow apply
''')
        self.assertEqual(r.returncode,0,r.stderr)
        for token in ['replace rule inet fw4 forward handle 4 jump nfqws2_flow',
                      'goto nfqws2_flow_scope', 'goto nfqws2_flow_add',
                      'ct original ip saddr != { 192.168.87.10 }',
                      'ct original ip6 saddr != { 2001:db8::/64 }',
                      'ct original packets 0-15 return', 'ct reply packets 0-15 return',
                      'flow offload @ft', 'delete flowtable inet fw4 ft', 'add flowtable inet fw4 ft']:
            self.assertIn(token,r.stdout)
        self.assertNotIn(' accept',r.stdout)
        self.assertNotIn('uci ',r.stdout)

    def test_flow_reload_and_stop_restore_only_recognized_hook(self):
        for action in ['apply','stop']:
            r=self.run_sh(self.config()+f'''
NFQWS_FLOW_STATE=managed; NFQWS_FLOW_HANDLE=19; NFQWS_FLOW_DEFINITION='add flowtable inet fw4 ft {{ hook ingress priority 0; devices = {{ "eth0" }}; counter; }}'
nfqws_render_flow {action}
''')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('flush chain inet fw4 nfqws2_flow_scope',r.stdout)
            self.assertNotIn('flush table',r.stdout)
            self.assertNotIn('flush ruleset',r.stdout)
            if action=='stop':
                self.assertIn('replace rule inet fw4 forward handle 19 meta l4proto { tcp, udp } flow offload @ft',r.stdout)
                self.assertIn('delete chain inet fw4 nfqws2_flow_add',r.stdout)

    def test_flow_failure_cannot_change_existing_firewall(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.run_sh(self.config()+'''
nfqws_flow_probe() { return 1; }
nft() { printf '%s\n' "$*" >> "$TEST_LOG"; echo 'comment "NFQWS2 native OpenWrt"'; }
nfqws_firewall_apply
''',NFQWS_RUN=td,TEST_LOG=td+'/calls')
            self.assertNotEqual(r.returncode,0)
            self.assertFalse(any(c.startswith('-f ') or c.startswith('delete ') for c in Path(td+'/calls').read_text().splitlines()))


if __name__ == '__main__': unittest.main()
