"""NF_ACCEPT resumes at the next table hook, not the next iptables rule.

The old ASUS observer swallowed client TLS before the core queue. Exercise
the actual rule renderer/install entry and this narrow kernel contract.
"""
import ipaddress
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IpHealthHookCoexistenceTests(unittest.TestCase):
    def installed_rules(self, mode='include', reverse=False, policy='ACCEPT'):
        with tempfile.TemporaryDirectory() as directory:
            script = f'''
set -f
. {shlex.quote(str(ROOT / 'ip-health/runtime.sh'))}
ASUS_WAN=eth0; ASUS_HEALTH_LAN=br0; ASUS_HEALTH_QUEUE=301
ASUS_CLIENT_MODE={mode}; ASUS_CLIENTS4=192.168.1.3; ASUS_CLIENTS6=''
ASUS_CT4={'reverse' if reverse else 'normal'}; ASUS_CT6=normal
ASUS_HEALTH_PRIVATE={shlex.quote(directory)}
iptables() {{ case "$*" in *' -S '*) for name; do :; done; printf -- '-P %s {policy}\\n' "$name";; *) printf '%s\\n' "$*";; esac; }}
asus_ip_health_firewall_family 4
'''
            result = subprocess.run(['sh', '-c', script], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
        direction = 'REPLY' if reverse else 'ORIGINAL'
        reply = 'ORIGINAL' if reverse else 'REPLY'
        selector = [] if mode == 'all' else ['-m', 'conntrack', '--ctorigsrc', '192.168.1.3']
        chains = {name: [] for name in ['PREROUTING', 'POSTROUTING', 'FORWARD', 'INPUT', 'OUTPUT']}
        for name in ['FORWARD', 'INPUT', 'OUTPUT']:
            chains[name].append(['-j', 'FOREIGN_MARK'])
        for name, iface, ct in [('PREROUTING', '-i', reply), ('POSTROUTING', '-o', direction)]:
            if mode == 'exclude':
                chains[name].append(selector + ['-j', 'RETURN'])
            chains[name].append([iface, 'eth0', '-p', 'tcp', '-m', 'conntrack', '--ctdir', ct] +
                                (selector if mode == 'include' else []) + ['-j', 'NFQUEUE', '--queue-num', '300'])
        for line in result.stdout.splitlines():
            args = shlex.split(line)
            if '-N' in args:
                chains[args[args.index('-N') + 1]] = []
            elif '-A' in args or '-I' in args:
                op = '-A' if '-A' in args else '-I'
                offset = args.index(op)
                name = args[offset + 1]
                rule = args[offset + 2:]
                if op == '-I':
                    position = int(rule.pop(0)) - 1 if rule and rule[0].isdigit() else 0
                    chains[name].insert(position, rule)
                else:
                    chains[name].append(rule)
        return chains

    def traverse(self, chains, hooks, packet):
        visits = []

        def matches(rule):
            for flag, key in [('-i', 'input'), ('-o', 'output'), ('-p', 'protocol'),
                              ('--sport', 'sport'), ('--dport', 'dport'), ('--ctdir', 'direction')]:
                if flag in rule and str(packet[key]) != rule[rule.index(flag) + 1]:
                    return False
            for flag, key in [('-s', 'src'), ('-d', 'dst'), ('--ctorigsrc', 'client')]:
                if flag in rule and ipaddress.ip_address(packet[key]) not in ipaddress.ip_network(rule[rule.index(flag) + 1], strict=False):
                    return False
            if '--mark' in rule:
                value, mask = rule[rule.index('--mark') + 1].split('/')
                if packet.get('mark', 0) & int(mask, 0) != int(value, 0):
                    return False
            return True

        def chain(name):
            for rule in chains[name]:
                if not matches(rule):
                    continue
                target = rule[rule.index('-j') + 1]
                if target == 'RETURN':
                    return False
                if target == 'FOREIGN_MARK':
                    visits.append('foreign')
                elif target == 'NFQUEUE':
                    visits.append(int(rule[rule.index('--queue-num') + 1]))
                    return True  # NF_ACCEPT ends this table's hook traversal.
                elif chain(target):
                    return True
            return False

        for hook in hooks:
            chain(hook)
        return visits

    def test_https_visits_both_queues_without_skipping_existing_mangle_rules(self):
        for reverse in [False, True]:
            for kind, hooks, incoming, local in [
                ('transit outgoing', ['FORWARD', 'POSTROUTING'], False, False),
                ('transit reply', ['PREROUTING', 'FORWARD'], True, False),
                ('router outgoing', ['OUTPUT', 'POSTROUTING'], False, True),
                ('router reply', ['PREROUTING', 'INPUT'], True, True),
            ]:
                with self.subTest(reverse=reverse, path=kind):
                    client = '192.168.1.3'
                    packet = {'input': 'eth0' if incoming else ('' if local else 'br0'),
                              'output': ('' if local else 'br0') if incoming else 'eth0',
                              'src': '142.251.151.4' if incoming else client,
                              'dst': client if incoming else '142.251.151.4',
                              'client': client, 'protocol': 'tcp',
                              'sport': 443 if incoming else 50000, 'dport': 50000 if incoming else 443,
                              'direction': ('ORIGINAL' if reverse else 'REPLY') if incoming else ('REPLY' if reverse else 'ORIGINAL')}
                    visits = self.traverse(self.installed_rules(reverse=reverse), hooks, packet)
                    self.assertEqual(sorted(x for x in visits if isinstance(x, int)), [300, 301], visits)
                    self.assertIn('foreign', visits, visits)
                    self.assertLess(visits.index('foreign'), visits.index(301), visits)


    def test_client_scope_vpn_and_local_marks_remain_fail_open(self):
        packet = {'input': 'br0', 'output': 'eth0', 'src': '192.168.1.4', 'dst': '142.251.151.4',
                  'client': '192.168.1.4', 'protocol': 'tcp', 'sport': 50000, 'dport': 443, 'direction': 'ORIGINAL'}
        for mode, expected in [('include', []), ('exclude', [300, 301]), ('all', [300, 301])]:
            with self.subTest(mode=mode):
                visits = self.traverse(self.installed_rules(mode), ['FORWARD', 'POSTROUTING'], packet)
                self.assertEqual(sorted(x for x in visits if isinstance(x, int)), expected)
        packet.update(src='192.168.1.3', client='192.168.1.3')
        visits = self.traverse(self.installed_rules('exclude'), ['FORWARD', 'POSTROUTING'], packet)
        self.assertEqual([x for x in visits if isinstance(x, int)], [])
        packet.update(output='tun11')
        visits = self.traverse(self.installed_rules(), ['FORWARD', 'POSTROUTING'], packet)
        self.assertEqual([x for x in visits if isinstance(x, int)], [])
        packet.update(input='', output='eth0', mark=0x100)
        visits = self.traverse(self.installed_rules(), ['OUTPUT', 'POSTROUTING'], packet)
        self.assertNotIn(301, visits, 'local policy-marked TLS must not be attributed to the initial WAN route')

    def test_dns_observes_selected_client_reply_once_and_leaves_other_uplinks_alone(self):
        packet = {'input': 'eth0', 'output': 'br0', 'src': '8.8.8.8', 'dst': '192.168.1.3',
                  'client': '192.168.1.3', 'protocol': 'udp', 'sport': 53, 'dport': 50000, 'direction': 'REPLY'}
        visits = self.traverse(self.installed_rules(), ['PREROUTING', 'FORWARD'], packet)
        self.assertEqual([x for x in visits if isinstance(x, int)], [301])
        for interface in ['tun11', 'wg0', 'br1']:
            packet['input'] = interface
            visits = self.traverse(self.installed_rules(), ['PREROUTING', 'FORWARD'], packet)
            self.assertEqual([x for x in visits if isinstance(x, int)], [])
        packet.update(input='', src='192.168.1.1')
        visits = self.traverse(self.installed_rules(), ['OUTPUT', 'POSTROUTING'], packet)
        self.assertEqual([x for x in visits if isinstance(x, int)], [301])
        packet['dst'] = '192.168.1.4'
        visits = self.traverse(self.installed_rules(), ['OUTPUT', 'POSTROUTING'], packet)
        self.assertEqual([x for x in visits if isinstance(x, int)], [])

    def test_cleanup_removes_old_and_new_owned_hooks(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'chains4').write_text('nfqh_pre\nnfqh_post\nnfqh_forward\nnfqh_local\nnfqh_in\nnfqh_out\n')
            body = '. ' + shlex.quote(str(ROOT / 'ip-health/runtime.sh')) + '\n' + f"""
ASUS_HEALTH_PRIVATE={shlex.quote(directory)}
ls() {{ printf '%s\\n' '-rw------- 1 0 0 10 marker'; }}
iptables() {{ printf '%s\\n' "$*" >> "$ASUS_HEALTH_PRIVATE/calls"; case "$*" in *' -D '*) return 1;; esac; }}
asus_ip_health_firewall_stop
"""
            result = subprocess.run(['sh', '-c', body], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (base / 'calls').read_text()
            for hook in ['PREROUTING -j nfqh_pre', 'POSTROUTING -j nfqh_post',
                         'INPUT -j nfqh_pre', 'FORWARD -j nfqh_forward',
                         'OUTPUT -j nfqh_local', 'OUTPUT -m mark --mark 0x0/0xffffffff -j nfqh_post']:
                self.assertIn('-D ' + hook, calls)
            self.assertFalse((base / 'chains4').exists())

    def test_nonaccept_mangle_policy_refuses_observer_without_owning_chains(self):
        with tempfile.TemporaryDirectory() as directory:
            script = '. ' + shlex.quote(str(ROOT / 'ip-health/runtime.sh')) + '\n' + f"""
ASUS_HEALTH_PRIVATE={shlex.quote(directory)}
iptables() {{
  case "$*" in *' -S '*) for name; do :; done; printf -- '-P %s DROP\\n' "$name";;
  *) printf '%s\\n' "$*" >> "$ASUS_HEALTH_PRIVATE/mutations";; esac
}}
asus_ip_health_firewall_family 4
"""
            result = subprocess.run(['sh', '-c', script], capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(Path(directory).iterdir()), [], 'unsupported base policy must not create or attach anything')

    def test_observers_never_hold_and_raw_replay_packets_past_core(self):
        for platform in ['asus', 'openwrt']:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                (base / 'private').mkdir()
                (base / 'public/events').mkdir(parents=True)
                (base / 'runtime.conf').write_text('UNCHANGED=1\n')
                (base / 'config.env').write_text('UNCHANGED=1\n')
                (base / 'pid').write_text('41\n')
                engine = base / 'engine'
                engine.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > ' + shlex.quote(str(base / 'argv')) + '\nexit 1\n')
                engine.chmod(0o700)
                path = ROOT / ('ip-health/runtime.sh' if platform == 'asus' else 'openwrt/ip-health-runtime.sh')
                body = '. ' + shlex.quote(str(path)) + '\n' + f"""
RUN_DIR={shlex.quote(directory)}; NFQWS_RUN="$RUN_DIR"; PIDFILE="$RUN_DIR/pid"
ASUS_HEALTH_PRIVATE="$RUN_DIR/private"; ASUS_HEALTH_PUBLIC="$RUN_DIR/public"
NFQWS_HEALTH_PRIVATE="$RUN_DIR/private"; NFQWS_HEALTH_PUBLIC="$RUN_DIR/public"
ASUS_HEALTH_LIB={shlex.quote(str(ROOT / 'ip-health'))}; NFQWS_HEALTH_LIB="$ASUS_HEALTH_LIB"
NFQWS_BIN={shlex.quote(str(engine))}; NFQUEUE_NUM=300; IPV6_ENABLED=0; ASUS_WAN=eth0; USER=$(id -u)
asus_running() {{ return 0; }}
asus_ip_health_directory() {{ return 0; }}
nfqws_health_directory() {{ return 0; }}
asus_ip_health_stop() {{ return 0; }}
nfqws_health_stop() {{ return 0; }}
asus_interface_valid() {{ return 0; }}
nfqws_process_pid() {{ echo 41; }}
nfqws_queue_facts() {{ echo 'unbound null null'; }}
nfqws_uplinks() {{ echo eth0; }}
nvram() {{ [ "$2" != lan_ifname ] || echo br0; }}
ip() {{ echo 'eth0 inet 93.184.216.34'; }}
awk() {{ case "$*" in *nfnetlink_queue*) return 1;; *) /usr/bin/awk "$@";; esac; }}
asus_ip_health_php() {{ [ "$1" != healthy ]; }}
nfqws_health_php() {{ return 0; }}
{'asus_ip_health_start' if platform == 'asus' else 'nfqws_health_start'}
"""
                result = subprocess.run(['sh', '-c', body], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 1, result.stderr)
                args = (base / 'argv').read_text().splitlines()
                self.assertIn('--reasm-disable', args, 'observer must pass partial TLS/QUIC to the core unchanged')
                self.assertLess(args.index('--reasm-disable'), args.index('--filter-tcp=443'))


if __name__ == '__main__':
    unittest.main()
