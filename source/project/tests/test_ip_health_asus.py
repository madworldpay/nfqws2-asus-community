"""Execute the ASUS rule renderer and admission/cleanup boundaries in a shell."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class IpHealthAsusTests(unittest.TestCase):
    def run_sh(self,body):
        source=ROOT/'ip-health/runtime.sh';self.assertTrue(source.exists(),'ASUS IP health adapter missing')
        return subprocess.run(['sh','-c','set -f\n. '+shlex.quote(str(source))+'\n'+body],capture_output=True,text=True,timeout=5)

    def config(self,extra=''):
        return "ASUS_WAN=eth0; ASUS_HEALTH_LAN=br0; ASUS_CLIENT_MODE=all; ASUS_CLIENTS4=''; ASUS_CLIENTS6=''; ASUS_CT4=normal; ASUS_CT6=normal; ASUS_HEALTH_QUEUE=301; "+extra+'\n'

    def test_rules_use_separate_bypass_queue_and_preserve_probe_mark(self):
        p=self.run_sh(self.config()+'asus_ip_health_rules 4');self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('--queue-num 301 --queue-bypass',p.stdout)
        self.assertNotIn('--queue-num 300',p.stdout)
        self.assertIn('-m mark --mark 0x40000000/0x40000000 -j RETURN',p.stdout)
        self.assertIn('-i eth0 -m conntrack --ctdir REPLY -j nfqh_in',p.stdout)
        self.assertIn('-o eth0 -m conntrack --ctdir ORIGINAL -j nfqh_out',p.stdout)
        self.assertIn('-o br0 -p udp --sport 53',p.stdout)
        self.assertNotIn('-F ',p.stdout)

    def test_selected_clients_and_ipv6_empty_include_are_respected(self):
        p=self.run_sh(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='192.168.1.3'")+'asus_ip_health_rules 4')
        self.assertIn('--ctorigsrc 192.168.1.3',p.stdout);self.assertIn('-d 192.168.1.3',p.stdout)
        p=self.run_sh(self.config("ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='192.168.1.3'")+'asus_ip_health_rules 6')
        self.assertNotIn('--queue-num',p.stdout)
        p=self.run_sh(self.config("ASUS_CLIENT_MODE=exclude; ASUS_CLIENTS4='192.168.1.3'")+'asus_ip_health_rules 4')
        self.assertLess(p.stdout.index('--ctorigsrc 192.168.1.3 -j RETURN'),p.stdout.index('-i eth0'))
        self.assertIn('-A nfqh_local -d 192.168.1.3 -j RETURN',p.stdout)

    def test_foreign_chain_creation_failure_is_never_claimed_or_flushed(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.run_sh(self.config()+f'ASUS_HEALTH_PRIVATE={shlex.quote(folder)}\n'+'''
iptables() { printf '%s\n' "$*"; return 1; }
asus_ip_health_firewall_family 4
''')
            self.assertNotEqual(p.returncode,0);self.assertIn('-N nfqh_pre',p.stdout)
            self.assertNotIn('-F nfqh_pre',p.stdout);self.assertNotIn('-X nfqh_pre',p.stdout)
            self.assertEqual((Path(folder)/'chains4').read_text(),'')

    def test_two_active_wans_are_unavailable_even_with_one_configured_interface(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'private').mkdir();(root/'public').mkdir();(root/'runtime.conf').write_text('STRATEGY=preserved\n');(root/'pid').write_text('41\n')
            p=self.run_sh(self.config()+f'''RUN_DIR={shlex.quote(folder)}; PIDFILE="$RUN_DIR/pid"; NFQUEUE_NUM=300; IPV6_ENABLED=0
ASUS_HEALTH_PRIVATE="$RUN_DIR/private"; ASUS_HEALTH_PUBLIC="$RUN_DIR/public"; ASUS_HEALTH_LIB={shlex.quote(str(ROOT/'ip-health'))}
asus_running() {{ return 0; }}
asus_ip_health_directory() {{ return 0; }}
asus_ip_health_php() {{ echo "$*" >> "$RUN_DIR/calls"; case "$1" in healthy|available) return 1;; esac; return 0; }}
asus_interface_valid() {{ return 0; }}
nvram() {{ case "$2" in wan0_state_t|wan1_state_t) echo 2;; lan_ifname) echo br0;; esac; }}
ip() {{ echo 'eth0 inet 1.2.3.4'; }}
asus_ip_health_start
''')
            self.assertEqual(p.returncode,0,p.stderr);self.assertIn('inactive multiwan_unsupported',(root/'calls').read_text())
            self.assertEqual((root/'runtime.conf').read_text(),'STRATEGY=preserved\n')
