"""Opt-in integration against a disposable official OpenWrt rootfs container.

Set NFQWS_TEST_DOCKER to its name. Never run against a router/host namespace.
This verifies native userspace and nft transactions, not target hardware.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
CONTAINER=os.environ.get('NFQWS_TEST_DOCKER')


@unittest.skipUnless(CONTAINER,'Requires an isolated OpenWrt test container')
class OpenWrtNativeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
        if not CONTAINER.startswith('nfqws-openwrt') or spec['HostConfig']['NetworkMode']=='host':
            raise RuntimeError('Refusing a non-test or host-network container')
        cls.sh('mkdir -p /usr/lib/nfqws2 /etc/nfqws2; chmod 700 /etc/nfqws2')
        for name in ['control.sh','platform.sh','firewall.sh','config.php','config-cli.php','flow.php','flow-cli.php']:
            cls.write('/usr/lib/nfqws2/'+name,(ROOT/'openwrt'/name).read_text())
        cls.write('/usr/lib/nfqws2/import-config.php',(ROOT/'webui/web/public/import-config.php').read_text())
        args=re.search(r'^_startup_args\(\) \{.*?^\}',(ROOT/'core/etc/init.d/common').read_text(),re.M|re.S).group()
        cls.write('/usr/lib/nfqws2/args.sh',args+'\n')
        cls.sh('mkdir -p /usr/lib/nfqws2/update /usr/share/nfqws2-web; chmod 755 /usr/lib/nfqws2/update /usr/share/nfqws2-web')
        for name in ['service-guard.php','service-lease.sh']:cls.write('/usr/lib/nfqws2/update/'+name,(ROOT/'openwrt/update'/name).read_text())
        for source in (ROOT/'webui/web/public').glob('*.php'):cls.write('/usr/share/nfqws2-web/'+source.name,source.read_text())
        cls.write('/usr/share/nfqws2-web/platform-profile.json','{"schema_version":1,"platform":"openwrt"}')
        cls.sh('chmod 755 /usr/lib/nfqws2/control.sh')
        # A process-boundary fixture, never a fake parser/firewall implementation.
        cls.write('/usr/bin/nfqws2',"""#!/bin/sh
[ "$1" = --dry-run ] || exit 1
printf '%s\\n' "$@" > /tmp/nfqws-preflight-argv
exit 0
""")
        cls.sh('chmod 755 /usr/bin/nfqws2')

    @staticmethod
    def sh(script,input=None,check=True):
        return subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',script],input=input,text=True,
                              capture_output=True,check=check,timeout=20)

    @classmethod
    def write(cls,path,text):
        cls.sh('cat > '+path,input=text)

    def test_preflight_quotes_data_and_failure_preserves_prior_launch(self):
        config='USER=nobody\nNFQUEUE_NUM=300\nNFQWS_ARGS="--filter-tcp=443 --comment=O\'Reilly"\n'
        self.write('/etc/nfqws2/nfqws2.conf',config)
        self.sh('chmod 600 /etc/nfqws2/nfqws2.conf; /usr/lib/nfqws2/control.sh preflight')
        before=self.sh('cat /var/run/nfqws2-native/launch.env').stdout
        argv=self.sh(". /var/run/nfqws2-native/launch.env; set -f; set -- $NFQWS_LAUNCH_ARGS; printf '%s\\n' \"$@\"").stdout
        self.assertIn("--comment=O'Reilly\n",argv)
        self.assertIn('--dry-run\n',self.sh('cat /tmp/nfqws-preflight-argv').stdout)
        self.write('/etc/nfqws2/nfqws2.conf',config+'\nUSER=$(touch /tmp/NATIVE_CONFIG_EXECUTED)\n')
        failed=self.sh('/usr/lib/nfqws2/control.sh preflight',check=False)
        self.assertNotEqual(failed.returncode,0)
        self.assertEqual(before,self.sh('cat /var/run/nfqws2-native/launch.env').stdout)
        self.sh('test ! -e /tmp/NATIVE_CONFIG_EXECUTED')

    def test_nft_atomic_apply_reload_and_restore_keeps_other_fw4_rules(self):
        script='''
set -e
. "$PWD/source/project/openwrt/firewall.sh"
NFQWS_RUN=/tmp/nfqws-native-nft; mkdir -p "$NFQWS_RUN"; chmod 700 "$NFQWS_RUN"
NFQWS_LIB="$PWD/source/project/openwrt"
NFQUEUE_NUM=300; TCP_PORTS=80,443; UDP_PORTS=443,3478:3481; IPV6_ENABLED=1
ASUS_CLIENT_MODE=include; ASUS_CLIENTS4='192.168.87.10 192.168.87.20/32'; ASUS_CLIENTS6='2001:db8::/64'
NFQWS_WAN='pppoe-wan eth0.20'
nft -j list table inet fw4 > "$NFQWS_RUN/before.json"
nfqws_firewall_apply
nfqws_flow_probe; test "$NFQWS_FLOW_STATE" = managed
nfqws_firewall_apply
nfqws_firewall_stop
nfqws_flow_probe; test "$NFQWS_FLOW_STATE" = system
nft -j list table inet fw4 > "$NFQWS_RUN/after.json"
'''
        self.sh(script)
        docs=[json.loads(self.sh(f'cat /tmp/nfqws-native-nft/{name}.json').stdout) for name in ['before','after']]
        def semantics(doc):
            def clean(value):
                if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k!='handle'}
                if isinstance(value,list):return [clean(v) for v in value]
                return value
            return clean(doc)
        self.assertEqual(semantics(docs[0]),semantics(docs[1]))


if __name__=='__main__':unittest.main()
