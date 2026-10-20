"""Read router resolver settings without contacting DNS or exporting identities."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from test_dpi_normalize import PHP,PUBLIC,ROOT
from test_support_relay_validation import fixture

class ReportDnsTests(unittest.TestCase):
    def collect(self,nvram,files=None,processes=()):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ['etc','opt','tmp','proc']:(root/name).mkdir()
            for name,value in (files or {}).items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value)
            for index,name in enumerate(processes,100):
                p=root/f'proc/{index}';p.mkdir();(p/'comm').write_text(name+'\n')
            script=root/'nvram';script.write_text('#!/bin/sh\ncat <<\'FIXTURE\'\n'+nvram+'\nFIXTURE\n');script.chmod(0o700)
            code='''require $argv[1].'/support-report-dns.php';$r=$argv[2];$io=new AsusReportIO(['etc'=>$r.'/etc','opt'=>$r.'/opt','tmp'=>$r.'/tmp','proc'=>$r.'/proc','commands'=>['nvram'=>[$r.'/nvram']]]);echo json_encode((new AsusReportDns($io,new AsusReportValues()))->collect());'''
            before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),d],capture_output=True,text=True,timeout=5)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual(p.stderr,'')
            self.assertEqual(before,{p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            return json.loads(p.stdout)
    def test_dot_configuration_generated_fallback_and_process_are_distinct(self):
        nv='''wan0_dnsenable_x=1
wan0_dns1_x=8.8.8.8
wan0_dns2_x=
wan0_dns=8.8.8.8 192.168.99.1
dnspriv_enable=1
dnspriv_profile=1
dnspriv_rulelist=<1.1.1.1>853>PRIVATE_ACCOUNT.example>PRIVATE_PIN
dhcp_dns_router=1
dhcp_dns1_x=192.168.99.1
dnsfilter_enable_x=0
dnsfilter_mode=0'''
        stubby='''dns_transport_list:
  - GETDNS_TRANSPORT_TLS
  - GETDNS_TRANSPORT_UDP
upstream_recursive_servers:
  - address_data: 1.1.1.1
    tls_port: 853
    tls_auth_name: "PRIVATE_ACCOUNT.example"
'''
        v=self.collect(nv,{'etc/stubby/stubby.yml':stubby,'tmp/resolv.dnsmasq':'nameserver 127.0.1.1\n'},['stubby'])['data']
        self.assertTrue(v['wan'][0]['automatic']);self.assertTrue(v['dot']['enabled']);self.assertEqual(v['dot']['profile'],'strict')
        self.assertEqual(v['dot']['generated_transports'],['tls','udp']);self.assertTrue(v['dot']['process_observed']);self.assertFalse(v['connectivity_tested'])
        self.assertEqual(v['dot']['configured'][0]['id'],v['dot']['generated_upstreams'][0]['id'])
        self.assertEqual(v['wan'][0]['configured'][0]['provider'],'google');self.assertEqual(v['dot']['configured'][0]['provider'],'cloudflare')
        self.assertEqual(v['lan']['configured'][0]['id'],v['wan'][0]['learned'][1]['id'])
        raw=json.dumps(v)
        for secret in ['PRIVATE_','192.168.99.1','8.8.8.8','1.1.1.1','127.0.1.1']:self.assertNotIn(secret,raw)
    def test_doh_component_and_permitted_protocol_are_not_working_claim(self):
        v=self.collect('dnspriv_enable=0\ndnspriv_profile=0\n',{'opt/etc/dnscrypt-proxy2/dnscrypt-proxy.toml':"doh_servers = true\ndnscrypt_servers = false\nserver_names = ['PRIVATE_ACCOUNT']\n[static.'PRIVATE_NAME']\nstamp = 'sdns://PRIVATE_STAMP'\n"},['dnscrypt-proxy'])['data']
        self.assertEqual(v['doh']['observed_components'],['dnscrypt-proxy']);self.assertTrue(v['doh']['configs'][0]['doh_allowed'])
        self.assertFalse(v['doh']['configs'][0]['dnscrypt_allowed']);self.assertFalse(v['dot']['enabled']);self.assertFalse(v['connectivity_tested'])
        self.assertNotIn('PRIVATE_',json.dumps(v));self.assertNotIn('working',json.dumps(v))
    def test_unknown_settings_do_not_become_disabled_and_duplicate_flags_are_unknown(self):
        v=self.collect('dnspriv_enable=1\ndnspriv_enable=0\nwan0_dnsenable_x=bad\ndnspriv_profile=bad\n')
        self.assertIsNone(v['data']['dot']['enabled']);self.assertIsNone(v['data']['wan'][0]['automatic']);self.assertEqual(v['data']['dot']['profile'],'unknown')
        self.assertEqual(v['data']['doh']['state'],'not_observed');self.assertFalse(v['data']['client_overrides_observed'])
    def test_new_section_is_optional_closed_and_valid_in_old_report_version(self):
        from jsonschema import Draft202012Validator
        v=json.loads(fixture());v['sections']['dns']=self.collect('dnspriv_enable=0\n')
        schema=json.loads((ROOT/'support/report.schema.json').read_text());validator=Draft202012Validator(schema)
        self.assertTrue(validator.is_valid(v),list(validator.iter_errors(v)))
        v['collector_version']='1.1.0';self.assertTrue(validator.is_valid(v))
        code="require $argv[1].'/support-json-schema.php';try{AsusSupportSchema::validate(stream_get_contents(STDIN),'report');echo 'valid';}catch(Throwable $e){echo $e->getMessage();}"
        p=subprocess.run([PHP,'-n','-r',code,str(PUBLIC)],input=json.dumps(v),capture_output=True,text=True)
        self.assertEqual(p.stdout,'valid');self.assertEqual(p.stderr,'')
        v['sections']['dns']['data']['ip']='192.168.99.1';self.assertFalse(validator.is_valid(v))
        old=json.loads(fixture());self.assertTrue(validator.is_valid(old))
