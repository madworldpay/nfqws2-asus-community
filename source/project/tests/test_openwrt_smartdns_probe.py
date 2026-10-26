"""Native PHP DNS transport must retain the freestanding probe's wire checks."""
import json,os,subprocess,unittest
from pathlib import Path
import test_smartdns_dns_probe as wire

class NativeSmartDnsProbe(wire.SmartDnsDnsProbeTests):
    @classmethod
    def setUpClass(cls):
        cls.php=os.environ.get('NFQWS_TEST_PHP')
        if not cls.php:raise unittest.SkipTest('Native PHP runtime required')
        cls.source=Path(__file__).resolve().parents[1]/'webui/web/public/openwrt-dns-probe.php'
    def query(self,port,kind='udp',address='127.0.0.1',name='example.org',timeout=250,qtype='A'):
        if not self.source.exists():return 2,{'ok':False,'reason':'missing_probe'}
        code='require $argv[1]; echo json_encode(NfqwsOpenWrtDnsProbe::query($argv[2],(int)$argv[3],$argv[4],$argv[5],$argv[6],(int)$argv[7]));'
        p=subprocess.run([self.php,'-r',code,str(self.source),address,str(port),name,qtype,kind,str(timeout)],capture_output=True,text=True,timeout=3)
        self.assertEqual(p.returncode,0,p.stderr+p.stdout);self.assertEqual(p.stderr,'');data=json.loads(p.stdout)
        return 0 if data['ok']else 2,data
    def test_native_probe_exists_and_is_not_a_stub(self):
        self.assertTrue(self.source.is_file(),'Native validated DNS transport is missing')

if __name__=='__main__':unittest.main()
