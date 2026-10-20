"""Checkup must distinguish missing evidence, platform blockers and DNS readiness."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC


class RouterCheckupTests(unittest.TestCase):
    def collect(self, files=None, nvram='', readonly=False, installed=False):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            for name in ['proc','opt','tmp','etc','sys','jffs','ark']:
                (r/name).mkdir()
            data = {'proc/meminfo':'MemTotal: 262144 kB\nMemAvailable: 100000 kB\nMemFree: 80000 kB\n',
                    'proc/modules':'nfnetlink_queue 100 0 - Live 0\n',
                    'proc/sys/kernel/osrelease':'2.6.36.4\n',
                    'proc/net/netfilter/nfnetlink_queue':'300 123 0 2 65535 0 0 7 1\n',
                    'opt/etc/opkg.conf':'arch all 100\narch armv7-2.6 150\n',
                    'opt/etc/nfqws2/nfqws2.conf':'NFQUEUE_NUM=300\n',
                    'opt/lib/opkg/info/nfqws2-asus.control':'Version: 1.3.1-asus6+b30\n',
                    'opt/etc/ssl/certs/ca-certificates.crt':'fixture\n',
                    'tmp/resolv.conf':'nameserver 127.0.0.1\n',
                    'tmp/resolv.dnsmasq':'nameserver 9.9.9.9\n',
                    'proc/mounts':f'/dev/sda1 {r}/opt ext4 {"ro" if readonly else "rw"},relatime 0 0\n/dev/mtdblock4 {r}/jffs jffs2 rw 0 0\n'}
            data.update(files or {})
            for name, value in data.items():
                if value is None:
                    continue
                q = r/name; q.parent.mkdir(parents=True, exist_ok=True); q.write_text(value)
            script = r/'nvram'; script.write_text("#!/bin/sh\ncat <<'FIXTURE'\nproductid=RT-AC87U\nfirmver=3.0.0.4\nbuildno=384\nextendno=13_10\njffs2_scripts=1\n"+nvram+"\nFIXTURE\n"); script.chmod(0o700)
            before = {str(p.relative_to(r)):p.read_bytes() for p in r.rglob('*') if p.is_file()}
            code = '''$file=$argv[1].'/router-checkup.php';if(!is_file($file)){echo json_encode(['error'=>'missing_checkup']);exit;}
            require $file;$r=$argv[2];$roots=[];foreach(['proc','opt','tmp','etc','sys','jffs','ark'] as $n)$roots[$n]=$r.'/'.$n;
            $roots['commands']=['nvram'=>[$r.'/nvram'],'machine'=>['/bin/echo','armv7l']];
            echo json_encode((new AsusRouterCheckup(new AsusReportIO($roots),['installed'=>fn()=>$argv[3]==='yes','installer_availability'=>fn()=>['available'=>true,'code'=>'ready'],'now'=>fn()=>1792400000]))->collect());'''
            p = subprocess.run([PHP,'-n','-r',code,str(PUBLIC),d,'yes' if installed else 'no'],capture_output=True,text=True,timeout=8)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr); self.assertEqual(p.stderr,'')
            self.assertEqual(before,{str(p.relative_to(r)):p.read_bytes() for p in r.rglob('*') if p.is_file()})
            return json.loads(p.stdout)

    def item(self, v, id):
        self.assertNotIn('error',v)
        return next(x for x in v['items'] if x['id']==id)

    def test_omitted_queue_uses_package_default_but_invalid_stays_unknown(self):
        for value,number,bound in [('NFQWS_ARGS="--filter-tcp=443"\n',300,True),
                ('NFQUEUE_NUM=""\n',None,False),('NFQUEUE_NUM=65536\n',None,False),
                ('f(){\nNFQWS_ARGS="--filter-tcp=443"\n}\n',None,False)]:
            with self.subTest(value=value):
                v=self.collect({'opt/etc/nfqws2/nfqws2.conf':value})
                facts=self.item(v,'nfqueue')['facts']
                self.assertEqual(facts['number'],number)
                self.assertEqual(facts['bound'],bound)

    def test_legacy_missing_memavailable_is_estimate(self):
        v = self.collect({'proc/meminfo':'MemTotal: 262144 kB\nMemFree: 70000 kB\nBuffers: 1000 kB\nCached: 10000 kB\n'})
        m = self.item(v,'memory')['facts']
        self.assertTrue(m['available_estimated'])
        self.assertGreaterEqual(m['available_kib'],70000)
        self.assertEqual(m['installer_reserve_kib'],65536)
        self.assertFalse(m['router_minimum_memory_claimed'])

    def test_unknown_ark_flag_is_information(self):
        v = self.collect()
        self.assertEqual(self.item(v,'ark')['facts']['loaded'],False)
        flags = self.item(v,'ark_flags')
        self.assertEqual(flags['state'],'info')
        self.assertIsNone(flags['facts']['ark_ids_enable'])
        self.assertEqual(flags['action_code'],'unknown_flag_is_not_failure')

    def test_nfq_missing_does_not_block_smartdns(self):
        v = self.collect({'proc/modules':'','proc/net/netfilter/nfnetlink_queue':None})
        self.assertFalse(self.item(v,'nfqueue')['facts']['bound'])
        self.assertFalse(v['readiness']['nfqws2']['ready'])
        self.assertTrue(v['readiness']['smartdns_install']['ready'])
        self.assertEqual(v['schema_version'],1)

    def test_foreign_dns_is_a_connect_conflict(self):
        v = self.collect({'opt/etc/smartdns/smartdns.conf':'server-https https://PRIVATE_TOKEN.example/dns-query?secret=CANARY\n'})
        self.assertTrue(self.item(v,'dns_runtime')['facts']['external_smartdns'])
        self.assertFalse(v['readiness']['smartdns_connect']['ready'])
        self.assertIn('external_smartdns',v['readiness']['smartdns_connect']['codes'])
        self.assertNotIn('CANARY',json.dumps(v))

    def test_readonly_opt_blocks_install_without_test_write(self):
        v = self.collect(readonly=True)
        self.assertEqual(self.item(v,'storage_opt')['state'],'attention')
        self.assertFalse(self.item(v,'storage_opt')['facts']['writable_estimate'])
        self.assertIn('opt_readonly',v['readiness']['smartdns_install']['codes'])

    def test_queue_number_alone_is_not_a_binding(self):
        v = self.collect({'proc/net/netfilter/nfnetlink_queue':'300 0 0 2 65535 0 0 0 1\n'})
        self.assertFalse(self.item(v,'nfqueue')['facts']['bound'])

    def test_installer_memory_reserve_does_not_block_an_installed_engine(self):
        v = self.collect({'proc/meminfo':'MemTotal: 262144 kB\nMemAvailable: 40000 kB\n'},installed=True)
        self.assertFalse(v['readiness']['smartdns_install']['ready'])
        self.assertTrue(v['readiness']['smartdns_connect']['ready'])

    def test_mounted_proc_symlink_is_confined_to_numeric_task(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d); (r/'proc/123').mkdir(parents=True)
            (r/'proc/123/mounts').write_text('fixture')
            (r/'proc/mounts').symlink_to('123/mounts')
            code = "require $argv[1].'/support-report-io.php';echo json_encode((new AsusReportIO(['proc'=>$argv[2]]))->read('mounts'));"
            def read():
                p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(r/'proc')],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr)
                return json.loads(p.stdout)
            self.assertEqual(read(),{'state':'available','value':'fixture'})
            (r/'proc/mounts').unlink(); (r/'outside').write_text('SECRET')
            (r/'proc/mounts').symlink_to(r/'outside')
            self.assertEqual(read()['state'],'denied')

    def test_hooks_have_separate_purposes_and_no_laboratory_recommendation(self):
        v = self.collect({'jffs/scripts/dnsmasq.postconf':'#!/bin/sh\nexit 0\n',
                          'jffs/scripts/post-mount':'#!/bin/sh\n# foreign\n'})
        hooks = self.item(v,'hooks')['facts']['items']
        purposes = {h['id']:h['purpose'] for h in hooks}
        self.assertEqual(purposes['dnsmasq_postconf'],'dns_forwarding')
        self.assertEqual(purposes['post_mount'],'opt_ready_start')
        self.assertEqual(purposes['firewall_start'],'firewall_reapply_if_used')
        self.assertNotIn('192.168.1.50',json.dumps(v))
        self.assertIn('check_hook_conflicts',v['readiness']['smartdns_connect']['codes'])

    def test_missing_dns_hook_is_not_a_smartdns_install_requirement(self):
        v = self.collect({'proc/modules':'', 'jffs/scripts/dnsmasq.postconf':None})
        self.assertTrue(v['readiness']['smartdns_install']['ready'])
        facts = self.item(v,'hooks')['facts']
        self.assertFalse(facts['smartdns_itself_requires_hook'])
        self.assertEqual(facts['selected_forwarding_method'],'merlin_dnsmasq_postconf')
        self.assertTrue(facts['selected_method_requires_postconf'])
        self.assertFalse(facts['local_forwarding_requires_firewall_hook'])

    def test_existing_hook_does_not_claim_boot_or_guest_network_success(self):
        v = self.collect({'jffs/scripts/dnsmasq.postconf':'#!/bin/sh\n# BEGIN NFQWS2 SMARTDNS MANAGED\n',
                          'jffs/scripts/post-mount':'#!/bin/sh\n# already starts Entware\n'})
        facts = self.item(v,'hooks')['facts']
        self.assertFalse(facts['boot_tested'])
        self.assertEqual(facts['dns_scope'],'primary_lan')
        self.assertFalse(facts['guest_sdn_vpn_tested'])
        self.assertTrue(facts['opt_readiness_required'])

    def test_dns_rss_is_separate_and_missing_measurement_is_not_zero(self):
        v = self.collect({'proc/101/comm':'smartdns\n',
                          'proc/101/status':'Name:\tsmartdns\nVmRSS:\t4096 kB\n',
                          'proc/102/comm':'dnsmasq\n',
                          'proc/102/status':'Name:\tdnsmasq\nVmRSS:\t768 kB\n',
                          'proc/103/comm':'smartdns\n',
                          'proc/104/comm':'other\n',
                          'proc/104/status':'VmRSS:\t999999 kB\nSECRET\n'})
        entries = self.item(v,'memory')['facts']['dns_process_rss']
        self.assertCountEqual(entries,[{'name':'smartdns','rss_kib':4096},
                                       {'name':'dnsmasq','rss_kib':768},
                                       {'name':'smartdns','rss_kib':None}])
        self.assertNotIn('SECRET',json.dumps(v))


if __name__=='__main__':
    unittest.main()
