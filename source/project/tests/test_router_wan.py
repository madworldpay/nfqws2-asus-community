"""Local WAN discovery must show real active addresses, never guess LAN or NVRAM IP."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC


class RouterWanTests(unittest.TestCase):
    def collect(self, nvram, links, addresses, addr_rc=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = {}
            for name, data, rc in [('nvram', nvram, 0), ('links', links, 0), ('addr4', addresses, addr_rc)]:
                path = root / name
                path.write_text("#!/bin/sh\ncat <<'LOCAL_FIXTURE'\n" + data + "\nLOCAL_FIXTURE\nexit " + str(rc) + "\n")
                path.chmod(0o700)
                commands[name] = [str(path)]
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            code = '''$file=$argv[1].'/router-wan.php';if(!is_file($file)){echo json_encode(['missing'=>true]);exit;}
            require $file;echo json_encode((new AsusRouterWan(new AsusReportIO(['commands'=>json_decode($argv[2],true)])))->collect());'''
            result = subprocess.run([PHP, '-n', '-r', code, str(PUBLIC), json.dumps(commands)], capture_output=True, text=True, timeout=8)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr, '')
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            return json.loads(result.stdout)

    def test_real_private_wan_address_is_shown_and_lan_is_not(self):
        actual = self.collect('wan0_state_t=2\nwan0_proto=dhcp\nwan0_ifname=eth1\nwan0_ipaddr=8.8.8.8\npassword=SECRET',
            '2: eth1: <BROADCAST,UP> mtu 1500\n3: br0: <UP> mtu 1500',
            '2: eth1 inet 192.168.2.2/24 brd 192.168.2.255 scope global eth1\n3: br0 inet 192.168.1.1/24 scope global br0')
        self.assertEqual(actual, {'schema_version': 1, 'state': 'available', 'addresses': [{'interface': 'eth1', 'address': '192.168.2.2'}]})
        self.assertNotIn('SECRET', json.dumps(actual))

    def test_dual_wan_uses_ppp_and_active_gateway_fallback_without_duplicates(self):
        actual = self.collect('wan0_state_t=2\nwan0_proto=pppoe\nwan0_ifname=eth0\nwan0_pppoe_ifname=ppp0\nwan1_state_t=2\nwan1_proto=dhcp\nwan1_ifname=gone\nwan1_gw_ifname=eth2',
            '2: ppp0: <POINTOPOINT,UP> mtu 1492\n3: eth2@eth0: <UP> mtu 1500\n4: eth0: <UP> mtu 1500',
            '2: ppp0 inet 203.0.113.8 peer 1.1.1.1/32 scope global ppp0\n3: eth2@eth0 inet 100.64.1.2/24 scope global eth2\n3: eth2@eth0 inet 100.64.1.2/24 scope global eth2\n4: eth0 inet 192.168.9.2/24 scope global eth0')
        self.assertEqual(actual['addresses'], [{'interface': 'ppp0', 'address': '203.0.113.8'}, {'interface': 'eth2', 'address': '100.64.1.2'}])
        self.assertEqual(actual['state'], 'available')

    def test_down_unknown_and_missing_wan_never_guess_lan_as_wan(self):
        for nvram in ['wan0_state_t=0\nwan0_ifname=eth1', 'wan0_state_t=2\nwan0_ifname=eth1', '']:
            actual = self.collect(nvram, '2: eth1: <BROADCAST> mtu 1500\n3: br0: <UP> mtu 1500', '3: br0 inet 192.168.1.1/24 scope global br0')
            self.assertEqual(actual['addresses'], [])
            self.assertEqual(actual['state'], 'unavailable')

    def test_partial_command_output_is_not_presented_as_current_wan(self):
        actual = self.collect('wan0_state_t=2\nwan0_ifname=eth1', '2: eth1: <UP> mtu 1500', '2: eth1 inet 192.168.2.2/24 scope global eth1', 1)
        self.assertEqual(actual['state'], 'unavailable')
        self.assertEqual(actual['addresses'], [])
