import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


class Overlay(unittest.TestCase):
    def patch(self):
        path=HERE/'native_overlay.py'
        self.assertTrue(path.exists(),'missing native integration')
        spec=importlib.util.spec_from_file_location('device_overlay',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.patch_native({key:(ROOT/'openwrt'/name).read_text()for key,name in [
            ('init','nfqws2.init'),('control','control.sh'),('firewall','firewall.sh')]})

    def test_native_hooks_parse_and_all_instances_share_normal_stop_boundary(self):
        result=self.patch()
        with tempfile.TemporaryDirectory()as temp:
            for key,value in result.items():
                path=Path(temp)/key;path.write_text(value)
                subprocess.run(['/bin/sh','-n',str(path)],check=True,capture_output=True)
        self.assertIn('nfqws_lab_instances',result['init'])
        self.assertIn('nfqws_lab_check',result['init'])
        self.assertNotIn('killall',result['init'])

    def test_index_keeps_normal_auth_and_blocks_update_only_at_mutation_boundary(self):
        path=HERE/'native_overlay.py';spec=importlib.util.spec_from_file_location('device_overlay',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertTrue(hasattr(module,'patch_index'),'missing authenticated dispatcher integration')
        source=(ROOT/'webui/web/public/index.php').read_text()
        result=module.patch_index(source,(HERE/'dispatcher-hook.php.inc').read_text())
        self.assertIn('AsusUpdateApi::validate($_POST)',result)
        self.assertIn('experimental_runtime_active',result)
        self.assertIn('deviceprofilesapply',result)
        self.assertEqual(result.count('NFQWS_DEVICE_PROFILES_EXPERIMENT_UPDATE'),1)

    def test_real_native_render_keeps_exclusions_before_profile_dispatch(self):
        result=self.patch()
        with tempfile.TemporaryDirectory()as temp:
            directory=Path(temp)
            (directory/'rules-definitions.nft').write_text(' set dp_0_4 { type ipv4_addr; elements = { 192.168.87.20 }; }\n chain dp_0_original { queue num 41000 bypass\n return\n }\n chain dp_0_reply { queue num 41000 bypass\n return\n }\n')
            (directory/'rules-original.nft').write_text('ct original ip saddr @dp_0_4 goto dp_0_original\n')
            (directory/'rules-reply.nft').write_text('ct original ip saddr @dp_0_4 goto dp_0_reply\n')
            firewall=directory/'firewall.sh'
            firewall.write_text(result['firewall'].replace('/usr/lib/nfqws2/device-profiles-native.sh',str(HERE/'device-profiles-native.sh')))
            env=os.environ|{'NFQWS_LAB_RUN':temp,'NFQUEUE_NUM':'300','IPV6_ENABLED':'0',
                'ASUS_CLIENT_MODE':'exclude','ASUS_CLIENTS4':'192.168.87.30','ASUS_CLIENTS6':'',
                'TCP_PORTS':'80,443','UDP_PORTS':'443','NFQWS_WAN':'wan0'}
            p=subprocess.run(['/bin/sh','-c','. "$1"; nfqws_render_rules','test',str(firewall)],env=env,text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'')
            for direction in ['original','reply']:
                section=p.stdout.split(' chain '+direction+' {')[1].split('\n }')[0]
                self.assertLess(section.index('saddr @clients4 return'),section.index('goto dp_0_'+direction))
                self.assertLess(section.index('goto dp_0_'+direction),section.index('queue num 300 bypass'))

if __name__=='__main__':unittest.main()
