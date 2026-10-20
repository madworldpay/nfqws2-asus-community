"""Firmware command doubles delimit the unavailable ASUS/kernel boundary."""
import os
from pathlib import Path
import subprocess
import shlex
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'asus/platform.sh'


class PlatformTests(unittest.TestCase):
    def run_sh(self, body, env=None):
        prelude = f'. "{LIB}"\n' if LIB.exists() else ''
        return subprocess.run(shlex.split(os.environ.get('TEST_SHELL', 'sh')) + ['-c', prelude + body], text=True,
                              capture_output=True, env={**os.environ, **(env or {})})

    def test_supported_models_and_unknown_model(self):
        for model, expected in [('GT-BE19000', 0), ('GT-BE19000AI', 0),
                                ('GT-AX6000', 0), ('', 1)]:
            with self.subTest(model=model):
                r = self.run_sh('nvram() { [ "$2" = productid ] && printf "%s" "$MODEL"; }; asus_model', {'MODEL': model})
                self.assertEqual(r.returncode, expected, r.stderr)
                if expected == 0:
                    self.assertEqual(r.stdout.strip(), model)
                    if model == "GT-AX6000": self.assertIn("own risk", r.stderr)

    def test_odmpid_identifies_rebranded_model(self):
        r = self.run_sh('nvram() { [ "$2" = odmpid ] && echo GT-BE19000AI; }; asus_model')
        self.assertEqual(r.stdout.strip(), 'GT-BE19000AI')

    def test_pppoe_uses_logical_interface_not_physical_port(self):
        r = self.run_sh('''
        nvram() { case "$2" in wan0_state_t) echo 2;; wan0_proto) echo pppoe;;
          wan0_pppoe_ifname) echo ppp0;; wan0_ifname) echo eth0;; esac; }
        ip() { [ "$*" = 'link show dev ppp0' ]; }
        ISP_INTERFACE=''; asus_interfaces
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), 'ppp0')

    def test_explicit_interface_validated_and_preserved(self):
        r = self.run_sh("ip() { [ \"$*\" = 'link show dev eth4' ]; }; ISP_INTERFACE=eth4; asus_interfaces")
        self.assertEqual(r.stdout.strip(), 'eth4')
        r = self.run_sh("ISP_INTERFACE='eth0;reboot'; asus_interfaces")
        self.assertNotEqual(r.returncode, 0)

    def config(self, extra=''):
        return '''
        NFQUEUE_NUM=300; TCP_PORTS=80,443; UDP_PORTS=443; IPV6_ENABLED=1
        ASUS_CLIENT_MODE=all; ASUS_CLIENTS4=''; ASUS_CLIENTS6=''
        ''' + extra

    def test_empty_include_and_invalid_queue_rejected(self):
        for extra in ['ASUS_CLIENT_MODE=include', 'NFQUEUE_NUM=65536',
                      "ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='   '",
                      "TCP_PORTS='80;reboot'", 'ASUS_CLIENT_MODE=bogus',
                      "ASUS_CLIENTS4='1.2.3.4 --jump ACCEPT'", 'IPV6_ENABLED=2',
                      "ASUS_CLIENTS6='2001:db8::1 --jump ACCEPT'"]:
            r = self.run_sh(self.config(extra) + '\nasus_validate')
            self.assertEqual(r.returncode, 1, r.stderr)

    def test_ipv4_inclusion_scopes_both_packet_directions(self):
        r = self.run_sh(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='192.0.2.10/32'") + '\nASUS_WAN=ppp0; asus_rules 4 mangle')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('--ctorigsrc 192.0.2.10/32 -j nfqa_out', r.stdout)
        self.assertIn('--ctorigsrc 192.0.2.10/32 -j nfqa_in', r.stdout)
        self.assertIn('--ctdir ORIGINAL', r.stdout)
        self.assertIn('--ctdir REPLY', r.stdout)
        self.assertIn('--queue-num 300 --queue-bypass', r.stdout)
        self.assertNotIn('-F POSTROUTING', r.stdout)

    def test_ipv6_include_scopes_both_directions_without_selecting_ipv4(self):
        r = self.run_sh(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS6='2001:db8::/64'") + '\nASUS_WAN=ppp0; asus_rules 6 mangle')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('--ctorigsrc 2001:db8::/64 -j nfqa_out', r.stdout)
        self.assertIn('--ctorigsrc 2001:db8::/64 -j nfqa_in', r.stdout)
        self.assertIn('--ctdir ORIGINAL', r.stdout)
        self.assertIn('--ctdir REPLY', r.stdout)
        self.assertIn('--queue-num 300 --queue-bypass', r.stdout)
        r = self.run_sh(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS6='2001:db8::/64'") + '\nASUS_WAN=ppp0; asus_rules 4 mangle')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('-j nfqa_in', r.stdout)
        self.assertNotIn('-j nfqa_out', r.stdout)

    def test_ipv6_list_satisfies_include_mode(self):
        r = self.run_sh(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS6='2001:db8::/64'") + '\nasus_validate')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_ipv6_include_does_not_select_unlisted_clients(self):
        r = self.run_sh(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='192.0.2.10'") + '\nASUS_WAN=ppp0; asus_rules 6 mangle')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('-j nfqa_in', r.stdout)
        self.assertNotIn('-j nfqa_out', r.stdout)

    def test_ipv6_exclusion_returns_before_queue_selection(self):
        r = self.run_sh(self.config("ASUS_CLIENT_MODE=exclude; ASUS_CLIENTS6='2001:db8::/64'") + '\nASUS_WAN=ppp0; asus_rules 6 mangle')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(r.stdout.index('--ctorigsrc 2001:db8::/64 -j RETURN'), r.stdout.index('-A nfqa_post -o ppp0 -m conntrack --ctdir ORIGINAL -j nfqa_out'))

    def test_exclusion_returns_before_queue_selection(self):
        r = self.run_sh(self.config("ASUS_CLIENT_MODE=exclude; ASUS_CLIENTS4='192.0.2.0/24'") + '\nASUS_WAN=eth0; asus_rules 4 mangle')
        self.assertLess(r.stdout.find('--ctorigsrc 192.0.2.0/24 -j RETURN'), r.stdout.find('-A nfqa_post -o eth0 -m conntrack --ctdir ORIGINAL -j nfqa_out'))

    def test_probe_failure_cleans_detached_chain(self):
        r = self.run_sh(self.config() + '''
        iptables() { printf '%s\n' "$*"; case "$*" in *' -A '*) return 1;; esac; }
        asus_probe_family iptables; result=$?; echo "RESULT=$result"
        ''')
        self.assertIn('RESULT=1', r.stdout)
        self.assertRegex(r.stdout, r'-X nfqa_probe_\d+')
        self.assertNotIn('-A PREROUTING', r.stdout)

    def test_probe_restores_accounting_enabled_by_old_connbytes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            body = self.config() + '''
            echo 0 > "$ACCT"
            sysctl() {
                case "$1" in -n) cat "$ACCT";; -w) echo "${2##*=}" > "$ACCT";; esac
            }
            iptables() {
                case "$*" in *'--connbytes '*) echo 1 > "$ACCT"; return "$FAIL";; esac
                return 0
            }
            asus_probe_restore() { cat >/dev/null; return 0; }
            asus_probe_family iptables; rc=$?
            printf 'result=%s accounting=%s\n' "$rc" "$(cat "$ACCT")"
            '''
            for fail in ['0', '1']:
                r = self.run_sh(body, {'ACCT': td + '/acct', 'FAIL': fail})
                self.assertEqual(r.stdout.strip(), f'result={fail} accounting=0', r.stderr)

    def test_cli_success_with_incompatible_restore_is_not_accepted(self):
        r = self.run_sh(self.config() + '''
        sysctl() { echo 1; }
        iptables() {
            case "$*" in
                *' -S '*) echo '-A probe -p tcp -j RETURN';;
                *' -X '*) echo cleaned >&2;;
            esac
            return 0
        }
        asus_probe_restore() { cat >/dev/null; return 1; }
        asus_probe_family iptables
        ''')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('cleaned', r.stderr)

    def test_direction_probe_classifies_packets_and_cleans_its_hook(self):
        # Only the unavailable kernel boundary is doubled; rule generation,
        # counter interpretation, result and cleanup are the real shell code.
        body = '''
        iptables() {
            case "$*" in
              *' -L '*) printf 'Chain probe (1 references)\n pkts bytes target prot opt in out source destination\n1 84 all\n%s 84 all\n%s 84 all\n' "$ORIGINAL" "$REPLY";;
              *' -D OUTPUT '*) echo detached >&2;;
              *' -X '*) echo removed >&2;;
            esac
            return 0
        }
        asus_probe_ping() { return 0; }
        asus_probe_direction iptables
        '''
        for original, reply, expected in [('1', '0', 'normal'), ('0', '1', 'reverse')]:
            r = self.run_sh(body, {'ORIGINAL': original, 'REPLY': reply})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), expected)
            self.assertIn('detached', r.stderr)
            self.assertIn('removed', r.stderr)
        r = self.run_sh(body, {'ORIGINAL': '0', 'REPLY': '0'})
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, '')
        self.assertIn('detached', r.stderr)

    def test_observed_reverse_direction_changes_selection_not_client_scope(self):
        r = self.run_sh(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='192.0.2.10/32'") + '''
        ASUS_CT4=reverse; ASUS_WAN=vlan2; asus_rules 4 mangle
        ''')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('-o vlan2 -m conntrack --ctdir REPLY --ctorigsrc 192.0.2.10/32 -j nfqa_out', r.stdout)
        self.assertIn('-i vlan2 -m conntrack --ctdir ORIGINAL --ctorigsrc 192.0.2.10/32 -j nfqa_in', r.stdout)
        self.assertIn('--connbytes-dir original', r.stdout)


if __name__ == '__main__':
    unittest.main()
